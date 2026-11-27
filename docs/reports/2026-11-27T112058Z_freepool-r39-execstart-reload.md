# ThinkCentre · восстановление контекста ExecStart при pid=0 — 2026-11-27

- RESULT: **R39 EXECSTART RELOAD — PASS. `R39_COMPILE=PASS`;
  `EXECSTART_CONTRACTS=PASS` — 4 PASSED; `BRIDGE_SLOT_CONTRACTS=PASS` —
  2 PASSED; `R16_CONTRACTS=PASS` — 250 PASSED (48,42 С);
  `R39_CONTEXT=PASS` — 235 PASSED (54,10 С); `SUBSCRIPTION_YOUTUBE` —
  21 PASSED (46,53 С); `WATCHDOG_CONTRACTS` — 20 PASSED (15,92 С);
  ПРОПУСКОВ НЕТ. ПОЛЬЗОВАТЕЛЬСКИЙ ЮНИТ:
  `R39_EXECSTART_USER_PATH`, `R39_RELOAD_MATCHED_MAINPID`,
  `R39_RELOAD_CHANGED_PATH_REJECTED`, `R39_EXECSTART_INSTALLED_ONLY`,
  `R39_EXECSTART_USER_UNIT_CLEANUP` — PASS. ШТАТНЫЕ КЛЮЧИ:
  `R39_HOST_XRAY_EXECSTART=STANDARD`, `EXECSTART_SOURCE=ARGV0`,
  `SOURCE=INSTALLED_ONLY`, `R39_HOST_XRAY=PASS`;
  `R39_HOST_SINGBOX_SLOT=blue`, `EXECSTART=STANDARD`,
  `EXECSTART_SOURCE=EXECSTART_PID`, `SOURCE=INSTALLED_ONLY`,
  `R39_HOST_SINGBOX=PASS`; `R39_HOST_FIELDS_MATCH`. ОБРАЗЫ — все четыре
  PASS; YouTube — все три PASS; `R39_BRIDGE_LOOPBACK=PASS`.
  ТРИ ПРОГОНА R16 — PASS (транспорт закрытия: RESET, EOF, EOF).
  РЕГРЕССИИ: `rotation`, `certificate`, `api-switch` — PASS. M3:
  СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; systemd 255 (255.4-1ubuntu8.19); Python 3.12.3;
  pytest 7.4.4; amd64; ядра — **Xray 26.11.9** (676eaf6, go1.27.3) и
  **sing-box 1.14.4**; кандидат
  `d546299db3a779e86415cc2bd89ae33ba01e5572`; ТЗ — `94220a5`; база
  бандла — `9e4c025e`. Временная пользовательская служба — копия Xray со
  случайным именем и лимитом 60 с, затем остановлена; штатные юниты,
  конфиги и процессы только читались. Аргументы процессов, PID, полные
  пути, хеши и логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-execstart-reload.bundle`: SHA-256 **OK**
  (`7a347ced…`), `git bundle verify` **OK**, приём = кандидат
  `d546299d…`.
- `EXECSTART_CONTRACTS` — **4 passed**, 34 deselected: при `pid=0`
  совпадение с первым аргументом живого процесса даёт ключ; иное
  значение, другой положительный PID, исчезновение cmdline и смена
  времени старта отклоняют замер.
- `BRIDGE_SLOT_CONTRACTS` — **2 passed**, 30 deselected.
- `R16_CONTRACTS` — **250 passed** (48,42 с); `R39_CONTEXT` — **235
  passed** (54,10 с); `SUBSCRIPTION_YOUTUBE` — **21 passed** (46,53 с);
  `WATCHDOG_CONTRACTS` — **20 passed** (15,92 с); пропусков нет.

## §2 Пользовательский юнит и pid=0

| Метка | Итог |
| --- | --- |
| `R39_EXECSTART_USER_PATH` | **PASS** — реальный systemd, копия Xray из пути с пробелом, ключ из поколения и обоих хешей |
| `R39_RELOAD_MATCHED_MAINPID` | **PASS** — при искусственно обнулённом поле ExecStart (`pid=0`) путь подтверждён по первому аргументу живого процесса (ARGV0), ключ совпал с исходным |
| `R39_RELOAD_CHANGED_PATH_REJECTED` | **PASS** — при подставленном другом пути контекст не подтверждён, ключ отсутствует |
| `R39_EXECSTART_INSTALLED_ONLY` | **PASS** — при запрете чтения образа ключ зависит только от файла ExecStart и поколения |
| `R39_EXECSTART_USER_UNIT_CLEANUP` | **PASS** — юнит остановлен и неактивен |

## §3 Штатный шлюз

- Xray: `R39_HOST_XRAY_EXECSTART=STANDARD`, **`EXECSTART_SOURCE=ARGV0`** —
  штатный случай `pid=0`, путь подтверждён по живому процессу;
  `SOURCE=INSTALLED_ONLY`, ключ стабилен — **`R39_HOST_XRAY=PASS`**.
- sing-box: активный слот **`blue`**, `EXECSTART=STANDARD`,
  `EXECSTART_SOURCE=EXECSTART_PID`, `SOURCE=INSTALLED_ONLY`, ключ
  стабилен — **`R39_HOST_SINGBOX=PASS`**.
- Состояния и PID пяти юнитов до и после совпали —
  `R39_HOST_FIELDS_MATCH`.

## §4 Образы, YouTube, мост

- `R39_IMAGE_XRAY_ATOMIC_REPLACE`, `R39_IMAGE_XRAY_RESTART`,
  `R39_IMAGE_SINGBOX_ATOMIC_REPLACE`, `R39_IMAGE_SINGBOX_RESTART` —
  **PASS**.
- `R39_YOUTUBE_SAME_CONTEXT`, `R39_YOUTUBE_NEW_WAN`,
  `R39_YOUTUBE_POLICY_RACE` — **PASS**.
- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID.

## §5 Три прогона R16

| Прогон | Переход | Удерживаемое | Транспорт закрытия | Закрытие | Восстановление |
| --- | --- | --- | --- | --- | --- |
| 1 | PASS | RETAINED | **RESET** | PASS | PASS |
| 2 | PASS | RETAINED | **EOF** | PASS | PASS |
| 3 | PASS | RETAINED | **EOF** | PASS | PASS |

- Все три `R16_REGION_ROUTE_*` — **PASS**; reset и EOF допустимы по ТЗ,
  данные от выхода и отказ CONNECT не наблюдались.

## §6 Регрессии и M3

- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Смена рабочего WAN и поколений — **NOT_RUN**.
- Дренирование рабочих соединений — **NOT_RUN**.
- Публичное видео — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Случай `pid=0` закрыт**: путь подтверждается первым аргументом
   живого процесса, ключ совпадает; чужой путь и чужие значения
   отклоняются, смена времени старта и исчезновение cmdline — тоже.
2. **Штатный Xray теперь PASS**: `ARGV0`, `STANDARD`, `INSTALLED_ONLY`;
   штатный sing-box — `EXECSTART_PID`, `blue`, `INSTALLED_ONLY`, PASS.
3. **Регрессии зелёные**, три прогона R16 стабильны (RESET/EOF/EOF).
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `EXECSTART_CONTRACTS.log`,
  `BRIDGE_SLOT_CONTRACTS.log`, `R39_CONTEXT.log`,
  `SUBSCRIPTION_YOUTUBE.log`, `WATCHDOG_CONTRACTS.log`,
  `user-execstart.log`, `images.log`, `youtube-probe.log`, `bridge.log`,
  `region-route-1/2/3.log`, `rotation.log`, `certificate.log`,
  `api-switch.log`, `xray-version.txt`, `singbox-version.log`,
  `before.txt`/`after.txt`, временные копии ядер и бандл — в приватном
  каталоге прогона 0700 на машине.
