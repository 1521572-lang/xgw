"""Тесты модели: отпечатки, страна, дедупликация."""

import links

from xgw.model import country_from_name, make_fingerprint, raw_to_node
from xgw.parsers.common import parse_link


def test_fingerprint_deterministic_and_sensitive():
    base = make_fingerprint("vless", "A.example.com", 443, "id-1", "tcp/reality")
    assert base == make_fingerprint("VLESS", "a.example.com", 443, "id-1", "tcp/reality")
    assert base != make_fingerprint("vless", "a.example.com", 8443, "id-1", "tcp/reality")
    assert base != make_fingerprint("vless", "a.example.com", 443, "id-2", "tcp/reality")
    assert len(base) == 8


def test_country_from_flags_and_codes():
    assert country_from_name("🇳🇱 NL-1") == "nl"
    assert country_from_name("US-2 Seattle") == "us"
    assert country_from_name("London 3") == "xx"


def test_raw_to_node_carries_fields():
    raw = parse_link(links.VLESS_REALITY)
    node = raw_to_node(raw, "main")
    assert node.source == "main"
    assert node.country == "nl"
    assert node.fingerprint == make_fingerprint(
        "vless", "203.0.113.10", 443,
        "11111111-2222-3333-4455-666666666661", "tcp/reality",
    )
