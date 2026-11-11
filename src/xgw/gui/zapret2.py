"""Управление дополнительным путём zapret2 через API панели."""

from __future__ import annotations

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

MODES = {"off": "Выключен", "compare": "Сравнение с VPN", "selective": "Выбранные домены"}


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
        form = QFormLayout()
        self.domains = QPlainTextEdit("\n".join(view.get("domains", [])))
        self.domains.setMaximumHeight(110)
        self.domains.setAccessibleName("Домены zapret2, по одному на строку")
        form.addRow("Домены", self.domains)
        box.addWidget(plain("Формат доменов — domain:имя или full:имя, по одному на строку."))
        self.strategy = QComboBox()
        self.strategy.addItems(["multisplit", "multidisorder"])
        self.strategy.setCurrentText(view.get("strategy", "multisplit"))
        form.addRow("Стратегия", self.strategy)
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
        _, self.results_note, self.results = self.card("Последнее сравнение")
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
            self.mode_control("Сравнить с VPN", "compare",
                              "Выполнить один круг запросов к сохранённым адресам через VPN "
                              "и напрямую через zapret2? Клиентский маршрут сохранится. "
                              "Прямые запросы используют домашний IP."),
            self.mode_control("Включить для доменов", "selective",
                              "Направлять выбранные HTTPS-домены через домашний IP после "
                              "успешной проверки? При отказе шлюз вернёт новые соединения на VPN. "
                              "Воспроизведение видео последними проверками ещё не подтверждено."),
            self.mode_control("Выключить zapret2", "off",
                              "Выключить прямой маршрут zapret2 и вернуть новые соединения "
                              "на обычный маршрут шлюза?"),
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
        self.settings_rows.update_rows([("settings", "Домены и проверки", settings, (
            Control("Настроить", self.edit,
                    view.get("can_edit", False) and self.can_act("zapret2")),
        ))])
        rows = []
        for row in view.get("probes", []):
            verdict = "успех" if row["ok"] else "не прошла"
            title = f"Проверка {row['probe']} · {row['path']} · {verdict}"
            code = (f"HTTP {row['http']}" if row["http"] else
                    f"CONNECT {row['connect_http']}" if row["connect_http"] else "Нет HTTP-ответа")
            rows.append((title, f"{code} · байт {row['bytes']} · переходов {row['redirects']}"))
        self.results.update_text(rows)
        set_text(self.results_note, "HTTP-проверка не подтверждает воспроизведение видео." if rows
                 else "Результатов сравнения пока нет. После завершения выключите режим "
                      "для нового сравнения или включения маршрута.")
