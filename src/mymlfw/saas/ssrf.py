"""SSRF guard: block private/link-local/metadata at TCP connect time."""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable


class SsrfError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or str(ip) == "169.254.169.254"
    )


def assert_public_host(host: str, *, resolve: Callable[[str], list[str]] | None = None) -> list[str]:
    """Resolve then reject any private/link-local address (connect-time check)."""
    name = (host or "").strip().lower()
    if not name or name in {"localhost", "metadata", "metadata.google.internal"}:
        raise SsrfError("ssrf_blocked", f"host rejected: {host}")
    resolver = resolve or (lambda h: [ai[4][0] for ai in socket.getaddrinfo(h, None)])
    try:
        addrs = resolver(name)
    except OSError as exc:
        raise SsrfError("ssrf_resolve_failed", str(exc)) from exc
    if not addrs:
        raise SsrfError("ssrf_blocked", "no addresses")
    for raw in addrs:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise SsrfError("ssrf_blocked", f"bad address {raw}") from exc
        if _blocked(ip):
            raise SsrfError("ssrf_blocked", f"private or link-local address {ip}")
    return list(addrs)


def guarded_connect(host: str, port: int, *, timeout: float = 3.0) -> socket.socket:
    """TCP connect only after every resolved address passes the private-IP block."""
    assert_public_host(host)
    sock = socket.create_connection((host, port), timeout=timeout)
    peer = sock.getpeername()[0]
    ip = ipaddress.ip_address(peer)
    if _blocked(ip):
        sock.close()
        raise SsrfError("ssrf_blocked", f"connected peer blocked {ip}")
    return sock
