"""Reject non-public http(s) URLs before follow_email_link fetches them."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from utils.validation import ValidationError

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def ensure_public_http_url(url: str) -> None:
    """Raise ValidationError unless url is http(s) to a public internet host."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Only http(s) links from the captured email can be opened")
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS:
        raise ValidationError("Refusing to open a local or empty host")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise ValidationError("Refusing to open a private or reserved address")
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValidationError(f"Could not resolve host: {host}") from exc
    for info in resolved:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValidationError("Refusing to open a host that resolves to a private address")
