# ThinkCentre · пересборка маршрута на границе R16 — 2026-11-27

- RESULT: **R16_ROUTE_DEADLINE — ОБЯЗАТЕЛЬНЫЕ БЛОКИ PASS. КОМПИЛЯЦИЯ:
  `R16_COMPILE=PASS`; КОНТРАКТЫ: `R16_CONTRACTS=PASS` — 246 PASSED (48,28 С),
  ПРОПУСКОВ НЕТ; ТАКТ WATCHDOG: `R16_WATCHDOG=PASS` — 12 PASSED (14,25 С,
  161 DESELECTED); СЦЕНАРИЙ МАРШРУТА: `R16_ROUTE_ALTERNATIVE=PASS`,
  `R16_ROUTE_CLOSED=PASS`, `R16_ROUTE_RECOVERY=PASS`,
  `R16_ROUTE_HELD_STREAM=RETAINED`; РЕГРЕССИИ XRAY: `F13_ROTATION=PASS`,
  `F13_CERTIFICATE=PASS`, `F13_API_SWITCH_ROLLBACK=PASS`,
  `F13_HELD_STREAM=RETAINED`; R16_HOST_FIELDS_MATCH. WATCHDOG_TIMING=FAIL:
  ТЕ ЖЕ 5 ТЕСТОВ ПАДАЮТ И НА КОНТРОЛЬНОЙ РЕВИЗИИ С ТЕМИ ЖЕ СТРОКАМИ —
  ИЗВЕСТНАЯ СРЕДА, НОВЫХ ОШИБОК НЕТ. ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ,
  ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`: observe, устройств 0, живых 0).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; amd64; Xray **26.11.9**
  (676eaf6, go1.27.3); кандидат
  `be91e2b965fdc2fa5571fbf27b07a6342617c403`; ТЗ — `33377a99`;
  контрольная ревизия — `2cda05a4`; база бандла — `9e4c025e`. Сетевые
  сценарии — loopback, изолированный префикс; полные логи и временные
  конфиги остаются локально.

## §1 Сборка и контракты

- `xgw-freepool-r16-route-deadline.bundle`: SHA-256 **OK**
  (`480f99db…`), `git bundle verify` **OK**, база `9e4c025e`
  присутствует, приём = кандидат `be91e2b9…`.
- `py_compile`/`compileall` исходников и helper: **`R16_COMPILE=PASS`**.
- Наборы R13/R50, WAN-поколение, API, конфиг и разбор
  `Subscription-Userinfo`: **246 passed** (48,28 с), пропусков нет.
- Такт watchdog: **12 passed** (14,25 с, 161 deselected), пропусков нет.
  Подтверждено: срок прерывает обычную паузу watchdog и запускает
  пересборку в пределах 10-минутного интервала; за секунду до истечения
  срочной пересборки нет; конфликт страны применённого выхода
  запускает её на ближайшей сверке.

## §2 Контроль таймингов

| Тест | Кандидат | Контроль `2cda05a4` |
| --- | --- | --- |
| `test_all_dead_refreshes_directly_and_rotates_at_once` | FAIL (`test_daemon.py:612`, `assert 0 == 1`) | FAIL, та же строка |
| `test_member_failing_the_first_check_is_replaced_at_once[FROZEN-True]` | FAIL (`:2094`, `assert 1 == 2`) | FAIL, та же строка |
| то же `[FROZEN-False]` | FAIL | FAIL |
| то же `[CONNECT_FAIL-True]` | FAIL | FAIL |
| то же `[CONNECT_FAIL-False]` | FAIL | FAIL |

- Итог: **5 failed на кандидате и 5 failed на контроле**, имена и строки
  совпадают; новых ошибок нет. Это известная среда (тот же набор падал
  на WSL на обеих ревизиях).

## §3 Маршрут на границе срока

| Метка | Итог |
| --- | --- |
| `R16_ROUTE_ALTERNATIVE` | **PASS** — после границы новые соединения идут к B, тег A снят через API |
| `R16_ROUTE_CLOSED` | **PASS** — после истечения подтверждения B новые соединения остаются без полезных данных и не уходят ни на A, ни на B |
| `R16_ROUTE_RECOVERY` | **PASS** — свежая проверка B восстанавливает обмен |
| `R16_ROUTE_HELD_STREAM` | **RETAINED** — один обмен после смены; принудительное завершение действующих соединений этим не подтверждается |

## §4 Регрессии Xray

- Ротация ключа: `OK` → `CONNECT_FAIL` (download/http) → `OK`.
- Сертификат: `OK` → `CERT_TIME_INVALID` (outbound_tls/certificate_time)
  → `OK`.
- API: переключение и обратное переключение без остановки процесса;
  удерживаемое соединение — `RETAINED`.

## §5 Сверка шлюза и M3

- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились** (xgw и xgw-xray active, xgw-singbox inactive);
  `R16_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; режим observe,
  устройств 0, живых 0, «весь дом» выкл.

## NOT_RUN

- Рабочий WAN — **NOT_RUN**.
- Пользовательские соединения — **NOT_RUN**.
- Принудительное завершение действующих соединений — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Планирование срочной пересборки подтверждено**: срок прерывает
   паузу watchdog, за секунду до границы пересборки нет, конфликт
   страны применённого выхода запускает её на ближайшей сверке.
2. **Маршрут на границе ведёт себя корректно**: переход на B, отказ без
   полезных данных после истечения и восстановление после свежей
   проверки; удерживаемое соединение — `RETAINED`.
3. **WATCHDOG_TIMING — среда, не регрессия**: пять тестов падают
   одинаково на кандидате и контроле, имена и строки совпадают.
4. **M3 по предпосылкам не готов**; рабочий трафик и сутки требуют
   отдельного окна.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R16_WATCHDOG.log`, `timing.log`,
  `timing-control.log`, `region-route.log`, `rotation.log`,
  `certificate.log`, `api-switch.log`, `xray-version.txt`,
  `before.txt`/`after.txt`, префиксы сценариев и бандл — в приватном
  каталоге прогона 0700 на машине.
