# ThinkCentre — медиамаршрут Selective и возврат на VPN

Для повторного запуска используй [редакцию 2](MEDIA-PROOF-2026-11-20-R2.md).
Эта редакция сохранена как основание опубликованного аудита.

Ubuntu 24.04 LTS amd64. Установленная база `3a00777` в пяти файлах поверх
`08d31ee`. Инструменты из `1e0c29099eb1c8186c7c7ffb2f4931adfc988596`.
Flash сама запускает команды, выполняет техническую проверку и автоматически
публикует обезличенный отчёт. При отсутствии терминала, sudo или панели
сама запрашивает доступ. Код и критерии готовит Codex.

Предыдущий проход принял установку, допуск 4/4 на свежем прямом CDN,
914,6 пригодной секунды при 720p и 315,2 после перемотки. Для long медиамаршрут
остался частичным. Контроль после SIGKILL зафиксировал повторный active,
а новый сеанс в доказанном VPN-окне ещё нужно измерить. В этом проходе
достаточно двух коротких медиасеансов. Суточный замер пропущен по решению
владельца. [Последний отчёт](../reports/2026-11-20T060738Z_selective-cdn-peer.md)

## 1. База и проверка импортов

Начни в Bash из репозитория XGW. Используй имеющиеся mpv, curl, yt-dlp и
интерпретатор тестов. Выбери тот же ролик 720p, если доступен, и присвой VIDEO
его ID. Опыт использует только отдельный checkout и временную политику.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
test "$(dpkg --print-architecture)" = amd64
printf '%s\n' "$PRETTY_NAME"
uname -r
BR=integration/zapret2-batch1
CODE=1e0c29099eb1c8186c7c7ffb2f4931adfc988596
BASE=3a00777c21ed017760cb7bfd0bb24478fc1f48ad
PREV=08d31ee93963bb00acb7a2275e7a554efcfb0f05
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-media-route.XXXXXXXX")
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
"$TEST_PY" -m pytest -o addopts='' -q tests/test_selective_probe_watch.py \
  tests/test_desync_route_evidence.py tests/test_youtube_telemetry.py
mpv --version >"$D/mpv-version.txt"
yt-dlp --version
curl --version
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
for path in zapret2.py desync/jobs.py desync/client.py watch/zapret2_control.py daemon.py; do
  git show "$BASE:src/xgw/$path" | sudo cmp - "$PACKAGE/$path"
done
for path in watch/panel.py watch/zapret2_management.py generator/profiles.py \
            net/nft.py net/sysctl.py nfqws2.py; do
  git show "$PREV:src/xgw/$path" | sudo cmp - "$PACKAGE/$path"
done
"$PY" -m xgw.desync.client status >"$D/initial.json"
```

Ожидаются off/off, неактивные воркеры, доступные панель и VPN. Перед
сетевой фазой проверь импорты под sudo из полного дерева с закреплённым SHA.
Именно этих модулей не хватало в предыдущем пакете.

```bash
sudo install -d -m 0755 /opt/xgw/handoff
TOOLS=$(sudo mktemp -d /opt/xgw/handoff/media-route-tools.XXXXXXXX)
git archive "$CODE" src/xgw docs/helpers/selective_probe_watch.py \
  docs/helpers/selective_wan_control.py docs/helpers/t11_management_restore.sh \
  | sudo tar --no-same-owner -x -C "$TOOLS"
