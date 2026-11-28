# ThinkCentre · кандидаты рабочего моста sing-box

Ubuntu 24.04 LTS amd64. Кандидат `1a4e197a847bbc31a3143c67be466fd2cf8d4202`. На `f59d579` прошли 113 контрактов. `preview` вернул `no_active_bridge`: в Xray было 0 портов моста, в sing-box объявлено 97. В сохранённом инвентаре было 55 совместимых с обоими ядрами записей. Теперь `preview` показывает, сколько из участников Xray сопоставляются с инвентарём однозначно и имеют объявленный прямой вход sing-box. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/2efa7b6a51505a27cf0745b7ec18231eef716838/docs/reports/2026-11-28T030259Z_singbox-bridge-admission.md)

Flash сама выполняет команды и публикует обезличенный отчёт при любом исходе. При недоступности терминала или разрешённого sudo запросить доступ. Контракты используют временный `XGW_ROOT`, а `PREVIEW` читает рабочие файлы с явно заданным `XGW_ROOT=/`. Работа с реальным шлюзом в этом задании ограничена чтением. Во время проверки читается API Xray (`lso`) и метаданные systemd. Штатные VPN, выбор выхода и службы сохраняют своё состояние. Ручной отказ `rotate` проверяется в контрактах с подставными службами.

## 1. Команды

Из полного клона XGW выполнить блок. Для контрактов можно задать `XGW_TEST_PYTHON` с pytest. `PRIVATE_ARTIFACTS` указывает на закрытые журналы. До и после просмотра и чтения API сверяются поля служб и содержимое файлов, включая сохранённый список подписок.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=1a4e197a847bbc31a3143c67be466fd2cf8d4202
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-candidates.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '3c0d33bd4b15119d288a0056e52da022b4fe43cc1bbb86a8b4e9a4f46fc3b0b4' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"

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

run CONTRACTS timeout -k 5 240 env "TMPDIR=$D/tmp" "PYTHONPATH=$PWD:$PWD/src:$PWD/tests" \
    "XGW_ROOT=$D/test-root" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_singbox_generations.py tests/test_dualcore.py
tail -n 14 "$D/CONTRACTS.log"

