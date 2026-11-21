# ThinkCentre — пересчёт метрик плеера и проверка правил XGW

**Ubuntu 24.04 LTS, Read-Only для шлюза.** Flash сама запускает
готовые команды и публикует один обезличенный отчёт при любом исходе.
Если недоступны терминал, панель или sudo, запроси доступ. Для пересчёта
используются сохранённые измерения mpv на ThinkCentre. Проверка ядром
выполняется в отдельном сетевом пространстве имён Linux.

Уже приняты 900 секунд обычного воспроизведения и 300 секунд после
перемотки за пределы буфера. Во втором окне подтверждён один
медиасокет через VPN Xray, видео прошло в 720p без остановок.
Пересчёт проверяет, что короткий буфер зафиксирован отдельной метрикой,
а вердикт принятого окна сохранился. Следующая часть выполняет
сетевые проверки T03–T05 по результатам аудита A2/A4/A5.
[Отчёт 900 с](../reports/2026-11-21T105249Z_selective-vpn-playback-900.md) ·
[Отчёт seek r2](../reports/2026-11-21T112442Z_selective-vpn-seek-300.md)

## 1. Запуск проверки

Выполни весь блок одним вызовом Bash из checkout XGW как обычный
пользователь панели. При необходимости экспортируй абсолютный
`XGW_TEST_PYTHON`. Проверь `sudo -n true`. Для интерактивного
подтверждения используй `sudo -v` в доступном терминале перед запуском.
Запиши ОС, ядро и версию nftables.

Если ранее сохранённые окна находятся в другом месте или найдено
несколько копий, укажи абсолютный путь к исходному каталогу окна в
`XGW_REPLAY_900_DIR` или `XGW_REPLAY_SEEK_DIR`. Сверь выбор с
приватными сводками двух отчётов. При отсутствии файлов проверь
остальные блоки и зафиксируй `NOT_AVAILABLE` для этого окна.

```bash
bash <<'BASH'
set -uo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
BR=integration/zapret2-batch1
CODE=06cad1085d4b684abbaff4f8ec44c064a8486ac3
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-playback-marks.XXXXXXXX") || exit 2
SRC="$D/source"
printf 'Private run: %s\n' "$D"
git -C "$REPO" fetch origin "$BR" &&
  git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
  git -C "$REPO" worktree add --detach "$SRC" "$CODE" || exit 2
trap 'git -C "$REPO" worktree remove "$SRC"' EXIT

run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}
xgw_python() { env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P "$@"; }
contracts() (
  cd "$SRC" || exit 2
  [[ $TEST_PY == /* && -x $TEST_PY ]] || exit 2
  timeout -k 4 180 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
    -q -o addopts='' -p no:cacheprovider "$@"
)
replay() {
  local name=$1 pattern=$2 directory=$3 summary_bytes samples_bytes
  local -a candidates=()
  if [[ -z $directory ]]; then
    mapfile -d '' -t candidates < <(find "$HOME" -maxdepth 2 -type f -size +0c \
      -path "$HOME/$pattern/$name.out" -print0)
    if [[ ${#candidates[@]} != 1 ]]; then
      printf 'archive_count=%s\n' "${#candidates[@]}" >&2
      return 3
    fi
    directory=${candidates[0]%/*}
  fi
  [[ $directory == /* && -f $directory/$name.out && -O $directory/$name.out &&
     -f $directory/play-samples.jsonl && -O $directory/play-samples.jsonl ]] || return 3
  summary_bytes=$(stat -c %s -- "$directory/$name.out") || return 3
  samples_bytes=$(stat -c %s -- "$directory/play-samples.jsonl") || return 3
  if (( summary_bytes > 16384 || samples_bytes > 8388608 )); then
    echo 'archive_size_limit' >&2
    return 2
  fi
  install -m 0600 -- "$directory/$name.out" "$D/$name.previous.json" &&
    install -m 0600 -- "$directory/play-samples.jsonl" "$D/$name.samples.jsonl" || return 3
  xgw_python -m docs.helpers.headless_playback "$D/$name.previous.json" replay \
    --samples "$D/$name.samples.jsonl"
}
vpn_control() {
  systemctl is-active --quiet xgw.service || return
  systemctl is-active --quiet xgw-xray.service || return
  timeout -k 2 12 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json,sys
v = json.load(sys.stdin)
assert v["fresh"] and v["policy_matched"]
assert v["mode"] == v["engine_mode"] == v["state"] == "off"
print("off/off fresh matched")' || return
  timeout -k 2 12 sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
render_fixture() {
  xgw_python - "$1" <<'PY'
from dataclasses import replace
import sys
from xgw.config import Config
from xgw.net import nft

case = sys.argv[1]
cfg = Config()
cfg.network.lan_if = "lan0"
cfg.network.wan_if = "wan0"
cfg.dns.direct_servers = ["192.0.2.53"]
cfg.capture.containers = case == "containers"
if case == "containers":
    cfg.capture.method = "tun"
if case in ("selected", "selected-replies"):
    cfg.zapret2.mode = "selective"
    cfg.zapret2.observe_synack = True
if case == "tailscale-vpn":
    cfg.tailscale.route = "vpn"
tailscale = case in ("tailscale-direct", "tailscale-vpn")
rules, warnings = nft.build_rules(
    cfg, capture=case != "off", blocked=case == "blocked",
    time_uids=(), tailscale=tailscale, tailnet=tailscale,
)
assert not warnings, warnings
if case == "selected-replies":
    rules = replace(rules, zapret2_reply_packets=8)
if case == "engine":
    rules = replace(rules, engine_queue=cfg.zapret2.engine_queue)
assert (rules.zapret2_queue is not None) == (case in ("selected", "selected-replies"))
assert (rules.engine_queue is not None) == (case == "engine")
assert bool(rules.containers) == (case == "containers")
print(nft.render(rules) + nft.render6(rules) + nft.render_guard(rules))
PY
}
check_fixture() {
  local fixture=$1
  render_fixture "$fixture" >"$D/$fixture.nft" || return
  timeout -k 2 15 sudo -n unshare --net -- nft --check --file - <"$D/$fixture.nft"
}

run vpn-before vpn_control
run replay-900 replay play-900 'xgw-vpn-play.*' "${XGW_REPLAY_900_DIR:-}"
run replay-seek replay play-seek 'xgw-vpn-seek.*' "${XGW_REPLAY_SEEK_DIR:-}"
run player-unit contracts tests/test_youtube_telemetry.py -k headless
run rules-unit contracts tests/test_nft.py tests/test_zapret2.py \
  tests/test_tailscale.py tests/test_tailscale_t2.py
if run sudo sudo -n true; then
  for case in off capture selected selected-replies engine tailscale-direct tailscale-vpn \
      containers blocked; do
    run "netns-$case" check_fixture "$case"
  done
fi
run vpn-after vpn_control
if [[ -s "$D/vpn-before.out" && -s "$D/vpn-after.out" ]]; then
  run control-unchanged cmp -s "$D/vpn-before.out" "$D/vpn-after.out"
fi
BASH
```

