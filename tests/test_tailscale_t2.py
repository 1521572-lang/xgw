"""Удалённый доступ к шлюзу через Tailscale (Т2 `TAILSCALE_MINIAPP_PLAN.md`, раздел 3.4):
разбор вывода CLI, команды карточки «Tailscale» (подставной CLI, fake_tailscale), Host панели
по tailnet только при Serve, включённом из панели, ссылка /panel бота, `xgw uninstall`.
"""

import json
import sys
from pathlib import Path

import pytest
from fake_tailscale import AUTH_URL, ENABLE_URL, FakeTailscale
from test_panel import TOKEN, Rig
from test_telegram import GROUP
from test_telegram import Rig as BotRig

from xgw import config, managed, qr, tailscale
from xgw.config import Config
from xgw.net.cmd import CommandError
from xgw.paths import Paths
from xgw.uninstall import Uninstaller
from xgw.watch import panel as panel_module
from xgw.watch.telegram import PRIVATE_ONLY

NAME = "gw.tailnet-1.ts.net"
HOST = f"{NAME}:8443"


# --- разбор вывода CLI ------------------------------------------------------------


def test_status_of_a_running_node_needs_login_and_stopped():
    fake = FakeTailscale()
    running = tailscale.status(fake)
    assert running.backend == "Running" and running.dns_name == NAME
    assert running.addresses == ("100.101.1.1", "fd7a:115c:a1e0::1") and not running.auth_url
    fake.backend, fake.auth_url = "NeedsLogin", AUTH_URL
    waiting = tailscale.status(fake)
    assert waiting.backend == "NeedsLogin" and waiting.auth_url == AUTH_URL
    assert waiting.dns_name == "" and waiting.addresses == ()  # «Self.TailscaleIPs»: null
    fake.backend = "Stopped"
    assert tailscale.status(fake).backend == "Stopped"


def test_status_without_the_cli_is_unknown_not_a_failure():
    def missing(argv, **_kwargs):
        raise CommandError("tailscale: программа не найдена")

    assert tailscale.status(missing) is None
    assert tailscale.prefs(missing) is None
    assert tailscale.serve_status(8781, missing) is None
    assert tailscale.override_dns(missing) is None


def test_prefs_are_read_carefully():
    fake = FakeTailscale()
    assert tailscale.prefs(fake) == tailscale.Prefs(ssh=False, netfilter=2, accept_dns=True)
    assert tailscale.parse_prefs('{"RunSSH": "yes", "NetfilterMode": true}') == tailscale.Prefs()
    assert tailscale.parse_prefs("не JSON") is None
    assert tailscale.parse_prefs("[1]") is None


def test_serve_status_finds_only_our_handler():
    fake = FakeTailscale()
    assert tailscale.serve_status(8781, fake) is False  # «{}» — Serve выключен
    fake.serve = "http://127.0.0.1:8781"
    assert tailscale.serve_status(8781, fake) is True
    assert tailscale.serve_status(9999, fake) is False  # 8443 ведёт не на эту панель
    assert tailscale.parse_serve("", 8781) is False
    assert tailscale.parse_serve("null", 8781) is False
    assert tailscale.parse_serve("oops", 8781) is None
    other = {"Web": {f"{NAME}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8781"}}}}}
    assert tailscale.parse_serve(json.dumps(other), 8781) is False


def test_card_commands():
    calls = []

    def runner(argv, **_kwargs):
        calls.append(list(argv))
        return ""

    tailscale.set_ssh(True, runner)
    tailscale.set_ssh(False, runner)
    tailscale.serve_off(runner)
    tailscale.fix("netfilter", runner)
    tailscale.fix("dns", runner)
    assert calls == [
        ["tailscale", "set", "--ssh"], ["tailscale", "set", "--ssh=false"],
        ["tailscale", "serve", "--https=8443", "off"],
        ["tailscale", "set", "--netfilter-mode=off"], ["tailscale", "set", "--accept-dns=false"],
    ]
    assert tailscale.serve_command(8781) == [
        "tailscale", "serve", "--bg", "--https=8443", "http://127.0.0.1:8781"]
    assert tailscale.login_command() == ["tailscale", "login", "--timeout=15m"]


def test_cli_urls_are_found_in_the_output():
    assert tailscale.find_url(f"\nTo authenticate, visit:\n\n\t{AUTH_URL}\n\n") == AUTH_URL
    assert tailscale.find_url(f"To enable, visit:\n\n         {ENABLE_URL}\n") == ENABLE_URL
    assert tailscale.find_url("Success.") == ""


