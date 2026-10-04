"""Supervise the original TeleBox runtime with isolated per-account state.

Secrets travel over anonymous stdin; stdout is a JSON control protocol. No shell,
Telegram message emulation, or shared Pyrogram SQLite session is used.
"""
from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.services.telegram import get_telegram_service
from backend.utils.account_locks import get_account_lock

SOURCE = Path(__file__).resolve().parents[2] / "telebox"


def node_heap_limit_mb() -> int:
    """Bound each account's V8 old-space budget on small shared hosts."""
    try:
        requested = int(os.getenv("TELEBOX_NODE_HEAP_MB", "128"))
    except ValueError:
        requested = 128
    return min(512, max(64, requested))


def redact(text: str, secrets: list[str] = ()) -> str:
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(api_hash|session|token|password|auth_key)([\s\"':=]+)[^\s,}\"']+", r"\1\2[REDACTED]", text)
    text = re.sub(r"[0-9a-fA-F]{32,}|[A-Za-z0-9+/=_-]{80,}", "[REDACTED]", text)
    text = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)
    return text[:2000]


class TeleBoxService:
    def __init__(self, root: Path | None = None, source: Path = SOURCE):
        self.root = root or get_settings().data_dir / "telebox"
        self.source = source
        self.workers: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.logs: dict[str, deque] = {}
        self.secrets: dict[str, list[str]] = {}
        self.closing = False

    def _account(self, account: str) -> str:
        service = get_telegram_service()
        account = service._normalize_account_name(account)
        if not service.account_exists(account):
            raise ValueError("账号不存在")
        return account

    def directory(self, account: str) -> Path:
        # Account names never become filesystem path segments.
        return self.root / hashlib.sha256(account.encode()).hexdigest()

    def rename_account_data(self, old: str, new: str) -> None:
        """Move account-local TeleBox state after SignPulse account rename succeeds."""
        old_dir, new_dir = self.directory(old), self.directory(new)
        if old_dir.exists():
            if new_dir.exists():
                raise ValueError("目标账号已有 TeleBox 数据，请先处理冲突")
            old_dir.replace(new_dir)
            marker = new_dir / "panel-state.json"
            if marker.exists():
                state = json.loads(marker.read_text())
                self._private_json(marker, {"account": new, "enabled": bool(state.get("enabled"))})
        self.logs[new] = self.logs.pop(old, deque(maxlen=300))
        self.secrets.pop(old, None)

    def _log(self, account: str, message: str, level: str = "info"):
        self.logs.setdefault(account, deque(maxlen=300)).append({
            "time": datetime.now(timezone.utc).isoformat(), "level": level,
            "message": redact(message, self.secrets.get(account, [])),
        })

    def _marker(self, account: str, enabled: bool):
        path = self.directory(account) / "panel-state.json"
        self._private_json(path, {"account": account, "enabled": enabled})

    @staticmethod
    def _private_json(path: Path, value: Any):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
        temporary.replace(path)
        path.chmod(0o600)

    def _prepare(self, account: str) -> Path:
        directory = self.directory(account)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        # Source is account-local because upstream TPM/update can write relative
        # to __dirname. Existing plugins/config/assets are never overwritten.
        for entry in ["src", "scripts", "panel", "plugins", "assets", "temp", "package.json", "package-lock.json", "tsconfig.json", "LICENSE", "UPSTREAM.json"]:
            source, target = self.source / entry, directory / entry
            if target.exists() or not source.exists():
                continue
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        # Refresh managed integration code on existing account directories too.
        # Upstream plugins, user plugins and account config remain account-local.
        shutil.copytree(self.source / "panel", directory / "panel", dirs_exist_ok=True)
        # Keep the runtime loader current for existing account directories.
        shutil.copy2(self.source / "src/utils/pluginManager.ts", directory / "src/utils/pluginManager.ts")
        for script in ("esbuild-register.cjs", "esbuild-esm-loader.mjs", "cjs-helpers.js"):
            shutil.copy2(self.source / "scripts" / script, directory / "scripts" / script)
        for folder in ["home", "cache", "temp"]:
            (directory / folder).mkdir(exist_ok=True, mode=0o700)
        dependencies = directory / "node_modules"
        if not dependencies.exists():
            dependencies.symlink_to((self.source / "node_modules").resolve(), target_is_directory=True)
        return directory

    def status(self, account: str):
        account = self._account(account)
        directory = self.directory(account)
        worker = self.workers.get(account)
        enabled = False
        marker = directory / "panel-state.json"
        if marker.exists():
            enabled = bool(json.loads(marker.read_text()).get("enabled"))
        config = directory / "config.json"
        try:
            authorized = bool(json.loads(config.read_text()).get("session")) if config.exists() else False
        except (OSError, ValueError, AttributeError):
            authorized = False
        return {"account": account, "status": worker["status"] if worker else "stopped", "enabled": enabled,
                "authorized": authorized,
                "message": worker.get("message", "") if worker else ""}

    def overview(self):
        accounts = get_telegram_service().list_accounts()
        return {"accounts": [self.status(item.get("name") or item.get("account_name")) for item in accounts]}

    async def _send(self, worker: dict, command: dict):
        process = worker["process"]
        if process.returncode is not None:
            raise ValueError("TeleBox 已停止")
        process.stdin.write((json.dumps(command) + "\n").encode())
        await process.stdin.drain()

    async def start(self, account: str):
        account = self._account(account)
        async with self.locks.setdefault(account, asyncio.Lock()):
            if self.closing:
                raise ValueError("系统正在停止")
            old = self.workers.get(account)
            if old and old["process"].returncode is None:
                return self.status(account)
            node = shutil.which(os.getenv("TELEBOX_NODE", "node"))
            if not node or not (self.source / "node_modules/teleproto").exists():
                raise ValueError("TeleBox 需要 Node.js 24 和已安装的依赖，请重新构建镜像")
            directory = self._prepare(account)
            lock_handle = (directory / "runtime.lock").open("a")
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_handle.close()
                raise ValueError("此账号 TeleBox 已由另一个服务进程管理")
            service = get_telegram_service()
            client, proxy = service._build_account_client(account, no_updates=True)
            credentials = {"api_id": client.api_id, "api_hash": client.api_hash}
            if proxy:
                scheme = proxy.get("scheme", "socks5")
                if scheme not in ("socks4", "socks5"):
                    lock_handle.close()
                    raise ValueError("TeleBox Telegram 连接需要 SOCKS4/5 代理")
                credentials["proxy"] = {"ip": proxy["hostname"], "port": proxy["port"],
                                        "socksType": 4 if scheme == "socks4" else 5,
                                        "username": proxy.get("username"), "password": proxy.get("password")}
            self.secrets[account] = [str(credentials["api_hash"])]
            if proxy and proxy.get("password"):
                self.secrets[account].append(proxy["password"])
            env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "TZ", "LD_LIBRARY_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
            env.update({"HOME": str(directory / "home"), "XDG_CACHE_HOME": str(directory / "cache"),
                        "TB_LOCALSTORAGE_FILE": str(directory / "cache/localstorage"), "NODE_ENV": "production"})
            try:
                process = await asyncio.create_subprocess_exec(
                    node, f"--max-old-space-size={node_heap_limit_mb()}", f"--localstorage-file={directory / 'cache/localstorage'}",
                    "-r", "tsconfig-paths/register", "-r", "./scripts/esbuild-register.cjs",
                    "./panel/worker.ts", cwd=directory, env=env,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True, limit=65536)
            except BaseException:
                lock_handle.close()
                raise
            worker = {"process": process, "status": "starting", "pending": {}, "lock": lock_handle, "tasks": set()}
            ready = asyncio.get_running_loop().create_future()
            worker["pending"]["init"] = ready
            self.workers[account] = worker
            self._marker(account, True)
            worker["readers"] = [asyncio.create_task(self._stdout(account, worker)), asyncio.create_task(self._stderr(account, worker)), asyncio.create_task(self._watch(account, worker))]
            await self._send(worker, {"action": "init", "id": "init", **credentials})
            self._log(account, "TeleBox 正在启动独立账号会话")
            try:
                result = await asyncio.wait_for(asyncio.shield(ready), 3)
                if not result.get("ok"):
                    raise ValueError(result.get("message") or "TeleBox 启动失败，请查看运行日志")
            except asyncio.TimeoutError:
                # QR authorization can legitimately take minutes. The later
                # state event and log report the actual outcome.
                pass
            return self.status(account)

    async def _accept(self, account: str, worker: dict, token: str):
        from pyrogram import raw
        try:
            payload = base64.b64decode(token, validate=True)
            if not 1 <= len(payload) <= 4096:
                raise ValueError("invalid token")
            service = get_telegram_service()
            client, _ = service._build_account_client(account, no_updates=True)
            async with get_account_lock(account):
                async with client:
                    await asyncio.wait_for(
                        client.invoke(raw.functions.auth.AcceptLoginToken(token=payload)), 30
                    )
        except Exception:
            worker["message"] = "独立会话授权失败，请检查账号登录状态或稍后重试"
            self._log(account, worker["message"], "error")

    async def _stdout(self, account: str, worker: dict):
        try:
            while line := await worker["process"].stdout.readline():
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    self._log(account, line.decode(errors="replace"))
                    continue
                if event.get("event") == "login_token":
                    task = asyncio.create_task(self._accept(account, worker, event.get("token", "")))
                    worker["tasks"].add(task)
                    task.add_done_callback(worker["tasks"].discard)
                elif event.get("event") == "state" and event.get("status") in {"running", "password_required", "failed"}:
                    worker["status"] = event["status"]
                elif event.get("event") == "result":
                    future = worker["pending"].pop(event.get("id"), None)
                    if future and not future.done():
                        future.set_result(event)
                    if event.get("id") == "init" and not event.get("ok"):
                        worker["status"] = "failed"
                        worker["message"] = redact(event.get("message") or "TeleBox 启动失败，请检查运行日志", self.secrets.get(account, []))
                        self._log(account, worker["message"], "error")
        except (ValueError, OSError):
            self._log(account, "TeleBox 控制通道已关闭", "error")

    async def _stderr(self, account: str, worker: dict):
        # Read fixed chunks so a plugin cannot kill log draining with a huge line.
        while data := await worker["process"].stderr.read(4096):
            for line in data.decode(errors="replace").splitlines():
                self._log(account, line)

    async def _watch(self, account: str, worker: dict):
        code = await worker["process"].wait()
        worker["status"] = "stopped" if worker.get("stopping") else "failed"
        if not worker.get("stopping") and not worker.get("message"):
            worker["message"] = f"TeleBox 进程退出（代码 {code}），请查看运行日志"
        for future in worker["pending"].values():
            if not future.done():
                future.set_result({"ok": False, "message": "TeleBox 进程已停止"})
        worker["pending"].clear()
        worker["lock"].close()
        for task in list(worker["tasks"]):
            task.cancel()
        self._log(account, f"TeleBox 进程退出 ({code})")

    async def _stop_locked(self, account: str, *, disable: bool):
        worker = self.workers.get(account)
        if disable:
            self._marker(account, False)
        if worker:
            worker["stopping"] = True
        if worker and worker["process"].returncode is None:
            worker["status"] = "stopping"
            try:
                os.killpg(worker["process"].pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(worker["process"].wait(), 25)
            except asyncio.TimeoutError:
                try:
                    os.killpg(worker["process"].pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await worker["process"].wait()
            await asyncio.gather(*worker["readers"], return_exceptions=True)
        if worker and worker["process"].returncode is not None:
            worker["status"] = "stopped"
        return self.status(account)

    async def stop(self, account: str, *, disable: bool = True):
        account = self._account(account)
        async with self.locks.setdefault(account, asyncio.Lock()):
            return await self._stop_locked(account, disable=disable)

    async def logout(self, account: str):
        """Revoke the independent TeleBox session, then remove its local authorization."""
        account = self._account(account)
        async with self.locks.setdefault(account, asyncio.Lock()):
            worker = self.workers.get(account)
            revoked = False
            if worker and worker["status"] == "running" and worker["process"].returncode is None:
                identifier = uuid.uuid4().hex
                future = asyncio.get_running_loop().create_future()
                worker["pending"][identifier] = future
                try:
                    await self._send(worker, {"action": "logout", "id": identifier})
                    result = await asyncio.wait_for(future, 20)
                    revoked = result.get("ok") is True and result.get("revoked") is True
                except (OSError, ValueError, asyncio.TimeoutError):
                    pass
                finally:
                    worker["pending"].pop(identifier, None)
            await self._stop_locked(account, disable=True)
            config = self.directory(account) / "config.json"
            if config.exists():
                try:
                    data = json.loads(config.read_text())
                    if not isinstance(data, dict):
                        data = {}
                except (OSError, ValueError):
                    data = {}
                data.pop("session", None)
                self._private_json(config, data)
            self._log(account, "TeleBox 独立会话已退出" if revoked else "TeleBox 本地会话已清除，远端撤销未确认")
            return {**self.status(account), "remote_revoked": revoked}

    async def password(self, account: str, password: str):
        account = self._account(account)
        worker = self.workers.get(account)
        if not worker or worker["status"] != "password_required":
            raise ValueError("当前账号没有等待两步验证密码")
        if not password or len(password) > 1024:
            raise ValueError("密码长度无效")
        self.secrets.setdefault(account, []).append(password)
        await self._send(worker, {"action": "password", "password": password})
        worker["status"] = "starting"
        return self.status(account)

    def log_items(self, account: str):
        account = self._account(account)
        return {"items": list(self.logs.get(account, []))}

    async def startup(self):
        self.closing = False
        if not self.root.exists():
            return
        for marker in self.root.glob("*/panel-state.json"):
            try:
                state = json.loads(marker.read_text())
                if state.get("enabled") and marker.parent == self.directory(state["account"]):
                    await self.start(state["account"])
            except Exception:
                continue

    async def shutdown(self):
        self.closing = True
        await asyncio.gather(*(self.stop(account, disable=False) for account in self.workers), return_exceptions=True)


_service: TeleBoxService | None = None

def get_telebox_service() -> TeleBoxService:
    global _service
    if _service is None:
        _service = TeleBoxService()
    return _service
