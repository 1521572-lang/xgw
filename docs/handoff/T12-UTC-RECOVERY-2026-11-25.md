# ThinkCentre · возврат Selective после смены суток UTC

На **Ubuntu 24.04 LTS** Flash сама запускает готовые проверки и
автоматически публикует обезличенный отчёт при любом исходе. Если
терминал, sudo, pytest, сессия панели или GitHub недоступны, запроси
доступ и выполни независимые фазы. Код и тесты подготовлены Codex.

[Предыдущий отчёт T12](../reports/2026-11-25T021333Z_t12-monitor-recovery.md)
подтвердил 168 контрактов, точное совпадение прежних агрегатов на
18,51 ч и пять живых отсчётов off/off. При возврате Selective после
исчерпания бюджета контроллер публикует `probe_inbound` и `nfqueue`
между `fallback` и `active`. Этот проход проверяет всю цепочку:
контроллер, карточку, запись мониторинга и CLI-анализ.

## Запуск

Из обычной рабочей копии под пользователем панели выполни блок.
Для отдельного окружения pytest задай `XGW_TEST_PYTHON`. Снимки
рабочего шлюза требуют sudo. При необходимости выполни `sudo -v`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=b3568352457142fe936fdea97067396c49aab56f
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-utc-recovery.XXXXXXXX")
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

baseline() {
  local journal
  local -a paths
  mapfile -t paths < <(find "$D/pytest" -maxdepth 2 -type f -name rollover.jsonl)
  [[ ${#paths[@]} == 1 ]] || { printf 'CONTROL_JOURNAL_UNAVAILABLE\n'; return 3; }
  journal=${paths[0]}
  PYTHONPATH="$D/previous/src" timeout -k 3 25 "$PY" -B -P -m xgw.desync.client \
    analyze "$journal" >"$D/previous.json" || return
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$journal" >"$D/current.json" || return
  "$PY" -I -B - "$D/previous.json" "$D/current.json" <<'PYTHON'
import json
import sys
from pathlib import Path

before, after = [json.loads(Path(path).read_text()) for path in sys.argv[1:]]
old, new = before.pop("selected_recovery"), after.pop("selected_recovery")
assert before == after
assert after["budget"]["confirmed_utc_rollovers"] == 1
assert old["observed_returns_to_active"] == 0 and new["observed_returns_to_active"] == 1
assert new["by_fallback_reason"] == {"probe_budget": 1}
assert new["max_sampling_window_seconds"] == 16
print(json.dumps({"previous_returns": old["observed_returns_to_active"],
                  "current_returns": new["observed_returns_to_active"],
                  "utc_rollovers": 1, "other_aggregates_match": True,
                  "max_sampling_window_seconds": new["max_sampling_window_seconds"]}))
PYTHON
}

passive() {
  local gate=0
  timeout -k 2 15 "$PY" -B -P - <<'PYTHON' || gate=$?
from xgw.desync.client import Client, observation

row = observation(Client().request("/api/state"))
reset = row["budget"].get("resets_at")
eligible = (row["mode"] == "selective" and row["state"] == "fallback"
            and row["reason"] == "probe_budget" and row["fresh"] is True
            and row["policy_matched"] is True and type(reset) is int
            and 20 <= reset - row["at"] <= 120)
raise SystemExit(0 if eligible else 3)
PYTHON
  case $gate in
    0) ;;
    3) printf 'PASSIVE_NOT_RUN_NO_NATURAL_UTC_WINDOW\n'; return 3 ;;
    *) printf 'PASSIVE_PANEL_UNAVAILABLE\n'; return "$gate" ;;
  esac
  timeout -k 3 210 "$PY" -B -P -m xgw.desync.client monitor \
    --output "$D/passive.jsonl" --seconds 180 --interval 15 >"$D/passive-collector.json" || return
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$D/passive.jsonl" \
    >"$D/passive-summary.json"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 180 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no --portable -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_zapret2.py tests/test_desync_monitor_recovery.py \
  tests/test_desync_monitor_budget.py tests/test_desync_monitor_expiry.py tests/test_zapret2_panel.py
run_phase BASELINE baseline
run_phase PASSIVE passive
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

- **CONTRACTS** — проверь сводку `CONTRACTS.log`. В контроле часы
  и сеть моделируются внутри теста. Контроллер удерживает VPN при
  остатке 256 КиБ, затем использует новый суточный бюджет и снова
  публикует `active`. Последовательность из четырёх состояний попадает
  в журнал. Тесты отдельно проверяют повтор снимка подготовки,
  смену настроек, разрыв, обратный порядок подготовки и предел 600 с
  на весь переход.
- **BASELINE** — сверь `BASELINE.log`. Тот же журнал контроллера даёт
  0 возвратов у родителя и 1 у кандидата, со сменой суток UTC у обоих.
  Остальные агрегаты совпадают. 16 с — окно между отсчётами контроля.
- **PASSIVE** — при естественном окне укажи число отсчётов, смену UTC,
  ошибки API и наблюдаемые возвраты. Без окна зафиксируй `NOT_RUN`.
  Часы хоста, бюджет, режим, службы и настройки оставь как есть.
  Подтверждение живого прямого YouTube и суточный проход T12 остаются
  отдельными фазами.
- **Шлюз** — зафиксируй сравнение снимков. При отличиях отдельно
  проверь совпадение хэшей настройки. Установка и запись трафика
  в этом проходе не требуются.

## Публикация

Укажи в `REPORT_SRC` абсолютный путь к отчёту с версиями, SHA,
исходами фаз и агрегатами. Исходные файлы, снимки и журналы оставь
на машине. Запусти из обычной рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-utc-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-utc-recovery.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Selective recovery at UTC rollover'
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
