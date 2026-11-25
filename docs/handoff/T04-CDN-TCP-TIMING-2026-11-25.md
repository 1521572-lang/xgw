# ThinkCentre · время наблюдения отправки и ACK на TCP-сокете

**Ubuntu 24.04 LTS.** Flash сама запускает готовые проверки и
публикует обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, pytest или GitHub запроси доступ и выполни доступные
фазы.

ThinkCentre подтвердил 127 контрактов по сводке NFQUEUE.
На loopback учтены доли 0/1 и 28/32. Последний сопоставимый
живой CDN-опыт зафиксировал ретрансляции и отсутствие ACK
полезных данных на прямом сокете. Для следующего такого окна
добавлены отметки первого отсчёта с отправкой, ACK, приёмом и
ретрансляцией. Они отсчитываются от начала наблюдения и отражают
момент чтения счётчика. Наибольший промежуток между чтениями
показывает разрешение измерения.
[Отчёт NFQUEUE](../reports/2026-11-25T052552Z_t12-queue-delivery-rate.md) ·
[Исходный TCP-отчёт](../reports/2026-11-24T202842Z_t04-cdn-tcp.md)

## Запуск

Из рабочей копии укажи `XGW_TEST_PYTHON`, если pytest установлен
отдельно. Для стенда при необходимости выполни `sudo -v`. Стенд
использует только loopback в отдельном сетевом пространстве имён.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=d432d47d105e83a6999eb6539bbd10abf1b74473
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t04-tcp-timing.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
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
}

loopback() {
  local lab host_netns
  lab=$(sudo -n mktemp -d /run/xgw-t04-timing.XXXXXXXX) || return
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
import time

from docs.helpers.cdn_tcp_observation import watch_transfer
from xgw.zapret2 import MARK

assert os.geteuid() == 0
assert os.stat("/proc/self/ns/net").st_ino != int(os.environ["XGW_HOST_NETNS"])
assert socket.if_nameindex() == [(1, "lo")]
subprocess.run(["ip", "link", "set", "lo", "up"], check=True, timeout=3)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 443))
    listener.listen()
    listener.settimeout(2)
    for reply, expected in ((False, "ack_without_tcp_data"), (True, "tcp_data_received")):
        with socket.socket() as client:
            client.settimeout(2)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)

            def transfer(reply=reply):
                client.connect(("127.0.0.1", 443))
                with listener.accept()[0] as server:
                    server.settimeout(2)
                    time.sleep(0.5)
                    client.sendall(b"fixture")
                    assert server.recv(7, socket.MSG_WAITALL) == b"fixture"
                    if reply:
                        time.sleep(1.0)
                        server.sendall(b"reply")
                        assert client.recv(5, socket.MSG_WAITALL) == b"reply"
                    time.sleep(1.5)
                return {"curl_rc": 28, "tcp": 0.01, "tls": 0}

            _, summary = watch_transfer("127.0.0.1", os.getpid(), transfer)
        assert summary["state"] == expected, summary
        assert summary["samples"] >= 3 and summary["largest_sample_gap_ms"] is not None
        assert 0 <= summary["first_sample_ms"] <= summary["first_send_ms"]
        assert 450 <= summary["first_send_ms"] <= summary["first_payload_ack_ms"]
        assert summary["first_retransmit_ms"] is None
        if reply:
            assert summary["first_receive_ms"] >= 1450
            assert summary["first_receive_ms"] >= summary["first_payload_ack_ms"]
        else:
            assert summary["first_receive_ms"] is None
        print(json.dumps(summary), flush=True)
PYTHON
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 150 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short \
  --basetemp "$D/pytest" tests/test_cdn_tcp_observation.py \
  tests/test_standalone_cdn_compare.py tests/test_selective_probe_watch.py \
  tests/test_desync_route_evidence.py
run_phase LOOPBACK loopback
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

- **CONTRACTS** — числа из `CONTRACTS.log`. Отдельно отметь
  отсчёты за границами окна, повтор строки одного опроса,
  фильтр маршрута и допустимые значения времён.
- **LOOPBACK** — укажи два исхода из `LOOPBACK.log`, число
  выборок, первое наблюдение ACK и приёма, наибольший интервал.
  Состояние `ack_without_tcp_data` ожидается в опыте без ответа.
  В другом опыте нужен `tcp_data_received` после задержки ответа.
- **Шлюз** — итог сверки снимков и хэшей. Живые данные для
  обновлённой диагностики получаются в следующей сопоставимой
  паре по плану T04.

## Автоматическая публикация

Укажи абсолютный путь Markdown-отчёта в `REPORT_SRC`. Публикуй
версии, SHA, исходы, времена и агрегаты. Приватные артефакты,
адреса и настройки оставь на машине.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t04-tcp-timing-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-cdn-tcp-timing.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre TCP socket observation timings'
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
