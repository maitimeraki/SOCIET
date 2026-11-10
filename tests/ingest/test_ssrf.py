"""SSRF guard tests. DNS and HTTP are fully mocked — never real egress."""

import ipaddress
import socket

import pytest

from src.ingest import ssrf
from src.ingest.extract import IngestValidationError

# Hostnames used by the tests resolve to these addresses; IP literals echo.
_RESOLVE = {"public.example": "93.184.216.34", "internal.example": "10.0.0.1"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Replace DNS so no hostname ever leaves the machine."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        ip = _RESOLVE.get(host)
        if ip is None:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                raise socket.gaierror(f"unresolved host: {host}") from None
            ip = host
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]

    monkeypatch.setattr("src.ingest.ssrf.socket.getaddrinfo", fake_getaddrinfo)


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b"", is_redirect=False):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.is_redirect = is_redirect

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_get(monkeypatch, responses, calls=None):
    def fake_get(url, **kwargs):
        if calls is not None:
            calls.append((url, kwargs))
        return responses[url]

    monkeypatch.setattr("src.ingest.ssrf.requests.get", fake_get)


# --- address validation -----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",  # loopback
        "http://[::1]/",  # IPv6 loopback
        "http://169.254.169.254/latest/meta-data/",  # link-local (cloud metadata)
        "http://10.0.0.5/",  # RFC1918
        "http://192.168.1.10/",  # RFC1918
        "http://172.16.0.1/",  # RFC1918
        "http://[::ffff:127.0.0.1]/",  # mapped IPv6 loopback
        "http://[fc00::1]/",  # IPv6 unique-local
        "http://100.64.0.1/",  # CGNAT / RFC 6598 shared space
        "http://100.100.100.200/",  # Alibaba Cloud metadata, inside CGNAT range
        "http://0.0.0.0/",  # unspecified
        "http://224.0.0.1/",  # multicast
        "http://internal.example/",  # hostname resolving private
    ],
)
def test_reject_non_public_addresses(url):
    with pytest.raises(IngestValidationError, match="non-public address"):
        ssrf.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://public.example/file",  # scheme not allowed
        "file:///etc/passwd",  # local file
        "http:///nohost",  # missing host
    ],
)
def test_reject_bad_scheme_or_host(url):
    with pytest.raises(IngestValidationError):
        ssrf.validate_url(url)


def test_allow_public_host():
    assert ssrf.validate_url("http://public.example/") == "http://public.example/"


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8"])
def test_allow_public_ip_literals(ip):
    # The CGNAT fix must not over-reject globally routable addresses.
    assert ssrf.validate_url(f"http://{ip}/") == f"http://{ip}/"


# --- fetch behaviour --------------------------------------------------------


def test_fetch_returns_body_and_disables_transport_redirects(monkeypatch):
    calls = []
    _install_get(
        monkeypatch,
        {"http://public.example/": _FakeResponse(200, body=b"hello world")},
        calls,
    )
    final_url, body = ssrf.fetch_url("http://public.example/")
    assert (final_url, body) == ("http://public.example/", b"hello world")
    assert calls[0][1]["allow_redirects"] is False


def test_redirect_to_private_is_blocked(monkeypatch):
    _install_get(
        monkeypatch,
        {
            "http://public.example/": _FakeResponse(
                302, {"Location": "http://127.0.0.1/"}, is_redirect=True
            )
        },
    )
    with pytest.raises(IngestValidationError, match="non-public address"):
        ssrf.fetch_url("http://public.example/")


def test_follows_public_redirect(monkeypatch):
    _install_get(
        monkeypatch,
        {
            "http://public.example/": _FakeResponse(
                301, {"Location": "http://public.example/final"}, is_redirect=True
            ),
            "http://public.example/final": _FakeResponse(200, body=b"landed"),
        },
    )
    assert ssrf.fetch_url("http://public.example/") == (
        "http://public.example/final",
        b"landed",
    )


def test_too_many_redirects(monkeypatch):
    responses = {
        f"http://public.example/{i}": _FakeResponse(
            302,
            {"Location": f"http://public.example/{i + 1}"},
            is_redirect=True,
        )
        for i in range(6)
    }
    _install_get(monkeypatch, responses)
    with pytest.raises(IngestValidationError, match="Too many redirects"):
        ssrf.fetch_url("http://public.example/0")


def test_oversized_response_is_capped(monkeypatch):
    _install_get(
        monkeypatch,
        {"http://public.example/": _FakeResponse(200, body=b"a" * 4096)},
    )
    with pytest.raises(IngestValidationError, match="exceeds the 1024 byte limit"):
        ssrf.fetch_url("http://public.example/", max_bytes=1024)


def test_http_error_is_rejected(monkeypatch):
    _install_get(
        monkeypatch,
        {"http://public.example/": _FakeResponse(403, body=b"")},
    )
    with pytest.raises(IngestValidationError, match="Download failed: HTTP 403"):
        ssrf.fetch_url("http://public.example/")
