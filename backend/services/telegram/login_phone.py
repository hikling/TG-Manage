"""TelegramService mixin: login_phone."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from backend.core.config import get_settings
from backend.services.telegram.accounts import (
    mark_account_connected,
)
from backend.services.telegram.pending_session import (
    cleanup_pending_session,
    new_pending_session_path,
    promote_pending_session,
)
from backend.services.telegram.sessions import (
    _cleanup_expired_login_sessions,
    _login_sessions,
    _qr_login_sessions,
)
from backend.utils.account_locks import get_account_lock
from backend.utils.proxy import require_proxy_dict
from backend.utils.tg_session import (
    get_global_semaphore,
    get_session_mode,
    save_session_string_file,
    set_account_api_credentials,
    set_account_session_string,
)

settings = get_settings()


logger = logging.getLogger("backend.telegram.login_phone")


def _sent_code_metadata(sent_code) -> Dict[str, Any]:
    def channel(value):
        name = getattr(value, "name", None)
        if isinstance(name, str):
            return name.lower()
        fallback = getattr(value, "value", None)
        return fallback.lower() if isinstance(fallback, str) else None

    return {
        "delivery_type": channel(getattr(sent_code, "type", None)),
        "next_type": channel(getattr(sent_code, "next_type", None)),
        "retry_after": getattr(sent_code, "timeout", None),
    }


async def _discard_login_client(client, session_key: Optional[str], release_lock, pending_path=None) -> None:
    """登录流程的统一清理：断连（容忍已断开/失败）→ 弹出会话 → 释放账号锁。

    各异常分支共用，避免断连/弹会话/放锁三环在新增分支时漏写。
    """
    try:
        try:
            await asyncio.wait_for(client.disconnect(), timeout=5)
        except Exception:
            storage = getattr(client, "storage", None)
            if getattr(storage, "conn", None):
                try:
                    await asyncio.wait_for(storage.close(), timeout=5)
                except Exception:
                    pass
    finally:
        try:
            cleanup_pending_session(pending_path)
        finally:
            if session_key:
                _login_sessions.pop(session_key, None)
            if release_lock:
                release_lock()


class TelegramPhoneLoginMixin:

    @staticmethod
    def _normalize_login_token_expires(expires: Optional[int]) -> int:
        now = int(time.time())
        if not expires:
            return now
        try:
            expires_int = int(expires)
        except (TypeError, ValueError):
            return now
        # 兼容 expires 为相对秒数的情况
        if expires_int < 1_000_000_000:
            expires_ts = now + max(0, expires_int)
        else:
            expires_ts = expires_int
        return expires_ts


    async def start_login(
        self, account_name: str, phone_number: str, proxy: Optional[str] = None,
        api_id: int = None, api_hash: str = None,
    ) -> Dict[str, Any]:
        """
        开始登录流程（发送验证码）

        这个方法会：
        1. 创建 Pyrogram 客户端
        2. 发送验证码到手机
        3. 返回 phone_code_hash 用于后续验证

        Args:
            account_name: 账号名称
            phone_number: 手机号（国际格式，如 +8613800138000）
            proxy: 代理地址（可选）

        Returns:
            包含 phone_code_hash 的字典
        """

        proxy_dict = require_proxy_dict(proxy)
        account_name = self._normalize_account_name(account_name)
        phone_number = str(phone_number or "").strip().replace(" ", "").replace("-", "")
        if not phone_number:
            raise ValueError("手机号不能为空")

        from pyrogram import Client
        from pyrogram.errors import FloodWait, PhoneNumberInvalid

        from tg_manage.core import close_client_by_name

        await _cleanup_expired_login_sessions()

        # A QR attempt for this account holds the same lock until canceled.
        for login_id, data in list(_qr_login_sessions.items()):
            if data.get("account_name") == account_name:
                await self._cleanup_qr_login(login_id)

        account_lock = get_account_lock(account_name)
        session_mode = get_session_mode()
        global_semaphore = get_global_semaphore()

        # 1. 清理全局 _login_sessions 中可能存在的残留连接
        # _login_sessions key 格式: f"{account_name}_{phone_number}"
        for key, value in list(_login_sessions.items()):
            if key.startswith(f"{account_name}_"):
                old_lock = value.get("lock")
                def release_old_lock(lock=old_lock):
                    if lock and lock.locked():
                        lock.release()

                await _discard_login_client(
                    value["client"], key, release_old_lock, value.get("pending_path"),
                )

        # 获取账号锁，避免与任务并发写 session
        await account_lock.acquire()

        def _release_account_lock() -> None:
            if account_lock.locked():
                account_lock.release()

        # 2. 确保没有后台任务占用
        try:
            await asyncio.wait_for(
                close_client_by_name(account_name, workdir=self.session_dir), timeout=8,
            )
        except asyncio.CancelledError:
            _release_account_lock()
            raise
        except asyncio.TimeoutError:
            _release_account_lock()
            raise ValueError("现有账户连接未及时释放，请稍后再试") from None
        except Exception as e:
            _release_account_lock()
            logger.debug("start_login 清理后台客户端失败 (%s)", type(e).__name__)
            raise ValueError("现有账户连接清理失败，请稍后再试") from None

        # Each login supplies credentials for this account.
        from backend.services.telegram.credentials import (
            validate_telegram_api_credentials,
        )

        try:
            api_id, api_hash = validate_telegram_api_credentials(api_id, api_hash)
        except ValueError:
            _release_account_lock()
            raise ValueError("Telegram API ID / API Hash 未配置或无效") from None

        pending_path = None
        try:
            pending_path = new_pending_session_path(self.session_dir, account_name) if session_mode == "file" else None
            client = Client(
                name=str(pending_path or self.session_dir / account_name),
                api_id=api_id, api_hash=api_hash, proxy=proxy_dict,
                in_memory=session_mode == "string", no_updates=True,
            )
        except Exception:
            cleanup_pending_session(pending_path)
            _release_account_lock()
            raise ValueError("登录会话初始化失败，请检查数据目录") from None

        try:
            async with global_semaphore:
                await asyncio.wait_for(client.connect(), timeout=20)

                self._accounts_cache = None

                if hasattr(client, "storage") and getattr(client.storage, "conn", None):
                    try:
                        client.storage.conn.execute("PRAGMA journal_mode=WAL")
                        client.storage.conn.execute("PRAGMA busy_timeout=30000")
                    except Exception:
                        pass

                sent_code = await asyncio.wait_for(client.send_code(phone_number), timeout=20)

            if not getattr(sent_code, "phone_code_hash", None):
                raise ValueError("Telegram 未返回验证码会话，请稍后重试")

            metadata = _sent_code_metadata(sent_code)

            session_key = f"{account_name}_{phone_number}"
            _login_sessions[session_key] = {
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
                "proxy": proxy,
                "lock": account_lock,
                "account_name": account_name,
                "api_id": api_id,
                "api_hash": api_hash,
                "pending_path": pending_path,
                "sent_at": time.monotonic(),
                **metadata,
                "_created_at": time.monotonic(),
            }

            # 保持连接，避免 session 变化导致验证码失效 (PhoneCodeExpired)
            # 断开连接会导致服务端重新分配 Session ID，从而使之前的 hash 失效

            return {
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
                "account_name": account_name,
                **metadata,
            }

        except PhoneNumberInvalid:
            await _discard_login_client(client, None, _release_account_lock, pending_path)
            raise ValueError("手机号格式无效，请使用国际格式（如 +8613800138000）")
        except FloodWait as e:
            await _discard_login_client(client, None, _release_account_lock, pending_path)
            raise ValueError(f"请求过于频繁，请等待 {e.value} 秒后重试")
        except asyncio.TimeoutError:
            await _discard_login_client(client, None, _release_account_lock, pending_path)
            raise ValueError("连接 Telegram 超时；未确认验证码请求是否送达，请稍后查看已登录设备") from None
        except asyncio.CancelledError:
            await _discard_login_client(client, None, _release_account_lock, pending_path)
            raise
        except Exception as e:
            logger.warning("手机号登录发送验证码阶段异常 (%s)", type(e).__name__)
            await _discard_login_client(client, None, _release_account_lock, pending_path)

            error_details = str(e)
            if (
                "database is locked" in error_details
                or "unable to open database file" in error_details
            ):
                raise ValueError(
                    "会话文件被占用，请稍后重试或重启程序"
                )

            raise ValueError("发送验证码失败，请检查账号代理或网络后重试") from None


    async def resend_login(
        self, account_name: str, phone_number: str, phone_code_hash: str,
    ) -> Dict[str, Any]:
        """Use Telegram's specified fallback route without creating another auth session."""
        from pyrogram.errors import FloodWait

        account_name = self._normalize_account_name(account_name)
        phone_number = str(phone_number or "").strip().replace(" ", "").replace("-", "")
        data = _login_sessions.get(f"{account_name}_{phone_number}")
        if not data or data.get("phone_code_hash") != phone_code_hash:
            raise ValueError("登录会话已过期，请重新开始登录")
        if not data.get("next_type"):
            raise ValueError("Telegram 未提供其他验证码送达方式，请检查现有设备或使用扫码登录")
        wait_seconds = max(60, int(data.get("retry_after") or 0))
        elapsed = time.monotonic() - float(data.get("sent_at") or 0)
        if elapsed < wait_seconds:
            raise ValueError(f"请等待 {int(wait_seconds - elapsed) + 1} 秒后再重新获取验证码")

        try:
            async with get_global_semaphore():
                sent_code = await asyncio.wait_for(
                    data["client"].resend_code(phone_number, phone_code_hash), timeout=20,
                )
        except FloodWait as exc:
            raise ValueError(f"请求过于频繁，请等待 {exc.value} 秒后重试") from None
        except asyncio.TimeoutError:
            data["sent_at"] = time.monotonic()
            raise ValueError("Telegram 重发请求超时，送达状态未确认；请稍后查看已登录设备") from None
        if not getattr(sent_code, "phone_code_hash", None):
            raise ValueError("Telegram 未返回新的验证码会话，请稍后重试")
        metadata = _sent_code_metadata(sent_code)
        data.update({
            "phone_code_hash": sent_code.phone_code_hash,
            "sent_at": time.monotonic(),
            **metadata,
        })
        return {
            "phone_code_hash": sent_code.phone_code_hash,
            "phone_number": phone_number,
            "account_name": account_name,
            **metadata,
        }


    async def verify_login(
        self,
        account_name: str,
        phone_number: str,
        phone_code: str,
        phone_code_hash: str,
        password: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        验证登录（输入验证码和可选的2FA密码）

        Args:
            account_name: 账号名称
            phone_number: 手机号
            phone_code: 验证码
            phone_code_hash: 从 start_login 返回的 hash
            password: 2FA 密码（可选）
            proxy: 代理地址（可选）

        Returns:
            登录结果
        """
        account_name = self._normalize_account_name(account_name)
        phone_number = str(phone_number or "").strip().replace(" ", "").replace("-", "")
        phone_code = str(phone_code or "").strip()
        phone_code_hash = str(phone_code_hash or "").strip()

        from pyrogram.errors import (
            PasswordHashInvalid,
            PhoneCodeExpired,
            PhoneCodeInvalid,
            SessionPasswordNeeded,
        )

        # 尝试从全局字典获取之前的 client
        session_key = f"{account_name}_{phone_number}"
        session_data = _login_sessions.get(session_key)

        if not session_data:
            raise ValueError("登录会话已过期，请重新发送验证码")

        client = session_data["client"]
        global_semaphore = get_global_semaphore()

        account_lock = session_data.get("lock")

        def _release_account_lock() -> None:
            if account_lock and account_lock.locked():
                account_lock.release()

        if account_lock and not account_lock.locked():
            await account_lock.acquire()

        try:
            async with global_semaphore:
                # 重新连接 (因为 start_login 中断开了)
                if not client.is_connected:
                    await client.connect()

                # 移除验证码中的空格和横线
                phone_code = phone_code.strip().replace(" ", "").replace("-", "")

                # 尝试使用验证码登录
                try:
                    await client.sign_in(phone_number, phone_code_hash, phone_code)

                    # 登录成功，获取用户信息
                    # get_me 走超时保护：网络挂起时登录接口不能无限等待
                    me = await asyncio.wait_for(client.get_me(), timeout=10)
                    await self._persist_client_session(client, account_name, session_data.get("proxy"))
                    set_account_api_credentials(account_name, session_data["api_id"], session_data["api_hash"])

                    # 断开连接并清理（成功路径同样容忍断连抖动，避免已登录被误报失败）
                    await client.disconnect()
                    promote_pending_session(session_data.get("pending_path"), self.session_dir, account_name)
                    await _discard_login_client(client, session_key, _release_account_lock)

                    return {
                        "success": True,
                        "user_id": me.id,
                        "first_name": me.first_name,
                        "username": me.username,
                    }

                except SessionPasswordNeeded:
                    # 需要 2FA 密码
                    if not password:
                        # 不断开连接，等待用户输入 2FA 密码
                        raise ValueError("此账号启用了两步验证，请输入 2FA 密码")

                    # 使用 2FA 密码登录
                    try:
                        await client.check_password(password)
                        me = await asyncio.wait_for(client.get_me(), timeout=10)
                        await self._persist_client_session(client, account_name, session_data.get("proxy"))
                        set_account_api_credentials(account_name, session_data["api_id"], session_data["api_hash"])

                        # 断开连接并清理
                        await client.disconnect()
                        promote_pending_session(session_data.get("pending_path"), self.session_dir, account_name)
                        await _discard_login_client(client, session_key, _release_account_lock)

                        return {
                            "success": True,
                            "user_id": me.id,
                            "first_name": me.first_name,
                            "username": me.username,
                        }
                    except PasswordHashInvalid:
                        raise ValueError("2FA 密码错误")

        except PhoneCodeInvalid:
            # Keep the same Telegram code hash/session for a corrected entry.
            raise ValueError("验证码错误，请检查验证码是否正确")
        except PhoneCodeExpired:
            await _discard_login_client(client, session_key, _release_account_lock, session_data.get("pending_path"))
            raise ValueError("验证码已过期，请重新获取")
        except ValueError as e:
            # 如果是 2FA 错误，不清理 session
            message = str(e)
            if message not in {"此账号启用了两步验证，请输入 2FA 密码", "2FA 密码错误"}:
                await _discard_login_client(client, session_key, _release_account_lock, session_data.get("pending_path"))
            if message in {"此账号启用了两步验证，请输入 2FA 密码", "2FA 密码错误", "导出 session_string 失败", "INVALID_ACCOUNT_PROXY"}:
                raise ValueError(message) from None
            raise ValueError("登录失败，请检查账号代理或网络后重试") from None
        except Exception as e:
            await _discard_login_client(client, session_key, _release_account_lock, session_data.get("pending_path"))

            # 更详细的错误信息
            error_msg = str(e)
            if "PHONE_CODE_INVALID" in error_msg:
                raise ValueError("验证码错误，请检查验证码是否正确")
            elif "PHONE_CODE_EXPIRED" in error_msg:
                raise ValueError("验证码已过期，请重新获取")
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                raise ValueError("此账号启用了两步验证，请输入 2FA 密码")
            else:
                raise ValueError("登录失败，请检查账号代理或网络后重试") from None


    async def cancel_login(self, account_name: str, phone_number: str, phone_code_hash: str) -> bool:
        account_name = self._normalize_account_name(account_name)
        phone_number = str(phone_number or "").strip().replace(" ", "").replace("-", "")
        data = _login_sessions.get(f"{account_name}_{phone_number}")
        if not data or data.get("phone_code_hash") != phone_code_hash:
            return False
        lock = data.get("lock")

        def release_lock() -> None:
            if lock and lock.locked():
                lock.release()

        await _discard_login_client(
            data["client"], f"{account_name}_{phone_number}", release_lock,
            data.get("pending_path"),
        )
        return True


    async def _persist_client_session(
        self, client, account_name: str, proxy: Optional[str] = None
    ) -> None:
        session_mode = get_session_mode()
        if session_mode == "string":
            session_string = await client.export_session_string()
            if not session_string:
                raise ValueError("导出 session_string 失败")
            set_account_session_string(account_name, session_string)
            save_session_string_file(self.session_dir, account_name, session_string)
            mark_account_connected(account_name)
        else:
            # 即使在 file 模式，也尝试保存 session_string 作为降级方案
            try:
                session_string = await client.export_session_string()
            except Exception:
                session_string = None
            if session_string:
                try:
                    set_account_session_string(account_name, session_string)
                    save_session_string_file(self.session_dir, account_name, session_string)
                    mark_account_connected(account_name)
                except Exception:
                    pass
        from backend.utils.tg_session import set_account_profile

        set_account_profile(account_name, proxy=proxy)
        mark_account_connected(account_name)
        self._accounts_cache = None
