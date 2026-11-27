# ThinkCentre · поколение политики замеров FreePool R39 — 2026-11-27

- RESULT: **R39_POLICY_EPOCH=PASS. `R39_COMPILE=PASS`; `R16_CONTRACTS=PASS`
  — 249 PASSED (44,05 С); `R39_CONTEXT=PASS` — 206 PASSED (51,79 С);
  `WATCHDOG_CONTRACTS=PASS` — 20 PASSED (18,47 С); ПРОПУСКОВ НЕТ.
  РЕАЛЬНАЯ ЗАГРУЗКА: `R39_POLICY_SAMPLE=PASS`,
  `R39_POLICY_CHANGE_DURING_SAMPLE=PASS`,
  `R39_POLICY_PERSISTED_RETURN=PASS`. ЯДРА: XRAY 26.11.9, SING-BOX 1.14.4;
  `R39_BRIDGE_LOOPBACK=PASS` (32-СИМВОЛЬНЫЙ ID). ШТАТНЫЕ КЛЮЧИ:
  `R39_HOST_XRAY=PASS`, `R39_HOST_SINGBOX=NOT_RUN` (СЛУЖБА НЕАКТИВНА);
  `R39_HOST_FIELDS_MATCH`. СЦЕНАРИИ: `R16_ROUTE_ALTERNATIVE/CLOSED/RECOVERY=PASS`,
  ОБА `HELD_STREAM=RETAINED`, `F13_ROTATION/CERTIFICATE/API_SWITCH_ROLLBACK=PASS`.
  ГОТОВНОСТЬ M3: СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; кандидат
  `411586a432768f485e7078577abd493c6f1ed918`; ТЗ — `29e09eb4`; база
  бандла — `9e4c025e`. Сценарии — отдельный префикс и loopback; штатные
  службы и файлы только считывались. Ключи, метаданные SQLite и конфиги
  остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-policy-epoch.bundle`: SHA-256 **OK**
  (`ab7bb3fc…`), `git bundle verify` **OK**, приём = кандидат
  `411586a4…`.
- `R16_CONTRACTS` — **249 passed** (44,05 с), пропусков нет.
- `R39_CONTEXT` (`runtime`, `traffic`, `singbox`, поколения sing-box,
  WAN-поколение, `speed`) — **206 passed** (51,79 с), пропусков нет.
- `WATCHDOG_CONTRACTS` (`conncheck`, такт, регион) — **20 passed**,
  163 deselected (18,47 с).
- Контрактами подтверждено: старый замер без поля политики не влияет на
  выбор; бюджет и добавление устройства при прежнем охвате сохраняют
  поколение; регион, порядок разрешённых fallback в preferred, TTL и
  смена охвата меняют ключ.

## §2 Реальная загрузка через Xray

- Тело загружено через установленный Xray; скорость сохранена вместе с
  поколением политики в приватной SQLite; число байтов совпало с телом
  — **`R39_POLICY_SAMPLE=PASS`**.

## §3 Смена условий во время загрузки

- Политика изменена **после начала** HTTP-запроса.
- Байты учтены (`_pool_own` равен размеру тела), запись скорости **не
  перезаписана** (метаданные прежние), старое число **исчезло из
  сводки**; поколение WAN прежнее; живое закрепление в фикстуре
  сохранилось — **`R39_POLICY_CHANGE_DURING_SAMPLE=PASS`**.

## §4 Переоткрытие и возврат

- Переоткрытие SQLite с той же политикой сохраняет поколение; возврат в
  первый регион выдаёт новое — **`R39_POLICY_PERSISTED_RETURN=PASS`**.

## §5 Регрессии ядер

- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный идентификатор, загрузка до
  и после перезапуска sing-box, отказ при остановке, смена отпечатка
  моста и стабильный прямой путь.
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

- Смена рабочего WAN — **NOT_RUN**.
- Переключение рабочих поколений — **NOT_RUN**.
- Принудительное завершение потоков — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.
- Ключ штатного sing-box — **NOT_RUN** (служба неактивна).

## Наблюдения для Codex

1. **Поколение политики привязано к значимым условиям**: регион, порядок
   fallback, TTL и охват меняют ключ; бюджет и устройство при прежнем
   охвате — нет; старый замер без поля политики не участвует в выборе.
2. **Смена условий во время загрузки**: байты учтены, результат не
   сохранён, прежнее число скрыто, WAN-поколение не тронуто, закрепление
   живо.
3. **SQLite хранит поколение**: переоткрытие сохраняет, возврат региона
   даёт новое.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `R39_CONTEXT.log`, `WATCHDOG_CONTRACTS.log`,
  `policy-sample.log`, `bridge.log`, `region-route.log`, `rotation.log`,
  `certificate.log`, `api-switch.log`, `xray-version.txt`,
  `singbox-version.log`, `before.txt`/`after.txt`, префиксы сценариев и
  бандл — в приватном каталоге прогона 0700 на машине.
