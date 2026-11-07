"""Окно XGW на Qt (offscreen): клиент и окно против настоящей панели демо-сцены
(tests/panel_demo.py, watch/panel.py по HTTP на 127.0.0.1). Без PyQt6 — пропускаются."""

import hashlib
import hmac
import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

import panel_demo  # noqa: E402

from xgw.gui import app as gui_app  # noqa: E402
from xgw.gui import client as clienting  # noqa: E402
from xgw.gui import login, model, theme, window  # noqa: E402
from xgw.watch import panel as paneling  # noqa: E402

COOKIE = hmac.new(panel_demo.TOKEN.encode(), b"xgw-panel", hashlib.sha256).hexdigest()


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait(qapp, condition, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("не дождались")
        qapp.processEvents()
        time.sleep(0.02)


@pytest.fixture()
def demo(tmp_path):
    panel = panel_demo.build(tmp_path, _free_port(), "work")
    panel.start()
    # Статус демо пишет поток раз в 2 с; до первой записи у панели ещё нет состояния
    # шлюза — тесты ждали бы его наперегонки (отчёт gui-look: тест падал через раз).
    deadline = time.monotonic() + 10
    while panel.state().get("state") != "DEGRADED" and time.monotonic() < deadline:
        time.sleep(0.05)
    yield panel
    panel.stop()


OPEN: list = []  # клиенты теста — закрываются после него (ответы не придут к удалённым)


@pytest.fixture(autouse=True)
def _close_clients(qapp):
    yield
    while OPEN:
        OPEN.pop().close()
    qapp.processEvents()


def _client(port: int, cookie: str = COOKIE, session: bool = True) -> clienting.ApiClient:
    client = clienting.ApiClient(model.Session(port, cookie) if session else None,
                                 rng=lambda: 0.5)
    OPEN.append(client)
    return client


def test_client_polls_one_request_at_a_time_and_acts_once(qapp, demo):
    client = _client(demo.port)
    states, done = [], []
    client.stateReceived.connect(states.append)
    client.actionFinished.connect(lambda *args: done.append(args))
    client.start()
    client.poll()
    client.poll()  # первый ещё идёт: второго запроса нет
    assert client.gate.issued == 1
    wait(qapp, lambda: states)
    assert states[0]["state"] == "DEGRADED" and client.link == clienting.LINK_OK
    assert client.act("scan") and not client.act("scan")
    wait(qapp, lambda: done)
    assert done[0][0] == "scan" and done[0][1] is True
    client.stop()


def test_wrong_cookie_asks_for_login_and_stops_polling(qapp, demo):
    client = _client(demo.port, "0" * 64)
    links = []
    client.linkChanged.connect(lambda link, text: links.append(link))
    client.start()
    wait(qapp, lambda: links)
    assert links == [clienting.LINK_AUTH] and not client.timer.isActive()


def test_lost_panel_backs_off_instead_of_storming(qapp):
    client = _client(_free_port())
    links = []
    client.linkChanged.connect(lambda link, text: links.append((link, text)))
    client.start()
    wait(qapp, lambda: links)
    assert links[0][0] == clienting.LINK_OFFLINE and links[0][1].startswith("Нет связи")
    assert client.gate.issued == 1
    assert 1500 <= client.timer.remainingTime() <= 2100  # пауза 2 с, а не 3 с опроса
    client.stop()


def test_login_code_becomes_the_panel_cookie_once(qapp, demo):
    client = _client(demo.port)
    code = paneling.new_login(demo.paths)
    results = []
    client.exchange(demo.port, code, lambda session, text: results.append((session, text)))
    wait(qapp, lambda: results)
    assert results[0][0] == model.Session(demo.port, COOKIE)
    client.exchange(demo.port, code, lambda session, text: results.append((session, text)))
    wait(qapp, lambda: len(results) == 2)
    assert results[1][0] is None and "не подошёл" in results[1][1]


def test_login_flow_reads_the_code_from_the_admin_command(qapp, demo):
    client = _client(demo.port)
    code = paneling.new_login(demo.paths)
    line = json.dumps({"port": demo.port, "code": code})
    flow = login.LoginFlow(client.exchange,
                           command=lambda: (sys.executable, ["-c", f"print({line!r})"]))
    results = []
    flow.finished.connect(lambda session, text: results.append((session, text)))
    assert flow.start() and not flow.start()
    wait(qapp, lambda: results)
    assert results[0][0] == model.Session(demo.port, COOKIE)
    dismissed = login.LoginFlow(client.exchange,
                                command=lambda: ("/bin/sh", ["-c", "exit 126"]))
    dismissed.finished.connect(lambda session, text: results.append((session, text)))
    dismissed.start()
    wait(qapp, lambda: len(results) == 2)
    assert results[1] == (None, "")
    missing = login.LoginFlow(client.exchange, command=lambda: "нет pkexec")
    missing.finished.connect(lambda session, text: results.append((session, text)))
    assert not missing.start() and results[2] == (None, "нет pkexec")


def _window(client, tmp_path):
    flow = login.LoginFlow(client.exchange, command=lambda: "нет pkexec")
    return window.MainWindow(client, flow, tmp_path / "gui.json")


def test_window_shows_real_state_and_keeps_working_when_resized(qapp, demo, tmp_path):
    client = _client(demo.port)
    win = _window(client, tmp_path)
    win.show()
    client.start()
    wait(qapp, lambda: win.state is not None)
    assert "Часть серверов недоступна" in win.chip.text() and win.chip.text().startswith("!")
    overview = win.overview
    assert overview.power.text() == "Выключить VPN" and overview.power.isEnabled()
    assert overview.metrics["speed"].text() == "87,3 Мбит/с"
    assert overview.metrics["rtt"].text() == "29 мс"
    assert overview.metrics["delay"].text() == "84 мс"
    assert "Xray 26.3.27" in overview.versions.text()
    assert overview.word.text() == "ЗАЩИЩЕНО" and overview.orb.tone == "ok"
    rows = overview.members.visible_rows()
    assert len(rows) == 5 and rows[0].is_main and not any(r.is_main for r in rows[1:])
    assert rows[0].name.text() == "Нидерланды · Амстердам 1"
    assert len(overview.spares.visible_rows()) == 4
    assert overview.alert.isVisible() and overview.fix_buttons["scan"].isVisible()
    for row in range(len(window.SECTIONS)):
        win.nav.setCurrentRow(row)
        assert win.stack.currentWidget() is win.pages[window.SECTIONS[row][0]]
    win.nav.setCurrentRow(0)
    win.resize(*window.MIN_SIZE)
    qapp.processEvents()
    shots = os.environ.get("XGW_GUI_SHOTS")
    if shots:
        for choice in ("light", "dark"):
            theme.apply(qapp, choice)
            for size in (window.MIN_SIZE, window.START_SIZE):
                win.resize(*size)
                qapp.processEvents()
                win.recolor()
                qapp.processEvents()
                win.grab().save(str(Path(shots) / f"overview-{choice}-{size[0]}x{size[1]}.png"))
            win.nav.setCurrentRow(1)
            qapp.processEvents()
            win.grab().save(str(Path(shots) / f"pending-{choice}.png"))
            win.nav.setCurrentRow(0)
    client.stop()
    win.close()


def test_power_click_goes_to_the_panel_once(qapp, demo, tmp_path):
    client = _client(demo.port)
    win = _window(client, tmp_path)
    win.show()
    client.start()
    wait(qapp, lambda: win.state is not None)
    done = []
    client.actionFinished.connect(lambda *args: done.append(args))
    win.overview.power.click()
    assert client.actions.busy("power") and not win.overview.power.isEnabled()
    win.overview.power.click()  # пока ждём ответа — второй раз не уходит
    wait(qapp, lambda: done)
    assert len(done) == 1 and done[0][0] == "power" and done[0][1] is True
    wait(qapp, lambda: win.overview.power.text() == "Включить VPN")
    client.stop()
    win.close()


def test_window_without_login_offers_to_sign_in(qapp, tmp_path):
    client = _client(0, session=False)
    win = _window(client, tmp_path)
    win.show()
    client.start()
    wait(qapp, lambda: win.stack.currentWidget() is win.login_page)
    win.login_page.button.click()
    wait(qapp, lambda: win.login_page.error.text() == "нет pkexec")
    client.stop()
    win.close()


def test_second_start_raises_the_first_window(qapp):
    name = f"xgw-gui-test-{os.getpid()}"
    raised = []
    first = gui_app.SingleInstance(name)
    assert first.listen(lambda: raised.append(1))
    assert gui_app.SingleInstance(name).notify_running()
    wait(qapp, lambda: raised)
    first.server.close()
    assert not gui_app.SingleInstance(name + "-none").notify_running()


def test_new_version_replaces_the_open_window_of_the_old_one(qapp):
    name = f"xgw-gui-test-swap-{os.getpid()}"
    raised, replaced = [], []
    old = gui_app.SingleInstance(name, "old")
    assert old.listen(lambda: raised.append(1), lambda: replaced.append(1))
    assert gui_app.SingleInstance(name, "old").notify_running()  # та же версия — вперёд
    wait(qapp, lambda: raised)
    assert not gui_app.SingleInstance(name, "new").notify_running()  # другая — замена
    assert replaced and not old.server.isListening()
    fresh = gui_app.SingleInstance(name, "new")
    assert fresh.listen(lambda: None)
    fresh.server.close()
    assert len(gui_app.code_stamp()) == 16


def test_status_word_hint_covers_the_row_and_closing_quits(qapp, demo, tmp_path):
    """Отчёт gui-s3: подсказка у точки в 10 пикселей не показалась, а после закрытия окна
    процесс остался. Подсказка — у всей правой колонки и строки; закрытие — выход."""
    import faulthandler

    client = _client(demo.port)
    win = _window(client, tmp_path)
    quits = []

    class App:
        def quit(self):
            quits.append(1)

    gui_app._watch_exit(win, App())
    win.resize(1024, 720)
    win.show()
    client.start()
    wait(qapp, lambda: win.overview.members.visible_rows())
    row = win.overview.members.visible_rows()[0]
    assert row.toolTip() and row.holder.toolTip() == row.dot.toolTip() == row.toolTip()
    win.close()
    faulthandler.cancel_dump_traceback_later()  # в тесте процесс не завершать
    assert quits == [1]


def test_servers_page_acts_through_the_panel(qapp, demo, tmp_path):
    client = _client(demo.port)
    win = _window(client, tmp_path)
    win.show()
    client.start()
    wait(qapp, lambda: win.state is not None)
    win.nav.setCurrentRow(1)
    page = win.servers
    wait(qapp, lambda: page.groups and any(not w.isHidden() for w in page.groups.values()))
    cards = [card for group in page.groups.values() for card in group.cards
             if not card.isHidden() and card.item is not None]
    germany = next(card for card in cards if card.item.code == "DE")
    done = []
    client.actionFinished.connect(lambda *args: done.append(args))
    germany.choose.click()
    wait(qapp, lambda: done)
    assert done[-1][0] == "pin" and done[-1][1] is True
    page.priority(germany.item, "high")
    wait(qapp, lambda: len(done) >= 2)
    assert done[-1][0].startswith("priority:") and done[-1][1] is True
    page.confirm = lambda title, text, yes: True
    page.remove(germany.item)
    wait(qapp, lambda: len(done) >= 3)
    assert done[-1][0] == "servers" and done[-1][1] is True
    page.search.setText("финл")
    assert all(card.item.code == "FI" for group in page.groups.values() if not group.isHidden()
               for card in group.cards if not card.isHidden())
    page.tab_buttons[1].click()
    assert page.pool_observe.isVisible() and not page.pool_house.isVisible()
    client.stop()
    win.close()


def test_subscriptions_page_adds_a_link_and_clears_the_field_only_on_success(qapp, demo,
                                                                             tmp_path):
    client = _client(demo.port)
    win = _window(client, tmp_path)
    win.show()
    client.start()
    wait(qapp, lambda: win.state is not None)
    win.nav.setCurrentRow(2)
    page = win.subscriptions
    wait(qapp, lambda: page.cards and not page.cards[0][0].isHidden())
    assert page.cards[0][1]["name"].text() == "main" and page.cards[0][1]["edit"].isHidden()
    done = []
    client.actionFinished.connect(lambda *args: done.append(args))
    page.text.setPlainText("это не ссылка")
    page.add.click()
    wait(qapp, lambda: done)
    assert done[-1][1] is False and page.text.toPlainText() == "это не ссылка"
    page.text.setPlainText("trojan://secret@example.org:443#Новый")
    page.add.click()
    wait(qapp, lambda: len(done) >= 2)
    assert done[-1][1] is True and page.text.toPlainText() == ""
    client.stop()
    win.close()
