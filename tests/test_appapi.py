"""API приложения XGW для Android (А1 `ANDROID_APP_PLAN.md`): привязка телефона по QR,
подпись запросов, белый список действий, конфиг Xray для телефона, Funnel из панели,
`xgw uninstall`. Сервер настоящий (127.0.0.1, свободный порт), «телефон» — phone_client.py."""

import base64
import json
import time
from pathlib import Path

import pytest
from fake_tailscale import FUNNEL_URL, FakeTailscale
from phone_client import PhoneClient
from phone_client import signed_text as client_signed_text
from test_panel import Rig

from xgw import config, managed, phones, qr, tailscale
from xgw.config import Config
from xgw.generator import phone as phoning
from xgw.paths import Paths
from xgw.uninstall import Uninstaller
from xgw.watch import appapi
from xgw.watch.appapi import AppApi

NAME = "gw.tailnet-1.ts.net"
GOLDEN = json.loads((Path(__file__).parent / "fixtures/golden/full_config.json")
                    .read_text(encoding="utf-8"))


# --- телефоны: привязка и подпись ----------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def book(tmp_path):
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    clock = Clock()
    return phones.Phones(paths, clock=clock), clock, paths


def _headers(phone_id: str, key: bytes, method: str, path: str, body: bytes, stamp: float,
             nonce: str = "nonce-0123456789ab") -> dict:
    stamp_text = str(int(stamp))
    return {
        "X-XGW-Phone": phone_id, "X-XGW-Time": stamp_text, "X-XGW-Nonce": nonce,
        "X-XGW-Signature": phones.sign(key, phone_id, method, path, stamp_text, nonce, body),
    }


def test_pairing_code_works_once_and_for_ten_minutes(book):
    store, clock, paths = book
    code = store.new_code()
    assert store.pairing()["code"] == code
    phone_id, key = store.pair(code, "Galaxy S25 Ultra")
    assert len(key) == 32 and store.pairing() == {"code": "", "until": None, "paired": phone_id}
    with pytest.raises(phones.PhoneError):
        store.pair(code, "второй раз")
    saved = json.loads(phones.store_file(paths).read_text(encoding="utf-8"))
    assert phones.store_file(paths).stat().st_mode & 0o777 == 0o600
    assert saved["phones"][phone_id]["name"] == "Galaxy S25 Ultra"
    late = store.new_code()
    clock.now += phones.PAIR_TTL + 1
    with pytest.raises(phones.PhoneError):
        store.pair(late, "поздно")


def test_wrong_codes_do_not_kill_the_qr_at_once(book):
    store, _clock, _paths = book
    code = store.new_code()
    for _ in range(phones.PAIR_TRIES - 1):
        with pytest.raises(phones.PhoneError):
            store.pair("x" * 32, "чужой")
    assert store.pair(code, "свой")[0]
    code = store.new_code()
    for _ in range(phones.PAIR_TRIES):
        with pytest.raises(phones.PhoneError):
            store.pair("y" * 32, "чужой")
    with pytest.raises(phones.PhoneError):
        store.pair(code, "свой")  # перебор — код погашен


def test_signature_time_replay_and_revoke(book):
    store, clock, _paths = book
    phone_id, key = store.pair(store.new_code(), "<b>Pixel</b>\x07")
    assert store.listing()[0].name == "bPixel/b"  # без разметки и управляющих символов
    body = b'{"name": "scan"}'
    good = _headers(phone_id, key, "POST", "/api/act", body, clock.now)
    assert store.verify(good, "POST", "/api/act", body).id == phone_id
    with pytest.raises(phones.PhoneError, match="повтор"):
        store.verify(good, "POST", "/api/act", body)
    for changed in (
        _headers(phone_id, key, "POST", "/api/act", body, clock.now, "nonce-other-123456"),
    ):
        with pytest.raises(phones.PhoneError, match="подпись"):
            store.verify(changed, "POST", "/api/act", b'{"name": "power"}')  # другое тело
    old = _headers(phone_id, key, "GET", "/api/state", b"", clock.now - 120, "nonce-old-1234567")
    with pytest.raises(phones.PhoneError, match="время"):
        store.verify(old, "GET", "/api/state", b"")
    stranger = _headers(phone_id, b"k" * 32, "GET", "/api/state", b"", clock.now,
                        "nonce-str-1234567")
    with pytest.raises(phones.PhoneError, match="подпись"):
        store.verify(stranger, "GET", "/api/state", b"")
    with pytest.raises(phones.PhoneError):
        store.verify({}, "GET", "/api/state", b"")
    assert store.revoke(phone_id)
    fresh = _headers(phone_id, key, "GET", "/api/state", b"", clock.now, "nonce-new-1234567")
    with pytest.raises(phones.PhoneError, match="не привязан"):
        store.verify(fresh, "GET", "/api/state", b"")


