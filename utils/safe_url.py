"""Keep follow_email_link on the public internet.

Layers, from cheap to strict:

* ``ensure_public_http_url`` is a synchronous check on the URL text (scheme,
  loopback names, private IP literals). It never touches DNS, so it is safe
  to call on the event loop for every redirect hop.
* ``PublicOnlyTransport`` is an httpx transport whose network backend resolves
  each hostname once, rejects the connection unless every address is public,
  and then connects to that vetted address. Because the same lookup is used
  for the check and the connection, a DNS answer cannot change between the
  two (DNS rebinding), and the check cannot be skipped by forgetting to call
  it: every connection the client makes goes through it.
* ``ensure_public_resolution`` is the best-effort variant used when an
  HTTP(S)_PROXY makes the connection and pinning is impossible.

``HostAllowList`` (``FOLLOW_EMAIL_LINK_ALLOW_HOSTS``) lets the *operator*, never
the model, opt specific local or internal hosts back in.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import ssl
import time
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import urlparse

import anyio
import httpcore
import httpx

from utils.validation import ValidationError

ALLOW_HOSTS_ENV = "FOLLOW_EMAIL_LINK_ALLOW_HOSTS"
_ALLOW_HINT = f" (set {ALLOW_HOSTS_ENV} on the server to allow local or internal hosts on purpose)"

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
# Ranges that ipaddress.is_global does not reject (or did not on every CPython
# patch level this package supports) but that must never be reached.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, cloud metadata
    ipaddress.ip_network("168.63.129.16/32"),  # Azure WireServer
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved + broadcast
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
_HOSTNAME = re.compile(r"[a-z0-9._-]+")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
Resolver = Callable[[str, int], Awaitable[list[str]]]

_ssl_context: ssl.SSLContext | None = None


def _parse_ip(value: str) -> IPAddress | None:
    """Return the IP literal in ``value`` (brackets / zone id stripped), or None."""
    candidate = value.strip("[]").split("%", 1)[0]
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Return the IPv4 address an IPv6 transition address maps to, if any."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address.teredo is not None:
        return address.teredo[1]
    if address in _NAT64 or address in _NAT64_LOCAL or address in _IPV4_COMPATIBLE:
        return ipaddress.IPv4Address(address.packed[-4:])
    return None


def is_public_address(address: IPAddress) -> bool:
    """True only for addresses that are routable on the public internet."""
    if isinstance(address, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            return is_public_address(embedded)
    if any(address in network for network in _BLOCKED_NETWORKS):
        return False
    return bool(address.is_global) and not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


class HostAllowList:
    """Operator-configured hosts that may be opened although they are not public.

    Entries (comma or whitespace separated in ``FOLLOW_EMAIL_LINK_ALLOW_HOSTS``):
    a hostname (``localhost``), a wildcard suffix (``*.corp.example``), an IP
    (``127.0.0.1``) or a network (``10.0.0.0/8``). An allowed hostname is still
    resolved once and pinned; it just skips the public-address requirement.
    """

    def __init__(self, entries: Iterable[str] = ()) -> None:
        self.hosts: set[str] = set()
        self.suffixes: list[str] = []
        self.networks: list[IPNetwork] = []
        for entry in entries:
            self.add(entry)

    @classmethod
    def from_env(cls, value: str | None) -> HostAllowList:
        return cls(token for token in re.split(r"[\s,]+", value or "") if token)

    def add(self, raw: str) -> None:
        entry = raw.strip().lower().rstrip(".")
        if not entry:
            return
        if "/" in entry:
            try:
                self.networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError as exc:
                raise ValueError(f"{ALLOW_HOSTS_ENV}: {raw!r} is not a valid network") from exc
            return
        literal = _parse_ip(entry)
        if literal is not None:
            self.networks.append(ipaddress.ip_network(literal))
        elif entry.startswith("*.") and _HOSTNAME.fullmatch(entry[2:]):
            self.suffixes.append(entry[1:])
        elif _HOSTNAME.fullmatch(entry):
            self.hosts.add(entry)
        else:
            raise ValueError(
                f"{ALLOW_HOSTS_ENV}: {raw!r} is not a hostname, *.suffix, IP address or network"
            )

    def allows_host(self, host: str) -> bool:
        name = host.lower().rstrip(".")
        return name in self.hosts or any(name.endswith(suffix) for suffix in self.suffixes)

    def allows_address(self, address: IPAddress) -> bool:
        return any(address in network for network in self.networks)

    def __bool__(self) -> bool:
        return bool(self.hosts or self.suffixes or self.networks)


_NO_ALLOW = HostAllowList()


def _address_ok(address: IPAddress, allowlist: HostAllowList) -> bool:
    return allowlist.allows_address(address) or is_public_address(address)


def ensure_public_http_url(url: str, allowlist: HostAllowList | None = None) -> None:
    """Raise ValidationError unless url is http(s) and not an obviously local host.

    This is a syntactic pre-flight only. Hostnames are vetted at connect time
    by ``PublicOnlyBackend`` so the check and the connection share one lookup.
    """
    allow = allowlist or _NO_ALLOW
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Only http(s) links from the captured email can be opened")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValidationError("Refusing to open a link without a host")
    literal = _parse_ip(host)
    if literal is not None:
        if not _address_ok(literal, allow):
            raise ValidationError("Refusing to open a private or reserved address" + _ALLOW_HINT)
        return
    if allow.allows_host(host):
        return
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ValidationError("Refusing to open a local host" + _ALLOW_HINT)
    if any(char.isspace() or not char.isprintable() for char in host) or "%" in host:
        raise ValidationError("Refusing to open a malformed host")


async def resolve_addresses(host: str, port: int) -> list[str]:
    """Resolve ``host`` without blocking the event loop and return its addresses."""
    try:
        infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise ValidationError(f"Could not resolve host: {host}") from exc
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _vet_addresses(host: str, addresses: list[str], allowlist: HostAllowList) -> list[str]:
    if not addresses:
        raise ValidationError(f"Could not resolve host: {host}")
    if allowlist.allows_host(host):
        return addresses
    for address in addresses:
        parsed = _parse_ip(address)
        if parsed is None or not _address_ok(parsed, allowlist):
            raise ValidationError(
                "Refusing to open a host that resolves to a private address" + _ALLOW_HINT
            )
    return addresses


async def ensure_public_resolution(
    url: str,
    allowlist: HostAllowList | None = None,
    timeout: float | None = None,
) -> None:
    """Best-effort check for connections a proxy will make on our behalf.

    The proxy resolves the name itself, so this cannot pin the address; it
    only refuses names that resolve to private addresses at check time.
    """
    allow = allowlist or _NO_ALLOW
    ensure_public_http_url(url, allow)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if _parse_ip(host) is not None or allow.allows_host(host):
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with anyio.fail_after(timeout):
            addresses = await resolve_addresses(host, port)
    except TimeoutError as exc:
        raise ValidationError(f"Timed out resolving host: {host}") from exc
    _vet_addresses(host, addresses, allow)


def _env(name: str) -> str:
    return os.environ.get(name.upper()) or os.environ.get(name.lower()) or ""


def proxy_for_url(url: str) -> str | None:
    """Return the HTTP(S)_PROXY / ALL_PROXY that applies to ``url``, honouring NO_PROXY."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for entry in re.split(r"[\s,]+", _env("NO_PROXY").strip()):
        if not entry:
            continue
        if entry == "*":
            return None
        pattern = entry.lower()
        if pattern.count(":") == 1:
            pattern = pattern.split(":", 1)[0]
        pattern = pattern.lstrip(".")
        if host == pattern or host.endswith("." + pattern):
            return None
    return _env(f"{parsed.scheme}_PROXY") or _env("ALL_PROXY") or None


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """httpcore network backend that only connects to vetted public addresses.

    DNS resolution and every connection attempt share the single ``timeout``
    httpcore passes in, so a slow resolver or a multi-homed host that drops
    packets cannot stretch one hop past the configured connect timeout.
    """

    def __init__(
        self,
        inner: httpcore.AsyncNetworkBackend,
        resolver: Resolver | None = None,
        allowlist: HostAllowList | None = None,
    ) -> None:
        self._inner = inner
        self._resolve = resolver or resolve_addresses
        self._allow = allowlist or _NO_ALLOW

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        deadline = None if timeout is None else time.monotonic() + timeout

        def remaining() -> float | None:
            if deadline is None:
                return None
            return max(0.0, deadline - time.monotonic())

        literal = _parse_ip(host)
        if literal is not None:
            if not _address_ok(literal, self._allow):
                raise ValidationError("Refusing to open a private or reserved address" + _ALLOW_HINT)
            addresses = [str(literal)]
        else:
            try:
                with anyio.fail_after(remaining()):
                    resolved = await self._resolve(host, port)
            except TimeoutError as exc:
                raise httpcore.ConnectTimeout(f"Timed out resolving {host}") from exc
            addresses = _vet_addresses(host, resolved, self._allow)

        last_error: Exception | None = None
        for address in addresses:
            budget = remaining()
            if budget is not None and budget <= 0:
                raise httpcore.ConnectTimeout(f"Timed out connecting to {host}")
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=budget,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise ValidationError("Refusing to open a unix socket from an email link")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def default_ssl_context() -> ssl.SSLContext:
    """Build the SSL context once (it costs ~250 ms).

    ``httpx.create_ssl_context`` honours SSL_CERT_FILE / SSL_CERT_DIR, so a
    corporate CA bundle works without code changes.
    """
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = httpx.create_ssl_context()
    return _ssl_context


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    """httpx transport that pins every connection to a vetted public address.

    It cannot go through a proxy: the proxy would resolve the hostname itself,
    outside the vetting. Proxied hops use a plain transport after
    ``ensure_public_resolution`` instead. Fails closed: if the installed
    httpx / httpcore no longer expose the connection pool's network backend
    (private attributes, guarded by a wiring test), the transport refuses to
    be built rather than silently connecting unpinned.
    """

    def __init__(
        self,
        resolver: Resolver | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        allowlist: HostAllowList | None = None,
        **kwargs: Any,
    ) -> None:
        if kwargs.get("proxy") is not None:
            raise ValueError("PublicOnlyTransport cannot pin connections through a proxy")
        kwargs.setdefault("trust_env", False)
        kwargs.setdefault("verify", default_ssl_context())
        super().__init__(**kwargs)
        pool = getattr(self, "_pool", None)
        inner = network_backend or getattr(pool, "_network_backend", None)
        if pool is None or not isinstance(inner, httpcore.AsyncNetworkBackend):
            raise RuntimeError(
                "Cannot pin connections with this httpx/httpcore version; refusing to open email links"
            )
        self._public_backend = PublicOnlyBackend(inner, resolver=resolver, allowlist=allowlist)
        pool._network_backend = self._public_backend

    @property
    def network_backend(self) -> PublicOnlyBackend:
        return self._public_backend
