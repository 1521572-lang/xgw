#!/bin/bash
# Validate ALT9 with the installed worker in a private loopback namespace.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=$1
[[ $CODE =~ ^[0-9a-f]{40}$ ]]
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-match.XXXXXXXX")
printf 'FLOWSEAL_POLICY_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"

state() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
  sudo -n /bin/bash -ec '
    file=/proc/net/netfilter/nfnetlink_queue
    if [[ -r $file ]]; then awk "{print \$1, \$2}" "$file" | sort; fi
  '
}

vpn() {
  local port status
  port=$(sudo -n "$PY" -I -B - <<'PY'
import json
from pathlib import Path

inbounds = json.loads(Path("/etc/xgw/xray/config.json").read_bytes())["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PY
  ) || return
  status=$(curl -q -4fsS --max-time 12 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' https://example.org/) || return
  printf '%s\n' "$status"
  [[ $status == 200 ]]
}

state >"$D/before.state"
vpn >"$D/before.https" || true
if timeout -k 2 8 /opt/xgw/zapret2/1.0.7/nfqws2 --version >"$D/engine.out" 2>&1; then
  head -n 1 "$D/engine.out"
fi
tests=0
timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
  PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest \
  --portable -o addopts= -p no:cacheprovider -q --tb=short \
  tests/test_desync_flowseal.py tests/test_desync_schema.py \
  tests/test_zapret2_management.py tests/test_desync_standalone.py \
  >"$D/contracts.out" 2>&1 || tests=$?
tail -n 6 "$D/contracts.out"
printf 'FLOWSEAL_POLICY_CONTRACTS_EXIT %s\n' "$tests"

LAB=$(sudo -n mktemp -d /run/xgw-flowseal-policy.XXXXXXXX)
sudo -n mkdir "$LAB/code"
git -C "$REPO" archive "$CODE" src docs/helpers/flowseal_policy_check.py docs/helpers/flowseal_policy_match.py |
  sudo -n tar --no-same-owner --no-same-permissions -x -C "$LAB/code"
HOST_NETNS=$(stat -Lc %i /proc/self/ns/net)
lab=0
sudo -n /usr/bin/timeout -k 3 140 /usr/bin/unshare --net /usr/bin/env \
  "PYTHONPATH=$LAB/code/src:$LAB/code" "$PY" -B -P "$LAB/code/docs/helpers/flowseal_policy_check.py" \
  --out "$LAB" --host-netns "$HOST_NETNS" --match >"$D/lab.out" 2>"$D/lab.err" || lab=$?
cat "$D/lab.out"
printf 'FLOWSEAL_POLICY_LAB_EXIT %s\n' "$lab"

state >"$D/after.state"
vpn >"$D/after.https" || true
if cmp -s "$D/before.state" "$D/after.state"; then
  printf 'FLOWSEAL_POLICY_GATEWAY_UNCHANGED\n'
else
  printf 'FLOWSEAL_POLICY_GATEWAY_STATE_DIFFERED\n'
fi
if grep -Fxq 200 "$D/before.https" && grep -Fxq 200 "$D/after.https"; then
  printf 'FLOWSEAL_POLICY_HTTPS_200\n'
else
  printf 'FLOWSEAL_POLICY_HTTPS_NOT_VERIFIED\n'
fi
[[ $tests == 0 && $lab == 0 ]] && cmp -s "$D/before.state" "$D/after.state" &&
  grep -Fxq 200 "$D/before.https" && grep -Fxq 200 "$D/after.https"
