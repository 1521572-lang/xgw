#!/usr/bin/env bash
# Apply and verify the accepted desktop map files without restarting the gateway.
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
[[ $# == 1 && $1 =~ ^[0-9a-f]{40}$ && -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]
CODE=$1
BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
HOME_BASE=3c4ae6b8446cd36e94dad1b3a9f74ac75dca23b5
GUI="/opt/xgw/gui/releases/$BASE"
ROOT=/var/lib/xgw/handoff
UNIT=xgw-gui-map-refresh-rollback
PY=${XGW_GUI_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import pytest, PyQt6.QtWidgets, PyQt6.QtSvg'
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
for revision in "$BASE" "$HOME_BASE"; do
  git -C "$REPO" cat-file -e "$revision^{commit}" || git -C "$REPO" fetch origin "$revision"
done
grep -Fq "$GUI/vpn_ui/main_xgw.py" /opt/xgw/lib/xgw/gui/app.py
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-gui-map-refresh.lock"
flock -n 9
if systemctl is-active --quiet "$UNIT.timer" || systemctl is-active --quiet "$UNIT.service"; then
  printf 'MAP_ROLLBACK_ALREADY_ACTIVE\n' >&2
  exit 2
fi

D=$(mktemp -d "$HOME/xgw-gui-map-refresh.XXXXXXXX")
printf 'PINNED %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$D"
mkdir -m 0700 "$D/before" "$D/after" "$D/qt-config"
MAP=(vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py)
CLIENT=src/xgw/gui/client.py
FILES=("${MAP[@]}" "$CLIENT")
git -C "$REPO" archive "$HOME_BASE" "${MAP[@]}" | tar -x -C "$D/before"
git -C "$REPO" archive "$BASE" "$CLIENT" | tar -x -C "$D/before"
git -C "$REPO" archive "$CODE" "${FILES[@]}" | tar -x -C "$D/after"
git -C "$REPO" archive "$CODE" docs/helpers/gui_home_install.py \
  docs/helpers/gui_catalog_install.py docs/helpers/gui_map_visibility.py \
  docs/helpers/run_gui_map_refresh.sh tests/test_gui_home_install.py \
  tests/test_gui_map_https.py | tar -x -C "$D"
timeout -k 3 45 "$PY" -B -P -m pytest -p no:cacheprovider -q \
  "$D/tests/test_gui_home_install.py" "$D/tests/test_gui_map_https.py"
printf 'MAP_DEPLOY_CONTRACTS_OK\n'

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
P=$(sudo -n mktemp -d "$ROOT/gui-map-refresh.XXXXXXXX")
[[ $P =~ ^/var/lib/xgw/handoff/gui-map-refresh\.[A-Za-z0-9]{8}$ ]]
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
  sudo -n /usr/bin/python3 -I -B "$P/gui_home_install.py" "$1" --map-refresh
}

controls() {
  if [[ $(services) != "$before" ]] ||
     ! sudo -n sha256sum --check --status "$D/settings.sha256"; then
    printf 'MAP_GATEWAY_BASELINE_MISMATCH %s\n' "$1" >&2
    return 2
  fi
  https_control "$1" || return 2
  printf 'MAP_GATEWAY_UNCHANGED\n'
}

installed_window() {
  local paths="$GUI:$GUI/src"
  env "PYTHONPATH=$paths" XGW_UI_QT=PyQt6 "$PY" -B -P - "$GUI" <<'PYTHON'
import sys
from pathlib import Path

from vpn_ui.views import map_canvas_view
from vpn_ui.xgw import window
from xgw.gui import client

root = Path(sys.argv[1])
for module, relative in ((map_canvas_view, "vpn_ui/views/map_canvas_view.py"),
                         (window, "vpn_ui/xgw/window.py"), (client, "src/xgw/gui/client.py")):
    if Path(module.__file__).resolve() != root / relative:
        raise ValueError("unexpected_loaded_module")
print("MAP_INSTALLED_MODULES_OK")
PYTHON
  timeout -k 4 125 env -u QT_QPA_PLATFORM "PYTHONPATH=$paths" XGW_UI_QT=PyQt6 \
    "XDG_CONFIG_HOME=$D/qt-config" "$PY" -B -P "$D/docs/helpers/gui_map_visibility.py" "$D"
}

armed=no
finish() {
  local rc=$?
  if [[ $armed == yes ]]; then
    if overlay rollback && [[ $(overlay check) == "READY changed files: 3" ]] &&
       sudo -n systemctl stop "$UNIT.timer"; then
      printf 'MAP_DEPLOY_ROLLED_BACK\n'
      controls rollback || rc=2
    else
      printf 'MAP_DEPLOY_ROLLBACK_PENDING\n' >&2
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
  printf 'MAP_ALREADY_INSTALLED_AND_VERIFIED\n'
  exit 0
fi
if [[ $ready != "READY changed files: 3" ]]; then
  printf 'MAP_DEPLOY_BASELINE_MISMATCH %s\n' "$ready" >&2
  exit 2
fi

sudo -n systemd-run --collect --unit="$UNIT" --on-active=10m --service-type=oneshot \
  --timer-property=AccuracySec=1s /usr/bin/python3 -I -B \
  "$P/gui_home_install.py" rollback --map-refresh
armed=yes
systemctl is-active --quiet "$UNIT.timer"
printf 'MAP_DEPLOY_ROLLBACK_ARMED\n'
overlay apply
[[ $(overlay check) == "READY changed files: 0" ]]
installed_window
controls installed
sudo -n systemctl stop "$UNIT.timer"
[[ $(overlay check) == "READY changed files: 0" ]]
armed=no
printf 'MAP_DEPLOYED_AND_VERIFIED\n'
