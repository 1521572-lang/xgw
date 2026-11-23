#!/bin/bash
# Measure one 2×2 HTTPS matrix on the verified Ubuntu base, then restore it.
set -euo pipefail
umask 077
CODE=$1
BASE=3a00777c21ed017760cb7bfd0bb24478fc1f48ad
BR=integration/zapret2-batch1
OVERLAY=--selective-worker-timing
UNIT=xgw-selective-worker-timing-rollback
VIDEO=${XGW_T09_VIDEO:-8plwv25NYRo}
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $CODE =~ ^[0-9a-f]{40}$ && $VIDEO =~ ^[A-Za-z0-9_-]{11}$ && $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-t09-live.XXXXXXXX")
printf 'T09_HOST %s %s\nT09_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$(uname -r)" "$CODE" "$D"

run() {
  local label=$1 rc=0
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err" || rc=$?
  printf 'T09_STEP %s %s\n' "$label" "$rc" | tee -a "$D/steps"
  return "$rc"
}

git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$BASE" "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree/src:$D/tree:$D/tree/tests"
run contracts timeout -k 3 180 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
  "$TEST_PY" -B -P -m pytest --portable -o addopts= -p no:cacheprovider -q --tb=short \
  tests/test_desync_jobs.py tests/test_desync_worker.py tests/test_zapret2_panel.py \
  tests/test_desync_event_socket.py tests/test_desync_schema.py tests/test_selective_admission.py

exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
run live-lock flock -n 9
run sudo sudo -n true
PACKAGE=$(readlink -e /opt/xgw/lib/xgw)
CFG=$(readlink -e /etc/xgw/config.toml)
PANEL=$(readlink -e /etc/xgw/panel.json)
FILES=(src/xgw/desync/worker.py src/xgw/desync/jobs.py src/xgw/watch/zapret2_control.py)
VPN_FORMAT="$D/format.json"
FORMAT="$VPN_FORMAT"
armed=0

lease_clear() {
  local unit fields
  for unit in xgw-zapret2.service xgw-nfqws2.service; do
    fields=$(systemctl show "$unit" -p ActiveState -p MainPID) || return
    grep -Fxq 'MainPID=0' <<<"$fields" &&
      grep -Exq 'ActiveState=(inactive|failed)' <<<"$fields" || return 2
  done
}

wait_off() {
  timeout -k 3 65 "$PY" -B -P - <<'PY'
import http.client
import time
from docs.helpers.selective_admission import off, overview
from xgw.desync.client import Client
from xgw.desync.jobs import ACTIVE

client = Client()
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        card = overview(client)
    except (OSError, ValueError, http.client.HTTPException):
        time.sleep(2)
        continue
    if off(card) and card["job"]["state"] not in ACTIVE:
        break
    time.sleep(2)
else:
    raise SystemExit("off_not_confirmed")
PY
  local rc=$?
  [[ $rc == 0 ]] && lease_clear
}

compare_base() {
  local file
  for file in "${FILES[@]}" src/xgw/zapret2.py; do
    printf '%s\n' "$file"
    git -C "$REPO" show "$BASE:$file" | sudo -n cmp - "$PACKAGE/${file#src/xgw/}" || return
  done
}

snapshot() {
  sudo -n timeout -k 3 30 env "PYTHONPATH=$D/tree/src" "$PY" -B -P \
    -m xgw.desync.route_evidence snapshot
}

