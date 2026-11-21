# ThinkCentre · запуск изолированного статуса через systemd (P2.5) — 2026-11-21

- RESULT: **ЖИВАЯ ПРОБА ПОЛНОСТЬЮ УСПЕШНА; КОНТРАКТНЫЙ ГЕЙТ НЕ ПРОЙДЕН
  (CONTRACT_TESTS_RC 1 — 7 отказов), поэтому полное принятие отложено
  до правки Codex.** Очистка и шлюз: TOOLS_REMOVED,
  **GATEWAY_UNCHANGED** — обе службы active, PID и три контрольных
  файла совпали, off/off fresh/matched, HTTPS 200.
- Живая проба подтвердила весь механизм socket-activation: systemd
  открыл relay-сокет root 0600 при reader в покое; временная панель
  через реальный `Panel.start()` заменила брошенный IPC-сокет без
  CAP_CHOWN; первый авторизованный запрос запустил reader за
  **664 мс** и вернул пять полей, совпавших со штатной панелью;
  перечитывание настроек сохранило сокет; отказ IPC — 503,
  восстановление — 200; остановка reader и следующий запрос — 200 с
  новым PID. Изоляция reader: caps 5×0, NoNewPrivs=1, отдельный
  mount namespace.
- Гейт: **196 passed / 7 failed / 0 skipped** (все 7 —
  tests/test_install.py; контрактный набор впервые включает
  установку). Классификация выполнена прогоном тех же тестов на
  родителе кандидата: **5 предсуществующих** (падают идентично),
  **2 внесены кандидатом** — оба требуют правки Codex (см. §3).
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43-generic; systemd 255
  (255.4-1ubuntu8.19); кандидат `ca7bc7a…` (SHA инструмента);
  SERVICE_FILES_VERIFIED — systemd-analyze verify прошёл для трёх
  unit-файлов (xgw.service, xgw-panel-read.service,
  xgw-panel-read.socket). Установки пакета, правок настроек,
  учётных записей и перезапусков XGW/Xray не было; сценарий
  остановил только временные unit.

## §1 База и контракты

- PINNED `ca7bc7a9a5953c78b915b66702b4dbd0d111ca13`; baseline:
  обе службы active, off/off fresh/matched, HTTPS 200, контрольные
  SHA трёх файлов зафиксированы.
- **CONTRACT_TESTS_RC 1** — 196 passed / 7 failed / 0 skipped за
  193с. Первая ошибка по порядку вывода:
  `test_reinstall_keeps_capture_enabled_even_if_xray_is_down`
  (предсуществующая).
- SERVICE_FILES_VERIFIED — статический анализ трёх unit-файлов
  кандидата без замечаний.

## §2 Живая проба socket-activation (все этапы OK)

| Проверка | Итог |
| --- | --- |
| service_dormant | OK — сокет systemd active root 0600, reader не запущен |
| stale_ipc_recovered | OK — брошенный сокет IPC заменён, root 0660 + GID читателя, у процесса проверки нет CAP_CHOWN/CAP_DAC_OVERRIDE/CAP_DAC_READ_SEARCH |
| panel_legacy_routes | OK — аноним 401 оставил reader незапущенным; одноразовый вход выдал cookie; HTML 200; полный обзор 200 |
| cold_activation_ms | **664 мс** — первый авторизованный запрос запустил reader и получил пять полей штатной панели |
| http_privileges / http_mount_namespace | OK (caps 5×0, NoNewPrivs=1, ns/mnt отдельный) |
| **ISOLATED_HTTP_STATUS_MATCH** | пять полей совпали с baseline |
| backend_recovered | OK — перечитывание настроек сохранило сокет (inode прежний); имитация отказа 503 → восстановление 200 |
| worker_reactivated | OK — остановка reader, следующий запрос 200 с **новым** PID reader |
| candidate_cleanup | OK — временный доверенный вход остановлен, временные сокеты удалены |

Примечание: при остановке socket-activated службы выводится
предупреждение systemd о том, что активен триггерящий сокет, —
последующая остановка сокета и проверка очистки прошли штатно.

## §3 Контрактный гейт: классификация 7 отказов

Прогон тех же 7 тестов на родителе `d3fd94e` дал 5 идентичных
отказов → предсуществующие (не блокируют кандидата):

1. test_reinstall_keeps_capture_enabled_even_if_xray_is_down
2. test_daemon_that_does_not_start_leaves_the_network_working[reinstall]
3. test_changed_singbox_unit_restarts_after_validation_instead_of_reload[True]
4. test_changed_singbox_unit_restarts_after_validation_instead_of_reload[False]
5. test_failed_migration_restores_unit_config_and_dac_before_restarting_old_worker

**Новые отказы, внесённые кандидатом (требуют правки):**

- **test_no_unit_opens_run_for_writing[xgw-panel-read.service]** —
  новый unit использует ProtectSystem=strict вместе с
  ProtectKernelTunables/ProtectProc, но без явной строки
  `ReadOnlyPaths=/run` (конвенция проекта: на systemd 255 такая
  комбинация оставляет /run доступным на запись). Reader получает
  relay-сокет как fd от systemd и подключается к IPC-сокету, поэтому
  закрытие /run на работу чтения не влияет.
- **test_xray_api_socket_is_open_only_to_the_xray_group** — тест
  требует `SupplementaryGroups == "xray"` для xgw.service (строгое
  равенство), кандидат установил `SupplementaryGroups=xray
  xgw-panel-read`. Нужна синхронизация теста с новой политикой
  (или пересмотр добавления группы).

## §4 Очистка

- TOOLS_REMOVED — оба временных unit (reader.socket, reader.service)
  остановлены, root-каталог инструментов удалён; временные сокеты и
  доверенный вход не пережили испытание.
- **GATEWAY_UNCHANGED** — обе службы active, PID и три контрольных
  файла до/после совпали, off/off fresh/matched, HTTPS 200.

## Наблюдения для Codex

1. **Механика P2.5 работает на живом шлюзе полностью**: socket
   activation с dormant-сокетом root 0600, активация первым
   авторизованным запросом (664 мс), «заражение» GID читателя на
   IPC-сокет без CAP_CHOWN у чекера, реактивация с новым PID после
   остановки, 503→200 при отказе бэкенда — все этапы пробы пройдены
   с первого раза.
2. До принятия осталось закрыть 2 новых отказа гейта: добавить
   `ReadOnlyPaths=/run` в xgw-panel-read.service и согласовать тест
   xray API-сокета с новой SupplementaryGroups (либо аргументировать
   отказ от группы xgw-panel-read у демона).
3. 5 предсуществующих отказов test_install.py подтверждены на
   родителе — рекомендую выделить их в отдельную линию исправления,
   чтобы контрактный набор с установкой можно было включать в гейт
   без шума.
4. Служебное предупреждение systemd «triggering units are still
   active» при остановке socket-activated службы — штатное;
   останавливать пару сокет+служба в этом порядке.
- Publication commit: `0c2225c5641996de29850bc9d64866c1859c9bb4` (2026-11-21T164610Z_panel-read-service.md).
