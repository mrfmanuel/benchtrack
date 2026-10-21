"""Which client a public request counts against (rate limit, spec §9.14).

`X-Forwarded-For` is not used: Render's proxy appends to whatever the client sent instead of
replacing it, so the leftmost entry is attacker-controlled. Uvicorn with
`--forwarded-allow-ips='*'` picks exactly that entry, which let a client get a fresh
rate-limit bucket on every request by sending a new fake IP.

Instead, the key is either:

- a single header that the edge in front of the app *overwrites* on every request, named by
  `CLIENT_IP_HEADER` (on Render, which is fronted by Cloudflare: `CF-Connecting-IP`), or
- the TCP peer address when no such header is configured or it is missing or malformed.

IPv6 clients usually control a whole /64, so IPv6 addresses are keyed by their /64.
"""

import ipaddress
from collections.abc import Mapping

IPV6_PREFIX = 64


def _parse(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _key(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.IPv6Network(f"{ip}/{IPV6_PREFIX}", strict=False))
    return str(ip)


def rate_limit_key(peer: str | None, headers: Mapping[str, str], trusted_header: str | None) -> str:
    if trusted_header:
        forwarded = _parse(headers.get(trusted_header))
        if forwarded is not None:
            return _key(forwarded)
    peer_ip = _parse(peer)
    if peer_ip is not None:
        return _key(peer_ip)
    return peer or "unknown"