def test_client_signs_the_same_text_as_the_gateway():
    args = ("abcdef012345", "post", "/api/act?x=1", "1800000000", "n" * 20, b"{}")
    assert client_signed_text(*args) == phones.signed_text(*args)


def test_phone_limit_and_rename(book):
    store, _clock, _paths = book
    for number in range(phones.MAX_PHONES):
        store.pair(store.new_code(), f"телефон {number}")
    with pytest.raises(phones.PhoneError, match="отвяжите"):
        store.pair(store.new_code(), "лишний")
    first = store.listing()[0]
    assert store.rename(first.id, "  Мой  ") and store.listing()[0].name == "Мой"
    assert not store.rename("000000000000", "нет такого")


# --- конфиг Xray для телефона -------------------------------------------------------


def test_phone_config_is_the_gateway_set_for_a_tun_inbound():
    config_ = phoning.build(GOLDEN)
    assert [inbound["protocol"] for inbound in config_["inbounds"]] == ["tun"]
    assert config_["inbounds"][0]["settings"] == {"name": phoning.TUN_NAME, "mtu": 1500}
    tags = [outbound["tag"] for outbound in config_["outbounds"]]
    assert tags == ["proxy-nl-1243", "proxy-de-1f80", "direct", "block", "dns-out"]
    assert phoning.servers(config_) == ["proxy-nl-1243", "proxy-de-1f80"]
    assert '"mark"' not in json.dumps(config_)  # метки шлюза на телефоне не нужны
    rules = config_["routing"]["rules"]
    assert not any("probe" in json.dumps(rule) for rule in rules)
    assert {"type": "field", "inboundTag": ["tun-in"], "port": "53",
            "outboundTag": "dns-out"} in rules
    assert rules[-1] == {"type": "field", "network": "tcp,udp", "balancerTag": "auto"}
    assert config_["routing"]["balancers"][0]["fallbackTag"] == "proxy-nl-1243"
    ping = config_["burstObservatory"]["pingConfig"]
    assert ping["httpMethod"] == "HEAD" and ping["interval"] == "3m"
    assert config_["dns"] == GOLDEN["dns"]
    assert "api" not in config_ and "stats" not in config_


def test_phone_config_drops_sing_box_bridges_and_keeps_chains():
    applied = json.loads(json.dumps(GOLDEN))
    bridge = {"tag": "proxy-sb-0001", "protocol": "socks", "settings": {
        "servers": [{"address": "127.0.0.1", "port": 22001}]}}
    chained = applied["outbounds"][1]
    chained["streamSettings"]["sockopt"]["dialerProxy"] = "fragment"
    fragment = {"tag": "fragment", "protocol": "freedom", "settings": {"fragment": {}},
                "streamSettings": {"sockopt": {"mark": 2}}}
    applied["outbounds"] += [bridge, fragment]
    applied["routing"]["balancers"][0]["fallbackTag"] = "spare-nl-d8a7"
    tags = [outbound["tag"] for outbound in phoning.build(applied)["outbounds"]]
    assert "proxy-sb-0001" not in tags and "fragment" in tags and "spare-nl-d8a7" in tags
    with pytest.raises(phoning.PhoneConfigError):
        phoning.build({"outbounds": [bridge, {"tag": "direct", "protocol": "freedom"}]})
    with pytest.raises(phoning.PhoneConfigError):
        phoning.build(None)