vpn_check() {
  local http
  snapshot >"$D/$1-before.json" &&
    http=$(curl -q -4fsS --noproxy '*' --max-time 15 --output "$D/$1-ip.txt" \
      --write-out '%{http_code}' https://api.ipify.org) &&
    printf '%s\n' "$http" && [[ $http == 200 ]] &&
    snapshot >"$D/$1-after.json" &&
    "$PY" -B -P -m xgw.desync.route_evidence delta \
      "$D/$1-before.json" "$D/$1-after.json" >"$D/$1-delta.json" &&
    "$PY" -I - "$D/$1-delta.json" <<'PY'
import json
import sys
from pathlib import Path

delta = json.loads(Path(sys.argv[1]).read_bytes())
vpn_bytes = sum(delta["groups"][group]["downlink"] or 0 for group in ("xray", "sing-box"))
assert delta["client_zapret2_rule"] is False and vpn_bytes > 0
PY
}

format_check() {
  "$PY" -B -P - "$FORMAT" "$1" <<'PY'
import sys
import time
from pathlib import Path
from docs.helpers.headless_playback import read_format
from xgw.desync.schema import youtube_cdn_expiry

url, duration, _ = read_format(Path(sys.argv[1]))
expiry = youtube_cdn_expiry(url)
assert duration >= 195 and expiry is not None and expiry - time.time() >= int(sys.argv[2])
PY
}

resolve() {
  timeout -k 3 72 yt-dlp "$@" --no-playlist --socket-timeout 10 --retries 1 \
    --extractor-retries 1 -f 'bv[height=720][protocol=https]' --dump-single-json \
    "https://www.youtube.com/watch?v=$VIDEO"
}

standalone_route_check() {
  "$PY" -B -P -m xgw.desync.route_evidence delta \
    "$D/standalone-before.out" "$D/standalone-after.out" >"$D/standalone-route.json" &&
    "$PY" -I - "$D/standalone-route.json" "$VPN_FORMAT" "$FORMAT" \
      "$D/vpn-range.out" "$D/standalone-range-pair.out" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

delta, vpn, direct, vpn_range, direct_pair = (
    json.loads(Path(file).read_bytes()) for file in sys.argv[1:]
)
downlink = delta["groups"]["zapret2"]["downlink"]
assert delta["client_zapret2_rule"] is True and (downlink or 0) > 0
vpn_peer = vpn_range.get("remote_ip")
comparison = {"same_hostname": urlsplit(vpn["url"]).hostname == urlsplit(direct["url"]).hostname,
              "same_connector_ip": (vpn_peer == direct_pair["first"]["remote_ip"]) if vpn_peer else None,
              "zapret2_downlink_delta": downlink}
print(json.dumps(comparison))
PY
}

admission() {
  timeout -k 3 390 "$PY" -B -P -m docs.helpers.selective_admission "$@"
}

stage() {
  local card_path=src/xgw/watch/zapret2_control.py
  sudo -n test -d /opt/xgw/handoff || sudo -n install -d -m 0755 /opt/xgw/handoff || return
  sudo -n test -d /var/lib/xgw/handoff ||
    sudo -n install -d -m 0755 /var/lib/xgw/handoff || return
  PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/t09-worker-timing.XXXXXXXX) || return
  BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/t09-worker-timing.XXXXXXXX) || return
  HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
  sudo -n mkdir "$PAYLOAD/code" "$PAYLOAD/base" || return
  git -C "$REPO" archive "$BASE" "${FILES[@]}" |
    sudo -n tar --no-same-owner --no-same-permissions -x -C "$PAYLOAD/base" || return
  git -C "$REPO" archive "$CODE" "${FILES[@]:0:2}" docs/helpers/desync_batch1_install.py \
      docs/helpers/t09-worker-start-card.patch docs/helpers/t11_management_restore.sh |
    sudo -n tar --no-same-owner --no-same-permissions -x -C "$PAYLOAD/code" || return
  sudo -n install -D -m 0644 "$PAYLOAD/base/$card_path" "$PAYLOAD/code/$card_path" &&
    sudo -n git -C "$PAYLOAD/code" apply --check docs/helpers/t09-worker-start-card.patch &&
    sudo -n git -C "$PAYLOAD/code" apply docs/helpers/t09-worker-start-card.patch &&
    sudo -n "$PY" -I "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
      --package "$PACKAGE" --backup "$BACKUP" &&
    sudo -n cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before" &&
    (sudo -n sha256sum "$CFG" "$PANEL" | sudo -n tee "$BACKUP/config-before.sha256" >/dev/null) &&
    sudo -n chmod 0600 "$BACKUP/config-before.sha256" || return
  sudo -n tee "$BACKUP/guard.sh" >/dev/null <<'GUARD' || return
#!/bin/bash
set -euo pipefail
backup=$1 py=$2 helper=$3 panel=$4 overlay=$5
exec 8>"$backup/t09-phase.lock"
flock 8
[[ -e "$backup/network-test-started" && ! -e "$backup/restore-completed" ]] || exit 0
mode=accept
if [[ -e "$backup/overlay-apply-started" ]]; then mode=rollback; fi
/bin/bash "$(dirname "$helper")/t11_management_restore.sh" "$py" "$helper" "$backup" "$panel" "$mode" "$overlay"
GUARD
  sudo -n chmod 0700 "$BACKUP/guard.sh" || return
  printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" >"$D/restore-location"
  sudo -n systemd-run --unit="$UNIT" --on-active=40m --timer-property=AccuracySec=1s \
    /bin/bash "$BACKUP/guard.sh" "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY" || return
  armed=1
  sudo -n systemctl is-active --quiet "$UNIT.timer"
}

apply_timing() {
  sudo -n flock "$BACKUP/t09-phase.lock" /bin/bash -ec '
    unit=$1; backup=$2; shift 2
    systemctl is-active --quiet "$unit.timer"
    test ! -e "$backup/restore-completed"
    touch "$backup/overlay-apply-started"
    exec "$@"
  ' bash "$UNIT" "$BACKUP" "$PY" -I "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
}

