"""Карточки с действительным состоянием шлюза; общих фиктивных переключателей нет."""
from xgw.gui import client as api
from xgw.gui import model

from .. import theme
from ..qt import Qt, QtCore, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics
from ..views.connection_card_view import ConnectionCardView

SECTIONS = (("zapret2", "zapret2"), ("devices", "Устройства"), ("traffic", "Трафик"),
            ("diagnostics", "Диагностика"), ("extra", "Ещё"))


class Card(ConnectionCardView):
    def __init__(self, bridge, parent=None):
        super().__init__(bridge, parent)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setToolTip("Состояние шлюза, подтверждённое демоном")
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.error_text.setTextFormat(Qt.TextFormat.PlainText)
        self.error_text.setProperty("elide", False)
        self.error_text.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                      QtWidgets.QSizePolicy.Policy.Preferred)
        self.subtitle.setWordWrap(True)
        self.subtitle.setMaximumWidth(440)
        self.title.setMinimumWidth(0)
        self.title.setMinimumWidth(250)
        self.title.setMaximumWidth(440)
        self.title.setWordWrap(True)
        self.title.setFixedHeight(72)
        bridge.gateway_changed.connect(self.refresh)

    def _connect(self):
        if self.bridge.link == api.LINK_AUTH:
            self.bridge.section_requested.emit("login")
        else:
            self.bridge.power()

    def refresh(self):
        bridge = self.bridge
        power = model.power(bridge.state or None, bridge.stale, acting=bridge.busy)
        country = bridge.map_country()
        if country:
            self.badge.show_flag(country)
        else:
            self.badge.show_icon("Bolt")
        self.title.setText(power.title)
        self.subtitle.setText(power.sub)
        self.flags.hide()
        self.more.hide()
        self.pill.hide()
        self.info.hide()
        self.cancel_button.hide()
        self.disconnect_button.hide()
        self.connect_button.show()
        auth = bridge.link == api.LINK_AUTH
        self.connect_button.setText("Войти в панель" if auth else
                                    "Ожидание…" if bridge.busy else
                                    "Выключить перехват" if power.pressed else "Включить перехват")
        self.connect_button.setEnabled(auth or power.enabled)
        self.connect_button.setToolTip("Включает или выключает текущий режим шлюза. "
                                      "Режим zapret2 выбирается в его разделе.")
        self.error_text.setText(bridge.message)
        self.error.setVisible(bool(bridge.message))


class Details(QtWidgets.QFrame):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("SidebarPane")
        box = QtWidgets.QVBoxLayout(self)
        self.status = QtWidgets.QLabel()
        self.server = QtWidgets.QLabel()
        self.metrics = QtWidgets.QLabel()
        self.guard = QtWidgets.QLabel()
        self.live = QtWidgets.QLabel("Текущая скорость и внешний IP: нет данных")
        for label in (self.status, self.server, self.metrics, self.guard, self.live):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            box.addWidget(label)
        self.setToolTip("Замеры сервера — последние пробы XGW. "
                        "Страна на карте определяется по IP точки подключения.")
        bridge.gateway_changed.connect(self.refresh)
        self.refresh()

    def set_wide(self, _wide):
        pass

    def refresh(self):
        b = self.bridge
        _tone, title = model.shield(b.state or None, b.stale, acting=b.busy)
        self.status.setText(title)
        zapret = b.state.get("zapret2") or {}
        direct = zapret.get("without_vpn")
        main = model.main_server(b.state) if not direct and not b.stale else None
        self.server.setText("Сервер: " + model.split_flag(main.name)[1] if main else
                            "Домашний адрес · VPN-серверы не используются" if direct and not b.stale
                            else "Текущий сервер: нет подтверждённых данных")
        if main:
            self.metrics.setText(f"Последний замер: {model.mbps_text(main.speed_mbps)} · "
                                 f"RTT {model.ms_text(main.rtt_ms)} · ядро {main.core or '—'}")
        else:
            self.metrics.setText("Замеры VPN-сервера: нет данных")
        capture = b.state.get("capture") or {}
        self.guard.setText("Блокировка при отказе: нет свежих данных" if b.stale else
            "Блокировка трафика: активна" if capture.get("blocked") else
            "Перехват выключен: прямой интернет" if capture.get("mode") == "off" else
            "При отказе интернет закрывается" if capture.get("fail_mode") == "closed" else
            "При отказе допускается прямой интернет" if capture.get("fail_mode") == "open" else
            "Политика блокировки: нет данных")


class WidgetBar(QtWidgets.QFrame):
    settings_requested = Signal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.setObjectName("WidgetPane")
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(6, 6, 6, 6)
        self.buttons = []
        icons = ("Bolt", "Servers", "ArrowDownLine", "ExclamationCircleFilled", "WindowTerminal")
        for (key, title), icon in zip(SECTIONS, icons, strict=True):
            button = QtWidgets.QToolButton()
            button.setText(title)
            button.setObjectName("XgwTool")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setProperty("icon_name", icon)
            button.setToolTip(title)
            button.clicked.connect(lambda _checked=False, section=key:
                                   bridge.section_requested.emit(section))
            box.addWidget(button)
            self.buttons.append(button)
        settings = QtWidgets.QToolButton()
        settings.setText("Настройки")
        settings.setObjectName("XgwTool")
        settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        settings.setProperty("icon_name", "WindowTerminal")
        settings.clicked.connect(self.settings_requested)
        box.addWidget(settings)
        self.buttons.append(settings)
        theme.manager().changed.connect(self.retint)
        self.retint()

    def retint(self):
        for button in self.buttons:
            button.setIcon(svg_loader.load_svg_icon(button.property("icon_name"),
                           theme.palette().text.hex, QtCore.QSize(24, 24)))
            button.setIconSize(QtCore.QSize(24, 24))

    def set_bar_width(self, width):
        self.setFixedWidth(width)
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if width <= Metrics.WIDGETS_COMPACT
                 else Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for button in self.buttons:
            button.setToolButtonStyle(style)
            button.setAccessibleName(button.text())
            button.setMinimumHeight(58)
            button.setFixedWidth(self.width() - 14)


class Settings(QtWidgets.QFrame):
    close_requested = Signal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsDrawer")
        box = QtWidgets.QVBoxLayout(self)
        box.addWidget(QtWidgets.QLabel("Настройки XGW"))
        for title, section in (("Подписки и отдельные ссылки", "subscriptions"),
                               ("Серверы, ядра и приоритеты", "servers"),
                               ("Маршруты устройств и исключения", "devices"),
                               ("zapret2: режим и стратегия", "zapret2"),
                               ("Tailscale, телефоны и обновления", "extra")):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(lambda _checked=False, key=section:
                                   bridge.section_requested.emit(key))
            box.addWidget(button)
        box.addWidget(QtWidgets.QLabel("Тема оформления"))
        self.theme = QtWidgets.QComboBox()
        self.theme.addItem("Тёмная", "dark")
        self.theme.addItem("Светлая", "light")
        self.theme.activated.connect(lambda _index: bridge.request_settings(
            theme=self.theme.currentData()))
        bridge.settings_changed.connect(lambda settings: self.theme.setCurrentIndex(
            max(0, self.theme.findData(settings.theme))))
        box.addWidget(self.theme)
        box.addStretch(1)
        close = QtWidgets.QPushButton("Закрыть")
        close.clicked.connect(self.close_requested)
        box.addWidget(close)
