"""Нативные разделы «Диагностика» и «Ещё». Все действия выполняет API панели."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QInputDialog, QSizePolicy, QVBoxLayout, QWidget

from . import listing
from .pages import _button, _card, _scroll, confirm
from .widgets import label, set_text


def plain(text: str = "", *, name: str = ""):
    widget = label(text, name=name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


@dataclass(frozen=True)
class Control:
    text: str
    invoke: Callable[[], None]
    enabled: bool = True


class Item(QWidget):
    def __init__(self) -> None:
        super().__init__()
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 4, 0, 4)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = plain(name="cardTitle")
        self.detail = plain(name="muted")
        for widget in (self.title, self.detail):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.title)
        text.addWidget(self.detail)
        box.addLayout(text, 1)
        self.tools = QVBoxLayout()
        box.addLayout(self.tools)
        self.buttons = []
        self.controls: tuple[Control, ...] = ()

    def _invoke(self, index: int) -> None:
        if index < len(self.controls) and self.controls[index].enabled:
            self.controls[index].invoke()

    def update_item(self, title: str, detail: str, controls: tuple[Control, ...]) -> None:
        self.controls = controls
        set_text(self.title, title)
        set_text(self.detail, detail)
        self.detail.setVisible(bool(detail))
        for index, control in enumerate(controls):
            if index == len(self.buttons):
                button = _button(control.text, lambda i=index: self._invoke(i))
                self.buttons.append(button)
                self.tools.addWidget(button)
            button = self.buttons[index]
            if button.text() != control.text:
                button.setText(control.text)
                button.setAccessibleName(control.text)
            button.setEnabled(control.enabled)
            button.show()
        for button in self.buttons[len(controls):]:
            button.hide()


class Rows(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(5)
        self.items: dict[str, Item] = {}

    def update_rows(self, rows: list[tuple[str, str, str, tuple[Control, ...]]]) -> None:
        keep = {key for key, *_ in rows}
        for key in self.items.keys() - keep:
            item = self.items.pop(key)
            self.box.removeWidget(item)
            item.hide()
            item.deleteLater()
        for index, (key, title, detail, controls) in enumerate(rows):
            if key not in self.items:
                self.items[key] = Item()
            item = self.items[key]
            if self.box.indexOf(item) != index:
                self.box.insertWidget(index, item)
                item.show()
            item.update_item(title, detail, controls)

    def update_text(self, rows: list[tuple[str, str]]) -> None:
        self.update_rows([(str(index), title, detail, ())
                          for index, (title, detail) in enumerate(rows)])


class QrCode(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.image = plain()
        self.image.setAccessibleName(title)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.image)
        box.addStretch(1)
        self.rows: tuple[str, ...] = ()
        self.hide()

    def show_code(self, rows: tuple[str, ...]) -> None:
        if rows == self.rows:
            return
        self.rows = rows
        if not rows:
            self.image.clear()
            self.hide()
            return
        side = len(rows) + 8
        scale = max(2, 240 // side)
        pixmap = QPixmap(side * scale, side * scale)
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        for y, row in enumerate(rows, 4):
            for x, pixel in enumerate(row, 4):
                if pixel == "1":
                    painter.fillRect(x * scale, y * scale, scale, scale, Qt.GlobalColor.black)
        painter.end()
        self.image.setPixmap(pixmap)
        self.show()


class Page(QWidget):
    def __init__(self, main, title: str) -> None:
        super().__init__()
        self.main = main
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 0)
        outer.setSpacing(12)
        outer.addWidget(plain(title, name="pageTitle"))
        self.hint = plain(name="muted")
        outer.addWidget(self.hint)
        inner = QWidget()
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(0, 0, 6, 16)
        self.body.setSpacing(12)
        outer.addWidget(_scroll(inner), 1)
        self.confirm = lambda title, text, yes: confirm(self, title, text, yes)

    def card(self, title: str):
        frame, box = _card()
        box.addWidget(plain(title, name="cardTitle"))
        note = plain(name="muted")
        box.addWidget(note)
        rows = Rows()
        box.addWidget(rows)
        self.body.addWidget(frame)
        return box, note, rows

    def can_act(self, key: str) -> bool:
        return (self.isVisible() and not self.main.stale and self.main.client.session is not None
                and not self.main.client.actions.busy(key))

    def control(self, text: str, name: str, body: dict | None = None, *,
                key: str = "", question: str = "", enabled: bool = True,
                still_valid: Callable[[], bool] | None = None) -> Control:
        key = key or name

        def send():
            if not self.can_act(key):
                return
            if question and not self.confirm(text + "?", question, text):
                return
            if self.can_act(key) and (still_valid is None or still_valid()):
                self.main.client.act(name, body or {}, key=key)

        return Control(text, send, enabled and self.can_act(key))

    def link(self, text: str, url: str) -> Control:
        target = QUrl(url)
        return Control(text, lambda: QDesktopServices.openUrl(target),
                       target.isValid() and not self.main.stale)

    def show_hint(self, state: dict | None) -> None:
        text = ("Ожидаю данные панели…" if state is None else
                "Показаны последние данные. Управление временно недоступно." if self.main.stale
                else "")
        set_text(self.hint, text)
        self.hint.setVisible(bool(text))


class DiagnosticsPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main, "Диагностика")
        box, self.check_note, self.checks = self.card("Проверка сети")
        self.run = _button("Проверить сеть", self._run, "netcheckRun")
        box.insertWidget(1, self.run, alignment=Qt.AlignmentFlag.AlignLeft)
        _, self.events_note, self.events = self.card("События")
        self.body.addStretch(1)

    def _run(self) -> None:
        if self.run.isEnabled() and self.can_act("netcheck"):
            self.main.client.act("netcheck", {}, key="netcheck")

    def show_state(self, state: dict | None) -> None:
        self.show_hint(state)
        data = state or {}
        now = data.get("now") or time.time()
        check = data.get("netcheck") or {}
        running = bool(check.get("running"))
        self.run.setEnabled(not running and self.can_act("netcheck"))
        note = "Проверяю сеть…" if running else (
            f"Проверено {listing.stamp(check['at'], now)}" if check.get("at")
            else "Сеть ещё не проверялась")
        set_text(self.check_note, note)
        self.checks.update_text(listing.network_checks(data))
        events = listing.recent_events(data, now)
        set_text(self.events_note, "" if events else "Событий пока нет")
        self.events_note.setVisible(not events)
        self.events.update_text(events)


TAILSCALE_STATE = {
    "absent": "Tailscale не установлен",
    "stopped": "Служба Tailscale остановлена",
    "unknown": "Tailscale не ответил",
    "login": "Требуется вход в Tailscale",
    "running": "Подключено к tailnet",
}


class ExtraPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main, "Ещё")
        box, self.ts_note, self.tailscale = self.card("Tailscale")
        self.auth_qr = QrCode("QR-код входа в Tailscale")
        box.addWidget(self.auth_qr)
        box, self.phone_note, self.phones = self.card("Телефоны")
        self.pair_qr = QrCode("QR-код привязки телефона")
        box.addWidget(self.pair_qr)
        _, self.core_note, self.cores = self.card("Ядра")
        self.body.addStretch(1)

    def show_state(self, state: dict | None) -> None:
        self.show_hint(state)
        data = state or {}
        now = data.get("now") or time.time()
        self._tailscale(data.get("tailscale") or {})
        self._phones(data.get("phones") or {}, now)
        self._cores(data.get("cores") or {}, (data.get("busy") or {}).get("cores"), now)

    def _toggle(self, step: str, on: bool, question: str, *, enabled: bool = True) -> Control:
        return self.control("Выключить" if on else "Включить", f"tailscale/{step}", {"on": not on},
                            question=question, enabled=enabled)

    def _tailscale(self, data: dict) -> None:
        state = data.get("state")
        identity = " · ".join(str(data[key]) for key in ("name", "address") if data.get(key))
        note = TAILSCALE_STATE.get(state, "Состояние Tailscale неизвестно")
        set_text(self.ts_note, f"{note} · {identity}" if identity and state == "running" else note)
        rows = []
        auth = listing.https_link(data.get("auth_url")) if state == "login" else ""
        self.auth_qr.show_code(listing.qr_rows(data.get("auth_qr"))
                               if auth and not self.main.stale else ())
        if state == "login":
            pending = bool(data.get("login_pending"))
            button = self.link("Открыть вход", auth) if auth else self.control(
                "Войти в Tailscale", "tailscale/login", enabled=not pending)
            rows.append(("login", "Вход", "Ожидаю ссылку…" if pending and not auth else "",
                         (button,)))
        if state and state != "absent":
            vpn = data.get("route") == "vpn"
            detail = ("Через VPN. Если Xray недоступен, Tailscale сохранит прямое подключение."
                      if vpn else "Напрямую, мимо VPN")
            button = self.control(
                "Напрямую" if vpn else "Через VPN", "tailscale/route",
                {"route": "direct" if vpn else "vpn"},
                question="Изменится маршрут подключения Tailscale к сети.",
            )
            rows.append(("route", "Маршрут Tailscale", detail, (button,)))
        if state == "running":
            ssh = data.get("ssh")
            rows.append(("ssh", "SSH через Tailscale", (
                "Включён" if ssh is True else "Выключен" if ssh is False else "Нет данных"
            ), (self._toggle("ssh", ssh is True,
                            "Изменится доступ по SSH из tailnet.", enabled=ssh is not None),)))
            for step, title, warning in (
                ("serve", "Панель по tailnet", "Изменится доступ к панели с устройств tailnet."),
                ("funnel", "Публичный адрес (Funnel)",
                 "Включение открывает адрес для приложения телефона в интернете. "
                 "Выключение прерывает доступ привязанных телефонов."),
            ):
                found = data.get(step) or {}
                on, pending = bool(found.get("on")), bool(found.get("pending"))
                detail = ("Нужно разрешение в консоли Tailscale" if pending else
                          "Включено, но адрес недоступен" if on and found.get("live") is False else
                          "Включено" if on else "Выключено")
                controls = [self._toggle(step, on, warning, enabled=not pending)]
                url = listing.https_link(found.get("enable_url")) if pending else ""
                if url:
                    controls.append(self.link("Разрешить в консоли", url))
                url = listing.https_link(found.get("url")) if step == "serve" and on else ""
                if url and not pending and found.get("live") is not False:
                    controls.append(self.link("Открыть панель", url))
                rows.append((step, title, detail, tuple(controls)))
            exit_state = data.get("exit") or {}
            advertised = exit_state.get("advertised")
            detail = ("Нужно одобрить в консоли Tailscale" if advertised
                      and exit_state.get("approved") is False else "Включён" if advertised
                      else "Выключен" if advertised is False else "Нет данных")
            rows.append(("exit", "Выходной узел", detail, (self._toggle(
                "exit", advertised is True, "Изменится выход в интернет через этот шлюз.",
                enabled=advertised is not None,
            ),)))
            for peer in data.get("peers") or []:
                ip = peer.get("ip")
                if not ip:
                    continue
                name, direct = str(peer.get("name") or ip), bool(peer.get("direct"))
                detail = " · ".join(filter(None, (
                    str(ip), str(peer.get("os") or ""), "Напрямую" if direct else "Через VPN",
                    "в сети" if peer.get("online") else "не в сети",
                )))
                button = self.control(
                    "Вернуть в VPN" if direct else "Напрямую", "tailscale/direct",
                    {"ip": ip, "name": name, "direct": not direct}, key=f"tailnet:{ip}",
                    question="" if direct else "Трафик устройства через выходной узел пойдёт "
                                               "мимо VPN.",
                )
                rows.append((f"peer:{ip}", name, detail, (button,)))
        if data.get("cgnat") and data.get("netfilter_off") is not True:
            button = self.control(
                "Выключить фаервол Tailscale", "tailscale/fix", {"name": "netfilter"},
                question="Фильтрацией трафика Tailscale будет управлять XGW.",
            )
            rows.append(("netfilter", "Конфликт адресов провайдера с Tailscale", "", (button,)))
        if data.get("override_dns") is True:
            button = self.control(
                "Не принимать DNS из tailnet", "tailscale/fix", {"name": "dns"},
                question="Имена MagicDNS перестанут разрешаться на этом шлюзе.",
            )
            rows.append(("dns", "DNS шлюза подменяется Tailscale", "", (button,)))
        self.tailscale.update_rows(rows)

    def _phones(self, data: dict, now: float) -> None:
        available = data.get("available") is True
        waiting = bool(data.get("waiting"))
        pairing = data.get("pairing") or {}
        until = pairing.get("until") or 0
        qr = listing.qr_rows(pairing.get("qr")) if until > max(now, time.time()) and (
            not waiting and not self.main.stale) else ()
        self.pair_qr.show_code(qr)
        rows = []
        note = "Привязка телефонов через приложение XGW" if available else "API телефона недоступен"
        if waiting or qr:
            note = ("Разрешите Funnel в консоли Tailscale" if waiting else
                    f"Наведите камеру приложения на QR-код до {listing.stamp(until, now)}")
            controls = [self.control("Отменить привязку", "phones/cancel", key="phone-pair")]
            url = listing.https_link(data.get("enable_url")) if waiting else ""
            if url:
                controls.insert(0, self.link("Разрешить Funnel", url))
            rows.append(("pair", "Привязка телефона", "", tuple(controls)))
        elif available:
            rows.append(("pair", "Привязка телефона", "", (self.control(
                "Привязать телефон", "phones/pair", key="phone-pair",
                question="Для привязки шлюз включит публичный адрес Funnel."
                if not data.get("funnel") else "",
            ),)))
        set_text(self.phone_note, note)
        for phone in data.get("list") or []:
            phone_id = phone.get("id")
            if not phone_id:
                continue
            name = str(phone.get("name") or "Телефон")
            detail = f"Привязан {listing.stamp(phone.get('paired'), now)}"
            if phone.get("seen"):
                detail += f" · на связи {listing.ago(phone['seen'], now)}"
            key = f"phone:{phone_id}"
            rename = Control("Переименовать", lambda i=phone_id, n=name: self._rename(i, n),
                             self.can_act(key))
            revoke = self.control(
                "Отвязать", "phones/revoke", {"id": phone_id}, key=key,
                question="Телефон потеряет доступ к управлению шлюзом и получению новых серверов.",
            )
            rows.append((key, name, detail, (rename, revoke)))
        self.phones.update_rows(rows)

    def _rename(self, phone_id: str, old: str) -> None:
        key = f"phone:{phone_id}"
        if not self.can_act(key):
            return
        text, ok = QInputDialog.getText(self, "Имя телефона", "Новое имя", text=old)
        text = text.strip()
        if ok and text and text != old and self.can_act(key):
            self.main.client.act("phones/rename", {"id": phone_id, "name": text}, key=key)

    def _core_ready(self, core: str, *, version: str, rollback: bool = False) -> bool:
        snapshot = self.main.state or {}
        data = snapshot.get("cores") or {}
        if data.get("active") or (snapshot.get("busy") or {}).get("cores"):
            return False
        for row in data.get("rows") or []:
            if row.get("core") == core:
                current = row.get("previous") if rollback else (row.get("latest") or {}).get(
                    "version")
                return current == version
        return False

    def _cores(self, data: dict, checking: bool, now: float) -> None:
        active, job = bool(data.get("active")), data.get("job") or {}
        entries = [row for row in data.get("rows") or [] if row.get("core") in ("xray", "sing-box")]
        if not entries:
            set_text(self.core_note, "Нет данных о ядрах")
            self.cores.update_rows([])
            return
        note = "Выпуски ещё не проверялись"
        if active:
            note = str(job.get("stage") or "Выполняется задание для ядра")
        elif checking:
            note = "Проверяю выпуски…"
        elif data.get("checked"):
            note = f"Проверено {listing.stamp(data['checked'], now)}"
        notes = [note]
        if data.get("error"):
            notes.append(str(data["error"]))
        if job.get("text") and not active:
            notes.append(str(job["text"]))
        set_text(self.core_note, "\n".join(notes))
        rows = [("check", "Выпуски на GitHub", "", (self.control(
            "Проверить выпуски", "cores/check", key="cores", enabled=not active and not checking,
        ),))]
        for row in entries:
            core = row.get("core")
            name = str(row.get("title") or core)
            installed = row.get("installed")
            detail = f"Установлено {installed}" if installed else "Ядро не установлено"
            if row.get("withdrawn"):
                detail += " · выпуск отозван"
            if row.get("watch_until"):
                detail += f" · наблюдение до {listing.stamp(row['watch_until'], now)}"
            rejected = row.get("rejected") or {}
            if rejected.get("version") and rejected.get("version") != installed:
                detail += f"\n{rejected['version']}: {rejected.get('reason') or 'отклонено'}"
            controls = []
            latest = row.get("latest") or {}
            version, previous = latest.get("version"), row.get("previous")
            if version:
                detail += f"\nДоступно {version}"
                if latest.get("prerelease"):
                    detail += " · предварительный выпуск"
                controls.append(self.control(
                    "Обновить", "cores/update", {"core": core, "version": version},
                    key="cores", enabled=not active and not checking,
                    question=f"Шлюз скачает выпуск {version}, сверит SHA-256 и проверит ядро. "
                             "На время перезапуска соединения могут прерваться.",
                    still_valid=lambda c=core, v=version: self._core_ready(c, version=v),
                ))
            if previous:
                detail += f"\nМожно вернуть {previous}"
                controls.append(self.control(
                    "Вернуть версию", "cores/rollback", {"core": core}, key="cores",
                    enabled=not active and not checking,
                    question=f"Шлюз вернёт версию {previous} и перезапустит ядро. "
                             "Соединения могут прерваться.",
                    still_valid=lambda c=core, v=previous: self._core_ready(
                        c, version=v, rollback=True),
                ))
            rows.append((core, name, detail, tuple(controls)))
        self.cores.update_rows(rows)
