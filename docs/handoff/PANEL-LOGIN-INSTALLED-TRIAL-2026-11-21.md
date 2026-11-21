# ThinkCentre — временная приёмка одноразового входа на установленной панели

**Ubuntu 24.04 LTS.** Flash сама запускает проверки, следит за
восстановлением и автоматически публикует отчёт. Если недоступны
терминал, сессия панели или sudo, запроси доступ и продолжи сама.
Изменения проверяются во временной установке пяти файлов панели.
Скрипт перезапускает `xgw.service` для загрузки и возврата этих файлов
и проверяет, что Xray сохранил исходный PID.

На отдельной панели уже подтверждены браузер, CLI, Qt и восстановление
со старой закладки. Репликация двух отказов cli-install показала
устаревший текст ожидаемой подсказки и захват журнала за пределами
обработчиков логгера XGW. Оба ожидания исправлены. В этом проходе
проверяются CLI и HTTP реально установленного приложения до
временной установки, с кандидатом и после отката.
[Отчёт лаборатории](../reports/2026-11-21T122428Z_panel-one-time-login.md)

## 1. Запуск

Выполни весь блок в Bash из checkout XGW как пользователь панели
в доступное окно перезапуска службы. Если pytest установлен
в отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
При необходимости подтверди sudo через `sudo -v` в интерактивном
терминале и проверь `sudo -n true`. Запиши `PRETTY_NAME` и ядро.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=52d57a533829bdd71592bdf2824ff7ea54e39abb
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-panel-login-source.XXXXXXXX")
SRC="$WORK/source"
printf 'Private test directory: %s\n' "$WORK"
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" worktree add --detach "$SRC" "$CODE"
trap 'git -C "$REPO" worktree remove "$SRC"' EXIT
cd "$SRC"
timeout -k 3 180 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
  -o addopts='' -p no:cacheprovider -q tests/test_ops.py tests/test_install.py \
  -k 'panel or gui_login' | tee "$WORK/contracts.out"
bash docs/helpers/t11_panel_login_trial.sh "$CODE"
BASH
```

Скрипт выводит путь отдельного приватного каталога испытания.
Он проверяет исходный режим, текущие SHA пяти файлов относительно
`08d31ee`, старую схему входа, HTTPS через штатный VPN и отсутствие
другого прогона. Установщик проверяет хэши до применения. При
несовпадении базы или занятости шлюза укажи блокер из файла этапа.

Снимки и копии лежат в принадлежащих root каталогах.
Таймер `xgw-panel-login-rollback.timer` на 20 минут вооружается до
применения. Скрипт запускает откат при штатном выходе и при ошибке
после постановки таймера. После подтверждения исходных файлов
и старого поведения входа таймер снимается.

## 2. Что проверить и записать

| Проверка | Критерий |
|---|---|
| `CONTRACTS` | Код 0 у среза cli-install. Запиши passed/failed/skipped. При отказе до установки публикуй результат группы. |
| `BASELINE` | Исходные файлы совпадают с базой. off/off fresh/matched, обе службы активны, контроль HTTPS 200. Старый URL отвечает 303 с cookie, имеющаяся сессия получает 200. |
| `CANDIDATE` | Таймер активен и пять файлов совпадают с кандидатом. `candidate-auth` возвращает `ok=true`. Реальная команда `xgw panel` выдаёт действующий одноразовый код. Старый URL даёт 303 без новой cookie, сессия открывает API. HEAD не расходует код, повторный GET получает 403. Чужие Host/Origin и POST без сессии отклоняются. |
| `RESTORE` | Коды 0 у rollback, restored-files, restored-status, restored-auth и cancel-timer. Три проверки SHA подтверждают сохранение настроек и ключа панели. HTTPS 200 после возврата, PID Xray совпадает с исходным. |

В отчёте публикуй имена проверок и их коды. Если не удалось
подтвердить откат, прочитай состояние таймера и служб, дождись
срабатывания уже поставленного таймера и зафиксируй его результат.
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-login-installed-trial.md"
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
