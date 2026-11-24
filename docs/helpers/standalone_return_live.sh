#!/bin/bash
# One guarded cycle with the five-file Standalone return patch.
set -euo pipefail
umask 077
CODE=$1
FIX_BASE=d8a4a0967a009ec6fb1a4b6dcf81fa27e5836c5a^
FIX=6d25c5f2418421d80520e099b845bfa02c82283e
BR=integration/zapret2-batch1
UNIT=xgw-standalone-return-rollback
OVERLAY=--standalone-return
PY=/usr/bin/python3
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $CODE =~ ^[0-9a-f]{40}$ ]]
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$FIX" "$CODE"
D=$(mktemp -d "$HOME/xgw-standalone-live.XXXXXXXX")
printf 'STANDALONE_LIVE_HOST %s %s\nSTANDALONE_LIVE_CODE %s\nPRIVATE_ARTIFACTS %s\n' \
  "$PRETTY_NAME" "$(uname -r)" "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src docs/helpers | tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src"

run() {
  local label=$1 rc=0
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err" || rc=$?
  printf 'STANDALONE_LIVE_STEP %s %s\n' "$label" "$rc" | tee -a "$D/steps"
  return "$rc"
}

exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
run lock flock -n 9
run sudo sudo -n true
PACKAGE=$(readlink -e /opt/xgw/lib/xgw)
CFG=$(readlink -e /etc/xgw/config.toml)
PANEL=$(readlink -e /etc/xgw/panel.json)
[[ $PACKAGE == /opt/xgw/*/xgw && -d $PACKAGE ]]
FILES=(src/xgw/zapret2.py src/xgw/watch/standalone.py src/xgw/apply/singbox_generation.py
       src/xgw/apply/singbox_process.py src/xgw/daemon.py)
armed=0

wait_off() {
  timeout -k 3 85 "$PY" -B -P - <<'PY'
import http.client
import time

from docs.helpers.selective_admission import off, overview
from xgw.desync.client import Client
from xgw.desync.jobs import ACTIVE

client = Client()
deadline = time.monotonic() + 75
while time.monotonic() < deadline:
    try:
        card = overview(client)
    except (OSError, ValueError, http.client.HTTPException):
        time.sleep(2)
        continue
    if off(card) and card.get("job", {}).get("state") not in ACTIVE:
        break
    time.sleep(2)
else:
    raise SystemExit("off_not_confirmed")
PY
}

topology() {
  sudo -n timeout -k 3 "$(($2 + 15))" "$PY" -I -B - "$1" "$2" <<'PY'
import json
import subprocess
import sys
import time
from pathlib import Path

runtime = Path("/run/xgw")
state_file = runtime / "singbox-generations.json"
wanted, seconds = sys.argv[1], int(sys.argv[2])
deadline = time.monotonic() + seconds
last = None
while time.monotonic() < deadline:
    units = subprocess.check_output(
        ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend",
         "--no-pager", "xgw-singbox*.service"],
        timeout=8, text=True,
    )
    unit_state = {row[0]: row[2] for row in map(str.split, units.splitlines()) if len(row) >= 3}
    state = json.loads(state_file.read_bytes())
    active = state["active"]
    marker = (runtime / "singbox-managed").is_file()
    pending, draining = bool(state["pending"]), bool(state["draining"])
    resume = state.get("resume_managed") is True
    stopping = state.get("standalone_stopping") is True
    sample = {"active": active, "marker": marker, "pending": pending, "draining": draining,
              "resume_managed": resume, "standalone_stopping": stopping, "units": unit_state}
    if sample != last:
        print(json.dumps(sample, sort_keys=True), flush=True)
        last = sample
    if wanted == "paused":
        ready = (active == "legacy" and not marker and resume and not pending and not draining
                 and not stopping
                 and all(value in ("inactive", "failed") for value in unit_state.values()))
    else:
        managed = (active in ("blue", "green") and marker and not pending and not resume and not stopping
                   and unit_state.get(f"xgw-singbox-{active}.service") == "active")
        ready = managed and (wanted != "stable" or (
            not draining and all(name == f"xgw-singbox-{active}.service"
                                 or value in ("inactive", "failed")
                                 for name, value in unit_state.items())))
    if ready:
        raise SystemExit(0)
    time.sleep(2)
raise SystemExit("topology_not_confirmed")
PY
}

vpn_check() {
  local port http
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
  http=$(curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' https://example.org/) || return
  printf '%s\n' "$http"
  [[ $http == 200 ]]
}

return_attributed() {
  local attempt
  for attempt in {1..3}; do
    sudo -n timeout -k 2 8 journalctl -b -u xgw.service --since "@$RETURN_STARTED" \
      --quiet --no-pager -o cat >"$D/return-journal.out" || return
    if grep -F 'Возврат к поколениям sing-box: применено через API без перезапуска' \
        "$D/return-journal.out" >/dev/null; then
      printf 'STANDALONE_LIVE_RETURN_ATTRIBUTED\n'
      return 0
    fi
    sleep 1
  done
  printf 'STANDALONE_LIVE_RETURN_ATTRIBUTION_NOT_VERIFIED\n'
  return 2
}

stage() {
  local file
  sudo -n test -d /opt/xgw/handoff || sudo -n install -d -m 0755 /opt/xgw/handoff || return
  sudo -n test -d /var/lib/xgw/handoff ||
    sudo -n install -d -m 0755 /var/lib/xgw/handoff || return
  PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/standalone-live.XXXXXXXX) || return
  BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/standalone-live.XXXXXXXX) || return
  HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
  sudo -n mkdir "$PAYLOAD/base" "$PAYLOAD/code" || return
  for file in "${FILES[@]}"; do
    sudo -n install -D -m 0644 "$PACKAGE/${file#src/xgw/}" "$PAYLOAD/base/$file" &&
      sudo -n install -D -m 0644 "$PAYLOAD/base/$file" "$PAYLOAD/code/$file" || return
  done
  git -C "$REPO" archive "$CODE" docs/helpers/desync_batch1_install.py \
    docs/helpers/t11_management_restore.sh |
    sudo -n tar --no-same-owner --no-same-permissions -x -C "$PAYLOAD/code" || return
  git -C "$REPO" diff --no-ext-diff --no-textconv --binary "$FIX_BASE" "$FIX" -- "${FILES[@]}" \
    >"$D/return.patch" || return
  [[ -s $D/return.patch ]] &&
    sudo -n git -c core.autocrlf=false -C "$PAYLOAD/code" apply --check - <"$D/return.patch" &&
    sudo -n git -c core.autocrlf=false -C "$PAYLOAD/code" apply - <"$D/return.patch" &&
    sudo -n git -c core.autocrlf=false -C "$PAYLOAD/code" apply --reverse --check - <"$D/return.patch" &&
    sudo -n "$PY" -I "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
      --package "$PACKAGE" --backup "$BACKUP" &&
    sudo -n cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before" &&
    (sudo -n sha256sum "$CFG" "$PANEL" | sudo -n tee "$BACKUP/config-before.sha256" >/dev/null) &&
    sudo -n chmod 0600 "$BACKUP/config-before.sha256" || return
  sudo -n tee "$BACKUP/guard.sh" >/dev/null <<'GUARD' || return
#!/bin/bash
set -euo pipefail
backup=$1 py=$2 helper=$3 panel=$4 overlay=$5
exec 8>"$backup/standalone-phase.lock"
flock 8
[[ -e "$backup/overlay-apply-started" && ! -e "$backup/restore-completed" ]] || exit 0
if [[ -e "$backup/standalone-issued" && ! -e "$backup/off-confirmed" ]]; then
  touch "$backup/network-test-started"
fi
/bin/bash "$(dirname "$helper")/t11_management_restore.sh" "$py" "$helper" "$backup" "$panel" rollback "$overlay"
GUARD
  sudo -n chmod 0700 "$BACKUP/guard.sh" || return
  printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" >"$D/restore-location"
  sudo -n systemd-run --unit="$UNIT" --on-active=25m --timer-property=AccuracySec=1s \
    /bin/bash "$BACKUP/guard.sh" "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY" || return
  armed=1
  sudo -n systemctl is-active --quiet "$UNIT.timer"
}

apply_trial() {
  sudo -n flock "$BACKUP/standalone-phase.lock" /bin/bash -ec '
    unit=$1; backup=$2; shift 2
    systemctl is-active --quiet "$unit.timer"
    test ! -e "$backup/restore-completed"
    touch "$backup/overlay-apply-started"
    exec "$@"
  ' bash "$UNIT" "$BACKUP" "$PY" -I "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
}

compare_package() {
  local file
  for file in "${FILES[@]}"; do
    sudo -n cmp -s "$PAYLOAD/$1/$file" "$PACKAGE/${file#src/xgw/}" || return
    printf '%s\n' "$file"
  done
}

restore_on_exit() {
  local rc=$?
  trap - EXIT
  if (( armed )); then
    if sudo -n test ! -e "$BACKUP/overlay-apply-started"; then
      run unused-timer sudo -n systemctl stop "$UNIT.timer" || rc=3
    elif run restore sudo -n /bin/bash "$BACKUP/guard.sh" \
         "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY" &&
       run restore-marker sudo -n test -f "$BACKUP/restore-completed" &&
       run final-files compare_package base &&
       run final-hashes sudo -n sha256sum --check --status "$BACKUP/config-before.sha256" &&
       run final-off wait_off &&
       run final-vpn vpn_check &&
       run final-timer sudo -n systemctl stop "$UNIT.timer"; then
      printf 'STANDALONE_LIVE_FILES_AND_VPN_RESTORED\n'
      if run final-topology topology managed 35; then
        printf 'STANDALONE_LIVE_FINAL_MANAGED\n'
      else
        printf 'STANDALONE_LIVE_FINAL_TOPOLOGY_NOT_VERIFIED\n'
        rc=3
      fi
    else
      printf 'STANDALONE_LIVE_RESTORE_NOT_VERIFIED\n'
      rc=3
    fi
  fi
  exit "$rc"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

run baseline-off wait_off
run baseline-topology topology stable 25
run baseline-vpn vpn_check
run stage stage
run before-apply-topology topology stable 15
run apply apply_trial
run candidate-files compare_package code
run candidate-off wait_off
run candidate-topology topology stable 35
run candidate-vpn vpn_check
sudo -n systemctl is-active --quiet "$UNIT.timer"
sudo -n touch "$BACKUP/standalone-issued"
run standalone-on timeout -k 3 190 "$PY" -B -P -m docs.helpers.selective_admission \
  standalone "$D/standalone-receipt"
run standalone-paused topology paused 30
RETURN_STARTED=$(date +%s)
run standalone-off timeout -k 3 70 "$PY" -B -P -m docs.helpers.selective_admission \
  off "$D/standalone-receipt"
run returned-off wait_off
run returned-vpn vpn_check
sudo -n touch "$BACKUP/off-confirmed"
run recovered-managed topology managed 240
run recovered-vpn vpn_check
run return-attribution return_attributed
printf 'STANDALONE_LIVE_MANAGED_RETURN_OK\n'
