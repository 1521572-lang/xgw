# ThinkCentre — параллельное чтение короткого статуса zapret2, P2.8

**Ubuntu 24.04 LTS.** Flash сама запускает готовую проверку и автоматически
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, рабочей сессии панели или GitHub запроси доступ и
продолжи сама. Код и сценарий подготовил Codex. Проведи техническую
приёмку по шагам ниже.

В P2.7 r2 прошли все 32 этапа. Первый короткий запрос активировал
читателя за 747 мс. HTTP, CLI и Qt получили одинаковые пять полей.
Откат восстановил 17 файлов и права, PID Xray сохранился.
[Отчёт P2.7 r2](../reports/2026-11-21T180208Z_panel-read-summary-r2.md)

Кандидат P2.8 обслуживает до четырёх чтений IPC одновременно. При
занятых обработчиках новое соединение закрывается сразу, ошибка
читателя по-прежнему возвращается как 503. Проверка использует обычные
авторизованные запросы и неизменную политику off/off.

## 1. Запуск

В согласованное окно перезапуска панели войди в терминал из рабочей
сессии XGW и обнови допуск командой `sudo -v`. При отдельном окружении
pytest задай абсолютный `XGW_TEST_PYTHON`. Сценарий сверяет исходные
файлы с базой предыдущей приёмки, ставит независимый таймер отката
на 20 минут и временно устанавливает кандидат. При установке и
возврате перезапускается `xgw.service`.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=506bc24fb078c1c7eb2d8cc3aa434540eee89d29
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_panel_installed_trial.sh" | bash -s -- "$CODE"
BASH
~~~

## 2. Что зафиксировать

| Этап | Критерий |
|---|---|
| contracts | Все 24 контракта проходят. В их числе параллельные IPC-запросы с одноразовыми допусками, отказ при занятых обработчиках и успешное чтение после их освобождения. |
| helper-modes, stage-modes, prepare, timer-active | STAGE_MODES_OK дважды, BASELINE_MATCH 17, таймер активен до замены. cli.py сверяется с ad81542, desync/client.py с 3a00777, остальные файлы с 08d31ee. При baseline_mismatch запиши имена файлов и вердикт NOT_RUN. |
| ONE_TIME_CLI_OK, READER_DORMANT_OK, INSTALLED_STATUS_MATCH, READER_RUN_READONLY_OK | Одноразовый вход прошёл, отклонённые запросы оставили читателя неактивным, первый авторизованный запрос дал 200 и пять полей, совпадающих с полным обзором. Запиши cold_ms и подтверждение режима чтения /run. |
| PARALLEL_STATUS_OK | Четыре одновременных авторизованных GET вернули 200 и каждый дал тот же набор пяти полей. |
| candidate-session, candidate-cli-summary, candidate-qt | Штатная сессия сохранилась. CLI_SUMMARY_OK подтверждает пять полей. Запиши QT_NETWORK_OK или QT_NOT_AVAILABLE. |
| INSTALLED_READER_RECOVERED_OK | При остановке читателя короткий маршрут дал 503, полный обзор дал 200. После запуска короткий запрос дал 200, пять полей совпали, читатель получил новый PID, PID XGW сохранился. |
| candidate-same-xray, candidate-same-settings, candidate-https | PID Xray и настройки совпали с базой, HTTPS 200. |
| rollback, restored-http, restored-same-xray, restored-same-settings, restored-https, cancel-timer, STAGE_REMOVED | Исходные файлы и права вернулись. Короткий маршрут снова дал 404, полный обзор дал 200. PID Xray и настройки совпали, HTTPS 200. Таймер снят, временный каталог удалён. |

Запиши ОС, SHA кандидата, код завершения, результат каждого
обязательного этапа и итог отката. При ошибке укажи последний
успешный этап и код первой ошибки. Если проверка прервана,
проверь `xgw-panel-reader-rollback.timer` и дождись срабатывания,
если таймер активен. Публикуй только обезличенные результаты.

## 3. Автоматическая публикация

Укажи абсолютный путь к готовому отчёту в `REPORT_SRC`, сама выполни
блок и верни ссылку на опубликованный коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-parallel-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-parallel.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre parallel panel status acceptance'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
