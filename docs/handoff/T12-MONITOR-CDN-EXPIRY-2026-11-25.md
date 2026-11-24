# ThinkCentre · граница срока CDN в журнале T12

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые команды, проверяет
артефакты и публикует один обезличенный отчёт на GitHub при любом
исходе. При недоступности терминала, pytest, журнала, учётной записи
панели или GitHub запроси доступ и выполни доступные фазы. Код и тесты
подготовлены Codex.

[Предыдущий отчёт T12](../reports/2026-11-24T212113Z_t12-monitor-accounting.md)
подтвердил 54 контракта, один UTC-переход в архиве на 18,51 ч и пять
отсчётов штатной панели off/off без ошибок. Этот проход проверяет,
что журнал также различает переход через срок CDN, первый снимок демона
после срока и явно зафиксированную реакцию `youtube_cdn_expired`.

## Запуск на машине

Из обычной рабочей копии укажи `XGW_TEST_PYTHON`, если pytest доступен
в отдельном окружении. Для сверки совместимости укажи `XGW_T12_DAY_LOG`
с абсолютным путём к тому же исходному журналу на 18,51 ч. При отсутствии
архива фаза `ARCHIVE` вернёт отдельный результат. Сравнение шлюза
требует `sudo -n true`. При необходимости получи доступ через `sudo -v`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=14f7670c9c5bf96caa33507afeaffc00e223a92a
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-expiry.XXXXXXXX")
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
  tail -n 15 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

analyze() {
  timeout -k 3 25 "$PY" -B -P -m xgw.desync.client analyze "$1"
}

legacy_archive() {
  local source=${XGW_T12_DAY_LOG:-} code=0
  if [[ $source != /* || ! -f $source || ! -r $source ]]; then
    printf 'ARCHIVE_NOT_AVAILABLE\n'
    return 3
  fi
  sha256sum -- "$source" >"$D/archive.sha256" || return
  analyze "$source" >"$D/archive-summary.json" || code=$?
  sha256sum --check --status "$D/archive.sha256" || return
  printf 'ARCHIVE_UNCHANGED\n'
  return "$code"
}

passive_window() {
  local window=0
  timeout -k 2 15 "$PY" -B -P - <<'PYTHON' || window=$?
from xgw.desync.client import Client, observation

sample = observation(Client().request("/api/state"))
deadline = sample.get("cdn_expires_at", 0)
eligible = (sample.get("mode") == "selective" and sample.get("state") == "active"
            and sample.get("fresh") is True and sample.get("policy_matched") is True
            and 20 <= deadline - sample["at"] <= 120)
raise SystemExit(0 if eligible else 3)
PYTHON
  case $window in
    0) ;;
    3) printf 'PASSIVE_SKIPPED_NO_NATURAL_WINDOW\n'; return 3 ;;
    *) printf 'PASSIVE_PANEL_UNAVAILABLE\n'; return "$window" ;;
  esac
  timeout -k 3 210 "$PY" -B -P -m xgw.desync.client monitor \
    --output "$D/passive.jsonl" --seconds 180 --interval 15 >"$D/passive-collector.json" || return
  stat -c 'PASSIVE_FILE mode=%a bytes=%s' "$D/passive.jsonl" || return
  analyze "$D/passive.jsonl" >"$D/passive-summary.json"
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short --portable \
  --basetemp "$D/pytest" tests/test_desync_monitor_expiry.py tests/test_desync_monitor_budget.py \
  tests/test_desync_jobs.py tests/test_zapret2_panel.py tests/test_selective_admission.py || true
run_phase ARCHIVE legacy_archive || true
run_phase PASSIVE passive_window || true
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

- **CONTRACTS** — прошедшие, упавшие и пропущенные проверки, длительность.
  Отдельно проверь цепочку из снимка панели через `monitor` до `analyze`.
  В тесте часы процесса моделируются, первый отсчёт за сроком содержит
  снимок демона до срока, позднее приходит явный `fallback`. Проверь также
  `blocked`, смену ревизии, разрыв, ошибку API, старую схему и обратный
  ход часов. В журнале нет подписи, имени CDN и параметров URL.
- **ARCHIVE** — напиши статус хэша, число отсчётов и длительность. Для
  прежней записи ожидаются 1109 отсчётов, 18,51 ч, одна подтверждённая
  смена UTC и один недоступный отсчёт бюджета. `samples_with_deadline: 0`
  означает, что старый журнал не содержит пригодных сроков CDN. Офлайн
  не подставляй текущий срок из настроек в старые записи.
- **PASSIVE** — запускать только при уже работающем Selective и сроке
  в ближайшие 20–120 с. При отсутствии окна отметь `NOT_RUN`, эту фазу
  оставь для штатного суточного наблюдения. Режим, URL, лимит и часы
  оставь как есть. При выполнении приведи режим файла, число отсчётов и
  ошибок, переходы с новым снимком демона и `confirmed_expiry_reactions`.
  Снимок с состоянием `fallback` и точной причиной отличается от
  `blocked`; VPN и видео требуют отдельных контрольных сеансов.
- **Шлюз** — укажи итог сравнения и категории отличий. Пассивное окно
  может совпасть с естественным изменением контроллера. Отдельно укажи
  совпадение хэшей конфигурации. Установка, новые пробы WAN,
  суточный запуск и захват трафика в этот проход не входят.

## Автоматическая публикация

Оставь на машине настройки, необработанные журналы, снимки, адреса и
пути. В отчёт включи версии, SHA, результаты фаз и агрегаты. Укажи
абсолютный путь к этому отчёту в `REPORT_SRC`, выполни блок при любом
исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-expiry-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-monitor-cdn-expiry.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre CDN expiry observation in T12'
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
