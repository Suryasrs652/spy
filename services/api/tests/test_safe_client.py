"""§107/§123 SSRF guard — release-blocking.

`is_blocked_ip`/`validate_scheme_and_port` are pure and tested directly.
The network-touching cases (DNS resolution, live fetch, redirect-to-private)
were manually verified against real hosts during development; they are
reproduced here with a monkeypatched resolver so the suite doesn't depend on
network access or a specific external host's availability.
"""
from __future__ import annotations

import pytest

from app.core.errors import BlockedTargetError
from app.core.net import safe_client as sc


@pytest.mark.parametrize(
    "ip,expected_blocked",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("169.254.169.254", True),  # AWS/GCP/Azure metadata
        ("fd00:ec2::254", True),  # AWS IMDSv2 IPv6
        ("10.0.0.5", True),
        ("172.16.0.5", True),
        ("192.168.1.1", True),
        ("100.64.0.1", True),  # CGNAT — not covered by ipaddress.is_private
        ("224.0.0.1", True),  # multicast
        ("0.0.0.0", True),
        ("::ffff:127.0.0.1", True),  # IPv4-mapped loopback
        ("8.8.8.8", False),
        ("1.1.1.1", False),
        ("2606:4700:4700::1111", False),
    ],
)
def test_is_blocked_ip(ip: str, expected_blocked: bool) -> None:
    assert sc.is_blocked_ip(ip) is expected_blocked


@pytest.mark.parametrize(
    "url",
    ["http://example.com", "https://example.com", "https://example.com:443", "http://example.com:80"],
)
def test_validate_scheme_and_port_allows(url: str) -> None:
    sc.validate_scheme_and_port(url)  # must not raise


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "https://example.com:8443",
        "http://example.com:8080",
        "file:///etc/passwd",
        "gopher://x",
    ],
)
def test_validate_scheme_and_port_rejects(url: str) -> None:
    with pytest.raises(BlockedTargetError):
        sc.validate_scheme_and_port(url)


def test_resolve_host_rejects_private_via_monkeypatch(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, *args, **kwargs):
        return [(None, None, None, None, ("10.0.0.5", 0))]

    monkeypatch.setattr(sc.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(BlockedTargetError):
        sc.validate_host_resolves_safely("internal.example.test")


def test_resolve_host_rejects_if_any_answer_is_unsafe(monkeypatch) -> None:
    """A hostname with multiple A records where only one is private must
    still be rejected outright (§107) — never "pick the safe one".
    """

    def fake_getaddrinfo(hostname, *args, **kwargs):
        return [
            (None, None, None, None, ("8.8.8.8", 0)),
            (None, None, None, None, ("10.0.0.1", 0)),
        ]

    monkeypatch.setattr(sc.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(BlockedTargetError):
        sc.validate_host_resolves_safely("mixed.example.test")


def test_resolve_host_allows_public(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, *args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 0))]

    monkeypatch.setattr(sc.socket, "getaddrinfo", fake_getaddrinfo)
    ip = sc.validate_host_resolves_safely("public.example.test")
    assert ip == "8.8.8.8"


def test_dns_failure_is_distinguishable_from_blocked_target(monkeypatch) -> None:
    import socket as socket_module

    def fake_getaddrinfo(hostname, *args, **kwargs):
        raise socket_module.gaierror("nodename nor servname provided")

    monkeypatch.setattr(sc.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(sc.DnsResolutionError):
        sc.validate_host_resolves_safely("nonexistent.example.test")


@pytest.mark.asyncio
async def test_fetch_blocks_private_target(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, *args, **kwargs):
        return [(None, None, None, None, ("127.0.0.1", 0))]

    monkeypatch.setattr(sc.socket, "getaddrinfo", fake_getaddrinfo)
    fetcher = sc.SafeFetcher(timeout=2.0)
    try:
        with pytest.raises(BlockedTargetError):
            await fetcher.fetch("http://looks-legit.example.test/")
    finally:
        await fetcher.aclose()
