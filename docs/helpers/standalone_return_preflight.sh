#!/bin/bash
# Rehearse the Standalone return fix on a private copy of the installed package.
set -euo pipefail
umask 077
CODE=$1
FIX=d8a4a0967a009ec6fb1a4b6dcf81fa27e5836c5a
BR=integration/zapret2-batch1
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $CODE =~ ^[0-9a-f]{40}$ && $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$FIX" "$CODE"
D=$(mktemp -d "$HOME/xgw-standalone-overlay.XXXXXXXX")
printf 'STANDALONE_OVERLAY_HOST %s %s\nSTANDALONE_OVERLAY_CODE %s\nPRIVATE_ARTIFACTS %s\n' \
  "$PRETTY_NAME" "$(uname -r)" "$CODE" "$D"
PACKAGE=$(readlink -e /opt/xgw/lib/xgw)
[[ $PACKAGE == /opt/xgw/*/xgw && -d $PACKAGE ]]
FILES=(src/xgw/zapret2.py src/xgw/watch/standalone.py src/xgw/apply/singbox_generation.py
       src/xgw/apply/singbox_process.py src/xgw/daemon.py)
installed=()
for name in "${FILES[@]}"; do installed+=("$PACKAGE/${name#src/xgw/}"); done

sudo -n true
mkdir -p "$D/tree/src" "$D/test-root"
git -C "$REPO" archive "$CODE" tests docs/helpers packaging vpn_ui pyproject.toml | tar -x -C "$D/tree"
sudo -n timeout -k 2 30 sha256sum -- "${installed[@]}" >"$D/installed.before"
sudo -n timeout -k 3 45 tar --exclude='__pycache__' --exclude='*.pyc' \
  -C "$(dirname "$PACKAGE")" -cf - xgw |
  tar --no-same-owner --no-same-permissions -xf - -C "$D/tree/src"

verify_installed() {
  local status=$?
  trap - EXIT
  if sudo -n timeout -k 2 30 sha256sum --check --status "$D/installed.before"; then
    printf 'STANDALONE_OVERLAY_INSTALLED_UNCHANGED\n'
  else
    printf 'STANDALONE_OVERLAY_INSTALLED_NOT_VERIFIED\n'
    status=3
  fi
  exit "$status"
}
trap verify_installed EXIT

cd "$D/tree"
for index in "${!FILES[@]}"; do
  if ! sudo -n cmp -s -- "${installed[index]}" "${FILES[index]}"; then
    printf 'STANDALONE_OVERLAY_COPY_MISMATCH %s\n' "${FILES[index]}"
    exit 2
  fi
done
git -C "$REPO" diff --no-ext-diff --no-textconv --binary "$FIX^" "$FIX" -- "${FILES[@]}" \
  >"$D/return.patch"
[[ -s $D/return.patch ]]
if git -c core.autocrlf=false apply --reverse --check "$D/return.patch" \
    2>"$D/reverse.err"; then
  printf 'STANDALONE_OVERLAY_ALREADY_PRESENT\n'
elif git -c core.autocrlf=false apply --check "$D/return.patch" 2>"$D/apply.err"; then
  git -c core.autocrlf=false apply "$D/return.patch"
  git -c core.autocrlf=false apply --reverse --check "$D/return.patch"
  printf 'STANDALONE_OVERLAY_COPY_PATCHED\n'
else
  printf 'STANDALONE_OVERLAY_CONTEXT_MISMATCH\n'
  exit 2
fi

export XGW_ROOT="$D/test-root" PYTHONPATH="$D/tree/src:$D/tree:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
contracts() {
  local label=$1 rc=0
  shift
  timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    -q --tb=short "$@" >"$D/$label.out" 2>&1 || rc=$?
  printf 'STANDALONE_OVERLAY_TEST %s %s\n' "$label" "$rc"
  tail -n 4 "$D/$label.out"
  return "$rc"
}

"$PY" -B -I - "${FILES[@]}" <<'PY'
import sys
from pathlib import Path

for name in sys.argv[1:]:
    path = Path(name)
    compile(path.read_bytes(), str(path), "exec")
PY
printf 'STANDALONE_OVERLAY_COPY_COMPILES\n'

result=0
contracts status --portable tests/test_desync_standalone.py || result=2
contracts managed \
  tests/test_singbox_generations.py::test_standalone_return_keeps_legacy_until_managed_bridge_is_verified \
  || result=2
exit "$result"
