#!/usr/bin/env bash
# Pin and temporarily apply the status-reader overlay on ThinkCentre.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $# == 1 && $1 =~ ^[0-9a-f]{40}$ ]]
CODE=$1
BASE=08d31ee93963bb00acb7a2275e7a554efcfb0f05
CLI_BASE=ad81542b57b3dd765ed9c115b356c9dd306aae2b
PROVEN=b614174b0dfc550c95bbabfc7f6c2a2b556a4f8d
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
UNIT=xgw-panel-reader-rollback
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$PROVEN" "$CODE"
git -C "$REPO" diff --quiet "$PROVEN" "$CODE" -- src/xgw packaging
printf 'PINNED %s | %s | %s\n' "$CODE" "$PRETTY_NAME" "$(uname -r)"
systemctl --version | sed -n '1p'
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
for timer in "$UNIT.timer" xgw-panel-login-rollback.timer; do
  if systemctl is-active --quiet "$timer"; then
    printf 'ACTIVE_ROLLBACK_TIMER %s\n' "$timer" >&2
    exit 2
  fi
done

D=$(mktemp -d "$HOME/xgw-panel-reader-installed.XXXXXXXX")
printf 'Private run: %s\n' "$D"
STAGE=
ARMED=no

step() {
  local label=$1 rc=0
  shift
  "$@" > "$D/$label.out" 2> "$D/$label.err" || rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}

overlay() {
  sudo -n "$PY" -I -B "$STAGE/code/docs/helpers/panel_installed_trial.py" "$1" "$STAGE"
}

check_http() {
  sudo -n timeout -k 3 120 "$PY" -I -B "$STAGE/code/docs/helpers/panel_installed_check.py" "$1"
}

check_session() {
  timeout -k 2 15 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P - "$1" <<'PYTHON'
import json
import sys

from xgw.desync.client import Client

client = Client()
overview = client.request("/api/zapret2/overview")["zapret2"]
keys = ("mode", "engine_mode", "state", "fresh", "policy_matched")
safe = {key: overview.get(key) for key in keys}
assert safe == dict(zip(keys, ("off", "off", "off", True, True), strict=True))
if sys.argv[1] == "candidate":
    assert client.request("/api/zapret2/status") == {"zapret2": safe}
print(json.dumps(safe, sort_keys=True))
PYTHON
}

wait_session() {
  local attempt
  for attempt in {1..10}; do
    check_session "$1" && return 0
    sleep 2
  done
  return 2
}

check_qt() {
  timeout -k 2 15 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P - <<'PYTHON'
import sys

try:
    from PyQt6.QtCore import QCoreApplication, QTimer
except ImportError:
    print("QT_NOT_AVAILABLE")
    sys.exit(0)

from xgw.gui.client import ApiClient
from xgw.gui.model import load_session, session_file

app = QCoreApplication([])
session = load_session(session_file())
assert session is not None
client = ApiClient(session)
results = []

def done(value, error):
    results.append((value, error))
    app.quit()

QTimer.singleShot(8000, app.quit)
assert client.fetch("panel-reader-test", "/api/zapret2/status", done)
app.exec()
client.close()
expected = {"mode": "off", "engine_mode": "off", "state": "off", "fresh": True,
            "policy_matched": True}
assert results == [({"zapret2": expected}, "")]
print("QT_NETWORK_OK")
PYTHON
}

snapshot_settings() {
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json /var/lib/xgw/panel-token
}

xray_pid() {
  local pid
  systemctl is-active --quiet xgw-xray.service || return
  pid=$(systemctl show xgw-xray.service --property=MainPID --value) || return
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
  printf '%s\n' "$pid"
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

controls() {
  local name=$1
  step "$name-settings" snapshot_settings &&
    step "$name-same-settings" cmp -s "$D/baseline-settings.out" "$D/$name-settings.out" &&
    step "$name-xray" xray_pid &&
    step "$name-same-xray" cmp -s "$D/baseline-xray.out" "$D/$name-xray.out" &&
    step "$name-https" https_control
}

finish() {
  local rc=$? state
  if [[ $ARMED == yes ]]; then
    if step rollback overlay rollback &&
       step restored-session wait_session restored && step restored-http check_http restored &&
       controls restored && step cancel-timer sudo -n systemctl stop "$UNIT.timer"; then
      state=$(systemctl show "$UNIT.service" --property=ActiveState --value) || state=unknown
      if [[ $state == inactive || $state == failed ]]; then
        ARMED=no
      else
        rc=2
      fi
    else
      rc=2
    fi
  fi
  if [[ $ARMED == no && -n $STAGE ]]; then
    if [[ $STAGE =~ ^/opt/xgw/handoff/panel-reader\.[A-Za-z0-9]{8}$ ]] &&
       sudo -n test ! -e "$STAGE/started" && step cleanup sudo -n rm -r -- "$STAGE"; then
      printf 'STAGE_REMOVED\n'
    else
      rc=2
    fi
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

step baseline-session check_session baseline
step baseline-settings snapshot_settings
step baseline-xray xray_pid
step baseline-https https_control
mkdir -- "$D/contracts"
git -C "$REPO" archive "$CODE" tests/test_panel_installed_trial.py \
  docs/helpers/panel_installed_trial.py docs/helpers/desync_batch1_install.py |
  tar -x -C "$D/contracts"
step contracts timeout -k 3 45 "$TEST_PY" -B -P -m pytest -p no:cacheprovider -q \
  "$D/contracts/tests/test_panel_installed_trial.py"
sudo -n install -d -m 0755 /opt/xgw/handoff
STAGE=$(sudo -n mktemp -d /opt/xgw/handoff/panel-reader.XXXXXXXX)
[[ $STAGE =~ ^/opt/xgw/handoff/panel-reader\.[A-Za-z0-9]{8}$ ]]
sudo -n install -d -m 0700 "$STAGE/code" "$STAGE/base"
git -C "$REPO" archive "$CODE" docs/helpers/desync_batch1_install.py \
  docs/helpers/panel_installed_trial.py docs/helpers/panel_installed_check.py \
  docs/helpers/t11_panel_login_check.py | sudo -n tar --no-same-owner -x -C "$STAGE/code"
listed=$(overlay paths)
mapfile -t files <<< "$listed"
git -C "$REPO" archive "$CODE" "${files[@]}" | sudo -n tar --no-same-owner -x -C "$STAGE/code"
for file in "${files[@]}"; do
  revision=$BASE
  if [[ $file == src/xgw/cli.py ]]; then revision=$CLI_BASE; fi
  if git -C "$REPO" cat-file -e "$revision:$file"; then
    git -C "$REPO" archive "$revision" "$file" | sudo -n tar --no-same-owner -x -C "$STAGE/base"
  fi
done

step baseline-http check_http baseline
step prepare overlay prepare
step arm-timer sudo -n systemd-run --collect --unit="$UNIT" --on-active=20m --service-type=oneshot \
  --property=TimeoutStartSec=360s --timer-property=AccuracySec=1s \
  "$PY" -I -B "$STAGE/code/docs/helpers/panel_installed_trial.py" rollback "$STAGE"
ARMED=yes
step timer-active systemctl is-active --quiet "$UNIT.timer"
step apply overlay apply
step candidate-ready wait_session baseline
step candidate-http check_http candidate
step candidate-session check_session candidate
step candidate-qt check_qt
controls candidate
