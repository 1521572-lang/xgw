# ThinkCentre — скрытие вкладки и восстановление веб-панели, P2.10

**Ubuntu 24.04 LTS.** Flash сама запускает сценарий из графической
сессии XGW и автоматически публикует один обезличенный отчёт при
любом исходе. При недоступности терминала, sudo, рабочего стола
или GitHub запроси доступ и продолжи сама. Код и команды
подготовил Codex.

В P2.9 прошли все 33 этапа. Окно Qt получило дополнительный ответ
через 380 мс. Веб-черновик пережил обрыв связи и остался открытым
до отмены. Первый ответ после восстановления занял 30,8 с.
Встроенный браузер оставлял вкладку в состоянии visible.
[Отчёт P2.9](../reports/2026-11-21T193701Z_panel-qt-resume.md)

Кандидат реагирует на событие online сразу. Если GET уже идёт,
оно сохраняет один запрос на обновление после ответа.
Доступность панели подтверждается фактическим GET 200.
[Событие online](https://developer.mozilla.org/en-US/docs/Web/API/Window/online_event)

## 1. Запуск на рабочей машине

Используй обычный Chrome в новом графическом сеансе браузера.
`XGW_TEST_PYTHON` может указывать на абсолютный путь к Python из
окружения Playwright, которое уже использовалось на ThinkCentre.
Если используется установленный графический Chromium Playwright,
задай `XGW_BROWSER_CHANNEL=chromium`. Проверь sudo через `sudo -v`
и выполни блок сама. При задержке авторизации или закрытом
терминале сначала запроси доступ.

Сценарий создаёт свежий вход через штатный CLI. Графический
браузер запрашивает страницу, CSS и данные у установленной
панели. Только ответ на запрос `/zapret2.js` в тестовом
контексте подменяется файлом из закреплённого коммита.
Файлы установки и службы шлюза остаются прежними. Режим Offline
действует в тестовом браузере. Запросы записи сценарий блокирует.
[Активация вкладки](https://playwright.dev/python/docs/api/class-page#page-bring-to-front) · [Сетевой контекст](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-set-offline)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]
BR=integration/zapret2-batch1
CODE=70c2071ea910ea4857031221bb5b4329ad0551c3
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import playwright.sync_api'
sudo -n true
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-panel-web-resume.XXXXXXXX")
git archive "$CODE" src/xgw/ui/zapret2.js docs/helpers/panel_web_resume.py \
  docs/helpers/youtube_telemetry.py tests/test_zapret2_web_refresh.cjs | tar -x -C "$D"
printf 'PINNED %s | %s\n' "$CODE" "$PRETTY_NAME"
if command -v node >/dev/null && [[ $(node -p "process.versions.node.split('.')[0]") -ge 18 ]]; then
  node --test "$D/tests/test_zapret2_web_refresh.cjs"
  printf 'WEB_CONTRACTS_OK\n'
else
  printf 'WEB_CONTRACTS_NOT_AVAILABLE\n'
fi
gateway_pids() {
  local unit pid
  for unit in xgw.service xgw-xray.service; do
    pid=$(systemctl show "$unit" -p MainPID --value) || return 2
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done
}
PID_BEFORE=$(gateway_pids)
rc=0
env -u DEBUG -u PWDEBUG timeout -k 5 120 "$PY" -B "$D/docs/helpers/panel_web_resume.py" \
  "$D/src/xgw/ui/zapret2.js" --channel "${XGW_BROWSER_CHANNEL:-chrome}" || rc=$?
PID_AFTER=$(gateway_pids)
if [[ $PID_BEFORE == "$PID_AFTER" ]]; then
  printf 'WEB_SERVICES_UNCHANGED\n'
else
  printf 'WEB_SERVICE_PID_CHANGED\n'
  exit 2
fi
exit "$rc"
BASH
~~~

## 2. Критерии

| Признак | Что фиксировать |
|---|---|
| WEB_BROWSER | Версия реального графического браузера. |
| WEB_HIDDEN_GETS 0 | После реального переключения вкладки браузер подтвердил hidden. За следующие 30 с запросов обзора нет. Если среда снова не передаёт hidden, зафиксируй NOT_VERIFIABLE. |
| WEB_VISIBLE_OK | После возврата вкладка visible, получен новый 200, черновик сохранён. |
| WEB_OFFLINE_DRAFT_OK | Браузер подтвердил Offline, баннер обрыва виден, черновик открыт, отправка формы отключена. |
| WEB_ONLINE_GET_MS, WEB_ONLINE_HTTP_200_MS | GET начался в первые 3 с после Online. Запиши отдельно задержку до запроса и до 200, затем наличие черновика и исчезновение баннера. |
| WEB_UI04_OK, WEB_SERVICES_UNCHANGED | Один экземпляр скрипта загружен, попыток записи и ошибок страницы нет, черновик отменён, PID XGW и Xray совпали. |

Если шаг завершился ошибкой, укажи последний успешный признак и
код ошибки. Используй только числовые метрики и обезличенные
признаки. При доступном vision визуально сверь форму и баннеры
во время прогона. Сеансовые URL, коды входа и заголовки запросов
в отчёт не включай.

## 3. Автоматическая публикация

Укажи абсолютный путь к готовому отчёту в `REPORT_SRC`,
выполни блок и верни ссылку на опубликованный коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-web-resume-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-web-resume.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre browser resume and visibility acceptance'
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
