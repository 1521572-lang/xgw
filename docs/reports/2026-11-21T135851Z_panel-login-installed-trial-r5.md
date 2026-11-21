# ThinkCentre · холодный старт панели с фоновым GeoIP, r5 — 2026-11-21

- RESULT: **ПОЛНЫЙ УСПЕХ — все 41 этап rc=0. panel-набор кандидата
  151 passed / 1 skipped; BASELINE PASS (7 файлов смешанной базы,
  first_state_ms=167); CANDIDATE: фикс GeoIP подтверждён на
  установленной панели — первый авторизованный ответ
  `first_state_ms=1249` (бюджет 5с выдержан, было 16843), в сборке
  `geoip_ms=25` (было 10898); страны GeoIP появились фоново (66/66
  строк за 7 опросов по 2с); одноразовая ссылка снова принята живьём
  (`one_time_cli=true`, 403-классы на месте); RESTORE штатный
  (rollback/cancel-timer/restored-auth — все 0), restored-auth
  подтверждает: старая панель всё ещё first_state_ms=16471 —
  замедление локализовано в старом коде, кандидат его убрал.
  Финал: off/off fresh/matched, обе службы active, файлы = смешанной
  базе (7 файлов), таймеров нет, HTTPS 200.**
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; кандидат `87f5233…` (PROVEN
  `f58ab0c…`), базы `08d31ee…` + cli `ad81542…`.

## §1 Тесты

- panel-набор (чекер, geodat, gui_server_data, panel, tailscale_t2,
  appapi): **151 passed / 1 skipped** за 107с.
- Источник входа подтверждён от r4: `LOGIN_SOURCE_VERIFIED_FROM_R4`
  (diff --quiet по src/tests вне GeoIP-файлов).

## §2 Прогон (41 этап rc=0)

Контроли до (статус/https/settings/xray) → baseline-files (7 файлов:
cli=ad81542, install/panel/geodat/server_geo=08d31ee, ui-ресурсы) →
stage/baseline-auth/baseline-geo → таймер 20м → apply → candidate-files/
status/**auth**/https/settings/xray/**state-budget**/**geo**/timings →
rollback → restored-files/service/**cancel-timer**/status/**auth**/
settings/xray/https — все rc=0.

## §3 Ключевые измерения

| Замер | Значение | Комментарий |
| --- | --- | --- |
| candidate **first_state_ms** | **1249** | бюджет ≤5000 выполнен (r4: 16843) |
| candidate **geoip_ms** в panel_state_timing | **25** | r4: 10898 — шаг более не блокирует запрос |
| candidate elapsed_ms | 1176 | вся сборка <1.3с на холодном старте |
| candidate state_after_login_ms | 458 | тёплый путь |
| baseline first_state_ms | 167 | тёплая база до опыта |
| **restored first_state_ms** | **16471** | старая панель — замедление осталось на базе |
| baseline-geo | 66/66 строк со страной, 1 опрос | старый путь: страны в первом ответе |
| candidate-geo | **66/66 со страной, 7 опросов** | страны появляются фоново в пределах 35с |
| one_time_cli / reused / Host / Origin | true / 403 / 403 / 403 | цепочка входа воспроизведена |

- Поведение кандидата соответствует дизайну: первый запрос отдаёт
  серверы сразу (без стран), страны появляются после фоновой сборки
  индекса — пользователь видит панель мгновенно.

## §4 Финал

Таймер снят до auth-проверок; откат штатный; файлы = смешанной базе
(7 файлов), ui-ресурсы на месте; обе службы active; off/off
fresh/matched; PID Xray сохранён; HTTPS 200; таймеров нет.

## Наблюдения для Codex

1. **Фикс GeoIP принят по существу**: холодный первый ответ 1.25с
   (было 16.8с), geoip-шаг 25мс (было ~11с), страны догружаются фоном
   без потери данных (66/66). Сравнение restored (16.5с) против
   candidate (1.25с) на одном стенде в одном прогоне — чистая улика.
2. Приёмка T11 (одноразовый вход + GeoIP-старт) полностью закрыта:
   r4 (принятие ссылки) + r5 (неблокирующий GeoIP) на установленной
   панели.
3. Для будущих ТЗ: 7-файловый оверлей с пофайловой сверкой и
   mixed-baseline (cli=ad81542) работает штатно — шаблон готов.
4. 1 skip — штатный root-зависимый тест.
- Publication commit: `5c2fed1fb934c43006ca18d8b5b893d32afb9f3f` (90b77c9 → 5c2fed1, ancestor verified).
