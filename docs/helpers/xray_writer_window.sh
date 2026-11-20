#!/usr/bin/env bash
# Run as the logged-in desktop user from the XGW checkout.
set -euo pipefail
umask 077
code=${1:?pass the pinned helper commit}
d=$(mktemp -d "${TMPDIR:-/tmp}/xgw-writer-ro.XXXXXXXX")
printf 'Private results: %s\n' "$d"
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9 || { echo BUSY; exit 2; }
sudo -n true
git cat-file -e "$code^{commit}"
py=/usr/bin/python3
cfg=/etc/xgw/xray/config.json
db=/var/lib/xgw/state.db

control() {
    systemctl is-active --quiet xgw.service || return
    systemctl is-active --quiet xgw-xray.service || return
    env PYTHONPATH=/opt/xgw/lib "$py" -B -P -m xgw.desync.client status |
        "$py" -I -c 'import json,sys
v=json.load(sys.stdin)
assert v["fresh"] and v["policy_matched"] and v["engine_mode"]=="off"
assert (v["mode"],v["state"]) in (("off","off"),("selective","active"),("selective","fallback"))
print(v["mode"],v["state"])' || return
    local port
    port=$(sudo -n "$py" -I -B -c 'import json,sys
with open(sys.argv[1]) as f: rows=json.load(f)["inbounds"]
p,=[int(i["port"]) for i in rows if i.get("tag")=="http-in" and i.get("listen")=="127.0.0.1"]
assert 0<p<65536
print(p)' "$cfg") || return
    curl -q --silent --show-error --fail --connect-timeout 4 --max-time 10 --max-filesize 131072 \
        --noproxy '' --proxy "http://127.0.0.1:$port" --output /dev/null \
        --write-out 'HTTPS via http-in %{http_code}\n' https://example.org/
}

control >"$d/before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$d/settings.sha256"
start=$(date +%s)
watch_rc=0
git show "$code:docs/helpers/xray_writer_observe.py" |
    sudo -n timeout -k 2 200 "$py" -I -B - --seconds 180 >"$d/watch.jsonl" || watch_rc=$?
end=$(date +%s)
after_rc=0
control >"$d/after" || after_rc=$?
settings_rc=0
sudo -n sha256sum --status -c "$d/settings.sha256" || settings_rc=$?
# Keep diagnostic extracts private and bounded, including on a busy gateway.
jr=0
for unit in xgw xgw-xray; do
    (ulimit -f 2048
     sudo -n timeout 12 journalctl -b --no-pager --since="@$start" --until="@$((end+1))" \
        -u "$unit.service" -n 200 -o short-unix >"$d/$unit.journal") || jr=$?
done
sudo -n timeout 8 "$py" -I -B - "$db" "$start" "$end" >"$d/events" <<'PY' && sq=0 || sq=$?
import sqlite3, sys
from pathlib import Path
db, start, end = sys.argv[1:]
conn = sqlite3.connect(Path(db).as_uri() + "?mode=ro", uri=True, timeout=1)
conn.execute("PRAGMA query_only=ON")
for ts, kind in conn.execute(
    "SELECT ts,kind FROM (SELECT ts,kind FROM events ORDER BY id DESC LIMIT 512) "
    "WHERE ts BETWEEN ? AND ? ORDER BY ts", (int(start)-2, int(end)+2)):
    print(ts, kind)
PY
audit_rc=127
if command -v ausearch >/dev/null; then
    export LC_ALL=C
    (ulimit -f 2048
     sudo -n timeout 12 ausearch -ts "$(date -d "@$start" +%x)" "$(date -d "@$start" +%T)" \
       -te "$(date -d "@$((end+1))" +%x)" "$(date -d "@$((end+1))" +%T)" \
       -f "$cfg" -i >"$d/audit") && audit_rc=0 || audit_rc=$?
fi
printf 'watch_rc=%s after_rc=%s settings_rc=%s journal_rc=%s events_rc=%s audit_rc=%s\n' \
    "$watch_rc" "$after_rc" "$settings_rc" "$jr" "$sq" "$audit_rc"
cat "$d/before" "$d/after"
tail -n 1 "$d/watch.jsonl"
[[ $watch_rc == 0 && $after_rc == 0 && $settings_rc == 0 ]]
