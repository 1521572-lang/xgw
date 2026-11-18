"""Карточки с действительным состоянием шлюза; общих фиктивных переключателей нет."""
from xgw.gui import client as api
from xgw.gui import model

from .. import theme
from ..components.custom_titlebar import IconLabel
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics
from ..views.connection_card_view import ConnectionCardView
from .overview import guard_status, overview, zapret_status
from .sidebar import country_name

SECTIONS = (("zapret2", "zapret2"), ("devices", "Устройства"), ("traffic", "Трафик"),
            ("diagnostics", "Диагностика"), ("extra", "Ещё"))


class Card(ConnectionCardView):
    def __init__(self, bridge, parent=None):
        super().__init__(bridge, parent)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.error_text.setTextFormat(Qt.TextFormat.PlainText)
        self.error_text.setProperty("elide", False)
        self.error_text.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                      QtWidgets.QSizePolicy.Policy.Preferred)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bridge.gateway_changed.connect(self.refresh)

    def _fit_heading(self):
        space = max(1, self.width() - self.badge.width() - 24)
        self.title.setText(self.title.fontMetrics().elidedText(
            self.title.toolTip(), Qt.TextElideMode.ElideRight, space))
        strip = (self.flags.width() + 8 if not self.flags.isHidden() else 0)
        if not self.more.isHidden():
            strip += self.more.sizeHint().width() + 8
        self.subtitle.setText(self.subtitle.fontMetrics().elidedText(
            self.subtitle.toolTip(), Qt.TextElideMode.ElideRight, max(1, self.width() - strip - 8)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_heading()

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
        state = bridge.state
        view = overview(state, bridge.stale, bridge.busy)
        mode = (state.get("capture") or {}).get("mode")
        zapret = state.get("zapret2") or {}
        title, subtitle, codes = power.title, power.sub, []
        if bridge.stale:
            title = "Нет свежих данных"
            subtitle = ("Войдите в панель для управления шлюзом" if bridge.link == api.LINK_AUTH
                        else "Ожидается ответ шлюза")
        elif (not bridge.busy and zapret.get("mode") != "standalone"
              and not zapret.get("without_vpn")):
            if mode == "on" and view.tone == "ok":
                title = view.server
                subtitle = " · ".join(filter(None, (country_name(country) if country else "",
                                                    view.source)))
            elif mode == "off" and not state.get("pin") and not model.pool_house(state):
                title, subtitle = "Автовыбор сервера", "Выбор сервера после подключения"
                codes = sorted({entry.country for entry in bridge.entries if entry.country
                                and not entry.pool})
                if codes:
                    subtitle = "Страны в каталоге"
        self.flags.set_codes(codes)
        self.more.setText(f"+{len(codes) - 3}" if len(codes) > 3 else "")
        self.more.setVisible(len(codes) > 3)
        self.title.setToolTip(title)
        self.title.setAccessibleName(title)
        self.subtitle.setToolTip(subtitle)
        self.subtitle.setAccessibleName(subtitle)
        self._fit_heading()
        self.pill.hide()
        self.info.hide()
        self.cancel_button.hide()
        self.disconnect_button.hide()
        self.connect_button.show()
        auth = bridge.link == api.LINK_AUTH
        self.connect_button.setText("Войти в панель" if auth else
                                    "Ожидание…" if bridge.busy else
                                    "Отключить" if power.pressed else "Подключить")
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
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
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
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(16)
        heading = QtWidgets.QHBoxLayout()
        self.icon = IconLabel("LockOpenFilled2", 20, "danger", self)
        self.status = plain_label("GatewayStatus")
        self.description = plain_label("StatusDescription")
        heading.addWidget(self.icon)
        heading.addWidget(self.status)
        heading.addWidget(self.description, 1)
        box.addLayout(heading)
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
        bridge.gateway_changed.connect(self.refresh)
        self.refresh()

    def set_wide(self, wide):
        if self._wide == wide:
            return
        self._wide = wide
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
        zapret = b.state.get("zapret2") or {}
        direct = zapret.get("without_vpn") and not b.stale
        selective = (view.tone == "ok" and zapret.get("mode") == "selective"
                     and zapret.get("state") == "active" and zapret.get("fresh") is True
                     and zapret.get("policy_matched") is True)
        self.status.setText("VPN и zapret2" if selective else view.status)
        self.status.setProperty("tone", "direct" if direct and view.tone == "ok" else view.tone)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        power = model.power(b.state or None, b.stale, acting=b.busy)
        icon, ink = ("LockFilled", "success") if view.tone == "ok" and not direct else (
            "LockOpenFilled2", "danger")
        if direct or selective:
            icon, ink = "Globe", "text_weak"
        if view.tone in ("warn", "bad", "busy"):
            icon, ink = "ExclamationCircleFilled", "warning"
        self.icon.set_icon(icon, ink)
        description = view.source if b.stale or direct else power.sub
        if selective:
            description = "Для выбранных доменов включён прямой маршрут"
        self.description.setText(description)
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
        box.setSpacing(2)
        self.buttons = []
        icons = ("Bolt", "Servers", "ArrowsSwitch", "Sliders", "ThreeDotsVertical")
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
        settings.setProperty("icon_name", "CogWheel")
        separator = QtWidgets.QFrame(self)
        separator.setObjectName("WidgetSeparator")
        separator.setFixedHeight(1)
        box.addWidget(separator)
        settings.clicked.connect(self.settings_requested)
        box.addWidget(settings)
        self.buttons.append(settings)
        self.zapret_note = plain_label("GatewayCaption")
        self.zapret_note.setObjectName("ZapretNote")
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
        if self.zapret_note.property("tone") != status.tone:
            self.zapret_note.setProperty("tone", status.tone)
            self.zapret_note.style().unpolish(self.zapret_note)
            self.zapret_note.style().polish(self.zapret_note)
            self.retint()

    def retint(self):
        art = {"Servers": "port-forwarding-off", "CogWheel": "settings",
               "Bolt": "netshield-on-level-1" if self.zapret_note.property("tone") == "ok"
               else "netshield-off"}
        for button in self.buttons:
            name = button.property("icon_name")
            size = QtCore.QSize(28, 28)
            if name in art:
                pixmap = svg_loader.illustration(art[name], theme.palette().name, 28)
                button.setIcon(QtGui.QIcon(pixmap))
            else:
                button.setIcon(svg_loader.load_svg_icon(name, theme.palette().text_weak.hex, size))
            button.setIconSize(size)

    def set_bar_width(self, width):
        self.setFixedWidth(width)
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if width <= Metrics.WIDGETS_COMPACT
                 else Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for button in self.buttons:
            button.setToolButtonStyle(style)
            if button is not self.buttons[0]:
                button.setAccessibleName(button.text())
            button.setFixedHeight(40 if width <= Metrics.WIDGETS_COMPACT else 59)
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
