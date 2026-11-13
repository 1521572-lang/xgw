"""Границы нового окна: выбор источника, подтверждение команды, stale и standalone."""
import copy
import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XGW_UI_QT"] = "PyQt6"
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
pytest.importorskip("PyQt6.QtSvg")

from vpn_ui.qt import QtCore, Signal  # noqa: E402
from vpn_ui.xgw.backend import GuardedApiClient, XgwBridge  # noqa: E402
from vpn_ui.xgw.catalog import POOL, catalog, filtered  # noqa: E402
from vpn_ui.xgw.window import XgwWindow  # noqa: E402
from xgw.gui import client, model  # noqa: E402


class Client(QtCore.QObject):
    stateReceived = Signal(dict)
    linkChanged = Signal(str, str)
    busyChanged = Signal(str, bool)
    actionFinished = Signal(str, bool, str)

    def __init__(self):
        super().__init__()
        self.actions = model.ActionGuard()
        self.session = model.Session(12345, "fixture")
        self.sent = []
        self.gets = []
        self.visible = True

    def act(self, name, body, key):
        self.sent.append((name, body))
        self.actions.begin(key)
        return True

    def fetch(self, kind, path, done):
        self.gets.append((kind, path, done))
        return True

    def close(self):
        pass

    def set_visible(self, _value):
        pass

    def poll_soon(self, _seconds):
        pass


class Login(QtCore.QObject):
    finished = Signal(object, str)
    process = None


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def scene(qapp):
    data = json.loads((Path(__file__).parent / "fixtures/gui/state-work.json").read_text())
    data.update(now=time.time(), updated=time.time())
    c = Client()
    b = XgwBridge(c)
    b.link = client.LINK_OK
    b.on_state(data)
    yield c, b, data
    b.close()


def test_catalog_sources_do_not_mix_and_empty_subscription_is_visible(scene):
    _c, _b, data = scene
    data["subscriptions"].append({"name": "Пустая", "error": "Не удалось обновить"})
    sources, entries = catalog(data)
    assert any(source.id == "sub:Пустая" and "Не удалось" in source.detail for source in sources)
    assert sources[-1].id == POOL
    for source in sources:
        assert all(item.source == source.id
                   for item in filtered(entries, source.id, "", "all", "name"))
    assert any(item.source == "sub:manual" for item in entries)


def test_pin_waits_for_actual_snapshot_and_stale_prevents_new_commands(scene):
    c, b, data = scene
    item = next(item for item in b.entries if item.choosable and not item.pool)
    b.select(item.id)
    assert c.sent == [("pin", {"tag": item.id, "ttl": "forever"})]
    b.select(item.id)
    assert len(c.sent) == 1
    c.actions.end("pin")
    c.actionFinished.emit("pin", True, "OK")
    b.on_state(data)
    assert b.busy  # Старый снимок не подтверждает pin, даже после HTTP 200.
    changed = copy.deepcopy(data)
    changed["pin"] = {"tag": item.id}
    b.on_state(changed)
    assert not b.busy
    b.on_link(client.LINK_OFFLINE, "Нет связи")
    b.power()
    b.automatic("sub:main")
    assert len(c.sent) == 1


def test_window_sources_details_tools_and_standalone(scene, tmp_path, qapp):
    c, b, data = scene
    w = XgwWindow(b, Login(), tmp_path / "session")
    w.resize(1100, 760)
    w.show()
    qapp.processEvents()
    sidebar = w.sidebar
    for index in range(sidebar.sources.count()):
        source = sidebar.sources.item(index).data(QtCore.Qt.ItemDataRole.UserRole)
        if source == POOL:
            continue
        sidebar.sources.setCurrentRow(index)
        assert all(item.source == source for item in filtered(b.entries, source, "", "all", "name"))
    assert not c.sent
    if sidebar.servers.topLevelItemCount():
        sidebar.servers.setCurrentItem(sidebar.servers.topLevelItem(0))
        sidebar.details()
        assert not c.sent
        sidebar.info.close()
    for section in ("servers", "subscriptions", "devices", "traffic", "diagnostics",
                    "extra", "zapret2"):
        w.open_section(section)
        qapp.processEvents()
        assert w.tools.key == section
    w.tools.close()
    changed = copy.deepcopy(data)
    changed["zapret2"] = {"mode": "standalone", "without_vpn": True, "state": "active",
                         "detail": "Выбранные домены через zapret2"}
    b.on_state(changed)
    assert "zapret2 без VPN" in w.card.title.text()
    assert "без VPN" in w.details.status.text()
    assert not b.can_select
    assert not w.map.focus_code
    assert not sidebar.choose.isEnabled()
    changed["zapret2"]["mode"] = "off"  # Возврат запрошен, прямой конфиг ещё применён.
    b.on_state(changed)
    assert not b.can_select
    b.on_link(client.LINK_AUTH, "Нужен вход")
    assert w.card.connect_button.text() == "Войти в панель"
    assert not b.can_select
    b.on_link(client.LINK_OK, "")
    b.on_state(data)
    sidebar.sources.setCurrentRow(0)
    qapp.processEvents()
    if os.environ.get("XGW_UI_SCREENSHOT"):
        w.grab().save(os.environ["XGW_UI_SCREENSHOT"])
    w.close()


def test_old_pool_reply_cannot_repopulate_after_auth_expiry(scene):
    c, b, _data = scene
    b.pool_visible = True
    b.fetch_pool()
    callback = c.gets[-1][2]
    b.on_link(client.LINK_AUTH, "Вход устарел")
    callback({"servers": [{"id": "old"}]}, "")
    assert b.pool is None


def test_nested_page_commands_are_checked_again_before_post(qapp, monkeypatch):
    sent = []
    monkeypatch.setattr(client.ApiClient, "act", lambda _self, name, body, key:
                        sent.append(name) or True)
    c = GuardedApiClient(None)
    b = XgwBridge(c)
    assert not c.act("pin", {"tag": "demo"})
    b.state["zapret2"] = {"mode": "off", "without_vpn": True}
    assert not c.act("unpin")
    b.link = client.LINK_OK
    b.on_state({"now": time.time(), "updated": time.time(),
                "zapret2": {"mode": "standalone"}})
    assert not c.act("pin", {"tag": "demo"})
    assert c.act("zapret2/mode", {"mode": "off"})
    assert sent == ["zapret2/mode"]
    b.close()
