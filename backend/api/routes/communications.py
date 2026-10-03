"""所有聊天、群聊及账号代理 API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, constr, validator

from backend.core.auth import get_current_user
from backend.services import communications as service

router = APIRouter(prefix="/communications", dependencies=[Depends(get_current_user)])


class ChatInput(BaseModel):
    chat_id: constr(strip_whitespace=True, min_length=1, max_length=64)

    @validator("chat_id")
    def valid_peer(cls, value):
        service.peer_id(value)
        return value


class MessageInput(ChatInput):
    text: constr(min_length=1, max_length=4096)
    reply_to_message_id: int | None = Field(None, ge=1, le=2147483647)

    @validator("text")
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value


class DialogAction(ChatInput):
    action: Literal["read", "archive", "unarchive", "pin", "unpin", "mute", "unmute"]


class ProxyInput(BaseModel):
    proxy: constr(max_length=2048)


@router.get("/proxies")
async def proxies():
    return service.proxies()


@router.put("/{account}/proxy")
async def set_proxy(account: str, body: ProxyInput):
    return await service.set_proxy(account, body.proxy)


@router.get("/{account}/dialogs")
async def dialogs(account: str, query: str = Query("", max_length=200), offset: int = Query(0, ge=0, le=100000), limit: int = Query(50, ge=1, le=100), archived: bool = False, kind: Literal["all", "groups"] = "all"):
    return await service.dialogs(account, query, offset, limit, archived, kind)


@router.get("/{account}/messages")
async def messages(account: str, chat_id: str = Query(..., max_length=64), before_id: int = Query(0, ge=0, le=2147483647), limit: int = Query(50, ge=1, le=100)):
    return await service.messages(account, chat_id, before_id, limit)


@router.post("/{account}/messages")
async def send(account: str, body: MessageInput):
    return await service.send_message(account, body.chat_id, body.text, body.reply_to_message_id)


@router.put("/{account}/messages/{message_id}")
async def edit(account: str, body: MessageInput, message_id: int):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    return await service.edit_message(account, body.chat_id, message_id, body.text)


@router.delete("/{account}/messages/{message_id}")
async def delete(account: str, body: ChatInput, message_id: int):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    return await service.delete_message(account, body.chat_id, message_id)


@router.post("/{account}/media")
async def upload(account: str, chat_id: str = Form(...), file: UploadFile = File(...), caption: str = Form(""), reply_to_message_id: int | None = Form(None)):
    from pathlib import PurePosixPath
    try:
        service.checked_account(account)
        service.peer_id(chat_id)
        if len(caption) > 1024 or (reply_to_message_id is not None and not 1 <= reply_to_message_id <= 2147483647):
            raise HTTPException(422, "附件说明或回复消息 ID 无效")
        data = await file.read(service.MAX_MEDIA_BYTES + 1)
        if not data:
            raise HTTPException(422, "不能发送空文件")
        filename = PurePosixPath((file.filename or "attachment.bin").replace("\\", "/")).name
        filename = "".join(c for c in filename if c.isprintable())[:200] or "attachment.bin"
        return await service.send_media(account, chat_id, data, filename, caption, reply_to_message_id)
    finally:
        await file.close()


@router.get("/{account}/media/{message_id}")
async def download(account: str, message_id: int, chat_id: str = Query(..., max_length=64)):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    data = await service.download_media(account, chat_id, message_id)
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="telegram-{message_id}.bin"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
@router.post("/{account}/dialogs/action")
async def action(account: str, body: DialogAction):
    return await service.dialog_action(account, body.chat_id, body.action)
