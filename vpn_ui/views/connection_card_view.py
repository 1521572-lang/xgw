"""Центр окна: карточка подключения сверху и сведения о сеансе снизу."""
from __future__ import annotations

from .. import theme
from ..components.custom_titlebar import IconLabel
from ..components.status_badge import ProtocolPill, StatusBadge
from ..components.traffic_graph import TrafficGraphWidget
from ..core.bridge import VpnUiBridge
from ..core.state import (
    AUTO_ID,
    GROUP_COUNTRIES,
    ConnectionSnapshot,
    ConnectionState,
    LocationInfo,
    TrafficStats,
    format_bytes,
    format_speed,
)
from ..qt import Qt, QtCore, QtGui, QtWidgets
from ..theme import svg_loader
from ..theme.tokens import Metrics


class CardBadge(QtWidgets.QWidget):
    """Плитка 54×36 слева от заголовка: флаг страны или молния «самого быстрого»."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(*Metrics.CARD_FLAG)
        self.code, self.icon = "", "Bolt"
        theme.manager().changed.connect(self.update)

    def show_flag(self, code: str) -> None:
        self.code = code
        self.update()

    def show_icon(self, icon: str) -> None:
        self.code, self.icon = "", icon
        self.update()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ratio = self.devicePixelRatioF()
        if self.code:
            painter.drawPixmap(0, 0, svg_loader.flag_pixmap(self.code, self.width(), self.height(),
                                                            ratio))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor(colors.vpn_green))
            painter.drawRoundedRect(QtCore.QRectF(self.rect()), 8, 8)
            painter.drawPixmap(QtCore.QPointF((self.width() - 24) / 2, (self.height() - 24) / 2),
                               svg_loader.icon_pixmap(self.icon, theme.tokens.DARK.text_invert, 24,
                                                      ratio))
        painter.end()


class FlagStrip(QtWidgets.QWidget):
    """До трёх флагов внахлёст: из каких стран выбирается самый быстрый сервер."""

    STEP = 20

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.codes: list[str] = []
        self.setFixedHeight(Metrics.FLAG[1])

    def set_codes(self, codes: list[str]) -> None:
        self.codes = codes[:3]
        width = Metrics.FLAG[0] + self.STEP * (len(self.codes) - 1) if self.codes else 0
        self.setFixedWidth(width)
        self.setVisible(bool(self.codes))
        self.update()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        ratio = self.devicePixelRatioF()
        for index in reversed(range(len(self.codes))):  # первый флаг лежит сверху
            painter.drawPixmap(index * self.STEP, 0, svg_loader.flag_pixmap(
                self.codes[index], *Metrics.FLAG, ratio))
        painter.end()


class ConnectionCardView(QtWidgets.QWidget):
    """Что выбрано для подключения и главная кнопка: подключить, отменить, отключить."""

    def __init__(self, bridge: VpnUiBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("ConnectionCard")
        self.badge = CardBadge(self)
        self.title = QtWidgets.QLabel(self)
        self.title.setObjectName("CardTitle")
        self.title.setProperty("elide", True)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(12)
        head.addStretch(1)
        head.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)

        self.subtitle = QtWidgets.QLabel(self)
        self.subtitle.setObjectName("CardSubtitle")
        self.flags = FlagStrip(self)
        self.more = QtWidgets.QLabel(self)
        self.more.setObjectName("CardSubtitle")
        self.pill = ProtocolPill("", self)
        self.info = IconLabel("InfoCircle", 20, "text_weak", self)
        line = QtWidgets.QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addStretch(1)
        for widget in (self.subtitle, self.flags, self.more, self.pill, self.info):
            line.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch(1)

        self.connect_button = self._button("Подключить", "ConnectButton")
        self.cancel_button = self._button("Отмена", "CancelButton")
        self.disconnect_button = self._button("Отключить", "DisconnectButton")
        self.connect_button.clicked.connect(self._connect)
        self.cancel_button.clicked.connect(bridge.request_disconnect)
        self.disconnect_button.clicked.connect(bridge.request_disconnect)
        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        for button in (self.connect_button, self.cancel_button, self.disconnect_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        self.error = QtWidgets.QFrame(self)
        self.error.setObjectName("ErrorBar")
        self.error_text = QtWidgets.QLabel(self.error)
        self.error_text.setObjectName("ErrorText")
        self.error_text.setWordWrap(True)
        self.error_text.setProperty("elide", True)
        bar = QtWidgets.QHBoxLayout(self.error)
        bar.setContentsMargins(12, 10, 12, 10)
        bar.setSpacing(10)
        bar.addWidget(IconLabel("ExclamationCircleFilled", 20, "warning", self.error), 0,
                      Qt.AlignmentFlag.AlignTop)
        bar.addWidget(self.error_text, 1)

        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(head)
        column.addSpacing(4)
        column.addLayout(line)
        column.addSpacing(16)
        column.addLayout(buttons)
        column.addSpacing(16)
        column.addWidget(self.error, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title.setFixedHeight(40)
        self.subtitle.setMinimumHeight(39)
        self.error.setMaximumWidth(480)

        bridge.connection_changed.connect(lambda _snapshot: self.refresh())
        bridge.servers_changed.connect(lambda _servers: self.refresh())
        bridge.settings_changed.connect(lambda _settings: self.refresh())
        self.refresh()

    def _button(self, text: str, name: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text, self)
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(Metrics.CONNECT_BUTTON[1])
        button.setMinimumWidth(Metrics.CONNECT_BUTTON[0])
        return button

    def _connect(self) -> None:
        self.bridge.request_connect(self.bridge.connection.server_id or AUTO_ID)

    def refresh(self) -> None:
        snapshot: ConnectionSnapshot = self.bridge.connection
        state = snapshot.state
        node = self.bridge.node(snapshot.server_id)
        if node is None:  # «самый быстрый»: показываем, из чего бэкенд будет выбирать
            countries = self.bridge.servers
            codes = list(dict.fromkeys(item.country_code for item in countries
                                       if item.group == GROUP_COUNTRIES and item.country_code))
            self.badge.show_icon("Bolt")
            self.title.setText("Самый быстрый сервер")
            self.subtitle.setText("Автоматически выбрано из" if codes else "Список серверов пуст")
            self.flags.set_codes(codes)
            self.more.setText(f"+{len(codes) - 3}" if len(codes) > 3 else "")
            self.more.setVisible(len(codes) > 3)
            self.pill.hide()
            self.info.setVisible(bool(codes))
            self.info.setToolTip("Сервер с наименьшей задержкой из доступных стран")
        else:
            if node.group == GROUP_COUNTRIES and node.country_code:
                self.badge.show_flag(node.country_code)
            else:
                self.badge.show_icon("Bolt")
            self.title.setText(node.country_name or node.name)
            parts = [node.city, node.name] if node.country_name else [node.city]
            self.subtitle.setText(" · ".join(part for part in parts if part) or "Сервер")
            self.flags.set_codes([])
            self.more.hide()
            self.pill.setText(node.protocol)
            self.pill.show()
            self.info.hide()
        self.connect_button.setVisible(state in (ConnectionState.DISCONNECTED,
                                                 ConnectionState.ERROR))
        self.connect_button.setText("Повторить" if state is ConnectionState.ERROR
                                    else "Подключить")
        self.cancel_button.setVisible(state is ConnectionState.CONNECTING)
        self.disconnect_button.setVisible(state is ConnectionState.CONNECTED)
        self.error.setVisible(state is ConnectionState.ERROR)
        self.error_text.setText(snapshot.detail or "Не удалось подключиться. Попробуйте ещё раз "
                                                   "или выберите другой сервер.")


class DetailRow(QtWidgets.QAbstractButton):
    """Ячейка сведений: мелкий заголовок и значение. Нажатие копирует значение."""

    def __init__(self, header: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.header, self.value = header, "—"
        self.setObjectName("DetailRow")
        self.setFixedHeight(Metrics.DETAIL_ROW)
        self.setMinimumWidth(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.clicked.connect(self._copy)
        theme.manager().changed.connect(self.update)
        self.set_value("—")

    def set_value(self, value: str) -> None:
        self.value = value or "—"
        self.setAccessibleName(f"{self.header}: {self.value}")
        self.setToolTip(f"{self.header}: {self.value}. Нажмите, чтобы скопировать")
        self.update()

    def _copy(self) -> None:
        QtGui.QGuiApplication.clipboard().setText(self.value)
        QtWidgets.QToolTip.showText(self.mapToGlobal(QtCore.QPoint(12, -8)), "Скопировано", self)

    def sizeHint(self) -> QtCore.QSize:
        metrics = QtGui.QFontMetrics(theme.font(theme.tokens.BODY_STRONG))
        return QtCore.QSize(metrics.horizontalAdvance(self.value) + 24, Metrics.DETAIL_ROW)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        box = QtCore.QRectF(self.rect())
        back = colors.fill_active if self.isDown() else (
            colors.fill_hover if self.underMouse() else None)
        if back is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor(back))
            painter.drawRoundedRect(box, Metrics.ROW_RADIUS, Metrics.ROW_RADIUS)
        room = box.width() - 24
        painter.setFont(theme.font(theme.tokens.CAPTION))
        painter.setPen(theme.qcolor(colors.text_weak))
        painter.drawText(QtCore.QRectF(12, 8, room, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(self.header,
                                                          Qt.TextElideMode.ElideRight, int(room)))
        painter.setFont(theme.font(theme.tokens.BODY_STRONG))
        painter.setPen(theme.qcolor(colors.text))
        painter.drawText(QtCore.QRectF(12, 26, room, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(self.value,
                                                          Qt.TextElideMode.ElideRight, int(room)))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), Metrics.ROW_RADIUS,
                                    Metrics.ROW_RADIUS)
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)


class SpeedPanel(QtWidgets.QFrame):
    """Текущие скорости (приём и отдача) над графиком за последнюю минуту."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SpeedPanel")
        self.unit = QtWidgets.QLabel("Скорость", self)
        self.unit.setObjectName("SpeedUnit")
        self.down = QtWidgets.QLabel("0 бит/с", self)
        self.down.setObjectName("SpeedValue")
        self.up = QtWidgets.QLabel("0 бит/с", self)
        self.up.setObjectName("SpeedValue")
        self.graph = TrafficGraphWidget(self)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        head.addWidget(self.unit)
        head.addStretch(1)
        head.addWidget(IconLabel("ArrowDownLine", 16, "chart_down", self))
        head.addWidget(self.down)
        head.addSpacing(4)
        head.addWidget(IconLabel("ArrowUpLine", 16, "chart_up", self))
        head.addWidget(self.up)
        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(12, 8, 12, 8)
        column.setSpacing(8)
        column.addLayout(head)
        column.addWidget(self.graph)

    def show_stats(self, stats: TrafficStats) -> None:
        self.down.setText(format_speed(stats.down_bps))
        self.up.setText(format_speed(stats.up_bps))
        self.graph.push(stats.down_bps, stats.up_bps)


