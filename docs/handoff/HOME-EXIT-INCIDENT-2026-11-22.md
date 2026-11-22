# ThinkCentre — журнал закрепления серверов и повторная проверка LEAK (r2)

**Ubuntu 24.04 LTS.** Flash сама запускает подготовленный
сценарий и автоматически публикует один обезличенный отчёт.
При недоступности терминала, sudo или GitHub запроси доступ.
Код и команды подготовил Codex.

В первом проходе сводка показала 41 событие. Диагностика зафиксировала
домашний выход закреплённого сервера, затем домашний выход при автовыборе
и замену сервера. Отдельной записи пакетного пути за этот интервал
не сохранилось. Две одинаковые записи о снятии закрепления оставили
источник второй команды неизвестным. Семь контрактов прошли при
повторе из временного каталога. Первый прогон зависел от имени
каталога и по `-k incident` выбрал все 163 теста.
[Отчёт первого прохода](../reports/2026-11-22T115700Z_home-exit-incident.md)

## 1. Разбор и контракты

Используй терминал. Выполни `sudo -v`. При отдельном окружении
pytest укажи абсолютный `XGW_TEST_PYTHON`. SQLite открывается в
режиме ro. Контракты работают с временной базой, подменённым Xray
и локальным HTTP-сервером на свободном порту. Установленный XGW
используется для чтения состояния. Команды управления маршрутом
и установка кандидата в сценарий не входят.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=4a6636f2a7b2302b714436584c393731233cc6a0
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-home-exit-incident.XXXXXXXX")
git archive "$CODE" src/xgw pyproject.toml docs/helpers/leak_cause_check.py \
  tests/conftest.py tests/links.py tests/fakenet.py tests/fakexray.py tests/test_daemon.py \
  tests/test_daemon_main.py tests/test_cli_commands.py tests/test_panel.py \
  tests/test_leak_incident.py | tar -x -C "$D"
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
(
  cd "$D"
  timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "PYTHONPATH=$D/src:$D/tests" "$PY" -B -P -m pytest -o addopts= \
    --rootdir "$D" -p no:cacheprovider -q --tb=short \
    tests/test_leak_incident.py \
    tests/test_daemon.py::test_server_exiting_at_home_is_replaced_and_not_taken_back \
    tests/test_daemon.py::test_leak_reports_success_only_after_the_rules_are_confirmed \
    tests/test_daemon.py::test_home_exit_without_route_evidence_does_not_claim_bypass \
    tests/test_cli_commands.py::test_pin_and_unpin \
    tests/test_cli_commands.py::test_pin_api_error \
    tests/test_panel.py::test_pin_goes_through_the_same_code_as_the_command \
    tests/test_daemon.py::test_pin_expires_and_is_restored_after_apply \
    tests/test_daemon.py::test_pin_is_dropped_when_node_leaves_balancer \
    tests/test_daemon_main.py::test_main_is_released_when_no_member_answers
) || test_rc=$?
printf 'HOME_EXIT_RESULT incident_rc=%s test_rc=%s\n' "$incident_rc" "$test_rc"
[[ $(services) == "$before" ]]
sudo -n sha256sum --check --status "$D/settings.sha256"
printf 'INCIDENT_GATEWAY_UNCHANGED\n'
(( incident_rc == 0 && test_rc == 0 ))
BASH
~~~

## 2. Что фиксировать

Запиши SHA, версию ОС, ядра, Python и pytest, коды двух фаз и
`INCIDENT_GATEWAY_UNCHANGED`. Целевой итог — ровно 13 прошедших
тестов за один запуск, коды 0 и совпавшие PID и SHA настроек.
Первые семь контрактов повторяют проверку диагностики и экспорта.
Остальные шесть проверяют источник события CLI и панели,
повторный unpin как команду, ошибку API, снятие по таймеру,
исчезновение сервера и переходы автовыбора. При другом числе
тестов запиши исход как ошибку сценария.

Сопоставь обезличенные строки `INCIDENT_EVENT` с первым отчётом.
`offset_s` отсчитывается от 02:20 МСК.

| Метка | Интерпретация |
|---|---|
| pin_set, pin_released без source | Старая запись о закреплении или снятии. Канал действия неизвестен. |
| pin_set, unpin_requested с source | Принятая Xray команда CLI или панели. Повторная команда возврата учитывается как команда. |
| pin_expired, pin_removed, pin_suspended, pin_resumed | События watchdog. |
| main_override_set, main_override_released | Подтверждённый вызов API Xray из автовыбора. |
| home_exit_alert, degraded, healthy | Переходы состояния watchdog. |
| pinned, own_exit | Диагностика указала выбранный сервер с выходом в домашнюю страну. |
| legacy_ambiguous | Старый текст совместим с расхождением проб и со сбоем пробы через Xray. Путь остаётся UNCONFIRMED. |
| capture_event, apply, rotation | Соседние события перехвата, применения и замены. Указывай порядок и время, установление причины требует прямого свидетельства. |

Если окно пусто, отметь NO_RETAINED_EVENTS. Источники нового формата
проверяются на фикстурах. У старых событий пропускается поле `source`.
По событиям можно описать результат диагностики watchdog. Для
отдельного подтверждения маршрута требуется запись пакетного пути
того же интервала. Файлы базы, журнал, адреса и теги оставь на машине.

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
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_home-exit-incident-r2.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre pin audit and isolated home-exit contracts'
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
