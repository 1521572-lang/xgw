# ThinkCentre — медиамаршрут Selective и возврат на VPN, редакция 2

Исполнитель — Flash, который проводил живой прогон CDN и mpv. Сам открой
терминал ThinkCentre под пользователем рабочего стола, войди в панель XGW
и выполни проверку. Для действий в панели используй vision при необходимости.
При недоступных терминале, sudo или панели запроси доступ у владельца.
После выдачи доступа продолжи сам. Твоя задача — техническая проверка и
публикация отчёта. За системный код отвечает Codex.

Ubuntu 24.04 LTS amd64. Установленная база `3a00777` поверх `08d31ee`,
инструменты `1e0c290` из отдельного дерева. Допуск 4/4 и воспроизведение
914,6 и 315,2 секунды уже приняты. В этом проходе нужны два коротких окна
для доказательства медиамаршрута и один новый CDN-запрос внутри fallback.
Суточный замер и матрица профилей в проход не входят.
[Предыдущий живой отчёт](../reports/2026-11-20T060738Z_selective-cdn-peer.md)

Другой исполнитель подтвердил 67 тестов, но остановился до живого прогона
из-за ограничений sudo. Повторять этот аудит не требуется.
[Отчёт об аудите](../reports/2026-11-20T092746Z_media-proof-tz-audit.md)

## 1. Доступ и исходное состояние

