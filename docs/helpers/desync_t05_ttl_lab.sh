#!/usr/bin/env bash
# Real kernel, four isolated namespaces, fixed documentation addresses and no default routes.
set -euo pipefail
umask 077
if (( EUID != 0 )) || (( $# != 1 )); then
  echo "usage: sudo bash docs/helpers/desync_t05_ttl_lab.sh NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi
HERE=$(cd "$(dirname "$0")" && pwd)
SOURCE=$(realpath "$HERE/../../src")
BIN=/opt/xgw/zapret2/1.0.7/nfqws2
LUA=/opt/xgw/zapret2/1.0.7/lua
test -x "$BIN"
for program in ip ss sysctl nft curl openssl tcpdump python3 timeout; do command -v "$program"; done
mkdir -- "$1"
OUT=$(realpath "$1")
C=xgwttl-c-$$
R1=xgwttl-a-$$
R2=xgwttl-b-$$
S=xgwttl-s-$$
NAMES=()
WORKER=
SERVER=
CAPS=()

run() {
  local namespace=$1
  shift
  ip netns exec "$namespace" "$@"
}

stop_capture() {
  local pid
  for pid in "${CAPS[@]}"; do
    kill -INT "$pid" 2>/dev/null || true
    wait "$pid" || true
  done
  CAPS=()
}

stop_worker() {
  if [[ -n "$WORKER" ]]; then
    kill "$WORKER" 2>/dev/null || true
    wait "$WORKER" || true
    WORKER=
  fi
}

cleanup() {
  local result=$?
  trap - EXIT
  stop_capture
  stop_worker
  if [[ -n "$SERVER" ]]; then
    kill "$SERVER" 2>/dev/null || true
    wait "$SERVER" || true
  fi
  local namespace
  for namespace in "${NAMES[@]}"; do
    ip netns delete "$namespace" || result=1
  done
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

printf 'Lab namespaces: %s %s %s %s\n' "$C" "$R1" "$R2" "$S"
for namespace in "$C" "$R1" "$R2" "$S"; do
  ip netns add "$namespace"
  NAMES+=("$namespace")
  ip -n "$namespace" link set lo up
done

link() {
  local left=$1 right=$2 prefix=$3
  ip -n "$left" link add right0 type veth peer name left0 netns "$right"
  ip -n "$left" addr add "$prefix.1/30" dev right0
  ip -n "$right" addr add "$prefix.2/30" dev left0
  ip -n "$left" link set right0 up
  ip -n "$right" link set left0 up
}
link "$C" "$R1" 192.0.2
link "$R1" "$R2" 198.51.100
link "$R2" "$S" 203.0.113
ip -n "$C" route add 203.0.113.2/32 via 192.0.2.2
ip -n "$R1" route add 203.0.113.2/32 via 198.51.100.2
ip -n "$R2" route add 192.0.2.1/32 via 198.51.100.1
ip -n "$S" route add 192.0.2.1/32 via 203.0.113.1
run "$R1" sysctl -qw net.ipv4.ip_forward=1
run "$R2" sysctl -qw net.ipv4.ip_forward=1

openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=probe.xgw.test \
  -addext subjectAltName=DNS:probe.xgw.test -keyout "$OUT/key.pem" -out "$OUT/cert.pem" \
  >"$OUT/cert.log" 2>&1
python3 -c 'import sys; sys.stdout.write("x" * 262144)' >"$OUT/body.txt"
cd "$OUT"
run "$S" sysctl -qw net.ipv4.ip_default_ttl=64
ip netns exec "$S" openssl s_server -quiet -WWW -accept 203.0.113.2:443 \
  -cert "$OUT/cert.pem" -key "$OUT/key.pem" >"$OUT/server.log" 2>&1 &
SERVER=$!
for (( i=0; i<50; i++ )); do
  if run "$S" ss -Hln 'sport = :443' | grep -q :443; then break; fi
  kill -0 "$SERVER"
  sleep 0.1
done
run "$S" ss -Hln 'sport = :443' | grep :443

rules() {
  local synack=$1 replies=${2:-0}
  if run "$C" nft list table inet xgw_guard >/dev/null 2>&1; then
    run "$C" nft delete table inet xgw_guard
  fi
  PYTHONPATH="$SOURCE" python3 - "$synack" "$replies" >"$OUT/client.nft" <<'PY'
import sys
from xgw.zapret2 import guard_blocks

print("table inet xgw_guard {")
for block in guard_blocks(201, observe_synack=sys.argv[1] == "on",
                          observe_reply_packets=int(sys.argv[2])):
    print("\n".join(block))
print("""
  chain lab_mark {
    type route hook output priority mangle; policy accept;
    meta mark & 0x40000000 != 0 return
    ip daddr 203.0.113.2 tcp dport 443 meta mark set 0x10000000
  }
}
add element inet xgw_guard zapret2_live { 0x10000000 timeout 120s, 0x50000000 timeout 120s }
""")
PY
  run "$C" nft --check -f "$OUT/client.nft"
  run "$C" nft -f "$OUT/client.nft"
}

start_worker() {
  local label=$1 strategy=$2
  local args=("$BIN" --qnum=201 --fwmark=0x40000000 --debug=0
              "--lua-init=@$LUA/zapret-lib.lua" "--lua-init=@$LUA/zapret-antidpi.lua"
              "--lua-init=@$HERE/desync_t05_ttl.lua" --filter-tcp=443 --filter-l7=tls
              --payload=tls_client_hello --lua-desync=xgw_ttl_observe "--lua-desync=$strategy")
  run "$C" timeout 10 "${args[@]}" --intercept=0 >"$OUT/$label.preflight.log" 2>&1
  ip netns exec "$C" "${args[@]}" >"$OUT/$label.worker.log" 2>&1 &
  WORKER=$!
  for (( i=0; i<50; i++ )); do
    if run "$C" awk '$1==201 {ok=1} END {exit !ok}' /proc/net/netfilter/nfnetlink_queue \
        2>/dev/null; then return; fi
    kill -0 "$WORKER"
    sleep 0.1
  done
  echo "no queue in lab" >&2
  return 1
}

trial() {
  local label=$1
  ip netns exec "$C" tcpdump -Z root -n -U -i right0 -s 128 -w "$OUT/$label.client.pcap" \
    'host 203.0.113.2 and tcp port 443' >"$OUT/$label.client.log" 2>&1 &
  CAPS+=("$!")
  ip netns exec "$S" tcpdump -Z root -n -U -i left0 -s 128 -w "$OUT/$label.server.pcap" \
    'host 192.0.2.1 and tcp port 443' >"$OUT/$label.server.log" 2>&1 &
  CAPS+=("$!")
  for (( i=0; i<50; i++ )); do
    if grep -q 'listening on' "$OUT/$label.client.log" &&
       grep -q 'listening on' "$OUT/$label.server.log"; then break; fi
    sleep 0.1
  done
  grep -q 'listening on' "$OUT/$label.client.log"
  grep -q 'listening on' "$OUT/$label.server.log"
  run "$C" curl --silent --show-error --fail --noproxy '*' --max-time 10 --http1.1 \
    --cacert "$OUT/cert.pem" --resolve probe.xgw.test:443:203.0.113.2 \
    https://probe.xgw.test/body.txt -o "$OUT/$label.body"
  cmp "$OUT/body.txt" "$OUT/$label.body"
  stop_capture
  run "$C" nft -a list table inet xgw_guard >"$OUT/$label.nft"
  echo "$label: HTTPS body matched"
}

MD5=hostfakesplit:midhost=midsld:tcp_md5
AUTO="$MD5:ip_autottl=-1,1-20"
rules on
start_worker md5 "$MD5"
trial md5
stop_worker
rules off
start_worker cold_off "$AUTO"
trial cold_off
stop_worker
rules on
start_worker cold_on "$AUTO"
trial cold_on
# Same worker and IP, but no incoming queue and a different real SYN/ACK TTL.
run "$C" nft flush chain inet xgw_guard zapret2_reply
run "$S" sysctl -qw net.ipv4.ip_default_ttl=60
trial warm_off
stop_worker
rules on
start_worker changed_ttl "$AUTO"
trial changed_ttl
stop_worker
run "$C" sysctl -qw net.netfilter.nf_conntrack_acct=1
rules on 8
start_worker early_reply8 "$MD5"
trial early_reply8
stop_worker
grep -h 'XGW_T05_TTL' "$OUT/"*.worker.log || true
printf 'Private lab artifacts: %s\n' "$OUT"
