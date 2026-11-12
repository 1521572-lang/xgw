"""Управление дополнительным путём zapret2 через API панели."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from .operations import Control, Page, plain
from .widgets import set_text, tone

MODES = {"off": "Выключен", "compare": "Сравнение с VPN", "selective": "Домены с возвратом на VPN",
         "standalone": "zapret2 без VPN"}

REQUIREMENTS = ("В режиме «без VPN» адреса проверок не нужны. Для selective и сравнения "
                "каждый адрес должен отдавать HTTP 2xx и не менее 16 КиБ тела. "
                "Ответ 204 и маленький служебный файл не подходят. "
                "Selective не следует перенаправлениям.")


def expiry_text(view: dict) -> str:
    lines = []
    for item in view.get("probe_expiry", []):
        until = item.get("expires_at")
        if until is None:
            detail = "срок по адресу неизвестен"
        else:
            stamp = datetime.fromtimestamp(until, UTC).strftime("%d.%m.%Y %H:%M UTC")
            detail = ("срок expire истёк " if until <= time.time() else "expire до ") + stamp
        lines.append(f"Проверка {item['probe']} · {detail}")
    return "\n".join(lines)


def summary(state: dict | None, stale: bool) -> tuple[str, str]:
    view = (state or {}).get("zapret2") or {}
    if not view:
        return "off", "zapret2 · нужны данные новой панели"
    if stale:
        return "warn", "zapret2 · данные устарели"
    kind = {"active": "ok", "blocked": "bad", "fallback": "warn",
            "pending": "busy", "preparing": "busy", "unknown": "warn"}.get(view["state"], "off")
    return kind, "zapret2 · " + view["title"]


class SettingsDialog(QDialog):
    def __init__(self, parent, view: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки zapret2")
        self.resize(560, 460)
        box = QVBoxLayout(self)
        box.addWidget(plain("Выбранные домены открываются через домашний IP. "
                            "Для YouTube нужны вместе страница и видеосеть."))
        box.addWidget(plain(REQUIREMENTS))
        box.addWidget(plain(expiry_text(view)))
        form = QFormLayout()
        self.domains = QPlainTextEdit("\n".join(view.get("domains", [])))
        self.domains.setMaximumHeight(110)
        self.domains.setAccessibleName("Домены zapret2, по одному на строку")
        form.addRow("Домены", self.domains)
        box.addWidget(plain("Формат доменов — domain:имя или full:имя, по одному на строку."))
        self.strategy = QComboBox()
        self.strategy.addItems(view.get("strategies") or ["multisplit", "multidisorder"])
        self.strategy.setCurrentText(view.get("strategy", "multisplit"))
        form.addRow("Стратегия", self.strategy)
        self.strategy.setToolTip("Какая стратегия проходит, зависит от провайдера. Сравнение "
                                 "с VPN умеет только multisplit и multidisorder.")
        self.urls = []
        for title in ("HTTPS-страница", "HTTPS-файл видео"):
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setAccessibleName(title)
            self.urls.append(field)
            form.addRow(title, field)
        box.addLayout(form)
        box.addWidget(plain(f"Сохранено адресов проверок — {view.get('probe_count', 0)}. "
                            "Пустые поля сохраняют прежние адреса. Для замены заполните оба. "
                            "Адрес файла видео должен быть действующим."))
        self.clear_urls = QCheckBox("Удалить сохранённые адреса проверок")
        self.clear_urls.toggled.connect(
            lambda checked: [f.setEnabled(not checked) for f in self.urls])
        box.addWidget(self.clear_urls)
        self.error = plain(name="muted")
        box.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def values(self) -> dict:
        result = {"domains": [s.strip().lower() for s in self.domains.toPlainText().splitlines()
                              if s.strip()], "strategy": self.strategy.currentText()}
        urls = [field.text().strip() for field in self.urls]
        if self.clear_urls.isChecked():
            result["probe_urls"] = []
        elif any(urls):
            result["probe_urls"] = urls
        return result

    def accept(self) -> None:
        urls = self.values().get("probe_urls")
        if urls and not all(urls):
            set_text(self.error, "Заполните оба адреса или оставьте оба поля пустыми.")
            return
        super().accept()


class Zapret2Page(Page):
    def __init__(self, main) -> None:
        super().__init__(main, "zapret2")
        _, self.status_note, self.status = self.card("Обход блокировок для выбранных доменов")
        _, self.settings_note, self.settings_rows = self.card("Настройки")
        _, self.results_note, self.results = self.card("Последние проверки")
        self.body.addStretch(1)

    def view(self) -> dict:
        return (self.main.state or {}).get("zapret2") or {}

    def mode_control(self, text: str, mode: str, question: str) -> Control:
        view = self.view()
        allowed = (view.get("can_off", False) if mode == "off" else
                   mode in view.get("blockers", {}) and not view["blockers"][mode])
        key = view.get("config_key")
        return self.control(
            text, "zapret2/mode", {"mode": mode, "expected": key}, key="zapret2",
            question=question, enabled=allowed,
            still_valid=lambda: self.view().get("config_key") == key and (
                self.view().get("can_off", False) if mode == "off" else
                mode in self.view().get("blockers", {}) and not self.view()["blockers"][mode]),
        )

    def edit(self) -> None:
        view = self.view()
        if not self.can_act("zapret2") or not view.get("can_edit"):
            return
        dialog = SettingsDialog(self, view)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if (self.can_act("zapret2") and self.view().get("can_edit")
                and self.view().get("config_key") == view.get("config_key")):
            self.main.client.act("zapret2/settings", {
                "expected": view["config_key"], "settings": dialog.values(),
            }, key="zapret2")

    def show_state(self, state: dict | None) -> None:
        self.show_hint(state)
        view = (state or {}).get("zapret2") or {}
        kind, title = summary(state, self.main.stale)
        set_text(self.status_note, title)
        tone(self.status_note, kind)
        if not view:
            self.status.update_text([("Требуется обновление панели шлюза",
                                      "Установите код поддержки zapret2 в интерфейсе.")])
            self.settings_rows.update_rows([])
            self.results.update_rows([])
            return
        controls = (
            self.mode_control("zapret2 без VPN", "standalone",
                              "Переключить шлюз на прямой интернет без VPN? "
                              "Выбранные HTTPS-домены пойдут через zapret2, остальные напрямую. "
                              "VPN-соединения прервутся при смене режима. Правила VPN для "
                              "устройств и пула будут приостановлены. При сбое zapret2 выбранные "
                              "домены блокируются, VPN автоматически не включается."),
            self.mode_control("Сравнить с VPN", "compare",
                              "Выполнить один круг запросов к сохранённым адресам через VPN "
                              "и напрямую через zapret2? Клиентский маршрут сохранится. "
                              "Прямые запросы используют домашний IP."),
            self.mode_control("Включить для доменов", "selective",
                              "Направлять выбранные HTTPS-домены через домашний IP после "
                              "успешной проверки? При отказе шлюз вернёт новые соединения на VPN. "
                              "Воспроизведение видео последними проверками ещё не подтверждено."),
            self.mode_control("Вернуться к VPN" if view.get("without_vpn") else
                              "Выключить zapret2", "off",
                              "Выключить режим zapret2 и вернуть обычный режим VPN? "
                              "Для VPN нужны настроенные серверы. "
                              "Смена режима прервёт соединения."),
        )
        detail = ("Последнее известное состояние. " if self.main.stale else "") + view["detail"]
        self.status.update_rows([("mode", "Выбран режим — " + MODES.get(view["mode"], "—"),
                                  detail, controls)])
        blockers = view.get("blockers", {})
        notes = list(dict.fromkeys(p for values in blockers.values() for p in values))
        set_text(self.settings_note, "\n".join(notes) or "Готов к запуску проверки.")
        settings = (f"Стратегия {view['strategy']} · адресов проверок {view['probe_count']}\n"
                    f"Проверка каждые {view['check_seconds']} с · повтор после отказа "
                    f"через {view['retry_seconds']} с · бюджет {view['daily_probe_mb']} МБ/сутки\n"
                    + "\n".join(view["domains"]))
        settings += "\n" + REQUIREMENTS + "\n" + expiry_text(view)
        self.settings_rows.update_rows([("settings", "Домены и проверки", settings, (
            Control("Настроить", self.edit,
                    view.get("can_edit", False) and self.can_act("zapret2")),
        ))])
        rows = []
        for row in view.get("probes", []):
            verdict = ("не запускалась" if row.get("verdict") == "not_run" else
                       "успех" if row["ok"] else "не прошла")
            title = f"Проверка {row['probe']} · {row['path']} · {verdict}"
            code = (f"HTTP {row['http']}" if row["http"] else
                    f"CONNECT {row['connect_http']}" if row["connect_http"] else "Нет HTTP-ответа")
            detail = row.get("detail", "")
            if row.get("verdict") != "not_run":
                detail += f"\n{code} · байт {row['bytes']} · переходов {row['redirects']}"
            if row.get("checked_at"):
                checked = datetime.fromtimestamp(row["checked_at"], UTC)
                stamp = checked.strftime("%d.%m %H:%M:%S UTC")
                detail += "\nПроверено " + stamp
            rows.append((title, detail))
        self.results.update_text(rows)
        set_text(self.results_note, "HTTP-проверка не подтверждает воспроизведение видео. "
                 "Срок expire взят из адреса и не подтверждает его действительность." if rows
                 else "Результатов проверок пока нет.")
