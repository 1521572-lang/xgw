#!/usr/bin/env bash
# Install an accepted, narrowly scoped diagnostics update on ThinkCentre.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $# == 1 || $# == 2 ]]
[[ $1 =~ ^[0-9a-f]{40}$ ]]
CODE=$1
TEST_CODE=$CODE
PROFILE=${2:---pin-audit}
case "$PROFILE" in
  --pin-audit)
    SCOPE=pin-audit
    PREFIX=PIN_AUDIT
    BASE=a2f37021cf119342d2f8344c91d26bafc12c3673
    ACCEPTED=4a6636f2a7b2302b714436584c393731233cc6a0
    FILES=(actions.py cli.py daemon.py gui/model.py tray.py ui/app.js
           watch/notify.py watch/panel.py watch/states.py)
    TEST_FILES=(docs/helpers/leak_cause_check.py tests/test_daemon_main.py
                tests/test_cli_commands.py tests/test_leak_incident.py)
    NODES=(tests/test_leak_incident.py
           tests/test_daemon.py::test_server_exiting_at_home_is_replaced_and_not_taken_back
           tests/test_daemon.py::test_leak_reports_success_only_after_the_rules_are_confirmed
           tests/test_daemon.py::test_home_exit_without_route_evidence_does_not_claim_bypass
           tests/test_cli_commands.py::test_pin_and_unpin
           tests/test_cli_commands.py::test_pin_api_error
           tests/test_panel.py::test_pin_goes_through_the_same_code_as_the_command
           tests/test_daemon.py::test_pin_expires_and_is_restored_after_apply
           tests/test_daemon.py::test_pin_is_dropped_when_node_leaves_balancer
           tests/test_daemon_main.py::test_main_is_released_when_no_member_answers)
    EXPECTED=13
    ;;
  --watchdog-wake|--watchdog-timing|--watchdog-scan|--watchdog-wan|--watchdog-scan-slot)
    SCOPE=watchdog-wake
    PREFIX=WATCHDOG_WAKE
    BASE=c7a0d3fccd30ae9e21aa26b01f0d97d779b58b61
    ACCEPTED=c69ff9a75dbeec702f0490f8691144d247b0835d
    FILES=(daemon.py)
    TEST_FILES=(docs/helpers/audit_host_observe.py tests/test_audit_host_observe.py
                tests/test_net.py)
    NODES=(tests/test_audit_host_observe.py
           tests/test_daemon.py::test_watchdog_wake_progress_keeps_first_arrival_and_batch
           tests/test_daemon.py::test_rules_event_restores_rules_right_away
           tests/test_daemon.py::test_net_event_starts_the_step_early_but_not_too_often
           tests/test_daemon.py::test_wake_after_resume_reloads_rules_and_scans
           tests/test_daemon.py::test_watchdog_schedule_includes_step_work_in_interval
           tests/test_net.py::test_iprule_ensure_removes_duplicates_and_ignores_foreign_rules
           tests/test_net.py::test_tun_and_its_route_come_back_after_xray_starts_again
           tests/test_net.py::test_loaded_notices_a_lost_interface_route_or_tproxy)
    EXPECTED=15
    if [[ $PROFILE != --watchdog-wake ]]; then
      SCOPE=watchdog-timing
      PREFIX=WATCHDOG_TIMING
      BASE=c69ff9a75dbeec702f0490f8691144d247b0835d
      ACCEPTED=6de2c66658f9889a42e906859e480ed05714d84d
      TEST_FILES+=(docs/helpers/watchdog_progress_gate.py tests/test_watchdog_progress_gate.py)
      NODES+=(tests/test_daemon.py::test_watchdog_reports_tick_overlap_and_separate_rules_check
              tests/test_watchdog_progress_gate.py)
      EXPECTED=22
      if [[ $PROFILE != --watchdog-timing ]]; then
        SCOPE=watchdog-scan
        PREFIX=WATCHDOG_SCAN
        BASE=6de2c66658f9889a42e906859e480ed05714d84d
        ACCEPTED=da6d12a21d0fb2fbdc7c4048737b02ecf9835629
        TEST_FILES+=(tests/test_scan_pacing.py)
        NODES+=(tests/test_scan_pacing.py tests/test_daemon.py::test_scan_does_not_block_watchdog)
        EXPECTED=30
        if [[ $PROFILE != --watchdog-scan ]]; then
          SCOPE=watchdog-wan
          PREFIX=WATCHDOG_WAN
          BASE=da6d12a21d0fb2fbdc7c4048737b02ecf9835629
          ACCEPTED=1fc8fa526f8353ade444f351f5509e9627059486
          TEST_FILES+=(tests/test_daemon_main.py tests/test_dualcore.py tests/test_tspu.py)
          NODES+=(tests/test_tspu.py::test_wan_is_down_only_when_every_check_host_is_down
                  tests/test_tspu.py::test_provider_rechecks_last_success_then_falls_back_in_config_order
                  tests/test_tspu.py::test_e2e_tries_another_host_and_rests_the_one_that_answered_403
                  tests/test_tspu.py::test_e2e_timings_distinguish_primary_and_fallback)
          EXPECTED=34
          if [[ $PROFILE == --watchdog-scan-slot ]]; then
            SCOPE=watchdog-scan-slot
            PREFIX=WATCHDOG_SCAN_SLOT
            BASE=1fc8fa526f8353ade444f351f5509e9627059486
            ACCEPTED=aa2a3ab4fc6c46134c5949283b2b6e8b658f250c
            EXPECTED=39
          else
            TEST_CODE=adf8e8b86867904324a9a62b6701e55e8ce8bb91
          fi
        else
          TEST_CODE=201c3d0d873ae8e6ea8df6042d0de856545f9d46
        fi
      else
        TEST_CODE=fd48a39d753ab49bdd4f64571d063b970203f74f
      fi
    else
      TEST_CODE=bb7508e1901f23dc078da8881d808dc6c7e0d8c5
    fi
    ;;
  *) exit 2 ;;
