"""Значок XGW в трее (0.1.18, ТЗ R9): модель и меню без демона, сторож, вход панели для трея,
установка и удаление. Окно Qt (trayapp.py) здесь не запускается — его проверяет ТЗ на машине."""

import json
import os
import types
from pathlib import Path

import pytest
from test_install import Box
from test_panel import Rig

from xgw import desktop, install, tray
from xgw.paths import Paths

# --- модель ----------------------------------------------------------------------------

STATE = {
    "enabled": True, "version": "0.1.18", "state": "HEALTHY", "xray": "26.10.21",
    "singbox": "1.14.3", "core_job": False,
    "main": {"name": "Германия 1", "country": "DE", "mbps": 85.0, "pinned": False},
    "speed_on": True, "busy": {"cores": False, "speed": False},
    "panel": "http://127.0.0.1:8781/",
}


def test_icon_follows_the_gateway_state():
    assert tray.kind(STATE) == "ok"
    assert tray.kind({**STATE, "state": "DEGRADED"}) == "warn"
    assert tray.kind({**STATE, "state": "WAN_DOWN"}) == "down"
    assert tray.kind({**STATE, "core_job": True}) == "job"  # идёт обновление ядра
    assert tray.kind(None) == "off" and tray.kind({**STATE, "state": None}) == "off"


def test_tooltip_tells_state_cores_and_the_chosen_server():
    text = tray.tooltip(STATE)
    assert text.splitlines()[0] == "XGW 0.1.18: в порядке"
    assert "Xray 26.10.21, sing-box 1.14.3" in text
    assert "основной: Германия 1 [DE], 85 Мбит/с" in text
    pinned = tray.tooltip({**STATE, "main": {**STATE["main"], "pinned": True, "mbps": 8.5}})
    assert "выбран вручную: Германия 1 [DE], 8,5 Мбит/с" in pinned
    assert "идёт обновление" in tray.tooltip({**STATE, "core_job": True})
    assert tray.tooltip(None, "панель не отвечает") == (
        "XGW: нет связи с панелью — панель не отвечает")


def test_menu_without_the_daemon_and_while_busy():
    labels = [label for _action, label, _on in tray.menu(STATE)]
    assert labels == ["Открыть панель", "Проверить выпуски ядер", "Замерить скорость сейчас",
                      "О программе", "Выход"]
    assert all(on for _action, _label, on in tray.menu(STATE))
    offline = dict((action, on) for action, _label, on in tray.menu(None))
    assert offline == {"open": True, "cores/check": False, "speed": False, "about": True,
                       "quit": True}
    busy = dict((action, on) for action, _label, on in tray.menu(
        {**STATE, "busy": {"cores": True, "speed": False}}))
    assert busy["cores/check"] is False and busy["speed"] is True
    off = dict((action, on) for action, _label, on in tray.menu({**STATE, "speed_on": False}))
    assert off["speed"] is False
    assert "«Выход» закрывает только значок" in tray.about(STATE)


def test_the_watchdog_restarts_a_crashed_icon_and_stops_on_quit():
    codes = iter([1, -11, tray.NO_TRAY, 0])
    pauses: list[float] = []
    lines: list[str] = []
    assert tray.supervise(["xgw", "tray", "--run"], spawn=lambda argv: next(codes),
                          sleep=pauses.append, log=lines.append) == 0
    assert pauses == [2.0, 4.0, 8.0]  # серия падений — пауза растёт
    assert "трея в сеансе нет" in lines[2]
    assert tray.supervise(["x"], spawn=lambda argv: tray.NOT_SET, sleep=pauses.append) == (
        tray.NOT_SET)  # не настроен — перезапуск не поможет

    def gone(argv):
        raise FileNotFoundError("нет /usr/local/bin/xgw")

    assert tray.supervise(["x"], spawn=gone, sleep=pauses.append, log=lines.append) == (
        tray.NOT_SET)
    clock = iter([0.0, 400.0, 400.0, 401.0])
    pauses.clear()
    tray.supervise(["x"], spawn=lambda argv: 1, sleep=pauses.append, clock=lambda: next(clock),
                   log=lines.append, rounds=2)
    assert pauses == [2.0, 4.0]


