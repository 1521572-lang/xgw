"""Главное окно XGW: верхняя строка (состояние, сервер, VPN, обновление), навигация слева и
страницы. Страницы обновляют только тексты своих виджетов — ничего не создаётся заново на
каждом опросе, поэтому фокус, выделение и прокрутка не сбиваются.

Этап 1–2 (docs/GUI-NATIVE.md): вход, «Обзор» и переключатель VPN. Разделы, которые ещё не
перенесены в окно, честно говорят об этом и открывают тот же раздел браузерной панели.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import client as clienting
from . import model, theme

SECTIONS = (
    ("overview", "Обзор"),
    ("servers", "Серверы"),
    ("subscriptions", "Подписки"),
    ("devices", "Устройства"),
    ("traffic", "Трафик"),
    ("diagnostics", "Диагностика"),
    ("extra", "Дополнительно"),
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
MIN_SIZE = (1024, 720)
START_SIZE = (1440, 900)


def _label(text: str = "", *, role: str = "", wrap: bool = True, name: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if role:
        label.setProperty("role", role)
    if name:
        label.setObjectName(name)
    return label


def _tone(widget: QWidget, tone: str) -> None:
    """Тон виджета для таблицы стилей; стиль пересчитывается, только если тон сменился."""
    if widget.property("tone") != tone:
        widget.setProperty("tone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _marked(tone: str, text: str) -> str:
    return f"{model.MARKS.get(tone, '')} {text}".strip()


class Card(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 14, 18, 16)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(_label(title, name="cardTitle", wrap=False))


class Facts(QWidget):
    """Подписи и значения в два столбца; значения меняются, строки не пересоздаются."""

    def __init__(self, names: list[tuple[str, str]]) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.values: dict[str, QLabel] = {}
        for row, (key, title) in enumerate(names):
            grid.addWidget(_label(title, role="muted", wrap=False), row, 0,
                           Qt.AlignmentFlag.AlignTop)
            value = _label("—")
            value.setAccessibleName(title)
            grid.addWidget(value, row, 1)
            self.values[key] = value

    def set(self, key: str, text: str) -> None:
        label = self.values[key]
        if label.text() != text:
            label.setText(text)


class LoginPage(QWidget):
    def __init__(self, on_login) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        card = Card("")
        card.setMaximumWidth(560)
        card.body.addWidget(_label("Вход в XGW", name="heroTitle"))
        card.body.addWidget(_label(
            "Окно управляет шлюзом через его панель на этой машине. Чтобы войти, Ubuntu спросит "
            "пароль администратора — один раз: вход запоминается, как в браузере."))
        self.error = _label("")
        _tone(self.error, "bad")
        self.error.hide()
        card.body.addWidget(self.error)
        self.button = QPushButton("Войти")
        self.button.setObjectName("primary")
        self.button.setAccessibleName("Войти в XGW с паролем администратора")
        self.button.clicked.connect(on_login)
        row = QHBoxLayout()
        row.addWidget(self.button)
        row.addStretch(1)
        card.body.addLayout(row)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(card)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(2)

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)
        self.button.setText("Ждём пароль администратора…" if busy else "Войти")

    def set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))


class PendingPage(QWidget):
    """Раздел ещё в браузерной панели: что в нём и кнопка открыть его там."""

    def __init__(self, title: str, about: str, open_panel) -> None:
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        card = Card(title)
        card.body.addWidget(_label(about))
        card.body.addWidget(_label(
            "В окно этот раздел ещё переносится. Пока он работает в браузерной панели XGW — "
            "с теми же действиями.", role="muted"))
        button = QPushButton("Открыть в браузерной панели")
        button.setAccessibleName(f"Открыть раздел «{title}» в браузерной панели")
        button.clicked.connect(open_panel)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        card.body.addLayout(row)
        layout.addWidget(card)
        layout.addStretch(1)


class OverviewPage(QWidget):
    """«Обзор»: VPN, состояние и что делать, сервер в работе, перехват, версии."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__()
        self.main = main
        window = main
        self.setObjectName("page")
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        hero = Card("VPN")
        top = QHBoxLayout()
        texts = QVBoxLayout()
        self.power_title = _label("", name="heroTitle")
        self.power_sub = _label("", role="muted")
        texts.addWidget(self.power_title)
        texts.addWidget(self.power_sub)
        top.addLayout(texts, 1)
        self.power = QPushButton("Включить VPN")
        self.power.setObjectName("power")
        self.power.setMinimumWidth(190)
        self.power.clicked.connect(window.toggle_power)
        top.addWidget(self.power, 0, Qt.AlignmentFlag.AlignTop)
        hero.body.addLayout(top)
        self.power_why = _label("")
        _tone(self.power_why, "warn")
        hero.body.addWidget(self.power_why)
        self.lifecycle = _label("")
        hero.body.addWidget(self.lifecycle)
        layout.addWidget(hero)

        state = Card("Состояние шлюза")
        self.state = _label("")
        self.state.setAccessibleName("Состояние шлюза")
        self.explain = _label("", role="muted")
        state.body.addWidget(self.state)
        state.body.addWidget(self.explain)
        fixes = QHBoxLayout()
        self.fix_buttons: dict[str, QPushButton] = {}
        for name, title in (("refresh", "Обновить подписки"), ("scan", "Проверить запасные"),
                            ("netcheck", "Проверить сеть")):
            button = QPushButton(title)
            button.setAccessibleName(title)
            button.clicked.connect(lambda _c=False, act=name: window.run_action(act))
            button.hide()
            fixes.addWidget(button)
            self.fix_buttons[name] = button
        fixes.addStretch(1)
        state.body.addLayout(fixes)
        layout.addWidget(state)

        row = QHBoxLayout()
        row.setSpacing(16)
        server = Card("Сервер в работе")
        self.server = Facts([
            ("name", "Сервер"), ("how", "Выбран"), ("country", "Страна"), ("core", "Ядро"),
            ("profile", "Профиль обхода"), ("speed", "Скорость"), ("rtt", "RTT"),
            ("delay", "Полная проба"),
        ])
        server.body.addWidget(self.server)
        server.body.addStretch(1)
        row.addWidget(server, 3)
        capture = Card("Перехват")
        self.capture = Facts([
            ("scope", "Через VPN"), ("mode", "Режим"), ("fail", "При сбое"),
            ("bypass", "Мимо VPN"),
        ])
        capture.body.addWidget(self.capture)
        capture.body.addStretch(1)
        row.addWidget(capture, 2)
        layout.addLayout(row)

        about = Card("Версии и данные")
        self.about = Facts([
            ("xgw", "XGW"), ("xray", "Xray"), ("singbox", "sing-box"), ("updated", "Состояние"),
        ])
        about.body.addWidget(self.about)
        layout.addWidget(about)
        layout.addStretch(1)

    def show_state(self, state: dict | None, stale: bool) -> None:
        acting = self.main.client.actions.busy("power")
        power = model.power(state, stale, acting=acting)
        self.power_title.setText(power.title)
        self.power_sub.setText(power.sub)
        self.power.setText("Выключаю…" if acting and power.pressed else
                           "Включаю…" if acting else
                           ("Выключить VPN" if power.pressed else "Включить VPN"))
        self.power.setAccessibleName(self.power.text())
        self.power.setEnabled(power.enabled)
        _tone(self.power, power.tone if power.pressed else "off")
        self.power.setProperty("pressed_state", power.pressed)
        self.power_why.setText(power.why)
        self.power_why.setVisible(bool(power.why))
        line = model.lifecycle(state, stale)
        self.lifecycle.setVisible(line is not None)
        if line is not None:
            _tone(self.lifecycle, line[0])
            self.lifecycle.setText(_marked(line[0], line[1]))

        tone, text = model.health(state, stale)
        _tone(self.state, tone)
        self.state.setText(_marked(tone, text))
        detail, fixes = self._explain(state, stale)
        self.explain.setText(detail)
        self.explain.setVisible(bool(detail))
        for name, button in self.fix_buttons.items():
            button.setVisible(name in fixes)
            button.setEnabled(not self.main.client.actions.busy(name)
                              and not _busy(state, name))

        main = model.main_server(state)
        if main is None:
            for key in self.server.values:
                self.server.set(key, "—")
            self.server.set("name", "нет: шлюз ещё не выбрал сервер" if state else "—")
        else:
            self.server.set("name", main.name)
            self.server.set("how", "вручную" if main.pinned else
                            "по замеру скорости" if main.basis == "speed" else "по задержке")
            self.server.set("country", main.country or "—")
            self.server.set("core", main.core or "—")
            self.server.set("profile", main.profile or "—")
            self.server.set("speed", model.mbps_text(main.speed_mbps))
            self.server.set("rtt", model.ms_text(main.rtt_ms))
            self.server.set("delay", model.ms_text(main.delay_ms))

        capture = (state or {}).get("capture") or {}
        modes = {"on": "включён", "open": "временно снят (Xray недоступен)", "off": "выключен",
                 "none": "не настроен"}
        self.capture.set("scope", model.scope_text(capture) if capture.get("mode") == "on"
                         else "ничего: VPN выключен" if capture else "—")
        self.capture.set("mode", modes.get(str(capture.get("mode") or ""), "—"))
        self.capture.set("fail", model.FAIL_MODES.get(str(capture.get("fail_mode") or ""), "—"))
        bypass = capture.get("bypass") or []
        self.capture.set("bypass", f"устройств: {len(bypass)}" if bypass else "нет")

        found = dict(model.versions(state))
        self.about.set("xgw", found.get("XGW") or "—")
        self.about.set("xray", found.get("Xray") or "—")
        self.about.set("singbox", found.get("sing-box") or "—")
        self.about.set("updated", self.main.freshness_text())

    @staticmethod
    def _explain(state: dict | None, stale: bool) -> tuple[str, set[str]]:
        """Что случилось и какие кнопки могут помочь (только существующие действия панели)."""
        if state is None:
            return "Окно не получает ответа от панели XGW на этой машине.", set()
        if stale:
            return ("Демон XGW давно не обновлял состояние: показанное могло устареть. "
                    "Проверьте службу: sudo systemctl status xgw"), set()
        name = str(state.get("state") or "")
        action = str(state.get("action") or "")
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
        self.setWindowTitle("XGW")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(*START_SIZE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._topbar())
        body = QHBoxLayout()
        body.setSpacing(0)
        root.addLayout(body, 1)
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setAccessibleName("Разделы")
        self.nav.setFixedWidth(210)
        for _key, title in SECTIONS:
            self.nav.addItem(title)
        side.addWidget(self.nav, 1)
        self.theme = QComboBox()
        self.theme.setAccessibleName("Тема окна")
        for key in theme.THEMES:
            self.theme.addItem(theme.THEME_NAMES[key], key)
        chosen = str(self.settings.value("theme", "system"))
        self.theme.setCurrentIndex(max(0, list(theme.THEMES).index(chosen)
                                       if chosen in theme.THEMES else 0))
        self.theme.currentIndexChanged.connect(self._theme_changed)
        holder = QWidget()
        holder.setObjectName("navfoot")
        holder.setFixedWidth(210)
        hold = QVBoxLayout(holder)
        hold.setContentsMargins(10, 6, 10, 10)
        hold.addWidget(_label("Тема", role="muted", wrap=False))
        hold.addWidget(self.theme)
        side.addWidget(holder)
        body.addLayout(side)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.login_page = LoginPage(self.start_login)
        self.overview = OverviewPage(self)
        self.pages: dict[str, QWidget] = {"overview": self.overview}
        for key, title in SECTIONS[1:]:
            self.pages[key] = PendingPage(title, PENDING[key], self.open_browser)
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

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start(1000)
        client.stateReceived.connect(self.on_state)
        client.linkChanged.connect(self.on_link)
        client.actionFinished.connect(self.on_action)
        client.busyChanged.connect(lambda _key, _busy: self.render())
        login.finished.connect(self.on_login)
        self.render()

    # --- верхняя строка ---------------------------------------------------------------------

    def _topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(14)
        title = _label("XGW", wrap=False)
        title.setStyleSheet("font-weight: 700; font-size: 13pt;")
        row.addWidget(title)
        self.chip = _label("", name="chip", wrap=False)
        self.chip.setAccessibleName("Состояние шлюза")
        row.addWidget(self.chip)
        self.via = _label("", role="muted", wrap=False)
        self.via.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.via.setAccessibleName("Сервер в работе")
        row.addWidget(self.via, 1)
        self.fresh = _label("", role="muted", wrap=False)
        self.fresh.setAccessibleName("Обновление данных")
        row.addWidget(self.fresh)
        self.top_power = QPushButton("Включить VPN")
        self.top_power.setAccessibleName("Включить или выключить VPN")
        self.top_power.clicked.connect(self.toggle_power)
        row.addWidget(self.top_power)
        return bar

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
        from . import model as m

        try:
            m.save_session(self.session_path, session)
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
            return "ещё не получено"
        age = time.monotonic() - self.received
        if self.link == clienting.LINK_OFFLINE:
            return f"панель не отвечает; последние данные — {model.ago_text(age)}"
        if self.stale:
            return f"данные устарели: демон не отвечает (получено {model.ago_text(age)})"
        return f"обновлено {model.ago_text(age)}"

    def render(self) -> None:
        state = None if self.link == clienting.LINK_OFFLINE and self.state is None else self.state
        stale = self.stale
        if self.link == clienting.LINK_OFFLINE:
            tone, text = "bad", "Панель XGW не отвечает"
        else:
            tone, text = (model.health(state, stale) if state is not None
                          else ("off", "Подключение…"))
        _tone(self.chip, tone)
        self.chip.setText(_marked(tone, text))
        main = model.main_server(state)
        self.via.setText(f"через {main.name}" + (" (выбран вручную)" if main.pinned else "")
                         if main is not None and not stale else "")
        power = model.power(state, stale, acting=self.client.actions.busy("power"))
        self.top_power.setText("Выключить VPN" if power.pressed else "Включить VPN")
        self.top_power.setEnabled(power.enabled)
        self.overview.show_state(state, stale)
        self._tick()

    def _tick(self) -> None:
        busy = self.client.gate.busy
        text = "обновляю…" if busy else self.freshness_text()
        if self.fresh.text() != text:
            self.fresh.setText(text)
        self.overview.about.set("updated", self.freshness_text())

    def _section(self, row: int) -> None:
        if self.link == clienting.LINK_AUTH or self.client.session is None:
            self.stack.setCurrentWidget(self.login_page)
            return
        key = SECTIONS[max(0, row)][0]
        self.stack.setCurrentWidget(self.pages[key])

    def _theme_changed(self) -> None:
        choice = str(self.theme.currentData())
        self.settings.setValue("theme", choice)
        theme.apply(QApplication.instance(), choice)

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

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.client.set_visible(False)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.client.set_visible(not self.isMinimized())
