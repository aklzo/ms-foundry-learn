"""SSRF guard, ported from ``fetch/guard.rs``.

Validate scheme/host shape without touching the network; IP-literal hosts
are checked synchronously, named hosts additionally need
:func:`ensure_public_host` to catch DNS pointing at internal ranges.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from ..errors import BlockedUrlError


def validate_url(url: str) -> None:
    """Reject URLs whose scheme, credentials, or host violate the policy."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise _blocked(url, "only http/https schemes are allowed")
    if parts.username or parts.password:
        raise _blocked(url, "credentials in URL are not allowed")
    host = parts.hostname
    if not host:
        raise _blocked(url, "URL has no host")
    ip = _parse_ip(host)
    if ip is not None:
        _check_ip(url, ip)
    else:
        _check_domain(url, host)


async def ensure_public_host(url: str) -> None:
    """Resolve a named host and reject it if any address is non-public.
    Call after :func:`validate_url` and immediately before fetching."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if _parse_ip(host) is not None:
        return  # IP literals were already checked synchronously.
    port = parts.port or (443 if parts.scheme == "https" else 80)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise _blocked(url, f"DNS resolution failed: {exc}") from exc
    for info in infos:
        _check_ip(url, ipaddress.ip_address(info[4][0]))


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _check_domain(url: str, domain: str) -> None:
    lower = domain.lower().rstrip(".")
    is_internal_name = (
        lower == "localhost"
        or lower.endswith(".localhost")
        or lower.endswith(".local")
        or lower.endswith(".internal")
        or "." not in lower
    )
    if is_internal_name:
        raise _blocked(url, "internal hostname")


def _check_ip(url: str, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if not _is_public_ip(ip):
        raise _blocked(url, "address is not publicly routable")


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Unwrap IPv4-mapped IPv6 (::ffff:127.0.0.1) before classifying.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # ``is_global`` covers loopback, private, link-local, unspecified,
    # broadcast, documentation, CGN 100.64/10, 0.0.0.0/8, ULA fc00::/7 —
    # the same set the Rust version enumerated by hand.
    return ip.is_global


def _blocked(url: str, reason: str) -> BlockedUrlError:
    return BlockedUrlError(f"{url}: {reason}")
