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
JOB_STATES = {"idle": "Проверка не запускалась", "queued": "Ожидает запуска",
              "running": "Проверка идёт", "restoring": "Возвращаются настройки",
              "complete": "Проверка завершена", "cancelled": "Проверка отменена",
              "interrupted": "Прервана перезапуском", "conflict": "Настройки изменены извне",
              "failed": "Ошибка проверки", "restore_failed": "Возврат не подтверждён",
              "unavailable": "Состояние недоступно"}

REQUIREMENTS = ("В режиме «без VPN» адреса проверок не нужны. HTTPS-проверка YouTube "
                "принимает страницу /t/terms и CDN /videoplayback или экспериментальный "
                "/generate_204. Она подтверждает доступность соединения. Для обычной "
                "проверки файла нужны HTTP 2xx и 16 КиБ тела. Перенаправления не выполняются.")


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
    if stale or view.get("fresh") is False:
        return "warn", "zapret2 · данные устарели"
    kind = {"active": "ok", "blocked": "bad", "fallback": "warn", "error": "bad",
            "absent": "warn",
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
        selected = (view.get("selected_strategy") or view.get("configured_strategy")
                    or "multisplit")
        if self.strategy.findText(selected) < 0:
            self.strategy.addItem(selected)  # Never silently replace a dormant preference.
        self.strategy.setCurrentText(selected)
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
        if view.get("youtube_transport_probe"):
            box.addWidget(plain("Включена HTTPS-проверка YouTube и CDN. Она проверяет "
                                "доступность транспорта, а не воспроизведение ролика."))
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
        _, self.jobs_note, self.jobs_rows = self.card("Проверка стратегий")
        self.body.addStretch(1)

    def view(self) -> dict:
        return (self.main.state or {}).get("zapret2") or {}

    def mode_control(self, text: str, mode: str, question: str) -> Control:
        view = self.view()
        allowed = (view.get("can_off", False) if mode == "off" else
                   mode in view.get("blockers", {}) and not view["blockers"][mode])
        allowed = allowed and (view.get("job") or {}).get("state") not in (
            "queued", "running", "restoring")
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
        job = view.get("job") or {"state": "idle"}
        running = job["state"] in ("queued", "running", "restoring")
        kind, title = summary(state, self.main.stale)
        set_text(self.status_note, title)
        tone(self.status_note, kind)
        if not view:
            self.status.update_text([("Требуется обновление панели шлюза",
                                      "Установите код поддержки zapret2 в интерфейсе.")])
            self.settings_rows.update_rows([])
            self.jobs_rows.update_rows([])
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
                              "Выключить обработку выбранных доменов и вернуть обычный режим? "
                              "Если общий движок zapret2 настроен на auto, он возобновит работу. "
                              "Для VPN нужны настроенные серверы. "
                              "Смена режима прервёт соединения."),
        )
        detail = ("Последнее известное состояние. " if self.main.stale else "") + view["detail"]
        last_transport_ok = (view.get("evidence") or {}).get("last_transport_ok_at")
        if last_transport_ok and not self.main.stale:
            stamp = datetime.fromtimestamp(last_transport_ok, UTC).strftime("%d.%m %H:%M:%S UTC")
            detail += "\nПоследний успех HTTPS: " + stamp
        mode_label = MODES.get(view["mode"], "—")
        if view.get("source") == "engine":
            mode_label = ("Движок zapret2" if view.get("engine_mode") == "auto"
                          else "Обработка выключена")
        self.status.update_rows([("mode", "Выбран режим — " + mode_label,
                                  detail, controls)])
        blockers = view.get("blockers", {})
        notes = list(dict.fromkeys(p for values in blockers.values() for p in values))
        set_text(self.settings_note, "\n".join(notes) or "Готов к запуску проверки.")
        strategy = view.get("strategy") or view.get("configured_strategy") or "не подтверждена"
        strategy_label = "Стратегия" if view.get("strategy") else "Настроенная стратегия"
        settings = (f"{strategy_label} {strategy} · адресов проверок {view['probe_count']}\n"
                    f"Проверка каждые {view['check_seconds']} с · повтор после отказа "
                    f"через {view['retry_seconds']} с · бюджет {view['daily_probe_mb']} МиБ/сутки\n"
                    + "\n".join(view["domains"]))
        budget = view.get("probe_budget")
        if budget and not self.main.stale:
            remaining = budget["remaining_bytes"] / (1024 * 1024)
            settings += f"\nОстаток бюджета проб: {remaining:.2f} МиБ · сброс в 00:00 UTC"
        settings += "\n" + REQUIREMENTS + "\n" + expiry_text(view)
        self.settings_rows.update_rows([("settings", "Домены и проверки", settings, (
            Control("Настроить", self.edit,
                    view.get("can_edit", False) and self.can_act("zapret2") and not running),
            self.control("CDN-проба без подписи", "zapret2/probe",
                         {"probe": "persistent", "expected": view.get("config_key")},
                         key="zapret2", enabled=view["mode"] == "off" and not running,
                         question="Сохранить служебный HTTPS-адрес того же CDN без подписи? "
                         "Работу видео нужно проверить отдельно."),
            self.control("Подготовить Flowseal ALT9", "zapret2/import",
                         {"import": "flowseal_alt9", "expected": view.get("config_key")},
                         key="zapret2", enabled=view["mode"] == "off" and not running,
                         question="Проверить локальные ассеты и сохранить профиль ALT9?"),
        ))])
        job = view.get("job") or {"state": "idle"}
        running = job["state"] in ("queued", "running", "restoring")
        controls = [
            self.control("Проверить девять стратегий", "zapret2/job/start", {
                "expected": view.get("config_key"),
                "candidates": ["multisplit", "multidisorder", "fake_md5_split", "fake_seq",
                               "fake_seq_split", "fake_md5", "hostfakesplit_md5",
                               "fake_static_md5", "fake_clone_md5"],
                "rounds": 2, "budget_seconds": 3600,
            }, key="zapret2", enabled=not running and view["mode"] == "off",
                question="Запустить два круга HTTPS-проверок до 60 минут? "
                         "Задание временно меняет профиль и включает Selective, "
                         "затем возвращает исходные настройки."),
            self.control("Отменить и вернуть настройки", "zapret2/job/cancel",
                         {"id": job.get("id")}, key="zapret2", enabled=running),
        ]
        if job.get("restore") == "pass":
            controls.append(self.control(
                "Вернуть исходный профиль", "zapret2/job/reset",
                {"id": job["id"], "expected": view.get("config_key")}, key="zapret2",
                enabled=not running and view["mode"] == "off"))
            for profile in job.get("candidates", []):
                hits = [r for r in job.get("results", []) if r["candidate"] == profile]
                if len(hits) == 2 and all(r["transport"] == "https_reachable" for r in hits):
                    controls.append(self.control(
                        "Сохранить " + profile, "zapret2/job/pin",
                        {"id": job["id"], "expected": view.get("config_key"),
                         "candidate": profile}, key="zapret2",
                        enabled=not running and view["mode"] == "off"))
        text = "\n".join(f"{r['candidate']} · {r['transport']} · {r['reason']}"
                         for r in job.get("results", []))
        self.jobs_rows.update_rows([("job", JOB_STATES.get(job["state"], "Нет данных"),
                                    text, controls)])
        set_text(self.jobs_note, "HTTPS-пробы проверяют транспорт. Качество видео измеряет плеер.")
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
