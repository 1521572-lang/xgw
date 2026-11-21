# ThinkCentre · временная приёмка одноразового входа на установленной панели, r2 — 2026-11-21

- RESULT: **CONTRACTS = PASS (проверены в r1: 12/12; в r2 подтверждено
  `diff --quiet` PROVEN→CODE без изменения src/tests/helpers),
  BASELINE = PASS (смешанная база r2 совпала пофайлово: cli.py =
  `ad81542`, остальные = `08d31ee`; старая схема входа 303+cookie,
  сессия 200), CANDIDATE = FAIL на auth-проверке (транзиент сразу после
  рестарта службы), RESTORE = подтверждён внештатным таймером**:
  автоматический откат сработал (rollback rc=0, файлы/SHA/Xray PID/
  HTTPS восстановлены), итоговая auth-проверка вручную — ok=true в обеих
  фазах; оставшийся взведённым таймер сработал в 16:06:53 — «rollback:
  complete», сервис rc=0. Финал: файлы = смешанной базе, обе службы
  active, off/off fresh/matched, HTTPS 200, старая схема входа работает.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; кандидат `61ddcda…` (проверки —
  из `52d57a5…`, PROVEN), базы `08d31ee…` + cli `ad81542…`.

## §1 CONTRACTS = PASS

- В r2 контракты не перезапускались: блок проверил
  `git diff --quiet PROVEN CODE -- src/xgw tests desync_batch1_install.py
  t11_panel_login_check.py` → **CONTRACTS_VERIFIED_FROM_R1** (12/12
  из r1), плюс `bash -n` на скрипт испытания.

## §2 BASELINE = PASS

| Шаг | rc |
| --- | --- |
| status-before / https-before / settings-before / xray-before | 0 / 0 / 0 / 0 |
| baseline-files (смешанная база, пофайлово) | 0 — cli.py=ad81542, install.py/panel.py=08d31ee, ui/*=08d31ee |
| stage / baseline-auth (старая схема: 303+cookie, сессия 200) | 0 / 0 |

- Отдельный результат сверки каждого файла сработал: r2 корректно
  учёл, что установленный `cli.py` старее `08d31ee`.

## §3 CANDIDATE = FAIL (транзиент auth-проверки после рестарта)

| Шаг | rc |
| --- | --- |
| arm-timer (20м) / timer-active / apply / candidate-files / candidate-status | 0 / 0 / 0 / 0 / 0 |
| **candidate-auth** | **2** — `{"ok": false, "phase": "candidate", "failed": "request_or_config"}` |

- Установка пяти файлов (3 модуля Python + 2 веб-ресурса) прошла,
  статус после рестарта fresh/matched; auth-проверка упала через ~9с
  после рестарта xgw.service общим исключением (OSError-класс) на первом
  HTTP-запросе к 127.0.0.1:8781.
- Диагностика: **та же проверка вручную на восстановленной панели
  проходит сейчас в обеих фазах** (baseline ok=true, restored ok=true) —
  отказ транзиентный. Причина: `wait_status` опрашивает desync event
  socket (`xgw.desync.client status`), который готов раньше HTTP-листенера
  панели; чекер делает один запрос без повторов. Новый CLI (`login_link`)
  из-за раннего падения не исполнялся — живая проверка одноразовой
  ссылки на установленной панели осталась за следующим прогоном.

## §4 RESTORE — подтверждён внештатным таймером

| Шаг | rc |
| --- | --- |
| rollback (автоматический) | 0 |
| restored-files (пофайлово = смешанной базе) | 0 |
| restored-status | 0 |
| **restored-auth** | **2** — тот же транзиент через ~10с после рестарта |
| restored-settings / settings-unchanged | 0 / 0 (SHA идентичны) |
| restored-xray / xray-unchanged | 0 / 0 (PID Xray сохранён) |
| restored-https | 0 (200) |
| cancel-timer | не выполнялся (ветка остановлена на restored-auth) |

- По ТЗ таймер оставлен взведённым и **сработал в 16:06:53**:
  `rollback: complete`, сервис rc=0, таймер inactive/dead. Финальная
  сверка после срабатывания: cli.py=`ad81542`, install.py/panel.py=
  `08d31ee`, ui-файлы на месте; обе службы active; off/off fresh/matched;
  auth-проверка restored **ok=true** вручную; HTTPS 200.

## §5 Вердикты

| Проверка | Итог |
| --- | --- |
| CONTRACTS | PASS |
| BASELINE | PASS |
| CANDIDATE | FAIL — транзиент auth-проверки сразу после рестарта (HTTP-листенер) |
| RESTORE | Подтверждён внештатным таймером + ручной сверкой финала |

## Наблюдения для Codex

1. **Смешанная база r2 сработала** — пофайловые match/mismatch строки,
   `cli.py=ad81542` учтён; r1-замечание закрыто.
2. **Гонка «event socket готов раньше HTTP-листенера»**: `wait_status`
   (`client status`) проходит до готовности HTTP-порта панели, чекер
   одноразовый. Предлагаю: (а) в `wait_status` добавить опрос
   `GET /api/state` с ожиданием 401 (до 24с), либо (б) чекеру — 3–4
   повтора первого запроса с паузой 1с. Без этого каждый прогон с
   рестартом будет лотереей на фазах candidate/restored-auth.
3. **cancel-timer вне ветки успеха**: отказ restored-auth оставил таймер
   взведённым (сработал штатно и безвредно). Можно переносить
   cancel-timer в finish() — но текущее поведение также безопасно
   (идемпотентный rollback как финальный предохранитель).
4. Живая проверка одноразовой ссылки на установленной панели (новый CLI
   + HTTP 303/403-цепочка) остаётся неподтверждённой — следующий прогон
   после починки гонки дойдёт до неё без других изменений.
- Publication commit: `c8a8701c3bb9d86f5eafab839691e9e80372f831` (a8df41b → c8a8701, ancestor verified).
