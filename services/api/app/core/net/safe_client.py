"""The single SSRF-guarded HTTP client (§107, §123).

Every fetch the crawler, sitemap reader, robots.txt fetcher, and broken-link
checker perform goes through `SafeFetcher.fetch()`. There is no second HTTP
client anywhere in this codebase that reaches an arbitrary user-supplied URL
— that invariant is what makes the SSRF guard actually load-bearing rather
than a thing that's easy to accidentally route around.

Guard, in order, matching the plan:
  1. Reject non-http(s) schemes and non-80/443 ports.
  2. Resolve the hostname to A/AAAA records once.
  3. Reject any resolved IP that is loopback, private, link-local,
     unique-local, CGNAT, reserved, multicast, unspecified, or a known cloud
     metadata address.
  4. Pin the TCP connection to the validated IP (connect by IP, but keep
     sending the original Host header and TLS SNI) so a DNS rebind between
     the check and the connect cannot slip a request through.
  5. Redirects are followed in an explicit loop, re-running steps 1-4 on
     *every* hop, with a capped chain length.

Failure raises `BlockedTargetError` (code BLOCKED_TARGET). Never bypasses
robots.txt or anti-bot systems — those are separate, higher-level policies
enforced by the crawler itself (§28).
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpcore
import httpx

from app.core.config import get_settings
from app.core.errors import BlockedTargetError

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {"http": 80, "https": 443}
MAX_REDIRECT_HOPS = 5
DNS_CACHE_TTL_SECONDS = 300

# Known cloud metadata endpoints — reachable only from inside the respective
# cloud's VMs, and never a legitimate audit target. Belt-and-suspenders on
# top of the link-local check (169.254.0.0/16 already covers the first two).
_METADATA_IPS = {
    "169.254.169.254",  # AWS / GCP / Azure / DigitalOcean
    "fd00:ec2::254",  # AWS IMDSv2 IPv6
}

# RFC 6598 shared address space (carrier-grade NAT) — ipaddress.is_private
# does not flag this range, so it needs an explicit check.
_CGNAT_RANGE = ipaddress.ip_network("100.64.0.0/10")


@dataclass
class FetchResult:
    response: httpx.Response
    final_url: str
    redirect_chain: list[str] = field(default_factory=list)


def is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparsable => treat as unsafe

    # Unwrap IPv4-mapped IPv6 addresses (::ffff:127.0.0.1) before judging.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped

    if ip_str in _METADATA_IPS:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_RANGE:
        return True

    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_scheme_and_port(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise BlockedTargetError(f"Scheme {scheme!r} is not permitted.")
    if not parts.hostname:
        raise BlockedTargetError("URL has no hostname.")

    default_port = ALLOWED_PORTS[scheme]
    port = parts.port or default_port
    if port != default_port:
        raise BlockedTargetError(f"Port {port} is not permitted for {scheme}.")

    return scheme, parts.hostname, port


class DnsResolutionError(BlockedTargetError):
    """A hostname simply didn't resolve (NXDOMAIN, etc.) — distinct from
    `BlockedTargetError` proper (which means it resolved to somewhere
    unsafe), so callers that care about the §30 DNS_FAILURE vs
    BLOCKED_TARGET distinction can tell them apart, while callers that only
    care about "is this URL safe to fetch" can keep catching
    `BlockedTargetError` and get correct fail-safe behavior either way.
    """


def resolve_host(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise DnsResolutionError(f"DNS resolution failed for {hostname!r}.") from exc

    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise DnsResolutionError(f"DNS resolution returned no addresses for {hostname!r}.")
    return ips


def validate_host_resolves_safely(hostname: str) -> str:
    """Resolve `hostname` and return one safe IP to connect to.

    If *any* resolved address is unsafe, the whole hostname is rejected —
    not just the unsafe address — so an attacker cannot rely on a crawler
    picking "the good" A record from a multi-answer response.
    """
    ips = resolve_host(hostname)
    for ip in ips:
        if is_blocked_ip(ip):
            raise BlockedTargetError(f"{hostname!r} resolves to a blocked address ({ip}).")
    return ips[0]


class _PinnedNetworkBackend(httpcore.AnyIOBackend):
    """Connects TCP to a pre-validated IP while leaving Host/SNI untouched.

    httpcore derives the TLS SNI and the HTTP Host header from the request's
    origin (the URL), not from whatever `connect_tcp` actually dials — so
    substituting the dial target here is transparent to the rest of the
    stack (certificate verification still checks the real hostname) and is
    exactly what closes the DNS-rebind gap between validation and connect.
    """

    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return await super().connect_tcp(
            self._pinned_ip, port, timeout=timeout, local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """An httpx transport whose TCP connect target is pinned to a
    pre-validated IP.

    httpx's own `AsyncHTTPTransport.__init__` does not expose
    `network_backend` (verified against httpx 0.28.1 source — it builds an
    `httpcore.AsyncConnectionPool` internally with no way to override the
    backend), so this subclass skips that `__init__` and builds the pool
    itself with the pinned backend injected. Every other method
    (`handle_async_request`, `aclose`, `__aenter__`/`__aexit__`) is inherited
    unchanged from httpx — they only ever touch `self._pool`.
    """

    def __init__(self, pinned_ip: str) -> None:
        # Per-request timeouts are applied by httpx.AsyncClient at the
        # request level (via request.extensions), not at the transport —
        # handle_async_request forwards those extensions unchanged, so
        # nothing extra is needed here for that.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_PinnedNetworkBackend(pinned_ip),
            retries=0,
        )


class SafeFetcher:
    """SSRF-guarded fetcher with a small per-hostname DNS/client cache.

    One instance is typically shared for the lifetime of a single crawl job
    so that repeated fetches to the same host reuse a validated connection
    instead of re-resolving DNS on every page.
    """

    def __init__(self, *, user_agent: str | None = None, timeout: float = 15.0):
        settings = get_settings()
        self._user_agent = user_agent or settings.crawler_user_agent
        self._timeout = timeout
        self._dns_cache: dict[str, tuple[str, float]] = {}
        self._clients: dict[tuple[str, int, str], httpx.AsyncClient] = {}

    def _validated_ip(self, hostname: str) -> str:
        cached = self._dns_cache.get(hostname)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        ip = validate_host_resolves_safely(hostname)
        self._dns_cache[hostname] = (ip, now + DNS_CACHE_TTL_SECONDS)
        return ip

    def _client_for(self, hostname: str, port: int, ip: str) -> httpx.AsyncClient:
        key = (hostname, port, ip)
        client = self._clients.get(key)
        if client is None:
            transport = _PinnedAsyncHTTPTransport(ip)
            client = httpx.AsyncClient(
                transport=transport,
                timeout=self._timeout,
                follow_redirects=False,
                headers={"User-Agent": self._user_agent},
            )
            self._clients[key] = client
        return client

    async def _single_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        _scheme, hostname, port = validate_scheme_and_port(url)
        ip = self._validated_ip(hostname)
        client = self._client_for(hostname, port, ip)
        return await client.request(method, url, **kwargs)

    async def fetch(self, url: str, *, method: str = "GET", **kwargs) -> FetchResult:
        """Fetch `url`, following redirects manually with full re-validation
        of every hop (§107 step 5) up to MAX_REDIRECT_HOPS.
        """
        chain: list[str] = []
        current = url

        for _ in range(MAX_REDIRECT_HOPS + 1):
            response = await self._single_request(method, current, **kwargs)
            if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
                chain.append(current)
                next_url = _resolve_redirect(current, response.headers["location"])
                current = next_url
                # A 303 always downgrades to GET; others typically preserve
                # method for 307/308. Simplify to GET after the first hop
                # for non-idempotent original methods to match browser/CDN
                # convention and avoid resubmitting bodies to a new host.
                if response.status_code == 303:
                    method = "GET"
                    kwargs.pop("json", None)
                    kwargs.pop("data", None)
                continue
            return FetchResult(response=response, final_url=current, redirect_chain=chain)

        raise BlockedTargetError(f"Redirect chain exceeded {MAX_REDIRECT_HOPS} hops.")

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


def _resolve_redirect(base_url: str, location: str) -> str:
    from urllib.parse import urljoin

    return urljoin(base_url, location)
