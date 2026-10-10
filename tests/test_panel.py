"""Панель управления: вход по токену, защита запросов, что она показывает и что
делают её кнопки. Сервер настоящий (127.0.0.1, свободный порт), система подменена."""

import http.client
import json
import os
import threading
import time

import links
import pytest
from fakenet import FakeKernel

from xgw import actions, config, engine, managed
from xgw.net.capture import Capture
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store, SubscriptionCache
from xgw.watch import panel as panel_module
from xgw.watch import status
from xgw.watch.panel import Panel

TOKEN = "panel-token-for-tests"
SUB_URL = "https://sub.example.net/api/sub/S3CR3T-SUB-TOKEN"
CONFIG = f"""
[network]
lan_if = "lan0"

[[subscriptions]]
name = "main"
url = "{SUB_URL}"

[manual]
links = ["{links.TROJAN}"]
"""
# отпечаток, тег, имя, источник, роль в ядре («» — в ядре его нет)
SERVERS = [
    ("aaaa1111", "proxy-nl-aaaa", "NL-1", "main", "member"),
    ("bbbb2222", "proxy-de-bbbb", "DE-1", "main", "member"),
    ("cccc3333", "spare-fi-cccc", "FI-1", "main", "spare"),
    ("dddd4444", "", "<b>KZ</b>", "main", ""),
    ("eeee5555", "", "Осталось 5 ГБ", "main", "filter"),
]


class FakeDaemon:
    def __init__(self) -> None:
        self.poke = threading.Event()
        self.asked: list[str] = []
        self.refresh_pending = self.scan_pending = False

    def request_refresh(self) -> None:
        self.asked.append("refresh")

    def request_scan(self) -> None:
        self.asked.append("scan")


