# ThinkCentre · подтверждение ротации watchdog после применения конфига — 2026-11-27

- RESULT: **ЦЕЛЕВЫЕ ПЯТЬ СЦЕНАРИЕВ ПРОХОДЯТ, НОВЫХ СБОЕВ НЕТ.
  `ROTATION_COMPILE=PASS`; `R16_CONTRACTS=PASS` — 246 PASSED (49,68 С),
  ПРОПУСКОВ НЕТ; `R16_WATCHDOG=PASS` — 12 PASSED (14,76 С);
  `ROTATION_CONTRACTS=PASS` — 18 PASSED (46,13 С); `APPLY_CONTRACTS=PASS`
  — 34 PASSED (8,31 С); СЦЕНАРИИ: `R16_ROUTE_ALTERNATIVE=PASS`,
  `R16_ROUTE_CLOSED=PASS`, `R16_ROUTE_RECOVERY=PASS`,
  `R16_ROUTE_HELD_STREAM=RETAINED`, `F13_ROTATION=PASS`,
  `F13_CERTIFICATE=PASS`, `F13_API_SWITCH_ROLLBACK=PASS`,
  `F13_HELD_STREAM=RETAINED`; `ROTATION_HOST_FIELDS_MATCH`.
  WATCHDOG_MATRIX=FAIL: 7 FAILED, 198 PASSED; НА КОНТРОЛЕ — 12 FAILED,
  191 PASSED. ВСЕ 7 СБОЕВ КАНДИДАТА СОВПАДАЮТ С КОНТРОЛЕМ, НОВЫХ НЕТ;
  5 ПРЕЖНИХ СБОЕВ ИСЧЕЗЛИ (ЦЕЛЬ ИСПРАВЛЕНИЯ). ГОТОВНОСТЬ M3: СТАТУС
  СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; amd64; Xray **26.11.9**
  (676eaf6, go1.27.3); кандидат
  `0bb6134ec3dd0e91f649ce898cfc4c6baba694f6`; ТЗ — `ad223c5e`;
  контроль — `ea3b1b91`; база бандла — `9e4c025e`. Записи и процессы —
  изолированный префикс; сетевые сценарии — loopback. Полные логи и
  данные остаются локально.

## §1 Бандл и контракты

- `xgw-watchdog-rotation-commit.bundle`: SHA-256 **OK** (`dfae270f…`),
  `git bundle verify` **OK**, база `9e4c025e` присутствует, приём =
  кандидат `0bb6134e…`.
- `ROTATION_COMPILE=PASS` — компиляция исходников и helper.
- `R16_CONTRACTS`: **246 passed** (49,68 с), пропусков нет.
- `R16_WATCHDOG`: **12 passed**, 163 deselected (14,76 с).
- `ROTATION_CONTRACTS`: **18 passed**, 157 deselected (46,13 с).
- `APPLY_CONTRACTS` (`rotation`, `applier`): **34 passed** (8,31 с).

## §2 Пять сценариев ротации

- `ALL_DEAD`: прямое обновление, проверка запасных и запрос срочной
  замены — **в одном шаге** (тест проходит).
- Первая неудача `FROZEN` или `CONNECT_FAIL`: запрос замены попадает
  в очередь **на первом шаге** для обоих типов подписок; следующий
  готовый результат применяется и заменяет участника — **проходит**.
- Отказ или откат сборки: оба варианта
  `test_failed_rotation_keeps_first_failure_until_apply_succeeds`
  проходят — старый участник и диагноз сохраняются, успешной записи
  о замене нет; после применения — новый участник в работе, прежний
  диагноз убран, событие о ротации одно.

## §3 Матрица watchdog: кандидат против контроля

| Показатель | Кандидат `0bb6134e` | Контроль `ea3b1b91` |
| --- | --- | --- |
| Итог двух файлов | **7 failed, 198 passed** (501 с) | **12 failed, 191 passed** (480 с) |
| Совпавшие сбои | 7 | те же 7 |
| Новые сбои | **0** | — |
| Исчезли (исправлены) | — | 5 |

- Совпавшие 7 (одинаковые на обеих ревизиях, ошибки в проверках
  правил/tun/tailscale): `test_daemon_reloads_missing_rules`,
  `test_daemon_names_the_tun_without_an_address`,
  `test_daemon_repairs_lan_path`, `test_rules_failure_is_reported_once`,
  `test_fail_closed_keeps_capture_while_xray_is_down`,
  `test_tailscale_goes_direct_while_xray_is_down`,
  `test_leak_reloads_rules_only_when_own_traffic_is_captured`.
  Характер ошибок тот же: пустые списки правил, лишний `up`,
  расхождение `[False, True]`, повтор события.
- Исчезли на кандидате (цель задания):
  `test_all_dead_refreshes_directly_and_rotates_at_once` и четыре
  параметра `test_member_failing_the_first_check_is_replaced_at_once`
  (`FROZEN`/`CONNECT_FAIL` × `True`/`False`).
- Примечание: штатное сравнение ТЗ по `FAILED`-строкам дало пустые
  списки, потому что прогон шёл без `-rf`; для отчёта выполнен
  диагностический повтор с `-rf --tb=line` (FLASH-ADD), результаты
  совпадают по числу и именам.

## §4 Изолированный Xray

- `region-route`: **`R16_ROUTE_ALTERNATIVE=PASS`**,
  **`R16_ROUTE_HELD_STREAM=RETAINED`**, **`R16_ROUTE_CLOSED=PASS`**,
  **`R16_ROUTE_RECOVERY=PASS`**.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  **`F13_ROTATION=PASS`**.
- `certificate`: `OK` → `CERT_TIME_INVALID` (outbound_tls/…time) →
  `OK` — **`F13_CERTIFICATE=PASS`**.
- `api-switch`: переключение и обратное переключение без остановки
  процесса, **`F13_HELD_STREAM=RETAINED`**,
  **`F13_API_SWITCH_ROLLBACK=PASS`**.

## §5 Штатный шлюз и M3

- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились** (xgw и xgw-xray active, xgw-singbox inactive);
  `ROTATION_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0, «весь дом» выкл.

## NOT_RUN

- Рабочий WAN — **NOT_RUN**.
- Принудительное завершение пользовательских соединений — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Пять целевых сценариев закрыты**: ротация после отказа
   участников и при первой неудаче работает, откат сборки сохраняет
   прежнего участника до успешного применения.
2. **Новых сбоев матрица не дала**; 7 оставшихся — средовые проверки
   правил/tun/tailscale, одинаковые на кандидате и контроле.
3. **Сравнение в ТЗ требует `-rf`**: без него `FAILED`-строки не
   печатаются и списки совпадений пустые — стоит поправить скрипт.
4. **M3 по предпосылкам не готов**; рабочий трафик и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R16_WATCHDOG.log`, `ROTATION_CONTRACTS.log`,
  `APPLY_CONTRACTS.log`, `watchdog-matrix.log`, `watchdog-control.log`,
  `matrix-cand-names.log`, `matrix-ctrl-names.log`, `cand.names`,
  `ctrl.names`, `region-route.log`, `rotation.log`, `certificate.log`,
  `api-switch.log`, `xray-version.txt`, `before.txt`/`after.txt`,
  контрольное дерево и бандл — в приватном каталоге прогона 0700 на
  машине.
