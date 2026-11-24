# ThinkCentre · подтверждение маршрута по журналу Xray

**Ubuntu 24.04 LTS.** Flash сама запускает команды и публикует один
обезличенный отчёт. При отсутствии терминала, sudo, доступа к журналу,
pytest или GitHub запроси доступ. Проведи доступные этапы при блокере.
Код, сценарии и критерии меняет Codex.

[Отчёт о смене CDN](../reports/2026-11-24T194402Z_t04-cdn-reload-xray.md)
подтвердил 202 контракта и все 11 проверок маршрута после локальной правки
стенда. Форма `//узел:порт` появляется у HTTP CONNECT. В новой версии
стенд и анализаторы читают её вместе с `tcp:`. Стенд сверяет локальный
адрес и порт конкретного CONNECT, назначение и вход. При расчёте по
архиву также сверяются эпоха Xray и временное окно. Две записи одного
сокета, даже в разных формах, дают неоднозначный результат.
[HTTP-вход Xray](https://github.com/XTLS/Xray-core/blob/676eaf6/proxy/http/server.go#L125-L145) ·
[Запись маршрута](https://github.com/XTLS/Xray-core/blob/676eaf6/app/dispatcher/default.go#L465-L479)

## Запуск

Начни из рабочей копии. Для netns и снимков проверь `sudo -n true`,
при необходимости авторизуйся через `sudo -v`. Если нужен существующий
venv с pytest, задай абсолютный путь в `XGW_TEST_PYTHON`. В netns
используются установленный Xray и системный Python с pytest. Пакет
шлюза и настройки остаются на месте. XRAY использует локальные выходы
blackhole, REPLAY читает сохранённые журналы и снимки без WAN-запросов.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=54e15083bd927d8cc35ab6912c4b95212a623ab4
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-xray-access.XXXXXXXX")
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
/opt/xgw/xray/xray version | sed -n '1p' || true
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n timeout -k 3 60 "$PY" -I -B - snapshot &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
run_phase() {
  local label=$1 rc=0
  shift
  "$@" >"$D/$label.log" 2>&1 || rc=$?
  tail -n 18 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$rc"
  return "$rc"
}
contracts() {
  timeout -k 3 120 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -v --tb=short --basetemp "$D/pytest" tests/test_desync_route_evidence.py \
    tests/test_selective_probe_watch.py tests/test_standalone_cdn_compare.py
}
xray_trial() (
  local root
  root=$(sudo -n mktemp -d /var/tmp/xgw-xray-access.XXXXXXXX) || exit $?
  [[ $root =~ ^/var/tmp/xgw-xray-access\.[A-Za-z0-9]{8}$ ]] || exit 2
  trap 'sudo -n rm -rf -- "$root"' EXIT
  git -C "$REPO" archive "$CODE" src tests docs/helpers |
    sudo -n tar --no-same-owner -x -C "$root" || exit $?
  timeout -k 3 70 sudo -n unshare --net -- /usr/bin/env -i \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$root:$root/src:$root/tests" \
    "$PY" -B -P "$root/docs/helpers/cdn_reload_xray_check.py"
)
replay() (
  local label=$1 prefix limits boot pid begin end
  prefix=${2:-}
  if [[ -z $prefix ]]; then
    prefix=$(find "$HOME" -maxdepth 2 -type f -path '*/xgw-standalone-live.*/*' \
      -name 'direct-counters-before.out' \
      -printf '%T@ %h\n' | sort -nr | sed -n '1s/^[^ ]* //p')
    [[ -n $prefix ]] || { echo NOT_AVAILABLE; exit 3; }
    prefix="$prefix/$label"
  fi
  local before=$prefix-counters-before.out after=$prefix-counters-after.out
  local journal=$D/$label.journal
  [[ -s $before && -s $after && -s $prefix-cdn.out ]] || { echo NOT_AVAILABLE; exit 3; }
  limits=$("$PY" -I - "$before" "$after" <<'PY'
import json
import math
import sys
from pathlib import Path
from uuid import UUID

before, after = (json.loads(Path(p).read_bytes()) for p in sys.argv[1:])
boot, pid, _ = before["xray_epoch"].split(":")
assert before["xray_epoch"] == after["xray_epoch"]
assert int(pid) > 0 and 0 < after["unix"] - before["unix"] <= 180
print(UUID(boot).hex, int(pid), math.floor(before["unix"]), math.ceil(after["unix"]) + 1)
PY
  ) || exit 2
  read -r boot pid begin end <<<"$limits"
  local -a query=(-q --no-pager -b "$boot" -u xgw-xray.service "_PID=$pid" \
                   --since "@$begin" --until "@$end" -n 5000 -o json \
                   --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT)
  if ! timeout -k 2 12 journalctl "${query[@]}" >"$journal" || [[ ! -s $journal ]]; then
    timeout -k 2 12 sudo -n journalctl "${query[@]}" >"$journal" || exit 3
  fi
  [[ -s $journal ]] || { echo JOURNAL_UNAVAILABLE; exit 3; }
  timeout -k 2 15 "$PY" -B -P -m docs.helpers.standalone_cdn_compare route \
    "$prefix-cdn.out" "$before" "$after" <"$journal"
)

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
contracts_rc=0
run_phase CONTRACTS contracts || contracts_rc=$?
xray_rc=0
run_phase XRAY xray_trial || xray_rc=$?
run_phase REPLAY_DIRECT replay direct "${XGW_REPLAY_DIRECT_PREFIX:-}" || true
run_phase REPLAY_VPN replay off "${XGW_REPLAY_VPN_PREFIX:-}" || true
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
gateway=NOT_VERIFIED
if [[ $before == 0 && $after == 0 ]]; then
  gateway=DIFFERENT
  if cmp -s "$D/state.before" "$D/state.after"; then gateway=UNCHANGED; fi
fi
printf 'XRAY_ACCESS_GATEWAY_%s\n' "$gateway"
[[ $contracts_rc == 0 && $xray_rc == 0 && $gateway == UNCHANGED ]]
BASH
~~~

## Критерии отчёта

- **CONTRACTS.** Укажи passed, failed и skipped. Отметь точное совпадение
  в обеих формах, отбрасывание UDP, URL с путём, другого сокета и входа,
  неоднозначность при смешанной паре.
- **XRAY.** Все 11 маршрутных меток из прошлого отчёта должны пройти на
  закреплённом коде. При отличии формата опиши структуру строки без
  адресов и портов. Запиши версии Ubuntu и Xray, SHA и сверку шлюза.
- **REPLAY.** Сверь принадлежность архивов прежнему CDN-опыту по времени.
  Если автоматический поиск нашёл другой проход, укажи правильные
  приватные префиксы файлов в `XGW_REPLAY_DIRECT_PREFIX` и
  `XGW_REPLAY_VPN_PREFIX` и повтори блок. Из архива вынеси только
  состояние, группу при точном совпадении и отдельный итог повтора.
  Для отсутствующего журнала или архива укажи причину. Пересчёт
  использует прежние наблюдения. Живая замена и допуск YouTube открыты.

Публикуй только SHA, версии, метки и числовые агрегаты. Оставь подписанные
ссылки, сырые журналы, идентификаторы соединений и пути к ним на машине.

## Автоматическая публикация

Укажи в `REPORT_SRC` абсолютный путь к обезличенному Markdown-отчёту.
Выполни блок при любом исходе из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-xray-access-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t04-xray-access.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Xray access parsing and archived route evidence'
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
