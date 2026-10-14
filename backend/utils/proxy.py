from __future__ import annotations

from typing import Optional
from urllib.parse import unquote, urlparse

SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks4", "socks5"})


def normalize_proxy_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value
    if "://" in value:
        return value
    if "@" in value:
        return f"socks5://{value}"
    parts = value.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"socks5://{host}:{port}"
    if len(parts) == 4:
        host, port, user, password = parts
        return f"socks5://{user}:{password}@{host}:{port}"
    return f"socks5://{value}"


def build_proxy_dict(raw: str) -> Optional[dict]:
    value = normalize_proxy_url(raw)
    if not value:
        return None
    try:
        parsed = urlparse(value)
        port = parsed.port
    except (ValueError, AttributeError):
        return None
    scheme = (parsed.scheme or "").lower()
    if not (scheme in SUPPORTED_PROXY_SCHEMES and parsed.hostname and port):
        return None
    if not (1 <= port <= 65535):
        return None
    proxy = {
        "scheme": scheme,
        "hostname": parsed.hostname,
        "port": port,
    }
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


def require_proxy_dict(raw: Optional[str]) -> Optional[dict]:
    """Resolve an explicitly supplied route, rejecting malformed proxies."""
    if raw is None or not raw.strip():
        return None
    proxy = build_proxy_dict(raw)
    if proxy is None:
        raise ValueError("INVALID_ACCOUNT_PROXY")
    return proxy
