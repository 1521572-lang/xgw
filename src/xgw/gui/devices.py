"""Устройства локальной сети в нативном окне. Действия выполняет панель XGW."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from . import listing, model
from .pages import _button, _card, _scroll, confirm
from .widgets import label, set_text


def _plain(text: str = "", *, name: str = ""):
    widget = label(text, name=name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def _action_label(button, text: str) -> None:
    if button.text() != text:
        button.setText(text)
        button.setAccessibleName(text)


class DeviceCard(QFrame):
    def __init__(self, page: DevicesPage) -> None:
        super().__init__()
        self.page = page
        self.item: listing.DeviceItem | None = None
        self.choices: tuple[tuple[str, str], ...] = ()
        self.setObjectName("row")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 14, 18, 14)
        self.name = _plain(name="rowName")
        self.address = _plain(name="muted")
        self.status = _plain()
        box.addWidget(self.name)
        box.addWidget(self.address)
        box.addWidget(self.status)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.route = QComboBox()
        self.route.setAccessibleName("Сервер устройства")
        self.route.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.route.setMinimumContentsLength(20)
        self.route.activated.connect(self._route)
        self.kernel = _button("Российские адреса", self._kernel, "deviceKernel")
        self.bypass = _button("Пустить мимо VPN", self._bypass, "deviceBypass")
        controls.addWidget(self.route, 1)
        controls.addWidget(self.kernel)
        controls.addWidget(self.bypass)
        box.addLayout(controls)

    def show_item(self, item: listing.DeviceItem, *, enabled: bool, pool_all: bool,
                  kernel_reason: str, recording: bool) -> None:
        self.item = item
        set_text(self.name, item.name)
        set_text(self.address, " · ".join(filter(None, (item.ip, item.mac))))
        set_text(self.status, item.status + (" · идёт запись трафика" if recording else ""))
        # Опрос обновляет выбранное значение. Сам список меняется только при новых вариантах.
        if item.choices != self.choices:
            self.choices = item.choices
            self.route.clear()
            for value, title in self.choices:
                self.route.addItem(title, value)
        index = self.route.findData(item.route)
        if index != self.route.currentIndex():
            self.route.setCurrentIndex(index)
        self.route.setVisible(not item.bypass)
        self.route.setEnabled(enabled and not pool_all)
        self.route.setToolTip("Весь дом через бесплатные серверы" if pool_all else "")
        _action_label(self.kernel, "Российские: мимо Xray" if item.kernel
                      else "Российские: через Xray")
        self.kernel.setVisible(not item.bypass)
        self.kernel.setEnabled(enabled and (item.kernel or not kernel_reason))
        self.kernel.setToolTip(kernel_reason if not item.kernel else "")
        _action_label(self.bypass, "Вернуть в VPN" if item.bypass else "Пустить мимо VPN")
        self.bypass.setEnabled(enabled and not item.locked and (item.bypass or not item.offline))
        self.bypass.setToolTip("Исключение задано в config.toml" if item.locked else "")

    def _send(self, action: str, **values) -> None:
        item = self.item
        if item is not None and self.isVisible() and self.page.can_act(item.mac):
            self.page.main.client.act(action, {"mac": item.mac, **values}, key=f"device:{item.mac}")

    def _route(self, index: int) -> None:
        item = self.item
        if item is None or not self.route.isEnabled():
            return
        wanted = self.route.itemData(index)
        self.route.setCurrentIndex(self.route.findData(item.route))
        if wanted is None or wanted == item.route:
            return
        if wanted == "pool" and not self.page.confirm(
            "Выбрать бесплатные серверы?",
            "Владельцы серверов видят, к каким сайтам идёт устройство. Если пригодных "
            "серверов нет, зарубежные сайты у устройства будут закрыты.",
            "Через бесплатные",
        ):
            return
        if self.route.isVisible() and self.route.isEnabled() and self.route.findData(wanted) >= 0:
            self._send("device/route", server=wanted)

    def _kernel(self) -> None:
        if self.item is not None and self.kernel.isEnabled():
            self._send("device/direct", on=not self.item.kernel)

    def _bypass(self) -> None:
        item = self.item
        if item is None or not self.bypass.isEnabled():
            return
        bypass = not item.bypass
        if bypass and not self.page.confirm(
            "Пустить устройство мимо VPN?",
            "Его трафик пойдёт напрямую, без защиты VPN. Адрес устройства закрепится за ним.",
            "Пустить мимо VPN",
        ):
            return
        if self.bypass.isEnabled():
            self._send("device", bypass=bypass)


class DevicesPage(QWidget):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.cards: dict[str, DeviceCard] = {}
        self.lan_ready = False
        self.direct = {}
        self.confirm = lambda title, text, yes: confirm(self, title, text, yes)
        self.setObjectName("page")
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 22, 28, 0)
        box.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label("Устройства", name="pageTitle", wrap=False))
        head.addStretch(1)
        head.addWidget(_button("Записи трафика в браузере", main.open_browser))
        box.addLayout(head)
        self.note = _plain(name="muted")
        box.addWidget(self.note)
        inner = QWidget()
        self.items = QVBoxLayout(inner)
        self.items.setContentsMargins(0, 0, 12, 12)
        self.items.setSpacing(10)
        host, panel = _card()
        panel.addWidget(label("Этот компьютер и контейнеры", name="cardTitle"))
        self.host_note = _plain()
        panel.addWidget(self.host_note)
        self.host = _button("Российские адреса", self._host, "hostKernel")
        panel.addWidget(self.host, alignment=Qt.AlignmentFlag.AlignLeft)
        self.items.addWidget(host)
        self.empty = label("Устройств пока нет", name="muted")
        self.items.addWidget(self.empty)
        self.items.addStretch(1)
        box.addWidget(_scroll(inner), 1)

    def can_act(self, mac: str) -> bool:
        return (self.lan_ready and not self.main.stale and mac in self.cards
                and not self.main.client.actions.busy(f"device:{mac}"))

    def _host(self) -> None:
        if self.host.isEnabled() and not self.main.stale:
            self.main.client.act("direct", {"on": not self.direct.get("on")}, key="direct")

    def show_state(self, state: dict | None) -> None:
        snapshot = state or {}
        lan = snapshot.get("lan") or {}
        self.lan_ready = bool(lan.get("interface") and lan.get("gateway"))
        mode = (snapshot.get("capture") or {}).get("mode")
        if state is None:
            note = "Ожидаю данные панели…"
        elif not self.lan_ready:
            note = "Локальная сеть устройств не настроена"
        else:
            note = f"Сеть {lan['interface']} · шлюз {lan['gateway']}"
        if mode in ("off", "blocked"):
            note += (" · перехват VPN выключен" if mode == "off"
                     else " · перехват заблокирован")
        if state is not None and self.main.stale:
            note += " · данные устарели"
        set_text(self.note, note)
        self.direct = snapshot.get("kernel_direct") or {}
        reason, on = str(self.direct.get("reason") or ""), bool(self.direct.get("on"))
        direct_text = "Российские адреса идут через Xray" if not on else (
            "Российские адреса: разгрузка Xray включена")
        if reason:
            direct_text += " · " + reason
        elif on:
            networks = self.direct.get("networks") or 0
            direct_text += f" · сетей: {networks}" if networks else " · список сетей пуст"
        set_text(self.host_note, direct_text if state is not None else "Ожидаю данные панели…")
        _action_label(self.host, "Вернуть через Xray" if on else "Российские адреса мимо Xray")
        self.host.setEnabled(state is not None and not self.main.stale and (on or not reason)
                             and not self.main.client.actions.busy("direct"))

        items = listing.devices(state)
        self.empty.setVisible(state is not None and not items)
        pool_all = model.pool_house(snapshot)
        active = (snapshot.get("records") or {}).get("active") or {}
        keep = {item.mac for item in items}
        for mac in self.cards.keys() - keep:
            card = self.cards.pop(mac)
            self.items.removeWidget(card)
            card.hide()
            card.deleteLater()
        for index, item in enumerate(items, 2):
            if item.mac not in self.cards:
                self.cards[item.mac] = DeviceCard(self)
            card = self.cards[item.mac]
            if self.items.indexOf(card) != index:
                self.items.insertWidget(index, card)
                card.show()
            card.show_item(item, enabled=self.can_act(item.mac), pool_all=pool_all,
                           kernel_reason=reason, recording=active.get("mac") == item.mac)
