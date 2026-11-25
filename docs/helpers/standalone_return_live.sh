#!/bin/bash
# One guarded cycle with the five-file Standalone return patch, optionally measuring CDN.
set -euo pipefail
umask 077
CODE=$1
MODE=${2:-cycle}
FIX_BASE=d8a4a0967a009ec6fb1a4b6dcf81fa27e5836c5a^
FIX=3ccda9467cc60b75381e544b9559820fe723e120
BR=integration/zapret2-batch1
UNIT=xgw-standalone-return-rollback
OVERLAY=--standalone-return
PY=/usr/bin/python3
VIDEO=${XGW_T09_VIDEO:-8plwv25NYRo}
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $CODE =~ ^[0-9a-f]{40}$ ]]
[[ $MODE == cycle || $MODE == resume || $MODE == cdn || $MODE == cdn-pair ]]
if [[ $MODE == cdn* ]]; then
  [[ $VIDEO =~ ^[A-Za-z0-9_-]{11}$ ]]
  command -v yt-dlp >/dev/null
fi
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
recovered=0

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
    if wanted == "observed":
        ready = True
    elif wanted == "legacy_resume":
        ready = (active == "legacy" and not marker and resume and not pending and not draining
                 and not stopping and unit_state.get("xgw-singbox.service") == "active")
    elif wanted == "paused":
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
  local attempt slot=
  if (( recovered )); then
    slot=$("$PY" -I -B -c 'import json,sys; print(json.loads(sys.stdin.readlines()[-1])["active"])' \
      <"$D/recovered-managed.out") || return
    [[ $slot == blue || $slot == green ]] || return 2
  fi
  for attempt in {1..3}; do
    sudo -n timeout -k 2 8 journalctl -b -u xgw.service --since "@$RETURN_STARTED" \
      --quiet --no-pager -o cat >"$D/return-journal.out" || return
    if [[ -n $slot ]] && grep -Eq "sing-box resume committed: slot=$slot mode=(api|unchanged)$" \
        "$D/return-journal.out"; then
      grep -Eo "sing-box resume committed: slot=$slot mode=(api|unchanged)$" "$D/return-journal.out"
      printf 'STANDALONE_LIVE_RETURN_ATTRIBUTED\n'
      return 0
    fi
    sleep 1
  done
  printf 'STANDALONE_LIVE_RETURN_ATTRIBUTION_NOT_VERIFIED\n'
  return 2
}

resolve_cdn() {
  timeout -k 3 42 yt-dlp --ignore-config --proxy '' --force-ipv4 --no-playlist \
    --socket-timeout 9 --retries 0 --extractor-retries 0 \
    -f 'bv[height=720][protocol=https]' --dump-single-json "https://www.youtube.com/watch?v=$VIDEO"
}

page_probe() {
  timeout -k 2 27 "$PY" -B -P -m docs.helpers.standalone_cdn_compare page
}

snapshot() {
  sudo -n timeout -k 2 12 env "PYTHONPATH=$D/tree/src" "$PY" -B -P -m xgw.desync.route_evidence snapshot
}

queue_snapshot() {
  sudo -n timeout -k 1 4 env "PYTHONPATH=$D/tree:$D/tree/src" "$PY" -B -P \
    -m docs.helpers.cdn_queue_observation
}

sample_cdn() {
  local deadline=$1
  shift
  timeout -k 2 "$deadline" "$PY" -B -P -m docs.helpers.standalone_cdn_compare sample "$@"
}