class PageClient:
    """Клиент панели: «page» из /api/tray по очереди (последнее повторяется)."""

    def __init__(self, *pages: dict) -> None:
        self.pages = list(pages)

    def state(self) -> dict:
        return {**STATE, "page": self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]}


def test_open_panel_raises_a_visible_tab_instead_of_a_new_one():
    """Заказчик: «можно сделать незаметным открытие второй вкладки?» Вкладка на экране —
    её окно выводит KWin; новая вкладка — только если вывести некого или нечем."""
    opened: list[str] = []
    asked: list[bool] = []  # просили ли KWin вывести окно
    ticks = iter(range(200))

    def run(client, raised=True):
        opened.clear()
        asked.clear()
        return tray.open_panel("http://p/", client, raise_it=lambda: asked.append(True) or raised,
                               launch=opened.append, sleep=lambda _s: None,
                               clock=lambda: next(ticks) * 0.3)

    assert run(PageClient({"seen": 1.0, "focused": 1.0})) == "raised" and opened == []
    # Не в фокусе — ждать, пока выведенная вкладка скажет о фокусе.
    assert run(PageClient({"seen": 1.0, "focused": 40.0}, {"seen": 0.1, "focused": 0.1})) == (
        "raised")
    assert run(PageClient({"seen": 1.0, "focused": None})) == "opened"  # окно не нашлось
    assert opened == ["http://p/"]
    assert run(PageClient({"seen": 30.0, "focused": 30.0})) == "opened"  # вкладку не видно
    assert asked == []
    # Окно свёрнуто: вкладка скрылась после опроса — выводится, и вкладка говорит о фокусе.
    minimized = {"seen": 60.0, "focused": 60.0, "hidden": 59.0, "closed": None}
    assert run(PageClient(minimized, {**minimized, "seen": 0.1, "focused": 0.1})) == "raised"
    # Вкладку закрыли — новая сразу, без попытки вывести окно.
    assert run(PageClient({**minimized, "closed": 58.0})) == "opened" and asked == []
    # «Скрылась» дошла на 0,2 с позже «закрылась» (испытания 25.10.2026) — тоже закрыта.
    assert run(PageClient({**minimized, "hidden": 3.2, "closed": 3.4})) == "opened"
    assert asked == []
    assert run(PageClient({"seen": 1.0, "focused": 1.0}), raised=False) == "opened"  # не KDE
    assert run(None) == "opened"  # нет файла значка


# --- один значок на человека (испытания 25.10.2026: три установки — три значка) ---------------


def test_a_second_icon_does_not_start(tmp_path):
    runtime = tmp_path / "run-user"
    runtime.mkdir()
    path = tray.lock_path(tmp_path / "home", {"XDG_RUNTIME_DIR": str(runtime)})
    assert path == runtime / tray.LOCK_NAME
    first = tray.take_lock(path)
    assert first is not None and path.read_text(encoding="ascii").strip() == str(os.getpid())
    assert tray.take_lock(path) is None  # значок уже запущен
    first.close()
    again = tray.take_lock(path)
    assert again is not None
    again.close()
    # Без XDG_RUNTIME_DIR (и /run/user/UID) — рядом с файлом значка.
    home = tmp_path / "home"
    fallback = tray.lock_path(home, {"XDG_RUNTIME_DIR": str(tmp_path / "нет")})
    assert fallback in (home / ".config/xgw" / tray.LOCK_NAME,
                        Path(f"/run/user/{os.getuid()}") / tray.LOCK_NAME)


def _proc(tmp_path, processes: dict[str, list[str]]):
    proc = tmp_path / "proc"
    for pid, words in processes.items():
        (proc / pid).mkdir(parents=True)
        (proc / pid / "cmdline").write_bytes(b"".join(w.encode() + b"\0" for w in words))
    return proc


