"""Trusted client-address resolution, shared by rate limits and the audit log.

``X-Forwarded-For`` is client-controlled; accepting it from any peer would let
a caller mint a fresh bucket per request. Trust is opt-in via
``FORWARDED_ALLOW_IPS`` — the proxy address, a network, or ``*``.

Assumption: the immediate trusted proxy appends (or overwrites) the client IP,
so we take the last hop. The leftmost entries are whatever a client chose to
send and must not be believed.
"""

import ipaddress

from src.config.settings import get_settings


def _is_trusted_peer(peer: str, allowed: list[str]) -> bool:
    """Exact address, CIDR network, or ``*`` — non-IP peers fall back to exact."""
    for entry in allowed:
        if entry == "*" or entry == peer:
            return True
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            # Non-IP peer or non-network entry: exact matching above is all.
            continue
    return False


def resolved_client_ip(peer: str | None, forwarded: str | None) -> str | None:
    """The forwarded client only when the direct peer is trusted; else the peer."""
    if forwarded and peer and _is_trusted_peer(peer, get_settings().forwarded_allow_ips):
        return forwarded.split(",")[-1].strip() or peer
    return peer or None
