#!/usr/bin/env bash
# Apply and verify a bounded desktop update without restarting the gateway.
set -euo pipefail
umask 077

https_control() {
  local phase=$1 code rc=0
  code=$(curl -q -4sS --noproxy '*' --connect-timeout 4 --max-time 10 \
    --proto '=https' --proto-redir '=https' --location --max-redirs 2 \
    --resolve 'one.one.one.one:443:1.1.1.1' \
    -o /dev/null -w '%{http_code}' https://one.one.one.one/) || rc=$?
  if (( rc != 0 )) || [[ ! $code =~ ^2[0-9]{2}$ ]]; then
    printf 'MAP_HTTPS_CONTROL_FAILED %s CURL_RC %s HTTP %s\n' "$phase" "$rc" "${code:-none}" >&2
    return 2
  fi
  printf 'MAP_HTTPS_CONTROL_OK %s HTTP %s\n' "$phase" "$code"
}

if [[ $# == 1 && $1 == --check-https ]]; then
  https_control standalone
  exit 0
fi

. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ $# -ge 1 && $# -le 2 && $1 =~ ^[0-9a-f]{40}$ && -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]
CODE=$1
SCOPE=map
PREFIX=MAP
WINDOW_CHECK=gui_map_visibility.py
if [[ $# == 2 ]]; then
  [[ $2 == --pin-refresh ]]
  SCOPE=pin
  PREFIX=PIN
  WINDOW_CHECK=gui_pin_installed.py
fi
BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
HOME_BASE=3c4ae6b8446cd36e94dad1b3a9f74ac75dca23b5
SIDEBAR_BASE=dfccea8c88418e839532ccaec40f85b019669f51
GUI="/opt/xgw/gui/releases/$BASE"
ROOT=/var/lib/xgw/handoff
UNIT="xgw-gui-$SCOPE-refresh-rollback"
PY=${XGW_GUI_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import pytest, PyQt6.QtWidgets, PyQt6.QtSvg'
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
REVISIONS=("$BASE" "$HOME_BASE")
if [[ $SCOPE == pin ]]; then
  REVISIONS=("$SIDEBAR_BASE")
fi
for revision in "${REVISIONS[@]}"; do
  git -C "$REPO" cat-file -e "$revision^{commit}" || git -C "$REPO" fetch origin "$revision"
done
grep -Fq "$GUI/vpn_ui/main_xgw.py" /opt/xgw/lib/xgw/gui/app.py
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-gui-map-refresh.lock"
flock -n 9
for scope in map pin; do
  other="xgw-gui-$scope-refresh-rollback"
  if systemctl is-active --quiet "$other.timer" || systemctl is-active --quiet "$other.service"; then
    printf '%s_ROLLBACK_ALREADY_ACTIVE\n' "$PREFIX" >&2
    exit 2
  fi
done

D=$(mktemp -d "$HOME/xgw-gui-$SCOPE-refresh.XXXXXXXX")
printf 'PINNED %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$D"
mkdir -m 0700 "$D/before" "$D/after" "$D/qt-config"
MAP=(vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py)
CLIENT=src/xgw/gui/client.py
CHECKS=(docs/helpers/gui_map_visibility.py)
if [[ $SCOPE == pin ]]; then
  FILES=(vpn_ui/xgw/sidebar.py)
  CHECKS+=(docs/helpers/gui_pin_installed.py)
  git -C "$REPO" archive "$SIDEBAR_BASE" "${FILES[@]}" | tar -x -C "$D/before"
else
  FILES=("${MAP[@]}" "$CLIENT")
  git -C "$REPO" archive "$HOME_BASE" "${MAP[@]}" | tar -x -C "$D/before"
  git -C "$REPO" archive "$BASE" "$CLIENT" | tar -x -C "$D/before"
fi
BASE_READY="READY changed files: ${#FILES[@]}"
git -C "$REPO" archive "$CODE" "${FILES[@]}" | tar -x -C "$D/after"
git -C "$REPO" archive "$CODE" docs/helpers/gui_home_install.py \
  docs/helpers/gui_catalog_install.py "${CHECKS[@]}" \
  docs/helpers/run_gui_map_refresh.sh tests/test_gui_home_install.py \
  tests/test_gui_map_https.py | tar -x -C "$D"
timeout -k 3 45 "$PY" -B -P -m pytest -p no:cacheprovider -q \
  "$D/tests/test_gui_home_install.py" "$D/tests/test_gui_map_https.py"
printf '%s_DEPLOY_CONTRACTS_OK\n' "$PREFIX"

services() {
  local unit pid
  for unit in xgw.service xgw-xray.service; do
    pid=$(systemctl show "$unit" -p MainPID --value) || return 2
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done
}

before=$(services)
https_control baseline
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.sha256"

test ! -L "$ROOT"
if ! sudo -n test -d "$ROOT"; then
  sudo -n install -d -m 0700 "$ROOT"
fi
P=$(sudo -n mktemp -d "$ROOT/gui-$SCOPE-refresh.XXXXXXXX")
[[ $P =~ ^/var/lib/xgw/handoff/gui-$SCOPE-refresh\.[A-Za-z0-9]{8}$ ]]
printf 'ROLLBACK_PAYLOAD %s\n' "$P"
for helper in gui_home_install.py gui_catalog_install.py; do
  sudo -n install -m 0600 "$D/docs/helpers/$helper" "$P/$helper"
done
for kind in before after; do
  for file in "${FILES[@]}"; do
    sudo -n install -D -m 0600 "$D/$kind/$file" "$P/$kind/$file"
  done
done

overlay() {
  sudo -n /usr/bin/python3 -I -B "$P/gui_home_install.py" "$1" "--$SCOPE-refresh"
}

controls() {
  if [[ $(services) != "$before" ]] ||
     ! sudo -n sha256sum --check --status "$D/settings.sha256"; then
    printf '%s_GATEWAY_BASELINE_MISMATCH %s\n' "$PREFIX" "$1" >&2
    return 2
  fi
  https_control "$1" || return 2
  printf '%s_GATEWAY_UNCHANGED\n' "$PREFIX"
}

installed_window() {
  local paths="$GUI:$GUI/src"
  env "PYTHONPATH=$paths" XGW_UI_QT=PyQt6 "$PY" -B -P - "$GUI" "$PREFIX" "${FILES[@]}" <<'PYTHON'
import importlib
import sys
from pathlib import Path

root, prefix, *files = sys.argv[1:]
root = Path(root)
for relative in files:
    name = relative.removeprefix("src/").removesuffix(".py").replace("/", ".")
    module = importlib.import_module(name)
    if Path(module.__file__).resolve() != root / relative:
        raise ValueError("unexpected_loaded_module")
print(f"{prefix}_INSTALLED_MODULES_OK")
PYTHON
  timeout -k 4 125 env -u QT_QPA_PLATFORM "PYTHONPATH=$D/docs/helpers:$paths" XGW_UI_QT=PyQt6 \
    "XDG_CONFIG_HOME=$D/qt-config" "$PY" -B -P "$D/docs/helpers/$WINDOW_CHECK" "$D"
}

armed=no
finish() {
  local rc=$?
  if [[ $armed == yes ]]; then
    if overlay rollback && [[ $(overlay check) == "$BASE_READY" ]] &&
       sudo -n systemctl stop "$UNIT.timer"; then
      printf '%s_DEPLOY_ROLLED_BACK\n' "$PREFIX"
      controls rollback || rc=2
    else
      printf '%s_DEPLOY_ROLLBACK_PENDING\n' "$PREFIX" >&2
      rc=2
    fi
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ready=$(overlay check)
if [[ $ready == "READY changed files: 0" ]]; then
  installed_window
  controls installed
  printf '%s_ALREADY_INSTALLED_AND_VERIFIED\n' "$PREFIX"
  exit 0
fi
if [[ $ready != "$BASE_READY" ]]; then
  printf '%s_DEPLOY_BASELINE_MISMATCH %s\n' "$PREFIX" "$ready" >&2
  exit 2
fi

sudo -n systemd-run --collect --unit="$UNIT" --on-active=10m --service-type=oneshot \
  --timer-property=AccuracySec=1s /usr/bin/python3 -I -B \
  "$P/gui_home_install.py" rollback "--$SCOPE-refresh"
armed=yes
systemctl is-active --quiet "$UNIT.timer"
printf '%s_DEPLOY_ROLLBACK_ARMED\n' "$PREFIX"
overlay apply
[[ $(overlay check) == "READY changed files: 0" ]]
installed_window
controls installed
sudo -n systemctl stop "$UNIT.timer"
[[ $(overlay check) == "READY changed files: 0" ]]
armed=no
printf '%s_DEPLOYED_AND_VERIFIED\n' "$PREFIX"
