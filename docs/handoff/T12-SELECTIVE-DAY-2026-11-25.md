# ThinkCentre · допуск к суточному наблюдению Selective

**Ubuntu 24.04 LTS.** Flash запускает готовые команды и публикует один
обезличенный отчёт при любом исходе. При недоступности терминала, sudo,
сессии панели, pytest, архива или GitHub запроси доступ и выполни
доступные фазы. Codex подготовил код и проверки.

На ThinkCentre прошли 190 контрактов. Архив на 18,51 ч подтвердил
смену `off/unknown` → `standalone/unknown`. Новый анализ показывает
время каждого состояния отдельно для каждой пары Selected/Engine.
Флаг `--require-selective` проверяет первый отсчёт и требует свежий
`active` с подтверждённой ревизией и прямым диапазоном 65 536 байт.
После старта монитор продолжает записывать события, включая fallback.
[Отчёт по политикам](../reports/2026-11-25T035208Z_t12-monitor-policy.md)

## Контракты, архив и текущий шлюз

Запусти блок из обычной рабочей копии под пользователем панели.
При необходимости укажи `XGW_TEST_PYTHON` и получи sudo через
`sudo -v`. Для пересчёта укажи в `XGW_T12_DAY_LOG` абсолютный путь
к тому же архиву на 18,51 ч. Для проверки текущего шлюза используй
уже действующий режим.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=c5e26554e024e37275e86f5889a838a8f4d11b8d
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-selective-day.XXXXXXXX")
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
intervals = after.pop("policy_state_intervals")
by_mode = intervals["seconds_by_policy_and_state"]
assert before == after
assert after["samples"] == 1109 and after["utc_boundary_sample_pairs"] == 1
assert 66000 <= after["elapsed_seconds"] <= 67000
assert by_mode["standalone/unknown"]["active"] > 43000
assert not any(mode.startswith("selective/") and states.get("active") for mode, states in by_mode.items())
print(json.dumps({"archive_unchanged": True, "previous_aggregates_match": True,
                  "samples": after["samples"], "elapsed_seconds": after["elapsed_seconds"],
                  "policy_state_intervals": intervals}))
PYTHON
}

guard() {
  local path="$D/selective-guard.jsonl" code=0
  timeout -k 3 90 "$PY" -B -P -m xgw.desync.client monitor \
    --require-selective --output "$path" --seconds 60 --interval 15 || code=$?
  if [[ $code == 0 ]]; then
    stat -c 'GUARD_FILE mode=%a bytes=%s' "$path" || return
    timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$path" \
      >"$D/guard-summary.json"
  else
    [[ ! -e $path ]] && printf 'GUARD_NO_JOURNAL\n'
    return "$code"
  fi
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 180 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no --portable -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_desync_jobs.py tests/test_zapret2_panel.py \
  tests/test_desync_monitor_policy.py tests/test_desync_monitor_recovery.py \
  tests/test_desync_monitor_budget.py tests/test_desync_monitor_expiry.py
run_phase ARCHIVE archive
run_phase GUARD guard
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

## Суточная фаза

Условия начала остаются в §6–7 действующей приёмки. Нужны свежие
подтверждения прямого воспроизведения и его маршрута, обычного VPN
и возврата после отказа. Используй предусмотренный там независимый
откат при временном переключении. Если на этом проходе этих
подтверждений нет, отметь `DAY_SELECTIVE=NOT_RUN` и публикуй результаты
доступных фаз. [Условия запуска и восстановления](COMBINED-ADMISSION-2026-11-19.md#7-суточный-selective--только-если-он-действительно-заработал)

Подставь в `D` абсолютный путь `PRIVATE_ARTIFACTS` из первого блока.
Запускай команду из сессии пользователя панели после выполнения условий.

~~~bash
bash -s -- "$D" <<'BASH'
set -euo pipefail
umask 077
D=$1
[[ $D == /* && -f $D/tree/src/xgw/desync/client.py ]]
PY=/usr/bin/python3
systemd-run --user --unit=xgw-t12-selective-day --wait --collect \
  --property=RuntimeMaxSec=25h --property=UMask=0077 \
  /usr/bin/env "PYTHONPATH=$D/tree/src" "$PY" -B -P -m xgw.desync.client monitor \
  --require-selective --output "$D/selective-day.jsonl" --seconds 86400 --interval 60
PYTHONPATH="$D/tree/src" "$PY" -B -P -m xgw.desync.client analyze "$D/selective-day.jsonl" \
  >"$D/selective-day-summary.json"
BASH
~~~

В суточной фазе укажи фактическую длительность, разрывы, секунды active,
fallback и blocked для `selective/off` или `selective/auto`, смену UTC,
истечение CDN, бюджет и новые сеансы после обеих границ. Запиши ручные
действия и исход возврата шлюза по §8. При прерывании пересчитай видимую
часть файла той же командой `analyze` и укажи фактическое покрытие.

## Отчёт

- **CONTRACTS** — итог из `CONTRACTS.log`. Зафиксируй отказы до записи
  файла, старт по подтверждённому диапазону и сохранение fallback
  после старта.
- **ARCHIVE** — итог из `ARCHIVE.log`. Укажи отдельно время
  `standalone/unknown` и Selective. Сверь прежние агрегаты и хэш.
- **GUARD** — при off/off ожидаются `selective_not_active`, код 2
  и `GUARD_NO_JOURNAL`. При активной политике со служебной HTTPS-пробой
  без диапазона ожидается `direct_cdn_range_unconfirmed`. При успешном
  старте проверь режим файла и прочитай `guard-summary.json`.
- **DAY_SELECTIVE** — исход и выполненные условия. Для шлюза приведи
  итог сравнения снимков и хэшей.

## Автоматическая публикация

Укажи абсолютный путь Markdown в `REPORT_SRC`. Включи версии, SHA,
исходы и агрегаты. Исходные журналы, адреса, параметры CDN и настройки
оставь на машине. Запусти блок из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-day-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-selective-day.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Selective day monitor admission'
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
