"""Дробление ClientHello (0.1.11): сборка конфига, применение через API и решения демона.

Ссылки и адреса — фейковые (tests/links.py). Модель DPI в тестах демона: запасной
«заблокирован» — без дробления скан не проходит (CONNECT_FAIL), с дроблением проходит.
Настоящий Xray дробит ClientHello на стенде (tests/stand/test_stand.py).
"""

import os
from pathlib import Path

import links
import pytest
from test_daemon import Harness, _started

from xgw import engine
from xgw.config import Config
from xgw.generator import fragment as fragmenting
from xgw.generator import validate
from xgw.generator.builder import applied_nodes, build, fragmented_fingerprints, select_nodes
from xgw.generator.diff import apply_plan, diff_configs
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.watch.scan import ScanResult

LINKS = [links.VLESS_REALITY, links.VLESS_WS, links.VLESS_KCP, links.VLESS_TCP_HTTP]
HOSTS = {"de.example.com": ["203.0.113.11"]}


def _nodes(link_list=LINKS):
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "test")
    return [raw_to_node(raw, "test") for raw in raws]


def _build(cfg: Config, nodes, fragment=()):
    cfg.filters.max_members = 2
    return build(cfg, select_nodes(nodes, cfg), hosts=HOSTS, probe_password="P" * 32,
                 fragment=fragment)


def _by_name(nodes, name):
    return next(node for node in nodes if node.name.endswith(name))


def _outbound(config, tag):
    return next(item for item in config["outbounds"] if item["tag"] == tag)


# --- сборка конфига ------------------------------------------------------------------


def test_chosen_servers_dial_through_the_fragment_outbound():
    nodes = _nodes()
    reality, kcp = _by_name(nodes, "NL-1"), _by_name(nodes, "FR-2")
    cfg = Config()
    result = _build(cfg, nodes, fragment={reality.fingerprint, kcp.fingerprint})
    config = result.config
    info = {item.fingerprint: item for item in result.nodes}
    # REALITY поверх TCP — через дробление; mKCP идёт по UDP, ClientHello у него нет.
    assert info[reality.fingerprint].fragment and not info[kcp.fingerprint].fragment
    sockopt = _outbound(config, info[reality.fingerprint].tag)["streamSettings"]["sockopt"]
    assert sockopt == {"mark": cfg.capture.mark_bypass, "domainStrategy": "UseIPv4",
                       "dialerProxy": "fragment"}
    assert "dialerProxy" not in _outbound(config, info[kcp.fingerprint].tag)[
        "streamSettings"]["sockopt"]
    assert _outbound(config, "fragment") == {
        "tag": "fragment", "protocol": "freedom",
        "settings": {"domainStrategy": "UseIPv4", "fragment": {
            "packets": "tlshello", "length": "100-200", "interval": "10-20"}},
        # Сокет создаёт этот outbound — ему и метка «мимо перехвата».
        "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}},
    }
    assert config["outbounds"][0]["tag"].startswith("proxy-")  # первый — по-прежнему сервер
    # Режим читается из применённого конфига — так он переживает обновление подписки.
    assert fragmented_fingerprints(config, nodes) == {reality.fingerprint}
    assert [item.fragment for item in applied_nodes(config, nodes)] == [
        item.fragment for item in result.nodes
    ]


def test_without_fragmented_servers_there_is_no_fragment_outbound():
    config = _build(Config(), _nodes()).config
    assert all(item["tag"] != "fragment" for item in config["outbounds"])
    assert fragmented_fingerprints(config, _nodes()) == set()


def test_mode_always_fragments_every_tls_server_and_off_none():
    nodes = _nodes()
    cfg = Config()
    cfg.fragment.mode = "always"
    result = _build(cfg, nodes)
    flags = {item.fingerprint: item.fragment for item in result.nodes}
    assert flags == {
        _by_name(nodes, "NL-1").fingerprint: True, _by_name(nodes, "DE-1").fingerprint: True,
        _by_name(nodes, "FR-2").fingerprint: False, _by_name(nodes, "FR-4").fingerprint: False,
    }
    cfg = Config()
    cfg.fragment.mode = "off"
    result = _build(cfg, nodes, fragment={node.fingerprint for node in nodes})
    assert not any(item.fragment for item in result.nodes)


