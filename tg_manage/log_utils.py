"""
日志脱敏与结构化工具
提供统一的日志安全处理函数，防止敏感数据泄露到日志中
"""

from __future__ import annotations

import re
from typing import Any

# 敏感字段模式：匹配 API key、session string、token 等
_SECRET_PATTERNS = [
    # OpenAI / 通用 sk-* API key
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    # Telegram session string（长 base64-like 字符串，通常 >100 字符）
    re.compile(r"[A-Za-z0-9+/=_-]{80,}={0,2}"),
    # Telegram bot token（数字:字母数字串，兼容较短的测试 token）
    re.compile(r"\d{8,12}:[A-Za-z0-9_-]{10,}"),
    # Telegram api_hash（32 位十六进制）
    re.compile(r"[0-9a-fA-F]{32}(?=[^0-9a-fA-F]|$)"),
    # data:image base64 图片
    re.compile(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]{50,}"),
    # 裸 base64 长片段（>=128 字符，可能含 = padding）
    re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{128,}={0,2}(?![A-Za-z0-9+/=])"),
    # 带凭据的 URL（http/https/socks4/socks5）
    re.compile(r"(?:https?|socks[45])://[^:]+:[^@]+@[^\s]+"),
    # Authorization header（支持带引号：'Authorization': 'Bearer xxx'）
    re.compile(r"""(?:['"]?(?:authorization|x-api-key)['"]?\s*[:=]\s*)(?:\S+\s+)?\S+""", re.IGNORECASE),
    # api_key=xxx 或 'api_key': xxx 字段值（支持带引号）
    re.compile(r"""(?:['"]?(?:api_key|api_secret|access_token|refresh_token)['"]?\s*[:=]\s*)['"]?\S+['"]?""", re.IGNORECASE),
]


def safe_text_preview(text: Any, max_chars: int = 120) -> str:
    """
    安全的文本预览：去控制字符、折叠空白、截断、过滤敏感信息
    用于日志中安全展示用户消息、AI prompt/response 等
    """
    if text is None:
        return ""
    s = str(text)
    # 去除控制字符（保留换行和空格）
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    # 折叠空白
    s = re.sub(r"\s+", " ", s).strip()
    # 过滤敏感模式
    for pattern in _SECRET_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    # 截断
    if len(s) > max_chars:
        s = s[: max_chars - 3] + "..."
    return s


def safe_traceback_preview(tb: str, max_lines: int = 6, max_line_chars: int = 200) -> str:
    """
    安全的 traceback 预览：脱敏每行内容，限制行数
    用于写入任务日志流（会持久化、API 展示、通知外发）
    """
    if not tb or tb == "NoneType: None\n":
        return ""
    lines = tb.strip().splitlines()
    # 只保留最后 N 行（最有排障价值的部分）
    tail = lines[-max_lines:]
    safe_lines = []
    for line in tail:
        # 保留行首缩进（traceback 可读性），仅对内容部分脱敏
        leading_spaces = len(line) - len(line.lstrip())
        indent = line[:leading_spaces]
        content = line[leading_spaces:]
        # 复用 safe_text_preview 避免重复逻辑
        safe_content = safe_text_preview(content, max_line_chars)
        safe_lines.append(f"{indent}{safe_content}")
    return "\n".join(safe_lines)