# --- API приложения ----------------------------------------------------------------


@pytest.fixture()
def api(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.paths.xray_config_file.write_text(json.dumps(GOLDEN), encoding="utf-8")
    monkeypatch.setattr(appapi, "FAIL_PAUSE", 0.0)
    server = AppApi(rig.panel, rig.panel.phones, port=0)
    server.start()
    rig.panel.app_api = server
    managed.set_tailscale_funnel(rig.store_path, NAME)
    rig.panel._wake()
    rig.phone = PhoneClient(f"http://127.0.0.1:{server.port}", host=NAME)
    rig.server = server
    yield rig
    server.stop()
    rig.panel.stop()


def _pair(rig) -> PhoneClient:
    status, payload = rig.phone.pair(rig.panel.phones.new_code(), "Galaxy S25 Ultra")
    assert status == 200 and payload["name"] == "Galaxy S25 Ultra", payload
    return rig.phone


def test_hello_answers_only_on_the_funnel_name(api):
    assert api.phone.raw("GET", "/api/hello") == (200, {"app": "XGW"})
    assert PhoneClient(f"http://127.0.0.1:{api.server.port}", host=f"{NAME}:443").raw(
        "GET", "/api/hello")[0] == 200
    for host in (f"127.0.0.1:{api.server.port}", "evil.example", f"{NAME}:8443"):
        client = PhoneClient(f"http://127.0.0.1:{api.server.port}", host=host)
        assert client.raw("GET", "/api/hello")[0] == 421
    managed.set_tailscale_funnel(api.store_path, "")
    api.panel._wake()
    assert api.phone.raw("GET", "/api/hello")[0] == 421  # Funnel выключен — API закрыт


def test_paired_phone_reads_the_state_without_secrets(api):
    phone = _pair(api)
    status, state = phone.signed("GET", "/api/state")
    assert status == 200 and state["state"] == "HEALTHY"
    assert [member["tag"] for member in state["members"]] == ["proxy-nl-aaaa", "proxy-de-bbbb"]
    assert state["power"]["can_off"] is True and state["spares"] == 1
    # Приложение показывает «нет интернета в сети» и прогресс замеров, как панель.
    assert "lan_problem" in state["capture"] and set(state["speed_progress"]) == {"total", "done"}
    text = json.dumps(state, ensure_ascii=False)
    assert "S3CR3T" not in text and "sub.example.net" not in text and "trojan://" not in text
    assert "subscriptions" not in state and "links" not in state and "events" not in state
    events = [row["detail"] for row in api.panel.state()["events"]]
    assert "телефон «Galaxy S25 Ultra» привязан" in events


def test_actions_are_a_white_list(api):
    phone = _pair(api)
    status, result = phone.signed("POST", "/api/act", {"name": "scan"})
    assert status == 200 and result["ok"] and api.daemon.asked == ["scan"]
    for name in ("add", "subscription/remove", "tailscale/route", "tailscale/ssh",
                 "phones/revoke", "servers", "core"):
        status, result = phone.signed("POST", "/api/act", {"name": name, "text": "x"})
        assert status == 403, name
    status, result = phone.signed("POST", "/api/act", {"name": "power", "on": False})
    assert status == 200 and result["ok"], result
    assert "tproxy" not in api.kernel.table  # то же, что кнопка панели
    assert api.panel.state()["capture"]["mode"] == "off"


def test_bad_requests_are_refused_and_lock_the_door(api, monkeypatch):
    phone = _pair(api)
    phone.signed("GET", "/api/state")
    assert phone.replay()[0] == 403  # тот же запрос второй раз
    stranger = PhoneClient(f"http://127.0.0.1:{api.server.port}", host=NAME,
                           phone=phone.phone, key=b"x" * 32)
    for _ in range(appapi.FAILS_MAX):
        status, _payload = stranger.signed("GET", "/api/state")
    assert status in (403, 429)
    assert stranger.signed("GET", "/api/state")[0] == 429
    assert phone.signed("GET", "/api/state")[0] == 429  # дверь закрыта для всех на минуту
    assert phone.raw("GET", "/api/hello")[0] == 200  # проверка Funnel — по-прежнему
    events = [row["detail"] for row in api.panel.state()["events"]]
    assert any("неудачных входов за минуту" in detail for detail in events)


def test_rate_limit_per_phone(api, monkeypatch):
    monkeypatch.setattr(appapi, "RATE", 3)
    phone = _pair(api)
    codes = [phone.signed("GET", "/api/state")[0] for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_phone_config_goes_only_to_a_paired_phone(api):
    assert api.phone.raw("GET", "/api/phone-config")[0] == 403
    phone = _pair(api)
    status, payload = phone.signed("GET", "/api/phone-config")
    assert status == 200 and payload["servers"] == ["proxy-nl-1243", "proxy-de-1f80"]
    assert payload["config"]["inbounds"][0]["protocol"] == "tun"
    api.paths.xray_config_file.write_text("{}", encoding="utf-8")
    status, payload = phone.signed("GET", "/api/phone-config")
    assert status == 409 and "применённого" in payload["error"]


def test_revoked_phone_is_refused_at_once(api):
    phone = _pair(api)
    assert phone.signed("GET", "/api/state")[0] == 200
    api.panel.phones.revoke(phone.phone)
    assert phone.signed("GET", "/api/state")[0] == 403


def test_big_and_broken_bodies(api):
    phone = _pair(api)
    status, _payload = phone.raw("POST", "/api/pair", b"x" * (appapi.MAX_BODY + 1))
    assert status == 413
    assert phone.raw("POST", "/api/pair", b"[1]")[0] == 400
    assert phone.signed("GET", "/api/nothing")[0] == 404


# --- панель: «Привязать телефон» и Funnel ---------------------------------------------


@pytest.fixture()
def card_rig(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    fake = FakeTailscale()
    rig.fake = fake
    panel = rig.panel
    panel.runner, panel.spawn = fake, fake.spawn
    panel.which = lambda name: f"/usr/bin/{name}"
    panel.sys_net = tmp_path / "sys-class-net"
    panel.ts_wait = 0.5
    socket = tailscale.socket_path(rig.paths)
    socket.parent.mkdir(parents=True, exist_ok=True)
    socket.write_text("", encoding="ascii")
    server = AppApi(panel, panel.phones, port=0)
    server.start()
    panel.app_api = server
    rig.client.login()
    yield rig
    server.stop()
    panel.stop()


def _act(rig, name: str, body: dict | None = None) -> dict:
    return rig.client.act(name, body or {})


def _phones(rig) -> dict:
    rig.panel._ts_card = (0.0, None)
    return rig.client.state()["phones"]


def test_one_button_turns_funnel_on_and_shows_the_qr(card_rig):
    fake = card_rig.fake
    result = _act(card_rig, "phones/pair")
    assert result["ok"] and "Наведите камеру" in result["text"]
    port = card_rig.panel.app_api.port
    assert fake.funnel == f"http://127.0.0.1:{port}"
    assert ("tailscale", "funnel", "--bg", "--https=443", f"http://127.0.0.1:{port}") in fake.calls
    assert card_rig.saved()["tailscale"]["funnel"] == NAME
    card = _phones(card_rig)
    link = card["pairing"]["link"]
    assert link.startswith(f"xgw://pair?u=https://{NAME}&c=")
    assert card["pairing"]["qr"] == qr.encode(link) and card["pairing"]["until"]
    funnel = card_rig.client.state()["tailscale"]["funnel"]
    assert funnel["on"] and funnel["live"] is True and funnel["url"] == f"https://{NAME}/"
    # Телефон сканирует QR: код из ссылки, адрес — имя шлюза.
    code = link.split("&c=")[1]
    phone = PhoneClient(f"http://127.0.0.1:{port}", host=NAME)
    status, payload = phone.pair(code, "Galaxy S25 Ultra")
    assert status == 200 and base64.b64decode(payload["key"])
    card = _phones(card_rig)
    assert card["pairing"]["link"] == "" and card["pairing"]["paired"] == "Galaxy S25 Ultra"
    assert [item["name"] for item in card["list"]] == ["Galaxy S25 Ultra"]


def test_pairing_waits_while_funnel_is_not_allowed(card_rig):
    fake = card_rig.fake
    fake.funnel_allowed = False
    result = _act(card_rig, "phones/pair")
    assert result["ok"] and "разрешить Funnel" in result["text"]
    card = _phones(card_rig)
    assert card["waiting"] and card["enable_url"] == FUNNEL_URL and card["pairing"]["qr"] == []
    fake.allow_funnel()
    card = _phones(card_rig)
    assert not card["waiting"] and card["pairing"]["qr"]


def test_funnel_off_closes_the_api_and_the_qr(card_rig):
    _act(card_rig, "phones/pair")
    port = card_rig.panel.app_api.port
    phone = PhoneClient(f"http://127.0.0.1:{port}", host=NAME)
    assert phone.raw("GET", "/api/hello")[0] == 200
    result = _act(card_rig, "tailscale/funnel", {"on": False})
    assert result["ok"] and card_rig.fake.funnel == ""
    assert card_rig.saved()["tailscale"]["funnel"] == ""
    assert phone.raw("GET", "/api/hello")[0] == 421
    assert _phones(card_rig)["pairing"]["link"] == ""


def test_rename_and_revoke_from_the_panel(card_rig):
    _act(card_rig, "phones/pair")
    code = _phones(card_rig)["pairing"]["link"].split("&c=")[1]
    card_rig.panel.phones.pair(code, "Телефон")
    phone_id = _phones(card_rig)["list"][0]["id"]
    assert _act(card_rig, "phones/rename", {"id": phone_id, "name": "Мой S25"})["ok"]
    assert _phones(card_rig)["list"][0]["name"] == "Мой S25"
    assert _act(card_rig, "phones/revoke", {"id": phone_id})["ok"]
    assert _phones(card_rig)["list"] == []
    assert not _act(card_rig, "phones/revoke", {"id": phone_id})["ok"]
    assert not _act(card_rig, "phones/rename", {"id": phone_id, "name": ""})["ok"]


def test_pairing_needs_tailscale_in_the_tailnet(card_rig):
    card_rig.fake.backend = "NeedsLogin"
    assert _act(card_rig, "phones/pair")["text"] == "сначала войдите в Tailscale"
    assert card_rig.fake.funnel == "" and _phones(card_rig)["pairing"]["link"] == ""


def test_app_port_comes_from_the_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[panel]\napp_port = 9876\n", encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.panel.app_port == 9876 and warnings == []
    assert Config().panel.app_port == 8782


# --- xgw uninstall --------------------------------------------------------------------


def test_uninstall_removes_the_funnel_xgw_enabled(tmp_path):
    fake, out = FakeTailscale(), []
    fake.funnel = fake.serve = "http://127.0.0.1:8782"
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    remover = Uninstaller(Config(), paths, runner=fake, out=out.append,
                          proc_sys=tmp_path / "proc", which=lambda name: f"/usr/bin/{name}")
    store = managed.path_for(paths.config_file)
    managed.set_tailscale_funnel(store, NAME)
    assert remover._tailscale().startswith("адрес для приложения на телефоне")
    assert fake.funnel == "" and fake.serve  # Serve XGW не включал — остался
    assert managed.load(store)[0]["tailscale"]["funnel"] == ""
    fake.fail["funnel"] = "no tailscaled"
    managed.set_tailscale_funnel(store, NAME)
    with pytest.raises(RuntimeError, match="sudo tailscale funnel --https=443 off"):
        remover._tailscale()


def test_hello_is_cheap_and_needs_no_phone(api, monkeypatch):
    calls = []
    monkeypatch.setattr(api.panel, "state", lambda: calls.append(1) or {})
    started = time.monotonic()
    assert api.phone.raw("GET", "/api/hello")[0] == 200
    assert calls == [] and time.monotonic() - started < 2
