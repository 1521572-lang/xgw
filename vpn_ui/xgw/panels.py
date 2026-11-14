"""Карточки с действительным состоянием шлюза; общих фиктивных переключателей нет."""
from xgw.gui import client as api
from xgw.gui import model

from .. import theme
from ..qt import Qt, QtCore, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics
from ..views.connection_card_view import ConnectionCardView
from .overview import guard_status, overview, zapret_status

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
        self.title.setText("Нет свежих данных" if bridge.stale else power.title)
        self.subtitle.setText("Войдите в панель для управления шлюзом" if
                              bridge.link == api.LINK_AUTH else
                              "Ожидается ответ шлюза" if bridge.stale else power.sub)
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


def plain_label(name):
    label = QtWidgets.QLabel()
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    return label


class Metric(QtWidgets.QFrame):
    def __init__(self, title, tooltip, parent=None):
        super().__init__(parent)
        self.setObjectName("GatewayMetric")
        self.setMinimumHeight(58)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(3)
        caption = plain_label("GatewayCaption")
        caption.setText(title)
        self.value = plain_label("GatewayValue")
        self.value.setText("—")
        self.setToolTip(tooltip)
        box.addWidget(caption)
        box.addWidget(self.value)


class Details(QtWidgets.QFrame):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("GatewayDetails")
        self.setAccessibleName("Текущее соединение шлюза")
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(7)
        heading = QtWidgets.QHBoxLayout()
        title = plain_label("GatewayCaption")
        title.setText("ТЕКУЩЕЕ СОЕДИНЕНИЕ")
        self.status = plain_label("GatewayStatus")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)
        box.addLayout(heading)
        self.server = plain_label("GatewayServer")
        self.source = plain_label("GatewayCaption")
        box.addWidget(self.server)
        box.addWidget(self.source)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(6)
        self.speed = Metric("Последний замер", "Последняя проба сервера, не текущая скорость.")
        self.rtt = Metric("Задержка RTT", "Время соединения в последней пробе XGW.")
        self.core = Metric("Ядро сервера", "Ядро, обслуживающее текущий VPN-сервер.")
        self.policy = Metric("При отказе", "Политика доступа, переданная шлюзом.")
        self.cells = (self.speed, self.rtt, self.core, self.policy)
        self._wide = None
        self.set_wide(True)
        box.addLayout(self.grid)
        foot = QtWidgets.QHBoxLayout()
        self.live = plain_label("GatewayCaption")
        self.live.setText("Текущая скорость и внешний IP: нет данных")
        traffic = QtWidgets.QPushButton("Трафик  ›")
        traffic.setObjectName("GatewayLink")
        traffic.setAccessibleName("Открыть расход трафика")
        traffic.clicked.connect(lambda: bridge.section_requested.emit("traffic"))
        foot.addWidget(self.live, 1)
        foot.addWidget(traffic)
        box.addLayout(foot)
        bridge.gateway_changed.connect(self.refresh)
        self.refresh()

    def set_wide(self, wide):
        if self._wide == wide:
            return
        self._wide = wide
        self.setMinimumHeight(206 if wide else 266)
        for cell in self.cells:
            self.grid.removeWidget(cell)
        for col in range(4):
            self.grid.setColumnStretch(col, 1 if col < (4 if wide else 2) else 0)
        for index, cell in enumerate(self.cells):
            self.grid.addWidget(cell, 0 if wide else index // 2, index if wide else index % 2)
        self.updateGeometry()

    def refresh(self):
        b = self.bridge
        view = overview(b.state, b.stale, b.busy)
        self.status.setText(view.status)
        self.status.setProperty("tone", view.tone)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.server.setText(view.server)
        self.source.setText(view.source)
        self.speed.value.setText(view.speed)
        self.rtt.value.setText(view.rtt)
        self.core.value.setText(view.core)
        guard = guard_status(b.state, b.stale)
        self.policy.value.setText(guard.text)
        self.policy.setToolTip(guard.detail)


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
        self.zapret_note = plain_label("GatewayCaption")
        self.zapret_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zapret_note.setAccessibleName("Состояние zapret2")
        box.insertWidget(1, self.zapret_note)
        bridge.gateway_changed.connect(lambda: self.refresh(bridge))
        theme.manager().changed.connect(self.retint)
        self.retint()
        self.refresh(bridge)

    def refresh(self, bridge):
        status = zapret_status(bridge.state, bridge.stale)
        self.zapret_note.setText(status.text)
        self.zapret_note.setToolTip(status.detail)
        self.buttons[0].setToolTip("zapret2 · " + status.text + "\n" + status.detail)
        self.buttons[0].setAccessibleName("zapret2 · " + status.text + ". Открыть управление")
        self.buttons[0].setProperty("gatewayTone", status.tone)
        self.buttons[0].style().unpolish(self.buttons[0])
        self.buttons[0].style().polish(self.buttons[0])

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
            if button is not self.buttons[0]:
                button.setAccessibleName(button.text())
            button.setFixedHeight(40 if width <= Metrics.WIDGETS_COMPACT else 58)
            button.setFixedWidth(self.width() - 14)


class Settings(QtWidgets.QFrame):
    close_requested = Signal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsDrawer")
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(20, 20, 20, 16)
        box.setSpacing(12)
        heading = plain_label("DrawerTitle")
        heading.setText("Настройки XGW")
        box.addWidget(heading)
        about = plain_label("GatewayCaption")
        about.setText("Подключения, устройства и оформление")
        box.addWidget(about)
        box.addSpacing(8)
        for title, section in (("Подписки и отдельные ссылки", "subscriptions"),
                               ("Серверы, ядра и приоритеты", "servers"),
                               ("Маршруты устройств и исключения", "devices"),
                               ("zapret2: режим и стратегия", "zapret2"),
                               ("Tailscale, телефоны и обновления", "extra")):
            button = QtWidgets.QPushButton(title + "  ›")
            button.setObjectName("SettingsLink")
            button.setMinimumHeight(48)
            button.setAccessibleName(title)
            button.clicked.connect(lambda _checked=False, key=section:
                                   bridge.section_requested.emit(key))
            box.addWidget(button)
        box.addSpacing(12)
        heading = plain_label("SectionTitle")
        heading.setText("ОФОРМЛЕНИЕ")
        box.addWidget(heading)
        self.theme = QtWidgets.QComboBox()
        self.theme.setAccessibleName("Тема оформления")
        self.theme.addItem("Тёмная", "dark")
        self.theme.addItem("Светлая", "light")
        self.theme.activated.connect(lambda _index: bridge.request_settings(
            theme=self.theme.currentData()))
        theme.manager().changed.connect(self.sync_theme)
        self.sync_theme()
        box.addWidget(self.theme)
        box.addStretch(1)
        close = QtWidgets.QPushButton("Закрыть")
        close.clicked.connect(self.close_requested)
        box.addWidget(close)

    def sync_theme(self):
        # CLI и меню могут переопределить настройку моста до показа шторки.
        self.theme.setCurrentIndex(max(0, self.theme.findData(theme.palette().name)))
