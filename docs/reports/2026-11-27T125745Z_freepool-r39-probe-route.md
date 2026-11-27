# ThinkCentre · привязка замера FreePool к служебному маршруту — 2026-11-27

- RESULT: **R39 PROBE ROUTE — PASS. `R39_COMPILE=PASS`;
  `PROBE_ROUTE_CONTRACTS=PASS` — 59 PASSED (36 DESELECTED);
  `EXECSTART_CONTRACTS=PASS` — 4 PASSED; `BRIDGE_SLOT_CONTRACTS=PASS` —
  2 PASSED; `R16_CONTRACTS=PASS` — 251 PASSED (53,10 С);
  `R39_CONTEXT=PASS` — 236 PASSED (53,73 С); `SUBSCRIPTION_YOUTUBE` —
  21 PASSED (47,72 С); `WATCHDOG_CONTRACTS` — 20 PASSED (17,08 С);
  ПРОПУСКОВ НЕТ. СЛУЖЕБНЫЙ МАРШРУТ: `R39_PROBE_BOUND=PASS`,
  `R39_PROBE_ROUTE_CHANGED_DURING_SAMPLE=PASS`,
  `R39_PROBE_WRONG_OUTBOUND_SKIPPED=PASS`. ВРЕМЕННАЯ СЛУЖБА ExecStart:
  все пять меток PASS. ОБРАЗЫ — все четыре PASS; YouTube — все три PASS;
  `R39_BRIDGE_LOOPBACK=PASS`. ШТАТНЫЕ КЛЮЧИ: `R39_HOST_XRAY=PASS`
  (`STANDARD`, `ARGV0`, `INSTALLED_ONLY`); `R39_HOST_SINGBOX_SLOT=blue`,
  `R39_HOST_SINGBOX=PASS` (`STANDARD`, `EXECSTART_PID`, `INSTALLED_ONLY`);
  `R39_HOST_FIELDS_MATCH`. ТРИ ПРОГОНА R16 — PASS (EOF, EOF, EOF).
  РЕГРЕССИИ: `rotation`, `certificate`, `api-switch` — PASS. M3: СТАТУС
  СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; systemd 255 (255.4-1ubuntu8.19); Python 3.12.3;
  pytest 7.4.4; amd64; ядра — **Xray 26.11.9** (676eaf6, go1.27.3) и
  **sing-box 1.14.4**; кандидат
  `21e37f97ad216b1e3b68f7903a560f87d4e2c694`; ТЗ — `28bff7fa`; база
  бандла — `9e4c025e`. Изменение правил — через API отдельного Xray,
  запросы — loopback; временная пользовательская служба — копия Xray со
  случайным именем и лимитом 60 с, затем остановлена. Абсолютные пути
  хоста, аргументы процессов, PID, хеши, базы, конфиги и полные логи
  остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-probe-route.bundle`: SHA-256 **OK** (`3f44e069…`),
  `git bundle verify` **OK**, приём = кандидат `21e37f97…`.
- `PROBE_ROUTE_CONTRACTS` — **59 passed**, 36 deselected: смена порта
  меняет отпечаток своего выхода; позднее общее правило и чужой вход
  сохраняют ключ; правило, ведущее к другому выходу, и более раннее
  общее правило скрывают неподтверждённый контекст.
- `R16_CONTRACTS` — **251 passed** (53,10 с); `R39_CONTEXT` — **236
  passed** (53,73 с); `SUBSCRIPTION_YOUTUBE` — **21 passed** (47,72 с);
  `WATCHDOG_CONTRACTS` — **20 passed** (17,08 с); пропусков нет.

## §2 Служебный маршрут пробы

| Проверка | Итог |
| --- | --- |
| `R39_PROBE_BOUND` | **PASS** — скорость и проба YouTube идут через отдельный Xray на первый локальный источник; у второго источника **ноль** запросов |
| `R39_PROBE_ROUTE_CHANGED_DURING_SAMPLE` | **PASS** — во время запроса стенд через API применяет другое правило: полученные байты учтены, запись SQLite прежняя, скорость и YouTube исчезли из текущей сводки |
| `R39_PROBE_WRONG_OUTBOUND_SKIPPED` | **PASS** — контрольный запрос через тот же вход доходит до второго источника и получает 503; планировщик пропускает этот вход для замера YouTube, запись и закрепление сохранены |

## §3 ExecStart, образы, YouTube, мост

- Временная пользовательская служба: `R39_EXECSTART_USER_PATH`,
  `R39_RELOAD_MATCHED_MAINPID`, `R39_RELOAD_CHANGED_PATH_REJECTED`,
  `R39_EXECSTART_INSTALLED_ONLY`, `R39_EXECSTART_USER_UNIT_CLEANUP` —
  **PASS**.
- `R39_IMAGE_XRAY_ATOMIC_REPLACE`, `R39_IMAGE_XRAY_RESTART`,
  `R39_IMAGE_SINGBOX_ATOMIC_REPLACE`, `R39_IMAGE_SINGBOX_RESTART` —
  **PASS**.
- `R39_YOUTUBE_SAME_CONTEXT`, `R39_YOUTUBE_NEW_WAN`,
  `R39_YOUTUBE_POLICY_RACE` — **PASS**.
- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID.

## §4 Штатный шлюз

- Xray: `EXECSTART=STANDARD`, `EXECSTART_SOURCE=ARGV0`,
  `SOURCE=INSTALLED_ONLY`, ключ стабилен — **`R39_HOST_XRAY=PASS`**.
- sing-box: активный слот **`blue`**, `EXECSTART=STANDARD`,
  `EXECSTART_SOURCE=EXECSTART_PID`, `SOURCE=INSTALLED_ONLY`, ключ
  стабилен — **`R39_HOST_SINGBOX=PASS`**.
- Состояния и PID пяти юнитов до и после совпали —
  `R39_HOST_FIELDS_MATCH`.

## §5 Три прогона R16 и регрессии

- `R16_REGION_ROUTE_1/2/3` — **PASS**; в каждом `ALTERNATIVE`,
  `HELD_STREAM=RETAINED`, `CLOSE_TRANSPORT=EOF`, `CLOSED`, `RECOVERY`.
- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.

## §6 Готовность M3

- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Публичное видео — **NOT_RUN**.
- Смена рабочего WAN и поколений — **NOT_RUN**.
- Штатное дренирование — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Замер привязан к служебному входу и маршруту**: проба идёт только
   через свой вход и свой выход, второй источник не получает запросов;
   смена правила в полёте учитывает байты, но не сохраняет результат.
2. **Чужой выход распознан**: контрольный запрос действительно доходит
   до второго источника, но планировщик не использует этот вход для
   YouTube, запись и закрепление сохраняются.
3. **Регрессии зелёные**: ExecStart (включая `pid=0` через ARGV0),
   образы, YouTube, мост, три R16 (EOF), rotation/certificate/api.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `PROBE_ROUTE_CONTRACTS.log`,
  `EXECSTART_CONTRACTS.log`, `BRIDGE_SLOT_CONTRACTS.log`,
  `R39_CONTEXT.log`, `SUBSCRIPTION_YOUTUBE.log`,
  `WATCHDOG_CONTRACTS.log`, `probe-route.log`, `user-execstart.log`,
  `images.log`, `youtube-probe.log`, `bridge.log`,
  `region-route-1/2/3.log`, `rotation.log`, `certificate.log`,
  `api-switch.log`, `xray-version.txt`, `singbox-version.log`,
  `before.txt`/`after.txt`, префиксы сценариев и бандл — в приватном
  каталоге прогона 0700 на машине.
