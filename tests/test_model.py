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


XHTTP = ("vless://11111111-2222-3333-4455-666666666661@edge.example.com:443"
         "?type=xhttp&security=tls&sni=edge.example.com&mode=packet-up&path=")


def _variants(*paths: str):
    return [raw_to_node(parse_link(f"{XHTTP}/{path}#{path}"), "main") for path in paths]


def test_variant_fingerprint_does_not_depend_on_the_neighbours():
    """R01 кросс-аудита 4cc96b9: A → A+B → A менял отпечаток A дважды, а с ним терялись выбор
    вручную, замеры и итоги проверок. С историей выдачи отпечаток варианта — его собственный:
    A остаётся A, B — B, хоть один, хоть вместе, в любом порядке."""
    from xgw.model import split_variants

    known: dict = {}
    (alone,) = _variants("a")
    split_variants([alone], known, now=1.0)
    first = alone.fingerprint
    a, b = _variants("a", "b")
    assert split_variants([a, b], known, now=2.0) == 1
    assert a.fingerprint == first != b.fingerprint
    second = b.fingerprint
    (a,) = _variants("a")
    split_variants([a], known, now=3.0)
    (b,) = _variants("b")
    split_variants([b], known, now=4.0)
    assert (a.fingerprint, b.fingerprint) == (first, second)
    b, a = _variants("b", "a")
    split_variants([b, a], known, now=5.0)
    assert (a.fingerprint, b.fingerprint) == (first, second)
    (c,) = _variants("c")  # вместо двух — один новый: какой из них, не понять — общий отпечаток
    split_variants([c], known, now=6.0)
    assert c.fingerprint == first


def test_a_single_server_whose_path_changes_on_every_download_keeps_its_fingerprint():
    """Отчёт audit6b: у 21 одиночного сервера подписки поле варианта другое при каждом
    скачивании — и с историей выдачи каждый раз новый отпечаток: сканы заново, очередь замеров
    скорости запасных («0 из 20») не доходила до конца. Единственный вариант — тот же сервер: он
    наследует отпечаток единственного варианта прошлого опроса; история не растёт."""
    from xgw.model import split_variants

    known: dict = {}
    seen = []
    for step, path in enumerate(("r1", "r2", "r3", "r4"), 1):
        (node,) = _variants(path)
        split_variants([node], known, now=float(step))
        seen.append(node.fingerprint)
    assert len(set(seen)) == 1 and sum(len(entries) for entries in known.values()) == 1
    # Вариант B, оставшийся один, держит свой отпечаток и тогда, когда его путь меняется.
    a, b = _variants("a", "b")
    split_variants([a, b], known, now=5.0)
    own = b.fingerprint
    (b,) = _variants("b")
    split_variants([b], known, now=6.0)
    assert b.fingerprint == own
    for step, path in enumerate(("b2", "b3"), 7):
        (node,) = _variants(path)
        split_variants([node], known, now=float(step))
        assert node.fingerprint == own


def test_websocket_host_from_headers_tells_servers_apart_and_old_ids_stay():
    """R01: серверы одного CDN, различимые только устаревшей записью headers.Host, — разные; а
    прежние отпечатки вариантов (без неё) при первом запуске сохраняются по прошлому списку."""
    from xgw import model

    link = ("vless://11111111-2222-3333-4455-666666666662@cdn.example.com:443"
            "?type=ws&security=tls&sni=cdn.example.com&path=%2F#X")

    def node(path: str, host: str):
        item = raw_to_node(parse_link(link), "main")
        item.outbound["streamSettings"]["wsSettings"] = {"path": path, "headers": {"Host": host}}
        return item

    one, two = node("/", "a.example"), node("/", "b.example")
    assert model.variant_key(one) != model.variant_key(two)
    assert model.variant_key(one, legacy=True) == model.variant_key(two, legacy=True)
    model.split_variants([one, two], {})
    assert one.fingerprint != two.fingerprint
    left, right = node("/l", "h.example"), node("/r", "h.example")
    base = left.fingerprint
    old = {model._variant_fingerprint(base, model.variant_key(item, legacy=True))
           for item in (left, right)}
    model.split_variants([left, right], {}, previous=old)
    assert {left.fingerprint, right.fingerprint} == old
