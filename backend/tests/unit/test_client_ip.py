"""Rate-limit client key: never X-Forwarded-For; optional edge header; IPv6 by /64."""

import pytest

from app.services.client_ip import rate_limit_key

CF = "CF-Connecting-IP"


def key(peer="10.0.0.5", trusted_header=None, **headers):
    normalized = {name.replace("_", "-"): value for name, value in headers.items()}
    return rate_limit_key(peer, normalized, trusted_header)


def test_peer_address_without_a_trusted_header():
    assert key() == "10.0.0.5"


@pytest.mark.parametrize("trusted_header", [None, CF])
def test_x_forwarded_for_is_never_used(trusted_header):
    spoofed = {"X-Forwarded-For": "198.51.100.77, 203.0.113.9"}
    assert rate_limit_key("10.0.0.5", spoofed, trusted_header) == "10.0.0.5"


def test_trusted_header_wins_when_configured():
    assert rate_limit_key("10.0.0.5", {CF: " 203.0.113.9 "}, CF) == "203.0.113.9"


def test_trusted_header_is_ignored_when_not_configured():
    assert rate_limit_key("10.0.0.5", {CF: "203.0.113.9"}, None) == "10.0.0.5"


@pytest.mark.parametrize("bad", ["", "not-an-ip", "203.0.113.9, 198.51.100.1", "999.1.1.1"])
def test_malformed_trusted_header_falls_back_to_the_peer(bad):
    assert rate_limit_key("10.0.0.5", {CF: bad}, CF) == "10.0.0.5"


def test_ipv6_clients_are_keyed_by_their_64():
    a = rate_limit_key("::1", {CF: "2001:db8:1:2::1"}, CF)
    b = rate_limit_key("::1", {CF: "2001:db8:1:2:ffff:ffff:ffff:ffff"}, CF)
    c = rate_limit_key("::1", {CF: "2001:db8:1:3::1"}, CF)
    assert a == b == "2001:db8:1:2::/64"
    assert c != a


def test_ipv4_mapped_ipv6_is_treated_as_ipv4():
    assert rate_limit_key("::ffff:203.0.113.9", {}, None) == "203.0.113.9"


@pytest.mark.parametrize(("peer", "expected"), [("testclient", "testclient"), (None, "unknown")])
def test_non_ip_peers_are_kept_as_is(peer, expected):
    assert rate_limit_key(peer, {}, None) == expected
