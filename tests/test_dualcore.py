"""Два ядра (0.1.12): сборка конфигов Xray и sing-box вместе, профили обхода, лестница при
блокировке, закрепление ядра, слежение за sing-box. Ядра подменены (tests/test_daemon.py);
ссылки и ключи — фейковые."""

import json

import links
import pytest
from test_daemon import Harness

from xgw import engine, managed
from xgw.config import Config
from xgw.daemon import PROFILE_RECHECK, PROFILE_RETRY, SINGBOX_RETRY
from xgw.generator import builder, profiles
from xgw.generator import fragment as fragmenting
from xgw.generator import singbox as singboxing
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths, atomic_write_json
from xgw.watch.scan import ScanResult

ANYTLS = "anytls://pw@any.example:443?sni=any.example#%F0%9F%87%B8%F0%9F%87%AA%20AnyTLS"
HY2 = ("hysteria2://s3cret@hy.example.com:443/?sni=hy.example.com"
       "#%F0%9F%87%AD%F0%9F%87%B0%20HY")
LINKS = [
    links.VLESS_WS, links.VLESS_REALITY, links.TROJAN, links.VMESS, links.VLESS_XHTTP,
    HY2, ANYTLS,
]


def _inventory(link_list=LINKS) -> engine.Inventory:
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "main")
    quotas = {"main": {"upload": 0, "download": 10**9, "total": 0}}  # безлимитная
    return engine.Inventory([raw_to_node(raw, "main") for raw in raws], quotas, True)


