# ThinkCentre · полнота TCP-отсчётов прямого CDN

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые проверки и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, pytest, панели или GitHub запроси доступ и
выполни доступные фазы.

ThinkCentre прошёл 118 проверок. Прямой запрос дал TLS-таймаут,
маршрут подтверждён, NFQUEUE за 11,501 с показала нулевые потери.
Прямой повтор остался `NOT_RUN`, через VPN повтор после HTTP 302
получил `206/65536`. На прямом сокете вернулся
`tcp_info_unobserved`. [Отчёт пары](../reports/2026-11-25T112725Z_t04-cdn-direct-retry.md)

`ss` может опустить `rto` или напечатать дробное значение. Наличие
TCP-данных теперь определяется также по другим полям. Некорректное
значение остаётся неизвестным. Сводка показывает число опросов
установленного сокета, опросов только в SYN-SENT и опросов
установленного сокета без полного набора данных.
[Исходный код iproute2 6.1](https://github.com/iproute2/iproute2/blob/v6.1.0/misc/ss.c)

## Запуск

Из рабочей копии задай `XGW_TEST_PYTHON`, если pytest установлен
отдельно. Для изолированного loopback при необходимости выполни
`sudo -v`. Если уже доступно согласованное окно Standalone с
паузой VPN, задай `XGW_CDN_LIVE=1` и используй прежнюю процедуру
независимого возврата. [Процедура](STANDALONE-MANAGED-LIVE-2026-11-23.md)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=d66ef3665c905b080837d1e1bbaf8e648d6b4a3a
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-tcp-info.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers packaging vpn_ui pyproject.toml \
  | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
ss -V
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  sudo -n timeout -k 3 60 "$PY" -I -B - snapshot <docs/helpers/audit_host_observe.py &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

run_phase() {
  local label=$1 code=0
  shift
  "$@" >"$D/$label.log" 2>&1 || code=$?
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

loopback() {
  local lab host_netns
  lab=$(sudo -n mktemp -d /run/xgw-t04-tcp-info.XXXXXXXX) || return
  host_netns=$(stat -Lc %i /proc/self/ns/net) || return
  if ! git -C "$REPO" archive "$CODE" src docs/helpers |
      sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$lab"; then
    return 2
  fi
  sudo -n timeout -k 2 25 unshare --net -- /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$lab:$lab/src" "XGW_HOST_NETNS=$host_netns" "$PY" -B -P - <<'PYTHON'
import json
import os
import re
import socket
import subprocess
import time

from docs.helpers import cdn_tcp_observation as tcp
from docs.helpers.selective_probe_watch import parse_socket_stats
from xgw.net import cmd
from xgw.zapret2 import MARK

assert os.geteuid() == 0
assert os.stat("/proc/self/ns/net").st_ino != int(os.environ["XGW_HOST_NETNS"])
assert socket.if_nameindex() == [(1, "lo")]
subprocess.run(["ip", "link", "set", "lo", "up"], check=True, timeout=3)
removed = 0

def read_without_rto(peer):
    global removed
    raw = cmd.run(["ss", "-HtaOeinp", "state", "big", "fwmark", "=", hex(MARK),
                   "and", "dst", "=", f"{peer}:443"], timeout=1)
    stripped, count = re.subn(r"(?<!\S)rto:\S+", "", raw)
    removed += count
    return parse_socket_stats(stripped)

tcp.read_sockets = read_without_rto
with socket.socket() as listener, socket.socket() as client:
    listener.bind(("127.0.0.1", 443))
    listener.listen()
    listener.settimeout(2)
    client.settimeout(2)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)

    def transfer():
        client.connect(("127.0.0.1", 443))
        with listener.accept()[0] as server:
            server.settimeout(2)
            client.sendall(b"fixture")
            assert server.recv(7, socket.MSG_WAITALL) == b"fixture"
            server.sendall(b"reply")
            assert client.recv(5, socket.MSG_WAITALL) == b"reply"
            time.sleep(2)
        return {"curl_rc": 0, "tcp": 0.01, "tls": 0.01}

    _, summary = tcp.watch_transfer("127.0.0.1", os.getpid(), transfer)
assert summary["state"] == "tcp_data_received", summary
assert summary["established_polls"] >= 2
assert summary["established_polls_without_tcp_info"] == 0
print(json.dumps({"rto_fields_removed": removed, "tcp": summary}))
PYTHON
}

live() (
  cd "$REPO"
  sudo -n true || exit
  git show "$CODE:docs/helpers/standalone_return_preflight.sh" |
    bash -s -- "$CODE" || exit
  git show "$CODE:docs/helpers/standalone_return_live.sh" |
    bash -s -- "$CODE" cdn-pair
)

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts_rc=0
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_selective_probe_watch.py \
  tests/test_cdn_tcp_observation.py tests/test_standalone_cdn_compare.py || contracts_rc=$?
loopback_rc=0
run_phase LOOPBACK loopback || loopback_rc=$?
if [[ $contracts_rc == 0 && $loopback_rc == 0 && ${XGW_CDN_LIVE:-0} == 1 ]]; then
  run_phase LIVE live || true
else
  printf 'T04_LIVE_NOT_RUN\n'
fi
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T04_GATEWAY_UNCHANGED\n'
  else
    printf 'T04_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T04_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Итоги

- **CONTRACTS** — сводка проверок. Укажи дробный и пропущенный
  `rto`, некорректные счётчики и разделение SYN-SENT/ESTAB.
- **LOOPBACK** — число удалённых полей и данные TCP. Ожидается
  `tcp_data_received` на обработанном выводе реального `ss`,
  два или более ESTAB-опросов и ноль ESTAB-опросов без полного
  набора данных.
- **LIVE** — при согласованном проходе укажи вердикт пары,
  три счётчика опросов, TCP и NFQUEUE. Если `tcp_info_unobserved`
  повторится, укажи, наблюдался ли ESTAB и сколько таких опросов
  осталось без данных. Укажи исход выключения и возврата.
  При отсутствии окна укажи `NOT_RUN`.
- **Шлюз** — итог сравнения снимков и хэшей. Если снимки отличаются,
  укажи категорию различий.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, исходы и агрегаты. Адреса, cookies сокетов, исходные
строки `ss`, URL и снимки оставь на машине.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-tcp-info-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-tcp-info-coverage.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre TCP info parser coverage'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
