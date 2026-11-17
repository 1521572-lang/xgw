#!/bin/bash
# Installed root-owned alongside the rollback manifest by t11_management_install.sh.
set -euo pipefail
py=$1
helper=$2
backup=$3
panel=$4
mode=$5
overlay=${6:---zapret2-management}
[[ "$mode" == accept || "$mode" == rollback ]]
exec 9>"$backup/restore.lock"
flock 9
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-t11-restore.XXXXXXXX")
trap 'rm -f -- "$temp"' EXIT
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
if [[ "$mode" == rollback ]]; then
  "$py" "$helper" rollback "$overlay" --backup "$backup"
else
  systemctl start xgw.service
fi
if [[ -e "$backup/network-test-started" ]]; then
  timeout 180 /usr/local/bin/xgw apply --now
fi
sha256sum -c "$backup/config-before.sha256"
systemctl is-active xgw.service
date -u +%FT%TZ > "$backup/restore-completed"
