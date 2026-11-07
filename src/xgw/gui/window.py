"""Главное окно XGW: узкая навигация со значками слева и страницы. «Обзор» устроен как у
современных VPN-клиентов: слева панель подключения (знак защиты, сервер в работе, крупные
метрики, большая кнопка VPN), справа — список серверов карточками.

Страницы обновляют только тексты своих виджетов — ничего не создаётся заново на каждом опросе,
поэтому фокус, выделение и прокрутка не сбиваются.

Этап 1–2 (docs/GUI-NATIVE.md): вход, «Обзор» и переключатель VPN. Разделы, которые ещё не
перенесены в окно, честно говорят об этом и открывают тот же раздел браузерной панели.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import client as clienting
from . import model, theme
from .widgets import (
    Badge,
    Metric,
    NavRail,
    ServerList,
    ShieldOrb,
    icon,
    label,
    set_text,
    tone,
)

SECTIONS = (
    ("overview", "Обзор"),
    ("servers", "Серверы"),
    ("subscriptions", "Подписки"),
    ("devices", "Устройства"),
    ("traffic", "Трафик"),
    ("diagnostics", "Диагностика"),
    ("extra", "Ещё"),
)
# Разделы, которые пока только в браузерной панели: что там есть.
PENDING = {
    "servers": "Серверы подписок и бесплатного пула: выбор сервера, приоритет, ядро, замеры "
               "скорости, проверка запасных.",
    "subscriptions": "Подписки и отдельные ссылки серверов: добавить, изменить, обновить, убрать.",
    "devices": "Устройства сети: маршрут через VPN или напрямую, свой сервер, запись трафика.",
    "traffic": "Расход трафика по устройствам, подпискам и бесплатному пулу.",
    "diagnostics": "«Проверить сеть», журнал событий, обновление ядер Xray и sing-box.",
    "extra": "Tailscale (вход, SSH, панель по tailnet, Funnel) и телефоны.",
}
TITLES = dict(SECTIONS) | {"extra": "Дополнительно"}
MIN_SIZE = (1024, 720)
START_SIZE = (1440, 900)
CONN_WIDTH = (360, 400)  # панель подключения: в узком окне и в широком
WIDE = 1200


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
        self.orb = ShieldOrb()
        self.orb.setMinimumHeight(150)
        card.body.addWidget(self.orb)
        title = label("Вход в XGW", name="heroTitle")
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
        self.button.setAccessibleName("Войти в XGW с паролем администратора")
        self.button.clicked.connect(on_login)
        card.body.addWidget(self.button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_centered(card, 520))

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)
        self.button.setText("Ждём пароль администратора…" if busy else "Войти")

    def set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))


class PendingPage(QWidget):
    """Раздел ещё в браузерной панели: что в нём и кнопка открыть его там."""

    def __init__(self, key: str, title: str, about: str, open_panel) -> None:
        super().__init__()
        self.setObjectName("page")
        card = Card()
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key = key
        card.body.addWidget(self.picture)
        head = label(title, name="pageTitle")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addWidget(head)
        for text, name in ((about, ""), ("В окно этот раздел ещё переносится. Пока он работает "
                                         "в браузерной панели XGW — с теми же действиями.",
                                         "muted")):
            line = label(text, name=name)
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.body.addWidget(line)
        card.body.addSpacing(6)
        button = QPushButton("Открыть в браузерной панели")
        button.setObjectName("primary")
        button.setAccessibleName(f"Открыть раздел «{title}» в браузерной панели")
        button.clicked.connect(open_panel)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        row.addStretch(1)
        card.body.addLayout(row)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_centered(card, 560))

    def recolor(self, colors: dict[str, str]) -> None:
        self.picture.setPixmap(icon(self.key, colors["accent"], size=56).pixmap(56, 56))


class OverviewPage(QWidget):
    """«Обзор»: панель подключения слева, серверы и защита сети справа."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__()
        self.main = main
        self.setObjectName("page")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._connection())
        outer.addWidget(self._servers(), 1)

    # --- панель подключения ---------------------------------------------------------------------

    def _connection(self) -> QWidget:
        self.conn = QFrame()
        self.conn.setObjectName("conn")
        self.conn.setFixedWidth(CONN_WIDTH[1])
        box = QVBoxLayout(self.conn)
        box.setContentsMargins(28, 26, 28, 18)
        box.setSpacing(6)
        self.word = label("", name="shieldWord", wrap=False)
        font = self.word.font()
        font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 1.4)
        self.word.setFont(font)
        self.word.setAccessibleName("Защита")
        box.addWidget(self.word)
        self.power_title = label("", name="heroTitle")
        box.addWidget(self.power_title)
        self.power_sub = label("", name="muted")
        box.addWidget(self.power_sub)
        self.lifecycle = label("", name="small")
        box.addWidget(self.lifecycle)
        box.addStretch(1)
        self.orb = ShieldOrb()
        self.orb.setMaximumHeight(250)
        box.addWidget(self.orb, 4)
        box.addStretch(1)

        server = QHBoxLayout()
        server.setSpacing(12)
        self.badge = Badge(40)
        server.addWidget(self.badge)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.server_name = label("", name="serverName")
        self.server_name.setAccessibleName("Сервер в работе")
        self.server_how = label("", name="small")
        names.addWidget(self.server_name)
        names.addWidget(self.server_how)
        server.addLayout(names, 1)
        box.addLayout(server)
        box.addSpacing(6)

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.metrics = {key: Metric(title, about) for key, title, about in (
            ("speed", "Скорость", "Последний замер скорости через этот сервер"),
            ("rtt", "RTT", "Время установления соединения с сервером (проба шлюза)"),
            ("delay", "Проба", "Полная проба ядра: запрос через сервер и ответ целиком"))}
        for widget in self.metrics.values():
            tiles.addWidget(widget)
        box.addLayout(tiles)
        self.engine = label("", name="small")
        box.addWidget(self.engine)
        box.addSpacing(10)

        self.power = QPushButton("Включить VPN")
        self.power.setObjectName("connect")
        self.power.setMinimumHeight(52)
        self.power.clicked.connect(self.main.toggle_power)
        box.addWidget(self.power)
        self.power_why = label("")
        tone(self.power_why, "warn")
        box.addWidget(self.power_why)
        box.addSpacing(8)
        self.versions = label("", name="small")
        self.versions.setAccessibleName("Версии")
        box.addWidget(self.versions)
        self.fresh = label("", name="small", wrap=False)
        self.fresh.setAccessibleName("Обновление данных")
        box.addWidget(self.fresh)
        return self.conn

    # --- серверы и защита сети ------------------------------------------------------------------

    def _servers(self) -> QWidget:
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(28, 24, 28, 24)
        box.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("Серверы", name="pageTitle", wrap=False))
        self.counts = label("", name="muted", wrap=False)
        head.addWidget(self.counts, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.main.chip = label("", name="chip", wrap=False)
        self.main.chip.setAccessibleName("Состояние шлюза")
        head.addWidget(self.main.chip)
        box.addLayout(head)

        self.alert = QFrame()
        self.alert.setObjectName("alert")
        alert = QVBoxLayout(self.alert)
        alert.setContentsMargins(16, 12, 16, 14)
        alert.setSpacing(6)
        self.state = label("", name="cardTitle")
        self.state.setAccessibleName("Состояние шлюза")
        self.explain = label("", name="muted")
        alert.addWidget(self.state)
        alert.addWidget(self.explain)
        fixes = QHBoxLayout()
        self.fix_buttons: dict[str, QPushButton] = {}
        for name, title in (("refresh", "Обновить подписки"), ("scan", "Проверить запасные"),
                            ("netcheck", "Проверить сеть")):
            button = QPushButton(title)
            button.setAccessibleName(title)
            button.clicked.connect(lambda _c=False, act=name: self.main.run_action(act))
            button.hide()
            fixes.addWidget(button)
            self.fix_buttons[name] = button
        fixes.addStretch(1)
        alert.addLayout(fixes)
        box.addWidget(self.alert)

        self.members_title = label("", name="section", wrap=False)
        box.addWidget(self.members_title)
        self.members = ServerList()
        box.addWidget(self.members)
        self.spares_title = label("", name="section", wrap=False)
        box.addWidget(self.spares_title)
        self.spares = ServerList()
        box.addWidget(self.spares)
        self.hidden = label("", name="small")
        box.addWidget(self.hidden)

        box.addSpacing(8)
        box.addWidget(label("ЗАЩИТА СЕТИ", name="section", wrap=False))
        guard = Card()
        self.guard: dict[str, QLabel] = {}
        for key, title in (("scope", "Через VPN"), ("fail", "При сбое Xray"),
                           ("bypass", "Мимо VPN")):
            row = QHBoxLayout()
            name = label(title, name="muted", wrap=False)
            name.setFixedWidth(130)
            value = label("—")
            value.setAccessibleName(title)
            row.addWidget(name, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(value, 1)
            guard.body.addLayout(row)
            self.guard[key] = value
        box.addWidget(guard)
        box.addStretch(1)
        return _scroll(inner)

    # --- отображение ----------------------------------------------------------------------------

    def show_state(self, state: dict | None, stale: bool) -> None:
        acting = self.main.client.actions.busy("power")
        power = model.power(state, stale, acting=acting)
        shield_tone, word = model.shield(state, stale, acting=acting)
        tone(self.conn, shield_tone)
        tone(self.word, shield_tone)
        set_text(self.word, word.upper())
        self.orb.set_tone(shield_tone)
        set_text(self.power_title, power.title)
        set_text(self.power_sub, power.sub)
        self.power.setText("Выключаю…" if acting and power.pressed else
                           "Включаю…" if acting else
                           ("Выключить VPN" if power.pressed else "Включить VPN"))
        self.power.setAccessibleName(self.power.text())
        self.power.setEnabled(power.enabled)
        tone(self.power, "on" if power.pressed else "off")
        set_text(self.power_why, power.why)
        self.power_why.setVisible(bool(power.why))
        line = model.lifecycle(state, stale)
        self.lifecycle.setVisible(line is not None)
        if line is not None:
            tone(self.lifecycle, line[0])
            set_text(self.lifecycle, _marked(line[0], line[1]))

        main = model.main_server(state)
        if main is None:
            self.badge.show_country("", "")
            set_text(self.server_name, "Сервер не выбран" if state else "—")
            set_text(self.server_how, "шлюз ещё не выбрал сервер" if state else "")
            for metric in self.metrics.values():
                metric.set("—")
            set_text(self.engine, "")
        else:
            flag, name = model.split_flag(main.name)
            self.badge.show_country(flag, main.country)
            set_text(self.server_name, name)
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
        self.members.show_rows(members)
        set_text(self.spares_title, f"ЗАПАСНЫЕ · {len(spares)}" if spares else "")
        self.spares_title.setVisible(bool(spares))
        self.spares.show_rows(spares)
        set_text(self.hidden, (f"Ещё {hidden} строк подписок не в работе (выключены или не "
                               "серверы). Выбор сервера, приоритет и замеры — в разделе "
                               "«Серверы».") if hidden else
                 "Выбор сервера, приоритет и замеры — в разделе «Серверы».")

    def _show_guard(self, state: dict | None) -> None:
        capture = (state or {}).get("capture") or {}
        set_text(self.guard["scope"], model.scope_text(capture) if capture.get("mode") == "on"
                 else "ничего: VPN выключен" if capture else "—")
        set_text(self.guard["fail"],
                 model.FAIL_MODES.get(str(capture.get("fail_mode") or ""), "—"))
        bypass = capture.get("bypass") or []
        set_text(self.guard["bypass"], f"устройств: {len(bypass)}" if bypass else "нет")

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
        self.theme_button = self.nav.add_bottom("Тема")
        self.theme_button.setAccessibleName("Тема окна")
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.theme_button)
        self.theme_actions = QActionGroup(self)
        chosen = str(self.settings.value("theme", "system"))
        for key in theme.THEMES:
            action = QAction(theme.THEME_NAMES[key], self, checkable=True)
            action.setData(key)
            action.setChecked(key == chosen or (chosen not in theme.THEMES and key == "system"))
            self.theme_actions.addAction(action)
            menu.addAction(action)
        self.theme_actions.triggered.connect(self._theme_changed)
        self.theme_button.setMenu(menu)
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.login_page = LoginPage(self.start_login)
        self.overview = OverviewPage(self)
        self.pages: dict[str, QWidget] = {"overview": self.overview}
        for key, _title in SECTIONS[1:]:
            self.pages[key] = PendingPage(key, TITLES[key], PENDING[key], self.open_browser)
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

    def _theme_changed(self, action: QAction) -> None:
        choice = str(action.data())
        self.settings.setValue("theme", choice)
        theme.apply(QApplication.instance(), choice)
        self.recolor()

    def recolor(self) -> None:
        """Значки рисуются цветом темы — после её смены их надо нарисовать заново."""
        colors = theme.current()
        self.nav.recolor(colors, {self.theme_button: "theme"})
        for page in self.pages.values():
            if isinstance(page, PendingPage):
                page.recolor(colors)
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.client.set_visible(True)
        if self.focusWidget() is None:
            self.stack.setFocus()  # без рамки фокуса на первой кнопке при запуске

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overview.conn.setFixedWidth(CONN_WIDTH[self.width() >= WIDE])

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.client.set_visible(False)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.client.set_visible(not self.isMinimized())
