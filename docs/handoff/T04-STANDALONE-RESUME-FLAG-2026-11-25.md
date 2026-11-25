# ThinkCentre · восстановление состояния поколений sing-box

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и
автоматически публикует обезличенный отчёт при любом исходе.
При недоступности терминала, sudo, pytest или GitHub запроси
доступ и выполни остальные фазы.

В предыдущем проходе Standalone выключился штатно и вернул
managed blue через API. Перед запуском Flash вручную удалила
устаревший `resume_managed` из runtime-состояния, потому что
проверка считала его признаком незавершённого перехода.
На прямом CDN снова получен TLS-таймаут. VPN успешно принял
диапазон 65 536 байт. [Отчёт ThinkCentre](../reports/2026-11-25T092146Z_t04-cdn-standalone-exit.md)

Запрос возврата в управляемое поколение относится к активному
legacy. Проверка готовности blue/green принимает прежний формат
с устаревшим флагом, если служба и маркер подтверждены, а
переходы завершены. Восстановление демона удаляет устаревшее
поле под общей блокировкой. На рабочем шлюзе ТЗ читает только
топологию и снимки.

## Запуск

Из рабочей копии задай `XGW_TEST_PYTHON`, если pytest установлен
отдельно. Для чтения снимков шлюза при необходимости выполни
`sudo -v`. Контролируемые состояния создаются тестами во
временном каталоге.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=fe93c5788143335215fd1183f9e4e59b10616039
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-resume-flag.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers packaging vpn_ui pyproject.toml \
  | tar -x -C "$D/tree"
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

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_singbox_generations.py tests/test_standalone_topology.py \
  tests/test_standalone_exit_evidence.py tests/test_selective_admission.py
run_phase TOPOLOGY sudo -n timeout -k 2 40 env "PYTHONPATH=$D/tree:$D/tree/src" \
  "$PY" -B -P -m docs.helpers.standalone_topology stable 25
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T04_GATEWAY_UNCHANGED\n'
  else
    printf 'T04_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T04_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Итоги

- **CONTRACTS** — сводка из `CONTRACTS.log`. Отметь обе проверки
  blue/green, удаление только устаревшего поля, сохранение запроса
  legacy и отказ готовности при pending, остановке или отсутствии
  живой службы. Проверь штатный переход от legacy к managed.
- **TOPOLOGY** — исход из `TOPOLOGY.log`. Укажи активный слот,
  маркер, состояния pending и draining, `resume_managed` и
  `stale_resume_managed`. Если старого поля в действующей записи
  уже нет, сценарий его обработки подтверждается контрактами.
  Исходное состояние рабочего шлюза оставь как есть.
- **Шлюз** — исход сравнения снимков и хэшей. Прямой диапазон CDN
  и причина прежнего `off_deadline` остаются открытыми.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, состояния и результаты. Снимки, настройки и журналы
оставь на машине. Выполни блок из рабочей копии при любом исходе.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-resume-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-standalone-resume-flag.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre managed sing-box resume flag recovery'
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
