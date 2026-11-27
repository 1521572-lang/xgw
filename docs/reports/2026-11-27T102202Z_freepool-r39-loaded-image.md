# ThinkCentre · загруженные образы ядер FreePool R39 — 2026-11-27

- RESULT: **R39_LOADED_IMAGE — ЧАСТИЧНЫЙ FAIL. ЗАГРУЖЕННЫЕ ОБРАЗЫ ОБОИХ
  ЯДЕР — PASS: `R39_IMAGE_XRAY_ATOMIC_REPLACE`, `R39_IMAGE_XRAY_RESTART`,
  `R39_IMAGE_SINGBOX_ATOMIC_REPLACE`, `R39_IMAGE_SINGBOX_RESTART`.
  РЕГРЕССИИ YouTube — все три PASS; `R39_BRIDGE_LOOPBACK=PASS`;
  `rotation`, `certificate`, `api-switch` — PASS; `R39_HOST_XRAY=PASS`
  (`SOURCE=INSTALLED_ONLY`), `R39_HOST_SINGBOX=NOT_RUN` (служба
  `xgw-singbox.service` неактивна); `R39_HOST_FIELDS_MATCH`.
  **`R39_CONTEXT=FAIL`** — 231 PASSED, 2 FAILED: оба варианта
  `test_bridge_measurement_context_requires_active_slot_and_matching_configs`
  на шаге «поколение = None». ПРИЧИНА: на хосте с **08:05 UTC активна
  `xgw-singbox-blue.service`**; новый `measurement_generation` для
  systemd-служб берёт `measurement_runtime()`, а тест подменяет только
  `runtime_generation` — реальная служба даёт поколение, и контекст не
  пуст. **`region-route`** в первом прогоне — FAIL (`ConnectionResetError`
  на шаге закрытия после ALTERNATIVE и HELD_STREAM=RETAINED), немедленный
  повтор — **PASS по всем четырём меткам** (транзиентно).
  Остальные контракты: R16 — 250 PASSED, SUBSCRIPTION_YOUTUBE — 21
  PASSED, WATCHDOG — 20 PASSED; пропусков нет. ГОТОВНОСТЬ M3: СТАТУС
  СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; ядра —
  **Xray 26.11.9** (676eaf6, go1.27.3) и **sing-box 1.14.4**; кандидат
  `8670c453503cef4ab7cff0d87f0d57a11618c53a`; ТЗ — `66ba4d28`; база
  бандла — `9e4c025e`. Копии ядер запускались в отдельном каталоге,
  запросы — loopback; со штатной установки только чтение. PID, хеши
  рабочих образов, базы, конфиги и полные логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-loaded-image.bundle`: SHA-256 **OK**
  (`2e2410d5…`), `git bundle verify` **OK**, приём = кандидат
  `8670c453…`.
- `R39_COMPILE=PASS`.
- `R16_CONTRACTS` — **250 passed** (49,84 с), пропусков нет.
- `R39_CONTEXT` — **231 passed, 2 failed** (53,41 с); сбои —
  `test_bridge_measurement_context_requires_active_slot_and_matching_configs`
  `[subscription]` и `[freepool]`, `tests/test_singbox.py:332`.
- `SUBSCRIPTION_YOUTUBE` — **21 passed**, 185 deselected (46,14 с).
- `WATCHDOG_CONTRACTS` — **20 passed** (17,85 с).

## §2 Два образа

| Метка | Итог |
| --- | --- |
| `R39_IMAGE_XRAY_ATOMIC_REPLACE` | **PASS** — идентичная замена сохраняет ключ; копия с тестовыми байтами меняет хеш файла на диске, `/proc/PID/exe` даёт прежний хеш, PID прежний; ключ содержит оба отпечатка |
| `R39_IMAGE_XRAY_RESTART` | **PASS** — после перезапуска новая копия — исполняемый образ, хеши совпадают, ключ использует новое поколение |
| `R39_IMAGE_SINGBOX_ATOMIC_REPLACE` | **PASS** (то же для sing-box) |
| `R39_IMAGE_SINGBOX_RESTART` | **PASS** |

## §3 Контекст моста: FAIL и причина

- На шаге «поколение = None» контекст не пуст: возвращён
  `{(порт, 'd'): (отпечаток, ключ)}` для обоих вариантов
  (`subscription` и `freepool`).
- Причина — **состояние хоста**: с 08:05 UTC сегодня активна
  `xgw-singbox-blue.service`. Новый `measurement_generation` для
  systemd-служб читает `measurement_runtime()`, а тест подменяет только
  `runtime_generation`; реальная служба даёт поколение, поэтому проверка
  «generation None → пусто» не выполняется. На хосте с неактивным blue
  та же проверка проходила.
- Это пробел изоляции теста от реальной systemd-службы, а не показанный
  отказ продуктовой логики: при живом поколении контекст обязан быть
  непустым.

## §4 Регрессии

- `R39_YOUTUBE_SAME_CONTEXT`, `R39_YOUTUBE_NEW_WAN`,
  `R39_YOUTUBE_POLICY_RACE` — **PASS**.
- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID.
- `region-route` — первый прогон **FAIL**: `ConnectionResetError` на
  `assert exchange(fresh) == b""` после `R16_ROUTE_ALTERNATIVE=PASS` и
  `R16_ROUTE_HELD_STREAM=RETAINED`; немедленный повтор — **PASS**
  (`ALTERNATIVE`, `CLOSED`, `RECOVERY`, `HELD_STREAM=RETAINED`).
  Наблюдение записано как транзиентное.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §5 Штатный шлюз и M3

- `R39_HOST_XRAY_SOURCE=INSTALLED_ONLY` — образ процесса штатного Xray
  недоступен на чтение (другой UID); ключ использует файл установки и
  поколение запуска, образ процесса остаётся непроверенным;
  `R39_HOST_XRAY=PASS` (ключ стабилен).
- `R39_HOST_SINGBOX=NOT_RUN` — `xgw-singbox.service` неактивна
  (поколение запуска недоступно).
- `systemctl show` (xgw, xgw-xray, xgw-singbox): состояния **не
  изменились**; `R39_HOST_FIELDS_MATCH`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Публичное воспроизведение — **NOT_RUN**.
- Смена рабочего WAN и поколений — **NOT_RUN**.
- Дренирование рабочих соединений — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.
- Ключ штатного sing-box — **NOT_RUN** (служба неактивна).
- `R16_ROUTE_CLOSED`/`RECOVERY` в первом прогоне — **NOT_RUN** до
  повтора; повтор дал PASS.

## Наблюдения для Codex

1. **Учёт загруженного образа работает для обоих ядер**: идентичная
   замена не меняет ключ, добавленные байты меняют только файл на
   диске, `/proc/PID/exe` и PID прежние, после перезапуска — новая
   копия и новое поколение.
2. **Нужна изоляция теста от реальной systemd-службы**:
   `test_bridge_measurement_context_requires_active_slot_and_matching_configs`
   должен подменять и `measurement_runtime` (или использовать
   несуществующий юнит), иначе активный `xgw-singbox-blue.service` на
   хосте ломает проверку «generation None».
3. **region-route транзиентен**: повтор сразу после сбоя прошёл все
   четыре метки; стоит отслеживать, если повторится.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R39_CONTEXT.log`, `SUBSCRIPTION_YOUTUBE.log`,
  `WATCHDOG_CONTRACTS.log`, `images.log`, `youtube-probe.log`,
  `bridge.log`, `region-route.log`, `region-route-retry.log`,
  `rotation.log`, `certificate.log`, `api-switch.log`,
  `xray-version.txt`, `singbox-version.log`, `before.txt`/`after.txt`,
  префиксы сценариев и бандл — в приватном каталоге прогона 0700 на
  машине.
