"""Главное окно XGW: навигация слева и страницы. «Обзор» следует компоновке Proton VPN:
список серверов слева, карта во всю область, поверх неё — состояние защиты, карточка
подключения с кнопкой и плитки защиты сети. Нажатие на сервер открывает его карточку.

Страницы обновляют только тексты своих виджетов — ничего не создаётся заново на каждом опросе,
поэтому фокус, выделение и прокрутка не сбиваются.

Разделы используют общий сеанс локальной панели и показывают состояние шлюза.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QPointF, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import client as clienting
from . import model, theme
from .devices import DevicesPage
from .operations import DiagnosticsPage, ExtraPage
from .pages import ServersPage, SubscriptionsPage
from .traffic import TrafficPage
from .widgets import (
    Badge,
    Elided,
    FeatureTile,
    Metric,
    NavRail,
    ServerList,
    ShieldOrb,
    StateHead,
    icon,
    label,
    set_text,
    tip,
    tone,
)
from .zapret2 import Zapret2Page
from .zapret2 import summary as zapret2_summary

SECTIONS = (
    ("overview", "Обзор"),
    ("servers", "Серверы"),
    ("subscriptions", "Подписки"),
    ("devices", "Устройства"),
    ("traffic", "Трафик"),
    ("diagnostics", "Диагностика"),
    ("extra", "Ещё"),
    ("zapret2", "zapret2"),
)
MIN_SIZE = (1024, 720)
START_SIZE = (1280, 820)
SERVERS_WIDTH = (310, 340)
CARD_WIDTH = (340, 380)  # карточка подключения поверх карты
EDGE = 24  # поля области с картой
WIDE = 1200
FAIL_SHORT = {"closed": "Интернет закрывается: мимо VPN ничего не уходит",
              "open": "Трафик временно идёт напрямую"}


def _marked(tone_name: str, text: str) -> str:
    return f"{model.MARKS.get(tone_name, '')} {text}".strip()


def _scroll(inner: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner.setObjectName("page")
    scroll.setWidget(inner)
    return scroll


class Card(QFrame):
    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 16, 20, 18)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(label(title, name="cardTitle", wrap=False))


def _centered(card: QWidget, width: int) -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    outer = QVBoxLayout(page)
    outer.addStretch(1)
    row = QHBoxLayout()
    row.addStretch(1)
    card.setMaximumWidth(width)
    row.addWidget(card, 3)
    row.addStretch(1)
    outer.addLayout(row)
    outer.addStretch(2)
    return page


class LoginPage(QWidget):
    def __init__(self, on_login) -> None:
        super().__init__()
        self.setObjectName("page")
        card = Card()
        card.body.setContentsMargins(28, 26, 28, 26)
        card.body.setSpacing(12)
        title = label("Вход в XGW", name="pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addWidget(title)
        about = label("Окно управляет шлюзом через его панель на этой машине. Чтобы войти, "
                      "Ubuntu спросит пароль администратора — один раз: вход запоминается, "
                      "как в браузере.", name="muted")
        about.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addWidget(about)
        self.error = label("")
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tone(self.error, "bad")
        self.error.hide()
        card.body.addWidget(self.error)
        card.body.addSpacing(6)
        self.button = QPushButton("Войти")
        self.button.setObjectName("connect")
        tone(self.button, "off")
        self.button.setMinimumHeight(46)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setAccessibleName("Войти в XGW с паролем администратора")
        self.button.clicked.connect(on_login)
        card.body.addWidget(self.button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_centered(card, 460))

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)
        self.button.setText("Ждём пароль администратора…" if busy else "Войти")

    def set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))


class OverviewPage(QWidget):
    """Компоновка Proton VPN: список серверов слева, карта во всю область и поверх неё —
    заголовок состояния, карточка подключения с кнопкой и плитки защиты сети."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__()
        self.main = main
        self.setObjectName("page")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.server_panel = self._servers()
        self.server_panel.setFixedWidth(SERVERS_WIDTH[1])
        outer.addWidget(self.server_panel)
        outer.addWidget(self._connection(), 1)

    # --- карта и карточка подключения -----------------------------------------------------------

    def _connection(self) -> QWidget:
        self.conn = QFrame()
        self.conn.setObjectName("conn")
        layers = QStackedLayout(self.conn)
        layers.setContentsMargins(0, 0, 0, 0)
        layers.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.orb = ShieldOrb()
        layers.addWidget(self.orb)
        content = QWidget()
        content.setObjectName("connectionContent")
        layers.addWidget(content)
        layers.setCurrentWidget(content)
        box = QVBoxLayout(content)
        box.setContentsMargins(EDGE, 22, EDGE, 10)
        box.setSpacing(0)

        self.head = StateHead()
        self.word = self.head.word
        box.addWidget(self.head)
        box.addSpacing(4)
        self.power_sub = label("", name="heroSub")
        self.power_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.power_sub)
        box.addSpacing(18)

        middle = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(10)
        column.addWidget(self._card())
        self.zapret2 = QPushButton("zapret2")
        self.zapret2.setObjectName("linkRow")
        self.zapret2.setIcon(icon("zapret2", theme.current()["accent"], size=18))
        self.zapret2.setIconSize(QSize(18, 18))
        self.zapret2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zapret2.setAccessibleName("Состояние и управление zapret2")
        self.zapret2.setToolTip("Открыть раздел zapret2: обход блокировок для выбранных доменов")
        self.zapret2.clicked.connect(lambda: self.main.open_section("zapret2"))
        column.addWidget(self.zapret2)
        column.addStretch(1)
        middle.addLayout(column)
        middle.addStretch(1)
        box.addLayout(middle, 1)
        box.addSpacing(12)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = {key: FeatureTile(title, about) for key, title, about in (
            ("capture", "Перехват", "Что демон XGW делает с трафиком прямо сейчас"),
            ("fail", "При сбое Xray", "Что будет с интернетом, если Xray перестанет отвечать"),
            ("bypass", "Мимо VPN", "Устройства, которым разрешён выход мимо VPN"))}
        for tile in self.tiles.values():
            tiles.addWidget(tile, 1)
        self.lifecycle = self.tiles["capture"].value
        self.guard = {key: self.tiles[key].value for key in ("fail", "bypass")}
        box.addLayout(tiles)
        box.addSpacing(8)

        foot = QHBoxLayout()
        self.versions = label("", name="small", wrap=False)
        self.versions.setAccessibleName("Версии")
        foot.addWidget(self.versions)
        foot.addStretch(1)
        self.fresh = label("", name="small", wrap=False)
        self.fresh.setAccessibleName("Обновление данных")
        foot.addWidget(self.fresh)
        box.addLayout(foot)
        return self.conn

    def _card(self) -> QWidget:
        self.card = QFrame()
        self.card.setObjectName("connCard")
        self.card.setFixedWidth(CARD_WIDTH[1])
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(40, 30, 90, 34))
        self.card.setGraphicsEffect(shadow)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(12)
        self.power_title = label("", name="heroTitle")
        box.addWidget(self.power_title)

        server = QHBoxLayout()
        server.setSpacing(12)
        self.badge = Badge(44)
        server.addWidget(self.badge)
        names = QVBoxLayout()
        names.setSpacing(1)
        self.server_name = Elided(name="serverName")
        self.server_name.setAccessibleName("Сервер в работе")
        self.server_how = label("", name="small", wrap=False)
        names.addWidget(self.server_name)
        names.addWidget(self.server_how)
        server.addLayout(names, 1)
        box.addLayout(server)

        self.power = QPushButton("Включить VPN")
        self.power.setObjectName("connect")
        self.power.setMinimumHeight(46)
        self.power.setCursor(Qt.CursorShape.PointingHandCursor)
        self.power.clicked.connect(self.main.toggle_power)
        box.addWidget(self.power)
        self.power_why = label("", name="small")
        tone(self.power_why, "warn")
        box.addWidget(self.power_why)

        line = QFrame()
        line.setObjectName("divider")
        box.addWidget(line)
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.metrics = {key: Metric(title, about) for key, title, about in (
            ("speed", "Скорость", "Последний замер скорости через этот сервер"),
            ("rtt", "RTT", "Время установления соединения с сервером (проба шлюза)"),
            ("delay", "Проба", "Полная проба ядра: запрос через сервер и ответ целиком"))}
        for widget in self.metrics.values():
            tiles.addWidget(widget, 1)
        box.addLayout(tiles)
        self.engine = label("", name="small", wrap=False)
        box.addWidget(self.engine)
        return self.card

    def place(self, wide: bool) -> None:
        """Ширины под размер окна и точка карты: страна сервера — в свободной части справа."""
        self.server_panel.setFixedWidth(SERVERS_WIDTH[wide])
        self.card.setFixedWidth(CARD_WIDTH[wide])
        width, height = self.conn.width(), self.conn.height()
        left = EDGE + CARD_WIDTH[wide]
        self.orb.set_focus(QPointF(left + max(120.0, (width - left) / 2), height * .5 - 16))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(self.main.width() >= WIDE)

    # --- серверы --------------------------------------------------------------------------------

    def _servers(self) -> QWidget:
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(12, 20, 12, 16)
        box.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 8, 0)
        head.addWidget(label("Серверы", name="listTitle", wrap=False))
        head.addStretch(1)
        self.counts = label("", name="small", wrap=False)
        head.addWidget(self.counts)
        box.addLayout(head)
        self.main.chip = label("", name="chip", wrap=False)
        self.main.chip.setAccessibleName("Состояние шлюза")
        chip = QHBoxLayout()
        chip.setContentsMargins(8, 0, 8, 0)
        chip.addWidget(self.main.chip)
        chip.addStretch(1)
        box.addLayout(chip)

        self.alert = QFrame()
        self.alert.setObjectName("alert")
        alert = QVBoxLayout(self.alert)
        alert.setContentsMargins(14, 12, 14, 12)
        alert.setSpacing(6)
        self.state = label("", name="cardTitle")
        self.state.setAccessibleName("Состояние шлюза")
        self.explain = label("", name="small")
        alert.addWidget(self.state)
        alert.addWidget(self.explain)
        fixes = QVBoxLayout()
        self.fix_buttons: dict[str, QPushButton] = {}
        for name, title in (("refresh", "Обновить подписки"), ("scan", "Проверить запасные"),
                            ("netcheck", "Проверить сеть")):
            button = QPushButton(title)
            button.setAccessibleName(title)
            button.clicked.connect(lambda _c=False, act=name: self.main.run_action(act))
            button.hide()
            fixes.addWidget(button)
            self.fix_buttons[name] = button
        alert.addLayout(fixes)
        box.addWidget(self.alert)
        box.addSpacing(4)

        self.members_title = self._section_title()
        box.addWidget(self.members_title)
        self.members = ServerList()
        box.addWidget(self.members)
        box.addSpacing(4)
        self.spares_title = self._section_title()
        box.addWidget(self.spares_title)
        self.spares = ServerList()
        box.addWidget(self.spares)
        self.hidden = label("", name="small")
        self.hidden.setContentsMargins(8, 4, 8, 0)
        box.addWidget(self.hidden)
        self.all_servers = QPushButton("Все серверы и замеры")
        self.all_servers.setAccessibleName("Открыть раздел «Серверы»")
        self.all_servers.clicked.connect(lambda: self.main.open_section("servers"))
        box.addWidget(self.all_servers)
        box.addStretch(1)
        scroll = _scroll(inner)
        inner.setObjectName("serverPanel")
        scroll.setObjectName("serverScroll")
        return scroll

    @staticmethod
    def _section_title() -> QLabel:
        title = label("", name="section", wrap=False)
        title.setContentsMargins(8, 0, 8, 0)
        return title

    # --- отображение ----------------------------------------------------------------------------

    def show_state(self, state: dict | None, stale: bool) -> None:
        acting = self.main.client.actions.busy("power")
        zapret_tone, zapret_text = zapret2_summary(state, stale)
        self.zapret2.setText(zapret_text)
        tone(self.zapret2, zapret_tone)
        power = model.power(state, stale, acting=acting)
        shield_tone, word = model.shield(state, stale, acting=acting)
        tone(self.conn, shield_tone)
        # Как у Proton: «не защищено» — красным, хотя для шлюза это не авария (тон off).
        self.head.show_state("bad" if shield_tone == "off" else shield_tone, word,
                             locked=shield_tone == "ok")
        self.orb.set_tone(shield_tone)
        set_text(self.power_title, power.title)
        zapret = (state or {}).get("zapret2") or {}
        direct_mode = bool(zapret.get("mode") == "standalone" or zapret.get("without_vpn"))
        extra = (" Выбранные домены идут через zapret2 с домашним IP."
                 if not stale and not direct_mode and zapret.get("state") == "active" else "")
        set_text(self.power_sub, power.sub + extra)
        self.power.setText("Выключаю…" if acting and power.pressed else
                           "Включаю…" if acting else
                           ("Выключить перехват" if power.pressed else "Включить zapret2")
                           if direct_mode else
                           ("Выключить VPN" if power.pressed else "Включить VPN"))
        self.power.setAccessibleName(self.power.text())
        self.power.setEnabled(power.enabled)
        tone(self.power, "on" if power.pressed else "off")
        set_text(self.power_why, power.why)
        self.power_why.setVisible(bool(power.why))
        line = model.lifecycle(state, stale)
        capture = (state or {}).get("capture") or {}
        if line is not None:
            tone(self.lifecycle, line[0])
            set_text(self.lifecycle, _marked(line[0], line[1].removeprefix("Перехват: ")))
        else:
            tone(self.lifecycle, "off")
            set_text(self.lifecycle, "—" if state is None or stale else
                     "Прямой интернет без VPN" if direct_mode and capture.get("mode") == "on"
                     else "выключен — трафик идёт напрямую"
                     if capture.get("mode") in ("off", "none") else "—")

        # Без VPN сервер подписки не участвует: его имя и замеры здесь вводили бы в заблуждение.
        main = None if direct_mode else model.main_server(state)
        self.orb.set_country(main.country if main is not None else "")
        if main is None:
            self.badge.show_country("", "")
            set_text(self.server_name, "Домашний адрес" if direct_mode and state else
                     "Сервер не выбран" if state else "—")
            set_text(self.server_how, "VPN-серверы не используются" if direct_mode and state
                     else "шлюз ещё не выбрал сервер" if state else "")
            for metric in self.metrics.values():
                metric.set("—")
            set_text(self.engine, "")
        else:
            flag, name = model.split_flag(main.name)
            self.badge.show_country(flag, main.country)
            set_text(self.server_name, name)
            tip(self.server_name, name)
            set_text(self.server_how, "выбран вручную" if main.pinned else
                     "выбран по замеру скорости" if main.basis == "speed" else
                     "выбран по задержке")
            self.metrics["speed"].set(model.mbps_text(main.speed_mbps))
            self.metrics["rtt"].set(model.ms_text(main.rtt_ms))
            self.metrics["delay"].set(model.ms_text(main.delay_ms))
            engine = " · ".join(part for part in (
                f"ядро {main.core}" if main.core else "",
                f"профиль {main.profile.split(':', 1)[-1]}" if main.profile else "") if part)
            set_text(self.engine, engine)
        self.engine.setVisible(bool(self.engine.text()))
        found = dict(model.versions(state))
        set_text(self.versions, " · ".join(f"{name} {found[name]}" for name in
                                           ("XGW", "Xray", "sing-box") if found.get(name)))
        self._show_health(state, stale)
        self._show_servers(state)
        self._show_guard(state)

    def _show_health(self, state: dict | None, stale: bool) -> None:
        health_tone, text = model.health(state, stale)
        detail, fixes = self._explain(state, stale)
        self.alert.setVisible(health_tone != "ok" or bool(detail))
        self.main.chip.setVisible(self.alert.isHidden())  # одно и то же дважды не пишем
        tone(self.alert, health_tone)
        tone(self.state, health_tone)
        set_text(self.state, _marked(health_tone, text))
        set_text(self.explain, detail)
        self.explain.setVisible(bool(detail))
        for name, button in self.fix_buttons.items():
            button.setVisible(name in fixes)
            button.setEnabled(not self.main.client.actions.busy(name)
                              and not _busy(state, name))

    def _show_servers(self, state: dict | None) -> None:
        members, spares, hidden = model.server_rows(state)
        alive = sum(1 for row in members if row.tone == "ok")
        set_text(self.counts, f"работают {alive} из {len(members)}" if members else "")
        set_text(self.members_title, f"В РАБОТЕ · {len(members)}" if members else "")
        self.members_title.setVisible(bool(members))
        self.members.show_rows(members, state)
        set_text(self.spares_title, f"ЗАПАСНЫЕ · {len(spares)}" if spares else "")
        self.spares_title.setVisible(bool(spares))
        self.spares.show_rows(spares, state)
        set_text(self.hidden, f"Ещё {hidden} строк подписок не в работе: выключены или не "
                              "серверы." if hidden else "")
        self.hidden.setVisible(bool(hidden))
        self.all_servers.setVisible(bool(state))

    def _show_guard(self, state: dict | None) -> None:
        capture = (state or {}).get("capture") or {}
        mode = str(capture.get("fail_mode") or "")
        set_text(self.guard["fail"], FAIL_SHORT.get(mode, "—"))
        tip(self.tiles["fail"], model.capital(model.FAIL_MODES.get(mode, "")) or
            "Что будет с интернетом, если Xray перестанет отвечать")
        bypass = capture.get("bypass") or []
        set_text(self.guard["bypass"], f"Устройств: {len(bypass)}" if bypass else
                 "Нет: все устройства идут через шлюз" if capture else "—")

    @staticmethod
    def _explain(state: dict | None, stale: bool) -> tuple[str, set[str]]:
        """Что случилось и какие кнопки могут помочь (только существующие действия панели)."""
        if state is None:
            return "Окно не получает ответа от панели XGW на этой машине.", set()
        if stale:
            return ("Демон XGW давно не обновлял состояние: показанное могло устареть. "
                    "Проверьте службу: sudo systemctl status xgw"), set()
        name = str(state.get("state") or "")
        # HEALTHY: «вмешательство не требуется» — не повод для карточки предупреждения.
        action = "" if name == "HEALTHY" else str(state.get("action") or "")
        fixes = {
            "ALL_DEAD": {"refresh", "scan"}, "DEGRADED": {"scan"}, "RESERVE": {"refresh", "scan"},
            "WAN_DOWN": {"netcheck"}, "PROBE_TARGET_UNREACHABLE": {"netcheck"},
            "LEAK": {"netcheck"}, "XRAY_DOWN": set(),
        }.get(name, set())
        if not state.get("members") and not (state.get("subscriptions") or state.get("links")):
            return "Серверов нет: добавьте подписку или ссылку сервера (раздел «Подписки»).", set()
        extra = [str(state.get(key) or "") for key in ("stranded", "class_warning",
                                                      "probe_target")]
        return " ".join(part for part in [model.capital(action), *extra] if part), fixes


