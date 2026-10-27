"""Второе ядро (0.1.12): конфиг sing-box, мост к Xray, применение, загрузка и обновление.
Ядро не нужно: службы подменены, адреса и ключи — фейковые."""

import hashlib
import http.server
import io
import json
import tarfile
import threading
from pathlib import Path

import links
import pytest

from xgw.apply.singbox import SingboxCore, SingboxService
from xgw.config import Config
from xgw.generator import profiles, singbox
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.sbcore import binary as sbbinary
from xgw.xraycore.binary import BinaryError
from xgw.xraycore.service import XrayServiceError

UUID = "2dd61d93-75d8-4da4-ac0e-6aece7eac365"
KEY = "yAnz5TF%2BlXXJte14tji3zlMNq%2Bhd2rYUIgJBgB3fBmk%3D"
PUB = "xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg%3D"
HY2 = "hysteria2://s3cret@203.0.113.50:443/?sni=hy.example&obfs=salamander&obfs-password=ob#HY"
ANYTLS = "anytls://pw@any.example:443?sni=any.example#AnyTLS"
WG = f"wireguard://{KEY}@203.0.113.51:51820?publickey={PUB}&address=10.0.0.2%2F32#WG"
STLS = ("ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.52:443?plugin=shadow-tls"
        "%3Bhost%3Dx.example%3Bpassword%3Dpp%3Bversion%3D3#STLS")


def _nodes(*link_list):
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "t")
    return [raw_to_node(raw, "t") for raw in raws]


def _by_name(nodes, name):
    return next(node for node in nodes if node.name.endswith(name))


# --- что умеет сервер ---------------------------------------------------------------------


def test_variants_depend_on_what_the_server_can_do():
    cfg = Config()
    nodes = _nodes(links.VLESS_WS, links.VLESS_REALITY, links.TROJAN, links.SS_PLAIN, HY2, ANYTLS)
    letters = {node.name: singbox.variant_letters(node.singbox, cfg) for node in nodes}
    assert letters["🇩🇪 DE-1"] == ["d", "f", "m"]  # TLS поверх TCP, без flow: все три
    assert letters["🇳🇱 NL-1"] == ["d", "f"]  # Vision: мультиплексирование нельзя
    assert letters["SS-2"] == ["d", "m"]  # без TLS резать нечего
    assert letters["HY"] == ["d"] and letters["AnyTLS"] == ["d", "f"]  # QUIC дробить нельзя
    cfg.core.mux_padding = False
    assert singbox.variant_letters(_by_name(nodes, "DE-1").singbox, cfg) == ["d", "f"]
    cfg.fragment.mode = "off"
    assert singbox.variant_letters(_by_name(nodes, "DE-1").singbox, cfg) == ["d"]


def test_fragment_variant_cuts_the_hello_and_waits_less_than_the_default():
    cfg = Config()
    plan = singbox.build(cfg, _nodes(links.TROJAN), {})
    node = _nodes(links.TROJAN)[0]
    outbounds = {item["tag"]: item for item in plan.config["outbounds"]}
    fragment = outbounds[singbox.tag_out(node.fingerprint, "f")]["tls"]
    assert fragment["fragment"] is True and fragment["record_fragment"] is True
    assert fragment["fragment_fallback_delay"] == singbox.FRAGMENT_DELAY
    mux = outbounds[singbox.tag_out(node.fingerprint, "m")]
    assert mux["multiplex"] == {"enabled": True, "protocol": "h2mux", "padding": True}
    assert mux["tls"]["record_fragment"] is True and "fragment" not in mux["tls"]
    default = outbounds[singbox.tag_out(node.fingerprint, "d")]
    assert "fragment" not in default["tls"] and "multiplex" not in default


# --- конфиг sing-box -----------------------------------------------------------------------


