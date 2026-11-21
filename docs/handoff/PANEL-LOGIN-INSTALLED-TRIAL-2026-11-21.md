# ThinkCentre — холодный старт панели с фоновым GeoIP, r5

**Ubuntu 24.04 LTS.** Flash сама запускает проверки, следит за
восстановлением и автоматически публикует отчёт. Если недоступны
терминал, сессия панели или sudo, запроси доступ и продолжи сама.
Изменения проверяются во временной установке пяти модулей Python
и двух веб-ресурсов.
Скрипт перезапускает `xgw.service` для загрузки и возврата этих файлов
и проверяет, что Xray сохранил исходный PID.

На отдельной панели уже подтверждены браузер, CLI, Qt и восстановление
со старой закладки. Репликация двух отказов cli-install показала
устаревший текст ожидаемой подсказки и захват журнала за пределами
обработчиков логгера XGW. Оба ожидания исправлены. В этом проходе
проверяются CLI и HTTP реально установленного приложения до
временной установки, с кандидатом и после отката.
[Отчёт лаборатории](../reports/2026-11-21T122428Z_panel-one-time-login.md)

В r1 двенадцать тестов cli-install прошли. До запуска таймера
сверка остановилась на `cli.py`. Установленный файл соответствует
`ad81542`. Отличие в `08d31ee` — строка справки про Ubuntu.
В r2 смешанная база прошла полную сверку и кандидат был временно
установлен. Проверки HTTP после запуска кандидата и после возврата
завершились общим кодом `request_or_config`. Одноразовый вход на
установленной панели остаётся открытым. Исходные файлы, настройки,
HTTPS и PID Xray восстановлены. Таймер выполнил дополнительный откат.
[Отчёт r1](../reports/2026-11-21T123845Z_panel-login-installed-trial.md)
· [Отчёт r2](../reports/2026-11-21T130826Z_panel-login-installed-trial.md)

В r3 анонимный `GET /api/state` получал 401 сразу после открытия
порта. Запрос с действующей cookie на кандидате и возвращённой
базе попадал в окно задержки. В замере после рестарта первый
ответ 200 появился примерно через 23 секунды. Таймер после
отката снят штатно. Новый проход измеряет первый авторизованный
запрос и пишет длительности этапов сборки ответа.
[Отчёт r3](../reports/2026-11-21T132112Z_panel-login-installed-trial-r3.md)

В r4 одноразовый вход и возврат исходных файлов прошли.
Первый авторизованный ответ кандидата занял 16 843 мс.
В замере сборки состояния GeoIP занял 10 898 из 11 413 мс.
После входа ответ занял 87 мс. В r5 индекс строится фоново.
Первый запрос отдаёт серверы, страны добавляются при следующем опросе
после готовности текущего индекса.
[Отчёт r4](../reports/2026-11-21T133451Z_panel-login-installed-trial-r4.md)

## 1. Запуск

Выполни весь блок в Bash из checkout XGW как пользователь панели
в доступное окно перезапуска службы. При необходимости подтверди
sudo через `sudo -v` в интерактивном терминале и проверь
`sudo -n true`. Запиши `PRETTY_NAME` и ядро.
Если pytest установлен в отдельном окружении, задай абсолютный
`XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=87f523364474d4062b7228533751170d738756bb
PROVEN=f58ab0c702540fc10cd8ba31125a4748d5294efe
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-panel-login-source.XXXXXXXX")
SRC="$WORK/source"
printf 'Private test directory: %s\n' "$WORK"
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$PROVEN" "$CODE"
git -C "$REPO" diff --quiet "$PROVEN" "$CODE" -- src/xgw tests \
  ':!src/xgw/geodat.py' ':!src/xgw/watch/server_geo.py' \
  ':!tests/test_geodat.py' ':!tests/test_gui_server_data.py' ':!tests/test_panel.py'
printf 'LOGIN_SOURCE_VERIFIED_FROM_R4\n'
git -C "$REPO" worktree add --detach "$SRC" "$CODE"
trap 'git -C "$REPO" worktree remove "$SRC"' EXIT
cd "$SRC"
bash -n docs/helpers/t11_panel_login_trial.sh
timeout -k 4 300 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
  -o addopts='' -p no:cacheprovider -q tests/test_t11_panel_login_check.py \
  tests/test_geodat.py tests/test_gui_server_data.py tests/test_panel.py \
  tests/test_tailscale_t2.py tests/test_appapi.py \
  | tee "$WORK/panel-tests.out"
bash docs/helpers/t11_panel_login_trial.sh "$CODE"
BASH
```

Скрипт выводит путь отдельного приватного каталога испытания.
Он проверяет исходный режим, старую схему входа, HTTPS через штатный
VPN и отсутствие другого прогона. Установщик сверяет байты до
применения. При несовпадении базы укажи все строки `mismatch`
из `baseline-files.out` и SHA известных версий этих файлов,
если их удалось подтвердить. Публикуй имена файлов и коммиты Git.

