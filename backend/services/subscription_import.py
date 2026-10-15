"""Bounded, credential-safe import of airport subscription documents.

Only audited Xray outbound shapes are produced here. A subscription never gets
to provide an arbitrary Xray config or local listener.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import yaml
from yaml.tokens import AliasToken, AnchorToken

MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_NODES = 128
MAX_REDIRECTS = 3
ALLOWED_SS_METHODS = frozenset({
    "aes-128-gcm", "aes-256-gcm", "chacha20-poly1305",
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
})


class SubscriptionError(ValueError):
    """Safe public error. Never include a subscription URL or node credential."""


@dataclass(frozen=True)
class ImportedNode:
    node_id: str
    label: str
    source: str
    outbound: dict[str, Any]


@dataclass(frozen=True)
class ImportResult:
    nodes: tuple[ImportedNode, ...]
    unsupported_count: int


def _safe_b64(value: str) -> bytes:
    compact = re.sub(r"\s+", "", value).replace("-", "+").replace("_", "/")
    if len(compact) > MAX_DOCUMENT_BYTES * 2 or not re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        raise SubscriptionError("SUBSCRIPTION_FORMAT_INVALID")
    try:
        return base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
    except (ValueError, base64.binascii.Error):
        raise SubscriptionError("SUBSCRIPTION_FORMAT_INVALID") from None


def _host(value: Any) -> str:
    host = str(value or "").strip()
    if not host or len(host) > 253 or any(c in host for c in "/@\\\r\n\x00"):
        raise SubscriptionError("NODE_INVALID")
    return host


def _port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise SubscriptionError("NODE_INVALID") from None
    if not 1 <= port <= 65535:
        raise SubscriptionError("NODE_INVALID")
    return port


def _nonempty(value: Any) -> str:
    result = str(value or "")
    if not result or len(result) > 1024:
        raise SubscriptionError("NODE_INVALID")
    return result


def _stream(network: str, security: str, fields: dict[str, Any]) -> dict[str, Any]:
    if network not in ("tcp", "ws", "grpc") or security not in ("none", "tls", "reality"):
        raise SubscriptionError("NODE_UNSUPPORTED")
    settings: dict[str, Any] = {"network": network}
    if network == "ws":
        path = str(fields.get("path") or "/")
        if not path.startswith("/") or len(path) > 1024:
            raise SubscriptionError("NODE_INVALID")
        settings["wsSettings"] = {"path": path, "headers": {"Host": str(fields.get("host") or "")}}
    elif network == "grpc":
        service = str(fields.get("serviceName") or "")
        if len(service) > 255:
            raise SubscriptionError("NODE_INVALID")
        settings["grpcSettings"] = {"serviceName": service}
    if security == "tls":
        settings["security"] = "tls"
        settings["tlsSettings"] = {
            "serverName": str(fields.get("serverName") or ""),
            "allowInsecure": False,
        }
        if fields.get("alpn"):
            settings["tlsSettings"]["alpn"] = [str(item) for item in fields["alpn"]][:5]
    elif security == "reality":
        if network not in ("tcp", "grpc"):
            raise SubscriptionError("NODE_UNSUPPORTED")
        settings["security"] = "reality"
        settings["realitySettings"] = {
            "serverName": _nonempty(fields.get("serverName")),
            "fingerprint": str(fields.get("fingerprint") or "chrome"),
            "publicKey": _nonempty(fields.get("publicKey")),
            "shortId": str(fields.get("shortId") or ""),
        }
    return settings


def _node(outbound: dict[str, Any], source: str, ordinal: int) -> ImportedNode:
    canonical = json.dumps(outbound, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
    prefix = "主订阅" if source == "primary" else "兜底订阅"
    return ImportedNode(digest, f"{prefix}节点 {ordinal}", source, outbound)


def _from_uri(line: str, source: str, ordinal: int) -> ImportedNode:
    parsed = urlsplit(line.strip())
    protocol = parsed.scheme.lower()
    if protocol not in ("vless", "vmess", "trojan", "ss"):
        raise SubscriptionError("NODE_UNSUPPORTED")
    if protocol == "vmess":
        payload = json.loads(_safe_b64(parsed.netloc + parsed.path))
        if not isinstance(payload, dict):
            raise SubscriptionError("NODE_INVALID")
        address, port = _host(payload.get("add")), _port(payload.get("port"))
        user = {"id": _nonempty(payload.get("id")), "alterId": int(payload.get("aid") or 0), "security": str(payload.get("scy") or "auto")}
        if user["alterId"] != 0:
            raise SubscriptionError("NODE_UNSUPPORTED")
        network = str(payload.get("net") or "tcp").lower()
        security = "tls" if str(payload.get("tls") or "").lower() in ("tls", "1", "true") else "none"
        fields = {"path": payload.get("path"), "host": payload.get("host"), "serverName": payload.get("sni") or payload.get("host") or address}
        outbound = {"protocol": "vmess", "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]}, "streamSettings": _stream(network, security, fields)}
    elif protocol == "ss":
        authority = parsed.netloc
        if "@" not in authority:
            authority = _safe_b64(authority + parsed.path).decode("utf-8")
        auth, separator, endpoint = authority.rpartition("@")
        if not separator:
            raise SubscriptionError("NODE_INVALID")
        if ":" not in auth:
            auth = _safe_b64(auth).decode("utf-8")
        method, separator, password = auth.partition(":")
        if not separator or method not in ALLOWED_SS_METHODS:
            raise SubscriptionError("NODE_UNSUPPORTED")
        target = urlsplit(f"ss://{endpoint}")
        outbound = {"protocol": "shadowsocks", "settings": {"servers": [{"address": _host(target.hostname), "port": _port(target.port), "method": method, "password": _nonempty(unquote(password))}]}}
    else:
        address, port = _host(parsed.hostname), _port(parsed.port)
        q = parse_qs(parsed.query, keep_blank_values=True)

        def first(key: str, default: str = "") -> str:
            return q.get(key, [default])[0]
        network = first("type", "tcp").lower()
        security = first("security", "tls" if protocol == "trojan" else "none").lower()
        fields = {"path": first("path", "/"), "host": first("host"), "serviceName": first("serviceName"), "serverName": first("sni", address), "publicKey": first("pbk"), "shortId": first("sid"), "fingerprint": first("fp", "chrome")}
        if protocol == "vless":
            if first("encryption", "none") != "none":
                raise SubscriptionError("NODE_UNSUPPORTED")
            user = {"id": _nonempty(unquote(parsed.username)), "encryption": "none"}
            if first("flow"):
                user["flow"] = first("flow")
            outbound = {"protocol": "vless", "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]}, "streamSettings": _stream(network, security, fields)}
        else:
            outbound = {"protocol": "trojan", "settings": {"servers": [{"address": address, "port": port, "password": _nonempty(unquote(parsed.username))}]}, "streamSettings": _stream(network, security, fields)}
    return _node(outbound, source, ordinal)


def _from_clash(item: dict[str, Any], source: str, ordinal: int) -> ImportedNode:
    kind = str(item.get("type") or "").lower()
    address, port = _host(item.get("server")), _port(item.get("port"))
    network = str(item.get("network") or "tcp").lower()
    tls = bool(item.get("tls"))
    reality = item.get("reality-opts") or {}
    security = "reality" if reality else "tls" if tls else "none"
    ws = item.get("ws-opts") or {}
    grpc = item.get("grpc-opts") or {}
    if not isinstance(ws, dict) or not isinstance(grpc, dict) or not isinstance(reality, dict):
        raise SubscriptionError("NODE_INVALID")
    fields = {"path": ws.get("path"), "host": (ws.get("headers") or {}).get("Host") if isinstance(ws.get("headers") or {}, dict) else "", "serviceName": grpc.get("grpc-service-name"), "serverName": item.get("servername") or item.get("sni") or address, "publicKey": reality.get("public-key"), "shortId": reality.get("short-id"), "fingerprint": item.get("client-fingerprint") or "chrome"}
    if kind in ("vless", "vmess"):
        user = {"id": _nonempty(item.get("uuid"))}
        if kind == "vless":
            user["encryption"] = "none"
            if item.get("flow"):
                user["flow"] = str(item["flow"])
        else:
            if int(item.get("alterId") or 0):
                raise SubscriptionError("NODE_UNSUPPORTED")
            user.update({"alterId": 0, "security": str(item.get("cipher") or "auto")})
        outbound = {"protocol": kind, "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]}, "streamSettings": _stream(network, security, fields)}
    elif kind == "trojan":
        outbound = {"protocol": "trojan", "settings": {"servers": [{"address": address, "port": port, "password": _nonempty(item.get("password"))}]}, "streamSettings": _stream(network, security, fields)}
    elif kind == "ss":
        method = str(item.get("cipher") or "")
        if method not in ALLOWED_SS_METHODS:
            raise SubscriptionError("NODE_UNSUPPORTED")
        if network != "tcp" or security != "none":
            raise SubscriptionError("NODE_UNSUPPORTED")
        outbound = {"protocol": "shadowsocks", "settings": {"servers": [{"address": address, "port": port, "method": method, "password": _nonempty(item.get("password"))}]}}
    else:
        raise SubscriptionError("NODE_UNSUPPORTED")
    return _node(outbound, source, ordinal)


def parse_subscription(document: bytes, source: str) -> ImportResult:
    if len(document) > MAX_DOCUMENT_BYTES:
        raise SubscriptionError("SUBSCRIPTION_TOO_LARGE")
    try:
        value = document.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise SubscriptionError("SUBSCRIPTION_FORMAT_INVALID") from None
    if not value:
        raise SubscriptionError("SUBSCRIPTION_EMPTY")
    items: list[Any]
    clash = False
    if value.startswith(("proxies:", "---", "{", "#")):
        try:
            if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(value)):
                raise SubscriptionError("SUBSCRIPTION_FORMAT_INVALID")
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("proxies"), list):
            items = parsed["proxies"]
            clash = True
        else:
            items = []
    else:
        if "://" not in value:
            try:
                value = _safe_b64(value).decode("utf-8")
            except (UnicodeDecodeError, SubscriptionError):
                raise SubscriptionError("SUBSCRIPTION_FORMAT_INVALID") from None
        items = [part.strip() for part in value.splitlines() if part.strip() and not part.startswith("#")]
    if len(items) > MAX_NODES:
        raise SubscriptionError("SUBSCRIPTION_TOO_MANY_NODES")
    nodes: list[ImportedNode] = []
    seen: set[str] = set()
    unsupported = 0
    for ordinal, item in enumerate(items, 1):
        try:
            node = _from_clash(item, source, ordinal) if clash and isinstance(item, dict) else _from_uri(item, source, ordinal) if isinstance(item, str) else None
        except (SubscriptionError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            node = None
        if node is None:
            unsupported += 1
        elif node.node_id not in seen:
            seen.add(node.node_id)
            nodes.append(node)
    return ImportResult(tuple(nodes), unsupported)


async def _validate_public_url(url: str) -> list[tuple[int, str]]:
    try:
        parsed = urlsplit(url)
        hostname, port = parsed.hostname, parsed.port
    except ValueError:
        raise SubscriptionError("SUBSCRIPTION_URL_INVALID") from None
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password or port not in (None, 443):
        raise SubscriptionError("SUBSCRIPTION_URL_INVALID")
    if len(url) > 4096 or any(ord(char) < 32 for char in url):
        raise SubscriptionError("SUBSCRIPTION_URL_INVALID")
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(hostname, 443, type=socket.SOCK_STREAM),
            timeout=5,
        )
    except (OSError, asyncio.TimeoutError):
        raise SubscriptionError("SUBSCRIPTION_DNS_FAILED") from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise SubscriptionError("SUBSCRIPTION_URL_FORBIDDEN")
    return list(dict.fromkeys((item[0], item[4][0]) for item in addresses))


async def _request_https(url: str, addresses: list[tuple[int, str]]) -> tuple[int, dict[str, str], bytes]:
    """Connect to the already validated address; TLS still verifies the URL host."""
    parsed = urlsplit(url)
    assert parsed.hostname is not None
    last_error: OSError | None = None
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    for family, address in addresses:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(address, 443, family=family, ssl=ssl.create_default_context(), server_hostname=parsed.hostname, limit=16384),
                timeout=5,
            )
            break
        except (OSError, asyncio.TimeoutError) as exc:
            last_error = OSError(type(exc).__name__)
    if reader is None or writer is None:
        raise last_error or OSError("connect failed")
    try:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        request = f"GET {target} HTTP/1.1\r\nHost: {parsed.hostname}\r\nAccept: text/plain, application/yaml, */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
        writer.write(request.encode("ascii"))
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=12)
        lines = head.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/1."):
            raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED")
        status = int(parts[1])
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line:
                continue
            key, sep, value = line.partition(":")
            if not sep:
                raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED")
            headers[key.lower().strip()] = value.strip()
        if status in (301, 302, 303, 307, 308):
            return status, headers, b""
        if status != 200 or headers.get("content-encoding", "identity").lower() != "identity":
            raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED")
        body = bytearray()
        if "chunked" in headers.get("transfer-encoding", "").lower():
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=12)
                if len(line) > 1024:
                    raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED")
                size = int(line.split(b";", 1)[0], 16)
                if size == 0:
                    break
                if size < 0 or len(body) + size > MAX_DOCUMENT_BYTES:
                    raise SubscriptionError("SUBSCRIPTION_TOO_LARGE")
                body.extend(await asyncio.wait_for(reader.readexactly(size), timeout=12))
                if await reader.readexactly(2) != b"\r\n":
                    raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED")
        elif "content-length" in headers:
            size = int(headers["content-length"])
            if size < 0 or size > MAX_DOCUMENT_BYTES:
                raise SubscriptionError("SUBSCRIPTION_TOO_LARGE")
            body.extend(await asyncio.wait_for(reader.readexactly(size), timeout=12))
        else:
            while True:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=12)
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_DOCUMENT_BYTES:
                    raise SubscriptionError("SUBSCRIPTION_TOO_LARGE")
        return status, headers, bytes(body)
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1)
        except (OSError, asyncio.TimeoutError):
            pass


async def fetch_subscription(url: str) -> bytes:
    """HTTPS fetch with redirect and size limits; errors expose fixed codes only."""
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            addresses = await _validate_public_url(current)
            status, headers, body = await asyncio.wait_for(_request_https(current, addresses), timeout=20)
            if status in (301, 302, 303, 307, 308):
                target = headers.get("location")
                if not target:
                    raise SubscriptionError("SUBSCRIPTION_REDIRECT_INVALID")
                current = urljoin(current, target)
                continue
            return body
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, UnicodeError, ValueError) as exc:
        if isinstance(exc, SubscriptionError):
            raise
        raise SubscriptionError("SUBSCRIPTION_FETCH_FAILED") from None
    raise SubscriptionError("SUBSCRIPTION_REDIRECT_LIMIT")
