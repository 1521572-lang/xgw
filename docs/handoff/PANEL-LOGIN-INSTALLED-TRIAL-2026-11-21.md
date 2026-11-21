# ThinkCentre — временная приёмка одноразового входа на установленной панели, r2

**Ubuntu 24.04 LTS.** Flash сама запускает проверки, следит за
восстановлением и автоматически публикует отчёт. Если недоступны
терминал, сессия панели или sudo, запроси доступ и продолжи сама.
Изменения проверяются во временной установке трёх модулей Python
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
В r2 скрипт использует `ad81542` для CLI, `08d31ee` для остальных
четырёх файлов и выводит отдельный результат сверки каждого файла.
[Отчёт r1](../reports/2026-11-21T123845Z_panel-login-installed-trial.md)

## 1. Запуск

Выполни весь блок в Bash из checkout XGW как пользователь панели
в доступное окно перезапуска службы. При необходимости подтверди
sudo через `sudo -v` в интерактивном терминале и проверь
`sudo -n true`. Запиши `PRETTY_NAME` и ядро.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=61ddcda9699b6ab0b418e8783aec94b89a9afa30
PROVEN=52d57a533829bdd71592bdf2824ff7ea54e39abb
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-panel-login-source.XXXXXXXX")
SRC="$WORK/source"
printf 'Private test directory: %s\n' "$WORK"
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$PROVEN" "$CODE"
git -C "$REPO" diff --quiet "$PROVEN" "$CODE" -- src/xgw tests \
  docs/helpers/desync_batch1_install.py docs/helpers/t11_panel_login_check.py
printf 'CONTRACTS_VERIFIED_FROM_R1\n'
git -C "$REPO" worktree add --detach "$SRC" "$CODE"
trap 'git -C "$REPO" worktree remove "$SRC"' EXIT
cd "$SRC"
bash -n docs/helpers/t11_panel_login_trial.sh
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
| `install.py`, `watch/panel.py`, `ui/login.html`, `ui/app.css` | `08d31ee` |

Снимки и копии лежат в принадлежащих root каталогах.
Таймер `xgw-panel-login-rollback.timer` на 20 минут вооружается до
применения. Скрипт запускает откат при штатном выходе и при ошибке
после постановки таймера. После подтверждения исходных файлов
и старого поведения входа таймер снимается.

## 2. Что проверить и записать

| Проверка | Критерий |
|---|---|
| `CONTRACTS` | `CONTRACTS_VERIFIED_FROM_R1`. Запиши 12/12 по отчёту r1 и результат проверки идентичности кода и тестов. |
| `BASELINE` | Исходные файлы совпадают с базой. off/off fresh/matched, обе службы активны, контроль HTTPS 200. Старый URL отвечает 303 с cookie, имеющаяся сессия получает 200. |
| `CANDIDATE` | Таймер активен и пять файлов совпадают с кандидатом. `candidate-auth` возвращает `ok=true`. Реальная команда `xgw panel` выдаёт действующий одноразовый код. Старый URL даёт 303 без новой cookie, сессия открывает API. HEAD не расходует код, повторный GET получает 403. Чужие Host/Origin и POST без сессии отклоняются. |
| `RESTORE` | Коды 0 у rollback, restored-files, restored-status, restored-auth и cancel-timer. SHA трёх файлов настроек и ключа панели совпадают с исходными. HTTPS 200 после возврата, PID Xray совпадает с исходным. |

В отчёте публикуй имена проверок и их коды. Если не удалось
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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-login-installed-trial-r2.md"
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
