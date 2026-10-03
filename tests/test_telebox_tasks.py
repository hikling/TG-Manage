"""TeleBox-only scheduling never executes legacy sign task actions."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.exceptions import HTTPException
from pydantic import ValidationError

from backend import scheduler as scheduler_module
from backend.api.routes.telebox_tasks import TaskInput
from backend.services import telebox_tasks


def payload(kind="plugin"):
    return TaskInput(
        name="每日测试", kind=kind, accounts=["one"], time="09:10",
        plugin="ping" if kind == "plugin" else None,
        command="ping" if kind == "plugin" else None,
        chats=["-100123"] if kind == "message" else [],
        text="hello" if kind == "message" else "",
    ).dict()


def test_task_input_rejects_old_actions_and_invalid_time():
    unicode_task = TaskInput(name="unicode", kind="plugin", accounts=["one"], time="09:00",
                             plugin="custom", command="签到")
    assert unicode_task.command == "签到"
    with pytest.raises(ValidationError):
        TaskInput(name="old", kind="legacy", accounts=["one"], time="09:00")
    with pytest.raises(ValidationError):
        TaskInput(name="bad", kind="plugin", accounts=["one"], time="25:99",
                  plugin="ping", command="ping")
    with pytest.raises(ValidationError):
        TaskInput(name="mixed", kind="message", accounts=["one"], time="09:00",
                  chats=["123"], text="hi", plugin="ping", command="ping")


@pytest.mark.asyncio
async def test_store_command_discovery_run_and_daily_message(monkeypatch, tmp_path):
    commands = [{"plugin": "ping", "command": "ping"}]
    calls = []

    class FakeTeleBox:
        def _account(self, account):
            if account != "one":
                raise ValueError("账号不存在")
            return account

        def status(self, account):
            self._account(account)
            return {"status": "running", "enabled": True, "commands": commands, "plugins": []}

        async def run_command(self, account, plugin, command, args):
            calls.append((account, plugin, command, args))

    monkeypatch.setattr(telebox_tasks, "get_telebox_service", lambda: FakeTeleBox())
    async def send(account, chat, text):
        calls.append((account, chat, text))
    monkeypatch.setattr(telebox_tasks.communications, "send_message", send)
    service = telebox_tasks.TeleBoxTaskService(tmp_path / "jobs.json")
    assert service.available("one")["commands"] == commands
    task = service.create(payload())
    assert service.list()[0]["id"] == task["id"]
    assert (await service.run(task["id"]))["success"] is True
    assert calls == [("one", "ping", "ping", "")]
    message = service.create(payload("message"))
    assert (await service.run(message["id"]))["success"] is True
    assert calls[-1] == ("one", "-100123", "hello")
    assert len(service.history()) == 2
    service.disable_account("one")
    assert all(not item["enabled"] for item in service.list())
    assert (tmp_path / "jobs.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_scheduler_replaces_legacy_jobs_with_telebox_jobs(monkeypatch):
    class Scheduler:
        timezone = "UTC"

        def __init__(self):
            self.jobs = {"sign-old": SimpleNamespace(id="sign-old")}

        def get_jobs(self):
            return list(self.jobs.values())

        def add_job(self, func, trigger, id, args, **kwargs):
            self.jobs[id] = SimpleNamespace(id=id, args=args, func=func, trigger=trigger)

        def remove_job(self, identifier):
            self.jobs.pop(identifier)

    instance = Scheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", instance)
    monkeypatch.setattr(scheduler_module, "_sync_auto_backup_job", lambda: None)
    monkeypatch.setattr("backend.scheduler.instance_lock.has_scheduler_lock", lambda: True)
    monkeypatch.setattr(telebox_tasks, "get_telebox_task_service", lambda: SimpleNamespace(list=lambda: [
        {"id": "new", "enabled": True, "time": "09:10"},
    ]))
    await scheduler_module.sync_jobs()
    assert set(instance.jobs) == {"tb-new"}
    assert instance.jobs["tb-new"].args == ["new"]


def test_task_rejects_missing_loaded_plugin(monkeypatch, tmp_path):
    fake = SimpleNamespace(_account=lambda _: "one", status=lambda _: {
        "status": "running", "enabled": True, "commands": [], "plugins": [],
    })
    monkeypatch.setattr(telebox_tasks, "get_telebox_service", lambda: fake)
    service = telebox_tasks.TeleBoxTaskService(tmp_path / "jobs.json")
    with pytest.raises(ValueError, match="没有加载"):
        service.create(payload())
    assert service.list() == []


def test_message_chat_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(telebox_tasks, "get_telebox_service", lambda: SimpleNamespace(_account=lambda _: "one"))
    service = telebox_tasks.TeleBoxTaskService(tmp_path / "jobs.json")
    invalid = payload("message")
    invalid["chats"] = ["../../oops"]
    with pytest.raises(HTTPException) as exc:
        service.create(invalid)
    assert exc.value.status_code == 422
