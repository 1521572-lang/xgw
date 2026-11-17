#!/bin/bash
# Run as the normal desktop user from a clean, pinned checkout. No policy changes.
set -euo pipefail
umask 077
CODE=$1
[[ "$CODE" =~ ^[0-9a-f]{40}$ ]]
test "$(git rev-parse HEAD)" = "$CODE"
test -z "$(git status --porcelain --untracked-files=no)"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
BASE=6f69cc278868bae07ae58c484b8f5b728ada1c29
git merge-base --is-ancestor "$BASE" "$CODE"
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
GUI=$(readlink -f /opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64)
PID=$(systemctl show xgw.service -p MainPID --value)
test "$PID" -gt 0
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/zapret2-management-$CODE"
BACKUP="/var/lib/xgw/handoff/zapret2-management-$CODE"
UNIT=xgw-zapret2-management-rollback
sudo test -d "$GUI"
sudo test -f "$PANEL"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" <<'PY'
import sys
from xgw import config
cfg, _ = config.load(sys.argv[1])
assert cfg.zapret2.mode == cfg.zapret2.engine == "off", "expected initial off/off"
PY
OLD=(src/xgw/watch/panel.py src/xgw/watch/zapret2_control.py
     src/xgw/ui/zapret2.html src/xgw/ui/zapret2.css src/xgw/ui/zapret2.js src/xgw/zapret2.py)
NEW=("${OLD[@]}" src/xgw/watch/zapret2_management.py src/xgw/gui/zapret2.py)
DEPS=(src/xgw/config.py src/xgw/managed.py src/xgw/paths.py src/xgw/desync/schema.py)
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base"
git archive "$CODE" "${NEW[@]}" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${OLD[@]}" "${DEPS[@]}" |
  sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$BASE" src/xgw/gui/zapret2.py | sudo tar --no-same-owner -x -C "$PAYLOAD/gui_base"
sudo chmod -R go-w -- "$PAYLOAD"
for file in "${DEPS[@]}"; do
  sudo cmp -- "$PAYLOAD/base/$file" "$PACKAGE/${file#src/xgw/}"
done
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" "$HELPER" prepare --zapret2-management --payload "$PAYLOAD" \
  --package "$PACKAGE" --gui "$GUI" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
printf '%s\n' "$PY" | sudo tee "$BACKUP/python.path" > /dev/null
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" > /dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256" "$BACKUP/panel.before" "$BACKUP/python.path"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo systemctl is-active "$UNIT.timer"
systemctl list-timers "$UNIT.timer" --no-pager
sudo "$PY" "$HELPER" apply --zapret2-management --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
printf '%s\n' "Installed with active rollback timer: $UNIT.timer" "Backup: $BACKUP"
