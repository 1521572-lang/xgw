# ThinkCentre · повтор моста R39 и закрытия маршрута R16 — 2026-11-27

- RESULT: **ПОВТОР УСПЕШЕН, ПРЕЖНИЕ СБОИ НЕ ВОСПРОИЗВЕЛИСЬ.
  `R39_COMPILE=PASS`; `BRIDGE_SLOT_CONTRACTS=PASS` — 2 PASSED (оба
  параметра, 30 DESELECTED); `R39_CONTEXT=PASS` — 233 PASSED (50,85 С);
  `R16_CONTRACTS=PASS` — 250 PASSED (46,82 С); `SUBSCRIPTION_YOUTUBE` —
  21 PASSED (44,11 С); `WATCHDOG_CONTRACTS` — 20 PASSED (17,64 С);
  ПРОПУСКОВ НЕТ. ОБРАЗЫ: все четыре `R39_IMAGE_*` PASS; YouTube — все три
  `R39_YOUTUBE_*` PASS; `R39_BRIDGE_LOOPBACK=PASS`. ТРИ ПРОГОНА
  ЗАКРЫТИЯ: `R16_REGION_ROUTE_1/2/3=PASS`, в каждом
  `ALTERNATIVE`, `HELD_STREAM=RETAINED`, `CLOSE_TRANSPORT=EOF`,
  `CLOSED`, `RECOVERY` — PASS. ШТАТНЫЕ КЛЮЧИ:
  `R39_HOST_SINGBOX_SLOT=blue`; `R39_HOST_XRAY_SOURCE=INSTALLED_ONLY`,
  `R39_HOST_XRAY=PASS`; `R39_HOST_SINGBOX_SOURCE=INSTALLED_ONLY`,
  `R39_HOST_SINGBOX=PASS`; `R39_HOST_FIELDS_MATCH`. РЕГРЕССИИ:
  `rotation`, `certificate`, `api-switch` — PASS. ГОТОВНОСТЬ M3:
  СТАТУС СВЕЖИЙ, ПРЕДПОСЫЛКИ НЕ ВЫПОЛНЕНЫ (`ready=false`).**
- ОС: Ubuntu 24.04.5 LTS; Python 3.12.3; pytest 7.4.4; amd64; ядра —
  **Xray 26.11.9** (676eaf6, go1.27.3) и **sing-box 1.14.4**; кандидат
  `b198caf11bb59d765616ce555fab7f276371885f`; ТЗ — `8436fd4e`; база
  бандла — `9e4c025e`. Копии ядер запускались отдельно, запросы —
  loopback; со штатной установки только чтение. PID, хеши, базы,
  конфиги и сырые логи остаются локально.

## §1 Бандл и контракты

- `xgw-freepool-r39-bridge-recheck.bundle`: SHA-256 **OK**
  (`5d97e625…`), `git bundle verify` **OK**, приём = кандидат
  `b198caf1…`.
- `R39_COMPILE=PASS`.
- `BRIDGE_SLOT_CONTRACTS` — **2 passed**, 30 deselected (2,55 с) — оба
  параметра `subscription` и `freepool`; фикстура сама задаёт
  `ActiveState`, PID, идентификатор запуска и образ, после `inactive`
  контекст пуст при любом состоянии служб хоста.
- `R39_CONTEXT` — **233 passed** (50,85 с), пропусков нет (прежние
  2 сбоя моста не воспроизвелись).
- `R16_CONTRACTS` — **250 passed** (46,82 с); `SUBSCRIPTION_YOUTUBE` —
  **21 passed**, 185 deselected (44,11 с); `WATCHDOG_CONTRACTS` —
  **20 passed** (17,64 с).

## §2 Штатный sing-box

- Из свежего статуса прочитан активный слот: **`R39_HOST_SINGBOX_SLOT=blue`**;
  ключ именно этого юнита стабилен.