sudo chmod -R go-w "$TOOLS"
diag() { sudo -n env PYTHONPATH="$TOOLS/src:$TOOLS" "$PY" -B -P "$@"; }
sudo -v
diag -c 'from xgw.desync import route_evidence
from docs.helpers import selective_probe_watch, selective_wan_control
print(route_evidence.__file__)' >"$D/module.txt"
rg -F "$TOOLS/src/xgw/desync/route_evidence.py" "$D/module.txt"
diag -m docs.helpers.selective_probe_watch --marked-sockets --seconds 2 >"$D/socket-check.jsonl"
rg -F '"state": "read"' "$D/socket-check.jsonl"
QUEUE=$(diag -c 'from xgw import config; from xgw.paths import Paths
print(config.load(Paths.from_env().config_file)[0].zapret2.queue_num)')
cat /proc/sys/net/netfilter/nf_conntrack_acct >"$D/conntrack-acct.txt"
```

Значение sysctl запиши как факт. Исходящее правило Selected в `zapret2_queue`
опирается на fwmark и порт 443. Нулевую дельту счётчика оцени по
фактическому правилу и трафику. При проблеме именно с `--marked-sockets`
укажи состояние read/unavailable/unexpected_format, вывод не подменяй.

## 2. Рабочий формат и временная политика

Сохрани свежий адрес формата через VPN для контрольного запроса после
отказа. Проверь обычный HTTPS-сайт вне списка доменов. Перед изменением
режима используй общий lock и таймер на 90 минут.

```bash
test "${#VIDEO}" -eq 11
resolve() {
  timeout 70 yt-dlp --no-playlist --socket-timeout 10 --retries 1 --extractor-retries 1 \
    -f 'bv[height=720][protocol=https]' --dump-single-json \
    "https://www.youtube.com/watch?v=$VIDEO" >"$1" 2>"$1.log"
}
VPN_FORMAT="$D/format-vpn.json"
resolve "$VPN_FORMAT"
"$PY" -m docs.helpers.headless_playback "$VPN_FORMAT" probe >"$D/vpn-before.json"
curl -4fsS --noproxy '*' --max-time 15 https://api.ipify.org >"$D/vpn-before.ip"
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
UNIT="xgw-selective-media-proof-$(date +%s)"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-media-proof.XXXXXXXX)
sudo cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$TOOLS/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
live() { sudo systemctl is-active --quiet "$UNIT.timer" && sudo test ! -e "$BACKUP/restore-completed"; }
```

Включи Standalone на multisplit со списком YouTube и выключенной
HTTPS-пробой. Дождись свежего active и without_vpn. Извлеки новый URL именно
через Standalone и проверь его GET. Если прямой контроль не прошёл,
запиши исход и восстанови политику. Коды прошлых матриц сохранены в отчёте.

```bash
live
FORMAT="$D/format-direct.json"
resolve "$FORMAT"
"$PY" -m docs.helpers.headless_playback "$FORMAT" probe >"$D/direct-check.json"
```

Верни off/off. Затем через штатный API выбери уже принятый `fake_md5`,
список YouTube, страницу `https://www.youtube.com/t/terms` и новый URL.
Испытание проверяет применённую политику и штатный HTTPS-допуск, поэтому
достаточно ручного выбора принятого профиля через настройки. Дождись
fresh/matched/off и пустого blockers.selective перед включением Selective.

```bash
live
"$PY" - "$FORMAT" <<'PY'
import sys
from pathlib import Path
from docs.helpers.headless_playback import read_format
from xgw.desync.client import Client
from xgw.desync.schema import YOUTUBE_DOMAINS
client = Client()
v = client.request("/api/zapret2/overview")["zapret2"]
assert v["fresh"] and v["policy_matched"] and v["mode"] == v["engine_mode"] == v["state"] == "off"
url, _, _ = read_format(Path(sys.argv[1]))
reply = client.request("/api/zapret2/settings", {
    "expected": v["config_key"],
    "settings": {"strategy": "fake_md5", "domains": list(YOUTUBE_DOMAINS),
                 "youtube_transport_probe": True, "check_seconds": 180, "retry_seconds": 120,
                 "daily_probe_mb": 512, "probe_urls": ["https://www.youtube.com/t/terms", url]},
})
if not reply.get("ok"):
    raise SystemExit(reply.get("code", "settings_failed"))
PY
```

Включи Selective штатной кнопкой. Сохрани `client status` при active. При
fallback запиши phase/kind/http обеих проб и перейди к возврату. Стабильность
применения, playback и маршрут оцениваются по разным артефактам.

## 3. Две короткие фазы с доказательством пути

После fresh/active/https_reachable запусти отдельные наблюдения сокетов
и счётчиков до старта mpv. Быстрый опрос ss идёт независимо от чтения Xray
и nft. Первые 15 с служат фоном. Не запускай параллельный YouTube на стенде
из других окон. Во время теста один раз запроси обычный внешний сайт через
VPN и сними пару счётчиков до и после этого запроса.

