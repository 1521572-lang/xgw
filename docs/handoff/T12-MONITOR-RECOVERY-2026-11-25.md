# ThinkCentre · наблюдение возврата из fallback в T12

На **Ubuntu 24.04 LTS** Flash сама запускает готовые команды и при
любом исходе публикует один обезличенный отчёт на GitHub. При
недоступности терминала, sudo, pytest, сессии панели, архива или GitHub
запроси доступ. Выполни доступные фазы независимо. Codex подготовил
код и тесты, правки рабочей копии в это задание не входят.

[Отчёт о диагностике sing-box](../reports/2026-11-25T013151Z_t12-singbox-diag.md)
подтвердил UID, отсутствие capabilities, `NoNewPrivileges`, положение
правила nftables и TLS 200 с нулём повторных захватов UDP на стенде.
Этот проход проверяет следующий пункт T12, учёт возвращений в состояние
`active` с той же политикой в журнале суточного наблюдения.

## Запуск на машине

Запусти из обычной рабочей копии под пользователем панели. Укажи
`XGW_TEST_PYTHON`, если pytest установлен в отдельном окружении. При
наличии того же архива на 18,51 ч укажи его абсолютный путь в
`XGW_T12_DAY_LOG`. Снимки рабочего шлюза используют `sudo -n`, при
необходимости получи доступ через `sudo -v`. Режим, профиль и службы
оставь как есть.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=d56aa86a1a6b8144a03b20df718b8e54580b1b78
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-recovery.XXXXXXXX")
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

analyze() {
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$1"
}

legacy_archive() {
  local source=${XGW_T12_DAY_LOG:-}
  if [[ $source != /* || ! -f $source || ! -r $source ]]; then
    printf 'ARCHIVE_NOT_AVAILABLE\n'
    return 3
  fi
  sha256sum -- "$source" >"$D/archive.sha256" || return
  PYTHONPATH="$D/previous/src" analyze "$source" >"$D/previous.json" || return
  analyze "$source" >"$D/current.json" || return
  sha256sum --check --status "$D/archive.sha256" || return
  "$PY" -I -B - "$D/previous.json" "$D/current.json" <<'PYTHON'
import json
import sys
from pathlib import Path

previous, current = [json.loads(Path(path).read_text()) for path in sys.argv[1:]]
recovery = current.pop("selected_recovery")
assert previous == current
assert recovery["comparable_sample_pairs"] == recovery["observed_returns_to_active"] == 0
print(json.dumps({"archive_unchanged": True, "previous_aggregates_match": True,
                  "samples": current["samples"], "elapsed_seconds": current["elapsed_seconds"],
                  "utc_boundary_sample_pairs": current["utc_boundary_sample_pairs"],
                  "selected_recovery": recovery}))
PYTHON
}

passive() {
  timeout -k 3 90 "$PY" -B -P -m xgw.desync.client monitor \
    --output "$D/passive.jsonl" --seconds 60 --interval 15 >"$D/passive-collector.json" || return
  stat -c 'PASSIVE_FILE mode=%a bytes=%s' "$D/passive.jsonl" || return
  analyze "$D/passive.jsonl" >"$D/passive-summary.json" || return
  "$PY" -I -B - "$D/passive.jsonl" "$D/passive-summary.json" <<'PYTHON'
import json
import sys
from pathlib import Path

journal, summary = map(Path, sys.argv[1:])
data = json.loads(summary.read_text())
rows = [json.loads(line) for line in journal.read_text().splitlines()]
assert journal.stat().st_mode & 0o777 == 0o600
assert all(0 < row["observed_at"] <= row["at"] for row in rows if "observed_at" in row)
print(json.dumps({"samples": data["samples"], "api_errors": data["api_errors"],
                  "samples_with_daemon_time": sum("observed_at" in row for row in rows),
                  "selected_recovery": data["selected_recovery"]}))
PYTHON
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no --portable -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_desync_monitor_recovery.py tests/test_desync_monitor_expiry.py \
  tests/test_desync_monitor_budget.py tests/test_desync_jobs.py tests/test_zapret2_panel.py
run_phase ARCHIVE legacy_archive
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

## Что фиксировать

Прочитай `CONTRACTS.log`, `ARCHIVE.log` и `PASSIVE.log` из
приватного каталога, напечатанного при запуске.

- **CONTRACTS** — число прошедших, упавших и пропущенных случаев.
  Проверь пары одного профиля с новым снимком демона, повторы,
  старые форматы, смену ревизии, ошибку API, обратный ход часов и
  пропуск промежуточного состояния. Поле возвращения появляется
  в выводе CLI даже для записей без подписанного адреса CDN.
- **ARCHIVE** — сравнение всех прежних агрегатов, хэш источника,
  число отсчётов, длительность и смена суток UTC. Для журнала на
  18,51 ч ожидаются 1109 отсчётов, одна смена суток и ноль сопоставимых
  пар с отметками демона. При отсутствии именно этого архива
  укажи `NOT_RUN`.
- **PASSIVE** — режим файла 0600, число отсчётов, ошибок API и
  записей с отметкой демона, `selected_recovery`. При off/off
  ожидаются ноль сопоставимых пар и ноль наблюдаемых возвращений.
  При естественном переходе `fallback` → `active` максимальное
  окно обозначает интервал между отсчётами. Для подтверждения
  воспроизведения и доступа через VPN нужны отдельные сеансы.
- **Шлюз** — сравни снимки. При естественном изменении состояния
  укажи агрегированные категории различий и отдельно итог сверки
  хэшей конфигурации. Внешние пробы и запись трафика не нужны.

## Автоматическая публикация

Укажи в `REPORT_SRC` абсолютный путь к отчёту с версиями, SHA,
исходами фаз и агрегатами. Исходный журнал, снимки, номера IP,
URL, имена хостов и учётные данные остаются на машине. Выполни блок
при любом исходе из обычной рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-recovery-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-monitor-recovery.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre T12 Selected recovery accounting'
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
