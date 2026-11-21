# ThinkCentre · повторная приёмка запуска статуса через systemd (P2.5 r2) — 2026-11-21

- RESULT: **ПОЛНЫЙ УСПЕХ, шлюз не тронут (GATEWAY_UNCHANGED), первый
  прогон без повторов; контрактный код 0 у полного набора.**
  Все 7 отказов первого прогона закрыты: 5 предсуществующих и 2
  внесённых кандидатом — плюс добавлены прямые проверки переключения
  поколения sing-box и отказа неисправного моста. Живая проба
  socket-activation воспроизведена целиком: активация за **735 мс**,
  пять полей совпали со штатной панелью, реактивация с новым PID,
  503→200; новый этап **reader_run_readonly** подтвердил фактический
  флаг `ST_RDONLY` на /run в пространстве монтирования запущенного
  читателя при продолжающей работе проверке статуса через IPC.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43-generic; systemd 255
  (255.4-1ubuntu8.19); кандидат `b614174…` (SHA инструмента);
  SERVICE_FILES_VERIFIED — systemd-analyze verify прошёл для трёх
  unit-файлов. Установки пакета, правок настроек, учётных записей и
  перезапусков XGW/Xray не было; сценарий остановил только
  временные unit.

## §1 База и контракты

- PINNED `b614174b0dfc550c95bbabfc7f6c2a2b556a4f8d`; baseline:
  обе службы active, off/off fresh/matched, HTTPS 200, контрольные
  SHA трёх файлов зафиксированы.
- **CONTRACT_TESTS_RC 0** — **205 passed / 0 failed / 0 skipped** за
  193с. Против первого прогона (196 passed / 7 failed): закрыты
  test_reinstall_keeps_capture_enabled_even_if_xray_is_down,
  test_daemon_that_does_not_start_leaves_the_network_working[reinstall],
  test_no_unit_opens_run_for_writing[xgw-panel-read.service],
  test_xray_api_socket_is_open_only_to_the_xray_group,
  test_changed_singbox_unit_restarts_after_validation_instead_of_reload[True/False],
  test_failed_migration_restores_unit_config_and_dac_before_restarting_old_worker;
  набор дополнен прямыми проверками переключения поколения и отказа
  неисправного моста.
- SERVICE_FILES_VERIFIED — статический анализ трёх unit-файлов
  кандидата без замечаний.

## §2 Живая проба socket-activation (все этапы OK)

| Проверка | Итог |
| --- | --- |
| service_dormant | OK — сокет systemd active root 0600, reader не запущен |
| stale_ipc_recovered | OK — брошенный сокет IPC заменён, root 0660 + GID читателя, у процесса проверки нет CAP_CHOWN/CAP_DAC_OVERRIDE/CAP_DAC_READ_SEARCH |
| panel_legacy_routes | OK — аноним 401 оставил reader незапущенным; одноразовый вход выдал cookie; HTML 200; полный обзор 200 |
| **reader_run_readonly** | **OK — у /run в mount namespace фактически запущенного читателя есть флаг ST_RDONLY; проверка статуса через IPC продолжает работать** |
| cold_activation_ms | **735 мс** — первый авторизованный запрос запустил reader и получил пять полей штатной панели |
| http_privileges / http_mount_namespace | OK (caps 5×0, NoNewPrivs=1, ns/mnt отдельный) |
| **ISOLATED_HTTP_STATUS_MATCH** | пять полей совпали с baseline |
| backend_recovered | OK — перечитывание настроек сохранило сокет; имитация отказа 503 → восстановление 200 |
| worker_reactivated | OK — остановка reader, следующий запрос 200 с **новым** PID reader |
| candidate_cleanup | OK — временный доверенный вход остановлен, временные сокеты удалены |

Примечание: предупреждение systemd о триггерящем сокете при остановке
socket-activated службы — штатное; пара сокет+служба останавливается
в этом порядке, проверка очистки прошла.

## §3 Очистка

- TOOLS_REMOVED — оба временных unit (reader.socket, reader.service)
  остановлены, root-каталог инструментов удалён.
- **GATEWAY_UNCHANGED** — обе службы active, PID и три контрольных
  файла до/после совпали, off/off fresh/matched, HTTPS 200.

## Наблюдения для Codex

1. **P2.5 принят целиком с первого прогона r2**: контрактный код 0 у
   полного набора (205 тестов), оба адресованных отказа закрыты —
   `ReadOnlyPaths=/run` в xgw-panel-read.service подтверждён
   фактическим `ST_RDONLY` в mount namespace живого читателя
   (reader_run_readonly), тест группы Xray обновлён под обе
   разрешённые группы демона.
2. Прямые проверки переключения поколения sing-box и отказа
   неисправного моста вошли в контрактный набор — гейт установки
   теперь закрывает контракты переустановки, смены поколения и
   восстановления DAC без шума от предсуществующих отказов.
3. Механика socket-activation стабильна между прогонами: 664 мс (r1)
   → 735 мс (r2) на холодной активации, реактивация и
   отказоустойчивость воспроизводятся.
4. Цепочка P2.1→P2.5 замкнута: системная учётная запись читателя,
   два unit-файла, активация по первому запросу доверенной панели,
   IPC v2 с одноразовыми допусками — профиль готов к включению в
   установку пакета.
- Publication commit: `11ec6abd1ee17cf0cd952f71dcd224b3ae10223f` (2026-11-21T170120Z_panel-read-service-r2.md).
