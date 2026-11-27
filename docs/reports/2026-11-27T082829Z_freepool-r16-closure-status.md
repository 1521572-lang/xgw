# ThinkCentre · причина закрытия FreePool R16 и диагностика watchdog — 2026-11-27

- RESULT: **ЛИНИЯ ЗАКРЫТИЯ R16 — PASS. `R16_STATUS_COMPILE=PASS`;
  `R16_CONTRACTS=PASS` — 247 PASSED (47,44 С), ПРОПУСКОВ НЕТ;
  `R16_WATCHDOG=PASS` — 12 PASSED (14,12 С); `ROTATION_CONTRACTS=PASS`
  — 18 PASSED (41,71 С); `APPLY_CONTRACTS=PASS` — 34 PASSED (7,99 С);
  `R16_CLOSURE_STATUS=PASS` — 4 PASSED (6,04 С); `PANEL_JS=PASS`.
  СЦЕНАРИИ XRAY: `R16_ROUTE_ALTERNATIVE=PASS`, `R16_ROUTE_CLOSED=PASS`,
  `R16_ROUTE_RECOVERY=PASS`, `R16_ROUTE_HELD_STREAM=RETAINED`,
  `F13_ROTATION=PASS`, `F13_CERTIFICATE=PASS`,
  `F13_API_SWITCH_ROLLBACK=PASS`, `F13_HELD_STREAM=RETAINED`.
  R16_STATUS_HOST_FIELDS_MATCH. WATCHDOG_CAPTURE_ISOLATED=FAIL (7 ПАДЕНИЙ
  В ИЗОЛЯЦИИ) И WATCHDOG_MATRIX=FAIL (7 FAILED, 198 PASSED, 485 С):
  ВСЕ 7 СОВПАЛИ С ИЗВЕСТНЫМ СПИСКОМ, НОВЫХ 0, НЕ ВОСПРОИЗВЕЛИСЬ 0.
  ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; Xray
  **26.11.9** (676eaf6, go1.27.3); кандидат
  `f2cb19e05677b3a361dbbfbeb3d950bbcf8c33d8`; ТЗ — `4d24f985`; база
  бандла — `9e4c025e`. Временные процессы — отдельный префикс, сетевые
  сценарии — loopback. Полные логи и конфиги остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r16-closure-status.bundle`: SHA-256 **OK**
  (`9c226bf7…`), `git bundle verify` **OK**, приём = кандидат
  `f2cb19e0…`.
- `R16_CONTRACTS` — **247 passed** (47,44 с), пропусков нет.
- `R16_WATCHDOG` — **12 passed**, 163 deselected (14,12 с).
- `ROTATION_CONTRACTS` — **18 passed**, 157 deselected (41,71 с).
- `APPLY_CONTRACTS` — **34 passed** (7,99 с).
- `PANEL_JS` — синтаксис `src/xgw/ui/app.js` проверен Node.js — PASS.

## §2 Причина закрытия R16

- `R16_CLOSURE_STATUS` — **4 passed** (6,04 с). Подтверждено: при
  закрытом пути без подтверждённой альтернативы — `region_evidence_expired`
  в JSON панели и текст о сроке в CLI и журнале; при работающей
  альтернативе причины нет; свежая проверка убирает причину истечения;
  страна вне разрешённого региона и просроченный каталог **сами по себе**
  этой причины не дают.

## §3 Семь тестов перехвата: изоляция и матрица

| Тест | Строка | Ожидалось → получено |
| --- | --- | --- |
| `test_daemon_reloads_missing_rules` | 990 | `restored` ожидалось → **`[]`** |
| `test_daemon_names_the_tun_without_an_address` | 1008 | `repaired` ожидалось → **`[]`** |
| `test_daemon_repairs_lan_path` | 1020 | `restored` ожидалось → **`[]`** |
| `test_rules_failure_is_reported_once` | 1071 | `["up"] * 3` → **`["up", "up", "up", "up"]`** (лишний `up`) |
| `test_fail_closed_keeps_capture_while_xray_is_down` | 1107 | `[]` и состояние `on` → **`["up"]`** |
| `test_tailscale_goes_direct_while_xray_is_down` | 1144 | переходы совпали, действия `[]` → **`["up"]`** |
| `test_leak_reloads_rules_only_when_own_traffic_is_captured` | 1159 | `["up"]` → **`["up", "up"]`** |

- Изолированный прогон: **7 failed** (21,35 с). Полная матрица двух
  файлов: **7 failed, 198 passed** (485,40 с), выход 1.
- Сравнение с известным списком: **совпали 7, новых 0, не
  воспроизвелись 0**. Симптомы одинаковы в изоляции и в матрице —
  зависимость от порядка не наблюдается. Общий признак: лишнее
  действие `up` либо пустой список действий; у тестов перехвата,
  правил и tailscale.
- Причина по одному набору не назначается: это среда перехвата
  (правила/tun/tailscale), тот же набор падал на предыдущих ревизиях.

## §4 Изолированный Xray

- `region-route`: `R16_ROUTE_ALTERNATIVE=PASS`,
  `R16_ROUTE_HELD_STREAM=RETAINED`, `R16_ROUTE_CLOSED=PASS`,
  `R16_ROUTE_RECOVERY=PASS`.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`.
- `certificate`: `OK` → `CERT_TIME_INVALID` (outbound_tls) → `OK` —
  `F13_CERTIFICATE=PASS`.
- `api-switch`: переключение и обратное без остановки процесса,
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §5 Штатный шлюз и M3

- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились** (xgw и xgw-xray active, xgw-singbox inactive);
  `R16_STATUS_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0, «весь дом» выкл.

## NOT_RUN

- Штатный WAN — **NOT_RUN**.
- Принудительное завершение рабочих соединений — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Причина закрытия R16 подтверждена** в панели, CLI и журнале;
   посторонние причины (страна вне региона, просроченный каталог) её
   не создают.
2. **Семь средовых падений не зависят от порядка**: те же имена, строки
   и значения в изоляции и в матрице; новых сбоев нет.
3. **Симптом общий — лишний `up`** (или пустой список действий) в
   проверках перехвата/правил/tun/tailscale; сравнение на одной Ubuntu
   24.04 этого не объясняет — нужна отдельная среда nftables.
4. **M3 по предпосылкам не готов**; рабочий трафик и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R16_WATCHDOG.log`, `ROTATION_CONTRACTS.log`,
  `APPLY_CONTRACTS.log`, `R16_CLOSURE_STATUS.log`,
  `WATCHDOG_CAPTURE_ISOLATED.log`, `watchdog-matrix.log`,
  `known-errors`, `current-errors`, `region-route.log`, `rotation.log`,
  `certificate.log`, `api-switch.log`, `xray-version.txt`,
  `before.txt`/`after.txt` и бандл — в приватном каталоге прогона 0700
  на машине.