esac
REPO=$(git rev-parse --show-toplevel)
PACKAGE=/opt/xgw/lib/xgw
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
UNIT="xgw-$SCOPE-rollback"
INSTALLER=docs/helpers/desync_batch1_install.py
PATHS=("${FILES[@]/#/src/xgw/}")
[[ $TEST_PY == /* && -x $TEST_PY ]]
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$ACCEPTED" "$CODE"
[[ $(git -C "$REPO" diff --name-only "$BASE" "$ACCEPTED" -- src/xgw) == \
   "$(printf '%s\n' "${PATHS[@]}")" ]]
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9

D=$(mktemp -d "$HOME/xgw-$SCOPE-install.XXXXXXXX")
printf 'PINNED %s | %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$(uname -r)" "$D"
mkdir -p "$D/tree/src" "$D/base"
tar -C /opt/xgw/lib --exclude=__pycache__ -cf - xgw | tar -C "$D/tree/src" -xf -
[[ -z $(find "$D/tree/src/xgw" ! -type d ! -type f -print -quit) ]]
git -C "$REPO" archive "$TEST_CODE" pyproject.toml \
  tests/conftest.py tests/links.py tests/fakenet.py tests/fakexray.py \
  tests/test_daemon.py tests/test_panel.py "${TEST_FILES[@]}" | tar -x -C "$D/tree"
git -C "$REPO" show "$CODE:$INSTALLER" >"$D/tree/$INSTALLER"
git -C "$REPO" diff --no-ext-diff --no-textconv "$BASE" "$ACCEPTED" -- "${PATHS[@]}" > "$D/audit.patch"
cd "$D/tree"
for path in "${PATHS[@]}"; do
  install -D -m 0600 "$path" "$D/base/$path"
done
if git -c core.autocrlf=false apply --reverse --check "$D/audit.patch" >/dev/null 2>"$D/reverse.err"; then
  printf '%s_ALREADY_PRESENT\n' "$PREFIX"
  present=yes
elif git -c core.autocrlf=false apply --check "$D/audit.patch" 2>"$D/patch.err"; then
  git -c core.autocrlf=false apply "$D/audit.patch"
  printf '%s_PATCH_APPLIED_TO_PRIVATE_COPY\n' "$PREFIX"
  present=no
else
  printf '%s_BASELINE_MISMATCH\n' "$PREFIX"
  exit 2
fi
timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
  "PYTHONPATH=$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest -o addopts= \
  --rootdir "$D/tree" -p no:cacheprovider -q --tb=short \
  "${NODES[@]}" | tee "$D/contracts.out"
grep -q "^$EXPECTED passed in " "$D/contracts.out"
printf '%s_CONTRACTS_OK\n' "$PREFIX"

pid() {
  local value
  systemctl is-active --quiet "$1" || return
  value=$(systemctl show "$1" -p MainPID --value) || return
  [[ $value =~ ^[1-9][0-9]*$ ]] || return 2
  printf '%s\n' "$value"
}

wait_status() {
  local release_at=$1 attempt
  for attempt in {1..30}; do
    if sudo -n "$PY" -I -B - "$release_at" <<'PYTHON'
import json
import sys
import time
from pathlib import Path
try:
    status = json.loads(Path("/run/xgw/status.json").read_bytes())
    updated = status["updated"]
    accepted = (updated >= float(sys.argv[1]) and 0 <= time.time() - updated <= 180
                and status["state"] in {"HEALTHY", "DEGRADED"}
                and status["xray"]["ok"] is True and not status.get("pin"))
except (OSError, ValueError, KeyError, TypeError):
    accepted = False
raise SystemExit(not accepted)
PYTHON
    then
      return 0
    fi
    sleep 2
  done
  printf '%s_STATUS_TIMEOUT\n' "$PREFIX" >&2
  return 2
}

check_wake_progress() {
  [[ $PROFILE != --pin-audit ]] || return 0
  if [[ $PROFILE != --watchdog-wake ]]; then
    local started_us
    if ! started_us=$(systemctl show xgw.service -p ExecMainStartTimestampMonotonic --value) ||
       [[ ! $started_us =~ ^[1-9][0-9]*$ ]]; then
      printf '%s_PROGRESS_UNAVAILABLE result=unknown_process_start\n' "$PREFIX" >&2
      return 2
    fi
    local progress_args=("$started_us")
    if [[ $PROFILE == --watchdog-scan ]]; then
      progress_args+=(--details)
    elif [[ $PROFILE == --watchdog-wan ]]; then
      progress_args+=(--provider)
    elif [[ $PROFILE == --watchdog-scan-slot ]]; then
      progress_args+=(--scan-slot)
    fi
    if ! git -C "$REPO" show "$CODE:docs/helpers/watchdog_progress_gate.py" |
         sudo -n /usr/bin/timeout -k 3 125 "$PY" -I -B - "${progress_args[@]}"; then
      printf '%s_PROGRESS_UNAVAILABLE\n' "$PREFIX" >&2
      return 2
    fi
    printf '%s_PROGRESS_OK\n' "$PREFIX"
    return 0
  fi
  if ! sudo -n "$PY" -I -B - <<'PYTHON'
import json
import os
import stat
import time
from pathlib import Path

try:
    with Path("/run/xgw/watchdog-step.json").open("rb") as stream:
        row = json.load(stream)
        mode = stat.S_IMODE(os.fstat(stream.fileno()).st_mode)
    at = row["at"]
    generation = row["generation"]
    wake = row["wake"]
    valid = (mode == 0o600 and type(generation) is int and generation > 0
             and row["phase"] in ("tick", "sleep")
             and type(at) in (int, float) and 0 <= time.monotonic() - at <= 180
             and (wake is None or isinstance(wake, dict)))
except (OSError, ValueError, KeyError, TypeError):
    valid = False
raise SystemExit(not valid)
PYTHON
  then
    printf '%s_PROGRESS_UNAVAILABLE\n' "$PREFIX" >&2
    return 2
  fi
  printf '%s_PROGRESS_OK\n' "$PREFIX"
}

https_control() {
  local port code
  port=$(sudo -n "$PY" -I -B - <<'PYTHON'
import json
with open("/etc/xgw/xray/config.json") as stream:
    rows = json.load(stream)["inbounds"]
port, = [row["port"] for row in rows if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PYTHON
  ) || return
  code=$(curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' https://example.org/) || return
  [[ $code == 200 ]] || return 2
  printf '%s_HTTPS %s 200\n' "$PREFIX" "$1"
}

verify_files() {
  local snapshot=$1 file
  for file in "${FILES[@]}"; do
    cmp -s "$snapshot/src/xgw/$file" "$PACKAGE/$file" || return 2
  done
}

controls() {
  [[ $(pid xgw-xray.service) == "$xray_before" ]] &&
    sudo -n sha256sum --check --status "$D/settings.sha256" &&
    verify_files "$2" && https_control "$1"
}

pending=$(systemctl list-units --state=active,activating --no-legend \
  'xgw-*-rollback.timer' 'xgw-*-rollback.service')
[[ -z $pending ]]
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json > "$D/settings.sha256"
xray_before=$(pid xgw-xray.service)
daemon_before=$(pid xgw.service)
wait_status 0
controls baseline "$D/base"
if [[ $present == yes ]]; then
  check_wake_progress
  if [[ $PROFILE != --pin-audit && $PROFILE != --watchdog-wake ]]; then
    [[ $(pid xgw.service) == "$daemon_before" ]]
    controls confirmed "$D/tree"
  fi
  printf '%s_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED\n' "$PREFIX"
  exit 0
fi

for directory in /opt/xgw/handoff /var/lib/xgw/handoff; do
  [[ ! -L $directory ]]
  sudo -n test -d "$directory" || sudo -n install -d -m 0700 "$directory"
done
PAYLOAD=$(sudo -n mktemp -d "/opt/xgw/handoff/$SCOPE.XXXXXXXX")
BACKUP=$(sudo -n mktemp -d "/var/lib/xgw/handoff/$SCOPE.XXXXXXXX")
printf 'ROLLBACK_PAYLOAD %s\nROLLBACK_BACKUP %s\n' "$PAYLOAD" "$BACKUP"
sudo -n install -m 0600 "$INSTALLER" "$PAYLOAD/install.py"
for path in "${PATHS[@]}"; do
  sudo -n install -D -m 0600 "$D/base/$path" "$PAYLOAD/base/$path"
  sudo -n install -D -m 0600 "$path" "$PAYLOAD/code/$path"
done
INSTALL=("$PY" -I -B "$PAYLOAD/install.py")
ARGS=("$PROFILE" --backup "$BACKUP")
sudo -n "${INSTALL[@]}" prepare "${ARGS[@]}" --payload "$PAYLOAD" --package "$PACKAGE"

finish() {
  local rc=$?
  if [[ $armed == yes ]]; then
    if sudo -n "${INSTALL[@]}" rollback "${ARGS[@]}" &&
       wait_status "$(date +%s.%N)" && controls restored "$D/base" &&
       sudo -n systemctl stop "$UNIT.timer"; then
      printf '%s_ROLLED_BACK\n' "$PREFIX"
    else
      printf '%s_ROLLBACK_PENDING\n' "$PREFIX" >&2
      rc=2
    fi
  fi
  exit "$rc"
}
armed=no
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo -n systemd-run --collect --unit="$UNIT" --on-active=15m --service-type=oneshot \
  "${INSTALL[@]}" rollback "${ARGS[@]}"
armed=yes
systemctl is-active --quiet "$UNIT.timer"
printf '%s_ROLLBACK_ARMED\n' "$PREFIX"
sudo -n "${INSTALL[@]}" apply "${ARGS[@]}"
daemon_after=$(pid xgw.service)
[[ $daemon_after != "$daemon_before" ]]
wait_status "$(date +%s.%N)"
check_wake_progress
[[ $(pid xgw.service) == "$daemon_after" ]]
controls installed "$D/tree"
sudo -n systemctl stop "$UNIT.timer"
if systemctl is-active --quiet "$UNIT.service"; then
  exit 2
fi
[[ $(pid xgw.service) == "$daemon_after" ]]
controls confirmed "$D/tree"
armed=no
printf '%s_DEPLOYED_AND_VERIFIED\n' "$PREFIX"
