#!/usr/bin/env bash
# Temporarily validate one-time login on the installed gateway, then restore.
set -uo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
[[ $# == 1 && $1 =~ ^[0-9a-f]{40}$ ]] || exit 2
CODE=$1
SRC=$(git rev-parse --show-toplevel) || exit 2
[[ $(git -C "$SRC" rev-parse HEAD) == "$CODE" ]] || exit 2
BASE=08d31ee93963bb00acb7a2275e7a554efcfb0f05
CLI_BASE=ad81542b57b3dd765ed9c115b356c9dd306aae2b
PY=/usr/bin/python3
UNIT=xgw-panel-login-rollback
PACKAGE=$(realpath -e /opt/xgw/lib/xgw) || exit 2
D=$(mktemp -d "$HOME/xgw-panel-login-trial.XXXXXXXX") || exit 2
printf 'Private run: %s\n' "$D"
# The installed CLI predates the overlays that provide the current panel backend.
declare -A BASELINES=(
  [src/xgw/cli.py]="$CLI_BASE"
  [src/xgw/install.py]="$BASE"
  [src/xgw/watch/panel.py]="$BASE"
  [src/xgw/ui/login.html]="$BASE"
  [src/xgw/ui/app.css]="$BASE"
)
FILES=("${!BASELINES[@]}")
CONFIG=(/etc/xgw/config.toml /etc/xgw/panel.json /var/lib/xgw/panel-token)

run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}

settings() { sudo -n sha256sum "${CONFIG[@]}"; }
xray_pid() {
  local pid
  pid=$(systemctl show xgw-xray.service --property=MainPID --value) || return
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
  printf '%s\n' "$pid"
}
status() {
  systemctl is-active --quiet xgw.service && systemctl is-active --quiet xgw-xray.service &&
    timeout -k 2 12 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json, sys
view = json.load(sys.stdin)
assert view["fresh"] and view["policy_matched"]
assert view["mode"] == view["engine_mode"] == view["state"] == "off"
print("off/off fresh matched")'
}
wait_status() {
  for attempt in {1..12}; do
    status && return 0
    sleep 2
  done
  return 2
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
  printf '%s\n' "$code"
  [[ $code == 200 ]]
}

package_matches() {
  local phase=$1 file revision rc=0
  for file in "${FILES[@]}"; do
    revision=${BASELINES[$file]}
    if [[ $phase == candidate ]]; then
      revision=$CODE
    fi
    if git -C "$SRC" show "$revision:$file" | sudo -n cmp -s - "$PACKAGE/${file#src/xgw/}"; then
      printf '%s\t%s\tmatch\n' "$file" "$revision"
    else
      printf '%s\t%s\tmismatch\n' "$file" "$revision"
      rc=2
    fi
  done
  return "$rc"
}
stage() {
  local file
  PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/panel-login.XXXXXXXX) || return
  BACKUP="/var/lib/xgw/handoff/${PAYLOAD##*/}"
  sudo -n install -d -m 0700 "$PAYLOAD/code" "$PAYLOAD/base" || return
  git -C "$SRC" archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py \
    docs/helpers/t11_panel_login_check.py |
    sudo -n tar --no-same-owner --no-same-permissions -x -C "$PAYLOAD/code" || return
  for file in "${FILES[@]}"; do
    git -C "$SRC" archive "${BASELINES[$file]}" "$file" |
      sudo -n tar --no-same-owner --no-same-permissions -x -C "$PAYLOAD/base" || return
  done
  HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
  CHECK="$PAYLOAD/code/docs/helpers/t11_panel_login_check.py"
}
auth() { timeout -k 3 45 sudo -n "$PY" -I -B "$CHECK" "$1"; }
overlay() { sudo -n "$PY" -I -B "$HELPER" "$1" --panel-login --backup "$BACKUP" "${@:2}"; }

finish() {
  local rc=$?
  if run rollback overlay rollback &&
     run restored-files package_matches baseline &&
     run restored-status wait_status && run restored-auth auth restored; then
    run cancel-timer sudo -n systemctl stop "$UNIT.timer" || rc=2
  else
    rc=2
  fi
  run restored-settings settings &&
    run settings-unchanged cmp -s "$D/settings-before.out" "$D/restored-settings.out" || rc=2
  run restored-xray xray_pid &&
    run xray-unchanged cmp -s "$D/xray-before.out" "$D/restored-xray.out" || rc=2
  run restored-https https_control || rc=2
  exit "$rc"
}

exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" || exit 2
run lock flock -n 9 && run sudo sudo -n true || exit 2
if systemctl is-active --quiet "$UNIT.timer"; then
  echo 'A panel rollback timer is still active.' >&2
  exit 2
fi
run status-before status && run https-before https_control &&
  run settings-before settings && run xray-before xray_pid &&
  run baseline-files package_matches baseline || exit 2
run stage-parent sudo -n mkdir -p -- /opt/xgw/handoff /var/lib/xgw/handoff || exit 2
run stage stage && run baseline-auth auth baseline &&
  run prepare overlay prepare --payload "$PAYLOAD" --package "$PACKAGE" || exit 2
run arm-timer sudo -n systemd-run --collect --unit="$UNIT" --on-active=20m \
  --timer-property=AccuracySec=1s \
  "$PY" -I -B "$HELPER" rollback --panel-login --backup "$BACKUP" || exit 2

trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run timer-active systemctl is-active --quiet "$UNIT.timer" &&
  run apply overlay apply && run candidate-files package_matches candidate &&
  run candidate-status wait_status && run candidate-auth auth candidate &&
  run candidate-https https_control && run candidate-settings settings &&
  run candidate-settings-unchanged cmp -s "$D/settings-before.out" "$D/candidate-settings.out" &&
  run candidate-xray xray_pid &&
  run candidate-xray-unchanged cmp -s "$D/xray-before.out" "$D/candidate-xray.out"
