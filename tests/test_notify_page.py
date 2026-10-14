"""Уведомления (рабочий стол, Telegram) и страница статуса для домашней сети."""

import http.client
import json
import time
from urllib.parse import parse_qs

import pytest
from fakesys import FakeSystem

from xgw import config, fetch
from xgw.net.cmd import CommandError
from xgw.paths import Paths
from xgw.watch import notify, status_page
from xgw.watch.notify import Notifier

BOT_TOKEN = "123456789:AAFakeFakeFakeFakeFakeFakeFakeFakeFake"


# --- рабочий стол -----------------------------------------------------------------


@pytest.fixture()
def desktop(tmp_path):
    system = FakeSystem()
    system.sessions = [
        {"session": "c1", "uid": 120, "user": "gdm", "class": "greeter"},
        {"session": "3", "uid": 1000, "user": "andre", "class": "user"},
    ]
    system.session_props = {"Type": "wayland", "Active": "yes", "Remote": "no"}
    (tmp_path / "1000").mkdir()
    (tmp_path / "1000" / "bus").write_text("", encoding="ascii")
    return system, tmp_path


def test_desktop_user_is_the_graphical_session_owner(desktop):
    system, run_user = desktop
    assert notify.find_desktop_user(system, run_user) == ("andre", 1000)
    # Экран входа (class=greeter) не спрашиваем вовсе.
    assert system.commands("loginctl", "show-session") == [
        ("loginctl", "show-session", "3", "-p", "Type", "-p", "Active", "-p", "Remote")]


@pytest.mark.parametrize(
    "props",
    [{"Type": "tty", "Active": "yes", "Remote": "no"},
     {"Type": "x11", "Active": "yes", "Remote": "yes"}],
)
def test_text_and_remote_sessions_get_no_desktop_notification(desktop, props):
    system, run_user = desktop
    system.session_props = props
    assert notify.find_desktop_user(system, run_user) is None


def test_no_session_bus_or_no_loginctl_means_nobody_to_notify(desktop, tmp_path):
    system, run_user = desktop
    (run_user / "1000" / "bus").unlink()
    assert notify.find_desktop_user(system, run_user) is None
    system.refuse["loginctl"] = "программа не найдена"
    assert notify.find_desktop_user(system, run_user) is None


def test_desktop_sink_runs_notify_send_as_the_session_user(desktop):
    system, run_user = desktop
    notify.desktop_sink(system, run_user)("LEAK", "выход в RU при включённом перехвате")
    call = system.calls[-1]
    assert call[:5] == ("runuser", "-u", "andre", "--", "env")
    assert call[5] == f"DBUS_SESSION_BUS_ADDRESS=unix:path={(run_user / '1000' / 'bus').as_posix()}"
    assert call[6] == "notify-send" and "--urgency=critical" in call
    assert call[-2:] == ("XGW: трафик идёт мимо VPN", "выход в RU при включённом перехвате")
    notify.desktop_sink(system, run_user)("rotation", "замена участников")
    assert "--urgency=normal" in system.calls[-1]
    assert system.calls[-1][-2] == "XGW: замена сервера"


def test_desktop_sink_is_silent_when_nobody_is_logged_in(desktop):
    system, run_user = desktop
    system.sessions = []
    notify.desktop_sink(system, run_user)("LEAK", "текст")
    assert not system.commands("runuser")


# --- Telegram ---------------------------------------------------------------------


def _telegram_cfg() -> config.Config:
    cfg = config.Config()
    cfg.notify.telegram_bot_token = BOT_TOKEN
    cfg.notify.telegram_chat_id = "-100200300"
    return cfg


def test_telegram_goes_through_xray_and_falls_back_to_a_direct_marked_request(monkeypatch):
    cfg = _telegram_cfg()
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if "proxy" in kwargs:
            raise fetch.FetchError("не удалось получить api.telegram.org: прокси не отвечает")
        return fetch.FetchResult(200, {}, b'{"ok":true}', url)

    monkeypatch.setattr(notify.engine, "healthy_http_in", lambda cfg: ("127.0.0.1", 10809))
    notify.telegram_sink(cfg, mark=2, post=post)("ALL_DEAD", "нет живых участников")
    assert [("proxy" in call) for call in calls] == [True, False]
    assert calls[0]["proxy"] == ("127.0.0.1", 10809)
    assert calls[1]["mark"] == 2 and calls[1]["bootstrap"] == cfg.dns.bootstrap
    assert calls[0]["url"] == f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = parse_qs(calls[0]["data"].decode("ascii"))
    assert body["chat_id"] == ["-100200300"]
    assert body["text"] == ["XGW: все серверы недоступны\nнет живых участников"]


