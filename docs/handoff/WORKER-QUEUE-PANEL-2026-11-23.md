# ThinkCentre — потери NFQUEUE в панели и контролируемое переполнение, T01/T08/T11

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает готовые проверки
и при любом исходе автоматически публикует один обезличенный отчёт.
При недоступности терминала, sudo или GitHub запроси доступ.

Предыдущий проход дал 94/94 и 30/30 контрактов. Реальное ядро
вернуло два нулевых счётчика при владельце и `null` после его
остановки в двух поколениях. В новом проходе проверяются интерфейсы
и положительная дельта переполнения. [Отчёт](../reports/2026-11-22T232844Z_worker-queue-diagnostics.md)

Веб-панель показывает суммарные потери, переполнение и ошибки
доставки netlink. Журнал показывает две дельты и поколение. Qt
показывает оба счётчика в состоянии активного режима. API сохраняет
ноль как измеренное значение и отдаёт `null` при отсутствии свежего
подтверждения или несовпадении поколения, очереди либо политики.

## 1. Запуск на ThinkCentre

Выполни `sudo -v`. Если pytest или PyQt6 установлены в отдельных
окружениях, экспортируй абсолютные пути `XGW_TEST_PYTHON` и
`XGW_QT_PYTHON`. Веб-контракт выполняется через установленный Node.js.
Блок использует кандидата из временного checkout и сохраняет
установленные службы и режим шлюза.

Два запуска nfqws2 повторяют базовую проверку владельца. Третий
слушатель создаёт лабораторную очередь на один пакет. Лаборатория
направляет восемь коротких UDP-датаграмм только в loopback
отдельного сетевого пространства. Ожидаются семь потерь при
переполнении и ноль ошибок доставки netlink. Это проверка чтения
счётчика, событий сокета и данных карточки. [Источник ABI и счётчиков](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/nfnetlink_queue.c#L1621)

Штатный nfqws2 запрашивает fail-open. В этом режиме ядро может
пропустить пакет при переполнении без прироста счётчика потерь.
Для проверки положительной дельты используются параметры только
лабораторного слушателя. [Код запуска nfqws2](../../third_party/zapret2/nfq2/nfqws.c#L403) · [Ветвление в ядре](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/nfnetlink_queue.c#L836)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'WORKER_QUEUE_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=200dc1d91809ca0d5055ac7bcb2e63e350edf4b7
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
contracts PORTABLE 63 --portable tests/test_zapret2_panel.py \
  tests/test_desync_event_socket.py tests/test_desync_worker.py
contracts HTTP 1 tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state
QT_PY=${XGW_QT_PYTHON:-$TEST_PY}
if [[ $QT_PY == /* && -x $QT_PY ]] && "$QT_PY" -B -c 'import pytest; import PyQt6.QtWidgets'; then
  QT_QPA_PLATFORM=offscreen TEST_PY="$QT_PY" \
    contracts QT 1 tests/test_gui_qt.py::test_zapret2_queue_losses_are_visible_and_clear_on_stale_data
else
  printf 'WORKER_QUEUE_QT_UNAVAILABLE\n'
fi
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

- `WORKER_QUEUE_PORTABLE_OK` и 63 passed. `WORKER_QUEUE_HTTP_OK`
  подтверждает, что браузерный API возвращает дельты после входа
  и блокирует чтение без сессии. `WORKER_QUEUE_QT_OK` подтверждает
  появление чисел и их очистку при устаревших данных. Веб-контракт
  ожидает 6/6, включая нулевое значение, старый API и две дельты
  в журнале. При отсутствии компонента укажи отдельный статус.
- `WORKER_QUEUE_LAB_OK` и код 0. Для поколений 1 и 2 ожидаются
  счётчики `[0, 0]` и `null` после остановки. Для третьего
  поколения приведи фактические `sent_attempts`, `overflow_delta`,
  `netlink_delta`, результат карточки и значение после закрытия
  слушателя. Положительная дельта доставки netlink в этом запуске
  отдельно не вызывается.
- При ошибке проверки посмотри приватный вывод соответствующего
  этапа. Укажи фазу, краткую обезличенную причину и независимые
  результаты. Сохрани сырые файлы на машине.
- Укажи версию ОС, ядро, SHA кандидата и итог сверки FIB, служб
  и SHA настроек. Публикуй только факт совпадения и классы
  маршрутов при расхождениях.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-worker-queue-panel-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_worker-queue-panel.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE panel and isolated overflow'
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