## 2. Критерии

- **REPLAY_900 и REPLAY_SEEK** — `PASS` при коде 0,
  `acceptance.ok=true`, `differing_fields=[]` и сохранённом
  `cache_buffer_below_5s=true`. Укажи минимум буфера, медиану
  ненулевых измерений чтения mpv, запас к битрейту, количество
  остановок в секундах и результат строгого окна. Для обоих принятых
  окон ожидается `cache_read_below_bitrate=false`. Различие в
  пересчёте опиши по `differing_fields`. Код 3 означает отсутствие
  подтверждённой пары файлов. Запусти остальные проверки даже в этом
  случае. Результат маршрута остаётся за исходным отчётом seek r2.
- **PLAYER_UNIT и RULES_UNIT** — укажи passed, failed, skipped и первую
  ошибку в обезличенной форме. Пропуски тестов nft под обычным
  пользователем укажи отдельно.
- **NETNS_NFT** — перечисли код каждой из девяти фикстур. Фикстуры
  `selected-replies` и `engine` проверяют синтаксис ветвей для
  доступных счётчиков conntrack. Контрактные тесты проверяют допуск этих
  ветвей. При отказе `unshare` укажи `BLOCKED` и причину.
  Проверка синтаксиса применима к данным фикстурам и ядру ThinkCentre.
  Повторяемый дефект доставки проверяется отдельной топологией из аудита.
- **CONTROL** — код 0 для обеих точек состояния и сравнения SHA,
  после прохода off/off fresh/matched. В отчёт идут коды,
  версии и численные результаты из приватных файлов.

## 3. Публикация

Подготовь один обезличенный отчёт при любом исходе. Укажи закреплённый
SHA, результаты обеих частей и контроль шлюза. Сырые JSONL, журналы,
адреса, конфиги и хэши настроек остаются в приватном каталоге. Укажи
абсолютный путь к готовому отчёту в `REPORT_SRC`, затем сама выполни
весь блок публикации и верни ссылку.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-playback-marks-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_playback-metrics-and-marks.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "Report ThinkCentre playback replay and packet mark checks"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
BASH
```
