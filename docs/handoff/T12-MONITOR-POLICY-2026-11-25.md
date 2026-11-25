# ThinkCentre · учёт применённых политик в журнале T12

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и
публикует один обезличенный отчёт при любом исходе. Запроси доступ
при недоступности терминала, sudo, pytest, архива или GitHub и
пройди доступные фазы. Codex подготовил код и тесты.

[Отчёт UTC](../reports/2026-11-25T031222Z_t12-utc-recovery.md) подтвердил
226 контрактов и один возврат Selective в контрольном журнале
после смены суток. Естественного окна при off/off не было.
Новый анализ учитывает подтверждённые смены политики, чтобы
при суточном наблюдении можно было сверить их с действиями оператора.

## Запуск

Из обычной рабочей копии укажи существующий Python с pytest в
`XGW_TEST_PYTHON`, если используется отдельное окружение. В
`XGW_T12_DAY_LOG` укажи абсолютный путь к прежнему журналу на 18,51 ч.
Он уже использован в [отчёте возвратов](../reports/2026-11-25T021333Z_t12-monitor-recovery.md).
Сами файлы и режим шлюза оставь как есть. Снимки требуют sudo,
при необходимости выполни `sudo -v`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=e47056a364fa006efb5aa7f5e9d75cd4c9b47e6e
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-monitor-policy.XXXXXXXX")
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

compare() {
  local source=$1 label=$2
  [[ $source == /* && -f $source && -r $source ]] || {
    printf 'INPUT_NOT_AVAILABLE %s\n' "$label"; return 3;
  }
  sha256sum -- "$source" >"$D/$label.sha256" || return
  PYTHONPATH="$D/previous/src" timeout -k 3 25 "$PY" -B -P -m xgw.desync.client \
    analyze "$source" >"$D/$label.before.json" || return
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$source" \
    >"$D/$label.after.json" || return
  sha256sum --check --status "$D/$label.sha256" || return
  "$PY" -I -B - "$D/$label.before.json" "$D/$label.after.json" "$label" <<'PYTHON'
import json
import sys
from pathlib import Path

before, after = [json.loads(Path(path).read_text()) for path in sys.argv[1:3]]
changes = after.pop("policy_changes")
assert before == after
assert changes["observed_changes"] == sum(changes["by_policy"].values())
assert changes["observed_changes"] == sum(changes["by_kind"].values())
if sys.argv[3] == "control":
    assert after["samples"] == 3
    assert changes["confirmed_samples"] == 2
    assert changes["by_policy"] == {"off/off → selective/off": 1}
    assert changes["by_kind"] == {"selected_changed": 1}
else:
    assert after["samples"] == 1109
    assert 66_600 <= after["elapsed_seconds"] <= 66_640
    assert after["utc_boundary_sample_pairs"] == 1
print(json.dumps({"input_unchanged": True, "previous_aggregates_match": True,
                  "samples": after["samples"], "elapsed_seconds": after["elapsed_seconds"],
                  "policy_changes": changes}, ensure_ascii=False))
PYTHON
}

panel_control() {
  local -a paths
  mapfile -t paths < <(find "$D/pytest" -maxdepth 2 -type f \
    -path '*/test_monitor_waits_for_daemon*' -name policy.jsonl)
  [[ ${#paths[@]} == 1 ]] || { printf 'CONTROL_JOURNAL_UNAVAILABLE\n'; return 3; }
  compare "${paths[0]}" control
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 180 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no --portable -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_desync_monitor_policy.py tests/test_desync_monitor_recovery.py \
  tests/test_desync_monitor_budget.py tests/test_desync_monitor_expiry.py \
  tests/test_desync_jobs.py tests/test_zapret2_panel.py
run_phase CONTROL panel_control
run_phase ARCHIVE compare "${XGW_T12_DAY_LOG:-}" archive
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

- **CONTRACTS** — сводка из `CONTRACTS.log`. Укажи исходы смены
  Selected и Engine, изменения ревизии при тех же режимах,
  прежней схемы без Engine и снятия неподтверждённых переходов.
  Сбои API, обратный ход часов и разрыв больше 600 с разрывают цепочку.
- **CONTROL** — три отсчёта через карточку панели. Старая политика,
  промежуточная `pending/policy_changed` и подтверждённая новая политика
  дают ровно одну смену Selected. В прежней и новой версиях все
  существовавшие агрегаты совпадают.
- **ARCHIVE** — приведи хэш-вердикт, число отсчётов и агрегат
  `policy_changes` из `ARCHIVE.log`. Число смен из архива заранее
  неизвестно. Если доступен только другой архив, эту фазу пометь
  `NOT_RUN`. Смена политики не устанавливает её автора или причину.
- **Шлюз** — сверь снимки и хэши настроек. Живые смены политики,
  установка, запись трафика и сетевые пробы для этого ТЗ не нужны.

## Автоматическая публикация

Публикуй версии, SHA, исходы фаз и агрегаты. Пути, снимки и журналы,
значения настроек и их отпечатки оставь на машине. Абсолютный путь
к отчёту укажи в `REPORT_SRC`. Выполни блок из обычной рабочей копии
при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-policy-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-monitor-policy.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre T12 policy change accounting'
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