class SessionDetailsView(QtWidgets.QWidget):
    """Строка статуса и сведения: без VPN — адрес, страна, провайдер; с VPN — метрики сеанса."""

    def __init__(self, bridge: VpnUiBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("SessionDetails")
        self.badge = StatusBadge(self)
        self.badge.setFixedHeight(Metrics.STATUS_ROW)
        self.rows = {
            "ip": DetailRow("Ваш IP-адрес", self),
            "country": DetailRow("Страна", self),
            "provider": DetailRow("Провайдер", self),
            "vpn_ip": DetailRow("IP-адрес VPN", self),
            "ping": DetailRow("Задержка", self),
            "protocol": DetailRow("Протокол", self),
            "volume": DetailRow("Объём", self),
        }
        self.speed = SpeedPanel(self)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(Metrics.EDGE)
        self.grid.setVerticalSpacing(0)
        status = QtWidgets.QHBoxLayout()
        status.setContentsMargins(10, 0, 0, 0)
        status.addWidget(self.badge)
        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addLayout(status)
        column.addLayout(self.grid)
        self._wide = True
        self._layout_key: tuple | None = None

        bridge.connection_changed.connect(self._connection)
        bridge.telemetry_changed.connect(self._telemetry)
        bridge.location_changed.connect(self._location)
        bridge.settings_changed.connect(lambda _settings: self._connection(bridge.connection))
        self._location(bridge.location)
        self._connection(bridge.connection)

    def set_wide(self, wide: bool) -> None:
        if wide != self._wide:
            self._wide = wide
            self._arrange()

    def _arrange(self) -> None:
        connected = self.bridge.connection.state is ConnectionState.CONNECTED
        key = (connected, self._wide)
        if key == self._layout_key:
            return
        self._layout_key = key
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(5):
            self.grid.setColumnStretch(column, 0)
            self.grid.setColumnMinimumWidth(column, 0)
        for widget in (*self.rows.values(), self.speed):
            widget.hide()
        if not connected:
            for column, name in enumerate(("ip", "country", "provider")):
                self.grid.addWidget(self.rows[name], 0, column)
                self.grid.setColumnStretch(column, 1)
                self.rows[name].show()
            return
        names = ("vpn_ip", "ping", "protocol", "volume")
        if self._wide:  # | A | B |   E   |  /  | C | D |       |
            for index, name in enumerate(names):
                self.grid.addWidget(self.rows[name], index // 2, index % 2)
            self.grid.addWidget(self.speed, 0, 2, 2, 1)
            self.grid.setColumnStretch(2, 1)
            self.grid.setColumnMinimumWidth(0, 160)
            self.grid.setColumnMinimumWidth(1, 210)  # «↓ 999,9 МБ  ↑ 999,9 МБ» целиком
        else:  # четыре ячейки в ряд, график под ними
            for column, name in enumerate(names):
                self.grid.addWidget(self.rows[name], 0, column)
                self.grid.setColumnStretch(column, 1)
                self.grid.setColumnMinimumWidth(column, 0)
            self.grid.addWidget(self.speed, 1, 0, 1, 4)
        for name in names:
            self.rows[name].show()
        self.speed.show()

    def _connection(self, snapshot: ConnectionSnapshot) -> None:
        self.badge.show_state(snapshot.state, snapshot.detail)
        node = self.bridge.node(snapshot.server_id)
        self.rows["protocol"].set_value(node.protocol if node else self.bridge.settings.protocol)
        if snapshot.state is not ConnectionState.CONNECTED:
            self.speed.graph.clear()
        self._arrange()

    def _telemetry(self, stats: TrafficStats) -> None:
        self.rows["vpn_ip"].set_value(stats.client_ip)
        self.rows["ping"].set_value(f"{stats.ping_ms} мс")
        self.rows["volume"].set_value(
            f"↓ {format_bytes(stats.total_down)}  ↑ {format_bytes(stats.total_up)}")
        if self.bridge.connection.state is ConnectionState.CONNECTED:
            self.speed.show_stats(stats)

    def _location(self, location: LocationInfo) -> None:
        self.rows["ip"].set_value(location.ip)
        self.rows["country"].set_value(location.country)
        self.rows["provider"].set_value(location.provider)