| Файл | Ожидаемая база |
|---|---|
| `cli.py` | `ad81542` |
| `install.py`, `watch/panel.py`, `ui/login.html`, `ui/app.css`, `geodat.py`, `watch/server_geo.py` | `08d31ee` |

Снимки и копии лежат в принадлежащих root каталогах.
Таймер `xgw-panel-login-rollback.timer` на 20 минут вооружается до
применения. Скрипт запускает откат при штатном выходе и при ошибке
после постановки таймера. После подтверждения исходных файлов и
активной `xgw.service` таймер снимается. Затем фиксируется результат
HTTP-входа на возвращённой панели.

Чекер до 24 секунд ждёт HTTP 401 от `GET /api/state` без сессии.
Затем один авторизованный запрос может ждать до 40 секунд.
`first_state_ms` измеряет время до заголовков ответа 200.
Одноразовая ссылка выдаётся после этого ответа. Получение сессии
и проверка повтора выполняются по одному разу. `state_after_login_ms`
проверяет доступ к состоянию с только что выданной cookie.

Перед откатом скрипт выгружает до 30 строк `panel_state_timing`
в `candidate-timings.out`. Панель пишет длительности этапов в
миллисекундах для сборки состояния дольше секунды, до одной
записи в минуту на экземпляр. Для анализа сопоставь
`elapsed_ms` с `first_state_ms` и укажи самый долгий этап.
Если задержка не воспроизвелась, запиши измеренное время и
наличие записи. Сценарий ограничен двумя перезапусками скрипта.

`baseline-geo` и `candidate-geo` считают активные строки
с определённой страной. Если на базе есть такие строки, кандидат
ждёт появления хотя бы одной страны до 35 секунд. Если исходное
измерение недоступно или на базе ноль стран, зафиксируй
неподтверждённое появление стран отдельно от результатов входа
и времени ответа.

## 2. Что проверить и записать

| Проверка | Критерий |
|---|---|
| `CONTRACTS` | `LOGIN_SOURCE_VERIFIED_FROM_R4` и код 0 у набора GeoIP, панели, чекера, Tailscale и Android API. Запиши passed/failed/skipped. |
| `BASELINE` | Исходные файлы совпадают с базой. off/off fresh/matched, обе службы активны, контроль HTTPS 200. Старый URL отвечает 303 с cookie, имеющаяся сессия получает 200. |
| `CANDIDATE` | Таймер активен и семь файлов совпадают с кандидатом. `candidate-auth` возвращает `ok=true`. Реальная команда `xgw panel` выдаёт действующий одноразовый код и её cookie открывает `/api/state`. Старый URL даёт 303 без новой cookie, сессия открывает API. HEAD не расходует код, повторный GET получает 403. Чужие Host/Origin и POST без сессии отклоняются. |
| `TIMINGS` | `candidate-state-budget` подтверждает первый ответ не дольше 5 секунд. Запиши `first_state_ms` до установки, на кандидате и после отката. Для кандидата добавь `state_after_login_ms` и разбивку `panel_state_timing`, если есть. |
| `GEOIP` | Если на базе была хотя бы одна активная строка со страной, на кандидате появляется хотя бы одна такая строка. Запиши `live_rows`, `with_country` и число попыток без адресов и названий серверов. |
| `RESTORE` | Коды 0 у rollback, restored-files, restored-service и cancel-timer подтверждают возврат пакета и снятие таймера. Отдельно нужны restored-status, restored-auth, сохранение SHA трёх файлов настроек и ключа панели, HTTPS 200 и прежний PID Xray. |

В отчёте публикуй имена проверок и их коды. Для каждого `*-auth`
запиши число попыток и время из `http_ready` либо этап `failed`,
тип ошибки, `errno` или HTTP-статус при их наличии. Если не удалось
подтвердить откат, прочитай состояние таймера и служб. Если таймер
активен, дождись его срабатывания и зафиксируй результат.
При недоступном шлюзе запиши последний подтверждённый этап.
Для сбоя до установки используй вердикт `NOT_RUN` с причиной.
Проверь, что в конце `xgw.service` и `xgw-xray.service` активны,
а режим соответствует исходному.

## 3. Публикация

При любом исходе создай один обезличенный Markdown-отчёт и сама
выполни следующий блок из checkout. Укажи абсолютный путь к готовому
отчёту в `REPORT_SRC`. Включи SHA кандидата и базы, состояние
до и после и обезличенный код первой ошибки. URL входа, cookie,
токен, PID и хэши настроек оставь на машине. Верни ссылку на
проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-login-trial-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-login-installed-trial-r5.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "Report ThinkCentre installed panel login trial"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
BASH
```