route_observation() {
  local phase=$1 begin=$2 end=$3
  sudo -n timeout -k 2 12 journalctl -b -u xgw-xray.service --quiet --no-pager \
    --since "@$begin" --until "@$end" -n 5000 -o json \
    --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT |
    "$PY" -B -P -m docs.helpers.standalone_cdn_compare route \
      "$D/$phase-cdn.out" "$D/$phase-counters-before.out" "$D/$phase-counters-after.out"
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
      if (( recovered )); then
        if run final-topology topology managed 35; then
          printf 'STANDALONE_LIVE_FINAL_MANAGED\n'
        else
          printf 'STANDALONE_LIVE_FINAL_TOPOLOGY_NOT_VERIFIED\n'
          rc=3
        fi
      else
        run final-topology topology observed 10 || true
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
initial_topology=stable
if [[ $MODE == resume ]]; then initial_topology=legacy_resume; fi
run baseline-topology topology "$initial_topology" 25
run baseline-vpn vpn_check
format=
if [[ $MODE == cdn-pair ]]; then
  format="$D/pair-format.json"
  if ! run baseline-resolve resolve_cdn ||
     ! run vpn-prepare timeout -k 2 57 "$PY" -B -P -m docs.helpers.standalone_cdn_compare \
         prepare "$D/baseline-resolve.out" "$format"; then
    if [[ -f $D/vpn-prepare.out ]]; then cat "$D/vpn-prepare.out"; fi
    printf 'STANDALONE_LIVE_CDN_PAIR_NOT_STARTED\n'
    exit 2
  fi
  cat "$D/vpn-prepare.out"
fi
run stage stage
run before-apply-topology topology "$initial_topology" 15
RETURN_STARTED=$(date +%s)
run apply apply_trial
run candidate-files compare_package code
run candidate-off wait_off
run candidate-vpn vpn_check
if [[ $MODE != resume ]]; then
  run candidate-topology topology stable 35
  strategy=multisplit
  if [[ $MODE == cdn* ]]; then
    strategy=fake_md5
    run off-page page_probe || true
    if [[ $MODE == cdn ]]; then run off-resolve resolve_cdn || true; fi
  fi
  sudo -n systemctl is-active --quiet "$UNIT.timer"
  sudo -n touch "$BACKUP/standalone-issued"
  run standalone-on timeout -k 3 190 "$PY" -B -P -m docs.helpers.selective_admission \
    standalone "$D/standalone-receipt" --strategy "$strategy"
  run standalone-paused topology paused 30
  if [[ $MODE == cdn* ]]; then
    run direct-revision-before timeout -k 2 12 "$PY" -B -P -m docs.helpers.selective_admission \
      check-standalone "$D/standalone-receipt"
    run direct-page page_probe || true
    origin=standalone
    direct_peer=()
    if [[ $MODE == cdn-pair ]]; then
      origin=vpn
      direct_peer=(--peer-from "$format")
    elif run direct-resolve resolve_cdn; then
      format="$D/direct-resolve.out"
    elif [[ -s $D/off-resolve.out ]]; then
      format="$D/off-resolve.out"
      origin=vpn
    fi
    if [[ -n $format ]]; then
      direct_begin=$(date +%s)
      run direct-counters-before snapshot || true
      if [[ $MODE == cdn-pair ]]; then
        direct_peer+=(--wan-tcp-snapshot "$D/direct-counters-before.out")
        run direct-queue-before queue_snapshot || true
      fi
      run direct-cdn sample_cdn 32 "$format" "${direct_peer[@]}" || true
      if [[ $MODE == cdn-pair ]]; then
        run direct-queue-after queue_snapshot || true
      fi
      run direct-counters-after snapshot || true
      direct_end=$(($(date +%s) + 1))
    fi
    if run direct-revision-after timeout -k 2 12 "$PY" -B -P -m docs.helpers.selective_admission \
        check-standalone "$D/standalone-receipt"; then
      direct_revision=confirmed
    else
      direct_revision=unconfirmed
    fi
  fi
  RETURN_STARTED=$(date +%s)
  run standalone-off timeout -k 3 70 "$PY" -B -P -m docs.helpers.selective_admission \
    off "$D/standalone-receipt"
  run returned-off wait_off
  run returned-vpn vpn_check
  sudo -n touch "$BACKUP/off-confirmed"
  if [[ $MODE == cdn* && -n $format ]]; then
    off_begin=$(date +%s)
    run off-counters-before snapshot || true
    peer_record="$D/direct-cdn.out"
    if [[ $MODE == cdn-pair ]]; then peer_record=$format; fi
    run off-cdn sample_cdn 57 "$format" --peer-from "$peer_record" --retry-302 || true
    run off-counters-after snapshot || true
    off_end=$(($(date +%s) + 1))
    run cdn-comparison "$PY" -B -P -m docs.helpers.standalone_cdn_compare compare \
      "$D/direct-cdn.out" "$D/off-cdn.out" "$origin"
    cat "$D/cdn-comparison.out"
    run direct-route route_observation direct "$direct_begin" "$direct_end" || true
    run off-route route_observation off "$off_begin" "$off_end" || true
    if [[ $MODE == cdn-pair && $direct_revision == confirmed ]]; then
      run pair-verdict "$PY" -B -P -m docs.helpers.standalone_cdn_compare evaluate \
        "$D/direct-cdn.out" "$D/off-cdn.out" "$D/direct-route.out" "$D/off-route.out" \
        --queue-before "$D/direct-queue-before.out" --queue-after "$D/direct-queue-after.out" || true
      cat "$D/pair-verdict.out"
    elif [[ $MODE == cdn-pair ]]; then
      printf 'STANDALONE_LIVE_CDN_PAIR_REVISION_UNCONFIRMED\n'
    fi
    for phase in direct off; do
      run "$phase-counters-delta" "$PY" -B -P -m xgw.desync.route_evidence delta \
        "$D/$phase-counters-before.out" "$D/$phase-counters-after.out" || true
    done
  elif [[ $MODE == cdn* ]]; then
    printf 'STANDALONE_LIVE_CDN_URL_UNAVAILABLE\n'
  fi
fi
if ! run recovered-managed topology managed 240; then
  run return-attribution return_attributed || true
  exit 2
fi
recovered=1
run recovered-vpn vpn_check
run return-attribution return_attributed
printf 'STANDALONE_LIVE_MANAGED_RETURN_OK\n'
