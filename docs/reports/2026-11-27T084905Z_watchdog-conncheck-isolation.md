# ThinkCentre · изоляция проверок watchdog от NetworkManager — 2026-11-27

- RESULT: **WATCHDOG CONNCHECK ISOLATION — PASS. `CONNCHECK_COMPILE=PASS`;
  `WATCHDOG_CAPTURE_ISOLATED=PASS` — 7 PASSED (20,09 С) С ИСХОДНЫМИ
  ОЖИДАНИЯМИ; `CONNCHECK_CONTRACTS=PASS` — 8 PASSED (6,26 С);
  НА КОНТРОЛЬНОМ КОДЕ `CONNCHECK_CONTROL_REPRODUCED_SEVEN` — 7 ПАДЕНИЙ,
  ИМЕНА СОВПАЛИ С ИЗВЕСТНЫМ СПИСКОМ ПОБАЙТНО; `WATCHDOG_MATRIX=PASS` —
  206 PASSED (480,09 С). `R16_CONTRACTS=PASS` — 247 PASSED (47,34 С);
  `R16_WATCHDOG=PASS` — 12; `ROTATION_CONTRACTS=PASS` — 18;
  `APPLY_CONTRACTS=PASS` — 34; `R16_CLOSURE_STATUS=PASS` — 4;
  `PANEL_JS=PASS`. СЦЕНАРИИ XRAY: `R16_ROUTE_ALTERNATIVE/CLOSED/RECOVERY=PASS`,
  ОБА `HELD_STREAM=RETAINED`, `F13_ROTATION/CERTIFICATE/API_SWITCH_ROLLBACK=PASS`.
  `HOST_NM_TARGET_PRESENT=true`; CONNCHECK_HOST_FIELDS_MATCH.
  ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; Xray
  **26.11.9** (676eaf6, go1.27.3); кандидат
  `3915490126cf88602d1f0031fb80855c454093b9`; ТЗ — `94d22f11`;
  контроль — `f2cb19e0`; база бандла — `9e4c025e`. Тесты пишут только в
  свои временные каталоги, сценарии — loopback. Адрес NetworkManager в
  отчёт не включён; полные логи остаются локально.

## §1 Бандл и контракты FreePool

- `xgw-watchdog-conncheck-isolation.bundle`: SHA-256 **OK**
  (`6ead77cc…`), `git bundle verify` **OK**, приём = кандидат
  `39154901…`.
- `R16_CONTRACTS` — **247 passed** (47,34 с), пропусков нет.
- `R16_WATCHDOG` — **12 passed**, 164 deselected (13,88 с).
- `ROTATION_CONTRACTS` — **18 passed**, 158 deselected (42,04 с).
- `APPLY_CONTRACTS` — **34 passed** (7,58 с).
- `R16_CLOSURE_STATUS` — **4 passed** (5,96 с); `PANEL_JS` — PASS.

## §2 Контроль причин

- На контрольном коде (`f2cb19e0`) синтетический результат проверки
  связности подан сразу после первого шага: **7 падений**, имена
  совпали с известным списком **побайтно** (`cmp`) —
  `CONNCHECK_CONTROL_REPRODUCED_SEVEN`.
- Симптомы те же, что в прошлом отчёте:
  - три пустых списка событий: `test_daemon_reloads_missing_rules`
    (строка 990, `restored` → `[]`),
    `test_daemon_names_the_tun_without_an_address` (1008, `repaired`
    → `[]`), `test_daemon_repairs_lan_path` (1020, `restored` → `[]`);
  - четыре лишних `up`: `test_rules_failure_is_reported_once` (1071,
    `["up"]*3` → 4), `test_fail_closed_keeps_capture_while_xray_is_down`
    (1107, `[]` → `["up"]`), `test_tailscale_goes_direct_while_xray_is_down`
    (1144, `[]` → `["up"]`), `test_leak_reloads_rules_only_when_own_traffic_is_captured`
    (1159, `["up"]` → 2).

## §3 Перехват и conncheck на кандидате

- `WATCHDOG_CAPTURE_ISOLATED` — **7 passed** (20,09 с), исходные
  ожидания без правок: изоляция от результата проверки связности
  работает.
- `CONNCHECK_CONTRACTS` — **8 passed** (6,26 с): один reload после
  готового синтетического результата, корректная запись адресов и
  `loaded=true`; следующая самостоятельная потеря правил
  восстанавливается watchdog с событием; контракты разбора, записи и
  фонового поиска проходят.
- Полная матрица `test_daemon.py` + `test_daemon_main.py` —
  **206 passed** (480,09 с), падений нет.

## §4 Изолированный Xray

- `region-route`: `R16_ROUTE_ALTERNATIVE`, `CLOSED`, `RECOVERY` — PASS;
  `R16_ROUTE_HELD_STREAM=RETAINED`.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`.
- `certificate`: `OK` → `CERT_TIME_INVALID` (outbound_tls) → `OK` —
  `F13_CERTIFICATE=PASS`.
- `api-switch`: переключение и обратное без остановки процесса,
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §5 Штатный шлюз и M3

- `HOST_NM_TARGET_PRESENT=true` — проверка связности настроена
  (адрес не публикуется).
- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились** (xgw и xgw-xray active, xgw-singbox inactive);
  `CONNCHECK_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0, «весь дом» выкл.

## NOT_RUN

- Рабочий WAN — **NOT_RUN** (тесты штатных правил на реальном WAN — в
  отдельно согласованном окне).
- Принудительное завершение рабочих соединений — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Причина семи падений подтверждена контрольным кодом**: поданный
   результат проверки связности воспроизводит ровно те же 7 имён и
   симптомов.
2. **Изоляция на кандидате работает**: семь проверок проходят в
   изоляции и в полной матрице (`206 passed`), без изменения ожиданий.
3. **Контракты conncheck**: один reload после готового результата,
   корректные адреса и `loaded=true`, самовосстановление после потери
   правил с событием.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R16_WATCHDOG.log`, `ROTATION_CONTRACTS.log`,
  `APPLY_CONTRACTS.log`, `R16_CLOSURE_STATUS.log`,
  `WATCHDOG_CAPTURE_ISOLATED.log`, `CONNCHECK_CONTRACTS.log`,
  `watchdog-control.log`, `watchdog-matrix.log`, `known-errors`,
  `control-errors`, `current-errors`, `region-route.log`, `rotation.log`,
  `certificate.log`, `api-switch.log`, `xray-version.txt`,
  `before.txt`/`after.txt`, контрольное дерево и бандл — в приватном
  каталоге прогона 0700 на машине.