def test_replace_closes_every_old_icon_watchdogs_first(tmp_path):
    """--replace находит прежние значки по /proc — и те, что запущены до блокировки: сначала
    сторожа (сторож до этой версии поднял бы свой значок снова), потом сами значки."""
    proc = _proc(tmp_path, {
        "100": ["/usr/bin/python3", "-I", "/usr/local/bin/xgw", "tray", "--run"],
        "101": ["/usr/bin/python3", "-I", "/usr/local/bin/xgw", "tray"],
        "102": ["/usr/bin/python3", "-m", "xgw", "tray", "--run"],
        "103": ["systemd-run", "--user", "--", "/usr/local/bin/xgw", "tray", "--replace"],
        "104": ["bash", "-c", "/usr/local/bin/xgw tray"],
        "105": ["/usr/bin/python3", "-I", "/usr/local/bin/xgw", "status"],
        "106": ["/usr/bin/python3", "-I", "/usr/local/bin/xgw", "tray", "--replace"],  # сам
        "107": [],
        "108": ["/usr/bin/python3", "-I", "/usr/local/bin/xgw", "tray", "--open", "http://x/"],
    })
    (proc / "self").mkdir()
    assert tray.other_instances(proc, me=106) == [101, 100, 102]
    assert tray.other_instances(proc, uid=os.getuid() + 1, me=106) == []  # чужие — не трогать
    killed: list[tuple[int, int]] = []
    closed = tray.replace(proc, kill=lambda pid, sig: killed.append((pid, sig)), me=106)
    assert closed == [101, 100, 102] and [pid for pid, _sig in killed] == closed
    assert {sig for _pid, sig in killed} == {tray.signal.SIGTERM}


def test_tray_command_starts_only_one_icon(tmp_path, monkeypatch):
    path = tmp_path / tray.LOCK_NAME
    monkeypatch.setattr(tray, "lock_path", lambda home=None, environ=None: path)
    monkeypatch.setattr(tray.signal, "signal", lambda *args: None)
    started: list[list[str]] = []
    monkeypatch.setattr(tray, "supervise",
                        lambda argv, spawn=None: started.append(argv) or 7)
    held = tray.take_lock(path)
    assert tray.main([]) == 0 and started == []  # уже запущен — второй не встаёт

    def release(proc=None, kill=None, me=None):
        held.close()  # прежний значок закрылся
        return [101]

    monkeypatch.setattr(tray, "replace", release)
    assert tray.main(["--replace"]) == 7 and len(started) == 1
    assert started[0][-2:] == ["tray", "--run"]
    seen: list[list[str]] = []
    monkeypatch.setattr(tray, "main", lambda argv: seen.append(argv) or 0)
    from xgw import cli

    assert cli.main(["tray", "--replace"]) == 0 and seen == [["--replace"]]


def test_login_autostart_replaces_an_icon_left_from_the_last_session(tmp_path, monkeypatch):
    """Сторож прошлого сеанса может пережить выход (Ubuntu не закрывает процессы человека) и
    держать блокировку со старым XAUTHORITY — его значок в новый сеанс не встанет. Вход в сеанс
    запускает `xgw tray --replace`, как установка: значок нового сеанса главнее."""
    entry = tray.desktop_entry(Path("/usr/local/bin/xgw"), Path("/opt/xgw/xgw.svg"))
    command = next(line for line in entry.splitlines() if line.startswith("Exec="))
    assert command == "Exec=/usr/local/bin/xgw tray --replace"
    path = tmp_path / tray.LOCK_NAME
    monkeypatch.setattr(tray, "lock_path", lambda home=None, environ=None: path)
    monkeypatch.setattr(tray.signal, "signal", lambda *args: None)
    started: list[list[str]] = []
    monkeypatch.setattr(tray, "supervise",
                        lambda argv, spawn=None: started.append(argv) or 0)
    stale = tray.take_lock(path)  # сторож прошлого сеанса
    closed: list[int] = []

    def close_stale(proc=None, kill=None, me=None):
        stale.close()
        closed.append(101)
        return [101]

    monkeypatch.setattr(tray, "replace", close_stale)
    assert tray.main(command.split()[2:]) == 0
    assert closed == [101] and len(started) == 1


def test_user_file_round_trip(tmp_path):
    home = tmp_path / "home"
    with pytest.raises(tray.TrayError, match="sudo xgw install"):
        tray.read_user_file(home)
    path = tray.write_user_file(home, os.getuid(), os.getgid(), 8781, "секрет")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert tray.read_user_file(home) == (8781, "секрет")
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(tray.TrayError, match="переустановите"):
        tray.read_user_file(home)


