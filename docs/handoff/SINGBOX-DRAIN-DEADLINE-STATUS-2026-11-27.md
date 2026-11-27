# ThinkCentre · последняя выборка и статус поколений sing-box

**Ubuntu 24.04 LTS amd64. Кандидат `a1513402062653683eb097d6f3c710d90afc9524`.** На предыдущей ревизии прошли 167 тестов и изолированный стенд с двумя sing-box 1.14.5. По журналу прежней медиапары снятие drain произошло за 0,16 секунды до окончания наблюдения и не попало в последний снимок. Этот проход проверяет выборку на границе срока и отображение причины ожидания в штатном формате статуса. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/791d964601db04a0611876598fc71b767fd52b74/docs/reports/2026-11-27T173530Z_singbox-drain-diagnostics.md)

Flash сама выполняет команды, анализирует журналы и публикует один обезличенный отчёт при любом исходе. При недоступности терминала, прав чтения или GitHub запросить доступ и продолжить доступные этапы. Кандидат запускается из приватной копии. Во время проверки рабочая конфигурация и службы наблюдаются чтением.

## 1. Проверка на ThinkCentre

Выполнить из полного клона XGW. При необходимости заранее указать абсолютный путь к Python с pytest в `XGW_TEST_PYTHON` и самостоятельно получить права чтения с помощью `sudo -v`. Сохранить напечатанный приватный путь. Установленные ядра и ОС записать по фактическим данным.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=a1513402062653683eb097d6f3c710d90afc9524
BUNDLE=docs/handoff/artifacts/xgw-singbox-drain-status.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-singbox-drain-status.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '5c5560bb136d3240f185b0f34ecf724dca13022362647b71c80b8a19ff7b68a6' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
unset XGW_XRAY_BIN XGW_SINGBOX_BIN XGW_TEST_FREEPOOL_XRAY PYTHONOPTIMIZE

run() {
    local label=$1 rc=0
    shift
    "$@" >"$D/$label.log" 2>&1 || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/status"
}

