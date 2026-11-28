# ThinkCentre · поставка и проверка писателя фаз FreePool R50

Ubuntu 24.04 LTS amd64. Кандидат `04d105c5834ba69911ffaf985471aec0af1b3a5a`. На ThinkCentre все 245 сохранённых за сутки таймаутов без полей фазы. Установленный файл писателя этих полей не содержит. Две отдельные пробы Xray получили ответ HTTP CONNECT и завершились таймаутом при TLS к адресу HTTPS-пробы. Задержка локализована с точки зрения клиента пробы. Причина внутри сетевого пути пока открыта. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/bfc24346ae044bfa725d16f997e9c06e175ca77d/docs/reports/2026-11-28T095636Z_freepool-r50-phase-sample.md)

Flash сама выполняет этапы и публикует обезличенный отчёт при любом исходе. Запросить доступ к терминалу или sudo, если он нужен для доступного этапа. Этап A использует тестовый префикс. Этап B выполняется после согласованного обновления рабочего демона этим кандидатом и проверяет уже установленный код чтением. При отсутствии окна или обновления завершить этап A и записать `LIVE=NOT_RUN`.

## A. Проверка поставки и писателя

Запустить из полного клона. Если pytest установлен в отдельной среде, указать `XGW_TEST_PYTHON`. Сохранить путь `PRIVATE_ARTIFACTS` для журналов и последующей сверки.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=04d105c5834ba69911ffaf985471aec0af1b3a5a
BUNDLE=docs/handoff/artifacts/xgw-freepool-r50-writer-acceptance.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '85f25d93c039792ea567c242d4ca1ff085faa3861a58fe889250cd75ccafea15' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging third_party vpn_ui README.md pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src:$PWD/tests" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
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

host_fields >"$D/host.before" 2>"$D/host.before.err" || echo HOST_FIELDS_BEFORE=UNKNOWN
run CONTRACTS timeout -k 5 200 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_freepool_candidates.py tests/test_build_release.py
tail -n 12 "$D/CONTRACTS.log"

run MANIFEST env "PYTHONPATH=$PWD/src" /usr/bin/python3 -B -P - "$PWD" "$D" <<'PY'
import runpy
import sys
import tarfile
from pathlib import Path

source, work = map(Path, sys.argv[1:])
build = runpy.run_path(str(source / "packaging/build_release.py"))
stage = work / "manifest-source"
build["stage_sources"](source, stage)
archive = work / "manifest.tar.gz"
build["write_archive"](stage, archive)
unpacked = work / "unpacked"
unpacked.mkdir()
with tarfile.open(archive) as stream:
    stream.extractall(unpacked, filter="data")
relative = "src/xgw/apply/singbox_probe.py"
assert (unpacked / "xgw" / relative).read_bytes() == (source / relative).read_bytes()
PY

if grep -qx 'MANIFEST=0' "$D/status"; then
    source="$D/unpacked/xgw"
    prefix="$D/installed"
    run INSTALL_PREFIX env "XGW_ROOT=$prefix" "PYTHONPATH=$source/src" \
        /usr/bin/python3 -B -P - "$source" <<'PY'
import sys
from pathlib import Path

from xgw.config import Config
from xgw.install import Installer
from xgw.paths import Paths

paths = Paths.from_env()
assert paths.root.is_absolute() and paths.root != Path("/")
Installer(Config(), paths, source_root=Path(sys.argv[1]))._code()
PY
    if grep -qx 'INSTALL_PREFIX=0' "$D/status"; then
        run INSTALLED_SCHEMA env "XGW_ROOT=$prefix" "PYTHONPATH=$prefix/opt/xgw/lib" \
            /usr/bin/python3 -B -P - "$prefix" <<'PY'
import sys
import time
from pathlib import Path

from xgw.apply import singbox_probe
from xgw.config import Config
from xgw.freepool import pool, probe, traffic
from xgw.freepool.models import Backend, ProviderResult, Status, Variant
from xgw.paths import Paths

prefix = Path(sys.argv[1])
assert Path(singbox_probe.__file__).is_relative_to(prefix)
assert Path(pool.__file__).is_relative_to(prefix)
cfg = Config()
cfg.free_pool.mode = "observe"
cfg.free_pool.providers = ["mahdibland"]
paths = Paths.from_env()
assert paths.root == prefix
now = int(time.time())
worker = pool.FreePool(cfg, paths, clock=lambda: now)
items = [
    Variant(provider="mahdibland", backend=Backend.XRAY, protocol="fixture", host="",
            address=f"198.51.100.{slot}", port=443, transport="tcp", name="fixture",
            country_hint="DE")
    for slot in (1, 2)
]
assert worker.store.commit(ProviderResult("mahdibland", Status.SUCCESS, items, now))
worker.store.save_candidates({items[0].variant_id: {"checked_at": now, "verdict": "TIMEOUT"}})
worker._record(items[1], probe.Outcome(
    "TIMEOUT", stage="download", probe_kind="timeout", probe_phase="tls",
))
report = traffic.candidate_report(cfg, paths, now, checked_since=now)["check_window"]
assert worker.summary()["check_phase_schema"] == report["check_phase_schema"] == 1
assert (report["checked"], report["timeouts"], report["schema_records"]) == (2, 2, 1)
assert {row["phase"] for row in report["timeout_groups"]} == {"unknown", "tls"}
print("INSTALLED_SCHEMA=PASS legacy=1 new=1 bridge_import=PASS")
PY
        run BRIDGE_CLI env XGW_ROOT="$prefix" "$prefix/usr/local/bin/xgw" singbox --help
        if grep -q 'probe-bridge' "$D/BRIDGE_CLI.log"; then echo 'BRIDGE_HELP=PASS'
        else echo 'BRIDGE_HELP=FAIL'; fi
    else
        echo 'INSTALLED_SCHEMA=NOT_RUN install prefix failed'
    fi
