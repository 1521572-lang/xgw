# ThinkCentre — короткий статус zapret2 на установленной панели, r2

**Ubuntu 24.04 LTS.** Flash сама выполняет готовый сценарий и
автоматически публикует один обезличенный отчёт при любом исходе.
При недоступности терминала, sudo, рабочей сессии панели или
GitHub запроси доступ и продолжи сама. Код подготовил Codex.

В P2.6 r2 прошёл 31 этап. Установленный читатель активировался
за 733 мс, Qt получил пять полей, после остановки читатель
запустился снова. Откат вернул файлы и права без смены PID Xray.
[Отчёт P2.6 r2](../reports/2026-11-21T173731Z_panel-read-installed-r2.md)

В первой попытке P2.7 прошли все 12 контрактов. Сценарий остановился
при сверке `desync/client.py`. Flash установила побайтовое совпадение
этого файла с `3a00777`. R2 использует подтверждённую ревизию для
этого файла. Прежние PID XGW и Xray и HTTPS 200 подтверждены.
[Первый отчёт P2.7](../reports/2026-11-21T175259Z_panel-read-summary.md)

В P2.7 короткий запрос использует ограниченное чтение снимка и
те же правила оценки актуальности и ревизии, что полный обзор.
Для него панель не читает SQLite и данные задания и не строит
сводку журнала. CLI предоставляет `status --summary` с пятью
полями. При 404 или 503 команда возвращает код 2 и
`isolated_status_unavailable`. Обычный `status` отдаёт полный обзор.

## 1. Запуск

Выполни блок как пользователь рабочей сессии XGW в окно перезапуска
панели. Подтверди sudo через `sudo -v`. Если pytest находится в
отдельном окружении, заранее задай абсолютный `XGW_TEST_PYTHON`.
Сценарий использует существующую сессию Qt, сверяет 17 файлов,
вооружает независимый таймер на 20 минут и временно заменяет нужные
файлы. Перезапускается `xgw.service`. Версии базы и процедура возврата
описаны в ТЗ P2.6. [Сценарий P2.6](PANEL-READ-INSTALLED-2026-11-21.md)

```bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=8c32072768c298844da061f44ce0c78483755440
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_installed_trial.sh" | bash -s -- "$CODE"
BASH
```

## 2. Что зафиксировать

| Этап | Критерий |
|---|---|
| `contracts` | Пройдены два контракта отката и десять контрактов короткого чтения и CLI. Они покрывают активное и выключенное состояние, истечение подтверждения, устаревший и отсутствующий снимок, несовпадение ревизии, недоступность читателя при 404 и 503. |
| `helper-modes`, `stage-modes`, `prepare`, `timer-active` | `STAGE_MODES_OK` дважды, `BASELINE_MATCH 17`, таймер активен до замены. `desync/client.py` сверяется с `3a00777`, `cli.py` с `ad81542`, остальные файлы с `08d31ee`. При `baseline_mismatch` запиши имена из вывода и вердикт `NOT_RUN`. |
| `ONE_TIME_CLI_OK`, `READER_DORMANT_OK`, `INSTALLED_STATUS_MATCH`, `READER_RUN_READONLY_OK` | Одноразовый вход прошёл, читатель активировался первым авторизованным запросом, пять полей равны полному обзору, `/run` только для чтения. Запиши `cold_ms` как замер активации. |
| `candidate-session`, `candidate-cli-summary`, `candidate-qt` | Обычный CLI и HTTP дают тот же снимок. Новый `status --summary` возвращает ровно пять полей и `CLI_SUMMARY_OK`. Запиши `QT_NETWORK_OK` или `QT_NOT_AVAILABLE`. |
| `INSTALLED_READER_RECOVERED_OK` | Остановка читателя дала 503 на коротком маршруте и 200 на полном обзоре. После запуска получен 200 с прежними полями, новым PID читателя и прежним PID XGW. |
| `rollback`, `restored-http`, `restored-same-xray`, `restored-same-settings`, `restored-https`, `cancel-timer`, `STAGE_REMOVED` | Исходные файлы и права возвращены, короткий маршрут снова 404, полный обзор 200, PID Xray и настройки совпали, HTTPS 200. Таймер остановлен, временный каталог удалён. |

При ошибке запиши последний успешный этап, код первой ошибки и
итог отката. При прерывании проверь таймер
`xgw-panel-reader-rollback.timer` и дождись его срабатывания,
если он активен. В отчёте публикуй только обезличенные результаты.

## 3. Автоматическая публикация

Укажи абсолютный путь к отчёту в `REPORT_SRC` и сама выполни блок.
Верни ссылку на проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-summary-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-summary-r2.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre compact zapret2 status acceptance r2'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
```