def test_config_has_a_bridge_per_variant_and_nothing_else():
    cfg = Config()
    nodes = _nodes(links.TROJAN, HY2)
    plan = singbox.build(cfg, nodes, {"hy.example": ["203.0.113.50"], "unrelated": ["1.1.1.1"]})
    config = plan.config
    assert [item["tag"] for item in config["inbounds"]] == sorted(
        item["tag"] for item in config["inbounds"])
    assert all(item["listen"] == "127.0.0.1" and item["type"] == "socks"
               for item in config["inbounds"])
    assert all(item["routing_mark"] == cfg.capture.mark_bypass for item in config["outbounds"])
    rules = config["route"]["rules"]
    assert rules[-1] == {"action": "reject"} and len(rules) == len(config["inbounds"]) + 1
    assert {rule["outbound"] for rule in rules[:-1]} == {
        item["tag"] for item in config["outbounds"]}
    # Адреса серверов-доменов разрешены заранее; чужие домены в конфиг не попадают.
    assert config["dns"]["servers"][0]["predefined"] == {}
    assert config["route"]["default_domain_resolver"] == "hosts"
    clash = config["experimental"]["clash_api"]
    assert clash["external_controller"] == f"127.0.0.1:{cfg.core.api_port}" and clash["secret"]
    assert "insecure" not in json.dumps(config)


def test_hosts_of_domain_servers_are_predefined():
    cfg = Config()
    nodes = _nodes(links.VLESS_WS)
    plan = singbox.build(cfg, nodes, {"de.example.com": ["203.0.113.11"], "other": ["1.1.1.1"]})
    assert plan.config["dns"]["servers"][0]["predefined"] == {"de.example.com": ["203.0.113.11"]}


def test_ports_password_and_secret_survive_a_rebuild():
    cfg = Config()
    nodes = _nodes(links.TROJAN, HY2)
    first = singbox.build(cfg, nodes, {})
    again = singbox.build(cfg, list(reversed(nodes)), {}, previous=first.config)
    assert again.ports == first.ports and again.password == first.password
    assert singbox.clash_secret(again.config) == singbox.clash_secret(first.config)
    assert again.config == first.config  # порядок серверов на результат не влияет
    # Новый сервер получает новые порты, а прежние остаются на месте.
    more = singbox.build(cfg, [*nodes, *_nodes(ANYTLS)], {}, previous=first.config)
    assert all(more.ports[key] == port for key, port in first.ports.items())
    assert len(set(more.ports.values())) == len(more.ports)
    assert min(more.ports.values()) >= cfg.core.port_base


def test_busy_ports_are_skipped():
    cfg = Config()
    nodes = _nodes(HY2)
    taken = {cfg.core.port_base, cfg.core.port_base + 1}
    plan = singbox.build(cfg, nodes, {}, avoid=taken)
    assert not set(plan.ports.values()) & taken


def test_servers_xray_only_and_skipped_ones_are_not_in_the_config():
    cfg = Config()
    nodes = _nodes(links.VLESS_XHTTP, HY2)
    plan = singbox.build(cfg, nodes, {})
    assert {fp for fp, _ in plan.ports} == {nodes[1].fingerprint}
    assert singbox.build(cfg, _nodes(links.VLESS_XHTTP), {}) is None  # вести через sing-box некого
    skipped = singbox.build(cfg, nodes, {}, skip={nodes[1].fingerprint})
    assert skipped is None


def test_wireguard_is_an_endpoint_and_chains_are_renamed_per_variant():
    cfg = Config()
    plan = singbox.build(cfg, _nodes(WG, STLS), {})
    config = plan.config
    assert [item["type"] for item in config["endpoints"]] == ["wireguard"]
    assert config["endpoints"][0]["routing_mark"] == cfg.capture.mark_bypass
    node = _nodes(STLS)[0]
    main = next(item for item in config["outbounds"] if item["tag"] == singbox.tag_out(
        node.fingerprint, "d"))
    chain = next(item for item in config["outbounds"] if item["type"] == "shadowtls")
    assert main["detour"] == chain["tag"] and chain["tag"].startswith("sb-out-")
    assert chain["routing_mark"] == cfg.capture.mark_bypass
    only_wireguard = singbox.build(cfg, _nodes(WG), {}).config
    assert only_wireguard["outbounds"]  # sing-box без outbound'ов не стартует


