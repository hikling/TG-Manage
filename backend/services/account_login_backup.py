"""Portable, password-encrypted backup of authorized Telegram account logins."""
from __future__ import annotations

import base64
import copy
import json
import os
import secrets
import sqlite3
import struct
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from backend.services.telegram.credentials import validate_telegram_api_credentials
from backend.utils.names import validate_storage_name
from backend.utils.tg_session import (
    _account_cipher,
    _load_account_store,
    _save_account_store,
    get_account_api_credentials,
    get_session_mode,
    is_valid_session_string,
    load_account_session_string,
)

MAGIC = b"TGLOGIN1"
MAX_BACKUP_BYTES = 10 * 1024 * 1024
ITERATIONS = 600_000


class LoginBackupError(ValueError):
    """Safe user-visible validation failure, without credentials in its text."""


def _password(value: str) -> bytes:
    if not isinstance(value, str) or len(value) < 12 or len(value.encode("utf-8")) > 1024:
        raise LoginBackupError("备份密码至少需要 12 个字符，且不能超过 1024 字节")
    return value.encode("utf-8")


def _key(password: bytes, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(password)


def _safe_name(value: str) -> str:
    name = validate_storage_name(value, field_name="account_name")
    if name != value:
        raise LoginBackupError("备份包含不安全的账户名称")
    # Import files can originate on Linux and must remain safe on Windows too.
    if any(char in name for char in '<>:"|?*') or name.endswith((" ", ".")):
        raise LoginBackupError("备份包含不安全的账户名称")
    if name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise LoginBackupError("备份包含不安全的账户名称")
    return name


def _normalize_session(value: str, api_id: int) -> tuple[str, tuple[int, int, bool, bytes, int, bool]]:
    if not 0 < api_id <= 0xFFFFFFFF:
        raise LoginBackupError("备份账户的 API ID 无效")
    if not is_valid_session_string(value):
        raise LoginBackupError("备份包含无效的账户会话")
    raw = base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))
    try:
        if len(raw) == struct.calcsize(">B?256sI?"):
            dc_id, test_mode, auth_key, user_id, is_bot = struct.unpack(">B?256sI?", raw)
            embedded_api_id = api_id
        elif len(raw) == struct.calcsize(">B?256sQ?"):
            dc_id, test_mode, auth_key, user_id, is_bot = struct.unpack(">B?256sQ?", raw)
            embedded_api_id = api_id
        else:
            dc_id, embedded_api_id, test_mode, auth_key, user_id, is_bot = struct.unpack(">BI?256sQ?", raw)
    except struct.error as exc:
        raise LoginBackupError("备份包含无效的账户会话") from exc
    if not 1 <= dc_id <= 255 or not any(auth_key) or user_id <= 0 or is_bot:
        raise LoginBackupError("备份包含未授权或非用户账户会话")
    if embedded_api_id not in (0, api_id):
        raise LoginBackupError("备份账户的 API ID 与会话不一致")
    fields = (dc_id, api_id, bool(test_mode), auth_key, user_id, False)
    normalized = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", *fields)).decode("ascii").rstrip("=")
    return normalized, fields


