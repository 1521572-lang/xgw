#!/usr/bin/env bash
# Read-only VPN acceptance on the Ubuntu gateway. Run as the panel user.
set -uo pipefail
umask 077

. /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 || $EUID == 0 ]]; then
  echo 'Requires the Ubuntu 24.04 gateway and its ordinary panel user.' >&2
  exit 2
fi
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P) || exit 2
if [[ $# != 1 || ! $1 =~ ^[0-9a-f]{40}$ ]] ||
   [[ $(git -C "$SRC" rev-parse HEAD) != "$1" ]]; then
  echo 'Run from the pinned checkout with its full commit SHA.' >&2
  exit 2
fi
CODE=$1
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
if [[ $TEST_PY != /* || ! -x $TEST_PY ]]; then
  echo 'XGW_TEST_PYTHON must be an absolute path to an executable interpreter.' >&2
  exit 2
fi
D=$(mktemp -d "$HOME/xgw-vpn-seek.XXXXXXXX") || exit 2
printf 'Private run: %s\n' "$D"

run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}

xgw_python() { env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P "$@"; }
headless_tests() (
  cd "$SRC" || exit 2
  timeout -k 2 60 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest -q \
    -o addopts='' -p no:cacheprovider tests/test_youtube_telemetry.py -k headless
)

vpn_status() {
  systemctl is-active --quiet xgw.service || return
  systemctl is-active --quiet xgw-xray.service || return
  timeout -k 2 12 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json, sys
v = json.load(sys.stdin)
assert v["fresh"] and v["policy_matched"]
assert v["mode"] == v["engine_mode"] == v["state"] == "off"'
}

http_port() {
  local file=/etc/xgw/xray/config.json
  local -a python=("$PY" -I -B)
  [[ -r $file ]] || python=(sudo -n "${python[@]}")
  timeout -k 2 12 "${python[@]}" - "$file" <<'PY'
import json, sys
with open(sys.argv[1]) as stream:
    inbounds = json.load(stream)["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PY
}

https_control() {
  local code
  code=$(curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$PORT" --output /dev/null --write-out '%{http_code}' \
    https://example.org/) || return
  printf '%s\n' "$code"
  [[ $code == 200 ]]
}

settings() {
  local file
  for file in /etc/xgw/config.toml /etc/xgw/panel.json; do
    if [[ -r $file ]]; then sha256sum "$file" || return
    else sudo -n sha256sum "$file" || return
    fi
  done
}

stage_snapshot_tools() {
  TOOLS=$(sudo -n mktemp -d /tmp/xgw-vpn-seek-tools.XXXXXXXX) || return
  [[ $TOOLS =~ ^/tmp/xgw-vpn-seek-tools\.[[:alnum:]]{8}$ ]] || return 2
  # The archive comes from the pinned Git object. Root never imports the working tree.
  git -C "$SRC" archive "$CODE" src/xgw |
    timeout -k 2 20 sudo -n tar --no-same-owner --no-same-permissions -x -C "$TOOLS"
}

snapshot_tool() {
  timeout -k 2 15 sudo -n env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "$PY" -I -B -c 'import runpy, sys
sys.path.insert(0, sys.argv.pop(1))
runpy.run_module("xgw.desync.route_evidence", run_name="__main__", alter_sys=True)' \
    "$TOOLS/src" "$@"
}

cleanup() {
  local status=$?
  if [[ $TOOLS =~ ^/tmp/xgw-vpn-seek-tools\.[[:alnum:]]{8}$ ]]; then
    run route-tools-cleanup timeout -k 2 12 sudo -n rm -r -- "$TOOLS" || status=2
  fi
  exit "$status"
}

snapshot_off() {
  "$PY" -I -c 'import json, sys
assert json.load(sys.stdin)["client_zapret2_rule"] is False' <"$D/route-before.out"
}

flow() {
  local bounds boot pid begin end
  bounds=$("$PY" -I - "$D/route-before.out" "$D/route-after.out" <<'PY'
import json, math, sys
from pathlib import Path
from uuid import UUID

a, b = (json.loads(Path(p).read_bytes()) for p in sys.argv[1:])
boot, pid, _ = a["xray_epoch"].split(":")
assert a["xray_epoch"] == b["xray_epoch"] and int(pid) > 0, "xray_epoch"
assert 0 < b["unix"] - a["unix"] <= 180, "capture_window"
print(UUID(boot).hex, int(pid), math.floor(a["unix"]), math.ceil(b["unix"]) + 1)
PY
  ) || return
  read -r boot pid begin end <<<"$bounds"
  timeout -k 2 12 sudo -n journalctl -q --no-pager -b "$boot" -u xgw-xray.service "_PID=$pid" \
    --since "@$begin" --until "@$end" -n 5000 -o json \
    --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT >"$D/route-journal.jsonl" || return
  xgw_python -m docs.helpers.selective_flow_evidence --player "$D/play-samples.jsonl" \
    --before "$D/route-before.out" --after "$D/route-after.out" <"$D/route-journal.jsonl"
}

run play-unit headless_tests || exit 2
run sudo sudo -n true || exit 2
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" || exit 2
run vpn-lock flock -n 9 || exit 2
run vpn-before vpn_status || exit 2
run http-port http_port || exit 2
read -r PORT <"$D/http-port.out" || exit 2
run https-before https_control || exit 2
run settings-before settings || exit 2

TOOLS=
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rc=0
if run route-tools stage_snapshot_tools && run route-tools-check snapshot_tool --help &&
   run resolve timeout -k 2 65 yt-dlp --ignore-config --proxy "http://127.0.0.1:$PORT" \
     --no-playlist --socket-timeout 10 --retries 1 --extractor-retries 1 \
     -f 'bv[height=720][protocol=https]' --dump-single-json \
     'https://www.youtube.com/watch?v=8plwv25NYRo' &&
   run route-before snapshot_tool snapshot && run route-off snapshot_off; then
  run play-seek timeout -k 4 385 env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P \
    -m docs.helpers.headless_playback "$D/resolve.out" play --seconds 300 \
    --seek-forward 480 --strict --peers --samples "$D/play-samples.jsonl" &
  player_job=$!
  for tick in {1..30}; do
    kill -0 "$player_job" 2>/dev/null || break
    sleep 5
  done
  route_after_ok=0
  if run route-after snapshot_tool snapshot; then
    route_after_ok=1
  else
    rc=2
  fi
  wait "$player_job" || rc=2
  if [[ $route_after_ok == 1 && -s "$D/play-samples.jsonl" ]]; then
    run flow-seek flow || rc=2
  fi
else
  rc=2
fi

run vpn-after vpn_status || rc=2
run https-after https_control || rc=2
if run settings-after settings; then
  run settings-unchanged cmp -s "$D/settings-before.out" "$D/settings-after.out" || rc=2
else
  rc=2
fi
exit "$rc"
