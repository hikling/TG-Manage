"""Bot API management. Tokens are encrypted at rest and never serialized to clients."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr

from backend.core.auth import get_current_user
from backend.core.config import get_settings

router = APIRouter(prefix="/bots", dependencies=[Depends(get_current_user)])
TOKEN_PATTERN = re.compile(r"^[0-9]{5,20}:[A-Za-z0-9_-]{25,100}$")


class BotRegistration(BaseModel):
    token: constr(strip_whitespace=True, min_length=30, max_length=130)


class BotProfile(BaseModel):
    first_name: constr(strip_whitespace=True, min_length=1, max_length=64) | None = None
    description: constr(max_length=512) | None = None
    short_description: constr(max_length=120) | None = None


class BotCommand(BaseModel):
    command: constr(regex=r"^[a-z0-9_]{1,32}$")
    description: constr(strip_whitespace=True, min_length=1, max_length=256)


class BotCommands(BaseModel):
    commands: list[BotCommand] = Field(default_factory=list, max_items=100)


class BotMessage(BaseModel):
    chat_id: constr(regex=r"^-?[0-9]{1,20}$")
    text: constr(strip_whitespace=True, min_length=1, max_length=4096)


def _path() -> Path:
    return get_settings().resolve_workdir() / "bots" / "registry.json"


def _cipher() -> Fernet:
    key = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _load() -> dict[str, dict[str, Any]]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        raise HTTPException(500, "机器人配置读取失败，请检查数据目录") from exc


def _save(data: dict[str, dict[str, Any]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
        path.chmod(0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def _token(bot_id: str) -> str:
    item = _load().get(bot_id)
    if item is None:
        raise HTTPException(404, "机器人不存在")
    try:
        return _cipher().decrypt(item["encrypted_token"].encode()).decode()
    except (InvalidToken, KeyError, ValueError) as exc:
        raise HTTPException(503, "无法解密机器人 Token，请检查 APP_SECRET_KEY") from exc


async def _call(token: str, method: str, payload: dict | None = None) -> Any:
    # HTTP errors and Bot API errors can include a URL containing the token.
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/{method}", json=payload or {}
            )
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Telegram Bot API 暂时不可用") from exc
    if not response.is_success or not isinstance(data, dict) or not data.get("ok"):
        raise HTTPException(400, "机器人请求失败，请检查 Token、权限或参数")
    return data.get("result")


def _public(bot_id: str, item: dict) -> dict:
    return {
        "id": bot_id,
        "username": item.get("username", ""),
        "first_name": item.get("first_name", ""),
        "description": item.get("description", ""),
        "short_description": item.get("short_description", ""),
        "running": True,
    }


@router.get("")
async def list_bots():
    return {"items": [_public(bot_id, item) for bot_id, item in _load().items()]}


@router.post("")
async def register(body: BotRegistration):
    if not TOKEN_PATTERN.fullmatch(body.token):
        raise HTTPException(422, "Bot Token 格式无效")
    info = await _call(body.token, "getMe")
    if not isinstance(info, dict) or not info.get("is_bot"):
        raise HTTPException(400, "该 Token 未绑定 Telegram 机器人")
    bot_id = str(info["id"])
    bots = _load()
    bots[bot_id] = {
        "encrypted_token": _cipher().encrypt(body.token.encode()).decode(),
        "username": info.get("username", ""),
        "first_name": info.get("first_name", ""),
    }
    _save(bots)
    return _public(bot_id, bots[bot_id])


@router.get("/{bot_id}")
async def detail(bot_id: str):
    token = _token(bot_id)
    data = _load()[bot_id]
    info = await _call(token, "getMe")
    description = await _call(token, "getMyDescription")
    short = await _call(token, "getMyShortDescription")
    return {
        **_public(bot_id, data),
        "first_name": info.get("first_name", data.get("first_name", "")),
        "description": description.get("description", ""),
        "short_description": short.get("short_description", ""),
    }


@router.put("/{bot_id}")
async def update(bot_id: str, body: BotProfile):
    token = _token(bot_id)
    if body.first_name is not None:
        await _call(token, "setMyName", {"name": body.first_name})
    if body.description is not None:
        await _call(token, "setMyDescription", {"description": body.description})
    if body.short_description is not None:
        await _call(token, "setMyShortDescription", {"short_description": body.short_description})
    bots = _load()
    if body.first_name is not None:
        bots[bot_id]["first_name"] = body.first_name
        _save(bots)
    return await detail(bot_id)


@router.delete("/{bot_id}")
async def remove(bot_id: str):
    bots = _load()
    if bot_id not in bots:
        raise HTTPException(404, "机器人不存在")
    bots.pop(bot_id)
    _save(bots)
    return {"ok": True}


@router.get("/{bot_id}/commands")
async def commands(bot_id: str):
    return {"commands": await _call(_token(bot_id), "getMyCommands")}


@router.put("/{bot_id}/commands")
async def update_commands(bot_id: str, body: BotCommands):
    await _call(_token(bot_id), "setMyCommands", {"commands": [item.dict() for item in body.commands]})
    return {"commands": [item.dict() for item in body.commands]}


@router.post("/{bot_id}/messages")
async def send_bot_message(bot_id: str, body: BotMessage):
    sent = await _call(_token(bot_id), "sendMessage", body.dict())
    return {"message_id": sent.get("message_id"), "chat_id": str(sent.get("chat", {}).get("id", ""))}
