# ThinkCentre · отдельный вердикт для SYN-SENT в прямом опыте

**Ubuntu 24.04 LTS.** Flash сама выполняет команды и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
sudo, pytest, панели или GitHub запроси доступ и выполни доступные
фазы.

На ThinkCentre прошли 108 проверок TCP. На прямом запросе
наблюдались 27 опросов SYN-SENT и ноль ESTAB при нулевых потерях
NFQUEUE. Через VPN получены 65 536 байт. Сразу после отката снимок
захватил штатный drain legacy, после его окончания работал blue.
[Отчёт ThinkCentre](../reports/2026-11-25T115428Z_t04-tcp-info-coverage.md)

`syn_sent_without_established` означает, что наблюдатель нашёл
один исходящий сокет, увидел не менее трёх опросов SYN-SENT,
ни одного ESTAB и последний опрос не более чем за секунду
до таймаута запроса. Сводка также показывает разрыв между
опросами и доступный счётчик ретрансляций. Этапы curl и
исходящего сокета Xray остаются отдельными показаниями.

## Запуск

Из рабочей копии задай `XGW_TEST_PYTHON`, если pytest установлен
отдельно. Для изолированного loopback при необходимости выполни
`sudo -v`. При согласованном окне с паузой VPN задай
`XGW_CDN_LIVE=1` и используй штатную процедуру возврата.
[Процедура](STANDALONE-MANAGED-LIVE-2026-11-23.md)

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=fa09d5cc9a6de7ead7098fbc52aa777f94177218
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-tcp-connect.XXXXXXXX")
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

loopback() (
  local lab host_netns
  lab=$(sudo -n mktemp -d /run/xgw-t04-tcp-connect.XXXXXXXX) || return
  trap 'sudo -n rm -rf -- "$lab"' EXIT
  host_netns=$(stat -Lc %i /proc/self/ns/net) || return
  if ! git -C "$REPO" archive "$CODE" src docs/helpers |
      sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$lab"; then
    return 2
  fi
  sudo -n timeout -k 2 25 unshare --net -- /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$lab:$lab/src" "XGW_HOST_NETNS=$host_netns" "$PY" -B -P - <<'PYTHON'
import json
import os
import socket
import subprocess

from docs.helpers.cdn_tcp_observation import watch_transfer
from xgw.zapret2 import MARK

assert os.geteuid() == 0
assert os.stat("/proc/self/ns/net").st_ino != int(os.environ["XGW_HOST_NETNS"])
assert socket.if_nameindex() == [(1, "lo")]
subprocess.run(["ip", "link", "set", "lo", "up"], check=True, timeout=3)
subprocess.run(["nft", "-f", "-"], check=True, timeout=3, text=True, input="""
table inet xgw_test_tcp {
  chain input {
    type filter hook input priority filter; policy accept;
    iifname "lo" ip daddr 127.0.0.1 tcp dport 443 drop
  }
}
""")
with socket.socket() as listener, socket.socket() as client:
    listener.bind(("127.0.0.1", 443))
    listener.listen()
    client.settimeout(4)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)

    def transfer():
        try:
            client.connect(("127.0.0.1", 443))
        except TimeoutError:
            return {"curl_rc": 28, "tcp": 0.01, "tls": 0}
        raise AssertionError("isolated TCP connect unexpectedly completed")

    _, summary = watch_transfer("127.0.0.1", os.getpid(), transfer)
assert summary["state"] == "syn_sent_without_established", summary
assert summary["established_polls"] == 0 and summary["syn_sent_only_polls"] >= 3
assert summary["last_syn_sent_before_end_ms"] <= 1000
print(json.dumps(summary))
PYTHON
)

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
  --basetemp "$D/pytest" tests/test_cdn_tcp_observation.py \
  tests/test_standalone_cdn_compare.py tests/test_standalone_topology.py \
  tests/test_selective_probe_watch.py || contracts_rc=$?
loopback_rc=0
run_phase LOOPBACK loopback || loopback_rc=$?
if [[ $contracts_rc == 0 && $loopback_rc == 0 && ${XGW_CDN_LIVE:-0} == 1 ]]; then
  if run_phase LIVE live; then
    run_phase SETTLED sudo -n timeout -k 3 350 env "PYTHONPATH=$D/tree:$D/tree/src" \
      "$PY" -B -P -m docs.helpers.standalone_topology stable 330 || true
  fi
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

- **CONTRACTS** — число тестов, пороги покрытия и переход к
  `insufficient_coverage` при слишком раннем последнем опросе
  или недостаточном числе опросов.
- **LOOPBACK** — укажи фазу, количество SYN-SENT/ESTAB,
  время последнего опроса и счётчик ретрансляций. Тестовый
  локальный TCP-сокет использует настоящий `ss`, а результат
  внешней команды для классификатора задан тестом.
- **LIVE** — при согласованном проходе укажи итог пары,
  фазу curl, вердикт исходящего TCP и NFQUEUE. Интерпретация
  ограничена опросами одного сокета. Укажи сверку возврата и
  `SETTLED` после drain. При отсутствии окна укажи `NOT_RUN`.
- **Шлюз** — итог сравнения снимков и хэшей. Изменение PID
  после временной установки отрази отдельно от итоговой топологии.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, исходы и агрегаты. Адреса, cookies, URL и исходные
снимки остаются локально.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-tcp-connect-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-tcp-connect-phase.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre TCP connect phase after timeout'
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
