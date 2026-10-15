"""Per-account Xray route policy, subscription state and read-only projection."""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import ipaddress
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from backend.core.config import get_settings
from backend.services.subscription_import import (
    ImportedNode,
    SubscriptionError,
    _validate_public_url,
    fetch_subscription,
    parse_subscription,
)
from backend.services.xray_runtime import XrayRuntime, XrayRuntimeError
from backend.utils.atomic_io import read_json_safe, write_json_atomic
from backend.utils.tg_session import (
    get_account_session_string,
    get_session_mode,
    list_account_names,
)

logger = logging.getLogger("backend.account_routes")

HEALTH_INTERVAL_SECONDS = 300
CONFIRM_SECONDS = 60
GEO_TTL_SECONDS = 3600
GEO_ENDPOINT = "https://ipwho.is/"


class RouteSetupRequired(ValueError):
    """No subscription has ever been configured; account traffic must pause."""

    def __init__(self) -> None:
        super().__init__("请先在设置中配置机场订阅")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_source() -> dict[str, Any]:
    return {"status": "unconfigured", "last_refreshed_at": None, "unsupported_count": 0}


def _default_assignment(mode: str = "direct") -> dict[str, Any]:
    return {
        "mode": mode, "key": None, "generation": 0, "runtime_generation": 0,
        "created_at": time.time(), "status": "pending" if mode != "direct" else "direct",
        "latency_ms": None, "route_checked_at": None, "exit_ip": None,
        "exit_country": None, "exit_region": None, "exit_checked_at": None,
    }


async def _probe_socks_port(port: int, timeout: float = 4.0) -> float | None:
    """Time local SOCKS CONNECT to Telegram DC; no Telegram session is opened."""
    async def run() -> float:
        from pyrogram.session.internals.data_center import DataCenter

        start = time.monotonic()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            if await reader.readexactly(2) != b"\x05\x00":
                raise OSError("socks handshake")
            host, target_port = DataCenter(2, False, False, False)
            ip = ipaddress.ip_address(host)
            writer.write(bytes((5, 1, 0, 1 if ip.version == 4 else 4)) + ip.packed + target_port.to_bytes(2, "big"))
            await writer.drain()
            head = await reader.readexactly(4)
            if head[:3] != b"\x05\x00\x00":
                raise OSError("socks connect")
            size = {1: 4, 4: 16}.get(head[3])
            if head[3] == 3:
                size = (await reader.readexactly(1))[0]
            if size is None:
                raise OSError("socks address")
            await reader.readexactly(size + 2)
            return (time.monotonic() - start) * 1000
        finally:
            writer.close()
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=1)

    try:
        return await asyncio.wait_for(run(), timeout=timeout)
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
        return None


