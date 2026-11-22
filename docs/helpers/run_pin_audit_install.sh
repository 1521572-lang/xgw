#!/usr/bin/env bash
# Install only the accepted pin audit and home-exit diagnostics on ThinkCentre.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $# == 1 && $1 =~ ^[0-9a-f]{40}$ ]]
CODE=$1
BASE=a2f37021cf119342d2f8344c91d26bafc12c3673
AUDIT=4a6636f2a7b2302b714436584c393731233cc6a0
REPO=$(git rev-parse --show-toplevel)
PACKAGE=/opt/xgw/lib/xgw
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
UNIT=xgw-pin-audit-rollback
INSTALLER=docs/helpers/desync_batch1_install.py
FILES=(actions.py cli.py daemon.py gui/model.py tray.py ui/app.js
       watch/notify.py watch/panel.py watch/states.py)
PATHS=("${FILES[@]/#/src/xgw/}")
[[ $TEST_PY == /* && -x $TEST_PY ]]
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$AUDIT" "$CODE"
[[ $(git -C "$REPO" diff --name-only "$BASE" "$AUDIT" -- src/xgw) == \
   "$(printf '%s\n' "${PATHS[@]}")" ]]
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9

D=$(mktemp -d "$HOME/xgw-pin-audit-install.XXXXXXXX")
printf 'PINNED %s | %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$(uname -r)" "$D"
mkdir -p "$D/tree/src" "$D/base"
tar -C /opt/xgw/lib --exclude=__pycache__ -cf - xgw | tar -C "$D/tree/src" -xf -
[[ -z $(find "$D/tree/src/xgw" ! -type d ! -type f -print -quit) ]]
git -C "$REPO" archive "$CODE" pyproject.toml "$INSTALLER" \
  docs/helpers/leak_cause_check.py tests/conftest.py tests/links.py tests/fakenet.py \
  tests/fakexray.py tests/test_daemon.py tests/test_daemon_main.py tests/test_cli_commands.py \
  tests/test_panel.py tests/test_leak_incident.py | tar -x -C "$D/tree"
git -C "$REPO" diff --no-ext-diff --no-textconv "$BASE" "$AUDIT" -- "${PATHS[@]}" > "$D/audit.patch"
cd "$D/tree"
for path in "${PATHS[@]}"; do
  install -D -m 0600 "$path" "$D/base/$path"
done
if git apply --reverse --check "$D/audit.patch" >/dev/null 2>"$D/reverse.err"; then
  printf 'PIN_AUDIT_ALREADY_PRESENT\n'
  present=yes
elif git apply --check "$D/audit.patch" 2>"$D/patch.err"; then
  git apply "$D/audit.patch"
  printf 'PIN_AUDIT_PATCH_APPLIED_TO_PRIVATE_COPY\n'
  present=no
else
  printf 'PIN_AUDIT_BASELINE_MISMATCH\n'
  exit 2
fi
timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
  "PYTHONPATH=$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest -o addopts= \
  --rootdir "$D/tree" -p no:cacheprovider -q --tb=short \
  tests/test_leak_incident.py \
  tests/test_daemon.py::test_server_exiting_at_home_is_replaced_and_not_taken_back \
  tests/test_daemon.py::test_leak_reports_success_only_after_the_rules_are_confirmed \
  tests/test_daemon.py::test_home_exit_without_route_evidence_does_not_claim_bypass \
  tests/test_cli_commands.py::test_pin_and_unpin \
  tests/test_cli_commands.py::test_pin_api_error \
  tests/test_panel.py::test_pin_goes_through_the_same_code_as_the_command \
  tests/test_daemon.py::test_pin_expires_and_is_restored_after_apply \
  tests/test_daemon.py::test_pin_is_dropped_when_node_leaves_balancer \
  tests/test_daemon_main.py::test_main_is_released_when_no_member_answers | tee "$D/contracts.out"
grep -q '^13 passed in ' "$D/contracts.out"
printf 'PIN_AUDIT_CONTRACTS_OK\n'

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
  printf 'PIN_AUDIT_STATUS_TIMEOUT\n' >&2
  return 2
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
  printf 'PIN_AUDIT_HTTPS %s 200\n' "$1"
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
  printf 'PIN_AUDIT_FILES_ALREADY_PRESENT_RUNTIME_NOT_RESTARTED\n'
  exit 0
fi

for directory in /opt/xgw/handoff /var/lib/xgw/handoff; do
  [[ ! -L $directory ]]
  sudo -n test -d "$directory" || sudo -n install -d -m 0700 "$directory"
done
PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/pin-audit.XXXXXXXX)
BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/pin-audit.XXXXXXXX)
printf 'ROLLBACK_PAYLOAD %s\nROLLBACK_BACKUP %s\n' "$PAYLOAD" "$BACKUP"
sudo -n install -m 0600 "$INSTALLER" "$PAYLOAD/install.py"
for path in "${PATHS[@]}"; do
  sudo -n install -D -m 0600 "$D/base/$path" "$PAYLOAD/base/$path"
  sudo -n install -D -m 0600 "$path" "$PAYLOAD/code/$path"
done
INSTALL=("$PY" -I -B "$PAYLOAD/install.py")
ARGS=(--pin-audit --backup "$BACKUP")
sudo -n "${INSTALL[@]}" prepare "${ARGS[@]}" --payload "$PAYLOAD" --package "$PACKAGE"

finish() {
  local rc=$?
  if [[ $armed == yes ]]; then
    if sudo -n "${INSTALL[@]}" rollback "${ARGS[@]}" &&
       wait_status "$(date +%s.%N)" && controls restored "$D/base" &&
       sudo -n systemctl stop "$UNIT.timer"; then
      printf 'PIN_AUDIT_ROLLED_BACK\n'
    else
      printf 'PIN_AUDIT_ROLLBACK_PENDING\n' >&2
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
printf 'PIN_AUDIT_ROLLBACK_ARMED\n'
sudo -n "${INSTALL[@]}" apply "${ARGS[@]}"
wait_status "$(date +%s.%N)"
daemon_after=$(pid xgw.service)
[[ $daemon_after != "$daemon_before" ]]
controls installed "$D/tree"
sudo -n systemctl stop "$UNIT.timer"
if systemctl is-active --quiet "$UNIT.service"; then
  exit 2
fi
[[ $(pid xgw.service) == "$daemon_after" ]]
controls confirmed "$D/tree"
armed=no
printf 'PIN_AUDIT_DEPLOYED_AND_VERIFIED\n'