def export_login_backup(password: str, *, service: object) -> tuple[bytes, int]:
    secret = _password(password)
    session_dir = service.session_dir
    records: list[dict[str, object]] = []
    for account in service.list_accounts(force_refresh=True):
        name = _safe_name(account["name"])
        session = load_account_session_string(name, session_dir=session_dir, session_mode=get_session_mode())
        if not session:
            # Unauthenticated placeholder session files do not contain a login.
            continue
        try:
            api_id, api_hash = get_account_api_credentials(name)
            session, _ = _normalize_session(session, api_id)
        except (ValueError, TypeError) as exc:
            raise LoginBackupError(f"账户 {name} 的登录资料不完整，请先修复后重试") from exc
        records.append({"name": name, "api_id": api_id, "api_hash": api_hash, "session": session})
    if not records:
        raise LoginBackupError("没有可备份的已登录账户")
    document = json.dumps({"version": 1, "accounts": records}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(document) > MAX_BACKUP_BYTES - 128:
        raise LoginBackupError("账户登录资料超过备份大小限制")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    encrypted = AESGCM(_key(secret, salt)).encrypt(nonce, document, MAGIC)
    return MAGIC + salt + nonce + encrypted, len(records)


def _decode_backup(blob: bytes, password: str) -> list[dict[str, object]]:
    secret = _password(password)
    if not isinstance(blob, bytes) or not 52 <= len(blob) <= MAX_BACKUP_BYTES or not blob.startswith(MAGIC):
        raise LoginBackupError("备份文件格式或大小无效")
    salt, nonce, ciphertext = blob[8:24], blob[24:36], blob[36:]
    try:
        plaintext = AESGCM(_key(secret, salt)).decrypt(nonce, ciphertext, MAGIC)
        document = json.loads(plaintext)
    except Exception as exc:
        raise LoginBackupError("备份密码错误或文件已损坏") from exc
    if not isinstance(document, dict) or type(document.get("version")) is not int or document["version"] != 1 or not isinstance(document.get("accounts"), list):
        raise LoginBackupError("备份文件版本或内容无效")
    records = document["accounts"]
    if not records or len(records) > 10_000:
        raise LoginBackupError("备份文件账户数量无效")
    checked: list[dict[str, object]] = []
    names: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise LoginBackupError("备份文件账户内容无效")
        try:
            name = _safe_name(record["name"])
            api_id, api_hash = validate_telegram_api_credentials(record["api_id"], record["api_hash"])
            session, fields = _normalize_session(record["session"], api_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise LoginBackupError("备份文件账户内容无效") from exc
        if name.casefold() in names:
            raise LoginBackupError("备份文件存在重复账户名称")
        names.add(name.casefold())
        checked.append({"name": name, "api_id": api_id, "api_hash": api_hash, "session": session, "fields": fields})
    return checked


def _new_session_file(path: Path, fields: tuple[int, int, bool, bytes, int, bool]) -> None:
    from pyrogram.storage.sqlite_storage import SCHEMA, SQLiteStorage

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO version VALUES (?)", (SQLiteStorage.VERSION,))
        dc_id, api_id, test_mode, auth_key, user_id, is_bot = fields
        conn.execute(
            "INSERT INTO sessions (dc_id,api_id,test_mode,auth_key,date,user_id,is_bot) VALUES (?,?,?,?,?,?,?)",
            (dc_id, api_id, int(test_mode), auth_key, int(time.time()), user_id, int(is_bot)),
        )
        conn.commit()
    finally:
        conn.close()
    path.chmod(0o600)


def import_login_backup(blob: bytes, password: str, *, service: object) -> dict[str, object]:
    # Decode and validate every account before the first mutation.
    records = _decode_backup(blob, password)
    session_dir = service.session_dir
    session_dir.mkdir(parents=True, exist_ok=True)
    store = copy.deepcopy(_load_account_store())
    existing = {name.casefold() for name in store.get("accounts", {})}
    existing.update(path.stem.casefold() for path in session_dir.glob("*.session"))
    existing.update(path.stem.casefold() for path in session_dir.glob("*.session_string"))
    skipped = [record["name"] for record in records if record["name"].casefold() in existing]
    restore = [record for record in records if record["name"].casefold() not in existing]
    staged: list[tuple[Path, Path, str]] = []
    published: list[Path] = []
    try:
        for record in restore:
            suffix = ".session_string" if get_session_mode() == "string" else ".session"
            final = session_dir / f"{record['name']}{suffix}"
            fd, temp_name = tempfile.mkstemp(prefix=".login-restore-", dir=session_dir)
            os.close(fd)
            temporary = Path(temp_name)
            if suffix == ".session":
                _new_session_file(temporary, record["fields"])
            else:
                temporary.write_text(record["session"], encoding="utf-8")
                temporary.chmod(0o600)
            staged.append((temporary, final, record["name"]))
            token = _account_cipher().encrypt(json.dumps({"api_id": record["api_id"], "api_hash": record["api_hash"]}).encode("utf-8"))
            store.setdefault("accounts", {})[record["name"]] = {"api_credentials": token.decode("ascii")}
        for temporary, final, name in staged:
            if final.exists():
                raise LoginBackupError(f"账户 {name} 已存在，恢复已取消")
            os.link(temporary, final)  # atomic create; never replace an existing session
            published.append(final)
        if published:
            _save_account_store(store)
            service._accounts_cache = None
        return {"restored": len(restore), "skipped": len(skipped)}
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