def test_background_job_runs_and_keeps_its_output(tmp_path):
    job = tailscale.Job([sys.executable, "-c", f"print({AUTH_URL!r})"], tmp_path / "out.log")
    job.proc.wait(timeout=30)
    assert job.code() == 0 and tailscale.find_url(job.text()) == AUTH_URL
    sleeper = tailscale.Job([sys.executable, "-c", "import time; time.sleep(60)"],
                            tmp_path / "sleep.log")
    assert sleeper.code() is None
    sleeper.stop()
    assert sleeper.proc.wait(timeout=30) != 0


# --- QR-код -----------------------------------------------------------------------


def test_qr_matches_the_reference_encoder():
    """Эталон — QR Code generator library (Project Nayuki): байтовый режим, уровень M."""
    golden = json.loads((Path(__file__).parent / "fixtures/qr_golden.json").read_text("utf-8"))
    for text, rows in golden.items():
        assert qr.encode(text) == rows, text
    assert len(qr.encode("hello")) == 21 and len(qr.encode("y" * 213)) == 57
    with pytest.raises(qr.TooLong):
        qr.encode("y" * 214)


# --- панель: карточка и Host по tailnet -------------------------------------------


@pytest.fixture()
def ts_rig(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    fake = FakeTailscale()
    rig.fake = fake
    panel = rig.panel
    panel.runner = fake
    panel.spawn = fake.spawn
    panel.which = lambda name: f"/usr/bin/{name}"
    panel.sys_net = tmp_path / "sys-class-net"
    panel.ts_wait = 0.5
    socket = tailscale.socket_path(rig.paths)
    socket.parent.mkdir(parents=True, exist_ok=True)
    socket.write_text("", encoding="ascii")
    rig.client.login()
    yield rig
    panel.stop()


def _card(rig) -> dict:
    rig.panel._ts_card = (0.0, None)  # не ждать, пока устареет ответ CLI
    return rig.client.state()["tailscale"]


def _ts_act(rig, step: str, body: dict | None = None, host: str | None = None) -> dict:
    client = rig.client
    origin = f"https://{host}" if host else f"http://127.0.0.1:{client.port}"
    response, text = client.request(
        "POST", f"/api/tailscale/{step}", body=body or {}, host=host,
        headers={"X-XGW-Panel": "1", "Content-Type": "application/json", "Origin": origin})
    assert response.status == 200, text
    return json.loads(text)


def test_card_states(ts_rig):
    card = _card(ts_rig)
    assert card["state"] == "running" and card["name"] == NAME and card["address"] == "100.101.1.1"
    assert card["ssh"] is False and card["serve"] == {
        "on": False, "live": False, "url": f"https://{NAME}:8443/", "pending": False,
        "enable_url": ""}
    assert card["route"] == "direct" and card["cgnat"] == [] and card["override_dns"] is False
    ts_rig.panel.which = lambda name: None
    assert _card(ts_rig)["state"] == "absent"
    ts_rig.panel.which = lambda name: f"/usr/bin/{name}"
    tailscale.socket_path(ts_rig.paths).unlink()
    assert _card(ts_rig)["state"] == "stopped"


def test_card_is_not_asked_on_every_poll(ts_rig):
    _card(ts_rig)
    before = len(ts_rig.fake.calls)
    ts_rig.client.state()
    ts_rig.client.state()
    assert len(ts_rig.fake.calls) == before


def test_login_runs_in_the_background_and_shows_the_link_and_qr(ts_rig):
    fake = ts_rig.fake
    assert _ts_act(ts_rig, "login")["text"] == "Шлюз уже в tailnet"  # иначе — новый профиль
    assert not any(call[:2] == ("tailscale", "login") for call in fake.calls)
    fake.backend = "NeedsLogin"
    result = _ts_act(ts_rig, "login")
    assert result["ok"] and "кнопка и QR-код" in result["text"]
    assert ("tailscale", "login", "--timeout=15m") in fake.calls
    card = _card(ts_rig)
    assert card["state"] == "login" and card["auth_url"] == AUTH_URL and card["login_pending"]
    assert card["auth_qr"] == qr.encode(AUTH_URL)  # ссылка не замаскирована
    assert "уже начат" in _ts_act(ts_rig, "login")["text"]  # второй login не запускается
    fake.complete_login()
    card = _card(ts_rig)
    assert card["state"] == "running" and not card["auth_url"] and not card["login_pending"]


def test_ssh_switch(ts_rig):
    fake = ts_rig.fake
    result = _ts_act(ts_rig, "ssh", {"on": True})
    assert result["ok"] and fake.ssh is True and _card(ts_rig)["ssh"] is True
    assert _ts_act(ts_rig, "ssh", {"on": False})["ok"] and fake.ssh is False
    assert not _ts_act(ts_rig, "ssh", {"on": "yes"})["ok"]
    fake.fail["set"] = "permission denied"
    result = _ts_act(ts_rig, "ssh", {"on": True})
    assert not result["ok"] and "permission denied" in result["text"]
    fake.fail.clear()
    fake.backend = "NeedsLogin"
    assert _ts_act(ts_rig, "ssh", {"on": True})["text"] == "сначала войдите в Tailscale"


def test_tailnet_host_is_accepted_only_while_serve_is_on_from_the_panel(ts_rig):
    client = ts_rig.client
    assert client.request("GET", "/api/state", host=HOST)[0].status == 403
    result = _ts_act(ts_rig, "serve", {"on": True})
    assert result["ok"] and "Панель по tailnet включена" in result["text"]
    assert ts_rig.fake.serve == f"http://127.0.0.1:{ts_rig.panel.port}"
    assert ts_rig.saved()["tailscale"] == {"serve": NAME, "route": None}
    response, text = client.request("GET", "/api/state", host=HOST)
    assert response.status == 200 and json.loads(text)["tailscale"]["serve"]["live"] is True
    # Изменения — со страницы, открытой по https://имя:8443, а не по http.
    assert _ts_act(ts_rig, "route", {"route": "direct"}, host=HOST)["ok"]
    response, _text = client.request(
        "POST", "/api/tailscale/route", body={"route": "vpn"}, host=HOST,
        headers={"X-XGW-Panel": "1", "Origin": f"http://{HOST}"})
    assert response.status == 403
    # Чужое имя в tailnet и тот же адрес без порта — нет.
    for host in ("other.tailnet-1.ts.net:8443", NAME, f"{NAME}:443"):
        assert client.request("GET", "/api/state", host=host)[0].status == 403
    assert _ts_act(ts_rig, "serve", {"on": False})["ok"]
    assert ts_rig.fake.serve == "" and ts_rig.saved()["tailscale"]["serve"] == ""
    assert client.request("GET", "/api/state", host=HOST)[0].status == 403


def test_tailnet_login_sets_a_secure_cookie(ts_rig):
    _ts_act(ts_rig, "serve", {"on": True})
    code = panel_module.new_login(ts_rig.paths)
    response, _text = ts_rig.client.request("GET", f"/?login={code}", host=HOST)
    cookie = response.getheader("Set-Cookie")
    assert response.status == 303 and "Secure" in cookie and "SameSite=Strict" in cookie
    response, _text = ts_rig.client.request("GET", f"/?token={TOKEN}")
    assert "Secure" not in response.getheader("Set-Cookie")  # http://127.0.0.1 — без него


def test_serve_waits_for_https_in_the_tailnet(ts_rig):
    fake = ts_rig.fake
    fake.https_enabled = False
    result = _ts_act(ts_rig, "serve", {"on": True})
    assert result["ok"] and "разрешить HTTPS" in result["text"]
    card = _card(ts_rig)
    assert card["serve"]["on"] and card["serve"]["pending"]
    assert card["serve"]["enable_url"] == ENABLE_URL and card["serve"]["live"] is False
    assert ts_rig.client.request("GET", "/api/state", host=HOST)[0].status == 200
    fake.enable_https()
    card = _card(ts_rig)
    assert card["serve"]["live"] is True and not card["serve"]["pending"]


def test_failed_serve_leaves_the_host_closed(ts_rig):
    ts_rig.fake.fail["serve"] = "serve: HTTPS is disabled for this tailnet"
    result = _ts_act(ts_rig, "serve", {"on": True})
    assert not result["ok"] and "HTTPS is disabled" in result["text"]
    assert managed.load(ts_rig.store_path)[0]["tailscale"]["serve"] == ""
    assert ts_rig.client.request("GET", "/api/state", host=HOST)[0].status == 403
    # Снять Serve не вышло — Host всё равно закрывается.
    ts_rig.fake.fail.clear()
    _ts_act(ts_rig, "serve", {"on": True})
    ts_rig.fake.fail["serve"] = "no tailscaled"
    result = _ts_act(ts_rig, "serve", {"on": False})
    assert not result["ok"] and "не снят" in result["text"]
    assert ts_rig.client.request("GET", "/api/state", host=HOST)[0].status == 403


def test_renamed_gateway_keeps_the_panel_on_its_new_name(ts_rig):
    _ts_act(ts_rig, "serve", {"on": True})
    ts_rig.fake.name = "home.tailnet-1.ts.net"
    assert _card(ts_rig)["serve"]["url"] == "https://home.tailnet-1.ts.net:8443/"
    assert ts_rig.saved()["tailscale"]["serve"] == "home.tailnet-1.ts.net"
    renamed = "home.tailnet-1.ts.net:8443"
    assert ts_rig.client.request("GET", "/api/state", host=renamed)[0].status == 200
    assert ts_rig.client.request("GET", "/api/state", host=HOST)[0].status == 403


def test_route_switch_goes_to_the_config(ts_rig):
    result = _ts_act(ts_rig, "route", {"route": "vpn"})
    assert result["ok"] and "через VPN" in result["text"]
    cfg, _warnings = config.load(ts_rig.config_path)
    assert cfg.tailscale.route == "vpn" and cfg.managed.tailscale_route == "vpn"
    assert ts_rig.panel.daemon.poke.is_set()  # демон перезагрузит правила
    card = _card(ts_rig)
    assert card["route"] == "vpn" and card["route_panel"] is True
    assert not _ts_act(ts_rig, "route", {"route": "exit"})["ok"]


def test_k5_and_k6_are_fixed_only_by_a_press(ts_rig):
    fake = ts_rig.fake
    fake.cgnat_wan = fake.override_dns = True
    card = _card(ts_rig)
    assert card["cgnat"] == ["адрес 100.70.1.0/24", "DNS 100.64.0.53"]
    assert card["netfilter_off"] is False and card["override_dns"] is True
    assert not any(call[:2] == ("tailscale", "set") for call in fake.calls)
    assert _ts_act(ts_rig, "fix", {"name": "netfilter"})["ok"] and fake.netfilter == 0
    card = _card(ts_rig)
    assert card["netfilter_off"] is True and card["cgnat"] == []
    assert _ts_act(ts_rig, "fix", {"name": "dns"})["ok"] and fake.accept_dns is False
    assert _card(ts_rig)["override_dns"] is False
    assert not _ts_act(ts_rig, "fix", {"name": "everything"})["ok"]


def test_card_needs_root_and_a_running_tailscaled(ts_rig):
    ts_rig.root_problem = "нужны права root: sudo xgw panel"
    assert _ts_act(ts_rig, "ssh", {"on": True})["text"] == "нужны права root: sudo xgw panel"
    ts_rig.root_problem = None
    tailscale.socket_path(ts_rig.paths).unlink()
    assert "tailscaled не запущен" in _ts_act(ts_rig, "serve", {"on": True})["text"]
    ts_rig.panel.which = lambda name: None
    assert _ts_act(ts_rig, "login")["text"] == "Tailscale не установлен"
    assert ts_rig.fake.ssh is False and ts_rig.fake.serve == ""


# --- код входа на 15 минут ----------------------------------------------------------


def test_link_code_lives_fifteen_minutes_and_once(tmp_path):
    paths = Paths(root=tmp_path)
    paths.ensure()
    now = 1_800_000_000.0
    code = panel_module.new_login(paths, ttl=panel_module.LINK_TTL)
    stored = next(panel_module.login_dir(paths).iterdir())
    assert code not in stored.read_text(encoding="ascii")  # на диске — только срок
    stamp = stored.stat().st_mtime
    assert panel_module.use_login(paths, code, now=lambda: stamp + 14 * 60)
    assert not panel_module.use_login(paths, code, now=lambda: stamp + 14 * 60)  # один вход
    late = panel_module.new_login(paths, ttl=panel_module.LINK_TTL)
    assert not panel_module.use_login(paths, late, now=lambda: now + 10**6)
    short = panel_module.new_login(paths)  # обычный код — по-прежнему минута
    stamp = next(panel_module.login_dir(paths).iterdir()).stat().st_mtime
    assert not panel_module.use_login(paths, short, now=lambda: stamp + 120)


# --- бот: /panel ------------------------------------------------------------------


@pytest.fixture()
def bot_rig(tmp_path, monkeypatch):
    rig = BotRig(tmp_path, monkeypatch)
    yield rig
    rig.fake.stop()


def test_panel_command_sends_a_one_time_tailnet_link(bot_rig):
    off = bot_rig.ask("/panel")
    assert "Панель по tailnet выключена" in off and "«Tailscale»" in off
    managed.set_tailscale_serve(managed.path_for(bot_rig.config_path), NAME)
    bot_rig.reload()
    text = bot_rig.ask("/panel")
    prefix = f"https://{NAME}:8443/?login="
    assert prefix in text and "15 минут" in text and "один вход" in text
    code = text.split(prefix)[1].split()[0]
    assert panel_module.use_login(bot_rig.paths, code)  # ссылка целиком, не замаскирована
    assert not panel_module.use_login(bot_rig.paths, code)
    assert "/panel" in bot_rig.ask("/help")


def test_panel_command_only_in_a_private_chat(tmp_path, monkeypatch):
    rig = BotRig(tmp_path, monkeypatch, chat=str(GROUP))
    try:
        managed.set_tailscale_serve(managed.path_for(rig.config_path), NAME)
        rig.reload()
        assert rig.ask("/panel", chat=GROUP, kind="supergroup") == PRIVATE_ONLY
        assert not panel_module.login_dir(rig.paths).exists() or not any(
            panel_module.login_dir(rig.paths).iterdir())
    finally:
        rig.fake.stop()


# --- panel.json и xgw uninstall ------------------------------------------------------


def test_store_keeps_only_valid_tailscale_settings(tmp_path):
    path = tmp_path / "panel.json"
    path.write_text(json.dumps({"tailscale": {"serve": "Bad Name!", "route": "exit"}}), "utf-8")
    assert managed.load(path)[0]["tailscale"] == {"serve": "", "route": None}
    assert managed.set_tailscale_serve(path, "GW.Tailnet-1.ts.net.")
    assert not managed.set_tailscale_serve(path, NAME)  # то же имя
    assert managed.set_tailscale_route(path, "vpn")
    assert managed.load(path)[0]["tailscale"] == {"serve": NAME, "route": "vpn"}
    with pytest.raises(managed.ManagedError):
        managed.set_tailscale_serve(path, "evil.example/x")
    with pytest.raises(managed.ManagedError):
        managed.set_tailscale_route(path, "exit")


class _Quiet(Uninstaller):
    """Все шаги удаления, кроме Tailscale, — пустые: проверяется только он."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for name in ("_stop_units", "_rules", "_dnsmasq", "_nm", "_sysctl", "_sleep", "_ufw",
                     "_unit_files", "_launcher", "_user"):
            setattr(self, name, lambda: None)

    def _files(self, purge: bool) -> None:
        pass


def _uninstaller(tmp_path, fake, out, **kwargs) -> _Quiet:
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    return _Quiet(Config(), paths, runner=fake, out=out.append, proc_sys=tmp_path / "proc",
                  which=kwargs.get("which", lambda name: f"/usr/bin/{name}"))


def test_uninstall_removes_only_the_serve_xgw_enabled(tmp_path):
    fake, out = FakeTailscale(), []
    fake.serve, fake.ssh = "http://127.0.0.1:8781", True
    remover = _uninstaller(tmp_path, fake, out)
    store = managed.path_for(remover.paths.config_file)
    assert remover.run(keep_files=True) == 0  # откат переустановки Serve не снимает
    assert remover.run() == 0 and fake.serve  # XGW Serve не включал
    managed.set_tailscale_serve(store, NAME)
    assert remover.run(keep_files=True) == 0 and fake.serve
    assert remover.run() == 0
    assert fake.serve == "" and fake.ssh is True and fake.backend == "Running"
    assert managed.load(store)[0]["tailscale"]["serve"] == ""
    assert any("tailscaled, вход в tailnet и SSH не тронуты" in line for line in out)
    assert [call for call in fake.calls if call[0] == "tailscale"] == [
        ("tailscale", "serve", "--https=8443", "off")]


def test_uninstall_reports_a_serve_it_could_not_remove(tmp_path):
    fake, out = FakeTailscale(), []
    fake.fail["serve"] = "failed to connect to local tailscaled"
    remover = _uninstaller(tmp_path, fake, out)
    managed.set_tailscale_serve(managed.path_for(remover.paths.config_file), NAME)
    assert remover.run() == 1
    assert any("sudo tailscale serve --https=8443 off" in line for line in out)
    gone = _uninstaller(tmp_path / "2", FakeTailscale(), out, which=lambda name: None)
    managed.set_tailscale_serve(managed.path_for(gone.paths.config_file), NAME)
    assert gone.run() == 0 and any("Tailscale не установлен" in line for line in out)
