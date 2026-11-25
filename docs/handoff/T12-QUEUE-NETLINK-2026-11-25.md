# ThinkCentre · потери доставки NFQUEUE в netlink

**Ubuntu 24.04 LTS.** Flash выполняет готовые проверки и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
sudo, pytest или GitHub запроси доступ и выполни доступные фазы.

На ThinkCentre прошёл 151 контракт. Стенд подтвердил 7 переполнений
NFQUEUE при 8 отправках и нулевую дельту netlink. Разбор JSONL,
карточка и событие совпали. Прежний архив сохранил все агрегаты.
Отдельная проверка положительной дельты netlink остаётся открытой.
[Отчёт NFQUEUE](../reports/2026-11-25T044745Z_t12-queue-monitor.md)

В новом опыте очередь вмещает 64 пакета, тест отправляет 32
датаграммы через loopback. Сокет netlink имеет небольшой буфер
приёма, который тест оставляет непрочитанным до замера. В ядре
отказ доставки в сокет и переполнение самой очереди обновляют
разные счётчики. [Исходный код Linux](https://github.com/torvalds/linux/blob/master/net/netfilter/nfnetlink_queue.c)

## Запуск

Выполни из обычной рабочей копии. Укажи `XGW_TEST_PYTHON`, если
pytest установлен в отдельном окружении. Для стенда при необходимости
начни с `sudo -v`. Он запускает штатный тест в отдельном сетевом
пространстве имён, проверяет внутри наличие только loopback и
записывает приватный JSONL в каталог под `/run`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=fcf395d580a082f9c249bb3d9fcaaed27d968d8d
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-queue-netlink.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  sudo -n timeout -k 3 60 "$PY" -I -B - snapshot <docs/helpers/audit_host_observe.py &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

run_phase() {
  local label=$1 code=0
  shift
  "$@" >"$D/$label.log" 2>&1 || code=$?
  printf '%s_EXIT %s\n' "$label" "$code"
}

kernel() {
  local lab host_netns
  lab=$(sudo -n mktemp -d /run/xgw-worker-diag.XXXXXXXX) || return
  host_netns=$(stat -Lc %i /proc/self/ns/net) || return
  if ! git -C "$REPO" archive "$CODE" src/xgw |
      sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$lab"; then
    return 2
  fi
  sudo -n /usr/bin/timeout -k 3 40 /usr/bin/unshare --net "$PY" -I -B - \
    --out "$lab" --host-netns "$host_netns" <docs/helpers/worker_queue_check.py
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no --portable -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_desync_worker.py tests/test_desync_event_socket.py \
  tests/test_zapret2_panel.py tests/test_desync_monitor_queue.py
run_phase KERNEL kernel
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T12_GATEWAY_UNCHANGED\n'
  else
    printf 'T12_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T12_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Итоги

- **CONTRACTS** — числа из `CONTRACTS.log`. Укажи проверки нулевой
  и положительной дельты, потери слушателя и обновления поколения.
- **KERNEL** — приведи обе итоговые строки `monitor_losses` из
  `KERNEL.log` и код выхода.
  Контроль переполнения должен дать 7/0 при 8 отправках. Во втором
  опыте укажи фактический размер буфера, последовательность 32,
  переполнение 0 и измеренную ненулевую дельту netlink. Тот же
  результат должен появиться в событии, карточке и анализе JSONL.
  При закрытии слушателя значения становятся недоступными.
  При `netlink_expected_counters` приведи фактические показания из
  строки перед ошибкой. Длительность интервала берётся из времени
  двух чтений счётчиков.
- **Шлюз** — итог сверки состояния и хэшей. Этот стенд проверяет
  учёт потерь на общей очереди. Живой прямой CDN остаётся отдельной
  фазой плана.

## Автоматическая публикация

Укажи абсолютный путь отчёта в `REPORT_SRC`. Публикуй версии, SHA,
счётчики и итоговые коды. Журналы, адреса и конфигурацию оставь
на машине. Выполни блок из рабочей копии.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-netlink-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-queue-netlink.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE netlink delivery loss'
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
