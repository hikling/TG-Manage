"""登录会话临时存储与清理。"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from backend.services.telegram.pending_session import (
    cleanup_pending_session,
    promote_pending_session,
)

logger = logging.getLogger("backend.telegram.sessions")

# 全局存储临时的登录 session
_login_sessions: dict = {}
_qr_login_sessions: dict = {}

# 登录 session 清理常量
_LOGIN_SESSION_MAX_AGE = 1800  # 手机号登录 session 最大存活时间（30 分钟）
_QR_LOGIN_SESSION_MAX_AGE = 600  # 扫码登录 session 最大存活时间（10 分钟）
_MAX_LOGIN_SESSIONS = 50  # 每种登录 session 的最大数量


async def _release_login_session(
    value: Any, *, preserve_session: bool = False, session_dir: Path | None = None,
) -> None:
    """关闭临时客户端，取消其计时器，并恰好释放一次账户锁。"""
    if not isinstance(value, dict):
        return
    current = asyncio.current_task()
    pending_path = value.get("pending_path")
    try:
        active_task = value.get("_active_task")
        if active_task is not None and active_task is not current and not active_task.done():
            active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(active_task), timeout=5)

        expire_task = value.get("expire_task")
        if expire_task is not None and expire_task is not current and not expire_task.done():
            expire_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(expire_task), timeout=5)

        client = value.get("client")
        handler = value.get("handler")
        if client and handler:
            try:
                client.remove_handler(*handler)
            except Exception as exc:
                logger.warning("清理扫码登录监听失败 (%s)", type(exc).__name__)
        if client:
            initialized = getattr(client, "is_initialized", False)
            try:
                if initialized:
                    await asyncio.wait_for(client.stop(), timeout=5)
                elif getattr(client, "is_connected", False):
                    await asyncio.wait_for(client.disconnect(), timeout=5)
            except Exception:
                if initialized and getattr(client, "is_connected", False):
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(client.disconnect(), timeout=5)
            storage = getattr(client, "storage", None)
            if not getattr(client, "is_connected", False) and getattr(storage, "conn", None):
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(storage.close(), timeout=5)
        if preserve_session:
            if session_dir is None:
                raise ValueError("保存扫码登录会话缺少数据目录")
            promote_pending_session(pending_path, session_dir, value["account_name"])
    finally:
        try:
            cleanup_pending_session(pending_path)
        finally:
            lock = value.get("lock")
            if lock and lock.locked():
                lock.release()


async def _remove_login_session(
    store: dict, key: str, *, expected: dict | None = None,
    preserve_session: bool = False, session_dir: Path | None = None,
) -> bool:
    """先移出字典再异步关闭，防止并发路径重复释放或误删新会话。"""
    value = store.get(key)
    if value is None or (expected is not None and value is not expected):
        return False
    store.pop(key)
    await _release_login_session(
        value, preserve_session=preserve_session, session_dir=session_dir,
    )
    return True


async def _expire_phone_login_session(key: str, value: dict) -> None:
    """验证码请求无人继续时独立释放连接；不会发起账户检测。"""
    await asyncio.sleep(_LOGIN_SESSION_MAX_AGE)
    await _remove_login_session(_login_sessions, key, expected=value)


def _start_phone_login_expiry(key: str, value: dict) -> None:
    task = asyncio.create_task(_expire_phone_login_session(key, value))
    value["expire_task"] = task

    def observe(completed: asyncio.Task) -> None:
        if completed.cancelled():
            return
        try:
            completed.result()
        except Exception as exc:
            logger.warning("手机号待登录会话到期清理失败 (%s)", type(exc).__name__)

    task.add_done_callback(observe)


def _begin_login_operation(value: dict) -> None:
    task = asyncio.current_task()
    active = value.get("_active_task")
    if active is not None and active is not task and not active.done():
        raise ValueError("登录会话正在处理，请稍后再试")
    value["_active_task"] = task


def _end_login_operation(value: dict) -> None:
    if value.get("_active_task") is asyncio.current_task():
        value.pop("_active_task", None)


async def cleanup_account_login_sessions(account_name: str) -> None:
    """删除账户前关闭它的电话/扫码待登录会话，释放其账户锁。

    调用方不应预先持有该账户锁；此函数不触碰已授权的持久会话。
    """
    for store in (_login_sessions, _qr_login_sessions):
        for key, value in list(store.items()):
            if value.get("account_name") == account_name:
                await _remove_login_session(store, key, expected=value)


async def cleanup_all_login_sessions() -> None:
    """应用关闭时释放所有待登录客户端、到期任务和账户锁。"""
    for store in (_login_sessions, _qr_login_sessions):
        for key, value in list(store.items()):
            await _remove_login_session(store, key, expected=value)


async def _cleanup_expired_login_sessions() -> None:
    """清理过期的登录 session，防止内存泄漏。"""
    now = time.monotonic()

    for store, max_age in (
        (_login_sessions, _LOGIN_SESSION_MAX_AGE),
        (_qr_login_sessions, _QR_LOGIN_SESSION_MAX_AGE),
    ):
        expired_keys = [
            key
            for key, value in list(store.items())
            if value.get("_created_at") is not None
            and (now - value["_created_at"]) > max_age
        ]
        for key in expired_keys:
            await _remove_login_session(store, key)

    for store in (_login_sessions, _qr_login_sessions):
        while len(store) > _MAX_LOGIN_SESSIONS:
            oldest_key = min(
                store.keys(),
                key=lambda k: store[k].get("_created_at", float("inf")),
            )
            await _remove_login_session(store, oldest_key)