def test_bridge_outbound_is_recognised_by_the_login_it_carries():
    outbound = singbox.bridge_outbound(22005, "f", "pw")
    assert outbound["protocol"] == "socks" and "streamSettings" not in outbound  # без метки
    assert singbox.bridge_variant(outbound) == "f"
    assert singbox.bridge_variant({"protocol": "vless", "settings": {}}) == ""
    foreign = singbox.bridge_outbound(22005, "f", "pw")
    foreign["settings"]["servers"][0]["address"] = "203.0.113.1"
    assert singbox.bridge_variant(foreign) == ""
    cfg = Config()
    plan = singbox.build(cfg, _nodes(HY2), {})
    assert singbox.bridge_ports(plan.config) == plan.ports
    assert singbox.bridge_password(plan.config) == plan.password


def test_profile_letters_and_tags_agree():
    assert profiles.LETTERS == {
        profiles.SB_DEFAULT: "d", profiles.SB_FRAGMENT: "f", profiles.SB_MUX: "m"}
    assert singbox.tag_in("0123abcd", "m") == "sb-in-0123abcd-m"
    assert singbox.tag_out("0123abcd", "m") == "sb-out-0123abcd-m"


def test_dual_server_ladder_tries_plain_singbox_before_its_fragmenting():
    """0.1.13: у сервера, которого умеют оба ядра, обычный sing-box (вариант «d», заведён в
    sing-box заранее) — ступень лестницы и выученный профиль, а не только база серверов sing-box."""
    cfg = Config()
    node = _nodes(links.TROJAN)[0]
    letters = singbox.variant_letters(node.singbox, cfg)
    assert "d" in letters
    avail = profiles.available(node, cfg, letters)
    base = profiles.base(cfg, avail)
    assert base == profiles.XRAY_DEFAULT
    for verdict in profiles.TRIGGER_VERDICTS:
        steps = profiles.ladder(verdict, base, base, avail)
        # Сначала ступени Xray (с 0.1.18 после дробления — ещё split), затем обычный sing-box и
        # только потом его дробление.
        before = steps[: steps.index(profiles.SB_DEFAULT)]
        assert profiles.XRAY_FRAGMENT in before
        assert all(step.startswith("xray:") for step in before), steps
        assert steps.index(profiles.SB_DEFAULT) < steps.index(profiles.SB_FRAGMENT)
        assert steps.index(profiles.SB_FRAGMENT) == steps.index(profiles.SB_DEFAULT) + 1
    learned = profiles.resolve(node, cfg, letters, current=profiles.SB_DEFAULT)
    assert learned == profiles.SB_DEFAULT
    # Без варианта «d» в работающем sing-box профиль недоступен — сервер на базе.
    assert profiles.resolve(node, cfg, {"f"}, current=profiles.SB_DEFAULT) == base
    # Закреплён Xray — sing-box недоступен вовсе.
    cfg.managed.core[node.fingerprint] = "xray"
    assert profiles.resolve(node, cfg, letters, current=profiles.SB_DEFAULT) == base


def test_plain_singbox_is_labelled_sb_everywhere():
    """Выученный обычный sing-box показывается так же, как у серверов только для sing-box:
    «[sb]» в `xgw servers`, «sb» на странице статуса, «sing-box» в панели."""
    from xgw.watch import status, status_page

    entry = {"tag": "spare-de-0123abcd", "profile": profiles.SB_DEFAULT, "protocol": "trojan"}
    assert status._fragment(entry) == " [sb]"
    assert status_page._core(entry) == "trojan · sb"
    app = (Path(__file__).resolve().parents[1] / "src/xgw/ui/app.js").read_text(encoding="utf-8")
    hint = app.split('"singbox:default": ["sing-box", "', 1)[1].split('"]', 1)[0]
    assert "умеют оба ядра" in hint and "сам" in hint


# --- применение конфига --------------------------------------------------------------------


class FakeService(SingboxService):
    def __init__(self, paths=None):
        self.active = False
        self.calls: list[str] = []
        self.fail: str | None = None
        self.on_start = None  # что сделать при запуске (открыть порты)

    def start(self):
        self.calls.append("start")
        if self.fail:
            raise XrayServiceError(self.fail)
        self.active = True
        if self.on_start:
            self.on_start()

    def stop(self):
        self.calls.append("stop")
        self.active = False

    def restart(self):
        self.calls.append("restart")
        if self.fail:
            raise XrayServiceError(self.fail)
        self.active = True
        if self.on_start:
            self.on_start()

    def reload(self):
        self.calls.append("reload")
        if self.fail:
            raise XrayServiceError(self.fail)

    def is_active(self):
        return self.active


