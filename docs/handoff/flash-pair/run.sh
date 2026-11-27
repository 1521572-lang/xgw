#!/usr/bin/env bash
# Run via the assignment card, in a fresh private directory.
set -euo pipefail
umask 077
export LC_ALL=C
export TZ=UTC
REPO=$(git -C "$1" rev-parse --show-toplevel)
D=$(realpath "$2")
SLOT=$3
[[ $SLOT == A || $SLOT == B ]]
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ -O "$D" && $(stat -c %a "$D") == 700 && ! -e "$D/evidence.txt" ]]
CACHE=${XDG_RUNTIME_DIR:-"$HOME/.cache"}
mkdir -p "$CACHE"
exec 9>"$CACHE/xgw-flash-pair-v1.lock"
flock -n 9 || { echo 'BUSY: retry after the other run'; exit 75; }

PKG=28bff7fa3b9e1b09f9c192c27414b27937e03ef5
CODE=21e37f97ad216b1e3b68f7903a560f87d4e2c694
OLD=7dac9eb6cd6a0cbe598cf7e0c8f6c676ef554b99
SPEC=docs/handoff/FREEPOOL-R39-PROBE-ROUTE-2026-11-27.md
BUNDLE=docs/handoff/artifacts/xgw-freepool-r39-probe-route.bundle
DIGEST=3f44e069de6976d79c83e9fabf697ee4e5cf7d8a190b3ad3b1afc86efd3dfd2a
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
unset PYTHONHOME PYTHONPATH PYTHONOPTIMIZE XGW_XRAY_BIN XGW_TEST_FREEPOOL_XRAY XGW_SINGBOX_BIN
export PYTHONNOUSERSITE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= PYTHONDONTWRITEBYTECODE=1
export XGW_ROOT="$D/isolated" TMPDIR="$D/tmp"
mkdir "$TMPDIR"

emit() { printf '%s\n' "$*" | tee -a "$D/evidence.txt"; }
host_fields() {
    local unit data
    for unit in xgw.service xgw-xray.service xgw-singbox.service xgw-singbox-blue.service xgw-singbox-green.service; do
        data=$(timeout -k 1 4 systemctl show "$unit" --property=LoadState,ActiveState,MainPID 2>/dev/null) ||
            [[ "$data" == *'LoadState=not-found'* ]] || return 1
        [[ "$data" == *'MainPID='* && "$data" == *'ActiveState='* && "$data" == *'LoadState='* ]] || return 1
        printf '%s\n%s\n' "$unit" "$data"
    done
}

emit "START slot=$SLOT utc=$(date -u +%FT%TZ) run=$(python3 -I -c 'import secrets; print(secrets.token_hex(8))')"
emit "OS=$VERSION_ID arch=$(uname -m) systemd=$(systemctl --version | awk 'NR==1 {print $2}')"
if versions=$("$PY" -B -c 'import sys, pytest; print(sys.version.split()[0], pytest.__version__)' 2>"$D/python.log"); then
    emit "PYTHON_PYTEST=$versions"
else
    emit 'PYTHON_PYTEST=UNAVAILABLE'
fi
core=0
if [[ -x "$XRAY" ]] && timeout -k 2 8 "$XRAY" version >"$D/xray.log" 2>&1; then
    core=1
    emit "XRAY=$(awk 'NR==1 {print $2}' "$D/xray.log")"
else
    emit 'XRAY=UNAVAILABLE'
fi
before=0
if host_fields >"$D/before.private"; then before=1; fi
if timeout -k 2 15 /usr/bin/python3 -I -B "$D/ranges.py" >"$D/ranges.log" 2>&1; then
    grep '^RANGE ' "$D/ranges.log" | tee -a "$D/evidence.txt"
else
    emit 'RANGES=ERROR'
fi

