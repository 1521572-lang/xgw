"""Выдвижная панель настроек: протокол, защита, маршрутизация и оформление."""
from __future__ import annotations

from .. import theme
from ..components.toggle_switch import ToggleSwitch
from ..core.bridge import VpnUiBridge
from ..core.state import PROTOCOLS, FeaturesState, UiSettings
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics

PROTOCOL_ABOUT = {
    "xray": "VLESS и Reality: устойчив к блокировкам",
    "sing-box": "Универсальное ядро с мультиплексированием",
    "wireguard": "Быстрый и лёгкий, работает по UDP",
    "openvpn": "Совместим со старыми сетями и роутерами",
}
FEATURE_TEXT = {
    "kill_switch": ("Kill switch", "Блокирует интернет, если соединение с VPN оборвалось"),
    "split_tunneling": ("Раздельное туннелирование",
                        "Выбранные приложения и адреса идут мимо VPN"),
    "custom_dns": ("Свой DNS-сервер", "Использовать указанный адрес вместо DNS сервера VPN"),
    "lan_bypass": ("Доступ к локальной сети",
                   "Принтеры и устройства домашней сети остаются доступны"),
}
ROUTING = (("all", "Весь трафик через VPN"), ("blocked", "Только заблокированные ресурсы"))
THEMES = (("dark", "Тёмная"), ("light", "Светлая"))


class SettingsCard(QtWidgets.QFrame):
    """Строка настройки: название, пояснение и элемент управления справа."""

    def __init__(self, title: str, about: str, control: QtWidgets.QWidget | None = None,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setMinimumHeight(Metrics.SETTINGS_CARD)
        self.title = QtWidgets.QLabel(title, self)
        self.title.setObjectName("SettingsTitle")
        self.about = QtWidgets.QLabel(about, self)
        self.about.setObjectName("SettingsAbout")
        self.about.setWordWrap(True)
        self.about.setProperty("elide", True)  # пояснение переносится по словам
        self.about.setVisible(bool(about))
        text = QtWidgets.QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.about)
        self.row = QtWidgets.QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(16)
        self.row.addLayout(text, 1)
        if control is not None:
            self.row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.column = QtWidgets.QVBoxLayout(self)
        self.column.setContentsMargins(16, 12, 16, 12)
        self.column.setSpacing(10)
        self.column.addLayout(self.row)


