# ThinkCentre · путь запущенного ядра из systemd ExecStart — 2026-11-27

- RESULT: **R39 EXECSTART — КОНТРАКТЫ И СЦЕНАРИИ PASS; У ШТАТНОГО XRAY
  ExecStart НЕ ПРИВЯЗАН К MainPID — `R39_HOST_XRAY=FAIL`.
  `R39_COMPILE=PASS`; `R16_CONTRACTS=PASS` — 250 PASSED (49,70 С);
  `EXECSTART_CONTRACTS=PASS` — 3 PASSED; `BRIDGE_SLOT_CONTRACTS=PASS` — 2
  PASSED; `R39_CONTEXT=PASS` — 234 PASSED (53,45 С); `SUBSCRIPTION_YOUTUBE`
  — 21 PASSED (46,25 С); `WATCHDOG_CONTRACTS` — 20 PASSED (17,59 С);
  ПРОПУСКОВ НЕТ. ПОЛЬЗОВАТЕЛЬСКИЙ ЮНИТ:
  `R39_EXECSTART_USER_PATH=PASS`, `R39_EXECSTART_INSTALLED_ONLY=PASS`,
  `R39_EXECSTART_USER_UNIT_CLEANUP=PASS`. ОБРАЗЫ — все четыре
  `R39_IMAGE_*` PASS; YouTube — все три `R39_YOUTUBE_*` PASS;
  `R39_BRIDGE_LOOPBACK=PASS`. ТРИ ПРОГОНА R16 — PASS (транспорт закрытия:
  EOF, EOF, RESET). ШТАТНЫЕ КЛЮЧИ: `R39_HOST_SINGBOX_SLOT=blue`,
  `EXECSTART=STANDARD`, `SOURCE=INSTALLED_ONLY`, `R39_HOST_SINGBOX=PASS`;
  `R39_HOST_XRAY=FAIL (ExecStart is not tied to MainPID)`,
  `R39_HOST_KEYS_FAILED`; `R39_HOST_FIELDS_MATCH`. РЕГРЕССИИ:
  `rotation`, `certificate`, `api-switch` — PASS. M3: СТАТУС СВЕЖИЙ,
  ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; systemd 255 (255.4-1ubuntu8.19); Python 3.12.3;
  pytest 7.4.4; amd64; ядра — **Xray 26.11.9** (676eaf6, go1.27.3) и
  **sing-box 1.14.4**; кандидат
  `8708e516c85a666fd2924a00e9a82c719eb0303f`; ТЗ — `231ab38`; база
  бандла — `9e4c025e`. Временная пользовательская служба создана с
  копией Xray, случайным именем и лимитом 60 с, затем остановлена.
  PID, абсолютные пути с хоста, хеши, конфиги и логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-systemd-execstart.bundle`: SHA-256 **OK**
  (`337775ae…`), `git bundle verify` **OK**, приём = кандидат
  `8708e516…`.
- `EXECSTART_CONTRACTS` — **3 passed**, 34 deselected: путь из описания
  запущенного ExecStart, различие загруженных байтов и отказ при гонке,
  чтение одного активного запуска.
- `BRIDGE_SLOT_CONTRACTS` — **2 passed**, 30 deselected.
- `R39_CONTEXT` — **234 passed** (53,45 с); `R16_CONTRACTS` — **250
  passed** (49,70 с); `SUBSCRIPTION_YOUTUBE` — **21 passed** (46,25 с);
  `WATCHDOG_CONTRACTS` — **20 passed** (17,59 с); пропусков нет.

## §2 Пользовательский юнит

| Метка | Итог |
| --- | --- |
| `R39_EXECSTART_USER_PATH` | **PASS** — реальный systemd запустил отдельную копию Xray из пути с пробелом; `measurement_runtime` вернул этот путь, ключ собран из поколения и обоих хешей |
| `R39_EXECSTART_INSTALLED_ONLY` | **PASS** — при запрете чтения образа ключ зависит только от файла ExecStart и поколения; правка «штатного» файла не меняет ключ, замена файла ExecStart меняет |
| `R39_EXECSTART_USER_UNIT_CLEANUP` | **PASS** — юнит остановлен и неактивен |

## §3 Образы, YouTube, мост

- `R39_IMAGE_XRAY_ATOMIC_REPLACE`, `R39_IMAGE_XRAY_RESTART`,
  `R39_IMAGE_SINGBOX_ATOMIC_REPLACE`, `R39_IMAGE_SINGBOX_RESTART` —
  **PASS**.
- `R39_YOUTUBE_SAME_CONTEXT`, `R39_YOUTUBE_NEW_WAN`,
  `R39_YOUTUBE_POLICY_RACE` — **PASS**.
- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID.

## §4 Штатный шлюз

- Активный слот sing-box из свежего статуса — **`blue`**;
  `R39_HOST_SINGBOX_EXECSTART=STANDARD` (путь совпадает со штатным),
  `SOURCE=INSTALLED_ONLY`, ключ стабилен —
  **`R39_HOST_SINGBOX=PASS`**.
- `R39_HOST_XRAY=FAIL (ExecStart is not tied to MainPID)`: у
  `xgw-xray.service` описание ExecStart содержит `pid=0`, а MainPID
  живой — по консервативной проверке путь исполняемого файла не
  подтверждён, замер по ExecStart отклонён. Причина — описание запуска
  не принадлежит текущему запуску (после `daemon-reload`); это штатное
  поведение проверки, зафиксировано как FAIL блока.
- Состояния и PID пяти юнитов (xgw, xray, legacy, blue, green) до и
  после совпали — `R39_HOST_FIELDS_MATCH`.

## §5 Три прогона R16

| Прогон | Переход | Удерживаемое | Транспорт закрытия | Закрытие | Восстановление |
| --- | --- | --- | --- | --- | --- |
| 1 | PASS | RETAINED | **EOF** | PASS | PASS |
| 2 | PASS | RETAINED | **EOF** | PASS | PASS |
| 3 | PASS | RETAINED | **RESET** | PASS | PASS |

- Все три `R16_REGION_ROUTE_*` — **PASS**; TCP reset в третьем прогоне
  допустим по ТЗ; отказ CONNECT и данные от выхода не наблюдались.

## §6 Регрессии и M3

- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Рабочее переключение WAN и поколений — **NOT_RUN**.
- Дренирование штатных потоков — **NOT_RUN**.
- Публичное видео — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Путь из ExecStart работает**: реальный systemd-юнит из пути с
   пробелом даёт корректный ключ; при запрете чтения образа ключ
   опирается только на файл ExecStart и поколение.
2. **Штатный Xray**: ExecStart не привязан к MainPID (`pid=0` после
   `daemon-reload`) — проверка консервативно отказывает; штатный ключ
   по файлу и поколению при этом строится, но путь запущенного образа
   не подтверждён. Стоит решить, нужно ли принимать `pid=0` при
   совпадении пути или требовать перезапуск/`daemon-reload`.
3. **Штатный sing-box** (`blue`, `STANDARD`, `INSTALLED_ONLY`) — PASS.
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