def test_telegram_failure_is_reported_without_the_token(monkeypatch, tmp_path):
    cfg = _telegram_cfg()
    monkeypatch.setattr(notify.engine, "healthy_http_in", lambda cfg: None)

    def post(url, **kwargs):
        return fetch.FetchResult(401, {}, b"{}", url)

    sink = notify.telegram_sink(cfg, mark=None, post=post)
    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        sink("LEAK", "текст")
    assert BOT_TOKEN not in str(error.value)

    # Notifier ошибку получателя не пробрасывает: событие записано, демон жив.
    notifier = Notifier(tmp_path / "state.db", 10, sinks=[sink])
    assert notifier.event("LEAK", "выход в RU", notify=True) is True


def test_sinks_follow_the_config():
    cfg = config.Config()
    assert len(notify.build_sinks(cfg, mark=None)) == 1  # рабочий стол включён по умолчанию
    cfg.notify.desktop = False
    assert notify.build_sinks(cfg, mark=None) == []
    cfg.notify.telegram_bot_token = BOT_TOKEN
    assert notify.build_sinks(cfg, mark=None) == []  # без chat_id отправлять некуда
    cfg.notify.telegram_chat_id = "1"
    assert len(notify.build_sinks(cfg, mark=None)) == 1


def test_broken_sink_does_not_break_the_others(tmp_path):
    seen: list[tuple[str, str]] = []

    def broken(kind, text):
        raise CommandError("runuser: программа не найдена")

    notifier = Notifier(tmp_path / "state.db", 10, sinks=[broken, lambda *a: seen.append(a)])
    assert notifier.event("LEAK", "выход в RU", notify=True)
    assert seen == [("LEAK", "выход в RU")]


