"""Application-owned Xray generations with loopback-only node inlets."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.services.subscription_import import ImportedNode


class XrayRuntimeError(RuntimeError):
    """Safe operational code; subprocess stderr is deliberately suppressed."""


@dataclass
class Generation:
    number: int
    process: asyncio.subprocess.Process
    config_path: Path
    ports: dict[str, int]
    node_ids: frozenset[str]
    retire_task: asyncio.Task[None] | None = None


def _reserve_ports(count: int) -> list[int]:
    held: list[socket.socket] = []
    try:
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            held.append(sock)
        return [int(sock.getsockname()[1]) for sock in held]
    finally:
        for sock in held:
            sock.close()


def build_xray_config(nodes: list[ImportedNode], ports: list[int]) -> dict[str, Any]:
    if len(nodes) != len(ports) or not nodes or len(nodes) > 256:
        raise XrayRuntimeError("XRAY_CONFIG_INVALID")
    inbounds: list[dict[str, Any]] = []
    outbounds: list[dict[str, Any]] = [
        {"protocol": "blackhole", "tag": "deny"},
    ]
    rules: list[dict[str, Any]] = []
    for ordinal, (node, port) in enumerate(zip(nodes, ports, strict=True)):
        tag = f"node-{ordinal}"
        inlet = f"in-{ordinal}"
        inbounds.append({
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "tag": inlet,
            "settings": {"auth": "noauth", "udp": False, "ip": "127.0.0.1"},
        })
        outbounds.append({**node.outbound, "tag": tag})
        rules.append({"type": "field", "inboundTag": [inlet], "outboundTag": tag})
    return {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {"domainStrategy": "AsIs", "rules": rules},
    }


class XrayRuntime:
    def __init__(self, directory: Path, binary: str = "/usr/local/bin/xray", drain_seconds: float = 35 * 60) -> None:
        self.directory = directory
        self.binary = binary
        self.drain_seconds = drain_seconds
        self.active: Generation | None = None
        self._generations: list[Generation] = []
        # A new Python process must never reuse a saved assignment generation.
        self._counter = secrets.randbits(52)
        self._lock = asyncio.Lock()

    @staticmethod
    def key(node: ImportedNode) -> str:
        return f"{node.source}:{node.node_id}"

    def port_for(self, key: str, generation_number: int | None = None) -> int | None:
        generation = self.active if generation_number is None else next(
            (item for item in self._generations if item.number == generation_number), None
        )
        if generation is None or generation.process.returncode is not None:
            return None
        return generation.ports.get(key)

    async def replace(
        self,
        nodes: list[ImportedNode],
        accept: Callable[[dict[str, int]], Awaitable[bool]] | None = None,
    ) -> bool:
        """Start candidate and swap only after validation/readiness. Return if changed."""
        async with self._lock:
            unique = {self.key(node): node for node in nodes}
            if self.active and self.active.process.returncode is None and self.active.node_ids == frozenset(unique):
                return False
            if not unique:
                previous, self.active = self.active, None
                if previous:
                    self._schedule_retire(previous)
                return previous is not None
            if len(self._generations) >= 4:
                raise XrayRuntimeError("XRAY_GENERATION_LIMIT")
            self.directory.mkdir(parents=True, exist_ok=True)
            ports = _reserve_ports(len(unique))
            ordered = list(unique.values())
            config = build_xray_config(ordered, ports)
            fd, raw_path = tempfile.mkstemp(prefix="xray-", suffix=".json", dir=self.directory)
            path = Path(raw_path)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                else:
                    os.chmod(path, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(config, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                await self._validate(path)
                process = await asyncio.create_subprocess_exec(
                    self.binary, "run", "-config", str(path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await self._ready(process, ports)
                    await asyncio.sleep(0.1)
                    if process.returncode is not None:
                        raise XrayRuntimeError("XRAY_START_FAILED")
                    mapping = dict(zip(unique, ports, strict=True))
                    if accept is not None and not await accept(mapping):
                        raise XrayRuntimeError("XRAY_CANDIDATE_UNHEALTHY")
                except BaseException:
                    await self._stop_process(process)
                    raise
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            self._counter += 1
            candidate = Generation(self._counter, process, path, dict(zip(unique, ports, strict=True)), frozenset(unique))
            old, self.active = self.active, candidate
            self._generations.append(candidate)
            if old:
                self._schedule_retire(old)
            return True

    async def _validate(self, path: Path) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                self.binary, "run", "-test", "-config", str(path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await asyncio.wait_for(process.wait(), timeout=8)
        except (OSError, asyncio.TimeoutError):
            if "process" in locals():
                await self._stop_process(process)
            raise XrayRuntimeError("XRAY_VALIDATE_FAILED") from None
        if code:
            raise XrayRuntimeError("XRAY_VALIDATE_FAILED")

    @staticmethod
    async def _ready(process: asyncio.subprocess.Process, ports: list[int]) -> None:
        deadline = asyncio.get_running_loop().time() + 8
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                raise XrayRuntimeError("XRAY_START_FAILED")
            try:
                for port in ports:
                    reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), timeout=0.3)
                    writer.close()
                    with contextlib.suppress(OSError, asyncio.TimeoutError):
                        await asyncio.wait_for(writer.wait_closed(), timeout=0.3)
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.1)
        raise XrayRuntimeError("XRAY_START_FAILED")

    def _schedule_retire(self, generation: Generation) -> None:
        async def retire() -> None:
            try:
                await asyncio.sleep(self.drain_seconds)
                await self._retire(generation)
            except asyncio.CancelledError:
                raise

        generation.retire_task = asyncio.create_task(retire())

    async def _retire(self, generation: Generation) -> None:
        await self._stop_process(generation.process)
        generation.config_path.unlink(missing_ok=True)
        with contextlib.suppress(ValueError):
            self._generations.remove(generation)

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def shutdown(self) -> None:
        async with self._lock:
            for generation in list(self._generations):
                if generation.retire_task:
                    generation.retire_task.cancel()
                await self._retire(generation)
            self.active = None