- Оба ядра: `SOURCE=INSTALLED_ONLY` (образ процесса другого UID не
  читается) — штатный режим с файлом установки и поколением запуска;
  `R39_HOST_XRAY=PASS`, `R39_HOST_SINGBOX=PASS`.
- Состояния и PID пяти юнитов (xgw, xray, legacy, blue, green) до и
  после совпали — `R39_HOST_FIELDS_MATCH`.

## §3 Три прогона закрытия маршрута

| Прогон | Переход | Удерживаемое | Транспорт закрытия | Закрытие | Восстановление |
| --- | --- | --- | --- | --- | --- |
| 1 | PASS | RETAINED | **EOF** | PASS | PASS |
| 2 | PASS | RETAINED | **EOF** | PASS | PASS |
| 3 | PASS | RETAINED | **EOF** | PASS | PASS |

- `R16_REGION_ROUTE_1/2/3=PASS`; во всех трёх TCP reset **не
  наблюдался** — закрытие пришло как EOF после успешного HTTP CONNECT.

## §4 Образы, YouTube, мост

- `R39_IMAGE_XRAY_ATOMIC_REPLACE`, `R39_IMAGE_XRAY_RESTART`,
  `R39_IMAGE_SINGBOX_ATOMIC_REPLACE`, `R39_IMAGE_SINGBOX_RESTART` —
  **PASS**: идентичная замена сохраняет ключ, различие файлов меняет
  только отпечаток на диске при прежнем `/proc/PID/exe`, после
  перезапуска — новая копия и новое поколение.
- `R39_YOUTUBE_SAME_CONTEXT`, `R39_YOUTUBE_NEW_WAN`,
  `R39_YOUTUBE_POLICY_RACE` — **PASS**.
- `R39_BRIDGE_LOOPBACK=PASS` — 32-символьный ID.

## §5 Регрессии и M3

- `rotation`: `OK` → `CONNECT_FAIL` (download/http) → `OK` —
  `F13_ROTATION=PASS`; `certificate`: `OK` → `CERT_TIME_INVALID` →
  `OK` — `F13_CERTIFICATE=PASS`; `api-switch`:
  `F13_HELD_STREAM=RETAINED`, `F13_API_SWITCH_ROLLBACK=PASS`.
- `M3_PREFLIGHT`: `fresh=true`, `ready=false`; observe, устройств 0,
  живых 0.

## NOT_RUN

- Публичное видео — **NOT_RUN**.
- Смена рабочего WAN и поколений — **NOT_RUN**.
- Принудительное закрытие рабочих потоков — **NOT_RUN**.
- Суточный M3 — **NOT_RUN**.

## Наблюдения для Codex

1. **Изоляция контракта моста исправлена**: оба параметра проходят,
   фикстура задаёт состояние службы сама, активный `blue` на хосте
   больше не влияет.
2. **Штатный sing-box учтён по активному слоту**: `blue`, ключ стабилен
   в режиме `INSTALLED_ONLY`.
3. **Закрытие маршрута стабильно**: три прогона из трёх, транспорт
   закрытия — EOF, reset не наблюдался; переход, удержание и
   восстановление зелёные.
4. **M3 по предпосылкам не готов**; рабочий WAN и сутки — отдельное
   окно.

## Локальные материалы (не публикуются)

- `R16_CONTRACTS.log`, `BRIDGE_SLOT_CONTRACTS.log`, `R39_CONTEXT.log`,
  `SUBSCRIPTION_YOUTUBE.log`, `WATCHDOG_CONTRACTS.log`, `images.log`,
  `youtube-probe.log`, `bridge.log`, `region-route-1.log`,
  `region-route-2.log`, `region-route-3.log`, `rotation.log`,
  `certificate.log`, `api-switch.log`, `xray-version.txt`,
  `singbox-version.log`, `before.txt`/`after.txt`, префиксы сценариев и
  бандл — в приватном каталоге прогона 0700 на машине.
