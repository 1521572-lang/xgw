# ThinkCentre · вход на установленной панели и время сборки состояния, r4 — 2026-11-21

- RESULT: **ПОЛНЫЙ УСПЕХ — все 38 этапов rc=0. CONTRACTS из r1 (12/12) +
  panel-тесты кандидата 139 passed / 1 skipped; BASELINE PASS (смешанная
  база, старая схема); CANDIDATE: пять файлов применены под таймером 20м,
  одноразовая ссылка проверена живьём на установленной панели —
  `one_time_cli=true`, повтор кода 403, чужой Host 403, чужой Origin 403;
  RESTORE: rollback rc=0, cancel-timer rc=0 (таймер снят до auth),
  restored-auth ok. ТЕЛО ЗАВИСАНИЯ НАЙДЕНО: `panel_state_timing`
  показывает `geoip_ms=10898` при elapsed_ms=11413 — сборка состояния
  блокируется шагом GeoIP ~11с на холодном старте (тёплый запрос 87мс);
  это и есть окно ~23с из r3**. Финал: off/off fresh/matched, обе службы
  active, файлы = смешанной базе, таймеров нет, HTTPS 200.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; кандидат `f58ab0c…` (PROVEN
  `52d57a5…`), базы `08d31ee…` + cli `ad81542…`.

## §1 Тесты

- readiness/panel-набор кандидата: **139 passed / 1 skipped** за 108с
  (test_t11_panel_login_check + test_panel + test_tailscale_t2 +
  test_appapi).

## §2 Прогон

| Шаг | rc |
| --- | --- |
| статус/https/settings/xray до + baseline-files (пофайлово) | 0 |
| stage / baseline-auth (старая схема, first_state_ms=190) | 0 / 0 |
| arm-timer / apply / candidate-files / candidate-status | 0 |
| **candidate-auth** | **0** — ок=true, вся цепочка |
| candidate-https/settings/-unchanged/xray/-unchanged/-timings | 0 |
| rollback / restored-files / restored-service / cancel-timer | 0 |
| restored-status / **restored-auth** / restored-settings | 0 / **0** / 0 |
| settings-unchanged / xray-unchanged / restored-https | 0 / 0 / 0 |

## §3 Одноразовая ссылка на установленной панели (живая)

| Поле | Значение |
| --- | --- |
| http_ready | 1 попытка, 0.006с — ожидание листенера сработало |
| **first_state_ms (candidate)** | **16843** — «холодный» запрос с cookie |
| **state_after_login_ms** | **87** — после выдачи сессии тёплый запрос |
| one_time_cli | true — реальная команда `xgw panel` выдала код |
| reused_code / foreign_host / foreign_origin | 403 / 403 / 403 |
| legacy (candidate) | 303 без выдачи cookie; сессия сохраняется |
| restored-auth | ок, first_state_ms=17589, legacy_login=true |

## §4 Тело зависания: panel_state_timing

Журнал кандидата (1 запись >1с за окно):

```
panel_state_timing elapsed_ms=11413 core_ms=18 capture_ms=149
geoip_ms=10898 catalog_ms=17 devices_events_ms=3 response_ms=135
tailscale_ms=185 phones_ms=3 zapret2_ms=4
```

- **geoip_ms=10898 — доминирующий член сборки состояния**: шаг GeoIP
  занимает ~11с на холодном старте; все остальные шаги — десятки-сотни мс.
- Это точно окно r3 (~23с): первый авторизованный запрос блокируется на
  GeoIP-шаге (после рестарта кеш/ресурс GeoIP холодный), последующие —
  тёплые (87мс). first_state_ms у кандидата (16843) и у старой панели
  (17589) согласуются: ~11с geoip + прочие шаги на холодном пути.
- baseline (не после рестарта): first_state_ms=190 — холодного пути нет.

## §5 Финал

Таймер снят до auth (структура r3), откат штатный: файлы = смешанной
базе (cli=ad81542, install/panel=08d31ee, ui-файлы на месте), обе службы
active, off/off fresh/matched, HTTPS 200, PID Xray сохранён, таймеров нет.

## Наблюдения для Codex

1. **Одноразовая ссылка принята на установленной панели end-to-end**:
   CLI → 303+cookie → повтор 403 → Host/Origin 403 → сессия живая.
   Приёмка Т11 на шлюзе завершена.
2. **Root cause зависания — шаг GeoIP в сборке состояния** (~11с холодный,
   87мс тёплый). Варианты: прогрев GeoIP при старте демона (фоновая
   первая сборка), кеш результата на диск, либо неблокирующий ответ
   (без geoip-поля, пока шаг не готов). После фикса окно ~23с исчезнет,
   и auth-проверки после рестарта станут мгновенными.
3. Инструментальная цепочка r4 (cold-wait 40с + panel_state_timing +
   пофайловые сверки) собрала всё за один прогон — можно фиксировать как
   шаблон для приёмок панели.
4. Небольшое замечание: 1 skip в panel-тестах — штатный (root-зависимый,
   как и в предыдущих группах).
- Publication commit: _заполняется при публикации_.