else
    echo 'INSTALL_PREFIX=NOT_RUN manifest failed'
fi

if host_fields >"$D/host.after" 2>"$D/host.after.err" &&
   [[ -s $D/host.before ]] && cmp -s "$D/host.before" "$D/host.after"; then
    echo HOST_FIELDS=MATCH
else
    echo HOST_FIELDS=DRIFT_OR_UNKNOWN
fi
BASH
~~~

## B. Чтение после согласованного рабочего обновления

Задать `XGW_PRIVATE_ARTIFACTS` как путь из A. Запустить после согласованного обновления, когда штатный xgw.service уже запущен. Этот блок подтверждает совпадение установленных файлов, схему из опубликованного демоном статуса и новые записи с момента запуска. Старая версия или отсутствие нового статуса отмечаются отдельно. Сохранённые данные могут появиться при следующей плановой проверке пула. При ожидании результатов оставить прежний интервал проверок.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
D=$XGW_PRIVATE_ARTIFACTS
[[ $D == /* && -O $D && -d $D/unpacked/xgw ]]
sudo -n true
state=$(systemctl show xgw.service -p ActiveState --value)
[[ $state == active ]]
for rel in cli.py fetch.py watch/checks.py watch/scan.py freepool/models.py \
           freepool/pool.py freepool/traffic.py freepool/probe.py apply/singbox_probe.py; do
    if ! sudo -n cmp -s "$D/unpacked/xgw/src/xgw/$rel" "/opt/xgw/lib/xgw/$rel"; then
        echo 'LIVE=NOT_RUN installed files differ'
        exit 0
    fi
done
systemctl show xgw.service -p MainPID -p InvocationID >"$D/writer.unit.before"
started=$(systemctl show xgw.service -p ExecMainStartTimestamp --value)
start_epoch=$(date -d "$started" +%s)
stop=$(( SECONDS + 120 ))
until sudo -n /usr/bin/python3 -I -B - "$start_epoch" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path("/run/xgw/status.json").read_bytes())
pool = status.get("free_pool") or {}
assert status.get("updated", 0) >= int(sys.argv[1])
assert pool.get("computed_at", 0) >= int(sys.argv[1])
assert pool.get("check_phase_schema") == 1
PY
do
    if (( SECONDS >= stop )); then echo 'WRITER=NOT_CONFIRMED'; exit 0; fi
    sleep 5
done 2>"$D/writer.status.err"
sudo -n /usr/bin/timeout -k 2 45 /usr/local/bin/xgw pool candidates \
    --checked-since "$start_epoch" --json >"$D/writer.window.json" 2>"$D/writer.window.err"
systemctl show xgw.service -p MainPID -p InvocationID >"$D/writer.unit.after"
if ! cmp -s "$D/writer.unit.before" "$D/writer.unit.after"; then
    echo 'LIVE=NOT_RUN daemon restarted during observation'
    exit 0
fi
echo WRITER=PASS
/usr/bin/python3 -I -B - "$D/writer.window.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    window = json.load(f)["check_window"]
assert window["check_phase_schema"] == 1
assert 0 <= window["schema_records"] <= window["checked"]
assert sum(row["count"] for row in window["timeout_groups"]) == window["timeouts"]
print(json.dumps(window, ensure_ascii=False))
print("LIVE=" + ("PASS" if window["schema_records"] else "WAITING_FOR_ROUTINE_CHECKS"))
PY
BASH
~~~

## Критерии

В отчёт включить число контрактов и первый сбой, результаты `MANIFEST`, `INSTALL_PREFIX`, `INSTALLED_SCHEMA`, `BRIDGE_HELP` и сверку полей служб. В тестовом кеше прежний таймаут остаётся с фазой `unknown`, новый даёт `tls` и учитывается в `schema_records`.

При доступном этапе B указать `WRITER`, `LIVE`, число свежих записей новой схемы и категории таймаутов. При `WAITING_FOR_ROUTINE_CHECKS` нужен повтор чтения после штатных проверок. Если свежие таймауты отсутствуют, подтвердить работу писателя по новым записям и оставить причину сетевых отказов открытой. Указать контроль обычного VPN из отчёта рабочего обновления, если он уже доступен. В отчёте сохранять агрегаты, версии и SHA тестового ТЗ и бандла.

## Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest и использованных ядер, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_freepool-r50-writer-acceptance.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre FreePool writer acceptance')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
