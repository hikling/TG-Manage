"""账号聊天操作：复用已有授权会话，不触发交互式登录。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from fastapi import HTTPException

from backend.services.telegram import get_telegram_service
from backend.utils.account_locks import get_account_lock
from backend.utils.names import validate_storage_name
from backend.utils.proxy import build_proxy_dict, normalize_proxy_url
from backend.utils.tg_session import (
    get_account_proxy,
    get_global_semaphore,
    get_media_upload_semaphore,
    set_account_profile,
)

MAX_MEDIA_BYTES = 20 * 1024 * 1024


def peer_id(value: str) -> int | str:
    """仅接受 Telegram ID 或用户名，拒绝链接及文件系统输入。"""
    import re
    value = str(value).strip()
    if re.fullmatch(r"-?[0-9]{1,20}", value):
        number = int(value)
        if number and -(2**63) < number < 2**63:
            return number
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value):
        return value.lstrip("@")
    raise HTTPException(422, "会话 ID 或用户名无效")


def checked_account(account: str):
    try:
        account = validate_storage_name(account, field_name="account")
    except ValueError:
        raise HTTPException(422, "账号名称无效") from None
    service = get_telegram_service()
    if not service.account_exists(account):
        raise HTTPException(404, "账号不存在，请先登录账号")
    return service, account


@asynccontextmanager
async def _client_for_account(service: Any, account: str):
    # 与签到、设备及账号修改共用锁和带引用计数的 Client。
    async with get_account_lock(account):
        try:
            # Match the established account-lock -> global Telegram permit order.
            async with get_global_semaphore():
                # Waiting or canceled requests must not retain an unstarted
                # client in the shared client cache.
                client, _ = service._build_account_client(account, no_updates=True)
                async with client:
                    yield client
        except HTTPException:
            raise
        except Exception as exc:
            # Telegram 异常可能携带手机号/请求正文，不向面板回传原始异常。
            from pyrogram.errors import FloodWait, RPCError
            if isinstance(exc, FloodWait):
                raise HTTPException(429, "Telegram 操作频繁，请稍后重试", headers={"Retry-After": str(max(1, int(exc.value)))}) from None
            if isinstance(exc, RPCError):
                code = getattr(exc, "ID", "TELEGRAM_ERROR")
                raise HTTPException(400, f"Telegram 操作失败：{code}") from None
            raise HTTPException(502, "Telegram 连接或操作失败，请检查账号授权及代理") from None


@asynccontextmanager
async def account_client(account: str):
    service, account = checked_account(account)
    async with _client_for_account(service, account) as client:
        yield client


@asynccontextmanager
async def media_upload_admission(account: str):
    """Bound upload buffers before reading, then retain Telegram admission through send."""
    service, account = checked_account(account)
    async with get_media_upload_semaphore():
        async with _client_for_account(service, account) as client:
            yield client


def timestamp(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def message_data(message: Any) -> dict:
    sender = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    sender_name = (getattr(sender, "title", None) or " ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])))
    media = getattr(message, "media", None)
    return {
        "id": message.id, "chat_id": str(message.chat.id),
        "text": str(getattr(message, "text", None) or getattr(message, "caption", None) or ""),
        "date": timestamp(getattr(message, "date", None)),
        "outgoing": bool(getattr(message, "outgoing", False)),
        "sender_name": sender_name or "", "reply_to_message_id": getattr(message, "reply_to_message_id", None),
        "media_type": getattr(media, "value", str(media)) if media else None,
        "has_media": bool(media),
    }


def dialog_data(dialog: Any, archived: bool) -> dict:
    chat = dialog.chat
    last = getattr(dialog, "top_message", None)
    kind = getattr(chat.type, "value", str(chat.type))
    return {"id": str(chat.id), "title": getattr(chat, "title", None) or " ".join(filter(None, [getattr(chat, "first_name", None), getattr(chat, "last_name", None)])) or str(chat.id),
            "username": getattr(chat, "username", None), "type": kind,
            "unread_count": getattr(dialog, "unread_messages_count", 0), "archived": archived,
            "last_message": str(getattr(last, "text", None) or getattr(last, "caption", None) or ""),
            "last_message_at": timestamp(getattr(last, "date", None))}


async def dialogs(account: str, query: str = "", offset: int = 0, limit: int = 50, archived: bool = False, kind: str = "all") -> dict:
    items = []
    matched = 0
    async with account_client(account) as client:
        async for dialog in client.get_dialogs(from_archive=archived):
            item = dialog_data(dialog, archived)
            if kind == "groups" and item["type"] not in {"group", "supergroup"}:
                continue
            if query and query.casefold() not in f'{item["title"]} {item["username"] or ""} {item["last_message"]}'.casefold():
                continue
            matched += 1
            if matched <= offset:
                continue
            items.append(item)
            if len(items) > limit:
                break
    return {"items": items[:limit], "has_more": len(items) > limit, "next_offset": offset + min(len(items), limit)}


async def messages(account: str, chat_id: str, before_id: int, limit: int) -> dict:
    peer = peer_id(chat_id)
    items = []
    async with account_client(account) as client:
        async for message in client.get_chat_history(peer, offset_id=before_id, limit=limit + 1):
            if not getattr(message, "empty", False):
                items.append(message_data(message))
    page = items[:limit]
    return {"items": list(reversed(page)), "has_more": len(items) > limit, "next_before_id": min((m["id"] for m in page), default=0)}


async def send_message(account: str, chat_id: str, text: str, reply: int | None = None):
    from pyrogram.enums import ParseMode
    async with account_client(account) as client:
        return message_data(await client.send_message(peer_id(chat_id), text, reply_to_message_id=reply, parse_mode=ParseMode.DISABLED))


async def edit_message(account: str, chat_id: str, message_id: int, text: str):
    from pyrogram.enums import ParseMode
    async with account_client(account) as client:
        return message_data(await client.edit_message_text(peer_id(chat_id), message_id, text, parse_mode=ParseMode.DISABLED))


async def delete_message(account: str, chat_id: str, message_id: int):
    async with account_client(account) as client:
        await client.delete_messages(peer_id(chat_id), message_id, revoke=True)
    return {"ok": True}


async def send_media_with_client(client: Any, chat_id: str, data: bytes, filename: str, caption: str, reply: int | None):
    from pyrogram.enums import ParseMode
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(413, "附件不能超过 20 MiB")
    with BytesIO(data) as stream:
        stream.name = filename
        return message_data(await client.send_document(peer_id(chat_id), stream, file_name=filename, caption=caption, reply_to_message_id=reply, parse_mode=ParseMode.DISABLED))


async def send_media(account: str, chat_id: str, data: bytes, filename: str, caption: str, reply: int | None):
    async with account_client(account) as client:
        return await send_media_with_client(
            client, chat_id, data, filename, caption, reply
        )


async def download_media(account: str, chat_id: str, message_id: int) -> bytes:
    async with account_client(account) as client:
        message = await client.get_messages(peer_id(chat_id), message_id)
        if not message or not getattr(message, "media", None):
            raise HTTPException(404, "消息附件不存在")
        media = next((getattr(message, key, None) for key in ("document", "video", "audio", "voice", "photo", "animation", "sticker", "video_note") if getattr(message, key, None)), None)
        if media is None:
            raise HTTPException(400, "该消息类型没有可下载的附件")
        if getattr(media, "file_size", 0) and media.file_size > MAX_MEDIA_BYTES:
            raise HTTPException(413, "附件超过 20 MiB 下载限制")
        data = bytearray()
        # 分块读取并检查实际长度，避免 Telegram 元数据缺失时无限分配内存。
        async for chunk in client.stream_media(message):
            data.extend(chunk)
            if len(data) > MAX_MEDIA_BYTES:
                raise HTTPException(413, "附件超过 20 MiB 下载限制")
        return bytes(data)


async def dialog_action(account: str, chat_id: str, action: str):
    peer = peer_id(chat_id)
    async with account_client(account) as client:
        methods = {"read": "read_chat_history", "archive": "archive_chats", "unarchive": "unarchive_chats"}
        if action in methods:
            await getattr(client, methods[action])(peer)
        elif action in {"pin", "unpin"}:
            from pyrogram import raw
            await client.invoke(raw.functions.messages.ToggleDialogPin(
                peer=raw.types.InputDialogPeer(peer=await client.resolve_peer(peer)),
                pinned=action == "pin",
            ))
        elif action in {"mute", "unmute"}:
            from pyrogram import raw
            await client.invoke(raw.functions.account.UpdateNotifySettings(
                peer=raw.types.InputNotifyPeer(peer=await client.resolve_peer(peer)),
                settings=raw.types.InputPeerNotifySettings(mute_until=2147483647 if action == "mute" else 0)))
        else:
            raise HTTPException(422, "不支持的会话操作")
    return {"ok": True}


def proxies():
    return {"items": [{"account": item["name"], "proxy": get_account_proxy(item["name"]) or ""} for item in get_telegram_service().list_accounts()]}


async def set_proxy(account: str, proxy: str):
    service, account = checked_account(account)
    proxy = normalize_proxy_url(proxy)
    if proxy and not build_proxy_dict(proxy):
        raise HTTPException(422, "代理地址无效，支持 HTTP、HTTPS、SOCKS4 和 SOCKS5")
    async with get_account_lock(account):
        set_account_profile(account, proxy=proxy)
        service._accounts_cache = None
    return {"ok": True, "message": "代理已保存，将在账号下一次连接时生效"}
