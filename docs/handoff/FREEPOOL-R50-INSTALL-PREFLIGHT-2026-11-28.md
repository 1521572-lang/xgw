# ThinkCentre · проверка Python до замены установленного XGW

Ubuntu 24.04 LTS amd64. Кандидат `6113fc7d8cce8d5fa45aea033d02ec4b0b608425`. На ThinkCentre приняты 21 контракт и сводка FreePool по ядрам. За сутки Xray дал 256 таймаутов из 287 проверенных вариантов, sing-box — 1 из 17, SSTP — 0 из 3. Свежих фаз в рабочем кеше нет. Перед обновлением писателя проверяем, что синтаксическая ошибка кандидата останавливает замену установленного кода. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/2f0097f35613315dfd5417ac922e8b794fbbb088/docs/reports/2026-11-28T103123Z_freepool-r50-backend-coverage.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. При необходимости запрашивает доступ к терминалу. Этап A выполняется без sudo в отдельном префиксе. Этап B — чтение после отдельного согласования и штатного обновления владельцем до этого кандидата. Если обновления ещё не было, опубликовать `LIVE=NOT_RUN` после этапа A.

## A. Архив и замена в отдельном префиксе

Из полного клона XGW выполнить блок. При отдельном окружении для pytest задать абсолютный путь `XGW_TEST_PYTHON`. Журналы остаются в `PRIVATE_ARTIFACTS`. Для этапа B сохранить этот каталог и взять распакованный там неизменённый архив.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=6113fc7d8cce8d5fa45aea033d02ec4b0b608425
BUNDLE=docs/handoff/artifacts/xgw-freepool-r50-install-preflight.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '41550f03f656b20d7dea3de265caf91f7bd069bce640850f88f8c3d4ba8ca89a' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging third_party vpn_ui README.md pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src:$PWD/tests" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
unset PYTHONOPTIMIZE XGW_XRAY_BIN XGW_SINGBOX_BIN XGW_TEST_FREEPOOL_XRAY

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
run CONTRACTS timeout -k 5 300 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no tests/test_install.py \
    tests/test_build_release.py tests/test_freepool_candidates.py tests/test_freepool_sources.py
tail -n 12 "$D/CONTRACTS.log"

run MANIFEST timeout -k 5 120 /usr/bin/python3 -I -B - "$PWD" "$D" <<'PY'
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
for rel in ("src/xgw/install.py", "src/xgw/apply/singbox_probe.py", "vpn_ui/qt.py"):
    assert (unpacked / "xgw" / rel).read_bytes() == (source / rel).read_bytes()
PY

if grep -qx 'MANIFEST=0' "$D/status"; then
    run MATRIX timeout -k 5 180 /usr/bin/python3 -I -B - "$D" <<'PY'
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

work = Path(sys.argv[1])
archive = work / "unpacked/xgw"
source = work / "matrix-source"
shutil.copytree(archive, source)
prefix = work / "installed"
lib = prefix / "opt/xgw/lib"
package = lib / "xgw"
launcher = prefix / "usr/local/bin/xgw"
etc = prefix / "etc/xgw"
etc.mkdir(parents=True)
config = b'[free_pool]\nmode = "observe"\n'
panel = b"{}\n"
(etc / "config.toml").write_bytes(config)
(etc / "panel.json").write_bytes(panel)

installer = """
import sys
from pathlib import Path

from xgw.config import Config
from xgw.install import Installer
from xgw.paths import Paths

source, prefix = map(Path, sys.argv[1:])
paths = Paths.from_env()
assert paths.root == prefix and paths.root != Path("/")
Installer(Config(), paths, source_root=source)._code()
"""

def install():
    env = {**os.environ, "XGW_ROOT": str(prefix), "PYTHONPATH": str(source / "src")}
    return subprocess.run([sys.executable, "-B", "-P", "-c", installer, str(source), str(prefix)],
                          env=env, capture_output=True, text=True, timeout=145)

