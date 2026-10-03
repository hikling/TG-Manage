"""Small scheduler store for TeleBox commands and workbench daily messages.

Legacy sign-task files are intentionally never read or executed here.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import get_settings
from backend.services import communications
from backend.services.telebox import get_telebox_service, redact


class TeleBoxTaskService:
    def __init__(self, path: Path | None = None):
        self.path = path or get_settings().data_dir / "telebox-tasks.json"
        self._running: dict[str, asyncio.Lock] = {}

    @contextmanager
    def _storage(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_suffix(".lock")
        with lock_path.open("a") as lock:
            lock_path.chmod(0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text()) if self.path.exists() else {"tasks": [], "history": []}
                yield data
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _save(self, data: dict):
        temp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        with temp.open("x") as file:
            os.chmod(temp, 0o600)
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        temp.replace(self.path)
        self.path.chmod(0o600)

    def list(self) -> list[dict]:
        with self._storage() as data:
            return [dict(task) for task in data["tasks"]]

    def get(self, identifier: str) -> dict:
        with self._storage() as data:
            task = next((task for task in data["tasks"] if task["id"] == identifier), None)
            if task is None:
                raise ValueError("任务不存在")
            return dict(task)

    def history(self, identifier: str | None = None) -> list[dict]:
        with self._storage() as data:
            return [dict(item) for item in data["history"] if identifier is None or item["task_id"] == identifier]

    def clear_history(self, account: str | None = None) -> int:
        with self._storage() as data:
            before = len(data["history"])
            data["history"] = ([item for item in data["history"]
                                if account not in item.get("accounts", [])]
                               if account is not None else [])
            self._save(data)
            return before - len(data["history"])

    @staticmethod
    def available(account: str) -> dict:
        status = get_telebox_service().status(account)
        return {"account": account, "status": status["status"], "enabled": status["enabled"],
                "commands": status["commands"], "plugins": status["plugins"]}

    def _validate(self, item: dict):
        telebox = get_telebox_service()
        for account in item["accounts"]:
            telebox._account(account)
        if item["kind"] == "plugin":
            if len(item["accounts"]) != 1:
                raise ValueError("TeleBox 插件任务须选择一个账号")
            if item["enabled"]:
                status = telebox.status(item["accounts"][0])
                if status["status"] != "running" or not status["enabled"]:
                    raise ValueError("请先启动此账号的 TeleBox，再选择插件命令")
                if {"plugin": item["plugin"], "command": item["command"]} not in status["commands"]:
                    raise ValueError("此账号没有加载所选 TeleBox 插件命令，请刷新插件")
        else:
            for chat_id in item["chats"]:
                communications.peer_id(chat_id)

    def create(self, item: dict) -> dict:
        self._validate(item)
        item = {"id": uuid.uuid4().hex, "enabled": True, **item}
        with self._storage() as data:
            if len(data["tasks"]) >= 500:
                raise ValueError("任务数量已达到上限")
            data["tasks"].append(item)
            self._save(data)
        return dict(item)

    def update(self, identifier: str, item: dict) -> dict:
        self._validate(item)
        with self._storage() as data:
            for index, task in enumerate(data["tasks"]):
                if task["id"] == identifier:
                    updated = {**item, "id": identifier}
                    data["tasks"][index] = updated
                    self._save(data)
                    return dict(updated)
        raise ValueError("任务不存在")

    def delete(self, identifier: str):
        with self._storage() as data:
            before = len(data["tasks"])
            data["tasks"] = [task for task in data["tasks"] if task["id"] != identifier]
            if len(data["tasks"]) == before:
                raise ValueError("任务不存在")
            self._save(data)

    def rename_account(self, old: str, new: str):
        with self._storage() as data:
            for task in data["tasks"]:
                task["accounts"] = [new if account == old else account for account in task["accounts"]]
            self._save(data)

    def disable_account(self, account: str):
        with self._storage() as data:
            for task in data["tasks"]:
                if account in task["accounts"]:
                    task["enabled"] = False
            self._save(data)

    async def run(self, identifier: str) -> dict:
        lock = self._running.setdefault(identifier, asyncio.Lock())
        if lock.locked():
            raise ValueError("任务已在运行")
        async with lock:
            task = self.get(identifier)
            try:
                if task["kind"] == "plugin":
                    await get_telebox_service().run_command(
                        task["accounts"][0], task["plugin"], task["command"], task.get("args", ""),
                    )
                    message = "命令已投递到 TeleBox；插件处理结果请查看 TeleBox 日志"
                else:
                    count = 0
                    for account in task["accounts"]:
                        for chat in task["chats"]:
                            await communications.send_message(account, chat, task["text"])
                            count += 1
                    message = f"已发送 {count} 条消息"
                success = True
            except Exception as exc:
                # Telegram/worker errors can contain private material; record only
                # a safe category for the task history.
                success = False
                message = redact(str(exc)) if isinstance(exc, ValueError) else "账号通信失败，请查看运行日志"
            entry = {"task_id": identifier, "task": task["name"], "accounts": task["accounts"],
                     "time": datetime.now(timezone.utc).isoformat(),
                     "success": success, "message": message}
            with self._storage() as data:
                data["history"] = (data["history"] + [entry])[-500:]
                self._save(data)
            return entry


_service: TeleBoxTaskService | None = None


def get_telebox_task_service() -> TeleBoxTaskService:
    global _service
    if _service is None:
        _service = TeleBoxTaskService()
    return _service
