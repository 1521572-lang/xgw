# ThinkCentre · доля потерь доставки NFQUEUE в netlink

**Ubuntu 24.04 LTS.** Flash выполняет готовые команды и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
sudo, pytest или GitHub запроси доступ и выполни доступные проверки.

На ThinkCentre прошли 120 контрактов. В контроле переполнения
измерено 7/0, в опыте с ограниченным буфером netlink измерено
0/28 при 32 назначенных идентификаторах. Ядро, событие, карточка
и сводка совпали. [Отчёт netlink](../reports/2026-11-25T051744Z_t12-queue-netlink.md)

Сводка T12 теперь включает `netlink_delivery_by_policy`. В каждом
режиме она суммирует назначенные идентификаторы и потери доставки
за одни и те же интервалы. При нулевом числе идентификаторов доля
равна `null`. Прежние журналы сохраняют доступные дельты без поля
доли. Этот знаменатель относится к этапу доставки в сокет
слушателя NFQUEUE. Переполнения продолжают учитываться отдельно.
[Порядок учёта в Linux 7.0](https://github.com/torvalds/linux/blob/v7.0/net/netfilter/nfnetlink_queue.c)

## Запуск

Выполни из обычной рабочей копии. Укажи `XGW_TEST_PYTHON` для
отдельного окружения pytest. При необходимости запусти `sudo -v`.
Стенд запускается в отдельном сетевом пространстве имён с loopback.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=ebb7fb18883a53e4e03af5f6638cb81cc3c89bc6
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-queue-delivery.XXXXXXXX")
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
  sudo -n timeout -k 3 40 /usr/bin/unshare --net "$PY" -I -B - \
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

## Отчёт

- **CONTRACTS** — исходы из `CONTRACTS.log`. Проверь прежнюю схему,
  смешанные интервалы, сброс или непригодное значение идентификатора
  и случай нулевого знаменателя. В смешанных интервалах сводка потерь
  остаётся полной для доступных счётчиков, а доля использует только
  интервалы с обоими показаниями.
- **KERNEL** — укажи итоговые `monitor_losses` и код. В первом
  опыте ожидается один назначенный идентификатор и ноль потерь
  доставки. Семь переполнений остаются в соседней сводке. Во втором
  опыте ожидается 32 назначенных идентификатора, ноль переполнений и
  положительная дельта netlink. При повторе 28 потерь доля равна
  0,875. Укажи число интервалов и время между чтениями счётчиков.
- **Шлюз** — итог сверки снимков и хэшей. Прямой диапазон CDN
  и суточное наблюдение остаются отдельными фазами плана.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, счётчики и исходы. Приватные журналы, конфигурацию
и адреса оставь на машине. Выполни блок из рабочей копии.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-delivery-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-queue-delivery-rate.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE delivery loss fraction'
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