host_files() {
    sudo -n /usr/bin/timeout -k 2 12 /usr/bin/python3 -I -B - <<'PY'
from hashlib import sha256
from pathlib import Path

for name in (
    "/etc/xgw/config.toml",
    "/etc/xgw/panel.json",
    "/etc/xgw/xray/config.json",
    "/etc/xgw/sing-box/config.json",
    "/etc/xgw/sing-box/generation-blue.json",
    "/etc/xgw/sing-box/generation-green.json",
    "/run/xgw/singbox-generations.json",
    "/var/lib/xgw/inventory.json",
):
    try:
        print(sha256(Path(name).read_bytes()).hexdigest())
    except FileNotFoundError:
        print("absent")
PY
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
if sudo -n true 2>/dev/null; then
    files_before=0
    host_files >"$D/files.before" 2>"$D/files.before.err" || files_before=$?
    run PREVIEW sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw singbox preview
    run RUNTIME sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P - <<'PY'
from pathlib import Path

from xgw import engine
from xgw.apply import singbox_process as p
from xgw.generator import builder, validate
from xgw.paths import Paths
from xgw.xraycore.api import ApiError

paths = Paths(Path("/"))
if paths.api_dirty_file.exists() or paths.pending_config_file.exists():
    print("RUNTIME=NOT_RUN xray_state_unsettled")
    raise SystemExit(1)
state = p.read(paths)
if state["pending"] or state["draining"]:
    print("RUNTIME=NOT_RUN generation_busy")
    raise SystemExit(1)
active = state["active"]
run_token = p.generation_run(active)
xray = engine.read_json(paths.xray_config_file)
current = engine.read_json(paths.singbox_config_file)
binary = validate.find_xray(None, paths)
if run_token is None or xray is None or current is None or binary is None:
    print("RUNTIME=NOT_RUN prerequisites_unavailable")
    raise SystemExit(1)
if active == "legacy":
    active_config = current
else:
    slot_path = p.config_path(paths, active)
    active_config = engine.read_json(slot_path)
if active_config is None:
    print("RUNTIME=NOT_RUN active_config_unavailable")
    raise SystemExit(1)
try:
    live = engine.make_api(paths, binary).handler_tags("outbound")
except ApiError:
    print("RUNTIME=NOT_RUN xray_list_unavailable")
    raise SystemExit(1)
expected = {node.tag for node in builder.applied_nodes(xray)}
actual = {tag for tag in live if builder.TAG_RE.fullmatch(tag) and
          tag.startswith(("proxy-", "spare-"))}
if (p.read(paths) != state or p.generation_run(active) != run_token or
        paths.api_dirty_file.exists() or paths.pending_config_file.exists()):
    print("RUNTIME=NOT_RUN runtime_drift")
    raise SystemExit(1)
print("SINGBOX_ACTIVE_CONFIG=" +
      ("LEGACY" if active == "legacy" else "MATCH" if active_config == current else "DRIFT"))
print("XRAY_MEMBER_TAGS=" + ("MATCH" if actual == expected else "DRIFT"))
print(f"XRAY_MEMBER_TAG_COUNT={len(expected)}/{len(actual)}")
raise SystemExit(int(actual != expected or active_config != current))
PY
    files_after=0
    host_files >"$D/files.after" 2>"$D/files.after.err" || files_after=$?
    if [[ $files_before == 0 && $files_after == 0 ]]; then
        if cmp -s "$D/files.before" "$D/files.after"; then echo HOST_FILES=MATCH; else echo HOST_FILES=DRIFT; fi
    else
        echo HOST_FILES=UNKNOWN
    fi
else
    echo 'RUNTIME=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo 'PREVIEW=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo HOST_FILES=UNKNOWN
fi

after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

## 2. Что записать

| Метка | Критерий |
| --- | --- |
| `CONTRACTS` | Число тестов, пропуски и первый сбой. В новых тестах только участник с точным совпадением и прямым входом получает `prepared`. Неоднозначный префикс, отключение, удаление, фильтр, закрепление Xray, отсутствие прямого входа и запасные исключаются. |
| `PREVIEW` | Привести `active`, `candidate`, `ready`, `reason`, `bridge_ports`, `configured_bridge_ports`, `runtime_checked`. При `no_active_bridge` ожидается `runtime_checked=false`, код 1. При готовом плане ожидаются код 0, `ready=true` и `runtime_checked=true`. |
| Инвентарь и состав при `no_active_bridge` | Привести `core_mode`, числовые категории `subscription_inventory` и `bridge_admission`. `total` считает теги участников `proxy-*`, `unresolved` отмечает отсутствующее или неоднозначное сопоставление, `eligible_dual` считает разрешённые записи с обоими ядрами, `prepared` — из них записи с объявленным входом `d`. `null` означает отсутствующий либо нечитаемый инвентарь. Запасные и другие варианты входов не входят в `prepared`. В норме `prepared ≤ eligible_dual ≤ total − unresolved`. |
| `RUNTIME` | В приватном журнале сверить совпадение файла активного временного слота с общим конфигом sing-box, проверку `MainPID` и времени его запуска до и после, совпадение множества тегов участников и запасных с результатом чтения `lso` Xray. Публиковать метки `MATCH`, `DRIFT`, `LEGACY` или `NOT_RUN` и счётчики, без тегов и PID. Совпадение тегов не подтверждает совпадение параметров маршрутов или внешний HTTPS. |
| `HOST_FIELDS`, `HOST_FILES` | Опубликовать MATCH, DRIFT или UNKNOWN. При расхождении указать категорию поля или файла. Идентификаторы запусков, хэши, названия серверов и содержимое файлов оставить локально. |

Условие следующего шага

- Если `prepared > 0`, два сравнения дали `MATCH` и контроль шлюза совпал, есть участник текущего состава с объявленным прямым входом. Зафиксировать этот допуск для подготовки отдельного согласованного окна.
- Если `prepared = 0`, указать, где теряется допуск: нет однозначных совпадений, нет разрешённых совместимых участников или для них нет прямых входов. При `DRIFT` или `UNKNOWN` результат о допуске отложить до стабильного снимка.
- Указать `NOT_RUN` для функционального HTTPS через мост, подключения моста к рабочему Xray, смены поколений и физического LAN. Эти проверки относятся к согласованному окну.

## 3. Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest, Xray и sing-box, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-bridge-candidates.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre bridge candidates')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