def tree_digest():
    with_files = {}
    for path in sorted(package.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                with_files[path.relative_to(package)] = hashlib.file_digest(stream, "sha256").digest()
    return with_files

def verify_cleanup():
    assert all(not (lib / name).exists() for name in ("xgw.new", "xgw.old"))
    assert (etc / "config.toml").read_bytes() == config
    assert (etc / "panel.json").read_bytes() == panel

first = install()
assert first.returncode == 0, first.stderr
verify_cleanup()
before = tree_digest()
launcher_before = launcher.read_bytes()
assert before and (package / "_desktop/vpn_ui/qt.py").is_file()
print("CLEAN_PREFIX=PASS", flush=True)

for label, rel in (("BROKEN_CORE", "src/xgw/__main__.py"), ("BROKEN_PROTON", "vpn_ui/qt.py")):
    path = source / rel
    original = path.read_bytes()
    path.write_bytes(b"def broken(:\n")
    try:
        result = install()
        assert result.returncode != 0
        assert "SyntaxError" in result.stderr and path.name in result.stderr, result.stderr
        verify_cleanup()
        assert tree_digest() == before
        assert launcher.read_bytes() == launcher_before
    finally:
        path.write_bytes(original)
    print(label + "=PASS", flush=True)

qt = source / "vpn_ui/qt.py"
qt.write_bytes(qt.read_bytes() + b"\n# isolated update fixture\n")
retry = install()
assert retry.returncode == 0, retry.stderr
verify_cleanup()
assert (package / "_desktop/vpn_ui/qt.py").read_bytes() == qt.read_bytes()
print("RETRY=PASS", flush=True)

env = {**os.environ, "XGW_ROOT": str(prefix)}
result = subprocess.run([str(launcher), "pool", "candidates", "--checked-since", "1", "--json"],
                        env=env, capture_output=True, text=True, timeout=15, check=True)
window = json.loads(result.stdout)["check_window"]
assert window["check_phase_schema"] == 1 and window["by_backend"] == []
result = subprocess.run([str(launcher), "singbox", "--help"], env=env, capture_output=True,
                        text=True, timeout=15, check=True)
assert "probe-bridge" in result.stdout
print("INSTALLED_CLI=PASS", flush=True)
PY
    grep -xE '(CLEAN_PREFIX|BROKEN_CORE|BROKEN_PROTON|RETRY|INSTALLED_CLI)=PASS' "$D/MATRIX.log" || true
else
    echo 'MATRIX=NOT_RUN manifest failed' | tee -a "$D/status"
fi

if host_fields >"$D/host.after" 2>"$D/host.after.err" &&
    [[ -s $D/host.before ]] && cmp -s "$D/host.before" "$D/host.after"; then
    echo HOST_FIELDS=MATCH
else
    echo HOST_FIELDS=DRIFT_OR_UNKNOWN
fi
BASH
~~~

Ожидаются `CONTRACTS=0`, `MANIFEST=0`, `MATRIX=0` и пять меток PASS. При синтаксической ошибке в ядре и Proton прежний Python-комплект, launcher, TOML и JSON должны совпасть побайтно. Рабочий шлюз сверяется отдельно по полям служб. В регрессии из `tests/test_install.py` также проверяется запуск прежнего демона после отказа в модели обновления.

## B. Чтение после согласованного обновления

Этот этап применим, когда владелец уже обновил рабочий XGW до `6113fc7d8cce8d5fa45aea033d02ec4b0b608425`. Задать `XGW_PRIVATE_ARTIFACTS` как путь из A. Нужен sudo для чтения. Если доступа нет, Flash запрашивает его либо записывает конкретный блокер. Обычный интервал фоновых проверок сохранить.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
D=$XGW_PRIVATE_ARTIFACTS
[[ $D == /* && -O $D && -d $D/unpacked/xgw/src/xgw ]]
sudo -n true
for rel in install.py cli.py fetch.py watch/checks.py watch/scan.py freepool/models.py \
           freepool/pool.py freepool/traffic.py freepool/probe.py apply/singbox_probe.py; do
    if ! sudo -n cmp -s "$D/unpacked/xgw/src/xgw/$rel" "/opt/xgw/lib/xgw/$rel"; then
        echo 'LIVE=NOT_RUN installed files differ or are unreadable'
        exit 0
    fi
done
systemctl is-active --quiet xgw.service
unit() { systemctl show xgw.service -p MainPID -p InvocationID -p ExecMainStartTimestamp; }
unit >"$D/writer.unit.before"
started=$(systemctl show xgw.service -p ExecMainStartTimestamp --value)
start_epoch=$(date -d "$started" +%s)
if ! sudo -n /usr/bin/python3 -I -B - "$start_epoch" 2>"$D/writer.status.err" <<'PY'
import json
import sys
from pathlib import Path

start = int(sys.argv[1])
status = json.loads(Path("/run/xgw/status.json").read_bytes())
pool = status.get("free_pool") or {}
assert status.get("updated", 0) >= start
assert pool.get("computed_at", 0) >= start
assert pool.get("check_phase_schema") == 1
PY
then
    echo 'WRITER=NOT_CONFIRMED fresh status unavailable'
    exit 0
fi
sudo -n /usr/bin/timeout -k 2 45 /usr/local/bin/xgw pool candidates --json \
    --checked-since "$start_epoch" >"$D/writer.window.json" 2>"$D/writer.window.err"
unit >"$D/writer.unit.after"
if ! cmp -s "$D/writer.unit.before" "$D/writer.unit.after"; then
    echo 'LIVE=NOT_RUN daemon restarted during observation'
    exit 0
fi
echo WRITER=PASS
/usr/bin/python3 -I -B - "$D/writer.window.json" <<'PY'
import json
import sys
from pathlib import Path

window = json.loads(Path(sys.argv[1]).read_bytes())["check_window"]
assert window["check_phase_schema"] == 1
assert 0 <= window["schema_records"] <= window["checked"]
assert sum(group["count"] for group in window["timeout_groups"]) == window["timeouts"]
for key in ("checked", "timeouts", "schema_records"):
    assert sum(row[key] for row in window["by_backend"]) == window[key]
print(json.dumps(window, ensure_ascii=False))
print("LIVE=" + ("PASS" if window["schema_records"] else "WAITING_FOR_ROUTINE_CHECKS"))
PY
BASH
~~~

`WRITER=PASS` подтверждает схему в свежем статусе штатного демона. Для `LIVE=PASS` нужна хотя бы одна новая запись. Если таймаутов с известной фазой всё ещё нет, причина задержек остаётся открытой.

## Автоматическая публикация

Сохранить SHA карточки, SHA кандидата, SHA-256 бандла, версии Ubuntu, Python и pytest, время UTC и результаты всех фаз. При отказе приложить первую обезличенную ошибку. Приватные пути, адреса, настройки, PID и полные журналы хранить только на ThinkCentre. Задать `REPORT_SRC` как абсолютный путь к готовому обезличенному Markdown. Из полного клона выполнить блок при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_freepool-r50-install-preflight.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre XGW staged update and FreePool writer')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
