# ThinkCentre — время до подтверждения владельца NFQUEUE

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает проверки и публикует
обезличенный отчёт. Запроси доступ, если недоступны терминал, sudo, архив
или GitHub. Продолжи независимые этапы при блокере.

В предыдущем отчёте прошли 86 контрактов и проверка конкурирующих записей.
В старых архивах есть длительность попыток и часть замеров для страницы
и CDN. Время запуска воркера появится в новых заданиях. Этот этап проверяет его по двум
реальным запускам закреплённого nfqws2 в отдельном сетевом пространстве.
Тесты не требуют переключения рабочего режима или установки файлов.

[Отчёт по фазам](../reports/2026-11-23T002922Z_t09-matrix-timing.md) · [Исходники архивной матрицы](T09-MATRIX-REPLAY-2026-11-23.md#1-исходные-файлы)

## 1. Запуск

Экспортируй уже найденный абсолютный путь `XGW_T09_JOB` к
`matrix-result.json` на 18 строк. При недоступном файле оставь переменную
пустой. Если pytest находится в venv, экспортируй абсолютный путь к его
Python в `XGW_TEST_PYTHON`. Выполни `sudo -v`, затем блок из рабочей копии
XGW.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'WORKER_START_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=fcc3734ccacdfb2eeb82166a97af92ddbb60ed6a
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-worker-start.XXXXXXXX")
printf 'WORKER_START_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

snapshot() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot >"$D/host.$1.json" &&
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.$1"
}
host_before=0
if sudo -n true && snapshot before; then
  host_before=1
fi

contracts() {
  local label=$1 rc=0
  shift
  timeout -k 3 180 "$TEST_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider -q --tb=short "$@" >"$D/$label.out" 2>&1 || rc=$?
  printf 'WORKER_START_TEST %s %s\n' "$label" "$rc"
  tail -n 3 "$D/$label.out"
}
contracts worker_status --portable tests/test_desync_worker.py \
  tests/test_desync_event_socket.py tests/test_zapret2_panel.py \
  tests/test_zapret2.py tests/test_desync_standalone.py
contracts matrix --portable tests/test_desync_jobs.py \
  tests/test_desync_tournament.py tests/test_desync_experiment.py
contracts engine_http tests/test_nfqws2.py \
  tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state

if sudo -n true && LAB=$(sudo -n mktemp -d /run/xgw-worker-diag.XXXXXXXX); then
  HOST_NETNS=$(stat -Lc %i /proc/self/ns/net)
  printf 'ROOT_PRIVATE_ARTIFACTS %s\n' "$LAB"
  if git -C "$REPO" archive "$CODE" src/xgw |
     sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$LAB"; then
    rc=0
    git -C "$REPO" show "$CODE:docs/helpers/worker_queue_check.py" |
      sudo -n /usr/bin/timeout -k 3 40 /usr/bin/unshare --net "$PY" -I -B - \
        --out "$LAB" --host-netns "$HOST_NETNS" >"$D/lab.out" 2>"$D/lab.err" || rc=$?
    cat "$D/lab.out"
    printf 'WORKER_START_LAB_EXIT %s\n' "$rc"
  else
    printf 'WORKER_START_LAB_UNAVAILABLE tree\n'
  fi
else
  printf 'WORKER_START_LAB_UNAVAILABLE sudo_or_run_dir\n'
fi

FILE=${XGW_T09_JOB:-}
if [[ $FILE == /* && -f $FILE && -r $FILE ]] &&
   sha256sum -- "$FILE" >"$D/source.sha256"; then
  rc=0
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client matrix --replay "$FILE" \
    >"$D/matrix.json" 2>"$D/matrix.err" || rc=$?
  printf 'WORKER_START_ARCHIVE_EXIT %s\n' "$rc"
  if [[ -s $D/matrix.json ]]; then cat "$D/matrix.json"; fi
  if sha256sum --check --status "$D/source.sha256"; then
    printf 'WORKER_START_SOURCE_UNCHANGED\n'
  else
    printf 'WORKER_START_SOURCE_CHANGED\n'
  fi
else
  printf 'WORKER_START_ARCHIVE_UNAVAILABLE\n'
fi

if (( host_before )) && snapshot after; then
  if cmp -s "$D/host.before.json" "$D/host.after.json" &&
     cmp -s "$D/settings.before" "$D/settings.after"; then
    printf 'WORKER_START_GATEWAY_UNCHANGED\n'
  else
    printf 'WORKER_START_GATEWAY_CHANGED\n'
  fi
else
  printf 'WORKER_START_GATEWAY_NOT_VERIFIED\n'
fi
BASH
~~~

## 2. Сверка и отчёт

- Ожидаемые контракты — 147 в `worker_status`, 86 в `matrix`, 31 в
  `engine_http`. Укажи фактическое число и код каждого набора.
- В лаборатории ожидаются `WORKER_QUEUE_LAB_OK` и код 0. Укажи оба
  фактических `worker_start_ms` в поколениях 1 и 2. Сценарий проверяет
  отсутствие значения до подтверждения владельца, сохранность первого
  показания при повторном чтении и сброс после исчезновения слушателя.
  Отдельный контроль третьего поколения должен сохранить переполнение
  7, netlink 0 и очистку показания после закрытия.
- `worker_start_ms` измеряется монотонными часами от резервирования
  очереди до первого подтверждения XGW по данным ядра, что сокет
  очереди принадлежит воркеру.
  Интервал включает задержку обнаружения владельца. Подготовка перед
  резервированием в интервал не входит.
- В старом архиве на 18 строк ожидается `samples=0, total_ms=null`
  для `worker_start` и `attempt_with_worker_start` в обоих кругах.
  Второй показатель суммирует время только попыток, для которых есть
  замер запуска. Используй его знаменателем при будущем расчёте доли.
  Оба интервала входят в полную попытку, поэтому сумму запуска отдельно
  к длительности попыток не прибавляй.
- Лабораторные миллисекунды относятся к запускам в отдельном
  пространстве. Доля запуска в живой матрице, воспроизведение видео,
  установка и смена режима — `NOT_RUN` в этом задании.
- Зафиксируй Ubuntu, ядро, SHA кандидата, состояние источника и
  FIB/PID/настроек. При блокере укажи конкретный этап. Публикуй
  агрегаты, сохраняя сырые журналы, идентификаторы, URL и локальные
  пути в приватных каталогах.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок при любом исходе из рабочей копии. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-worker-start-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_worker-startup.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE worker startup timing'
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