def test_fetch_can_post(monkeypatch):
    sent: dict = {}

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.sock = None

        def request(self, method, path, body=None, headers=None):
            sent.update(method=method, path=path, body=body, headers=headers)

        def getresponse(self):
            class Response:
                status = 200

                def read(self, _limit):
                    return b"ok"

                def getheaders(self):
                    return []

            return Response()

    class FakeSocket:
        def close(self):
            pass

    monkeypatch.setattr(fetch.http.client, "HTTPConnection", FakeConnection)
    monkeypatch.setattr(fetch.marknet, "connect_marked", lambda *a, **k: FakeSocket())
    reply = fetch.fetch_url("http://203.0.113.7/send", data=b"a=1",
                            headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert reply.body == b"ok" and sent["method"] == "POST" and sent["body"] == b"a=1"
    fetch.fetch_url("http://203.0.113.7/get")
    assert sent["method"] == "GET" and sent["body"] is None


# --- страница статуса ---------------------------------------------------------------


SNAPSHOT = {
    "updated": time.time(), "daemon": True, "state": "DEGRADED", "since": time.time() - 600,
    "action": "замена участников", "xray": {"ok": True, "version": "26.3.27"},
    "capture": {"mode": "on", "lan_if": "lan0", "lan": True, "local": True,
                "bypass": ["192.168.50.20"], "loaded": True},
    "members": [
        {"tag": "proxy-nl-1", "name": "<script>alert(1)</script>", "alive": True, "delay_ms": 41},
        {"tag": "proxy-de-2", "name": "DE", "alive": False, "delay_ms": None},
    ],
    "spares": [{"tag": "spare-fr-3", "name": "FR", "verdict": "FROZEN", "bytes": 16384,
                "seconds": 5.2, "scanned": time.time()}],
    "selecting": ["proxy-nl-1"], "pin": None, "quota": {},
    "budget": {"probes_mb": 377.5, "scans_mb": 1.6, "total_mb": 379.1, "e2e_mb": 283.1,
               "limit_mb": 1024, "warnings": []},
    "events": [{"ts": time.time(), "kind": "rotation", "detail": "замена: a → <b>"}],
}
DEVICES = [
    {"ip": "192.168.50.20", "name": "tv", "mac": "02:00:00:00:00:20", "expires": 1791628983},
    {"ip": "192.168.50.139", "name": '"><img src=x>', "mac": "e2:1a:01:92:72:d5", "expires": 0},
]


def test_page_shows_state_servers_and_devices_and_escapes_foreign_text():
    page = status_page.render_page(SNAPSHOT, DEVICES)
    for text in ("DEGRADED", "proxy-nl-1 ←", "мёртв", "FROZEN", "16384 Б за 5.2 с",
                 "мимо VPN", "через VPN", "бессрочно", "~379.1 МБ в сутки"):
        assert text in page, text
    # Имена серверов приходят из подписки, имена устройств — от устройств.
    assert "<script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<img" not in page and "&lt;b&gt;" in page
    assert 'http-equiv="refresh"' in page


def test_page_shows_the_probe_url_warning_the_node_summary_and_the_monthly_traffic():
    """То же, что в панели и `xgw status`, видно и с телефона: не отвечает адрес проверки
    (серверы при этом работают), сводка разбора подписок, расход на проверки за месяц."""
    snapshot = {
        **SNAPSHOT, "state": "PROBE_TARGET_UNREACHABLE",
        "probe_target": "Внимание: все пробы падают с одинаковой ошибкой — вероятно, "
                        "недоступен сам probe.url (HTTP 403 <b>)",
        "nodes": {"members": 5, "spares": 65, "dropped": 4, "duplicates": 12},
        "budget": {**SNAPSHOT["budget"], "all_mb": 1169.5, "month_gb": 35.1},
    }
    page = status_page.render_page(snapshot, DEVICES)
    assert "недоступен сам probe.url (HTTP 403 &lt;b&gt;)" in page
    assert "Узлов: 5 активных, 65 запасных (отброшено 4 недоступных/служебных" in page
    assert "Всего ~1169.5 МБ в сутки, ~35.1 ГБ в месяц." in page
    # Прежний снимок (от демона старой версии) страницу не ломает.
    old = status_page.render_page(SNAPSHOT, DEVICES)
    assert "ГБ в месяц" not in old and "Узлов:" not in old


def test_page_without_status_and_with_stale_status():
    assert "ещё не записал статус" in status_page.render_page(None, [])
    stale = dict(SNAPSHOT, updated=time.time() - 3600)
    assert "Статус устарел" in status_page.render_page(stale, [])


def test_token_comes_from_config_or_is_generated_once(tmp_path):
    paths = Paths(root=tmp_path)
    cfg = config.Config()
    assert status_page.token_for(cfg, paths) == ""
    token = status_page.ensure_token(cfg, paths)
    assert len(token) >= 20 and status_page.ensure_token(cfg, paths) == token
    cfg.status.token = "свой-токен"
    assert status_page.ensure_token(cfg, paths) == "свой-токен"


def test_page_is_off_without_lan_or_when_disabled(tmp_path):
    paths = Paths(root=tmp_path)
    cfg = config.Config()
    assert status_page.StatusPage.from_config(cfg, paths) is None
    cfg.status.lan_page = True
    assert status_page.StatusPage.from_config(cfg, paths) is None  # LAN не настроен
    cfg.network.lan_if = "lan0"
    page = status_page.StatusPage.from_config(cfg, paths)
    assert page is not None and page.address == "192.168.50.1" and page.port == 8780
    assert page.token == paths.status_token_file.read_text(encoding="ascii").strip()


@pytest.fixture()
def served(tmp_path):
    page = status_page.StatusPage(Paths(root=tmp_path), "секрет-123", "127.0.0.1", port=0)
    page.snapshot = lambda: SNAPSHOT
    page.devices = lambda: DEVICES
    page.start()
    try:
        yield page
    finally:
        page.stop()


def _request(page, path, method="GET", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", page.port, timeout=5)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode("utf-8")
    finally:
        connection.close()


def test_server_requires_the_token(served):
    from urllib.parse import quote

    token = quote("секрет-123")
    assert _request(served, "/")[0] == 403
    assert _request(served, "/?token=wrong")[0] == 403
    assert _request(served, "/", headers={"Cookie": "xgw_token=wrong"})[0] == 403
    # Сам токен в cookie не подходит: в браузере хранится производное от него.
    assert _request(served, "/", headers={"Cookie": f"xgw_token={token}"})[0] == 403
    assert _request(served, "/status.json")[0] == 403

    code, headers, body = _request(served, f"/?token={token}")
    assert code == 303 and headers["Location"] == "/" and body == ""
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie

    assert cookie.isascii() and "секрет" not in cookie
    auth = {"Cookie": cookie.split(";")[0]}
    code, headers, body = _request(served, "/", headers=auth)
    assert code == 200 and "DEGRADED" in body and "секрет-123" not in body
    assert headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    code, _, body = _request(served, "/status.json", headers=auth)
    assert code == 200 and json.loads(body)["devices"][0]["name"] == "tv"
    assert _request(served, "/missing", headers=auth)[0] == 404


def test_server_is_read_only(served):
    from urllib.parse import quote

    path = f"/?token={quote('секрет-123')}"
    for method in ("POST", "PUT", "DELETE"):
        assert _request(served, path, method=method)[0] == 501
    code, _, body = _request(served, "/", method="HEAD",
                             headers={"Cookie": "xgw_token=wrong"})
    assert code == 403 and body == ""