host_fields() {
    local unit fields
    for unit in xgw.service xgw-xray.service xgw-singbox.service \
                xgw-singbox-blue.service xgw-singbox-green.service; do
        fields=$(timeout -k 1 4 systemctl show "$unit" -p LoadState -p ActiveState -p MainPID) ||
            [[ "$fields" == *'LoadState=not-found'* ]] || return 1
        [[ "$fields" == *'LoadState='* && "$fields" == *'ActiveState='* && "$fields" == *'MainPID='* ]] ||
            return 1
        printf '%s\n%s\n' "$unit" "$fields"
    done
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q \
    src/xgw/apply/singbox_process.py src/xgw/watch/status.py docs/helpers/standalone_topology.py

pytest_run() {
    timeout -k 5 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --color=no -v -rs -rfE --tb=short --show-capture=no "$@"
}
run BOUNDARY pytest_run tests/test_standalone_topology.py::test_stable_takes_final_sample_at_the_deadline
run STATUS_CONTRACTS pytest_run \
    tests/test_singbox_generations.py::test_drain_summary_preserves_countdown_and_exposes_blocker \
    tests/test_dualcore.py::test_status_has_a_line_about_the_second_core
run REGRESSIONS pytest_run tests/test_singbox_generations.py tests/test_standalone_topology.py \
    tests/test_desync_standalone.py tests/test_singbox.py tests/test_runtime.py \
    tests/test_standalone_cdn_compare.py tests/test_dualcore.py
for test_log in BOUNDARY STATUS_CONTRACTS REGRESSIONS; do
    tail -n 8 "$D/$test_log.log"
done

read_host() {
    sudo -n timeout -k 3 30 env -u XGW_ROOT "PYTHONPATH=$PWD:$PWD/src" /usr/bin/python3 -B -P "$@"
}
run HOST_JSON read_host -m xgw status --json
run HOST_TEXT read_host -m xgw status
run HOST_OBSERVED read_host -m docs.helpers.standalone_topology observed 5
run HOST_COMPARE /usr/bin/python3 -I -B - "$D/HOST_JSON.log" "$D/HOST_OBSERVED.log" <<'PYTHON'
import json
import sys
from pathlib import Path

status, observed = (json.loads(Path(name).read_bytes()) for name in sys.argv[1:])
g = status["singbox"]["generations"]
phases = ("none", "deadline_unknown", "grace_period", "api_dirty", "old_ports_unknown",
          "config_unavailable", "old_bridge_referenced", "awaiting_cleanup")
slots = ("legacy", "blue", "green")
assert g["active"] in slots and (g["draining"] is None or g["draining"] in slots)
assert g["drain_phase"] in phases and type(g["drain_left_s"]) is int and g["drain_left_s"] >= 0
match = (g["active"], g["draining"], g["drain_phase"]) == (
    observed["active"], observed["drain_slot"], observed["drain_phase"])
print(json.dumps({"active": g["active"], "draining": g["draining"],
                  "phase": g["drain_phase"], "left_s": g["drain_left_s"],
                  "same_observation": match}))
PYTHON
if grep -Fxq 'HOST_COMPARE=0' "$D/status"; then cat "$D/HOST_COMPARE.log"; fi
after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

Если чтение stdout не разобралось, посмотреть свой приватный лог и указать код, фазу и причину. Если между чтениями менялся слот или фаза, записать `same_observation=false` и допустим один повтор чтения после штатного перехода. Состояние работающего шлюза оставить владельцу.

## 2. Критерии

| Этап | Что записать |
| --- | --- |
| `BOUNDARY` | Два сценария, порядок выборок 0, 2, 4, 5 с и итог. Снятие drain между предпоследней выборкой и концом окна даёт `stable`. При продолжающемся drain возвращается `topology_not_confirmed` после финального чтения. |
| `STATUS_CONTRACTS` | Таймер в JSON по-прежнему числовой. `drain_phase` показывает прежний мост в конфиге и неизвестный срок. CLI показывает причину ожидания при известной фазе и читает старый статус без этого поля. |
| `REGRESSIONS` | Число passed/failed/skipped, первый сбой и зависимость. |
| Штатные чтения | `HOST_JSON`, `HOST_TEXT`, `HOST_OBSERVED`, итог сравнения слотов и фаз, итог пяти юнитов до/после. При покое ожидается `phase=none` и `left_s=0`. Формулировки активного drain проверяются контрактами, если живого перехода в окне не наблюдалось. |
| Остаток | Живой переход рабочих поколений и прямой CDN в этом проходе `NOT_RUN`. При несоответствии чтений указать наблюдавшиеся категории. |

## 3. Автоматическая публикация

Подготовить непустой Markdown и задать в `REPORT_SRC` его абсолютный путь. Включить SHA ТЗ и кандидата, версии, исход каждой фазы, время и конкретные причины пропусков. Публикуются только названия фаз, версии, слоты и агрегаты. Адреса, PID, конфиги, полный статус, журналы и локальные пути остаются на ThinkCentre.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-drain-deadline-status.md
  export GIT_INDEX_FILE="$pub/index"
  blob=$(git -C "$repo" hash-object -w -- "$REPORT_SRC")
  local_ref=refs/xgw-report/$(basename "$pub")
  trap 'git -C "$repo" update-ref -d "$local_ref"' EXIT
  for i in 1 2 3; do
    git -C "$repo" fetch --quiet --no-tags --no-write-fetch-head origin "$ref:$local_ref"
    tip=$(git -C "$repo" rev-parse "$local_ref")
    if prev=$(git -C "$repo" rev-parse --verify "$tip:$file" 2>/dev/null); then
      [[ $prev == "$blob" ]] || exit 1
      printf 'PUBLISHED %s %s\n' "$tip" "$file"
      exit 0
    fi
    git -C "$repo" read-tree "$tip"
    git -C "$repo" update-index --add --cacheinfo "100644,$blob,$file"
    tree=$(git -C "$repo" write-tree)
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre sing-box drain deadline and status')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

Выполнить публикацию также при блокере или частичном исходе. Если не хватает прав записи, запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
