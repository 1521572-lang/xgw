# Телефон: диалоги экрана подписок, повтор — 2026-11-08

- Дата; CODE 53df8de (правка помощника: нажимать только выше панели вкладок); сумма OK (4be4ddb7…). Приложение, сборка 8 на телефоне и шлюз не менялись, ничего не устанавливалось.
- Шлюз до: on/HTTPS OK; state=HEALTHY, subscriptions=3; version_code=8; телефон подключён, devices=1.
- Экран: `OK app_open`; remove_buttons=3, edit_buttons=2, restore_buttons=1; `OK remove_on_every_subscription`, helper_rc=0.
- Диалоги: **3 × (OK dialog_opened → OK cancel_found → OK dialog_closed)**; `INFO dialogs=3 config_note=1` (сумма config_note и edit_buttons равна N: 1+2=3); `OK dialogs_checked`, helper_rc=0 — правка помощника устранила уход на вкладку «События» (п. 346).
- Crash-проверка: `INFO crash_lines=0`, `OK no_crash`, helper_rc=0.
- Конечное: on/HTTPS OK; subscriptions=3 — **то же** (да).
- Итог: **PASS** — все три диалога «Убрать» открываются и закрываются «Отменой», кнопки на месте (у всех «Убрать», убранные с «Вернуть»), крэшей нет, шлюз не менялся. На телефоне сборка 8.