compare_candidate() {
  local file
  for file in "${FILES[@]}"; do
    sudo -n cmp "$PAYLOAD/code/$file" "$PACKAGE/${file#src/xgw/}" || return
    printf '%s\n' "$file"
  done
}

restore_on_exit() {
  local rc=$?
  trap - EXIT
  if (( armed )); then
    if sudo -n test ! -e "$BACKUP/network-test-started"; then
      run unused-timer sudo -n systemctl stop "$UNIT.timer" || rc=3
    elif run restore sudo -n /bin/bash "$BACKUP/guard.sh" \
         "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY" &&
       run restore-marker sudo -n test -f "$BACKUP/restore-completed" &&
       run final-hashes sudo -n sha256sum --check --status "$BACKUP/config-before.sha256" &&
       run final-base compare_base &&
       run final-off wait_off &&
       run final-vpn vpn_check vpn-final &&
       run final-timer sudo -n systemctl stop "$UNIT.timer"; then
      printf 'T09_RESTORED\n'
    else
      printf 'T09_RESTORE_NOT_VERIFIED\n'
      rc=3
    fi
  fi
  exit "$rc"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

run initial-off wait_off
run initial-base compare_base
run initial-vpn vpn_check vpn-initial
run resolve resolve
mv -- "$D/resolve.out" "$FORMAT"
run format-check format_check 1350
run vpn-range "$PY" -B -P -m docs.helpers.headless_playback "$FORMAT" probe
run vpn-range-check "$PY" -I -c \
  'import json,sys; x=json.load(open(sys.argv[1])); assert x["ok"] and (x["status"],x["bytes"])==(206,65536)' \
  "$D/vpn-range.out"

run guard stage
sudo -n touch "$BACKUP/network-test-started"
run standalone-on admission standalone "$D/standalone-receipt"
run standalone-resolve resolve --ignore-config --proxy '' --force-ipv4
FORMAT="$D/standalone-resolve.out"
run standalone-format format_check 1350
run standalone-revision-before admission check-standalone "$D/standalone-receipt"
run standalone-before snapshot
run standalone-range-pair "$PY" -B -P -m docs.helpers.headless_playback "$FORMAT" probe-pair
run standalone-after snapshot
run standalone-revision-after admission check-standalone "$D/standalone-receipt"
run standalone-route standalone_route_check
run standalone-off admission off "$D/standalone-receipt"
run standalone-off-confirmed wait_off
run base-admission admission admit "$D/base-receipt" --format "$FORMAT" --checks 2 \
  --recover-cdn-once --timeout 360
run base-rule snapshot
run base-rule-check "$PY" -I -c \
  'import json,sys; assert json.load(open(sys.argv[1]))["client_zapret2_rule"] is True' \
  "$D/base-rule.out"
run base-off admission off "$D/base-receipt"
run before-apply-off wait_off
run before-apply-format format_check 1000
run overlay-apply apply_timing
run overlay-files compare_candidate
run overlay-off wait_off
run overlay-vpn vpn_check vpn-overlay
run matrix-format format_check 940

run matrix-start "$PY" -B -P -m xgw.desync.client start \
  --candidates fake_md5 multidisorder --rounds 2 --seconds 850
wait_rc=0
run matrix-wait timeout -k 3 970 "$PY" -B -P - "$D" <<'PY' || wait_rc=$?
import http.client
import json
import re
import sys
import time
from pathlib import Path
from docs.helpers.selective_admission import overview
from xgw.desync.client import Client
from xgw.desync.jobs import ACTIVE

folder = Path(sys.argv[1])
job_id = json.loads((folder / "matrix-start.out").read_bytes())["id"]
assert re.fullmatch("[0-9a-f]{32}", job_id)
client = Client()
deadline = time.monotonic() + 940
while time.monotonic() < deadline:
    try:
        job = overview(client)["job"]
    except (OSError, ValueError, http.client.HTTPException):
        time.sleep(2)
        continue
    if job.get("id") == job_id:
        pending = folder / "job.tmp"
        pending.write_text(json.dumps(job), encoding="utf-8")
        pending.replace(folder / "job.json")
        if job["state"] not in ACTIVE:
            break
    time.sleep(2)
else:
    job = overview(client)["job"]
    if job.get("id") == job_id and job["state"] in ACTIVE:
        client.request("/api/zapret2/job/cancel", {"id": job_id})
    raise SystemExit("matrix_timeout")
PY
matrix_rc=0
if [[ -f $D/job.json ]]; then
  run matrix-summary "$PY" -B -P -m xgw.desync.client matrix --replay "$D/job.json" || matrix_rc=$?
  cat "$D/matrix-summary.out"
fi
if (( wait_rc )); then exit "$wait_rc"; fi
exit "$matrix_rc"