prepare() {
    git -C "$REPO" show "$PKG:$BUNDLE" >"$D/code.bundle" || return 1
    printf '%s  %s\n' "$DIGEST" "$D/code.bundle" | sha256sum --check - || return 1
    git -C "$REPO" bundle verify "$D/code.bundle" || return 1
    git -C "$REPO" fetch --no-tags --no-write-fetch-head "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest || return 1
    [[ $(git -C "$REPO" rev-parse "$CODE^") == "$OLD" ]] || return 1
    local rev
    for rev in "$OLD" "$CODE"; do
        mkdir "$D/$rev" || return 1
        git -C "$REPO" archive "$rev" src | tar -x -C "$D/$rev" || return 1
        git -C "$REPO" archive "$CODE" tests pyproject.toml config.example.toml docs/helpers/freepool_lifecycle.py |
            tar -x -C "$D/$rev" || return 1
    done
    git -C "$REPO" show "$PKG:$SPEC" >"$D/r39.md" || return 1
    /usr/bin/python3 -I - "$D/r39.md" "$D/route.py" <<'PY'
import ast
import sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text().splitlines()
[start] = [i for i, line in enumerate(lines) if '"$D/probe-route.log"' in line and line.endswith("<<'PYTHON'")]
code = "\n".join(lines[start + 1:lines.index("PYTHON", start + 1)]) + "\n"
ast.parse(code)
Path(sys.argv[2]).write_text(code)
PY
}

contracts() (
    local rev=$1 rc=0 log="$D/$1.log"
    cd "$D/$rev"
    export XGW_ROOT="$D/state-$rev" PYTHONPATH="$PWD/src"
    timeout -k 4 90 "$PY" -B -m pytest -o addopts= --color=no -q --tb=short --show-capture=no -p no:cacheprovider \
        tests/test_freepool_traffic.py::test_pool_outbound_keys_follow_chains \
        tests/test_freepool_traffic.py::test_pool_outbound_keys_require_the_applied_probe_route >"$log" 2>&1 || rc=$?
    emit "CONTRACT rev=$rev rc=$rc"
    # Only publish bounded pytest fields. Tracebacks with machine paths remain private.
    awk '/^(FAILED|ERROR) tests\/test_freepool_traffic.py::/ {print "NODE", $1, $2}
         /^tests\/test_freepool_traffic.py:[0-9]+: / {print "SOURCE", $1, $2}
         /^[0-9]+ (passed|failed|skipped|errors?)(,| in )/ {print "COUNTS", $0}' "$log" | tee -a "$D/evidence.txt"
)

if prepare >"$D/prepare.log" 2>&1; then
    emit "INPUT=VERIFIED control=$OLD candidate=$CODE"
    contracts "$OLD"
    contracts "$CODE"
    if (( core )); then
        tree="$D/$CODE"
        rc=0
        timeout -k 5 90 env PYTHONPATH="$tree/src:$tree/tests:$tree/docs/helpers" \
            "$PY" -B -P "$D/route.py" "$D/route-state" "$XRAY" >"$D/route.log" 2>&1 || rc=$?
        emit "XRAY_LOOPBACK_RC=$rc"
        awk '/^R39_PROBE_[A-Z_]+=PASS$/ {print}' "$D/route.log" | tee -a "$D/evidence.txt"
    else
        emit 'XRAY_LOOPBACK=NOT_RUN missing_binary'
    fi
else
    emit 'INPUT=BLOCKED see_private_prepare_log'
    emit 'CONTRACTS_AND_XRAY_LOOPBACK=NOT_RUN'
fi
if host_fields >"$D/after.private" && (( before )); then
    if cmp -s "$D/before.private" "$D/after.private"; then emit 'HOST_FIELDS=MATCH'; else emit 'HOST_FIELDS=DRIFT'; fi
else
    emit 'HOST_FIELDS=UNKNOWN'
fi
emit "END utc=$(date -u +%FT%TZ)"
sha256sum "$D/evidence.txt" | cut -d' ' -f1