# --- вход панели для трея ----------------------------------------------------------------


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    yield instance
    instance.panel.stop()


def test_tray_endpoint_needs_its_own_token_and_does_only_two_things(rig):
    token = tray.ensure_token(rig.paths)
    client = tray.Client(rig.panel.port, "wrong-token")
    with pytest.raises(tray.TrayError, match="401"):
        client.state()
    client = tray.Client(rig.panel.port, token)
    state = client.state()
    assert state["state"] == "HEALTHY" and state["enabled"] is True
    assert set(state) >= {"version", "xray", "singbox", "core_job", "main", "busy", "panel"}
    assert client.act("cores/check")["ok"] and rig.daemon.asked == ["cores"]
    assert client.act("speed")["ok"] and rig.daemon.asked == ["cores", "speed"]
    with pytest.raises(tray.TrayError):
        client.act("power")
    # Токен трея не открывает панель: состояние панели и её действия — только по cookie.
    response, _text = rig.client.request("GET", "/api/state", headers={tray.HEADER: token})
    assert response.status == 401
    response, _text = rig.client.request(
        "POST", "/api/tray/power", body={}, headers={tray.HEADER: token})
    assert response.status == 404
    events = rig.panel._db("SELECT detail FROM events")
    assert any("значок в трее" in row["detail"] for row in events)


# --- установка и удаление ------------------------------------------------------------------


@pytest.fixture()
def box(tmp_path):
    return Box(tmp_path)


def test_install_sets_up_the_tray_for_the_person_and_uninstall_removes_it(box, tmp_path,
                                                                         monkeypatch):
    home = tmp_path / "home" / "anna"
    person = desktop.User("anna", os.getuid())
    monkeypatch.setattr(desktop, "invoking_user", lambda environ=None: person)
    monkeypatch.setattr(desktop, "graphical", lambda user, runner=None: True)
    monkeypatch.setattr(install.pwd, "getpwuid", lambda uid: types.SimpleNamespace(
        pw_dir=str(home), pw_gid=os.getgid()))
    box.has_qt = False
    assert box.install() == 0, box.text()
    assert "python3-pyqt6" in box.system.packages
    autostart = box.paths.root / tray.AUTOSTART
    text = autostart.read_text(encoding="utf-8")
    assert f"Exec={box.paths.launcher} tray --replace\n" in text
    assert "X-KDE-autostart-after=panel" in text
    port, token = tray.read_user_file(home)
    assert port == box.cfg.panel.port and token == tray.read_token(box.paths)
    # --replace: значок прошлой установки уступает место новому (иначе их по одному на установку).
    assert any(call[:2] == ("systemd-run", "--user") and call[-2:] == ("tray", "--replace")
               for call in box.system.calls)
    assert "значок в трее для anna" in box.text()
    box.out.clear()
    assert box.uninstall() == 0, box.text()
    assert not autostart.exists() and not tray.user_file(home).exists()
    assert not tray.token_file(box.paths).exists()
    assert ("pkill", "-f", f"{box.paths.launcher} tray") in box.system.calls


def test_tray_disabled_removes_the_autostart_and_qt_failure_is_only_a_warning(box):
    box.has_qt = False
    box.system.refuse["python3-pyqt6"] = "нет пакета"
    assert box.install() == 0, box.text()
    assert "значок в трее не поставлен" in box.text()
    assert not (box.paths.root / tray.AUTOSTART).exists()
    box.has_qt = True
    assert box.install() == 0
    assert (box.paths.root / tray.AUTOSTART).exists()
    box.cfg.tray.enabled = False
    assert box.install() == 0
    assert not (box.paths.root / tray.AUTOSTART).exists()
    assert "значок в трее выключен" in box.text()


def test_paths_root_keeps_the_autostart_inside_the_test_root(tmp_path):
    paths = Paths(root=tmp_path)
    assert str(paths.root / tray.AUTOSTART).startswith(str(tmp_path))
    assert json.loads(json.dumps(STATE))["main"]["country"] == "DE"