@pytest.fixture()
def core(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    service = FakeService()
    instance = SingboxCore(cfg, paths, service, validator=lambda config: (True, ""),
                           wait_seconds=0.3)
    instance.service_fake = service
    monkeypatch.setattr("xgw.apply.singbox._listening", lambda port: True)
    return instance


def _config(extra=None):
    config = singbox.build(Config(), _nodes(HY2), {}).config
    return {**config, **(extra or {})}


def test_first_config_starts_sing_box_and_the_same_one_changes_nothing(core):
    config = _config()
    assert core.apply(config, reload=False).mode == "deferred"
    assert core.paths.singbox_pending_file.exists() and not core.paths.singbox_config_file.exists()
    outcome = core.apply(config, reload=True)
    assert outcome.mode == "started" and core.service_fake.calls == ["start"]
    assert core.read() == config and not core.paths.singbox_pending_file.exists()
    assert core.apply(config, reload=True).mode == "unchanged"
    assert core.apply(config, reload=False).mode == "unchanged"


def test_changed_config_is_reloaded_not_restarted_and_kept_as_last_good(core):
    first, second = _config(), _config({"log": {"level": "error"}})
    core.apply(first, reload=True)
    assert core.apply(second, reload=False).mode == "deferred"
    assert core.read() == first  # отложенный конфиг рабочий не трогает
    assert core.apply(second, reload=True).mode == "reloaded"
    assert core.service_fake.calls == ["start", "reload"]
    assert json.loads(core.paths.singbox_last_good_file.read_text(encoding="utf-8")) == first


def test_config_sing_box_check_refuses_is_never_written(core):
    core.validator = lambda config: (False, "unknown field")
    outcome = core.apply(_config(), reload=True)
    assert outcome.mode == "rejected" and "unknown field" in outcome.detail
    assert core.read() is None and core.service_fake.calls == []


def test_ports_that_do_not_open_roll_back_to_last_good(core, monkeypatch):
    first = _config()
    core.apply(first, reload=True)
    monkeypatch.setattr("xgw.apply.singbox._listening", lambda port: False)
    second = _config({"log": {"level": "error"}})
    outcome = core.apply(second, reload=True)
    assert outcome.mode == "failed"  # откат тоже не поднял порты
    monkeypatch.undo()
    assert core.read() == first  # на диске — прежний рабочий конфиг


def test_rollback_works_when_the_old_config_does_come_up(core, monkeypatch):
    first = _config()
    core.apply(first, reload=True)
    state = {"opened": False}
    monkeypatch.setattr("xgw.apply.singbox._listening", lambda port: state["opened"])
    core.service_fake.on_start = lambda: state.update(opened=True)
    # Новый конфиг портов не открывает (reload ничего не делает), а прежний после рестарта — да.
    outcome = core.apply(_config({"log": {"level": "error"}}), reload=True)
    assert outcome.mode == "rollback" and core.read() == first
    assert core.service_fake.calls[-1] == "restart"


def test_service_that_will_not_start_is_reported(core):
    core.service_fake.fail = "systemctl start: ошибка"
    outcome = core.apply(_config(), reload=True)
    assert outcome.mode == "failed" and "ошибка" in outcome.detail


def test_no_servers_for_sing_box_stops_it_when_allowed(core):
    core.apply(_config(), reload=True)
    assert core.apply(None, reload=False).mode == "deferred" and core.read() is not None
    assert core.apply(None, reload=True).mode == "removed"
    assert core.read() is None and core.service_fake.calls[-1] == "stop"
    assert core.apply(None, reload=True).mode == "unchanged"


def test_explicit_rollback_returns_the_previous_config(core):
    first, second = _config(), _config({"log": {"level": "error"}})
    core.apply(first, reload=True)
    core.apply(second, reload=True)
    assert core.rollback("тест").mode == "rollback" and core.read() == first
    assert core.rollback("ещё раз").mode == "unchanged"  # теперь они совпали


class _Api(http.server.BaseHTTPRequestHandler):
    secret = "s3cret"

    def do_GET(self):
        sent = self.headers.get("Authorization")
        ok = self.path == "/version" and sent == f"Bearer {self.secret}"
        self.send_response(200 if ok else 401)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_alive_asks_the_clash_api_with_the_secret(core):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        core.cfg.core.api_port = server.server_address[1]
        config = _config()
        config["experimental"]["clash_api"]["secret"] = _Api.secret
        core.apply(config, reload=True)
        assert core.alive()
        config["experimental"]["clash_api"]["secret"] = "wrong"
        singbox_path = core.paths.singbox_config_file
        singbox_path.write_text(json.dumps(config), encoding="utf-8")
        assert not core.alive()  # неверный секрет API
        core.service_fake.active = False
        singbox_path.write_text(json.dumps(_config()), encoding="utf-8")
        assert not core.alive()  # служба не запущена
    finally:
        server.shutdown()


# --- загрузка бинарника --------------------------------------------------------------------


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class _Result:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status = body, status


def _release(archive: bytes, digest: str | None = None) -> sbbinary.Release:
    name = sbbinary.asset_name("v1.14.3", "linux", "x86_64")
    sha = hashlib.sha256(archive).hexdigest() if digest is None else digest
    return sbbinary.Release("v1.14.3", {name: ("https://example.invalid/a.tar.gz", sha)})


def test_download_verifies_sha_and_extracts_only_the_binary(tmp_path, monkeypatch):
    archive = _archive({
        "sing-box-1.14.3-linux-amd64/sing-box": b"\x7fELF-binary",
        "sing-box-1.14.3-linux-amd64/libcronet.so": b"lib",
        "../evil": b"x",
    })
    monkeypatch.setattr("xgw.sbcore.binary.platform_pair", lambda: ("linux", "x86_64"))
    digest = hashlib.sha256(archive).hexdigest()
    monkeypatch.setitem(sbbinary.PINNED_SHA256, ("linux", "x86_64"), digest)
    monkeypatch.setattr("xgw.fetch.fetch_url", lambda url, **kw: _Result(archive))
    tag, path = sbbinary.download_release(tmp_path / "out", "1.14.3", release=_release(archive))
    assert tag == "v1.14.3" and path.read_bytes() == b"\x7fELF-binary"
    assert path.stat().st_mode & 0o111
    assert sorted(item.name for item in (tmp_path / "out").iterdir()) == ["sing-box"]
    assert not (tmp_path / "evil").exists()


def test_download_refuses_a_wrong_hash_a_second_opinion_and_a_missing_binary(tmp_path, monkeypatch):
    archive = _archive({"x/sing-box": b"bin"})
    monkeypatch.setattr("xgw.sbcore.binary.platform_pair", lambda: ("linux", "x86_64"))
    monkeypatch.setattr("xgw.fetch.fetch_url", lambda url, **kw: _Result(archive))
    monkeypatch.setitem(sbbinary.PINNED_SHA256, ("linux", "x86_64"), "0" * 64)
    with pytest.raises(BinaryError, match=r"SHA-256|не совпад"):
        sbbinary.download_release(tmp_path / "a", "1.14.3", release=_release(archive))
    # Хеш, который сообщает GitHub, расходится с зашитым — загрузка отвергается.
    digest = hashlib.sha256(archive).hexdigest()
    monkeypatch.setitem(sbbinary.PINNED_SHA256, ("linux", "x86_64"), digest)
    with pytest.raises(BinaryError, match="не совпадает с проверенным"):
        sbbinary.download_release(tmp_path / "b", "1.14.3", release=_release(archive, "f" * 64))
    empty = _archive({"x/LICENSE": b"mit"})
    digest = hashlib.sha256(empty).hexdigest()
    monkeypatch.setitem(sbbinary.PINNED_SHA256, ("linux", "x86_64"), digest)
    monkeypatch.setattr("xgw.fetch.fetch_url", lambda url, **kw: _Result(empty))
    with pytest.raises(BinaryError, match="нет бинарника"):
        sbbinary.download_release(tmp_path / "c", "1.14.3", release=_release(empty))


def test_hash_comes_from_the_api_where_none_is_pinned():
    release = _release(b"x", "a" * 64)
    name = sbbinary.asset_name("v1.14.3", "linux", "aarch64")
    release.assets[name] = ("https://example.invalid/b", "b" * 64)
    assert sbbinary.expected_sha256(release, name, "linux", "aarch64") == "b" * 64
    release.assets[name] = ("https://example.invalid/b", "")
    with pytest.raises(BinaryError):
        sbbinary.expected_sha256(release, name, "linux", "aarch64")


def test_only_the_verified_version_is_accepted():
    assert sbbinary.parse_version("v1.14.3") == (1, 14, 3)
    with pytest.raises(BinaryError):
        sbbinary.parse_version("latest")
    with pytest.raises(BinaryError):
        sbbinary.get_release("latest")


# --- xgw update-singbox --------------------------------------------------------------------


def test_update_singbox_installs_the_checked_version(tmp_path, monkeypatch):
    from xgw.sbcore import update

    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    lines: list[str] = []

    def fake_download(dest: Path, version, *, release=None, **kw):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "sing-box").write_bytes(b"new")
        return "v1.14.3", dest / "sing-box"

    monkeypatch.setattr(update.singboxing, "installed_version",
                        lambda path: (1, 14, 3) if Path(path).read_bytes() == b"new" else None)
    code = update.update_singbox(
        Config(), paths, out=lines.append, get_release=lambda *a, **kw: _release(b""),
        download=fake_download,
    )
    assert code == 0 and paths.singbox_bin.read_bytes() == b"new"
    assert "sing-box установлен" in lines[-1]
    again = update.update_singbox(
        Config(), paths, out=lines.append, get_release=lambda *a, **kw: _release(b""),
        download=fake_download,
    )
    assert again == 0 and "уже нужная версия" in lines[-1]