def test_eligibility():
    assert fragmenting.eligible({"streamSettings": {"security": "reality", "network": "raw"}})
    assert fragmenting.eligible({"streamSettings": {"security": "tls", "network": "xhttp"}})
    assert not fragmenting.eligible({"streamSettings": {"security": "none"}})
    assert not fragmenting.eligible({"streamSettings": {"security": "tls", "network": "kcp"}})
    # XHTTP поверх HTTP/3 — это QUIC.
    assert not fragmenting.eligible({"streamSettings": {
        "security": "tls", "network": "xhttp", "tlsSettings": {"alpn": ["h3"]}}})
    # Звено цепочки из JSON-подписки уже устанавливает соединение через свой outbound.
    assert not fragmenting.eligible({"streamSettings": {
        "security": "tls", "sockopt": {"dialerProxy": "chain-nl-1"}}})


@pytest.mark.skipif(not os.environ.get("XGW_XRAY_BIN"), reason="нужен Xray (XGW_XRAY_BIN)")
def test_xray_accepts_the_config_with_fragmenting():
    nodes = _nodes()
    result = _build(Config(), nodes, fragment={node.fingerprint for node in nodes})
    ok, output = validate.validate_config(result.config, Path(os.environ["XGW_XRAY_BIN"]))
    assert ok, output


def test_fragmenting_is_switched_through_the_api_in_the_right_order():
    """Outbound fragment добавляется раньше, чем на него сошлётся заменённый сервер, а
    снимается — после того, как сервер заменён обратно (apply_plan)."""
    nodes = _nodes()
    reality = _by_name(nodes, "NL-1")
    plain = _build(Config(), nodes).config
    split = _build(Config(), nodes, fragment={reality.fingerprint}).config

    class Client:
        def __init__(self):
            self.calls = []

        def add_outbounds(self, items):
            self.calls += [("ado", item["tag"]) for item in items]

        def remove_outbound(self, tag):
            self.calls.append(("rmo", tag))

        def add_inbounds(self, items):
            self.calls += [("adi", item["tag"]) for item in items]

        def remove_inbound(self, tag):
            self.calls.append(("rmi", tag))

        def replace_routing(self, routing):
            self.calls.append(("adrules", ""))

    tag = next(item.tag for item in _build(Config(), nodes).nodes
               if item.fingerprint == reality.fingerprint)
    forward = diff_configs(plain, split)
    assert forward.plan is not None and not forward.restart_reasons  # без перезапуска Xray
    client = Client()
    apply_plan(client, forward.plan)
    assert client.calls == [("ado", "fragment"), ("rmo", tag), ("ado", tag)]
    back = diff_configs(split, plain)
    assert back.plan is not None and not back.restart_reasons
    client = Client()
    apply_plan(client, back.plan)
    assert client.calls == [("rmo", tag), ("ado", tag), ("rmo", "fragment")]


