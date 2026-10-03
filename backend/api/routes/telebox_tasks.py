"""Authenticated TeleBox-only scheduled jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr, root_validator, validator

from backend.core.auth import get_current_user
from backend.scheduler import sync_jobs
from backend.services.telebox_tasks import get_telebox_task_service

router = APIRouter(prefix="/telebox-tasks", dependencies=[Depends(get_current_user)])


class TaskInput(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=80)
    kind: Literal["plugin", "message"]
    accounts: list[constr(strip_whitespace=True, min_length=1, max_length=128)] = Field(..., min_items=1, max_items=20)
    time: constr(regex=r"^\d{2}:\d{2}$")
    enabled: bool = True
    plugin: constr(regex=r"^[A-Za-z0-9_-]{1,80}$") | None = None
    command: constr(min_length=1, max_length=80, regex=r"^[^\x00-\x1f\x7f]+$") | None = None
    args: constr(max_length=500) = ""
    chats: list[constr(min_length=1, max_length=64)] = Field(default_factory=list, max_items=100)
    text: constr(max_length=4096) = ""

    @validator("time")
    def valid_time(cls, value):
        datetime.strptime(value, "%H:%M")
        return value

    @root_validator
    def valid_task(cls, values):
        if values.get("kind") == "plugin":
            if not values.get("plugin") or not values.get("command"):
                raise ValueError("请选择 TeleBox 已加载的插件命令")
            if values.get("chats") or values.get("text"):
                raise ValueError("插件任务不能附带群消息动作")
            if "\n" in values.get("args", "") or "\r" in values.get("args", ""):
                raise ValueError("命令参数不允许换行")
        elif values.get("kind") == "message":
            if not values.get("chats") or not values.get("text", "").strip():
                raise ValueError("每日消息任务须选择对话并填写消息")
            if values.get("plugin") or values.get("command"):
                raise ValueError("每日消息任务不能附带插件动作")
        return values


def _error(exc: ValueError):
    return HTTPException(404 if "不存在" in str(exc) else 400, str(exc))


@router.get("")
def list_tasks():
    service = get_telebox_task_service()
    return {"items": service.list(), "history": service.history()[-100:]}


@router.get("/available/{account}")
def available(account: str):
    try:
        return get_telebox_task_service().available(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("", status_code=201)
async def create(payload: TaskInput):
    try:
        task = get_telebox_task_service().create(payload.dict())
        await sync_jobs()
        return task
    except ValueError as exc:
        raise _error(exc) from None


@router.put("/{identifier}")
async def update(identifier: str, payload: TaskInput):
    try:
        task = get_telebox_task_service().update(identifier, payload.dict())
        await sync_jobs()
        return task
    except ValueError as exc:
        raise _error(exc) from None


@router.delete("/{identifier}")
async def delete(identifier: str):
    try:
        get_telebox_task_service().delete(identifier)
        await sync_jobs()
        return {"ok": True}
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{identifier}/run")
async def run(identifier: str):
    try:
        return await get_telebox_task_service().run(identifier)
    except ValueError as exc:
        raise _error(exc) from None