def test_update_singbox_refuses_another_version_and_a_failed_download(tmp_path, monkeypatch):
    from xgw.sbcore import update

    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    lines: list[str] = []

    def broken(*args, **kwargs):
        raise BinaryError("нет сети")

    assert update.update_singbox(Config(), paths, out=lines.append,
                                 get_release=lambda *a, **kw: _release(b""), download=broken) == 1
    assert "не загружен" in lines[-1] and not paths.singbox_bin.exists()

    def other(dest: Path, version, *, release=None, **kw):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "sing-box").write_bytes(b"other")
        return "v1.14.3", dest / "sing-box"

    monkeypatch.setattr(update.singboxing, "installed_version", lambda path: (1, 13, 0))
    assert update.update_singbox(Config(), paths, out=lines.append,
                                 get_release=lambda *a, **kw: _release(b""), download=other) == 1
    assert "а нужен 1.14.3" in lines[-1] and not paths.singbox_bin.exists()


# --- поиск серверов, которых sing-box не принимает (аудит, F-07) ---------------------------


def test_servers_sing_box_refuses_are_found_by_halves_and_remembered(monkeypatch, tmp_path):
    """Как у Xray (validate.narrow): плохой сервер ищется делением пополам, а при следующей
    сборке отбрасывается без запуска sing-box."""
    from xgw.generator import validate

    monkeypatch.setattr(validate, "_REJECTED", {})
    nodes = _nodes(HY2, ANYTLS, WG, STLS)
    bad = _by_name(nodes, "AnyTLS")
    bad.singbox.main["no_such_field"] = 1
    seen: list[dict] = []

    def check(config, _bin):
        seen.append(config)
        if "no_such_field" in json.dumps(config):
            return False, ('FATAL[0000] decode config at <config>: outbounds[1]: json: '
                           'unknown field "no_such_field"')
        return True, ""

    monkeypatch.setattr(singbox, "_check_once", check)
    binary = tmp_path / "sing-box"
    binary.write_bytes(b"sing-box")
    invalid = singbox.find_invalid(nodes, Config(), binary)
    assert invalid == {bad.fingerprint: 'unknown field "no_such_field"'}
    assert len(seen) == 5  # вместо 4 по одному — но и при 100 серверах около 15
    # WireGuard — endpoint: в общем конфиге он в endpoints, первым outbound'ом — block.
    mixed = next(config for config in seen if config.get("endpoints"))
    assert mixed["outbounds"][0] == {"type": "block", "tag": "block"}
    seen.clear()
    assert singbox.find_invalid(nodes, Config(), binary) == invalid
    assert len(seen) == 1
