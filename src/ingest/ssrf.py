"""SSRF guard for user-supplied URLs (plan §7).

The host is resolved with ``socket.getaddrinfo`` and every returned address is
rejected unless it is globally routable — private, loopback, link-local,
multicast, reserved, unspecified and IPv6 site-local ranges are blocked, for
IPv4 and IPv6 alike (including ``::ffff:`` mapped addresses). Redirects are
followed by hand, re-validating each hop, and the body is capped while it
streams. Every rejection raises ``IngestValidationError`` (422-mappable).
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

from src.ingest.extract import IngestValidationError

MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 5_000_000
_CHUNK_BYTES = 65536
_USER_AGENT = "SimulationWorld/1.0"
_ALLOWED_SCHEMES = ("http", "https")


def _is_public(ip: str) -> bool:
    """True only for globally routable addresses (mapped IPv6 unwrapped)."""
    address = ipaddress.ip_address(ip.split("%", 1)[0])  # drop any scope id
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or getattr(address, "is_site_local", False)
        # Belt-and-suspenders: also catch shared/non-routable space the flags
        # above miss, e.g. CGNAT 100.64.0.0/10 (RFC 6598) — is_global is False
        # there but every flag above is False too.
        or not address.is_global
    )


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise IngestValidationError(f"Could not resolve host ({host})") from exc
    return [info[4][0] for info in infos]


def validate_url(url: str) -> str:
    """Validate scheme and every resolved address; return the URL if safe."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise IngestValidationError(
            f"Unsupported URL scheme ({parsed.scheme or 'none'})"
        )
    if not parsed.hostname:
        raise IngestValidationError("URL is missing a host")
    for ip in _resolve(parsed.hostname):
        if not _is_public(ip):
            raise IngestValidationError(f"URL resolves to a non-public address ({ip})")
    return url


def _read_capped(response: requests.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise IngestValidationError(f"Response exceeds the {max_bytes} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(url: str, max_bytes: int = MAX_RESPONSE_BYTES) -> tuple[str, bytes]:
    """Fetch a URL through the guard; return ``(final_url, body_bytes)``.

    Redirects are disabled on the transport and followed manually so every hop
    is re-validated. Callers decode/parse the bytes; this never touches disk.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(current)
        with requests.get(
            current,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": _USER_AGENT},
        ) as response:
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise IngestValidationError("Redirect without a Location header")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise IngestValidationError(
                    f"Download failed: HTTP {response.status_code}"
                )
            return current, _read_capped(response, max_bytes)
    raise IngestValidationError("Too many redirects")
