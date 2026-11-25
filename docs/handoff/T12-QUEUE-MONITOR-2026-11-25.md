# ThinkCentre · потери NFQUEUE в журнале T12

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые проверки и
публикует обезличенный отчёт при любом исходе. Если терминал, sudo,
pytest, исходный архив или GitHub недоступны, запроси доступ и
выполни остальные фазы. Codex подготовил реализацию и тесты.

На ThinkCentre прошли 204 контракта допуска к суточному наблюдению.
В архиве подтверждены 12,15 ч active в Standalone. Проверка старта
при off/off вернула код 2 до создания журнала. Суточная фаза
ждёт прямого диапазона CDN и подтверждения воспроизведения.
[Отчёт допуска](../reports/2026-11-25T043645Z_t12-selective-day.md)

В новом отчёте `queue_losses` видны интервалы и отдельные приращения
счётчиков переполнения и доставки netlink по каждой паре режимов.
Пара отсчётов учитывается при непрерывной работе того же слушателя,
свежей политике и монотонных счётчиках. В архиве без таких отсчётов
ожидается пустая сводка. На стенде данные проходят из ядра через
карточку панели и JSONL до анализатора.

## Проверки на машине

Из обычной рабочей копии задай `XGW_TEST_PYTHON`, если pytest установлен
в отдельном окружении. Для архива укажи прежний путь в
`XGW_T12_DAY_LOG`. Стенд под sudo использует отдельное сетевое
пространство имён с loopback. При необходимости начни с `sudo -v`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=1cfa592e9dc9288d92fa38b641c41847dd670797
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-queue-monitor.XXXXXXXX")
mkdir "$D/tree" "$D/previous"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
git -C "$REPO" archive "$CODE^" src | tar -x -C "$D/previous"
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

archive() {
  local source=${XGW_T12_DAY_LOG:-}
  [[ $source == /* && -f $source && -r $source ]] || {
    printf 'ARCHIVE_NOT_AVAILABLE\n'; return 3;
  }
  sha256sum -- "$source" >"$D/archive.sha256" || return
  PYTHONPATH="$D/previous/src" timeout -k 3 25 "$PY" -B -P -m xgw.desync.client \
    analyze "$source" >"$D/archive.before.json" || return
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$source" \
    >"$D/archive.after.json" || return
  sha256sum --check --status "$D/archive.sha256" || return
  "$PY" -I -B - "$D/archive.before.json" "$D/archive.after.json" <<'PYTHON'
import json
import sys
from pathlib import Path

before, after = [json.loads(Path(path).read_text()) for path in sys.argv[1:]]
losses = after.pop("queue_losses")
assert before == after and after["samples"] == 1109
assert 66_000 <= after["elapsed_seconds"] <= 67_000
assert losses == {"samples_with_counters": 0, "by_policy": {}}
print(json.dumps({"unchanged": True, "previous_aggregates_match": True,
                  "samples": after["samples"], "queue_losses": losses}))
PYTHON
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
  tests/test_zapret2_panel.py tests/test_desync_jobs.py tests/test_desync_monitor_queue.py
run_phase ARCHIVE archive
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

- **CONTRACTS** — сводка `CONTRACTS.log`. Подтверди различие нулевой
  дельты и недоступного отсчёта, смену слушателя и перезапуск демона,
  неподтверждённую политику, сброс счётчиков и разрыв.
- **ARCHIVE** — хэш и совпадение прежних агрегатов из `ARCHIVE.log`.
  В прежней записи 1109 отсчётов, пригодных счётчиков NFQUEUE там нет.
  При отсутствии именно этого архива укажи `NOT_RUN`.
- **KERNEL** — сводка `KERNEL.log`. На loopback ожидаются 8 отправок,
  7 переполнений, netlink 0. Разбор JSONL должен дать две записи
  со счётчиками и один измеренный интервал `off/auto` с дельтами 7 и 0.
  После закрытия слушателя отсчёт счётчиков становится недоступен.
  Эти потери относятся к очереди в целом. Для атрибуции конкретного
  CDN-сокета используй отдельные наблюдения маршрута и TCP.
- **Шлюз** — итог сравнения снимков и настроек. Прямой диапазон CDN
  в рабочем режиме и суточное окно остаются отдельными фазами плана.

## Автоматическая публикация

Укажи абсолютный путь отчёта в `REPORT_SRC`. Публикуй версии, SHA,
итоги, интервалы и дельты. Снимки, сырые строки журнала, метки
запуска и адреса оставь на машине. Выполни из рабочей копии.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-queue-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-queue-monitor.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre NFQUEUE loss accounting'
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
