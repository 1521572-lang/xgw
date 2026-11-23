# ThinkCentre — причины остановки воркера и повтор NFQUEUE, T01/T08/T11

**Ubuntu 24.04 LTS.** Flash самостоятельно выполняет готовые команды и
автоматически публикует один обезличенный отчёт при любом исходе.
При недоступности терминала, sudo или GitHub запроси доступ.

Веб-панель, HTTP и Qt прошли предыдущую проверку. Лаборатория
с многострочным правилом зафиксировала семь переполнений из восьми
датаграмм и ноль ошибок netlink. В закреплённой версии помощника
nftables 1.0.9 отклонил формат правила. Кандидат исправляет разметку
и отдельно сообщает об отсутствии `libnetfilter_queue.so.1`.
[Предыдущий отчёт](../reports/2026-11-22T235429Z_worker-queue-panel.md)

XGW добавляет в журнал ограниченный набор причин для завершившегося
воркера. При остановке он читает до восьми подходящих записей по имени
службы и идентификатору её запуска. При наличии сигнатуры фиксирует
отказ загрузки hostlist или ipset, фатальную ошибку Lua или наблюдавшееся
сообщение Lua. Последнее поле отражает наблюдение и само по себе не
устанавливает причину остановки. Сырой текст остаётся в системном
журнале. При отсутствии записи дополнительное событие не создаётся.
[Поля systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#LogExtraFields=)

## 1. Запуск

Выполни `sudo -v`. Если pytest установлен в отдельном окружении,
экспортируй абсолютный путь `XGW_TEST_PYTHON`. Для веб-контракта
нужен установленный Node.js, для переполнения — системный пакет
`libnetfilter-queue1`, который зафиксирован в предыдущем отчёте.
Если компонента нет, отрази недоступный этап и продолжи независимые
проверки.

Сценарий использует закреплённый checkout. Лаборатория очереди работает
в отдельном сетевом пространстве с loopback. Вторая лаборатория
запускает отдельную временную службу с `PrivateNetwork=yes` под
случайным именем, повторно используя её имя с новым идентификатором
запуска. Она проверяет реальные метки journald, сигнатуры отказов
списков и штатное сообщение закреплённого nfqws2 при ошибке
инициализации Lua. Оба контроля читают состояние рабочего шлюза
до и после.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'WORKER_QUEUE_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=c59ea35088887f6411ab9b922bbf09f4522f4483
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-worker-diag.XXXXXXXX")
printf 'WORKER_QUEUE_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"

fib() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
}
fib >"$D/fib.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"

contracts() {
  local label=$1 expected=$2
  shift 2
  if timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
      PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest \
      -o addopts= -p no:cacheprovider -q --tb=short "$@" >"$D/$label.out" 2>&1 &&
      grep -Eq "^$expected passed in " "$D/$label.out"; then
    grep -E "^$expected passed in " "$D/$label.out"
    printf 'WORKER_QUEUE_%s_OK\n' "$label"
  else
    printf 'WORKER_QUEUE_%s_FAILED\n' "$label"
  fi
}
contracts PORTABLE 145 --portable tests/test_desync_worker.py tests/test_desync_event_socket.py \
  tests/test_zapret2_panel.py tests/test_zapret2.py tests/test_desync_standalone.py
contracts ENGINE_HTTP 31 tests/test_nfqws2.py \
  tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state
if command -v node >/dev/null; then
  if timeout -k 3 30 node --test tests/test_zapret2_web_refresh.cjs >"$D/web.out" 2>&1; then
    cat "$D/web.out"
    printf 'WORKER_QUEUE_WEB_OK\n'
  else
    printf 'WORKER_QUEUE_WEB_FAILED\n'
  fi
else
  printf 'WORKER_QUEUE_WEB_UNAVAILABLE\n'
fi

LAB=$(sudo -n mktemp -d /run/xgw-worker-diag.XXXXXXXX)
HOST_NETNS=$(stat -Lc %i /proc/self/ns/net)
printf 'ROOT_PRIVATE_ARTIFACTS %s\n' "$LAB"
git -C "$REPO" archive "$CODE" src/xgw |
  sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$LAB"
rc=0
git -C "$REPO" show "$CODE:docs/helpers/worker_queue_check.py" |
  sudo -n /usr/bin/timeout -k 3 40 /usr/bin/unshare --net "$PY" -I -B - \
    --out "$LAB" --host-netns "$HOST_NETNS" >"$D/lab.out" 2>"$D/lab.err" || rc=$?
cat "$D/lab.out"
printf 'WORKER_QUEUE_LAB_EXIT %s\n' "$rc"


fault_rc=0
git -C "$REPO" show "$CODE:docs/helpers/worker_fault_check.py" |
  sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - "$LAB" \
    >"$D/fault.out" 2>"$D/fault.err" || fault_rc=$?
cat "$D/fault.out"
printf 'WORKER_FAULT_LAB_EXIT %s\n' "$fault_rc"

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'WORKER_QUEUE_GATEWAY_UNCHANGED\n'
else
  printf 'WORKER_QUEUE_GATEWAY_CHANGED\n'
fi
BASH
~~~

## 2. Что включить в отчёт

- Контракты. Ожидаются `WORKER_QUEUE_PORTABLE_OK` с 145 проверками,
  `WORKER_QUEUE_ENGINE_HTTP_OK` с 31 проверкой и
  `WORKER_QUEUE_WEB_OK` с 7 проверками. Укажи результаты по этапам.
- Очередь. Ожидаются `WORKER_QUEUE_LAB_OK` и код 0 в закреплённом
  прогоне. Приведи нули в поколениях 1 и 2, значение после остановки
  и дельты третьего поколения. Ожидание для него — восемь попыток,
  переполнение 7, доставка netlink 0, карточка `ok`, после
  закрытия `null`.
- Диагностика отказов. Ожидаются `WORKER_FAULT_CASES 4/4` и код 0.
  Приведи четыре результата с поколением, кодом завершения и меткой
  причины. `hostlist_marker` и `ipset_marker` проверяют доставку
  синтетической сигнатуры через реальный journald. Реальная ошибка
  распаковки проверена предыдущим отдельным ТЗ по спискам.
  `lua_init` проверяет реальный выход nfqws2 и
  `lua_error_observed`. `clean_exit` проверяет отсутствие
  переноса причины от предыдущего запуска с тем же именем.
- При ошибке приведи этап и краткую обезличенную причину из
  приватного вывода. Выполняй закреплённый сценарий без правок.
- Укажи версию ОС, ядро, SHA кандидата и результат сверки FIB,
  служб и настроек. Сырые логи, пути и идентификаторы оставь
  на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-worker-fault-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_worker-fault-diagnostics.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre worker fault diagnostics and pinned queue lab'
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