class Dual(Harness):
    """Демон с двумя ядрами: профиль сервера в скане определяет вердикт."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, fragment="auto", **kwargs)
        self.singbox_ok = True
        self.source = _inventory()
        self.table: dict[str, dict[str, str]] = {}  # probe-тег → {профиль или "*": вердикт}
        self.seen: list[tuple[str, str]] = []  # (probe-тег, профиль) каждого скана

    def _scan(self, info, password, url=None):
        self.scanned.append(info.tag)
        self.seen.append((info.probe_tag, info.profile))
        rules = self.table.get(info.probe_tag, {})
        verdict = rules.get(info.profile, rules.get("*", "OK"))
        return ScanResult(info.tag, verdict, 65536 if verdict == "OK" else 16384, 0.5)

    def node(self, info):
        return next(node for node in self.inventory.nodes if node.fingerprint == info.fingerprint)

    def spares(self, *, capability=None, tls=False):
        result = []
        for info in self.view():
            if info.role != "spare":
                continue
            node = self.node(info)
            if capability and node.capability != capability:
                continue
            if tls and not (node.outbound and fragmenting.eligible(node.outbound)):
                continue
            result.append(info)
        return result

    def profile(self, info) -> str:
        return next(item.profile for item in self.view() if item.fingerprint == info.fingerprint)


@pytest.fixture()
def dual(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    instance = Dual(cfg, paths)
    yield instance
    instance.store.close()


def _start(daemon: Dual) -> Dual:
    daemon.tick()
    daemon.set_alive()
    daemon.applied.clear()
    daemon.scanned.clear()
    daemon.seen.clear()
    return daemon


def _rescan(daemon: Dual) -> None:
    daemon.next_scan = daemon.t
    daemon.next_refresh = daemon.t + 3600


def _walk(daemon: Dual, spare, ticks=8, until=None) -> list[str]:
    """Шаги демона; возвращает профили сервера после каждого."""
    seen = []
    for _ in range(ticks):
        daemon.tick()
        seen.append(daemon.profile(spare))
        if until and seen[-1] == until and spare.probe_tag not in daemon._profile_trial_tags():
            break
    return seen


Dual._profile_trial_tags = lambda self: {t.probe_tag for t in self._profile_trial.values()}


def _has(daemon: Dual, text: str) -> bool:
    """Есть ли среди событий журнала такое (события хранятся как «вид: текст»)."""
    return any(text in event for event in daemon.events())


# --- сборка ------------------------------------------------------------------------------


def test_servers_only_singbox_can_run_get_a_bridge_and_the_rest_stay_on_xray(dual):
    dual.cfg.filters.max_members = 7  # все серверы подписки — в конфиг
    dual.tick()
    xray = engine.read_json(dual.paths.xray_config_file)
    sb = engine.read_json(dual.paths.singbox_config_file)
    assert sb is not None, "sing-box нужен: есть серверы, которые умеет только он"
    nodes = {node.fingerprint: node for node in dual.inventory.nodes}
    view = dual.view()
    assert {nodes[info.fingerprint].capability for info in view} == {"dual", "xray", "singbox"}
    bridges = singboxing.bridge_ports(sb)
    for info in view:
        node = nodes[info.fingerprint]
        outbound = next(item for item in xray["outbounds"] if item["tag"] == info.tag)
        if node.capability == "singbox":
            assert info.profile == "singbox:default"
            assert singboxing.bridge_variant(outbound) == "d"
            server = outbound["settings"]["servers"][0]
            assert server["port"] == bridges[(info.fingerprint, "d")]
            assert "streamSettings" not in outbound  # без метки: loopback_guard такую отбросил бы
        else:
            assert info.profile == "xray:default" and singboxing.bridge_variant(outbound) == ""
            assert outbound["protocol"] in ("vless", "vmess", "trojan")
        if node.capability == "xray":
            assert not any(fp == info.fingerprint for fp, _ in bridges)
    assert "xgwSingboxPin" not in str(xray)


def test_without_singbox_those_servers_are_left_out_and_counted(dual):
    dual.singbox_ok = False
    dual.tick()
    assert engine.read_json(dual.paths.singbox_config_file) is None
    names = {node.name for node in dual.inventory.nodes if node.fingerprint in {
        info.fingerprint for info in dual.view()}}
    assert "🇭🇰 HY" not in names and "🇸🇪 AnyTLS" not in names
    assembly = dual._assemble(None)
    assert assembly.selection.stats["core"] == 2
    assert engine.summary(assembly)["dropped"] >= 2


def test_mode_xray_keeps_singbox_out_even_when_it_is_installed(dual):
    dual.cfg.core.mode = "xray"
    dual.tick()
    assert engine.read_json(dual.paths.singbox_config_file) is None
    assert all(info.profile in ("xray:default", "xray:fragment") for info in dual.view())
    assembly = dual._assemble(None)
    assert assembly.singbox.config is None and assembly.selection.stats["core"] == 2


def test_dual_servers_get_all_their_variants_in_advance(dual):
    dual.tick()
    sb = engine.read_json(dual.paths.singbox_config_file)
    letters: dict[str, set[str]] = {}
    for (fingerprint, letter) in singboxing.bridge_ports(sb):
        letters.setdefault(fingerprint, set()).add(letter)
    nodes = {node.fingerprint: node for node in dual.inventory.nodes}
    for fingerprint, got in letters.items():
        assert got == set(singboxing.variant_letters(nodes[fingerprint].singbox, dual.cfg))


def test_a_pin_to_singbox_moves_a_dual_server_and_a_pin_to_xray_returns_it(dual):
    _start(dual)
    spare = dual.spares(capability="dual")[0]
    assert dual.profile(spare) == "xray:default"
    dual.cfg.managed.core[spare.fingerprint] = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(spare) == "singbox:default"
    outbound = next(item for item in engine.read_json(dual.paths.xray_config_file)["outbounds"]
                    if item["tag"] == spare.tag)
    assert singboxing.bridge_variant(outbound) == "d"
    dual.cfg.managed.core[spare.fingerprint] = "xray"
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(spare) == "xray:default"
    del dual.cfg.managed.core[spare.fingerprint]
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(spare) == "xray:default"  # auto: шлюз вернулся к базе


def test_a_server_only_singbox_can_run_is_dropped_when_pinned_to_xray(dual):
    dual.tick()
    victim = next(node for node in dual.inventory.nodes if node.capability == "singbox")
    dual.cfg.managed.core[victim.fingerprint] = "xray"
    dual._rebuild_asked = True
    dual.tick()
    assert victim.fingerprint not in {info.fingerprint for info in dual.view()}


# --- лестница профилей -------------------------------------------------------------------


def test_frozen_spare_climbs_the_ladder_to_the_first_profile_that_answers(dual):
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {
        "xray:default": "FROZEN", "xray:fragment": "STALL_BEFORE_BODY",
        "singbox:default": "FROZEN", "singbox:tls_fragment": "FROZEN",
        "singbox:mux_padded": "OK",
    }
    _rescan(dual)
    seen = [dual.tick() and dual.profile(spare) for _ in range(6)]
    assert seen[:5] == ["xray:fragment", "singbox:default", "singbox:tls_fragment",
                        "singbox:mux_padded", "singbox:mux_padded"]
    probed = [profile for tag, profile in dual.seen if tag == spare.probe_tag]
    assert probed[:5] == ["xray:default", "xray:fragment", "singbox:default",
                          "singbox:tls_fragment", "singbox:mux_padded"]
    assert _has(dual, "не отвечает на профиле «Xray с дроблением ClientHello» — пробую "
                      "«sing-box»")
    assert _has(dual, "не отвечает на профиле «sing-box» — пробую «sing-box с дроблением TLS»")
    assert _has(dual, "отвечает на профиле «sing-box с мультиплексированием и паддингом» — "
                      "он закреплён")
    # Всё прошло заменами outbound'ов в Xray: конфиг sing-box записан один раз (при запуске).
    configs = {json.dumps(config, sort_keys=True) for config, _reload in dual.singbox.applied}
    assert len(configs) == 1 and dual.profile(spare) == "singbox:mux_padded"
    assert dual._profile_trial == {}


def test_a_refused_connection_gets_one_try_per_core_then_waits_six_hours(dual):
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"*": "CONNECT_FAIL"}
    _rescan(dual)
    profiles_seen = [dual.tick() and dual.profile(spare) for _ in range(5)]
    assert profiles_seen[:4] == ["xray:fragment", "singbox:default", "singbox:tls_fragment",
                                 "xray:default"]
    probed = [profile for tag, profile in dual.seen if tag == spare.probe_tag]
    assert probed == ["xray:default", "xray:fragment", "singbox:default",
                      "singbox:tls_fragment"]  # без mux
    assert _has(dual, "не отвечает ни на одном профиле — возвращён «Xray»")
    applied = len(dual.applied)
    dual.t += 3600
    _rescan(dual)
    dual.tick()
    assert len(dual.applied) == applied and dual.profile(spare) == "xray:default"
    dual.t += PROFILE_RETRY
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "xray:fragment"  # новая попытка


def test_a_spare_only_singbox_runs_has_its_own_ladder(dual):
    _start(dual)
    spare = next(info for info in dual.spares(capability="singbox")
                 if dual.node(info).name.endswith("AnyTLS"))
    assert dual.profile(spare) == "singbox:default"
    dual.table[spare.probe_tag] = {"singbox:default": "FROZEN"}
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "singbox:tls_fragment"  # AnyTLS: дробление есть, mux нет
    dual.tick()
    assert dual.profile(spare) == "singbox:tls_fragment" and dual._profile_trial == {}


def test_hysteria2_has_no_ladder_because_quic_cannot_be_fragmented(dual):
    _start(dual)
    spare = next((info for info in dual.spares(capability="singbox")
                  if dual.node(info).name.endswith("HY")), None)
    if spare is None:
        pytest.skip("hysteria2 в участниках")
    dual.table[spare.probe_tag] = {"*": "FROZEN"}
    applied = len(dual.applied)
    _rescan(dual)
    dual.tick()
    assert len(dual.applied) == applied and dual.profile(spare) == "singbox:default"


def test_heavy_profile_is_checked_on_the_base_once_a_day(dual):
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"xray:default": "FROZEN"}
    _rescan(dual)
    dual.tick()
    dual.tick()
    assert dual.profile(spare) == "xray:fragment" and not dual._profile_trial
    dual.table[spare.probe_tag] = {}  # провайдер перестал блокировать
    dual.t += 12 * 3600
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "xray:fragment"
    dual.t += PROFILE_RECHECK
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "xray:default"
    dual.tick()
    assert _has(dual, "отвечает и без дробления ClientHello — оно выключено")


def test_members_are_not_moved_between_profiles(dual):
    _start(dual)
    member = next(info for info in dual.view() if info.role == "proxy")
    dual.table[member.probe_tag] = {"*": "FROZEN"}
    dual.vetted.clear()
    _rescan(dual)
    dual.tick()
    assert dual.profile(member) == member.profile and dual._profile_wanted == {}


def test_fragment_off_removes_every_fragmenting_profile(dual):
    dual.cfg.fragment.mode = "off"
    dual.tick()
    sb = engine.read_json(dual.paths.singbox_config_file)
    assert all(letter != "f" for _fp, letter in singboxing.bridge_ports(sb))
    spare = dual.spares(capability="dual", tls=True)[0]
    available = profiles.available(dual.node(spare), dual.cfg, dual._bridged_letters(
        spare.fingerprint))
    assert profiles.XRAY_FRAGMENT not in available and profiles.SB_FRAGMENT not in available


def test_a_learned_profile_survives_a_rebuild_and_a_restart(dual):
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"xray:default": "FROZEN", "xray:fragment": "FROZEN",
                                   "singbox:default": "FROZEN", "singbox:tls_fragment": "OK"}
    _rescan(dual)
    for _ in range(5):
        dual.tick()
    assert dual.profile(spare) == "singbox:tls_fragment"
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    assert dual.profile(spare) == "singbox:tls_fragment"
    again = Dual(dual.cfg, dual.paths)
    again.inventory = dual.inventory
    assert again.profile(spare) == "singbox:tls_fragment"


def test_a_dual_spare_that_answers_only_on_plain_singbox_moves_there_and_stays(dual):
    """Отчёт 0.1.12: часть серверов, которые на Xray не отвечали, ответили на обычном sing-box.
    Шлюз сам переводит такой сервер на sing-box — ступень между дроблением Xray и дроблением
    sing-box, — и профиль переживает пересборку и перезапуск демона."""
    from xgw.watch import status

    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"xray:default": "TIMEOUT", "xray:fragment": "TIMEOUT"}
    _rescan(dual)
    seen = _walk(dual, spare, until="singbox:default")
    assert seen[-1] == "singbox:default" and "singbox:tls_fragment" not in seen, seen
    assert not dual._profile_trial
    assert _has(dual, "не отвечает на профиле «Xray с дроблением ClientHello» — пробую "
                      "«sing-box»")
    assert _has(dual, "отвечает на профиле «sing-box» — он закреплён (был «Xray»)")
    # Сборка по обновлению подписки и сборка после перезапуска демона его не сбрасывают.
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    assert dual.profile(spare) == "singbox:default"
    again = Dual(dual.cfg, dual.paths)
    try:
        again.inventory = dual.inventory
        again._rebuild(None, urgent=True, reason="перезапуск")
        assert again.profile(spare) == "singbox:default"
    finally:
        again.store.close()
    # Метки: [sb] в `xgw servers`; профиль и ядро — в статусе, откуда их берёт и панель.
    snapshot = dual.status()
    entry = next(item for item in snapshot["spares"] if item["tag"] == spare.tag)
    assert entry["profile"] == "singbox:default" and entry["core"] == "sing-box"
    line = next(text for text in status.render_servers(snapshot).splitlines()
                if spare.tag in text)
    assert "[sb]" in line, line


def test_plain_singbox_is_checked_on_the_base_daily_like_the_other_learned(dual):
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"xray:default": "CONNECT_FAIL", "xray:fragment": "CONNECT_FAIL"}
    _rescan(dual)
    _walk(dual, spare, until="singbox:default")
    assert dual.profile(spare) == "singbox:default" and not dual._profile_trial
    dual.t += 12 * 3600
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "singbox:default"  # до суток не трогается
    # Сутки — проверка на базе. Xray по-прежнему не отвечает: сервер возвращается на sing-box.
    dual.t += PROFILE_RECHECK
    _rescan(dual)
    dual.tick()
    assert dual.profile(spare) == "xray:default"
    dual.tick()
    assert dual.profile(spare) == "singbox:default"
    assert _has(dual, "на профиле «Xray» не отвечает — возвращён «sing-box»")
    # Блокировка ушла: на следующей суточной проверке сервер остаётся на Xray.
    dual.table[spare.probe_tag] = {}
    dual.t += PROFILE_RECHECK
    _rescan(dual)
    dual.tick()
    dual.tick()
    assert dual.profile(spare) == "xray:default"
    assert _has(dual, "отвечает и на профиле «Xray» — он возвращён (был «sing-box»)")


def test_plain_singbox_from_a_pin_or_the_mode_is_not_kept_once_the_gateway_chooses(dual):
    """Обычный sing-box дают и настройки: `xgw core … sing-box` и [core] mode = "sing-box". После
    `xgw core … auto` и возврата mode = "auto" сервер — снова на базе, а не «выученный»."""
    _start(dual)
    spare = dual.spares(capability="dual")[0]
    dual.cfg.managed.core[spare.fingerprint] = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(spare) == "singbox:default"
    del dual.cfg.managed.core[spare.fingerprint]  # xgw core … auto
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(spare) == "xray:default"
    duals = [info for info in dual.view() if dual.node(info).capability == "dual"]
    dual.cfg.core.mode = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    assert duals and all(dual.profile(info) == "singbox:default" for info in duals)
    dual.cfg.core.mode = "auto"
    dual._rebuild_asked = True
    dual.tick()
    assert all(dual.profile(info) == "xray:default" for info in duals)


def test_without_the_core_snapshot_plain_singbox_is_not_taken_for_learned(dual):
    """Обновление с 0.1.12: снимка настроек ядра в базе нет — обычный sing-box у сервера с базой
    Xray считается следом настроек, как в 0.1.12. Снимок пишет только применённая сборка."""
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"xray:default": "TIMEOUT", "xray:fragment": "TIMEOUT"}
    _rescan(dual)
    _walk(dual, spare, until="singbox:default")
    assert dual.profile(spare) == "singbox:default"
    assert json.loads(dual.store.get_meta(profiles.CORE_META)) == {"mode": "auto", "pins": {}}
    dual.store.set_meta(profiles.CORE_META, "")
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    assert dual.profile(spare) == "xray:default"
    assert dual.store.get_meta(profiles.CORE_META)  # записан заново
    # `xgw generate` пишет конфиг в отдельный файл — снимок он не трогает.
    assembly = dual._assemble(None)
    dual.store.set_meta(profiles.CORE_META, "")
    engine.persist(dual.paths, assembly, {}, applied=False)
    assert dual.store.get_meta(profiles.CORE_META) == ""


# --- sing-box занят трафиком --------------------------------------------------------------


def test_new_sing_box_config_waits_while_a_member_goes_through_it(dual):
    dual.tick()
    dual.set_alive()
    member = next(info for info in dual.view() if info.role == "proxy"
                  and dual.node(info).capability == "dual")
    dual.cfg.managed.core[member.fingerprint] = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    assert dual.profile(member) == "singbox:default"
    before = engine.read_json(dual.paths.singbox_config_file)
    # Состав серверов sing-box изменился: пропал сервер подписки.
    gone = next(node for node in dual.inventory.nodes
                if node.capability == "singbox" and node.fingerprint != member.fingerprint)
    dual.inventory = engine.Inventory(
        [node for node in dual.inventory.nodes if node is not gone],
        dual.inventory.quotas, True,
    )
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    assert engine.read_json(dual.paths.singbox_config_file) == before  # рабочий не тронут
    assert dual.paths.singbox_pending_file.exists()
    assert dual.profile(member) == "singbox:default"  # участник на мосту, который уже есть
    # Срочно — применяется сразу.
    dual._rebuild(None, urgent=True, reason="авария")
    assert engine.read_json(dual.paths.singbox_config_file) != before
    assert not dual.paths.singbox_pending_file.exists()


def test_deferred_sing_box_config_is_applied_in_the_restart_window(dual):
    import datetime

    dual.tick()
    dual.set_alive()
    member = next(info for info in dual.view() if info.role == "proxy"
                  and dual.node(info).capability == "dual")
    dual.cfg.managed.core[member.fingerprint] = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    dual.inventory = engine.Inventory(
        [node for node in dual.inventory.nodes if node.capability != "singbox"],
        dual.inventory.quotas, True,
    )
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    assert dual.paths.singbox_pending_file.exists()
    dual.t += 60
    dual.tick()
    assert dual.paths.singbox_pending_file.exists()  # днём конфиг ждёт
    dual.now_time = lambda: datetime.time(4, 30)
    dual.t += 60
    dual.tick()
    assert not dual.paths.singbox_pending_file.exists()


def test_xray_is_not_pointed_at_bridges_that_do_not_exist_yet(dual):
    """Пока новый конфиг sing-box ждёт, Xray ссылается только на мосты работающего."""
    dual.tick()
    dual.set_alive()
    member = next(info for info in dual.view() if info.role == "proxy"
                  and dual.node(info).capability == "dual")
    dual.cfg.managed.core[member.fingerprint] = "sing-box"
    dual._rebuild_asked = True
    dual.tick()
    ports = set(singboxing.bridge_ports(engine.read_json(dual.paths.singbox_config_file)).values())
    extra = _inventory([*LINKS, "anytls://pw2@new.example:443?sni=new.example#%F0%9F%87%AB%F0%9F%87%AE%20New"])
    dual.inventory = extra
    dual._rebuild(None, urgent=False, reason="обновление подписки")
    xray = engine.read_json(dual.paths.xray_config_file)
    used = {
        server["port"] for outbound in xray["outbounds"]
        if singboxing.bridge_variant(outbound)
        for server in outbound["settings"]["servers"]
    }
    assert used <= ports, "Xray сослался на мост, которого в работающем sing-box нет"
    assert "New" not in " ".join(
        node.name for node in dual.inventory.nodes if node.fingerprint in {
            info.fingerprint for info in dual.view()})


# --- слежение за sing-box ------------------------------------------------------------------


def test_dead_singbox_is_restarted(dual):
    _start(dual)
    dual.singbox.is_alive = False
    dual.t += 20
    dual.tick()
    assert dual.singbox.restarts == 1 and dual.singbox.is_alive
    assert _has(dual, "sing-box не отвечал — служба перезапущена")
    assert dual._singbox_down == 0 and not dual._singbox_failed


def test_singbox_that_will_not_start_is_rolled_back_then_servers_move_to_xray(dual):
    _start(dual)
    dual.singbox.is_alive = False
    dual.singbox.restart_error = "не запустился"
    dual.singbox.rollback_mode = "unchanged"  # откатывать нечего
    dual.t += 20
    dual.tick()
    assert not dual._singbox_failed and dual.singbox.restarts == 1
    dual.t += 20
    dual.tick()
    assert dual.singbox.rollbacks and dual._singbox_failed
    assert _has(dual, "sing-box не поднимается — серверы переведены на Xray")
    assert all(info.profile in ("xray:default", "xray:fragment") for info in dual.view())
    # Серверы только для sing-box ушли из конфига, а сам его конфиг остался — на случай починки.
    assert engine.read_json(dual.paths.singbox_config_file) is not None
    # Пока он не заработает, раз в SINGBOX_RETRY пробуем.
    restarts = dual.singbox.restarts
    dual.t += 20
    dual.tick()
    assert dual.singbox.restarts == restarts
    dual.singbox.restart_error = None
    dual.t += SINGBOX_RETRY
    dual.tick()
    assert not dual._singbox_failed and _has(dual, "sing-box снова работает")
    assert any(info.profile == "singbox:default" for info in dual.view())


def test_a_good_rollback_ends_the_incident(dual):
    _start(dual)
    dual.singbox.is_alive = False
    dual.singbox.restart_error = "не запустился"
    dual.singbox.rollback_mode = "rollback"
    for _ in range(2):
        dual.t += 20
        dual.tick()
    assert not dual._singbox_failed and _has(dual, "откатил конфиг на last-good")


def test_status_shows_core_profile_and_protocol(dual):
    _start(dual)
    snapshot = dual.status()
    entries = [*snapshot["members"], *snapshot["spares"]]
    assert {entry["core"] for entry in entries} == {"xray", "sing-box"}
    assert all("profile" in entry and "protocol" in entry for entry in entries)
    assert snapshot["singbox"]["bridged"] == sum(1 for e in entries if e["core"] == "sing-box")
    assert snapshot["singbox"]["mode"] == "auto" and snapshot["singbox_pending"] is False
    from xgw.watch import status

    text = status.render_servers(snapshot)
    assert "[sb]" in text and "[xray]" in text


# --- настройки и закрепление -------------------------------------------------------------


def test_core_pin_is_stored_per_fingerprint_and_auto_is_not_stored(tmp_path):
    path = tmp_path / "panel.json"
    assert managed.set_core(path, ["aaaa1111"], "sing-box") is True
    assert managed.set_core(path, ["aaaa1111"], "sing-box") is False
    assert managed.load(path)[0]["core"] == {"aaaa1111": "sing-box"}
    assert managed.set_core(path, ["aaaa1111"], "xray") is True
    assert managed.set_core(path, ["aaaa1111"], "auto") is True
    assert managed.load(path)[0]["core"] == {}
    with pytest.raises(managed.ManagedError):
        managed.set_core(path, ["не отпечаток"], "xray")
    with pytest.raises(managed.ManagedError):
        managed.set_core(path, ["aaaa1111"], "mihomo")
    atomic_write_json(path, {"core": {"aaaa1111": "xray", "bbbb2222": "mihomo", "x": "xray"}})
    assert managed.load(path)[0]["core"] == {"aaaa1111": "xray"}


def test_core_section_of_the_config(tmp_path):
    from xgw import config

    path = tmp_path / "config.toml"
    path.write_text('[core]\nmode = "sing-box"\nmux_padding = false\nport_base = 23001\n',
                    encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.core.mode == "sing-box" and cfg.core.mux_padding is False
    assert cfg.core.port_base == 23001 and cfg.core.api_port == 10087 and not warnings
    path.write_text('[core]\nmode = "mihomo"\nport_base = 80\napi_port = 99999\n', encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.core.mode == "auto" and cfg.core.port_base == 22001 and cfg.core.api_port == 10087
    assert len(warnings) == 3 and "core.mode" in warnings[0]
    assert config.Config().core.mode == "auto" and config.Config().core.mux_padding is True


def test_profile_rules_for_the_five_profiles():
    cfg = Config()
    dual_node = raw_to_node(parse_links_text(links.VLESS_WS, "t")[0][0], "t")
    letters = {"d", "f", "m"}
    avail = profiles.available(dual_node, cfg, letters)
    assert avail == [profiles.XRAY_DEFAULT, profiles.XRAY_FRAGMENT, profiles.SB_DEFAULT,
                     profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.base(cfg, avail) == profiles.XRAY_DEFAULT
    cfg.fragment.mode = "always"
    assert profiles.base(cfg, avail) == profiles.XRAY_FRAGMENT
    cfg.fragment.mode = "auto"
    cfg.managed.core[dual_node.fingerprint] = "sing-box"
    avail = profiles.available(dual_node, cfg, letters)
    assert avail == [profiles.SB_DEFAULT, profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.base(cfg, avail) == profiles.SB_DEFAULT
    cfg.managed.core[dual_node.fingerprint] = "xray"
    assert profiles.available(dual_node, cfg, letters) == [
        profiles.XRAY_DEFAULT, profiles.XRAY_FRAGMENT]
    # Без заведённых вариантов sing-box остаются только профили Xray.
    cfg.managed.core.clear()
    assert profiles.available(dual_node, cfg, set()) == [
        profiles.XRAY_DEFAULT, profiles.XRAY_FRAGMENT]
    # Обученный профиль сохраняется, пока он допустим; настроечный (база) следует за настройками.
    assert profiles.resolve(dual_node, cfg, letters, current=profiles.SB_MUX) == profiles.SB_MUX
    # Обычный sing-box у сервера с базой Xray (0.1.13) — выученный, пока ядро сервера в
    # настройках то же, что при прошлой сборке; иначе его дало закрепление — сервер на базу.
    assert profiles.resolve(dual_node, cfg, letters, current=profiles.SB_DEFAULT) == (
        profiles.SB_DEFAULT)
    assert profiles.resolve(dual_node, cfg, letters, current=profiles.SB_DEFAULT,
                            same_pin=False) == profiles.XRAY_DEFAULT
    assert profiles.resolve(dual_node, cfg, letters, current=profiles.SB_MUX,
                            same_pin=False) == profiles.SB_MUX  # прочие выученные — как в 0.1.12
    cfg.core.mode = "xray"
    cfg.managed.core[dual_node.fingerprint] = "xray"
    assert profiles.resolve(dual_node, cfg, letters, current=profiles.SB_MUX) == (
        profiles.XRAY_DEFAULT)
    assert profiles.core_of(profiles.SB_FRAGMENT) == "sing-box"
    assert profiles.label(profiles.SB_MUX) == "sb+mux"


def test_ladder_orders_and_filters_the_steps():
    avail = [profiles.XRAY_DEFAULT, profiles.XRAY_FRAGMENT, profiles.SB_FRAGMENT, profiles.SB_MUX]
    base = profiles.XRAY_DEFAULT
    assert profiles.ladder("FROZEN", base, base, avail) == [
        profiles.XRAY_FRAGMENT, profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.ladder("CONNECT_FAIL", base, base, avail) == [
        profiles.XRAY_FRAGMENT, profiles.SB_FRAGMENT]
    # На ступени XRAY_FRAGMENT: сначала база (вдруг сломался сам профиль), потом дальше.
    assert profiles.ladder("FROZEN", profiles.XRAY_FRAGMENT, base, avail) == [
        profiles.XRAY_DEFAULT, profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.ladder("FROZEN", profiles.SB_MUX, base, avail) == [profiles.XRAY_DEFAULT]
    assert profiles.ladder("TIMEOUT", base, base, [profiles.XRAY_DEFAULT]) == []
    # 0.1.13: обычный sing-box — между дроблением Xray и дроблением sing-box, для обоих вердиктов.
    full = [profiles.XRAY_DEFAULT, profiles.XRAY_FRAGMENT, profiles.SB_DEFAULT,
            profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.ladder("STALL_BEFORE_BODY", base, base, full) == [
        profiles.XRAY_FRAGMENT, profiles.SB_DEFAULT, profiles.SB_FRAGMENT, profiles.SB_MUX]
    assert profiles.ladder("TIMEOUT", base, base, full) == [
        profiles.XRAY_FRAGMENT, profiles.SB_DEFAULT, profiles.SB_FRAGMENT]
    # На обычном sing-box перестал отвечать: сначала база, потом дальше по лестнице.
    assert profiles.ladder("CONNECT_FAIL", profiles.SB_DEFAULT, base, full) == [
        profiles.XRAY_DEFAULT, profiles.SB_FRAGMENT]
    # У сервера только для sing-box обычный sing-box — база: лестница с неё не начинается заново.
    only_sb = [profiles.SB_DEFAULT, profiles.SB_FRAGMENT]
    assert profiles.ladder("FROZEN", profiles.SB_DEFAULT, profiles.SB_DEFAULT, only_sb) == [
        profiles.SB_FRAGMENT]


def test_core_settings_snapshot_tells_a_pin_from_learning():
    cfg = Config()
    fingerprint = "aaaa1111bbbb2222"
    saved = profiles.core_settings(cfg)
    assert saved == {"mode": "auto", "pins": {}}
    assert profiles.pin_unchanged(cfg, saved, fingerprint)
    assert not profiles.pin_unchanged(cfg, None, fingerprint)  # снимка нет — как в 0.1.12
    cfg.managed.core[fingerprint] = "sing-box"
    assert not profiles.pin_unchanged(cfg, saved, fingerprint)
    assert profiles.pin_unchanged(cfg, saved, "cccc3333dddd4444")  # чужое закрепление не в счёт
    pinned = profiles.core_settings(cfg)
    cfg.managed.core.clear()
    cfg.core.mode = "sing-box"
    assert profiles.pin_unchanged(cfg, pinned, fingerprint)  # и так, и так — sing-box
    assert not profiles.pin_unchanged(cfg, saved, "cccc3333dddd4444")
    assert not profiles.pin_unchanged(cfg, {"mode": "auto", "pins": "сломано"}, fingerprint)


def test_builder_info_reads_the_profile_from_the_outbound(dual):
    dual.tick()
    xray = engine.read_json(dual.paths.xray_config_file)
    for info in builder.applied_nodes(xray, dual.inventory.nodes):
        outbound = next(item for item in xray["outbounds"] if item["tag"] == info.tag)
        assert info.profile == builder.outbound_profile(outbound)
        assert info.fragment == (info.profile == "xray:fragment")


# --- массовая блокировка и квота ---------------------------------------------------------


def test_when_nothing_answers_other_cores_and_transports_are_scanned_first(dual):
    """ТЗ 4.2: в ALL_DEAD первыми проверяются запасные не на том ядре и не на том транспорте, на
    каком упали участники, — но класс серверов по-прежнему главнее."""
    dual.cfg.filters.max_members = 1
    _start(dual)
    (member,) = [info for info in dual.view() if info.role == "proxy"]
    nodes = {node.fingerprint: node for node in dual.inventory.nodes}

    def kind(info):
        transport = "udp" if nodes[info.fingerprint].protocol == "hysteria2" else "tcp"
        return profiles.core_of(info.profile), transport

    dual.machine.state = type(dual.machine.state)("ALL_DEAD")
    dual.scan_queue.clear()
    dual._queue_scan(dual.view(), dual.t, everything=True)
    by_probe = {info.probe_tag: info for info in dual.view()}
    flags = [kind(by_probe[tag]) != kind(member) for tag in dual.scan_queue]
    assert any(flags) and not all(flags)  # в подписке есть и другое ядро, и то же самое
    assert flags == sorted(flags, reverse=True), "альтернативные должны идти первыми"
    # В обычном состоянии порядок прежний: по классу и отпечатку, без предпочтений.
    dual.machine.state = type(dual.machine.state)("HEALTHY")
    dual.scan_queue.clear()
    dual._queue_scan(dual.view(), dual.t)
    order = [by_probe[tag].fingerprint for tag in dual.scan_queue]
    assert order == sorted(order)


def test_limited_subscriptions_do_not_cross_to_the_other_core_in_the_background(dual):
    """ТЗ 4.2: серверы с лимитом трафика не перебирают ядра в фоне — каждая проба тратит
    квоту. Дробление в своём ядре (как в 0.1.11) остаётся."""
    dual.source.quotas = {"main": {"upload": 0, "download": 10**9, "total": 10**12}}
    _start(dual)
    spare = dual.spares(capability="dual", tls=True)[0]
    dual.table[spare.probe_tag] = {"*": "FROZEN"}
    _rescan(dual)
    seen = [dual.tick() and dual.profile(spare) for _ in range(4)]
    assert seen[0] == "xray:fragment"  # дробление Xray — пробуется
    assert all(profile.startswith("xray:") for profile in seen), seen  # на sing-box — нет
    probed = {profile for tag, profile in dual.seen if tag == spare.probe_tag}
    assert probed <= {"xray:default", "xray:fragment"}


def test_status_has_a_line_about_the_second_core():
    from xgw.watch import status

    assert status.render_singbox({}) == ""
    assert "выключен" in status.render_singbox({"mode": "xray"})
    assert "не установлен" in status.render_singbox({"mode": "auto", "installed": False})
    base = {"mode": "auto", "installed": True, "version": "1.14.3", "expected": True,
            "alive": True, "failed": False, "bridged": 3}
    assert status.render_singbox(base) == "sing-box 1.14.3: работает, серверов через него: 3"
    assert "ждёт окна" in status.render_singbox(base, pending=True)
    assert "НЕ ОТВЕЧАЕТ — демон" in status.render_singbox({**base, "alive": False})
    assert "переведены на него" in status.render_singbox({**base, "failed": True})
    assert "серверов для него пока нет" in status.render_singbox({**base, "expected": False})
