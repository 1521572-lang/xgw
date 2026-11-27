# ThinkCentre · бинарники ядер в контексте замеров FreePool R39 — 2026-11-27

- RESULT: **R39_CORE_FINGERPRINT — PASS ПО ВСЕМ ДОСТУПНЫМ БЛОКАМ.
  `R39_COMPILE=PASS`; `R16_CONTRACTS=PASS` — 247 PASSED (49,14 С);
  `R39_CONTEXT=PASS` — 183 PASSED (50,35 С); `WATCHDOG_CONTRACTS=PASS` —
  20 PASSED (17,54 С); ПРОПУСКОВ НЕТ. ОБА ЯДРА:
  `R39_BINARY_FIXTURE_xray=PASS`, `R39_BINARY_FIXTURE_sing-box=PASS`;
  `R39_BRIDGE_LOOPBACK=PASS` (ИСХОДНЫЙ 32-СИМВОЛЬНЫЙ ID). ШТАТНЫЕ КЛЮЧИ:
  `R39_HOST_XRAY=PASS`, `R39_HOST_SINGBOX=NOT_RUN` (СЛУЖБА НЕАКТИВНА —
  НЕТ ИДЕНТИФИКАТОРА ЗАПУСКА); `R39_HOST_FIELDS_MATCH`. СЦЕНАРИИ XRAY:
  `R16_ROUTE_ALTERNATIVE/CLOSED/RECOVERY=PASS`, ОБА
  `HELD_STREAM=RETAINED`, `F13_ROTATION/CERTIFICATE/API_SWITCH_ROLLBACK=PASS`.
  ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; ядра —
  **Xray 26.11.9** (676eaf6, go1.27.3) и **sing-box 1.14.4**;
  кандидат `afd4a4ec19e30dc2876f8297d56b02c3c80255db`; ТЗ — `0ddc22ba`;
  база бандла — `9e4c025e`. Сценарии — временные копии файлов и
  loopback; штатные процессы только считывались. Ключи, PID и пути в
  отчёт не включены; полные логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-core-fingerprint.bundle`: SHA-256 **OK**
  (`04288c93…`), `git bundle verify` **OK**, приём = кандидат
  `afd4a4ec…`.
- `R39_COMPILE=PASS` — исходники, helper, `conftest` и тест демона.
- `R16_CONTRACTS` — **247 passed** (49,14 с), пропусков нет.
- `R39_CONTEXT` (`runtime`, `traffic`, `singbox`, поколения sing-box,
  WAN-поколение) — **183 passed** (50,35 с), пропусков нет.
- `WATCHDOG_CONTRACTS` (`conncheck`, такт watchdog, регион) —
  **20 passed**, 163 deselected (17,54 с).

## §2 Частные копии ядер

| Событие | Xray | sing-box |
| --- | --- | --- |
| Идентичная замена файла | ключ **сохранён** | ключ **сохранён** |
| Другие байты при прежнем запуске | ключ **изменён**, идентификатор запуска прежний | то же |
| Удаление файла | ключ **скрыт** | ключ **скрыт** |
| Восстановление исходных байтов | ключ **вернулся** | ключ **вернулся** |
| После остановки процесса | ключ **недоступен** | ключ **недоступен** |

- Метки: **`R39_BINARY_FIXTURE_xray=PASS`**,
  **`R39_BINARY_FIXTURE_sing-box=PASS`**.

## §3 Мост

- `R39_BRIDGE_LOOPBACK=PASS` — исходная фикстура с 32-символьным
  идентификатором: загрузка до и после перезапуска sing-box, отказ при
  остановке, смена отпечатка моста и стабильный прямой путь.

## §4 Штатный шлюз

- `R39_HOST_XRAY=PASS` — ключ замера по штатному файлу установки и
  идентификатору запуска стабилен при двух чтениях.
- `R39_HOST_SINGBOX=NOT_RUN` — служба sing-box неактивна, идентификатор
  запуска недоступен; байты из адресного пространства процесса этим
  блоком не проверяются.
- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились** (xgw и xgw-xray active, xgw-singbox inactive);
  `R39_HOST_FIELDS_MATCH`.

## §5 Сценарии Xray

- `region-route`: `R16_ROUTE_ALTERNATIVE`, `CLOSED`, `RECOVERY` — PASS;
  `R16_ROUTE_HELD_STREAM=RETAINED`.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`.
- `certificate`: `OK` → `CERT_TIME_INVALID` (outbound_tls) → `OK` —
  `F13_CERTIFICATE=PASS`.
- `api-switch`: переключение и обратное без остановки процесса,
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §6 Готовность M3

- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0, «весь дом» выкл.

## NOT_RUN

- Смена рабочего WAN — **NOT_RUN**.
- Переключение рабочих поколений — **NOT_RUN**.
- Принудительное завершение потоков — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.
- Ключ штатного sing-box — **NOT_RUN** (служба неактивна).

## Наблюдения для Codex

1. **Контекст замера привязан к байтам файла ядра**: идентичная замена
   не меняет ключ, другие байты меняют его при том же запуске, удаление
   скрывает, восстановление возвращает; для Xray и sing-box одинаково.
2. **Мост с исходным 32-символьным ID** проходит полный loopback-сценарий.
3. **Штатный Xray-ключ стабилен**; sing-box-ключ недоступен из-за
   неактивной службы — ожидаемый `NOT_RUN`.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R39_CONTEXT.log`, `WATCHDOG_CONTRACTS.log`,
  `xray.fixture-version.log`, `sing-box.fixture-version.log`,
  `xray.fixture.log`, `sing-box.fixture.log`, `bridge.log`,
  `region-route.log`, `rotation.log`, `certificate.log`,
  `api-switch.log`, `before.txt`/`after.txt`, временные копии ядер и
  бандл — в приватном каталоге прогона 0700 на машине.
