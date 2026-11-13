"""Один ApiClient: аутентификация, свежесть и намерения, подтверждаемые демоном."""
from __future__ import annotations

import time

from xgw.gui import client as api
from xgw.gui import model

from ..core.bridge import VpnUiBridge
from ..core.state import ConnectionState, ServerNode
from ..qt import QtCore, Signal
from .catalog import POOL, catalog


class GuardedApiClient(api.ApiClient):
    """Проверять свежесть и перед POST из вложенного диалога старой страницы."""

    bridge = None

    def act(self, name, body=None, key=None):
        if self.bridge is not None:
            zapret = self.bridge.state.get("zapret2") or {}
            standalone = zapret.get("mode") == "standalone" or zapret.get("without_vpn")
            if self.bridge.stale or (standalone and name in
                                    ("pin", "unpin", "freepool/pin", "sticky")):
                self.bridge.message = "Действие недоступно: проверьте связь и текущий режим."
                self.bridge.gateway_changed.emit()
                return False
        return super().act(name, body, key)


class XgwBridge(VpnUiBridge):
    gateway_changed = Signal()
    section_requested = Signal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        if isinstance(client, GuardedApiClient):
            client.bridge = self
        self.state: dict = {}
        self.received = 0.0
        self.link = api.LINK_OFFLINE
        self.sources, self.entries = [], []
        self.pool = None
        self.pool_error = ""
        self.pool_at = 0.0
        self.pool_visible = False
        self.pool_loading = False
        self.pool_generation = 0
        self.pool_session = client.session
        self.message = ""
        self.waiting: dict[str, float] = {}
        self.targets: dict[str, dict] = {}
        self.connect_requested.connect(lambda _target: self.power())
        self.disconnect_requested.connect(self.power)
        client.stateReceived.connect(self.on_state)
        client.linkChanged.connect(self.on_link)
        client.busyChanged.connect(lambda _key, _busy: self.render())
        client.actionFinished.connect(self.on_action)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    @property
    def stale(self):
        return (self.link != api.LINK_OK or not self.received or
                time.monotonic() - self.received > model.STALE_S or model.is_stale(self.state))

    @property
    def busy(self):
        return bool(self.waiting) or any(self.client.actions.busy(key) for key in
                                       ("power", "pin", "unpin", "freepool/pin"))

    @property
    def can_select(self):
        zapret = self.state.get("zapret2") or {}
        return (not self.stale and not self.busy and zapret.get("mode") != "standalone"
                and not zapret.get("without_vpn"))

    def on_state(self, state):
        self.state, self.received = state, time.monotonic()
        # POST-ответ не подтверждает режим. Ожидаем следующий снимок демона.
        for key in list(self.waiting):
            target = self.targets.get(key, {})
            matched = (
                (key == "power" and (state.get("capture") or {}).get("mode") ==
                ("on" if target.get("on") else "off")) or
                (key == "pin" and (state.get("pin") or {}).get("tag") == target.get("tag")) or
                (key == "unpin" and not state.get("pin")) or
                (key == "freepool/pin" and ((state.get("free_pool") or {}).get("pin") or "") ==
                target.get("id")))
            if not self.client.actions.busy(key) and matched:
                self.waiting.pop(key)
                self.targets.pop(key, None)
                self.message = "Изменение подтверждено состоянием шлюза."
        self.render()

    def on_link(self, link, text):
        if link == api.LINK_OK and self.link != api.LINK_OK:
            self.message = ""
        self.link = link
        if text:
            self.message = text
        if link == api.LINK_AUTH:
            self.pool_generation += 1
            self.pool = None
            self.pool_at = 0
            self.pool_loading = False
        self.render()

    def on_action(self, key, ok, text):
        self.message = ("Команда принята; ожидаю состояние шлюза. " + text
                        if ok and key in self.waiting else text)
        if not ok:
            self.waiting.pop(key, None)
            self.targets.pop(key, None)
        self.render()

    def tick(self):
        expired = [key for key, deadline in self.waiting.items() if time.monotonic() > deadline]
        for key in expired:
            self.waiting.pop(key)
            self.targets.pop(key, None)
        if expired:
            self.message = "Нет подтверждения действия от демона. Проверьте состояние шлюза."
        if self.stale or expired:
            self.render()
        if self.pool_visible and self.client.visible:
            self.fetch_pool()

    def send(self, name, body=None):
        if self.stale or self.busy:
            return
        self.waiting[name] = time.monotonic() + 30
        self.targets[name] = body or {}
        if not self.client.act(name, body or {}, key=name):
            self.waiting.pop(name, None)
            self.targets.pop(name, None)
        self.render()

    def power(self):
        power = model.power(self.state, self.stale, acting=self.busy)
        if power.enabled:
            self.send("power", {"on": not power.pressed})

    def select(self, identifier):
        item = next((entry for entry in self.entries if entry.id == identifier), None)
        if self.can_select and item is not None and item.choosable:
            if item.pool:
                self.send("freepool/pin", {"id": identifier.removeprefix("pool:")})
            else:
                self.send("pin", {"tag": identifier, "ttl": "forever"})

    def automatic(self, source):
        if self.can_select:
            self.send("freepool/pin", {"id": ""}) if source == POOL else self.send("unpin")

    def fetch_pool(self):
        if self.pool_session != self.client.session:
            self.pool_generation += 1
            self.pool_session = self.client.session
            self.pool, self.pool_at, self.pool_loading = None, 0, False
        if (self.stale or self.pool_loading or
                (self.pool_at and time.monotonic() - self.pool_at < 30)):
            return
        self.pool_loading = True
        self.pool_at = time.monotonic()
        generation = self.pool_generation

        def done(data, error):
            if generation != self.pool_generation:
                return
            self.pool_loading = False
            self.pool, self.pool_error = data, error
            self.render()

        if not self.client.fetch("pool", "/api/pool", done):
            self.pool_loading = False

    def render(self):
        self.sources, self.entries = catalog(self.state, self.pool)
        nodes = [ServerNode(item.id, item.name, country_code=item.country, protocol="",
                            available=item.choosable or item.chosen) for item in self.entries]
        if nodes != self.servers:
            self.set_server_list(nodes)
        power = model.power(self.state or None, self.stale, acting=self.busy)
        direct = (self.state.get("zapret2") or {}).get("without_vpn")
        tone, _text = model.shield(self.state or None, self.stale)
        if self.stale:
            state = ConnectionState.ERROR
        elif self.busy or "включается" in power.title.lower():
            state = ConnectionState.CONNECTING
        elif power.tone == "bad":
            state = ConnectionState.ERROR
        elif power.pressed and tone == "ok" and not direct:
            state = ConnectionState.CONNECTED
        else:
            state = ConnectionState.DISCONNECTED
        main = model.main_server(self.state) if self.state else None
        self.update_connection_state(state, main.tag if main and not direct else "auto", power.sub)
        self.gateway_changed.emit()

    def close(self):
        self.timer.stop()
        self.client.close()
