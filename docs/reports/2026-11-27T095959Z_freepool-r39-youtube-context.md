# ThinkCentre · проверки YouTube в контексте FreePool R39 — 2026-11-27

- RESULT: **R39_YOUTUBE_CONTEXT=PASS. `R39_COMPILE=PASS`; `R16_CONTRACTS=PASS`
  — 250 PASSED (45,83 С); `R39_CONTEXT=PASS` — 232 PASSED (50,39 С);
  `SUBSCRIPTION_YOUTUBE=PASS` — 21 PASSED, 185 DESELECTED (45,00 С);
  `WATCHDOG_CONTRACTS=PASS` — 20 PASSED (17,34 С); ПРОПУСКОВ НЕТ.
  РЕАЛЬНЫЕ ПРОВЕРКИ ЧЕРЕЗ XRAY: `R39_YOUTUBE_SAME_CONTEXT=PASS`,
  `R39_YOUTUBE_NEW_WAN=PASS`, `R39_YOUTUBE_POLICY_RACE=PASS`.
  ЯДРА: XRAY 26.11.9, SING-BOX 1.14.4; `R39_BRIDGE_LOOPBACK=PASS`
  (32-СИМВОЛЬНЫЙ ID). ШТАТНЫЕ КЛЮЧИ: `R39_HOST_XRAY=PASS`,
  `R39_HOST_SINGBOX=NOT_RUN` (СЛУЖБА НЕАКТИВНА); `R39_HOST_FIELDS_MATCH`.
  СЦЕНАРИИ: `R16_ROUTE_ALTERNATIVE/CLOSED/RECOVERY=PASS`, ОБА
  `HELD_STREAM=RETAINED`, `F13_ROTATION/CERTIFICATE/API_SWITCH_ROLLBACK=PASS`.
  ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; кандидат
  `ee6f67978e4b658bcab9ca659fb383bcf77d192b`; ТЗ — `ee757dbd`; база
  бандла — `9e4c025e`. Проверки — отдельный каталог и loopback; источник
  отдавал заданные 503 и 204. Публичное воспроизведение YouTube не
  использовалось. SQLite, конфиги и полные логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-youtube-context.bundle`: SHA-256 **OK**
  (`af48b887…`), `git bundle verify` **OK**, приём = кандидат
  `ee6f6797…`.
- `R16_CONTRACTS` — **250 passed** (45,83 с), пропусков нет.
- `R39_CONTEXT` (`runtime`, `traffic`, `singbox`, поколения, WAN, `speed`,
  `youtube`) — **232 passed** (50,39 с), пропусков нет.
- `SUBSCRIPTION_YOUTUBE` (`test_daemon` + `test_daemon_main`, `-k
  'youtube or media'`) — **21 passed**, 185 deselected (45,00 с).
- `WATCHDOG_CONTRACTS` (`conncheck`, такт, регион) — **20 passed**
  (17,34 с).
- Контрактами подтверждено: старая запись без контекста исключается;
  при смене политики учитываются 1024 байта; результат YouTube не
  зависит от лимита обычного замера; изменение порога скрывает старый
  результат.

## §2 Один контекст

- Два HTTP 503 через установленный Xray подряд: в SQLite два отказа,
  выход считается неподходящим для YouTube —
  **`R39_YOUTUBE_SAME_CONTEXT=PASS`**.

## §3 Новое поколение WAN

- После смены метки WAN сводка сразу скрывает старый результат,
  следующий 503 начинает счёт с единицы, закрепление сохраняется —
  **`R39_YOUTUBE_NEW_WAN=PASS`**.

## §4 Смена политики во время запроса

- Источник меняет регион после начала HTTP: запись SQLite остаётся
  прежней, результата в сводке нет; следующий запрос в новом контексте
  сохраняет успех и обнуляет счётчик —
  **`R39_YOUTUBE_POLICY_RACE=PASS`**.

## §5 Регрессии ядер

- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID, загрузка до и после
  перезапуска sing-box, отказ при остановке, смена отпечатка моста,
  стабильный прямой путь.
- `region-route`: `R16_ROUTE_ALTERNATIVE`, `CLOSED`, `RECOVERY` — PASS;
  `R16_ROUTE_HELD_STREAM=RETAINED`.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §6 Штатный шлюз и M3

- `R39_HOST_XRAY=PASS` — ключ замера по штатному файлу и идентификатору
  запуска стабилен.
- `R39_HOST_SINGBOX=NOT_RUN` — служба неактивна, идентификатор запуска
  недоступен.
- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились**; `R39_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Публичное воспроизведение YouTube — **NOT_RUN**.
- Смена рабочего WAN — **NOT_RUN**.
- Переключение рабочих поколений — **NOT_RUN**.
- Принудительное закрытие потоков — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.
- Ключ штатного sing-box — **NOT_RUN** (служба неактивна).

## Наблюдения для Codex

1. **Результаты YouTube привязаны к контексту**: два отказа в одном
   контексте считаются, смена WAN начинает счёт заново и скрывает
   старый результат, закрепление не снимается.
2. **Смена политики во время HTTP не оставляет ложно успешной
   записи**: SQLite прежний, сводка без результата, следующий запрос в
   новом контексте сохраняет успех и обнуляет счётчик.
3. **Старые записи без контекста исключаются**, порог YouTube скрывает
   прежний результат, лимит обычного замера не влияет.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R39_CONTEXT.log`, `SUBSCRIPTION_YOUTUBE.log`,
  `WATCHDOG_CONTRACTS.log`, `youtube-probe.log`, `bridge.log`,
  `region-route.log`, `rotation.log`, `certificate.log`,
  `api-switch.log`, `xray-version.txt`, `singbox-version.log`,
  `before.txt`/`after.txt`, префиксы сценариев и бандл — в приватном
  каталоге прогона 0700 на машине.
