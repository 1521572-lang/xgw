"""Сборка конфига: карантин доменов, которых нет в DNS, и сводка разбора подписок."""

import json
import logging

import links
import pytest

from xgw import engine, fetch
from xgw.config import Config
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.store import Store

LOG = logging.getLogger("test")


def _vless(host: str, name: str, suffix: str) -> str:
    return (
        f"vless://11111111-2222-3333-4455-6666666666{suffix}@{host}:443?"
        f"security=tls&sni={host}&type=tcp#{name}"
    )


GONE = _vless("gone.example.net", "FR%20gone", "a1")
ALIVE = _vless("alive.example.net", "DE%20alive", "a2")
SERVICE = "vless://11111111-2222-3333-4455-6666666666a3@127.0.0.1:443?type=tcp#service"
EXPIRES = _vless("203.0.113.90", "expire%202026-12-01", "a4")


def _inventory(*link_list: str) -> engine.Inventory:
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "main")
    return engine.Inventory([raw_to_node(raw, "main") for raw in raws])


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


@pytest.fixture()
def dns(monkeypatch):
    """Подставной DNS: что знает — отдаёт, имя из gone — «такого нет», прочее — сбой."""
    book = {"alive.example.net": ["203.0.113.50"]}
    gone = {"gone.example.net"}
    asked: list[str] = []

    def resolve(name, bootstrap, mark):
        asked.append(name)
        if name in gone:
            raise fetch.NoSuchDomain(f"домен {name} не разрешается: такого имени нет (NXDOMAIN)")
        if name in book:
            return book[name]
        raise fetch.ResolveError(f"не удалось разрешить {name}: таймаут")

    monkeypatch.setattr(engine, "resolve_domain", resolve)
    resolve.asked, resolve.gone, resolve.book = asked, gone, book
    return resolve


def _assemble(paths, inventory, cfg=None):
    cfg = cfg or Config()
    return engine.assemble(cfg, paths, inventory, mark=None, logger=LOG, xray_bin=None,
                           check=False)


def test_server_with_a_dead_domain_is_set_aside_and_not_asked_again(paths, dns, caplog):
    """Домена нет в DNS (так было с *.aib2bsas.online): сервер в конфиг не попадает и
    пробы на него не тратятся; при следующих сборках имя даже не спрашивается."""
    inventory = _inventory(links.VLESS_REALITY, GONE, ALIVE)
    with caplog.at_level(logging.WARNING):
        assembly = _assemble(paths, inventory)
    names = [node.name for node in [*assembly.selection.members, *assembly.selection.spares]]
    assert "FR gone" not in names and "DE alive" in names and len(names) == 2
    text = json.dumps(assembly.result.config, ensure_ascii=False)
    assert "gone.example.net" not in text
    assert assembly.result.config["dns"]["hosts"] == {"alive.example.net": ["203.0.113.50"]}
    assert assembly.selection.stats["dns"] == 1
    assert engine.quarantined() == frozenset({"gone.example.net"})
    assert "повторная проверка через 6 ч" in caplog.text

    dns.asked.clear()
    _assemble(paths, inventory)
    assert "gone.example.net" not in dns.asked  # карантин: резолверы не дёргаем


def test_quarantine_ends_after_six_hours_or_on_request(paths, dns, monkeypatch):
    inventory = _inventory(links.VLESS_REALITY, GONE)
    _assemble(paths, inventory)
    assert engine.quarantined()
    dns.gone.clear()
    dns.book["gone.example.net"] = ["203.0.113.77"]  # владелец вернул домен

    assert len(_assemble(paths, inventory).result.nodes) == 1  # срок ещё не вышел
    clock = engine.time.monotonic()
    monkeypatch.setattr(engine.time, "monotonic", lambda: clock + 6 * 3600 + 1)
    assert engine.quarantined() == frozenset()
    assert len(_assemble(paths, inventory).result.nodes) == 2

    # Кнопка «Обновить» в панели проверяет отложенные домены сразу.
    dns.gone.add("gone.example.net")
    _assemble(paths, inventory)  # прежний ответ ещё в кэше на четверть часа
    engine._hosts_cache.clear()
    _assemble(paths, inventory)
    assert engine.quarantined()
    engine.forget_quarantine()
    assert engine.quarantined() == frozenset()


def test_resolver_failure_does_not_drop_servers(paths, dns):
    """Нет сети или резолверы не отвечают — это не «домена нет»: иначе при отключении
    интернета из конфига пропали бы все серверы с доменными именами."""
    unknown = _vless("unknown.example.net", "NL%20unknown", "a5")
    assembly = _assemble(paths, _inventory(links.VLESS_REALITY, unknown))
    assert len(assembly.result.nodes) == 2 and engine.quarantined() == frozenset()
    assert assembly.selection.stats["dns"] == 0


def test_no_usable_server_because_of_dns_is_said_plainly(paths, dns):
    with pytest.raises(engine.EngineError, match="домены серверов не разрешаются"):
        _assemble(paths, _inventory(GONE))
    engine.forget_quarantine()
    with pytest.raises(engine.EngineError, match="после фильтров не осталось серверов"):
        _assemble(paths, _inventory(SERVICE))


def test_summary_counts_what_was_dropped_and_merged(paths, dns):
    """«Узлов: N активных, K запасных (отброшено X недоступных/служебных, схлопнуто Y
    дублей)» — из чего складываются числа."""
    cfg = Config()
    cfg.filters.max_members = 1
    duplicate = links.VLESS_REALITY.rsplit("#", 1)[0] + "#NL%20copy"
    inventory = _inventory(
        links.VLESS_REALITY, duplicate, links.TROJAN, GONE, SERVICE, EXPIRES, ALIVE)
    assembly = _assemble(paths, inventory, cfg)
    summary = engine.summary(assembly)
    assert summary == {
        "members": 1, "spares": 2,
        "dropped": 3,  # домен без адреса, служебный адрес и запись «expire» (фильтр имён)
        "duplicates": 1, "excluded": 0, "dns": 1,
    }
    assert assembly.selection.stats["total"] == 7

    engine.persist(paths, assembly, {})
    store = Store(paths.db_file)
    try:
        assert json.loads(store.get_meta("nodes_summary")) == summary
    finally:
        store.close()

    # Отключённый в панели сервер считается отдельно: это выбор человека, а не сбой.
    cfg.managed.disabled = [assembly.selection.spares[0].fingerprint]
    again = engine.summary(_assemble(paths, inventory, cfg))
    assert again["excluded"] == 1 and again["spares"] == 1 and again["dropped"] == 3


def test_server_list_for_the_panel_names_the_dns_reason(paths, dns):
    inventory = _inventory(links.VLESS_REALITY, GONE)
    _assemble(paths, inventory)
    engine.save_inventory(paths, Config(), inventory)
    listed = {item["name"]: item["skip"] for item in engine.load_inventory(paths)}
    assert listed == {"🇳🇱 NL-1": "", "FR gone": "dns"}
