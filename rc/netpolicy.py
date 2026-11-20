"""Outbound endpoint policy.

Remote model servers must use HTTPS. Plain HTTP is allowed only for a
loopback server (Ollama / LM Studio / local gateways), so an API key is never
sent in clear text over a LAN.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def _is_loopback(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_base_url(url: str) -> str:
    """Return a normalized base URL or raise ValueError with a user-facing reason."""
    text = (url or "").strip().rstrip("/")
    if not text:
        raise ValueError("服务地址不能为空")
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise ValueError("服务地址必须以 http:// 或 https:// 开头")
    host = parts.hostname or ""
    if not host:
        raise ValueError("服务地址缺少主机名")
    if parts.username or parts.password:
        raise ValueError("服务地址不能包含用户名或密码")
    if parts.scheme == "http" and not _is_loopback(host):
        raise ValueError("远程服务地址必须使用 HTTPS；http:// 只允许本机地址")
    return text
