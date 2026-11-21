#!/usr/bin/env bash
# Run the pinned standalone panel read acceptance from a freshly fetched checkout.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf '%s | %s\n' "$PRETTY_NAME" "$(uname -r)"
sudo -n true
[[ $# == 1 && $1 =~ ^[0-9a-f]{40}$ ]]
CODE=$1
git merge-base --is-ancestor "$CODE" FETCH_HEAD
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-panel-read-sandbox.XXXXXXXX")
SRC="$WORK/source"
TOOLS=
BASELINE=no
printf 'Private run: %s\n' "$WORK"

capture_state() {
  local dir="$WORK/$1" unit pid
  mkdir -- "$dir" || return
  for unit in xgw.service xgw-xray.service; do
    systemctl is-active --quiet "$unit" || return
    pid=$(systemctl show "$unit" --property=MainPID --value) || return
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done > "$dir/pids" || return
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json \
    /var/lib/xgw/panel-token > "$dir/settings" || return
  timeout -k 2 15 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json, sys
view = json.load(sys.stdin)
keys = ("mode", "engine_mode", "state", "fresh", "policy_matched")
safe = {key: view.get(key) for key in keys}
assert safe == dict(zip(keys, ("off", "off", "off", True, True)))
print(json.dumps(safe, sort_keys=True))' > "$dir/status" || return
}

https_control() {
  local port code
  port=$(sudo -n "$PY" -I -B -c 'import json
with open("/etc/xgw/xray/config.json") as stream:
    inbounds = json.load(stream)["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)') || return
  code=$(curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" --output /dev/null --write-out '%{http_code}' \
    https://example.org/) || return
  [[ $code == 200 ]] || return 2
  printf 'HTTPS 200\n'
}

stop_transient() {
  local unit="${TOOLS##*/}.service" state
  state=$(sudo -n systemctl show "$unit" --property=ActiveState --value) || return
  if [[ $state != inactive && $state != failed ]]; then
    sudo -n timeout -k 2 8 systemctl stop "$unit" || return
    state=$(sudo -n systemctl show "$unit" --property=ActiveState --value) || return
  fi
  [[ $state == inactive || $state == failed ]]
}

finish() {
  local rc=$?
  if [[ -n $TOOLS ]]; then
    if [[ $TOOLS =~ ^/run/xgw-panel-sandbox\.[A-Za-z0-9]{8}$ ]] && stop_transient &&
       sudo -n rm -r -- "$TOOLS" && sudo -n test ! -e "$TOOLS"; then
      printf 'TOOLS_REMOVED\n'
    else
      printf 'TOOLS_CLEANUP_FAILED\n' >&2
      rc=1
    fi
  fi
  if [[ $BASELINE == yes ]]; then
    if capture_state after &&
       cmp -s "$WORK/before/pids" "$WORK/after/pids" &&
       cmp -s "$WORK/before/settings" "$WORK/after/settings" &&
       cmp -s "$WORK/before/status" "$WORK/after/status" && https_control; then
      printf 'GATEWAY_UNCHANGED\n'
    else
      printf 'GATEWAY_CONTROL_FAILED\n' >&2
      rc=1
    fi
  fi
  if [[ -d $SRC ]] && ! git -C "$REPO" worktree remove "$SRC"; then
    printf 'SOURCE_CLEANUP_FAILED\n' >&2
    rc=1
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

git -C "$REPO" worktree add --detach "$SRC" "$CODE"
printf 'PINNED %s\n' "$CODE"
capture_state before
https_control
BASELINE=yes
printf 'BASELINE_OK\n'

test_rc=0
(
  cd "$SRC"
  timeout -k 4 300 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
    -o addopts='' -p no:cacheprovider -q tests/test_panel_ipc.py \
    tests/test_panel_read_http.py tests/test_desync_event_socket.py \
    tests/test_panel.py tests/test_t11_panel_login_check.py
) | tee "$WORK/tests.out" || test_rc=$?
printf 'CONTRACT_TESTS_RC %s\n' "$test_rc"

TOOLS=$(sudo -n mktemp -d /run/xgw-panel-sandbox.XXXXXXXX)
[[ $TOOLS =~ ^/run/xgw-panel-sandbox\.[A-Za-z0-9]{8}$ ]]
git -C "$REPO" archive --format=tar "$CODE" src/xgw docs/helpers/panel_ipc_lab.py \
  packaging/panel-read-hardening.conf |
  sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$TOOLS"
sudo -n chmod 0711 "$TOOLS"
sudo -n chmod -R a+rX -- "$TOOLS/src" "$TOOLS/docs" "$TOOLS/packaging"
sudo -n timeout -k 3 55 "$PY" -I -B "$TOOLS/docs/helpers/panel_ipc_lab.py" --http-sandbox |
  tee "$WORK/isolated-http.out"
"$PY" -I - "$WORK/before/status" "$WORK/isolated-http.out" <<'PYTHON'
import json
import sys
from pathlib import Path

baseline = json.loads(Path(sys.argv[1]).read_text())
lines = Path(sys.argv[2]).read_text().splitlines()
payload, = [line.removeprefix("allowed ") for line in lines if line.startswith("allowed ")]
assert json.loads(payload) == baseline, "ISOLATED_HTTP_STATUS_MISMATCH"
print("ISOLATED_HTTP_STATUS_MATCH")
PYTHON
exit "$test_rc"