def _busy(state: dict | None, name: str) -> bool:
    busy = (state or {}).get("busy") or {}
    if name == "netcheck":
        return bool(((state or {}).get("netcheck") or {}).get("running"))
    return bool(busy.get(name))


class MainWindow(QMainWindow):
    closed = pyqtSignal()  # окно закрыто: программе пора выходить (app._watch_exit)

    def __init__(self, client: clienting.ApiClient, login, session_path) -> None:
        super().__init__()
        self.client, self.login, self.session_path = client, login, session_path
        self.settings = QSettings("XGW", "gui")
        self.state: dict | None = None
        self.received: float | None = None  # time.monotonic() последнего ответа
        self.link = ""
        self.chip: QLabel  # метка состояния — в заголовке списка серверов «Обзора»
        self.setWindowTitle("XGW")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(*START_SIZE)

        central = QWidget()
        self.setCentralWidget(central)
        body = QHBoxLayout(central)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = NavRail(SECTIONS)
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.login_page = LoginPage(self.start_login)
        self.overview = OverviewPage(self)
        self.servers = ServersPage(self)
        self.subscriptions = SubscriptionsPage(self)
        self.devices = DevicesPage(self)
        self.traffic = TrafficPage(self)
        self.diagnostics = DiagnosticsPage(self)
        self.extra = ExtraPage(self)
        self.zapret2 = Zapret2Page(self)
        self.pages: dict[str, QWidget] = {"overview": self.overview, "servers": self.servers,
                                          "subscriptions": self.subscriptions,
                                          "devices": self.devices, "traffic": self.traffic,
                                          "diagnostics": self.diagnostics, "extra": self.extra,
                                          "zapret2": self.zapret2}
        for key, _title in SECTIONS:
            self.stack.addWidget(self.pages[key])
        self.stack.addWidget(self.login_page)
        self.nav.currentRowChanged.connect(self._section)
        self.nav.setCurrentRow(0)
        for number in range(len(SECTIONS)):
            QShortcut(QKeySequence(f"Ctrl+{number + 1}"), self,
                      activated=lambda row=number: self.nav.setCurrentRow(row))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.client.poll_soon(0.0))
        self.statusBar().showMessage("Подключаюсь к панели XGW…")
        self.statusBar().setSizeGripEnabled(False)
        self.recolor()

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start(1000)
        client.stateReceived.connect(self.on_state)
        client.linkChanged.connect(self.on_link)
        client.actionFinished.connect(self.on_action)
        client.busyChanged.connect(lambda _key, _busy: self.render())
        login.finished.connect(self.on_login)
        self.render()

    # --- события клиента --------------------------------------------------------------------

    def on_state(self, state: dict) -> None:
        self.state, self.received = state, time.monotonic()
        if self.stack.currentWidget() is self.login_page:
            self._section(self.nav.currentRow())
        self.render()

    def on_link(self, link: str, text: str) -> None:
        self.link = link
        if link == clienting.LINK_AUTH:
            self.stack.setCurrentWidget(self.login_page)
            self.login_page.set_error("" if self.client.session is None else
                                      "Вход устарел — войдите снова")
        if text:
            self.statusBar().showMessage(text)
        elif link == clienting.LINK_OK:
            self.statusBar().clearMessage()
        self.render()

    def on_action(self, key: str, ok: bool, text: str) -> None:
        self.statusBar().showMessage(_marked("ok" if ok else "bad", text), 15000)
        self.subscriptions.action_done(key, ok)
        self.render()

    # --- вход ---------------------------------------------------------------------------------

    def start_login(self) -> None:
        if self.login.start():
            self.login_page.set_busy(True)
            self.login_page.set_error("")

    def on_login(self, session, text: str) -> None:
        self.login_page.set_busy(False)
        if session is None:
            self.login_page.set_error(text)
            return
        try:
            model.save_session(self.session_path, session)
        except OSError as exc:
            self.statusBar().showMessage(f"Вход не запомнен: {exc}", 15000)
        self.client.set_session(session)
        self._section(self.nav.currentRow())

    # --- действия -----------------------------------------------------------------------------

    def toggle_power(self) -> None:
        power = model.power(self.state, self.stale, acting=self.client.actions.busy("power"))
        if power.enabled:
            self.client.act("power", {"on": not power.pressed}, key="power")

    def run_action(self, name: str) -> None:
        self.client.act(name, {}, key=name)

    def open_section(self, key: str) -> None:
        self.nav.setCurrentRow(next(i for i, (name, _) in enumerate(SECTIONS) if name == key))

    def open_browser(self) -> None:
        session = self.client.session
        port = session.port if session is not None else 8781
        QDesktopServices.openUrl(QUrl(f"http://127.0.0.1:{port}/"))

    # --- отображение --------------------------------------------------------------------------

    @property
    def stale(self) -> bool:
        if self.state is None or self.link == clienting.LINK_OFFLINE:
            return True
        return model.is_stale(self.state)

    def freshness_text(self) -> str:
        if self.received is None:
            return "Данные ещё не получены"
        age = time.monotonic() - self.received
        if self.link == clienting.LINK_OFFLINE:
            return f"Панель не отвечает; последние данные — {model.ago_text(age)}"
        if self.stale:
            return f"Данные устарели: демон не отвечает (получено {model.ago_text(age)})"
        return f"Обновлено {model.ago_text(age)}"

    def render(self) -> None:
        state = None if self.link == clienting.LINK_OFFLINE and self.state is None else self.state
        stale = self.stale
        if self.link == clienting.LINK_OFFLINE:
            chip_tone, text = "bad", "Панель XGW не отвечает"
        else:
            chip_tone, text = (model.health(state, stale) if state is not None
                               else ("off", "Подключение…"))
        tone(self.chip, chip_tone)
        set_text(self.chip, _marked(chip_tone, text))
        self.overview.show_state(state, stale)
        current = self.stack.currentWidget()
        if current in (self.servers, self.subscriptions, self.devices,
                       self.diagnostics, self.extra, self.zapret2):
            current.show_state(state)
        elif current is self.traffic:
            self.traffic.refresh()
        self._logo(model.shield(state, stale)[0] if state is not None else "off")
        self._tick()

    def _logo(self, shield_tone: str) -> None:
        if self.nav.logo.property("tone") == shield_tone:
            return
        self.nav.logo.setProperty("tone", shield_tone)
        from PyQt6 import QtCore, QtGui

        from .. import trayapp

        kind = {"bad": "down", "busy": "job"}.get(shield_tone, shield_tone)
        self.nav.logo.setPixmap(trayapp.icon(QtGui, QtCore, kind).pixmap(36, 36))

    def _tick(self) -> None:
        text = "Обновляю…" if self.client.gate.busy else self.freshness_text()
        set_text(self.overview.fresh, text)

    def _section(self, row: int) -> None:
        if self.link == clienting.LINK_AUTH or self.client.session is None:
            self.stack.setCurrentWidget(self.login_page)
            return
        key = SECTIONS[max(0, row)][0]
        self.stack.setCurrentWidget(self.pages[key])
        if key in ("servers", "subscriptions", "devices", "diagnostics", "extra", "zapret2"):
            self.pages[key].show_state(self.state)
        elif key == "traffic":
            self.traffic.refresh()

    def recolor(self) -> None:
        """Значки рисуются цветом темы — после её смены их надо нарисовать заново."""
        colors = theme.current()
        self.nav.recolor(colors, {})
        self.servers.recolor()
        self.update()

    # --- видимость: опрос реже, пока окно не видно ------------------------------------------

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        self.client.close()  # демон, Xray и sing-box работают дальше
        super().closeEvent(event)
        self.closed.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.client.set_visible(True)
        if self.focusWidget() is None:
            self.stack.setFocus()  # без рамки фокуса на первой кнопке при запуске

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= WIDE
        self.nav.set_wide(wide)
        self.overview.place(wide)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.client.set_visible(False)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.client.set_visible(not self.isMinimized())