class Client:
    """Браузер в миниатюре: помнит cookie и шлёт то же, что страница панели."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.cookie = ""

    def request(self, method: str, path: str, *, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        send = {"Host": host or f"127.0.0.1:{self.port}"}
        if self.cookie:
            send["Cookie"] = self.cookie
        send.update(headers or {})
        data = None if body is None else json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data, headers=send)
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        conn.close()
        return response, text

    def login(self) -> None:
        response, _text = self.request("GET", f"/?token={TOKEN}")
        assert response.status == 303
        self.cookie = response.getheader("Set-Cookie").split(";")[0]

    def state(self) -> dict:
        response, text = self.request("GET", "/api/state")
        assert response.status == 200, text
        return json.loads(text)

    def act(self, name: str, body: dict) -> dict:
        response, text = self.request(
            "POST", f"/api/{name}", body=body,
            headers={"X-XGW-Panel": "1", "Content-Type": "application/json",
                     "Origin": f"http://127.0.0.1:{self.port}"},
        )
        assert response.status == 200, text
        return json.loads(text)


def _snapshot(excluded=()) -> dict:
    members, spares = [], []
    for fingerprint, tag, name, source, role in SERVERS:
        base = {"tag": tag, "fingerprint": fingerprint, "name": name, "source": source}
        if fingerprint in excluded:
            continue
        if role == "member":
            members.append({**base, "alive": True, "delay_ms": 80, "dead_since": None})
        elif role == "spare":
            spares.append({**base, "verdict": "OK", "bytes": 65536, "seconds": 0.4,
                           "scanned": time.time()})
    return {
        "updated": time.time(), "daemon": True, "state": "HEALTHY", "action": "",
        "since": time.time(), "xray": {"ok": True, "version": "26.3.27"},
        "capture": {"loaded": True}, "members": members, "spares": spares,
        "quota": {"main": {"upload": 1, "download": 2, "total": 10}},
        "sub_errors": {}, "budget": {"total_mb": 10}, "pending_restart": False, "events": [],
    }


class Rig:
    def __init__(self, tmp_path, monkeypatch) -> None:
        self.paths = Paths(root=tmp_path / "root")
        self.paths.ensure()
        self.config_path = self.paths.config_file
        self.config_path.write_text(CONFIG, encoding="utf-8")
        self.store_path = managed.path_for(self.config_path)
        status.write_status(self.paths, _snapshot())
        atomic_write_json(engine.inventory_file(self.paths), {"servers": [
            {"fingerprint": fingerprint, "name": name, "source": source, "protocol": "vless",
             "skip": role if role == "filter" else ""}
            for fingerprint, _tag, name, source, role in SERVERS
        ]})
        Store(self.paths.db_file).close()
        self.kernel = FakeKernel()
        proc = tmp_path / "proc"
        (proc / "net/ipv4").mkdir(parents=True)
        (proc / "net/ipv4/ip_forward").write_text("0\n", encoding="ascii")
        self.root_problem: str | None = None
        self.xray_up = True
        monkeypatch.setattr(
            engine, "healthy_http_in", lambda _cfg: ("127.0.0.1", 10809) if self.xray_up else None
        )
        self.daemon = FakeDaemon()
        self.panel = Panel(
            self.paths, self.config_path, TOKEN, port=0,
            root_problem=lambda: self.root_problem,
            capture_factory=lambda cfg, paths, **kwargs: Capture(
                cfg, paths, runner=self.kernel, proc_sys=proc, time_uids=(), **kwargs),
        )
        monkeypatch.setattr(Panel, "_selected", lambda self, ok, now: ["proxy-nl-aaaa"])
        cfg, _warnings = config.load(self.config_path)
        self.panel.configure(cfg, self.daemon)
        self.panel.start()
        self.client = Client(self.panel.port)

    def saved(self) -> dict:
        return json.loads(self.store_path.read_text(encoding="utf-8"))


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    yield instance
    instance.panel.stop()


@pytest.fixture()
def user(rig):
    rig.client.login()
    return rig.client


# --- вход и защита запросов --------------------------------------------------------


def test_without_token_there_is_only_the_login_page(rig):
    response, text = rig.client.request("GET", "/")
    assert response.status == 200 and 'name="token"' in text and 'id="power"' not in text
    assert response.getheader("Set-Cookie") is None
    assert "default-src 'none'" in response.getheader("Content-Security-Policy")
    assert rig.client.request("GET", "/api/state")[0].status == 401
    response, _text = rig.client.request(
        "POST", "/api/power", body={"on": False}, headers={"X-XGW-Panel": "1"})
    assert response.status == 401 and rig.kernel.calls == []


def test_token_moves_into_a_cookie_and_out_of_the_address(rig):
    response, _text = rig.client.request("GET", f"/?token={TOKEN}")
    cookie = response.getheader("Set-Cookie")
    assert response.status == 303 and response.getheader("Location") == "/"
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and TOKEN not in cookie
    rig.client.cookie = cookie.split(";")[0]
    response, text = rig.client.request("GET", "/")
    assert response.status == 200 and 'id="power"' in text
    # Чужой токен и чужая cookie не подходят.
    response, text = rig.client.request("GET", "/?token=guess")
    assert response.status == 403 and 'name="token"' in text
    rig.client.cookie = "xgw_panel=" + "0" * 64
    assert rig.client.request("GET", "/api/state")[0].status == 401


def test_foreign_host_header_is_refused(rig, user):
    """Подмена DNS (rebinding): сайт злоумышленника указывает на 127.0.0.1."""
    for host in ("evil.example", f"evil.example:{rig.panel.port}", "127.0.0.1:1"):
        response, text = user.request("GET", "/api/state", host=host)
        assert response.status == 403 and "127.0.0.1" in text
    assert user.request("GET", "/api/state", host=f"localhost:{rig.panel.port}")[0].status == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},  # обычная форма чужого сайта такой заголовок не отправит
        {"X-XGW-Panel": "1", "Origin": "http://evil.example"},
        {"X-XGW-Panel": "1", "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_changes_are_accepted_only_from_the_panel_page(rig, user, headers):
    response, _text = user.request("POST", "/api/power", body={"on": False}, headers=headers)
    assert response.status == 403
    assert rig.kernel.calls == [] and rig.panel._capture().choice() is None


def test_bad_requests_get_clear_answers(rig, user):
    headers = {"X-XGW-Panel": "1"}
    assert user.request("POST", "/api/power", headers=headers)[0].status == 200  # пустое тело
    conn = http.client.HTTPConnection("127.0.0.1", rig.panel.port, timeout=10)
    conn.request("POST", "/api/power", body=b"{not json",
                 headers={**headers, "Cookie": user.cookie})
    assert conn.getresponse().status == 400
    conn.close()
    response, _text = user.request("POST", "/api/add", body={"text": "x" * 70000}, headers=headers)
    assert response.status == 413
    assert user.act("no-such-action", {}) == {
        "ok": False, "text": "нет такого действия", "notes": []}
    assert user.request("GET", "/../etc/passwd")[0].status == 404
    response, text = user.request("HEAD", "/app.js")
    assert response.status == 200 and text == ""
    for path in ("/app.js", "/app.css", "/icon.svg"):
        assert rig.client.request("GET", path)[0].status == 200


# --- что видно ---------------------------------------------------------------------


def test_state_shows_servers_by_subscription_and_no_secrets(rig, user):
    managed.set_servers(rig.store_path, ["dddd4444"], "disabled")
    rig.panel._wake()
    _response, text = user.request("GET", "/api/state")
    state = json.loads(text)
    assert "S3CR3T" not in text and "fake-trojan" not in text.lower() and TOKEN not in text
    assert state["subscriptions"] == [{
        "name": "main", "host": "sub.example.net", "secure": True, "managed": False,
        "servers": 4, "fetched": None, "error": "",  # с отключённым, без служебной записи
        "quota": {"upload": 1, "download": 2, "total": 10},
    }]
    assert state["sources"] == ["main", "manual"]
    by_name = {server["name"]: server for server in state["servers"]}
    assert by_name["NL-1"]["status"] == "member" and by_name["NL-1"]["selected"] is True
    assert by_name["NL-1"]["delay_ms"] == 80 and by_name["FI-1"]["status"] == "spare"
    assert by_name["<b>KZ</b>"]["status"] == "disabled" and not by_name["<b>KZ</b>"]["pending"]
    assert by_name["Осталось 5 ГБ"] == {
        "fingerprint": "eeee5555", "name": "Осталось 5 ГБ", "source": "main",
        "protocol": "vless", "status": "skipped", "skip": "filter",
    }
    assert [server["status"] for server in state["servers"]] == [
        "member", "member", "spare", "disabled", "skipped"]
    assert state["links"][0]["label"].startswith("trojan · ") and not state["links"][0]["managed"]
    assert state["capture"]["mode"] == "on" and state["lan"] == {
        "interface": "lan0", "gateway": "192.168.50.1"}
    assert state["power"] == {"can_on": False, "can_off": True, "why": ""}


def test_working_server_missing_from_the_list_is_still_shown(rig, user):
    engine.inventory_file(rig.paths).unlink()
    names = [server["name"] for server in user.state()["servers"]]
    assert names == ["NL-1", "DE-1", "FI-1"]


def test_devices_and_events_are_listed(rig, user):
    from xgw.net import dnsmasq

    leases = dnsmasq.leases_path(rig.paths)
    leases.parent.mkdir(parents=True, exist_ok=True)
    leases.write_text("1791600000 aa:bb:cc:00:11:22 192.168.50.101 phone *\n", encoding="utf-8")
    with actions.open_store(rig.paths) as store:
        store.add_event("apply", f"подписка {SUB_URL} применена")
    state = user.state()
    assert state["devices"] == [{"expires": 1791600000, "mac": "aa:bb:cc:00:11:22",
                                 "ip": "192.168.50.101", "name": "phone", "bypass": False}]
    assert state["events"][0]["kind"] == "apply" and "S3CR3T" not in state["events"][0]["detail"]


# --- кнопка включения ----------------------------------------------------------------


def test_power_button_does_what_enable_and_disable_do(rig, user):
    assert user.act("power", {"on": False})["ok"]
    assert "tproxy" not in rig.kernel.table and "masquerade" in rig.kernel.table
    state = user.state()
    assert state["capture"]["mode"] == "off"
    assert state["power"] == {"can_on": True, "can_off": False, "why": ""}

    result = user.act("power", {"on": True})
    assert result["ok"] and "перехват включён: сеть lan0 и эта машина" in result["text"]
    assert "tproxy to 127.0.0.1:12345" in rig.kernel.table
    assert user.state()["capture"]["mode"] == "on"
    assert [event["kind"] for event in user.state()["events"]][:2] == ["capture", "capture"]


def test_power_on_is_refused_while_xray_is_down(rig, user):
    user.act("power", {"on": False})
    rig.xray_up = False
    calls = len(rig.kernel.calls)
    result = user.act("power", {"on": True})
    assert not result["ok"] and "Xray не отвечает" in result["text"]
    assert len(rig.kernel.calls) == calls and user.state()["capture"]["mode"] == "off"


def test_power_needs_root_and_servers(rig, user):
    rig.root_problem = "нужны права root: sudo xgw …"
    assert user.state()["power"]["why"] == rig.root_problem
    assert not user.act("power", {"on": False})["ok"] and rig.kernel.calls == []
    rig.root_problem = None
    user.act("power", {"on": False})
    status.write_status(rig.paths, {**_snapshot(), "members": [], "spares": []})
    power = user.state()["power"]
    assert power["can_on"] is False and "добавьте подписку" in power["why"]
    assert not user.act("power", {"on": "yes"})["ok"]


# --- подписки и ссылки ---------------------------------------------------------------


def test_subscription_is_added_shown_at_once_and_removed(rig, user):
    url = "https://new.example.org/sub/ANOTHER-S3CR3T"
    result = user.act("add", {"text": f"  {url}\n"})
    assert result == {"ok": True, "notes": [],
                      "text": "Подписка «new.example.org» добавлена — получаю серверы…"}
    assert rig.saved()["subscriptions"] == [
        {"name": "new.example.org", "url": url, "user_agent": "", "refresh_minutes": 60}]
    if os.name != "nt":
        assert rig.store_path.stat().st_mode & 0o777 == 0o600
    assert rig.daemon.poke.is_set()  # демон перечитает настройки сразу
    added = user.state()["subscriptions"][1]
    assert added["name"] == "new.example.org" and added["managed"] and added["fetched"] is None
    cfg, warnings = config.load(rig.config_path)
    assert [sub.url for sub in cfg.subscriptions] == [SUB_URL, url] and warnings == []
    assert cfg.managed.subscriptions == ["new.example.org"]

    assert not user.act("add", {"text": url})["ok"]  # вторая такая же
    SubscriptionCache(rig.paths.cache_dir).save("new.example.org", b"cached body")
    assert user.act("subscription/remove", {"name": "new.example.org"})["ok"]
    assert rig.saved()["subscriptions"] == []
    assert SubscriptionCache(rig.paths.cache_dir).load("new.example.org") is None
    result = user.act("subscription/remove", {"name": "main"})  # вписана в config.toml
    assert not result["ok"] and "config.toml" in result["text"]


@pytest.mark.parametrize(
    "text",
    ["file:///etc/shadow", "ftp://example.org/sub", "https://", "просто текст", "", "vless://x"],
)
def test_bad_input_is_refused_with_a_reason(rig, user, text):
    result = user.act("add", {"text": text})
    assert not result["ok"] and result["text"]
    assert not rig.store_path.exists()


def test_server_links_are_added_and_removed(rig, user):
    result = user.act("add", {"text": f"{links.VLESS_REALITY}\n{links.VMESS}\n"})
    assert result["ok"] and result["text"] == "Добавлено серверов: 2"
    state = user.state()
    assert [link["managed"] for link in state["links"]] == [False, True, True]
    assert links.FAKE_PBK not in json.dumps(state)
    assert not user.act("add", {"text": links.VMESS})["ok"]  # уже есть
    assert not user.act("add", {"text": links.TROJAN})["ok"]  # уже есть в config.toml
    ours, theirs = state["links"][1]["id"], state["links"][0]["id"]
    assert user.act("link/remove", {"id": ours})["ok"] and len(rig.saved()["links"]) == 1
    assert not user.act("link/remove", {"id": theirs})["ok"]


# --- список серверов -----------------------------------------------------------------


def test_server_is_disabled_removed_and_returned(rig, user):
    result = user.act("servers", {"fingerprints": ["bbbb2222"], "mode": "disabled"})
    assert result["ok"] and result["text"] == "сервер «DE-1» отключён"
    assert rig.saved()["disabled"] == ["bbbb2222"] and rig.daemon.poke.is_set()
    server = next(s for s in user.state()["servers"] if s["fingerprint"] == "bbbb2222")
    # Ядро его ещё использует — демон уберёт на ближайшем шаге; панель говорит об этом.
    assert server["status"] == "disabled" and server["pending"] is True
    status.write_status(rig.paths, _snapshot(excluded={"bbbb2222"}))
    server = next(s for s in user.state()["servers"] if s["fingerprint"] == "bbbb2222")
    assert server["pending"] is False

    assert user.act("servers", {"fingerprints": ["bbbb2222"], "mode": "removed"})["ok"]
    assert rig.saved()["disabled"] == [] and rig.saved()["removed"] == ["bbbb2222"]
    state = user.state()
    assert "bbbb2222" not in [s["fingerprint"] for s in state["servers"]]
    assert state["removed"] == [
        {"fingerprint": "bbbb2222", "name": "DE-1", "source": "main", "protocol": "vless"}]

    result = user.act("servers", {"fingerprints": ["bbbb2222"], "mode": "enabled"})
    assert result["text"] == "сервер «DE-1» возвращён в список"
    assert rig.saved()["removed"] == [] and user.state()["removed"] == []
    cfg, _warnings = config.load(rig.config_path)
    assert cfg.managed.disabled == [] and cfg.managed.removed == []


def test_last_enabled_server_cannot_be_switched_off(rig, user):
    others = ["aaaa1111", "bbbb2222", "dddd4444"]
    assert user.act("servers", {"fingerprints": others, "mode": "disabled"})["ok"]
    result = user.act("servers", {"fingerprints": ["cccc3333"], "mode": "removed"})
    assert not result["ok"] and "ни одного включённого сервера" in result["text"]
    assert rig.saved()["removed"] == []


def test_switching_everything_off_keeps_one_server(rig, user):
    everyone = ["aaaa1111", "bbbb2222", "cccc3333", "dddd4444"]
    result = user.act("servers", {"fingerprints": everyone, "mode": "disabled"})
    assert result["ok"] and result["text"] == "серверов отключено: 3"
    assert "«NL-1» оставлен включённым" in result["notes"][0]
    assert rig.saved()["disabled"] == ["bbbb2222", "cccc3333", "dddd4444"]


@pytest.mark.parametrize(
    "body",
    [
        {"fingerprints": ["ffff0000"], "mode": "disabled"},  # такого сервера нет
        {"fingerprints": ["aaaa1111"], "mode": "вон"},
        {"fingerprints": "aaaa1111", "mode": "disabled"},
        {"fingerprints": [], "mode": "disabled"},
        {"fingerprints": [["aaaa1111"]], "mode": "disabled"},
    ],
)
def test_wrong_server_requests_change_nothing(rig, user, body):
    assert not user.act("servers", body)["ok"]
    assert not rig.store_path.exists()


# --- закрепление, обновление, проверка ------------------------------------------------


def test_pin_goes_through_the_same_code_as_the_command(rig, user, monkeypatch):
    seen: list[tuple] = []

    def fake_pin(cfg, paths, tag, ttl):
        seen.append((tag, ttl))
        return actions.Outcome(0, f"{tag} закреплён на {ttl}", hints=("снять раньше: xgw unpin",))

    monkeypatch.setattr(actions, "pin", fake_pin)
    monkeypatch.setattr(actions, "unpin", lambda cfg, paths: actions.Outcome(0, "снято"))
    result = user.act("pin", {"tag": "proxy-nl-aaaa", "ttl": "1h"})
    # Подсказки с командами терминала панель не показывает.
    assert result == {"ok": True, "text": "proxy-nl-aaaa закреплён на 1h", "notes": []}
    assert seen == [("proxy-nl-aaaa", "1h")]
    assert not user.act("pin", {"tag": "proxy-nl-aaaa", "ttl": "99h"})["ok"] and len(seen) == 1
    assert user.act("unpin", {})["ok"]


def test_pin_from_the_store_is_shown(rig, user):
    with actions.open_store(rig.paths) as store:
        store.set_meta("pin", json.dumps({"tag": "proxy-nl-aaaa", "until": time.time() + 600}))
    assert user.state()["pin"]["tag"] == "proxy-nl-aaaa"
    with actions.open_store(rig.paths) as store:
        store.set_meta("pin", json.dumps({"tag": "proxy-nl-aaaa", "until": time.time() - 1}))
    assert user.state()["pin"] is None


def test_refresh_and_scan_are_passed_to_the_daemon(rig, user):
    assert user.act("refresh", {})["ok"] and user.act("scan", {})["ok"]
    assert rig.daemon.asked == ["refresh", "scan"]
    rig.daemon.refresh_pending = True
    assert user.state()["busy"] == {"refresh": True, "scan": False}
    rig.panel.configure(rig.panel.cfg, None)  # демон ещё не создан
    assert not user.act("refresh", {})["ok"]


def test_refresh_without_subscriptions_is_refused(rig, user):
    rig.config_path.write_text("", encoding="utf-8")
    rig.panel.configure(config.load(rig.config_path)[0], rig.daemon)
    result = user.act("refresh", {})
    assert not result["ok"] and rig.daemon.asked == []


# --- токен и запуск вместе с демоном --------------------------------------------------


def test_token_is_created_once_and_kept_private(tmp_path):
    paths = Paths(root=tmp_path)
    token = panel_module.ensure_token(paths)
    assert len(token) >= 24 and panel_module.ensure_token(paths) == token
    assert panel_module.read_token(paths) == token
    if os.name != "nt":
        assert panel_module.token_file(paths).stat().st_mode & 0o777 == 0o600


def test_panel_follows_the_config(tmp_path):
    paths = Paths(root=tmp_path)
    cfg = config.Config()
    cfg.panel.enabled = False
    assert Panel.from_config(cfg, paths, paths.config_file) is None
    cfg.panel.enabled, cfg.panel.port = True, 8899
    built = Panel.from_config(cfg, paths, paths.config_file)
    assert built.port == 8899 and built.token == panel_module.read_token(paths)
    assert panel_module.address(cfg) == "http://127.0.0.1:8899/"