Выполняй блоки в одном обычном Bash из репозитория XGW. При сбое
обязательного шага переходи к публикации `6, если предохранитель ещё
не запущен, либо к восстановлению `5 и публикации `6, если уже запущен.
Сбои сборщиков и анализатора запиши по отдельности. Пакетный дамп здесь
не нужен.

```bash
set +e
set -uo pipefail
umask 077
BR=integration/zapret2-batch1
CODE=1e0c29099eb1c8186c7c7ffb2f4931adfc988596
BASE=3a00777c21ed017760cb7bfd0bb24478fc1f48ad
PREV=08d31ee93963bb00acb7a2275e7a554efcfb0f05
VIDEO=8plwv25NYRo
PY=/usr/bin/python3
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-media-r2.XXXXXXXX")
BACKUP= UNIT=
result() { printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" | tee -a "$D/steps.tsv"; }
run() {
  local step=$1 rc
  shift
  "$@" >"$D/$step.out" 2>"$D/$step.err"
  rc=$?
  result "$step" "$rc"
  return "$rc"
}
. /etc/os-release
printf '%s\n' "$PRETTY_NAME"
uname -r
awk '/^(NoNewPrivs|CapEff):/ {print}' /proc/self/status
if [[ -n $REPO && -d $D && $ID == ubuntu && $VERSION_ID == 24.04 &&
      $(dpkg --print-architecture) == amd64 ]] &&
   command -v mpv yt-dlp curl grep ss nft flock >/dev/null &&
   sudo -v && sudo -n true; then
  echo ACCESS_OK
else
  echo BLOCKED_ENV
fi
```

Продолжай только после `ACCESS_OK`. Если `sudo` отклонён из-за
`NoNewPrivs=1`, запроси обычный терминал на ThinkCentre с sudo и проверь
заново. Если доступ так и не выдан, опубликуй `BLOCKED_ENV` по `6.
Если тестовый ролик недоступен, допустима одна замена на длинный ролик с
HTTPS-форматом 720p и длительностью не менее 665 секунд. Задай его ID в
`VIDEO` и используй тот же ролик для всех сравнений.

```bash
source_tree() {
  git -C "$REPO" fetch origin "$BR" &&
    git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
    git -C "$REPO" worktree add --detach "$D/source" "$CODE"
}
if run source-tree source_tree && cd "$D/source"; then
  export PYTHONPATH="$D/source/src:$D/source"
  echo SOURCE_OK
else
  echo SOURCE_BLOCKED
fi
```

После `SOURCE_OK` проверь установленную базу и исходный режим.

```bash
compare_package() {
  local path package
  package=$(readlink -f /opt/xgw/lib/xgw) || return
  for path in zapret2.py desync/jobs.py desync/client.py watch/zapret2_control.py daemon.py; do
    git show "$BASE:src/xgw/$path" | sudo -n cmp - "$package/$path" || return
    printf '%s\n' "$path"
  done
  for path in watch/panel.py watch/zapret2_management.py generator/profiles.py \
              net/nft.py net/sysctl.py nfqws2.py; do
    git show "$PREV:src/xgw/$path" | sudo -n cmp - "$package/$path" || return
    printf '%s\n' "$path"
  done
}
off_status() {
  "$PY" -m xgw.desync.client status >"$1" &&
    "$PY" -c 'import json, sys
with open(sys.argv[1]) as stream:
    v = json.load(stream)
assert v["fresh"] and v["policy_matched"]
assert v["mode"] == v["engine_mode"] == v["state"] == "off"' "$1"
}
workers_off() {
  local service fields
  for service in xgw-zapret2.service xgw-nfqws2.service; do
    fields=$(systemctl show "$service" -p ActiveState -p MainPID) || return
    printf '%s\n%s\n' "$service" "$fields"
    grep -Fxq 'MainPID=0' <<<"$fields" &&
      grep -Exq 'ActiveState=(inactive|failed)' <<<"$fields" || return 1
  done
}
diag() { sudo -n env PYTHONPATH="$TOOLS/src:$TOOLS" "$PY" -B -P "$@"; }
prepare_tools() {
  sudo -n test -d /opt/xgw/handoff || sudo -n install -d -m 0755 /opt/xgw/handoff || return
  TOOLS=$(sudo -n mktemp -d /opt/xgw/handoff/media-route-r2-tools.XXXXXXXX) || return
  git archive "$CODE" src/xgw docs/helpers/selective_probe_watch.py \
    docs/helpers/selective_wan_control.py docs/helpers/t11_management_restore.sh |
    sudo -n tar --no-same-owner -x -C "$TOOLS" || return
  sudo -n chmod -R go-w "$TOOLS" || return
  diag -c 'from xgw.desync import route_evidence
from docs.helpers import selective_probe_watch, selective_wan_control
print(route_evidence.__file__)' >"$D/module.txt" &&
    grep -Fx -- "$TOOLS/src/xgw/desync/route_evidence.py" "$D/module.txt"
}
if run base compare_package && run initial-off off_status "$D/initial.json" &&
   run initial-workers workers_off && run initial-daemon systemctl is-active xgw.service &&
   run tools prepare_tools; then
  echo BASE_OK
else
  echo BASE_OR_PANEL_BLOCKED
fi
```

После `BASE_OK` сними короткий контрольный журнал. При отсутствии
`state=read` различай unavailable и unexpected_format. Продолжай другие
измерения, вывод по сокетам пометь частичным. Сверка базы охватывает
11 перечисленных файлов, каждый отмечай отдельно.

```bash
run socket-check diag -m docs.helpers.selective_probe_watch --marked-sockets --seconds 2
run socket-read grep -F '"state": "read"' "$D/socket-check.out"
QUEUE=$(diag -c 'from xgw import config; from xgw.paths import Paths
print(config.load(Paths.from_env().config_file)[0].zapret2.queue_num)')
run conntrack-acct cat /proc/sys/net/netfilter/nf_conntrack_acct
[[ $QUEUE =~ ^[0-9]+$ ]] && echo QUEUE_OK
```

## 2. Контроль VPN, предохранитель и временная политика

После `QUEUE_OK` проверь VPN в off/off. Нужны CDN 206 и 65536 байт,
успешный обычный HTTPS вне списка YouTube и дельта VPN-аутбаунда в
сопоставимых снимках без клиентского правила zapret2.

```bash
resolve() {
  [[ $VIDEO =~ ^[A-Za-z0-9_-]{11}$ ]] || return 2
  timeout 70 yt-dlp --no-playlist --socket-timeout 10 --retries 1 --extractor-retries 1 \
    -f 'bv[height=720][protocol=https]' --dump-single-json \
    "https://www.youtube.com/watch?v=$VIDEO" >"$1" 2>"$1.log"
}
probe206() {
  "$PY" -m docs.helpers.headless_playback "$1" probe >"$2" &&
    "$PY" -c 'import json, sys
with open(sys.argv[1]) as stream:
    v = json.load(stream)
assert v["status"] == 206 and v["bytes"] == 65536' "$2"
}
snapshot() { diag -m xgw.desync.route_evidence snapshot >"$D/$1.json"; }
delta() { "$PY" -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"; }
site() { curl -q -4fsS --noproxy '*' --max-time 15 https://api.ipify.org; }
vpn_site() {
  local label=$1
  snapshot "$label-before" && site && snapshot "$label-after"
}
VPN_FORMAT="$D/format-vpn.json"
if run vpn-resolve resolve "$VPN_FORMAT" &&
   run vpn-media probe206 "$VPN_FORMAT" "$D/vpn-before.json" &&
   run vpn-site vpn_site vpn-site &&
   run vpn-site-delta delta vpn-site-before vpn-site-after; then
  echo VPN_BASELINE_CAPTURED
else
  echo VPN_BASELINE_FAILED
fi
```

Если VPN-контроль не подтверждён, переходи к `6. Иначе убедись, что
другой сетевой эксперимент не идёт, и запусти восстановление по таймеру
90 минут. Сохрани shell открытым до `5, чтобы он удерживал общий lock.

```bash
arm() {
  CFG=$(readlink -e /etc/xgw/config.toml) || return
  PANEL=$(readlink -e /etc/xgw/panel.json) || return
  UNIT="xgw-selective-media-r2-$(date +%s)-$$"
  sudo -n test -d /var/lib/xgw/handoff ||
    sudo -n install -d -m 0755 /var/lib/xgw/handoff || return
  BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/selective-media-r2.XXXXXXXX) || return
  sudo -n cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before" &&
    (sudo -n sha256sum "$CFG" "$PANEL" | sudo -n tee "$BACKUP/config-before.sha256" >/dev/null) &&
    sudo -n chmod 0600 "$BACKUP/config-before.sha256" &&
    sudo -n install -m 0700 "$TOOLS/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh" ||
    return
  sudo -n tee "$BACKUP/guard.sh" >/dev/null <<'SH' || return
#!/bin/bash
set -euo pipefail
backup=$1
exec 8>"$backup/media-restore.lock"
flock 8
[[ -e "$backup/network-test-started" ]] || exit 0
[[ ! -e "$backup/restore-completed" ]] || exit 0
/bin/bash "$backup/restore.sh" "$2" unused "$backup" "$3" accept
SH
  sudo -n chmod 0700 "$BACKUP/guard.sh" &&
    sudo -n systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
      /bin/bash "$BACKUP/guard.sh" "$BACKUP" "$PY" "$PANEL" &&
    sudo -n systemctl is-active "$UNIT.timer" &&
    sudo -n touch "$BACKUP/network-test-started"
}
live() {
  [[ -n $UNIT && -n $BACKUP ]] &&
    sudo -n systemctl is-active --quiet "$UNIT.timer" &&
    sudo -n test -f "$BACKUP/network-test-started" &&
    sudo -n test ! -e "$BACKUP/restore-completed"
}
if exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run live-lock flock -n 9 && sudo -v && run arm arm && live; then
  echo READY_FOR_LIVE
else
  echo LIVE_NOT_STARTED
fi
```

После `READY_FOR_LIVE` выбери Standalone с ранее принятым multisplit,
списком YouTube и выключенной HTTPS-пробой. Дождись
fresh/matched/active/without_vpn и зафиксируй прямой CDN-контроль.
При сбое извлечения URL или GET переходи к `5.

```bash
FORMAT="$D/format-direct.json"
if live && run direct-state "$PY" -m xgw.desync.client status &&
   "$PY" -c 'import json, sys
with open(sys.argv[1]) as stream:
    v = json.load(stream)
assert v["fresh"] and v["policy_matched"] and v["without_vpn"]
assert (v["mode"], v["engine_mode"], v["state"]) == ("standalone", "off", "active")' "$D/direct-state.out" &&
   run direct-resolve resolve "$FORMAT" &&
   run direct-media probe206 "$FORMAT" "$D/direct-check.json"; then
  echo DIRECT_OK
else
  echo DIRECT_CHECK_FAILED
fi
```

После `DIRECT_OK` верни off/off штатной кнопкой. Сохрани настройки
Selective. Проверь `blockers.selective` на ревизии из ответа POST после
появления fresh/matched. Старый URL может блокировать предыдущую ревизию.

```bash
if live && run before-settings off_status "$D/before-settings.json"; then
  "$PY" - "$D" "$FORMAT" >"$D/settings.out" 2>"$D/settings.err" <<'PY'
import http.client, json, sys, time
from pathlib import Path

from docs.helpers.headless_playback import read_format
from xgw.desync.client import Client
from xgw.desync.schema import YOUTUBE_DOMAINS

d, media = map(Path, sys.argv[1:])
previous = json.loads((d / "before-settings.json").read_text())
url, duration, _ = read_format(media)
if duration < 665:
    raise SystemExit("format_too_short_for_seek")
client = Client()
reply = client.request("/api/zapret2/settings", {
    "expected": previous["config_key"],
    "settings": {"strategy": "fake_md5", "domains": list(YOUTUBE_DOMAINS),
                 "youtube_transport_probe": True, "check_seconds": 180, "retry_seconds": 120,
                 "daily_probe_mb": 512, "probe_urls": ["https://www.youtube.com/t/terms", url]},
})
if not reply.get("ok") or not reply.get("config_key"):
    raise SystemExit(reply.get("code", "settings_failed"))
deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    try:
        view = client.request("/api/zapret2/overview")["zapret2"]
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        time.sleep(1)
        continue
    (d / "settings-view.json").write_text(json.dumps(view))
    if (view["fresh"] and view["policy_matched"] and view["config_key"] == reply["config_key"]
            and view["mode"] == view["engine_mode"] == view["state"] == "off"
            and view.get("blockers", {}).get("selective") == []):
        print("SELECTIVE_SETTINGS_READY")
        break
    time.sleep(1)
else:
    raise SystemExit("settings_not_applied_or_selective_blocked")
PY
  settings_rc=$?
  result selective-settings "$settings_rc"
  cat "$D/settings.out"
else
  echo SELECTIVE_SETTINGS_BLOCKED
fi
```

Только после `SELECTIVE_SETTINGS_READY` включи Selective штатной кнопкой.
Дождись fresh/matched/active с `https_reachable`. При fallback запиши
`phase/kind/http` проб страницы и CDN и перейди к восстановлению `5.

## 3. Две короткие фазы с доказательством пути

После fresh/active/https_reachable запусти отдельные наблюдения сокетов
и счётчиков до старта mpv. Быстрый опрос ss идёт независимо от чтения Xray
и nft. Первые 15 с служат фоном. Не запускай параллельный YouTube на стенде
из других окон. Между окнами запроси обычный внешний сайт через VPN и сними счётчики.
Так контрольный запрос не попадёт в окно анализа mpv.

```bash
selective_active() {
  "$PY" - "$1" <<'PY'
import json, sys
from pathlib import Path
from xgw.desync.client import Client
state = Client().request("/api/zapret2/overview")["zapret2"]
Path(sys.argv[1]).write_text(json.dumps(state))
assert state["fresh"] and state["policy_matched"] and state["mode"] == "selective"
assert state["engine_mode"] == "off" and state["state"] == "active"
assert state["evidence"]["transport"] == "https_reachable"
PY
}
capture() {
  local label=$1 gateway marked
  shift
  live && run "$label-active" selective_active "$D/$label-active.json" || return
  diag -m docs.helpers.selective_probe_watch --seconds 180 --queue "$QUEUE" \
    --media-pairs >"$D/$label-gateway.jsonl" 2>"$D/$label-gateway.err" &
  gateway=$!
  diag -m docs.helpers.selective_probe_watch --seconds 180 --marked-sockets \
    >"$D/$label-marked.jsonl" 2>"$D/$label-marked.err" &
  marked=$!
  sleep 15
  run "$label-player" timeout 155 "$PY" -m docs.helpers.headless_playback "$FORMAT" play \
    --seconds 120 --peers --samples "$D/$label-player.jsonl" "$@"
  wait "$gateway"; result "$label-gateway" "$?"
  wait "$marked"; result "$label-marked" "$?"
  run "$label-evidence" "$PY" -m docs.helpers.selective_media_evidence \
    --player "$D/$label-player.jsonl" --gateway "$D/$label-gateway.jsonl" \
    --marked "$D/$label-marked.jsonl"
}
sudo -v && capture initial
if live && run between-active selective_active "$D/between-active.json"; then
  run selective-site vpn_site selective-site
  run selective-site-delta delta selective-site-before selective-site-after
  sudo -v && capture seek --seek-forward 480
fi
```

В обоих окнах запиши длительность сеанса и число принятых пар. Анализатор
берёт интервалы вне служебных проб, сверяет владельца NFQUEUE, PID Xray и
время роста на сокетах одного CDN. Для сопоставления нужны не менее 32 КиБ
на каждой стороне. `media_path=SUPPORTED` означает, что одновременно
вырос downlink аутбаунда zapret2 сверх фона. Подтверди также обычный VPN по
ненулевой дельте соответствующего Xray/sing-box аутбаунда. Значение
`nfqueue=OBSERVED` требует собственных положительных дельт сверх фона.
Поддержка маршрута в коротком окне относится к этому окну.

При нулевых счётчиках сохрани привязанный к времени маленький листинг
`sudo nft -j -a list chain inet xgw_guard zapret2_queue` и строку нужной очереди
из `/proc/net/netfilter/nfnetlink_queue`. Различай ноль, отсутствующий
счётчик и отсутствие пары. Смена CDN-адреса или владельца сокета не годится
для слияния двух окон. Пустой корректный JSONL даёт `UNKNOWN` и код 0. Для отсутствующего или
повреждённого файла запиши код анализатора и продолжай к следующему шагу.
Если в первом отрезке не было передачи, разрешён один
короткий повтор с новым именем. При блокере сообщи точное поле.

## 4. Новый CDN-сеанс внутри автоматического fallback

Выполни один SIGKILL только для MainPID `xgw-zapret2.service`. Перед
этим подтверди active, принадлежность очереди и срок VPN-адреса из `2.
Адрес был получен через VPN, а сам GET откроет новое соединение.
Если адрес истёк, переходи к ручному контролю в `5 с новой ссылкой.

```bash
if live && sudo -v &&
   run fallback-active selective_active "$D/fallback-active.json" &&
   run fallback-url "$PY" -c 'import sys
from pathlib import Path
from docs.helpers.headless_playback import read_format
read_format(Path(sys.argv[1]))' "$VPN_FORMAT" &&
   run fallback-owner diag -c 'import sys
from xgw.desync import worker
from xgw.net import cmd
assert worker.verify_owner(cmd.run, worker.SELECTED_UNIT, int(sys.argv[1]))' "$QUEUE"; then
  "$PY" - "$D" "$VPN_FORMAT" "$TOOLS" >"$D/fallback.out" 2>"$D/fallback.err" <<'PY'
import http.client, json, subprocess, sys, time
from pathlib import Path

from xgw.desync.client import Client

d, media, tools = map(Path, sys.argv[1:])
client = Client()
revision = json.loads((d / "fallback-active.json").read_text())["config_key"]
started = time.monotonic()

def record(step, **fields):
    print(json.dumps({"step": step, "seconds": round(time.monotonic() - started, 3), **fields}),
          flush=True)

def card(label):
    try:
        view = client.request("/api/zapret2/overview")["zapret2"]
    except (ValueError, OSError, KeyError, http.client.HTTPException) as exc:
        record(label, error=type(exc).__name__)
        return {}
    record(label, state=view.get("state"), fresh=view.get("fresh"))
    (d / f"{label}.json").write_text(json.dumps(view))
    return view

def in_fallback(view):
    return (view.get("fresh") is True and view.get("policy_matched") is True
            and view.get("config_key") == revision and view.get("mode") == "selective"
            and view.get("state") == "fallback")

def command(label, args, limit):
    record(label + "-start")
    try:
        with (d / f"{label}.json").open("w") as out:
            rc = subprocess.run(args, stdout=out, timeout=limit, check=False).returncode
    except (OSError, subprocess.SubprocessError) as exc:
        record(label + "-error", error=type(exc).__name__)
        return False
    record(label + "-end", rc=rc)
    return rc == 0

def snapshot(label):
    args = ["sudo", "-n", "env", f"PYTHONPATH={tools / 'src'}:{tools}", sys.executable,
            "-B", "-P", "-m", "xgw.desync.route_evidence", "snapshot"]
    if command(label, args, 7):
        return json.loads((d / f"{label}.json").read_text())
    return {}

if not command("worker-kill", ["sudo", "-n", "systemctl", "kill", "--kill-whom=main",
                              "--signal=SIGKILL", "xgw-zapret2.service"], 7):
    raise SystemExit("worker_kill_failed")

deadline = time.monotonic() + 45
poll = 0
while time.monotonic() < deadline:
    poll += 1
    if in_fallback(card(f"fallback-poll-{poll}")):
        before = snapshot("fallback-route-before")
        if before.get("client_zapret2_rule") is False and in_fallback(card("fallback-before-get")):
            command("fallback-media", [sys.executable, "-m", "docs.helpers.headless_playback",
                                       str(media), "probe"], 26)
            card("fallback-after-get")
            if snapshot("fallback-route-after"):
                command("fallback-delta", [sys.executable, "-m", "xgw.desync.route_evidence",
                                           "delta", str(d / "fallback-route-before.json"),
                                           str(d / "fallback-route-after.json")], 7)
            card("fallback-after-snapshots")
            break
    time.sleep(0.5)
else:
    record("fallback-proof-window-not-observed")
PY
  result fallback-script "$?"
else
  echo FALLBACK_NOT_RUN
fi
```

Для `AUTO_FALLBACK=PASS` нужны fresh/matched fallback на той же ревизии
до и после GET, HTTP 206 и 65536 байт, сопоставимые снимки с закрытым
клиентским правилом и рост VPN-аутбаунда сверх фона. Если active вернулся
до конца запроса или дельту нельзя отнести к запросу, укажи PARTIAL.
Если окно доказано, а GET завершился ошибкой, укажи FAIL с кодом и фазой.
Служебную VPN-пробу и повторный active отметь отдельно. Если нужно
проверить повторный active, наблюдай панель ещё до 150 секунд, затем `5.

## 5. Восстановление

Сначала верни off/off штатной кнопкой, если таймер ещё не начал
восстановление. При недоступной панели сразу выполни следующий блок.
Ручной вход и таймер используют один lock и проверяют один маркер,
поэтому после успешного восстановления второй вызов ничего не меняет.

```bash
verify_restore() {
  local failed=0
  run restore-marker sudo -n test -f "$BACKUP/restore-completed" || failed=1
  run restore-hashes sudo -n sha256sum -c "$BACKUP/config-before.sha256" || failed=1
  run restore-daemon systemctl is-active xgw.service || failed=1
  run restore-workers workers_off || failed=1
  run restore-panel off_status "$D/final.json" || failed=1
  run restore-route snapshot restored || failed=1
  run restore-gate "$PY" -c 'import json, sys
with open(sys.argv[1]) as stream:
    v = json.load(stream)
assert v["client_zapret2_rule"] is False' "$D/restored.json" || failed=1
  run restore-site site || failed=1
  return "$failed"
}
stop_timer() {
  run timer-stop sudo -n systemctl stop "$UNIT.timer" &&
    run timer-state systemctl show "$UNIT.timer" -p ActiveState &&
    grep -Fxq 'ActiveState=inactive' "$D/timer-state.out"
}
RESTORE_OK=0
finish_restore() {
  if verify_restore; then
    if stop_timer; then
      RESTORE_OK=1
      echo RESTORE_VERIFIED
    else
      echo TIMER_STOP_UNCONFIRMED
    fi
  else
    echo RESTORE_UNCONFIRMED
  fi
}
if [[ -n $BACKUP && -n $UNIT ]] && sudo -v; then
  if sudo -n test -f "$BACKUP/network-test-started"; then
    run restore sudo -n /bin/bash "$BACKUP/guard.sh" "$BACKUP" "$PY" "$PANEL"
    finish_restore
  elif sudo -n bash -c 'test -f "$1/guard.sh" && test ! -e "$1/network-test-started"' bash "$BACKUP"; then
    stop_timer
  fi
  run timer-final systemctl show "$UNIT.timer" -p ActiveState -p SubState
fi
```

При сбое проверки оставь таймер как есть, зафиксируй его фактическое
состояние и сразу сообщи владельцу, что именно не подтверждено.
При кратковременной задержке панели повтори `finish_restore`.
При `RESTORE_VERIFIED` сделай отдельный ручной
VPN-контроль и освободи lock по окончании сетевых операций.

```bash
if [[ ${RESTORE_OK:-0} == 1 ]] && run final-resolve resolve "$D/format-vpn-final.json"; then
  run final-before snapshot final-before
  run final-media probe206 "$D/format-vpn-final.json" "$D/vpn-final.json"
  run final-after snapshot final-after
  run final-delta delta final-before final-after
fi
exec 9>&-
```

## 6. Отчёт и автоматическая публикация

Сам опубликуй один обезличенный отчёт при любом исходе. Укажи Ubuntu,
ревизии, исходное состояние, доступность sudo и этап остановки, если был.
Выведи отдельно `INITIAL_PLAY`, `SEEK_PLAY`, `MEDIA_PATH`, `NFQUEUE`,
`VPN_OTHER_SITE`, `AUTO_FALLBACK`, `MANUAL_VPN` и `RESTORE`. Включи
пригодные секунды, число совпавших интервалов, HTTP и размер, относительное
время событий fallback, сравнимость снимков, дельты и состояние таймера.
Сырые журналы, URL, IP, cookie и конфиги оставь на машине.
Если терминал так и не выдан, опубликуй `BLOCKED_ENV` доступным способом
на GitHub.

```bash
if PUB=$(mktemp -d "$HOME/xgw-media-r2-publish.XXXXXXXX") &&
   git -C "$REPO" fetch origin "$BR" &&
   git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD &&
   cd "$PUB/repo"; then
  REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_selective-media-proof-r2.md"
  printf 'Заполни %s\n' "$REPORT"
else
  echo PUBLICATION_CHECKOUT_FAILED
fi
```

Заполни файл по фактическим результатам, затем выполни публикацию.

```bash
if [[ -n ${REPORT:-} ]] && test -s "$REPORT" && git add -- "$REPORT" &&
   test "$(git diff --cached --name-only)" = "$REPORT" && git diff --cached --check &&
   git commit -m "docs: report Selective media proof rerun on ThinkCentre"; then
  if ! git push origin "HEAD:refs/heads/$BR"; then
    git fetch origin "$BR" && git rebase FETCH_HEAD && git push origin "HEAD:refs/heads/$BR"
  fi
  SHA=$(git rev-parse HEAD)
  if git fetch origin "$BR" && git merge-base --is-ancestor "$SHA" FETCH_HEAD; then
    printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
  else
    echo PUBLICATION_UNCONFIRMED
  fi
fi
```
