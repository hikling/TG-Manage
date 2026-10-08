"""所有聊天、群聊及账号代理 API。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, constr, validator

from backend.core.auth import get_current_user
from backend.services import communications as service
from backend.services.config import get_config_service

router = APIRouter(prefix="/communications", dependencies=[Depends(get_current_user)])


def require_chat_center():
    if get_config_service().get_global_settings().get("chat_center_enabled") is not True:
        raise HTTPException(403, "聊天中心未开启；官方验证码请在账号管理中查看")


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


@router.get("/{account}/dialogs", dependencies=[Depends(require_chat_center)])
async def dialogs(account: str, query: str = Query("", max_length=200), offset: int = Query(0, ge=0, le=100000), limit: int = Query(50, ge=1, le=100), archived: bool = False, kind: Literal["all", "groups"] = "all"):
    return await service.dialogs(account, query, offset, limit, archived, kind)


@router.get("/{account}/messages", dependencies=[Depends(require_chat_center)])
async def messages(account: str, chat_id: str = Query(..., max_length=64), before_id: int = Query(0, ge=0, le=2147483647), limit: int = Query(50, ge=1, le=100)):
    return await service.messages(account, chat_id, before_id, limit)


@router.post("/{account}/messages", dependencies=[Depends(require_chat_center)])
async def send(account: str, body: MessageInput):
    return await service.send_message(account, body.chat_id, body.text, body.reply_to_message_id)


@router.put("/{account}/messages/{message_id}", dependencies=[Depends(require_chat_center)])
async def edit(account: str, body: MessageInput, message_id: int):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    return await service.edit_message(account, body.chat_id, message_id, body.text)


@router.delete("/{account}/messages/{message_id}", dependencies=[Depends(require_chat_center)])
async def delete(account: str, body: ChatInput, message_id: int):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    return await service.delete_message(account, body.chat_id, message_id)


@router.post("/{account}/media", dependencies=[Depends(require_chat_center)])
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


@router.get("/{account}/media/{message_id}", dependencies=[Depends(require_chat_center)])
async def download(account: str, message_id: int, chat_id: str = Query(..., max_length=64)):
    if not 1 <= message_id <= 2147483647:
        raise HTTPException(422, "消息 ID 无效")
    data = await service.download_media(account, chat_id, message_id)
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="telegram-{message_id}.bin"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{account}/avatar/{chat_id}", dependencies=[Depends(require_chat_center)])
async def avatar(account: str, chat_id: str):
    from backend.core.config import get_settings
    from backend.services import avatar_cache
    from backend.services.telegram import get_telegram_service

    service.checked_account(account)
    peer = service.peer_id(chat_id)
    if not isinstance(peer, int):
        raise HTTPException(422, "头像需要会话 ID")
    directory = get_settings().resolve_workdir() / "avatars" / "chats"
    directory.mkdir(parents=True, exist_ok=True)
    avatar_cache.enforce_chat_cache_limit(directory)
    cache = directory / f"chat_{peer}.jpg"
    marker = directory / f"chat_{peer}.no_avatar"
    if avatar_cache.marker_hits_no_avatar(marker):
        raise HTTPException(404, "No avatar available")
    data = avatar_cache.read_cached_avatar(cache)
    if data is None:
        try:
            data = await avatar_cache.get_avatar_bytes(
                cache, marker,
                lambda: get_telegram_service().download_chat_avatar(account, peer),
                max_bytes=avatar_cache.CHAT_AVATAR_MAX_BYTES,
            )
        except Exception:
            raise HTTPException(502, "头像暂时不可用") from None
        if data is None:
            avatar_cache.mark_no_avatar(marker)
            raise HTTPException(404, "No avatar available")
        avatar_cache.enforce_chat_cache_limit(directory)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
@router.post("/{account}/dialogs/action", dependencies=[Depends(require_chat_center)])
async def action(account: str, body: DialogAction):
    return await service.dialog_action(account, body.chat_id, body.action)