```bash
snapshot() { diag -m xgw.desync.route_evidence snapshot >"$D/$1.json"; }
control_site() {
  local label=$1
  snapshot "$label-vpn-before"
  curl -4fsS --noproxy '*' --max-time 15 https://api.ipify.org >"$D/$label-vpn.ip"
  snapshot "$label-vpn-after"
  "$PY" -m xgw.desync.route_evidence delta "$D/$label-vpn-before.json" \
    "$D/$label-vpn-after.json" >"$D/$label-vpn-delta.json"
}
capture() {
  local label=$1
  shift
  live || return
  "$PY" - "$D/$label-active.json" <<'PY'
import json, sys
from pathlib import Path
from xgw.desync.client import Client
state = Client().request("/api/zapret2/overview")["zapret2"]
Path(sys.argv[1]).write_text(json.dumps(state))
assert state["fresh"] and state["policy_matched"] and state["mode"] == "selective"
assert state["state"] == "active" and state["evidence"]["transport"] == "https_reachable"
PY
  sudo -v
  diag -m docs.helpers.selective_probe_watch --seconds 180 --queue "$QUEUE" \
    --media-pairs >"$D/$label-gateway.jsonl" &
  local gateway=$!
  diag -m docs.helpers.selective_probe_watch --seconds 180 --marked-sockets \
    >"$D/$label-marked.jsonl" &
  local marked=$!
  sleep 15
  "$PY" -m docs.helpers.headless_playback "$FORMAT" play --seconds 120 --peers \
    --samples "$D/$label-player.jsonl" "$@" >"$D/$label-player.json" &
  local player=$!
  sleep 20
  control_site "$label" || echo VPN_CONTROL_PARTIAL
  wait "$player" || echo PLAYER_PARTIAL
  wait "$gateway" || echo GATEWAY_CAPTURE_PARTIAL
  wait "$marked" || echo SOCKET_CAPTURE_PARTIAL
  "$PY" -m docs.helpers.selective_media_evidence --player "$D/$label-player.jsonl" \
    --gateway "$D/$label-gateway.jsonl" --marked "$D/$label-marked.jsonl" \
    >"$D/$label-evidence.json"
}
capture initial
capture seek --seek-forward 480
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
для слияния двух окон. Если в первом отрезке не было передачи, разрешён один
короткий повтор с новым именем. При блокере сообщи точное поле.

## 4. Возврат во время автоматического fallback

После проверки медиамаршрута проведи один SIGKILL только для MainPID
`xgw-zapret2.service` после проверки принадлежности очереди. Используй
VPN_FORMAT из §1–2. Нужна свежая передача **до повторного active**.

```bash
live
sudo -v
diag -c 'import sys; from xgw.desync import worker; from xgw.net import cmd
assert worker.verify_owner(cmd.run, worker.SELECTED_UNIT, int(sys.argv[1]))' "$QUEUE"
sudo systemctl kill --kill-whom=main --signal=SIGKILL xgw-zapret2.service
"$PY" - "$D" "$VPN_FORMAT" "$TOOLS" <<'PY'
import json, subprocess, sys, time
from pathlib import Path
from xgw.desync.client import Client
d, media, tools = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
client = Client()
deadline = time.monotonic() + 45
def card():
    return client.request("/api/zapret2/overview")["zapret2"]
def snapshot(label):
    cmd = ["sudo", "-n", "env", f"PYTHONPATH={tools / 'src'}:{tools}",
           sys.executable, "-B", "-P", "-m", "xgw.desync.route_evidence", "snapshot"]
    with (d / f"fallback-{label}-route.json").open("w") as out:
        try:
            return subprocess.run(cmd, stdout=out, timeout=10, check=False).returncode == 0
        except subprocess.TimeoutExpired:
            return False
while time.monotonic() < deadline:
    v = card()
    if v["fresh"] and v["policy_matched"] and v["state"] == "fallback":
        (d / "fallback-before.json").write_text(json.dumps(v))
        before = snapshot("before")
        if card()["state"] == "fallback":
            with (d / "fallback-media.json").open("w") as out:
                subprocess.run([sys.executable, "-m", "docs.helpers.headless_playback",
                                media, "probe"], stdout=out, check=False)
            after = snapshot("after")
            if before and after:
                with (d / "fallback-delta.json").open("w") as out:
                    subprocess.run([sys.executable, "-m", "xgw.desync.route_evidence", "delta",
                                    str(d / "fallback-before-route.json"),
                                    str(d / "fallback-after-route.json")], stdout=out, check=False)
        (d / "fallback-after.json").write_text(json.dumps(card()))
        break
    time.sleep(0.5)
else:
    print("fallback_window_not_observed")
PY
```

Запиши результат служебного VPN-контроля, причину fallback, факт закрытия
gate и время нового CDN-запроса. Для доказательства пути нужен снимок Xray
с выключенным клиентским правилом и ростом VPN-аутбаунда. Если новый active
успел наступить, результат автоматического fallback оставь PARTIAL.
Повтори контроль после штатного off/off и пометь его как ручной возврат.
Отдельно зафиксируй, восстановился ли active автоматически.

## 5. Восстановление и публикация

Сначала верни off/off штатной кнопкой. Если панели нет, используй
предохранитель. Если таймер сработал, проверь его результат прежде чем
запускать restore ещё раз. Проверь хэши файлов, воркеры, панель и новый
VPN-сеанс. После подтверждения погаси свой таймер.

```bash
if [[ -n ${BACKUP:-} ]] && sudo test -f "$BACKUP/restore.sh"; then
  if ! sudo test -f "$BACKUP/restore-completed"; then
    sudo /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
  fi
  sudo sha256sum -c "$BACKUP/config-before.sha256"
  systemctl is-active xgw.service
  systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
  "$PY" -m xgw.desync.client status >"$D/final.json"
fi
```

Опубликуй один обезличенный отчёт при любом исходе. Укажи проверку базы и
импортов, пригодные секунды, число окон с совпавшими сокетами и дельтами,
оба результата VPN и состояние после возврата. Сырые URL, IP, конфиги,
socket cookies и JSONL оставь на машине.

```bash
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$D/publish" FETCH_HEAD
cd "$D/publish"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_selective-media-proof.md"
test ! -e "$REPORT"
# Заполни отчёт.
test -s "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report Selective media path and VPN fallback evidence"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
```