class SettingsDrawerView(QtWidgets.QFrame):
    close_requested = Signal()

    def __init__(self, bridge: VpnUiBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("SettingsDrawer")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        title = QtWidgets.QLabel("Настройки", self)
        title.setObjectName("DrawerTitle")
        self.close_button = QtWidgets.QToolButton(self)
        self.close_button.setObjectName("DrawerClose")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Закрыть настройки (Esc)")
        self.close_button.setAccessibleName("Закрыть настройки")
        self.close_button.clicked.connect(self.close_requested)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(24, 16, 16, 8)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.close_button)

        body = QtWidgets.QWidget()
        body.setObjectName("DrawerBody")
        self.items = QtWidgets.QVBoxLayout(body)
        self.items.setContentsMargins(24, 4, 16, 24)
        self.items.setSpacing(4)
        self._build_protocol()
        self._build_features()
        self._build_routing()
        self._build_appearance()
        self.items.addStretch(1)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setObjectName("DrawerScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(body)

        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(head)
        column.addWidget(scroll, 1)

        bridge.features_changed.connect(self._show_features)
        bridge.settings_changed.connect(self._show_settings)
        theme.manager().changed.connect(self._retint)
        self._retint()
        self._show_features(bridge.features)
        self._show_settings(bridge.settings)

    # --- разделы ---------------------------------------------------------------------
    def _section(self, text: str) -> None:
        label = QtWidgets.QLabel(text, self)
        label.setObjectName("SectionTitle")
        self.items.addSpacing(12)
        self.items.addWidget(label)
        self.items.addSpacing(4)

    def _build_protocol(self) -> None:
        self._section("Протокол")
        self.protocol_group = QtWidgets.QButtonGroup(self)
        self.protocol_buttons: dict[str, QtWidgets.QRadioButton] = {}
        for name in PROTOCOLS:
            radio = QtWidgets.QRadioButton(self)
            radio.setObjectName("ProtocolRadio")
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setAccessibleName(f"Протокол {name}")
            radio.clicked.connect(lambda _checked=False, value=name:
                                  self.bridge.request_protocol(value))
            self.protocol_group.addButton(radio)
            self.protocol_buttons[name] = radio
            self.items.addWidget(SettingsCard(name, PROTOCOL_ABOUT[name], radio, self))

    def _build_features(self) -> None:
        self._section("Защита")
        self.toggles: dict[str, ToggleSwitch] = {}
        for name, (title, about) in FEATURE_TEXT.items():
            toggle = ToggleSwitch(self)
            toggle.setAccessibleName(title)
            toggle.toggled.connect(lambda checked, key=name:
                                   self.bridge.request_feature(key, checked))
            self.toggles[name] = toggle
            card = SettingsCard(title, about, toggle, self)
            if name == "custom_dns":
                self.dns_edit = QtWidgets.QLineEdit(card)
                self.dns_edit.setObjectName("DnsEdit")
                self.dns_edit.setPlaceholderText("Адрес DNS-сервера, например 9.9.9.9")
                self.dns_edit.setAccessibleName("Адрес DNS-сервера")
                self.dns_edit.editingFinished.connect(self._dns_edited)
                card.column.addWidget(self.dns_edit)
            self.items.addWidget(card)

    def _combo(self, options: tuple[tuple[str, str], ...], name: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox(self)
        combo.setObjectName("SettingsCombo")
        combo.setAccessibleName(name)
        combo.setMinimumWidth(170)
        for value, text in options:
            combo.addItem(text, value)
        return combo

    def _build_routing(self) -> None:
        self._section("Маршрутизация")
        self.routing = self._combo(ROUTING, "Что идёт через VPN")
        self.routing.activated.connect(lambda _index: self.bridge.request_settings(
            routing=self.routing.currentData()))
        self.items.addWidget(SettingsCard("Что идёт через VPN", "", self.routing, self))
        self.interface = self._combo((("auto", "Автоматически"),), "Сетевой интерфейс")
        self.interface.activated.connect(lambda _index: self.bridge.request_settings(
            interface=self.interface.currentData()))
        self.items.addWidget(SettingsCard("Сетевой интерфейс",
                                          "Через какой интерфейс идти к серверу", self.interface,
                                          self))

    def _build_appearance(self) -> None:
        self._section("Оформление и запуск")
        self.theme_combo = self._combo(THEMES, "Тема оформления")
        self.theme_combo.activated.connect(lambda _index: self.bridge.request_settings(
            theme=self.theme_combo.currentData()))
        self.items.addWidget(SettingsCard("Тема", "", self.theme_combo, self))
        self.auto_connect = ToggleSwitch(self)
        self.auto_connect.setAccessibleName("Подключаться при запуске")
        self.auto_connect.toggled.connect(lambda checked: self.bridge.request_settings(
            auto_connect=checked))
        self.items.addWidget(SettingsCard("Подключаться при запуске",
                                          "Сразу после входа в систему", self.auto_connect, self))

    # --- синхронизация с мостом ------------------------------------------------------
    def set_interfaces(self, names: list[str]) -> None:
        """Список интерфейсов от бэкенда; «Автоматически» остаётся первым пунктом."""
        current = self.interface.currentData()
        self.interface.clear()
        self.interface.addItem("Автоматически", "auto")
        for name in names:
            self.interface.addItem(name, name)
        index = self.interface.findData(current)
        self.interface.setCurrentIndex(max(0, index))

    def _dns_edited(self) -> None:
        text = self.dns_edit.text().strip()
        if text != self.bridge.settings.dns_address:
            self.bridge.request_settings(dns_address=text)

    def _show_features(self, features: FeaturesState) -> None:
        for name, toggle in self.toggles.items():
            toggle.set_checked_silently(features.enabled(name))
        self.dns_edit.setVisible(features.custom_dns)

    def _show_settings(self, settings: UiSettings) -> None:
        radio = self.protocol_buttons.get(settings.protocol)
        if radio is not None and not radio.isChecked():
            radio.setChecked(True)
        for combo, value in ((self.routing, settings.routing), (self.interface, settings.interface),
                             (self.theme_combo, settings.theme)):
            index = combo.findData(value)
            if index >= 0 and index != combo.currentIndex():
                combo.setCurrentIndex(index)
        self.auto_connect.set_checked_silently(settings.auto_connect)
        if not self.dns_edit.hasFocus() and self.dns_edit.text() != settings.dns_address:
            self.dns_edit.setText(settings.dns_address)

    def _retint(self) -> None:
        self.close_button.setIcon(svg_loader.load_svg_icon(
            "Cross", theme.palette().text.hex, QtCore.QSize(16, 16)))
        self.close_button.setIconSize(QtCore.QSize(16, 16))

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            return
        super().keyPressEvent(event)
