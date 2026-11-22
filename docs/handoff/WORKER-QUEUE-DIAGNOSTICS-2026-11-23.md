# ThinkCentre — диагностика потерь NFQUEUE, T01/T08/T11

**Ubuntu 24.04 LTS.** Flash сама выполняет техническую проверку
и автоматически публикует один обезличенный отчёт при любом исходе.
При недоступности терминала, sudo или GitHub запроси нужный доступ.

Предыдущая лаборатория прошла 6/6. Недоступный положительный список
сохранил прежние данные в памяти. Повреждённые hostlist и ipset
завершили дочерние процессы с кодом 200. Защита образца публикации
отклонила пять негодных кандидатов до замены.
[Отчёт по обновлению списков](../reports/2026-11-22T231433Z_flowseal-list-reload.md)

XGW теперь читает `queue_dropped` и `queue_user_dropped` при
подтверждённом владельце очереди. В журнале `overflow` относится
к переполнению, `netlink` — к ошибке доставки сокету. Старый
формат запроса и курсора версии 1 поддерживается. Событие
`queue_drops` содержит дельты как два отдельных поля. Смена
сокета, потеря владельца или сброс счётчика начинают новый отсчёт.
[Исходник счётчиков Linux](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/nfnetlink_queue.c#L836)

## 1. Запуск

В терминале ThinkCentre выполни `sudo -v`. Если pytest установлен в
отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
Запусти блок из рабочей копии XGW. Он возьмёт файлы из закреплённого
коммита. Лабораторный дочерний nfqws2 создаёт очередь 201 в новом
сетевом пространстве с одним loopback. Два запуска слушателя
идут последовательно. Слушатель не получает пакеты, поэтому
этот контроль проверяет доступность реальных счётчиков и
пропажу владельца. Рост счётчиков и сбросы покрыты фикстурами.
Службы и настройки рабочего шлюза сверяются до и после.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=db2a5da5fe25db068b526e2ec7fafb937fc1619a
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
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml |
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
contracts PORTABLE 94 --portable tests/test_desync_worker.py tests/test_desync_event_socket.py \
  tests/test_zapret2.py tests/test_desync_standalone.py
contracts ENGINE 30 tests/test_nfqws2.py

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

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'WORKER_QUEUE_GATEWAY_UNCHANGED\n'
else
  printf 'WORKER_QUEUE_GATEWAY_CHANGED\n'
fi
BASH
~~~

## 2. Критерии и отчёт

- `WORKER_QUEUE_PORTABLE_OK` и 94 passed. Укажи число,
  длительность и результат контрактов очереди, сокета,
  режима Standalone и контроллера.
- `WORKER_QUEUE_ENGINE_OK` и 30 passed. Укажи итог контрактов
  Engine. Контроль ошибки preflight сверяет причину до закрытия
  контроллера и состояние после закрытия.
- `WORKER_QUEUE_LAB_OK` и `WORKER_QUEUE_LAB_EXIT 0`. Для
  поколений 1 и 2 приведи две пары счётчиков и исход чтения
  через реальный UNIX-сокет. Ожидаются `[0, 0]` в каждом
  поколении и `null` после остановки слушателя.
  `owner_unverified` подтверждает потерю владельца.
  Отдельно отметь `live_positive_drop=NOT_INDUCED`.
- `WORKER_QUEUE_LAB_FAILED` требует имени фазы. При ошибке
  старта или доступа к `/proc` проверь приватный журнал
  дочернего процесса и перенеси только обезличенную причину.
  При отсутствии закреплённого двигателя или разрешения
  на namespace зафиксируй недоступную фазу. Укажи результаты
  независимых контрактов.
- Приведи ОС, ядро, SHA кандидата и `WORKER_QUEUE_GATEWAY_UNCHANGED`
  либо `WORKER_QUEUE_GATEWAY_CHANGED`. Укажи, совпали ли классы
  FIB, PID служб и настройки. Сырые журналы, идентификаторы
  сокетов, пути и содержимое конфигураций оставь на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-worker-queue-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_worker-queue-diagnostics.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE worker diagnostics'
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
