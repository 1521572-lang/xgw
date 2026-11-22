# ThinkCentre — разбор предупреждения LEAK после снятия pin

**Ubuntu 24.04 LTS.** Flash сама запускает подготовленный
сценарий и автоматически публикует один обезличенный отчёт.
При недоступности терминала, sudo или GitHub запроси доступ.
Код и команды подготовил Codex.

Диалог временного закрепления доставлен в установленный GUI.
Во время ручной проверки слепой клик в отдельном модальном окне
закрепил сервер. При возврате автовыбора был сигнал LEAK.
Исходные настройки и PID сохранились, HTTPS после восстановления
дал 200. Требуется выделить события этого интервала и оценить,
какой путь подтверждают исходные данные.
[Отчёт установки](../reports/2026-11-21T234507Z_gui-server-pin-deploy.md)

## 1. Разбор и контракты

Используй терминал. Выполни `sudo -v`. При отдельном окружении
pytest укажи абсолютный `XGW_TEST_PYTHON`. Команда читает
сохранённые события SQLite в режиме ro. Прогоны pytest используют
фикстуры. Повторное закрепление и установка кандидата отсутствуют
в этом задании.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=d63df89335fa4623c2b9ac317637f4a5124db626
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-home-exit-incident.XXXXXXXX")
git archive "$CODE" src/xgw docs/helpers/leak_cause_check.py \
  tests/links.py tests/test_daemon.py tests/test_leak_incident.py | tar -x -C "$D"
printf 'PINNED %s | %s\n' "$CODE" "$PRETTY_NAME"
sudo -n true
services() {
  local unit pid
  for unit in xgw.service xgw-xray.service; do
    pid=$(systemctl show "$unit" -p MainPID --value) || return 2
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done
}
before=$(services)
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.sha256"
incident_rc=0
git show "$CODE:docs/helpers/leak_cause_check.py" |
  sudo -n /usr/bin/timeout -k 3 15 /usr/bin/python3 -I -B - incident \
    '2026-11-22T02:20:00+03:00' '2026-11-22T02:45:00+03:00' |
  tee "$D/timeline.txt" || incident_rc=$?
test_rc=0
timeout -k 3 60 env "PYTHONPATH=$D/src:$D/tests" "$PY" -B -P -m pytest -p no:cacheprovider -q \
  "$D/tests/test_leak_incident.py" "$D/tests/test_daemon.py" \
  -k 'incident or home_exit_without_route_evidence or leak_reports_success or server_exiting_at_home' || test_rc=$?
printf 'HOME_EXIT_RESULT incident_rc=%s test_rc=%s\n' "$incident_rc" "$test_rc"
[[ $(services) == "$before" ]]
sudo -n sha256sum --check --status "$D/settings.sha256"
printf 'INCIDENT_GATEWAY_UNCHANGED\n'
(( incident_rc == 0 && test_rc == 0 ))
BASH
~~~

## 2. Что фиксировать

Запиши результаты семи контрактов и обезличенные строки
`INCIDENT_EVENT`. `offset_s` отсчитывается от 02:20 МСК.

| Метка | Интерпретация |
|---|---|
| pin_set, pin_released | Зафиксированные действия закрепления и возврата. |
| home_exit_alert, degraded, healthy | Переходы состояния watchdog. |
| pinned, own_exit | Диагностика указала выбранный сервер с выходом в домашнюю страну. |
| legacy_ambiguous | Старый текст совместим с расхождением проб и со сбоем пробы через Xray. Путь остаётся UNCONFIRMED. |
| capture_event, apply, rotation | Соседние события перехвата, применения и замены. Указывай порядок и время, установление причины требует прямого свидетельства. |

Если окно пусто, отметь NO_RETAINED_EVENTS. При сохранённой записи
пакетного пути того же интервала укажи её агрегированные выводы
отдельно. При одних штатных событиях отрази доступный уровень
доказательства в отчёте. Файлы базы, исходный журнал, адреса и теги
оставь на машине.

В следующих проверках GUI используй клиент с блокировкой записи
для просмотра и отмены. Модальный диалог может быть отдельным
X-окном. Сначала определи и сними именно его, затем закрой Esc.
При отсутствии снимка останови GUI-действия.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-home-exit-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_home-exit-incident.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre home-country alert after unpin'
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