class AccountRouteService:
    def __init__(self, directory: Path | None = None, runtime: XrayRuntime | None = None) -> None:
        self.directory = directory or get_settings().resolve_base_dir() / "xray"
        self.secrets_path = self.directory / "subscriptions.json"
        self.state_path = self.directory / "routes.json"
        self.runtime = runtime or XrayRuntime(self.directory)
        self._lock = asyncio.Lock()
        self._callbacks: list[Callable[[set[str]], Any]] = []
        self._confirm_tasks: dict[str, asyncio.Task[None]] = {}
        self._geo_tasks: set[asyncio.Task[None]] = set()
        self._geo_inflight: dict[str, asyncio.Task[dict[str, str | None]]] = {}
        self._last_health = 0.0
        self._secret = read_json_safe(self.secrets_path, {})
        if not isinstance(self._secret, dict):
            self._secret = {}
        self._secret.setdefault("primary_url", None)
        self._secret.setdefault("fallback_url", None)
        self._secret.setdefault("ever_configured", bool(self._secret["primary_url"] or self._secret["fallback_url"]))
        self._secret.setdefault("latency_threshold_ms", 800)
        self._secret.setdefault("sources", {"primary": _default_source(), "fallback": _default_source()})
        self._secret.setdefault("nodes", {"primary": [], "fallback": []})
        self._state = read_json_safe(self.state_path, {})
        if not isinstance(self._state, dict):
            self._state = {}
        self._state.setdefault("assignments", {})
        self._state.setdefault("health", {})
        self._state.setdefault("generation", 0)
        self._geo_cache: dict[str, tuple[float, dict[str, str | None]]] = {}

    @staticmethod
    def _key(node: ImportedNode) -> str:
        return XrayRuntime.key(node)

    def _nodes(self) -> list[ImportedNode]:
        nodes: list[ImportedNode] = []
        for source in ("primary", "fallback"):
            for raw in self._secret["nodes"].get(source, []):
                if not isinstance(raw, dict):
                    continue
                try:
                    nodes.append(ImportedNode(raw["node_id"], raw["label"], source, raw["outbound"]))
                except (KeyError, TypeError):
                    continue
        return nodes

    def _save_secret(self) -> None:
        write_json_atomic(self.secrets_path, self._secret)
        os.chmod(self.secrets_path, 0o600)

    def _save_state(self) -> None:
        write_json_atomic(self.state_path, self._state)
        os.chmod(self.state_path, 0o600)

    def _all_accounts(self) -> set[str]:
        directory = get_settings().resolve_session_dir()
        extension = "*.session_string" if get_session_mode() == "string" else "*.session"
        durable = {path.name.removesuffix(".session_string" if get_session_mode() == "string" else ".session")
                   for path in directory.glob(extension) if path.is_file()}
        if get_session_mode() == "string":
            durable.update(name for name in list_account_names() if get_account_session_string(name))
        now = time.time()
        for name, entry in list(self._state["assignments"].items()):
            if name not in durable and now - float(entry.get("created_at") or 0) > 35 * 60:
                self._state["assignments"].pop(name, None)
        pending = set(self._state["assignments"])
        return durable | pending

    def register_change_callback(self, callback: Callable[[set[str]], Any]) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    async def _notify(self, changed: set[str]) -> None:
        if not changed:
            return
        for callback in tuple(self._callbacks):
            try:
                result = callback(set(changed))
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning("账户路由变更通知失败（%s）", type(exc).__name__)

    async def startup(self) -> None:
        async with self._lock:
            nodes = self._nodes()
            if nodes:
                try:
                    await self.runtime.replace(nodes)
                except (XrayRuntimeError, OSError) as exc:
                    logger.warning("Xray 启动失败（%s）", type(exc).__name__)
            changed = self._reconcile()
        await self._notify(changed)
        if not nodes and (self._secret["primary_url"] or self._secret["fallback_url"]):
            await self.refresh_subscriptions()
        else:
            self._schedule_geo_for_accounts(changed)
            if nodes and self.runtime.active:
                await self.health_tick()

    async def shutdown(self) -> None:
        for task in (*self._confirm_tasks.values(), *self._geo_tasks, *self._geo_inflight.values()):
            task.cancel()
        if self._confirm_tasks or self._geo_tasks or self._geo_inflight:
            await asyncio.gather(*self._confirm_tasks.values(), *self._geo_tasks, *self._geo_inflight.values(), return_exceptions=True)
        self._confirm_tasks.clear()
        self._geo_tasks.clear()
        self._geo_inflight.clear()
        self._callbacks.clear()
        await self.runtime.shutdown()

    async def get_subscription_settings(self) -> dict[str, Any]:
        return self._settings_projection()

    def _settings_projection(self) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        for source in ("primary", "fallback"):
            raw = self._secret["sources"].get(source, {})
            sources[source] = {
                "configured": bool(self._secret.get(f"{source}_url")),
                "status": str(raw.get("status") or "unconfigured"),
                "last_refreshed_at": raw.get("last_refreshed_at"),
                "usable_count": sum(1 for node in self._nodes() if node.source == source and self._state["health"].get(self._key(node), {}).get("healthy") is True),
                "unsupported_count": int(raw.get("unsupported_count") or 0),
                "label": "主订阅" if source == "primary" else "兜底订阅",
            }
        assignments = self._state["assignments"].values()
        modes = {entry.get("mode") for entry in assignments if isinstance(entry, dict)}
        route_mode = "setup_required" if not self._secret["ever_configured"] else "direct" if not modes else "mixed" if len(modes) > 1 else next(iter(modes))
        return {**sources, "latency_threshold_ms": self._secret["latency_threshold_ms"], "route_mode": route_mode}

    async def update_subscription_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(changes, dict) or set(changes) - {"primary_url", "fallback_url", "latency_threshold_ms"}:
            raise SubscriptionError("SUBSCRIPTION_SETTINGS_INVALID")
        for source in ("primary", "fallback"):
            field = f"{source}_url"
            if field in changes and changes[field] is not None and str(changes[field]).strip():
                await _validate_public_url(str(changes[field]).strip())
        if "latency_threshold_ms" in changes:
            value = changes["latency_threshold_ms"]
            if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 10000:
                raise SubscriptionError("LATENCY_THRESHOLD_INVALID")
        changed_url = False
        async with self._lock:
            for source in ("primary", "fallback"):
                field = f"{source}_url"
                if field in changes:
                    new_url = str(changes[field]).strip() if changes[field] else None
                    changed_url |= self._secret.get(field) != new_url
                    self._secret[field] = new_url
                    if new_url:
                        self._secret["ever_configured"] = True
                    else:
                        self._secret["nodes"][source] = []
                        self._secret["sources"][source] = _default_source()
            if "latency_threshold_ms" in changes:
                self._secret["latency_threshold_ms"] = changes["latency_threshold_ms"]
            self._save_secret()
        if changed_url:
            await self.refresh_subscriptions()
        return self._settings_projection()

    async def refresh_subscriptions(self) -> set[str]:
        """Fetch sources, validate a candidate, then atomically publish routes."""
        async with self._lock:
            prospective = {source: list(self._secret["nodes"].get(source, [])) for source in ("primary", "fallback")}
            source_updates: dict[str, dict[str, Any]] = {}
            changed_sources: set[str] = set()
            for source in ("primary", "fallback"):
                url = self._secret.get(f"{source}_url")
                if not url:
                    prospective[source] = []
                    source_updates[source] = _default_source()
                    continue
                try:
                    result = parse_subscription(await fetch_subscription(url), source)
                    if not result.nodes:
                        raise SubscriptionError("SUBSCRIPTION_NO_SUPPORTED_NODES")
                    prospective[source] = [node.__dict__ for node in result.nodes]
                    source_updates[source] = {"status": "ready", "last_refreshed_at": _now(), "unsupported_count": result.unsupported_count}
                    changed_sources.add(source)
                except SubscriptionError as exc:
                    source_updates[source] = {**self._secret["sources"].get(source, _default_source()), "status": str(exc)}
            candidates = [ImportedNode(raw["node_id"], raw["label"], source, raw["outbound"])
                          for source in ("primary", "fallback") for raw in prospective[source]]
            samples: dict[str, float | None] = {}

            async def accept(ports: dict[str, int]) -> bool:
                semaphore = asyncio.Semaphore(6)

                async def sample(key: str, port: int) -> None:
                    async with semaphore:
                        samples[key] = await _probe_socks_port(port)

                await asyncio.gather(*(sample(key, port) for key, port in ports.items()))
                has_usable_candidate = any(
                    latency is not None and latency <= self._secret["latency_threshold_ms"]
                    for latency in samples.values()
                )
                has_working_previous = any(
                    self._state["health"].get(self._key(node), {}).get("healthy") is True
                    and self.runtime.port_for(self._key(node)) is not None
                    for node in self._nodes()
                )
                # Preserve a working generation if every new exit fails. An
                # initial unreachable pool must still be published so the
                # recovery job can observe it and leave setup_required.
                return has_usable_candidate or not has_working_previous

            previous_keys = {self._key(node) for node in self._nodes()}
            proposed_keys = {self._key(node) for node in candidates}
            try:
                await self.runtime.replace(candidates, accept=accept if changed_sources and proposed_keys != previous_keys else None)
            except (XrayRuntimeError, OSError) as exc:
                for source in changed_sources:
                    source_updates[source]["status"] = "XRAY_CANDIDATE_FAILED"
                self._secret["sources"].update(source_updates)
                self._save_secret()
                logger.warning("Xray 候选配置未启用（%s）", type(exc).__name__)
            else:
                self._secret["nodes"] = prospective
                self._secret["sources"].update(source_updates)
                self._save_secret()
                for key in set(self._state["health"]) - proposed_keys:
                    self._state["health"].pop(key, None)
                    self._geo_cache.pop(key, None)
                    task = self._confirm_tasks.pop(key, None)
                    if task is not None:
                        task.cancel()
                for key, latency in samples.items():
                    self._record_sample(key, latency)
            changed = self._reconcile()
        await self._notify(changed)
        self._schedule_geo_for_accounts(changed)
        return changed

    async def subscription_tick(self) -> set[str]:
        return await self.refresh_subscriptions()

    def _record_sample(self, key: str, latency: float | None) -> None:
        state = self._state["health"].setdefault(key, {"healthy": None, "bad_streak": 0, "good_streak": 0, "latency_ms": None, "checked_at": None})
        threshold = self._secret["latency_threshold_ms"]
        good = latency is not None and latency <= threshold
        state["checked_at"] = _now()
        state["latency_ms"] = round(latency) if latency is not None else None
        if good:
            state["good_streak"] = min(2, state["good_streak"] + 1)
            state["bad_streak"] = 0
            if state["healthy"] is not False or state["good_streak"] >= 2:
                state["healthy"] = True
        else:
            state["bad_streak"] = min(2, state["bad_streak"] + 1)
            state["good_streak"] = 0
            if state["bad_streak"] >= 2:
                state["healthy"] = False
                self._geo_cache.pop(key, None)
            elif key not in self._confirm_tasks:
                self._confirm_tasks[key] = asyncio.create_task(self._confirm_after(key))

    async def _confirm_after(self, key: str) -> None:
        try:
            await asyncio.sleep(CONFIRM_SECONDS)
            async with self._lock:
                port = self.runtime.port_for(key)
                if port is None or key not in {self._key(node) for node in self._nodes()}:
                    return
                latency = await _probe_socks_port(port)
                self._record_sample(key, latency)
                changed = self._reconcile()
            await self._notify(changed)
            self._schedule_geo_for_accounts(changed)
        except asyncio.CancelledError:
            raise
        finally:
            self._confirm_tasks.pop(key, None)

    async def health_tick(self) -> set[str]:
        async with self._lock:
            self._last_health = time.monotonic()
            nodes = self._nodes()
            if nodes and (self.runtime.active is None or self.runtime.active.process.returncode is not None):
                try:
                    await self.runtime.replace(nodes)
                except (XrayRuntimeError, OSError) as exc:
                    logger.warning("Xray 重启失败（%s）", type(exc).__name__)
            semaphore = asyncio.Semaphore(6)
            samples: dict[str, float | None] = {}

            async def probe(node: ImportedNode) -> None:
                key = self._key(node)
                port = self.runtime.port_for(key)
                async with semaphore:
                    samples[key] = await _probe_socks_port(port) if port is not None else None

            await asyncio.gather(*(probe(node) for node in nodes))
            for key, latency in samples.items():
                self._record_sample(key, latency)
            changed = self._reconcile()
        await self._notify(changed)
        now = time.monotonic()
        geo_due = {
            account for account, entry in self._state["assignments"].items()
            if isinstance(entry, dict) and entry.get("mode") != "setup_required"
            and (
                (cached := self._geo_cache.get(entry.get("key") or "direct")) is None
                or now - cached[0] >= (GEO_TTL_SECONDS if cached[1].get("ip") else 300)
            )
        }
        self._schedule_geo_for_accounts(changed | geo_due)
        return changed

    def _best_node(self, account: str, *, exclude: str | None = None, source: str | None = None) -> ImportedNode | None:
        assignments = self._state["assignments"]
        loads: dict[str, int] = {}
        used_ips: set[str] = set()
        for name, entry in assignments.items():
            if name == account or not isinstance(entry, dict):
                continue
            key = entry.get("key")
            if key:
                loads[key] = loads.get(key, 0) + 1
            if entry.get("exit_ip"):
                used_ips.add(entry["exit_ip"])
        eligible: list[ImportedNode] = []
        for node in self._nodes():
            key = self._key(node)
            health = self._state["health"].get(key, {})
            if key == exclude or (source and node.source != source) or health.get("healthy") is not True or self.runtime.port_for(key) is None:
                continue
            eligible.append(node)
        if not eligible:
            return None
        return min(eligible, key=lambda node: (
            0 if node.source == "primary" else 1,
            1 if self._geo_cache.get(self._key(node), (0, {}))[1].get("ip") in used_ips else 0,
            1 if loads.get(self._key(node), 0) else 0,
            self._state["health"][self._key(node)].get("latency_ms") or 999999,
            loads.get(self._key(node), 0),
        ))

    def _assign(self, account: str, node: ImportedNode | None) -> bool:
        assignments = self._state["assignments"]
        old = assignments.get(account)
        mode = node.source if node else "direct" if self._secret["ever_configured"] else "setup_required"
        key = self._key(node) if node else None
        runtime_generation = self.runtime.active.number if node and self.runtime.active else 0
        if old and old.get("mode") == mode and old.get("key") == key and old.get("runtime_generation") == runtime_generation:
            return False
        if key and old and old.get("key") == key and old.get("runtime_generation") != runtime_generation:
            self._geo_cache.pop(key, None)
        self._state["generation"] = int(self._state["generation"]) + 1
        entry = _default_assignment(mode)
        entry.update({"key": key, "generation": self._state["generation"], "runtime_generation": runtime_generation, "status": "pending" if node else mode})
        if node:
            health = self._state["health"].get(key, {})
            entry["latency_ms"] = health.get("latency_ms")
            entry["route_checked_at"] = health.get("checked_at")
            entry["status"] = "healthy" if health.get("healthy") else "pending"
        assignments[account] = entry
        return True

    def _reconcile(self) -> set[str]:
        changed: set[str] = set()
        for account in sorted(self._all_accounts()):
            current = self._state["assignments"].get(account)
            current_key = current.get("key") if isinstance(current, dict) else None
            health = self._state["health"].get(current_key, {}) if current_key else {}
            active = current_key and self.runtime.port_for(current_key) is not None and health.get("bad_streak", 0) < 2
            node: ImportedNode | None = None
            if active:
                node = next((item for item in self._nodes() if self._key(item) == current_key), None)
                if node and node.source == "fallback":
                    primary = self._best_node(account, source="primary")
                    if primary and self._state["health"][self._key(primary)].get("good_streak", 0) >= 2:
                        node = primary
            else:
                node = self._best_node(account, exclude=current_key if health.get("bad_streak", 0) >= 2 else None)
                if node and current and current.get("mode") == "direct" and self._state["health"][self._key(node)].get("good_streak", 0) < 2:
                    node = None
            if self._assign(account, node):
                changed.add(account)
            elif node and current:
                current["latency_ms"] = health.get("latency_ms")
                current["route_checked_at"] = health.get("checked_at")
                current["status"] = "healthy" if health.get("bad_streak", 0) == 0 else "degraded"
        self._save_state()
        return changed

    def resolve_account_route(self, account_name: str) -> dict[str, Any] | None:
        if not self._secret["ever_configured"]:
            raise RouteSetupRequired()
        entry = self._state["assignments"].get(account_name)
        if not entry:
            node = self._best_node(account_name)
            self._assign(account_name, node)
            self._save_state()
            entry = self._state["assignments"][account_name]
            self._schedule_geo_for_accounts({account_name})
        if entry["mode"] == "setup_required":
            raise RouteSetupRequired()
        key = entry.get("key")
        port = self.runtime.port_for(key, entry.get("runtime_generation")) if key else None
        if port is None:
            if key:
                self._assign(account_name, None)
                self._save_state()
            return None
        return {"scheme": "socks5", "hostname": "127.0.0.1", "port": port}

    def rename_account_route(self, old_name: str, new_name: str) -> None:
        """Move sticky state with account inventory; pending geo uses generation guard."""
        if old_name == new_name:
            return
        entry = self._state["assignments"].pop(old_name, None)
        if entry is not None:
            self._state["assignments"][new_name] = entry
            self._save_state()

    def delete_account_route(self, account_name: str) -> None:
        if self._state["assignments"].pop(account_name, None) is not None:
            self._save_state()

    def account_route_status(self, account_name: str) -> dict[str, Any]:
        entry = self._state["assignments"].get(account_name)
        if not isinstance(entry, dict):
            entry = _default_assignment("setup_required" if not self._secret["ever_configured"] else "direct")
        key = entry.get("key")
        node = next((item for item in self._nodes() if self._key(item) == key), None)
        shared = bool(key and sum(1 for item in self._state["assignments"].values() if isinstance(item, dict) and item.get("key") == key) > 1)
        return {
            "route_mode": entry.get("mode", "direct"),
            "route_status": entry.get("status", "pending"),
            "node_label": node.label if node else None,
            "latency_ms": entry.get("latency_ms"),
            "route_checked_at": entry.get("route_checked_at"),
            "exit_ip": entry.get("exit_ip"),
            "exit_country": entry.get("exit_country"),
            "exit_region": entry.get("exit_region"),
            "exit_checked_at": entry.get("exit_checked_at"),
            "shared_node": shared,
        }

    def _schedule_geo_for_accounts(self, accounts: set[str]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for account in accounts:
            task = loop.create_task(self._verify_exit(account))
            self._geo_tasks.add(task)
            task.add_done_callback(self._geo_tasks.discard)

    async def _verify_exit(self, account: str) -> None:
        entry = self._state["assignments"].get(account)
        if not entry or entry["mode"] == "setup_required":
            return
        key, generation = entry.get("key"), entry.get("generation")
        cache_key = key or "direct"
        cached = self._geo_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < (GEO_TTL_SECONDS if cached[1].get("ip") else 300):
            geo = cached[1]
        else:
            port = self.runtime.port_for(key, entry.get("runtime_generation")) if key else None
            if key and port is None:
                return
            inflight_key = f"{cache_key}:{entry.get('runtime_generation')}"
            task = self._geo_inflight.get(inflight_key)
            if task is None:
                task = asyncio.create_task(self._fetch_geo(cache_key, port, entry.get("runtime_generation")))
                self._geo_inflight[inflight_key] = task

                def release(completed: asyncio.Task[dict[str, str | None]]) -> None:
                    if self._geo_inflight.get(inflight_key) is completed:
                        self._geo_inflight.pop(inflight_key, None)

                task.add_done_callback(release)
            geo = await asyncio.shield(task)
        async with self._lock:
            current = self._state["assignments"].get(account)
            if current and current.get("key") == key and current.get("generation") == generation:
                current.update({"exit_ip": geo["ip"], "exit_country": geo["country"], "exit_region": geo["region"], "exit_checked_at": _now() if geo["ip"] else None})
                self._save_state()

    async def _fetch_geo(self, cache_key: str, port: int | None, runtime_generation: int | None) -> dict[str, str | None]:
        def current_route() -> bool:
            return cache_key == "direct" or (
                self.runtime.active is not None and self.runtime.active.number == runtime_generation
            )
        try:
            proxy = f"socks5://127.0.0.1:{port}" if port else None
            async with httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=5.0) as client:
                response = await client.get(GEO_ENDPOINT)
                response.raise_for_status()
                body = response.json()
            address = str(body.get("ip") or "")
            if not ipaddress.ip_address(address).is_global or body.get("success") is False:
                raise ValueError("invalid geo exit")
            geo = {"ip": address, "country": str(body.get("country") or "")[:80] or None,
                   "region": str(body.get("region") or "")[:80] or None}
            if current_route() and (cache_key == "direct" or self._state["health"].get(cache_key, {}).get("healthy") is True):
                self._geo_cache[cache_key] = (time.monotonic(), geo)
            return geo
        except (httpx.HTTPError, ValueError, TypeError, ImportError):
            geo = {"ip": None, "country": None, "region": None}
            if current_route():
                self._geo_cache[cache_key] = (time.monotonic(), geo)
            return geo


_route_service: AccountRouteService | None = None


def get_route_service() -> AccountRouteService:
    global _route_service
    directory = get_settings().resolve_base_dir() / "xray"
    if _route_service is None or _route_service.directory != directory:
        _route_service = AccountRouteService(directory)
    return _route_service


def resolve_account_route(account_name: str) -> dict[str, Any] | None:
    return get_route_service().resolve_account_route(account_name)


def account_route_status(account_name: str) -> dict[str, Any]:
    return get_route_service().account_route_status(account_name)


def rename_account_route(old_name: str, new_name: str) -> None:
    get_route_service().rename_account_route(old_name, new_name)


def delete_account_route(account_name: str) -> None:
    get_route_service().delete_account_route(account_name)
