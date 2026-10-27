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


def test_raw_to_node_trims_the_name():
    raw = parse_link(links.VLESS_REALITY)
    raw.name = "\u00a0🇹🇷 Турция \t"
    assert raw_to_node(raw, "main").name == "🇹🇷 Турция"
    raw.name = "   "
    assert raw_to_node(raw, "main").name == "203.0.113.10:443"


def test_variants_of_one_server_are_not_duplicates():
    """Пятый аудит, T2: одни протокол, адрес, порт, ключ и транспорт, но разные путь и режим
    XHTTP — разные серверы (CDN с путём на каждый выход), а не дубль: им отпечаток с этими
    полями. Настоящий дубль (поля те же) — тот же отпечаток; у прочих он прежний."""
    from xgw.model import split_variants

    base = ("vless://11111111-2222-3333-4455-666666666661@edge.example.com:443"
            "?type=xhttp&security=tls&sni=edge.example.com&path=")
    first = raw_to_node(parse_link(base + "/a&mode=packet-up#A"), "main")
    twin = raw_to_node(parse_link(base + "/a&mode=packet-up#A2"), "other")
    second = raw_to_node(parse_link(base + "/b&mode=stream-up#B"), "main")
    alone = raw_to_node(parse_link(links.VLESS_REALITY), "main")
    shared, kept = first.fingerprint, alone.fingerprint
    assert first.fingerprint == second.fingerprint == twin.fingerprint
    assert split_variants([first, twin, second, alone]) == 3
    assert first.fingerprint == twin.fingerprint != second.fingerprint
    assert shared not in (first.fingerprint, second.fingerprint)
    assert alone.fingerprint == kept
    assert len(first.fingerprint) == 8