def test_allow_insecure_from_a_json_subscription_is_not_passed_to_xray():
    nodes = _nodes([links.VLESS_WS])
    nodes[0].outbound["streamSettings"]["tlsSettings"]["allowInsecure"] = True
    config = _build(Config(), nodes).config
    tls = config["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert "allowInsecure" not in tls and tls["serverName"] == "de.example.com"


# --- демон ---------------------------------------------------------------------------


class Dpi(Harness):
    """Демон за «провайдером с DPI»: blocked — probe-теги серверов, которые отвечают только
    с дроблением ClientHello; dead — не отвечают никак."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, fragment="auto", **kwargs)
        self.blocked: set[str] = set()
        self.dead: set[str] = set()
        self.modes: list[tuple[str, bool]] = []  # (probe-тег, с дроблением ли) каждого скана

    def _scan(self, info, password, url=None):
        self.scanned.append(info.tag)
        self.modes.append((info.probe_tag, info.fragment))
        if info.probe_tag in self.dead:
            return ScanResult(info.tag, "TIMEOUT", 0, 10.0, "таймаут")
        if info.probe_tag in self.blocked and not info.fragment:
            return ScanResult(info.tag, "CONNECT_FAIL", 0, 0.1, "соединение сброшено")
        return ScanResult(info.tag, "OK", 65536, 0.5)

    def spare(self, index: int = 0):
        return [info for info in self.view() if info.role == "spare"][index]

    def mode(self, fingerprint: str) -> bool:
        return next(info.fragment for info in self.view() if info.fingerprint == fingerprint)


@pytest.fixture()
def dpi(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    # Вторая ступень дробления в Xray (0.1.18) — в своих тестах: здесь лестница, как до неё.
    cfg.fragment.split = False
    return Dpi(cfg, paths)


def _rescan(daemon: Dpi) -> None:
    """Плановый скан запасных — на следующем шаге."""
    daemon.next_scan = daemon.t
    daemon.next_refresh = daemon.t + 3600  # подписку на этом шаге не обновлять


def test_spare_that_answers_only_with_fragmenting_gets_it_and_keeps_it(dpi):
    _started(dpi)
    spare = dpi.spare()
    dpi.blocked.add(spare.probe_tag)
    _rescan(dpi)
    dpi.tick()  # скан без дробления не прошёл — сервер переключён на дробление и ждёт скана
    assert dpi.mode(spare.fingerprint) is True
    assert len(dpi.applied) == 1 and not dpi.applied[0][1]  # через API, не срочно
    assert spare.probe_tag not in dpi._fresh_scans()  # по старому скану в работу не возьмут
    dpi.tick()  # скан с дроблением прошёл
    assert dpi.modes[-1] == (spare.probe_tag, True)
    assert dpi._fresh_scans()[spare.probe_tag]["verdict"] == "OK"
    name = next(node.name for node in dpi.inventory.nodes
                if node.fingerprint == spare.fingerprint)
    assert (
        f"fragment: «{name}» ({spare.tag}) отвечает только с дроблением ClientHello — оно включено"
        in dpi.events()
    )
    assert next(entry for entry in dpi.status()["spares"]
                if entry["tag"] == spare.tag)["fragment"] is True
    # Обновление подписки и новый демон (перезапуск службы) режим не сбрасывают.
    dpi._rebuild(None, urgent=False, reason="обновление подписки")
    assert dpi.mode(spare.fingerprint) is True
    again = Dpi(dpi.cfg, dpi.paths)
    again.inventory = dpi.inventory
    assert again.mode(spare.fingerprint) is True


def test_spares_with_one_name_are_told_apart_by_tag_in_events(dpi):
    """Перепроверка 0.1.18 (25.10.2026): двенадцать серверов «🚀Авто | Лучший сервер» одной
    подписки в событиях обхода выглядели как один сервер, эскалация которого идёт каждую
    минуту. В событии после имени — тег сервера."""
    _started(dpi)
    first, second = dpi.spare(0), dpi.spare(1)
    for node in dpi.inventory.nodes:
        if node.fingerprint in (first.fingerprint, second.fingerprint):
            node.name = "🚀Авто | Лучший сервер"
    dpi.blocked.update((first.probe_tag, second.probe_tag))
    _rescan(dpi)
    dpi.tick()  # без дробления не ответили — обоим включено дробление
    dpi.tick()  # с дроблением ответили
    for spare in (first, second):
        assert (
            f"fragment: «🚀Авто | Лучший сервер» ({spare.tag}) отвечает только с дроблением "
            "ClientHello — оно включено" in dpi.events()
        ), spare.tag


def test_fragmenting_that_does_not_help_is_undone_and_retried_after_six_hours(dpi):
    _started(dpi)
    spare = dpi.spare()
    dpi.dead.add(spare.probe_tag)
    _rescan(dpi)
    dpi.tick()
    assert dpi.mode(spare.fingerprint) is True
    dpi.tick()  # и с дроблением не отвечает — прежний режим возвращается тем же шагом
    assert dpi.mode(spare.fingerprint) is False and len(dpi.applied) == 2
    assert any("не отвечает и с дроблением ClientHello — оно выключено" in event
               for event in dpi.events())
    dpi.t += 3600
    _rescan(dpi)
    dpi.tick()  # снова не отвечает, но пробовали меньше FRAGMENT_RETRY назад
    assert len(dpi.applied) == 2 and dpi.mode(spare.fingerprint) is False
    dpi.t += 5 * 3600 + 60
    _rescan(dpi)
    dpi.tick()
    assert dpi.mode(spare.fingerprint) is True and len(dpi.applied) == 3


def test_fragmented_spare_is_tried_without_it_after_a_calm_streak(dpi):
    """ТЗ R1.3 (0.1.18): сервер на дроблении пробуется без него, когда прошёл
    fragment.calm_probes проверок подряд (20) и пробыл на дроблении не меньше
    fragment.calm_hours (12 ч) — дробление тратит процессор сервера и чуть скорости. До 0.1.18 —
    раз в сутки, сколько бы проверок ни было."""
    _started(dpi)
    spare = dpi.spare()
    dpi.blocked.add(spare.probe_tag)
    _rescan(dpi)
    dpi.tick()
    dpi.tick()
    assert dpi.mode(spare.fingerprint) is True
    dpi.blocked.clear()  # провайдер перестал блокировать
    for _ in range(19):  # 19 проверок за 12 ч 40 мин — проверок мало
        dpi.t += 2400
        _rescan(dpi)
        dpi.tick()
    assert dpi.mode(spare.fingerprint) is True and dpi._calm[spare.fingerprint] == 19
    dpi.t += 2400
    _rescan(dpi)
    dpi.tick()  # двадцатая и больше 12 ч — пробуется без дробления
    assert dpi.mode(spare.fingerprint) is False
    dpi.tick()
    assert any("отвечает и без дробления ClientHello — оно выключено" in event
               for event in dpi.events())
    assert dpi.mode(spare.fingerprint) is False


def test_twenty_quick_checks_are_not_enough_without_twelve_hours(dpi):
    """И наоборот: 20 проверок подряд за пару часов — мало времени, дробление остаётся."""
    _started(dpi)
    spare = dpi.spare()
    dpi.blocked.add(spare.probe_tag)
    _rescan(dpi)
    dpi.tick()
    dpi.tick()
    dpi.blocked.clear()
    for _ in range(25):
        dpi.t += 300
        _rescan(dpi)
        dpi.tick()
    assert dpi.mode(spare.fingerprint) is True and dpi._calm[spare.fingerprint] >= 20


def test_dead_member_gives_way_to_a_spare_that_answers_only_with_fragmenting(dpi):
    """Провайдер блокирует запасные по SNI: участник умер — его место занимает запасной,
    которому шлюз сам включил дробление, и в участниках дробление у него остаётся."""
    dpi.cfg.filters.rotate_after_min = 0
    _started(dpi)
    spares = [info for info in dpi.view() if info.role == "spare"]
    dpi.blocked.update(info.probe_tag for info in spares)
    victim = dpi.tags("proxy")[0]
    dpi.set_alive(**{victim.replace("-", "_"): False})
    _rescan(dpi)
    for _ in range(6):
        dpi.tick()
        if victim not in dpi.tags("proxy"):
            break
    assert victim not in dpi.tags("proxy")
    newcomer = next(info for info in dpi.view() if info.role == "proxy"
                    and info.fingerprint in {spare.fingerprint for spare in spares})
    assert newcomer.fragment is True


def test_a_member_is_fragmented_in_place_and_mode_off_switches_nobody(dpi):
    """ТЗ R1 (0.1.18): при глушении по всей сети (ядро считает мёртвыми и других участников)
    участник, который без дробления не отвечает (CONNECT_FAIL), не списывается — ему на месте
    включают дробление ClientHello, и он остаётся в работе. Одиночный отказ при живых других —
    замена сразу (анти-ТСПУ 2.0, test_tspu). При fragment.mode = "off" не переключают никого."""
    _started(dpi)
    member = next(info for info in dpi.view() if info.role == "proxy")
    dpi.set_alive(**{
        tag.replace("-", "_"): False for tag in dpi.tags("proxy") if tag != member.tag
    })
    dpi.blocked.add(member.probe_tag)
    dpi.vetted.clear()  # первая проверка участника — снова
    _rescan(dpi)
    dpi.tick()
    assert dpi.mode(member.fingerprint) is True  # дробление на месте, без замены
    assert member.tag in dpi.tags("proxy") and member.tag not in dpi.bad_members
    assert dpi.applied[-1][1] is True  # срочно: трафик через него ждёт
    dpi.tick()  # с дроблением отвечает — так и остаётся
    assert dpi.mode(member.fingerprint) is True and member.tag in dpi.tags("proxy")
    assert any("отвечает только с дроблением ClientHello — оно включено" in event
               for event in dpi.events())
    dpi.cfg.fragment.mode = "off"
    spare = dpi.spare()
    dpi.blocked.add(spare.probe_tag)
    applied = len(dpi.applied)
    _rescan(dpi)
    dpi.tick()
    assert dpi.mode(spare.fingerprint) is False
    assert dpi._profile_wanted == {} and dpi._profile_trial == {}
    assert len(dpi.applied) >= applied


def test_engine_keeps_fragmenting_from_the_applied_config(dpi):
    _started(dpi)
    spare = dpi.spare()
    assembly = engine.assemble(
        dpi.cfg, dpi.paths, dpi.inventory, mark=None, logger=dpi.log, xray_bin=None,
        check=False, fragment={spare.fingerprint},
    )
    dpi._apply(assembly.result.config, urgent=False)
    again = engine.assemble(
        dpi.cfg, dpi.paths, dpi.inventory, mark=None, logger=dpi.log, xray_bin=None,
        check=False,
    )
    assert fragmented_fingerprints(again.result.config, dpi.inventory.nodes) == {
        spare.fingerprint}
