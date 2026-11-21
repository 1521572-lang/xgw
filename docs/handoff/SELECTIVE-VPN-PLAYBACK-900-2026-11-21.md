# ThinkCentre — 900 секунд видео после проверки пропускной способности VPN

**Read-Only, Ubuntu 24.04 LTS.** Flash сама запускает проверку и публикует
один отчёт при любом исходе. Для недоступного терминала, панели или sudo
запроси доступ. Окно процесса плеера ограничено 980 секундами.
Рабочий режим — off/off. Команды читают состояние, загружают один
видеоформат и пишут приватные файлы опыта.

Через штатный VPN один непрерывный ответ доставил 24 МиБ со скоростью
206 КБ/с в первые 5 с и 203 КБ/с в поздних интервалах. Запас к
битрейту формата был примерно 2×. Второй запрос получил 302 до
передачи тела. Проверяем, соответствует ли такой запас длительному
воспроизведению на текущем маршруте. Источник ограничения скорости
остаётся открытым. [Отчёт о загрузке](../reports/2026-11-21T095638Z_selective-vpn-profile.md)

## 1. Подготовка и контроль

Начни в Bash из checkout XGW как обычный пользователь. Если pytest
установлен в отдельном окружении, укажи абсолютный путь к его
интерпретатору в `XGW_TEST_PYTHON`.

```bash
set -uo pipefail
umask 077
BR=integration/zapret2-batch1
CODE=aed27a1bb9e6d8a9bf5c098912902d4a6d886476
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-vpn-play.XXXXXXXX") || exit 2
SRC="$D/source"
printf 'Private run: %s\n' "$D"
git -C "$REPO" fetch origin "$BR" &&
  git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
  git -C "$REPO" worktree add --detach "$SRC" "$CODE" || exit 2
run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}
xgw_python() { env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P "$@"; }
xgw_headless_tests() (
  cd "$SRC" || exit 2
  env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest -q -o addopts='' \
    -p no:cacheprovider tests/test_youtube_telemetry.py -k headless
)
run play-unit xgw_headless_tests
```

После `play-unit=0` определи только функции `xgw_readonly_vpn`,
`xgw_http_port`, `xgw_https_control` и `xgw_checksum` из §2
[ТЗ профиля VPN](SELECTIVE-VPN-PROFILE-2026-11-21.md). Они проверяют
off/off, штатный HTTP-прокси и SHA настроек. Затем продолжай в том же Bash.

```bash
READY=0
CONTROL_READY=0
if exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run vpn-lock flock -n 9 && run vpn-before xgw_readonly_vpn &&
   PORT=$(xgw_http_port) && run https-before xgw_https_control &&
   run settings-before xgw_checksum /etc/xgw/config.toml /etc/xgw/panel.json; then
  CONTROL_READY=1
  VIDEO=8plwv25NYRo
  if timeout -k 2 65 yt-dlp --ignore-config --proxy "http://127.0.0.1:$PORT" --no-playlist \
      --socket-timeout 10 --retries 1 --extractor-retries 1 \
      -f 'bv[height=720][protocol=https]' --dump-single-json \
      "https://www.youtube.com/watch?v=$VIDEO" >"$D/format.json" 2>"$D/resolve.err"; then
    READY=1
  fi
fi
```

Если `READY=0`, зафиксируй блокер и перейди к заключительному
контролю. Короткий контроль через `http-in` относится к состоянию VPN.
Плеер запускается обычным клиентом шлюза. Для подтверждения его пути
нужны сокет и запись Xray из следующего блока.

## 2. Один запуск mpv и проверка маршрута на старте

Снимок Xray использует код из отдельного root-owned каталога,
как в принятой проверке медиапотока. При невозможности получить снимок
запиши ограничение и оцени качество по журналу плеера.

```bash
xgw_prepare_snapshots() {
  sudo -n install -d -m 0755 /opt/xgw/handoff || return
  TOOLS=$(sudo -n mktemp -d /opt/xgw/handoff/vpn-play.XXXXXXXX) || return
  git -C "$REPO" archive "$CODE" src/xgw |
    sudo -n tar --no-same-owner -x -C "$TOOLS" || return
  sudo -n chmod -R go-w "$TOOLS"
}
xgw_play_snapshot() {
  sudo -n env "PYTHONPATH=$TOOLS/src" "$PY" -B -P -m xgw.desync.route_evidence snapshot
}
xgw_play_flow() {
  local bounds boot pid begin end
  bounds=$("$PY" -I - "$D/route-before.out" "$D/route-after.out" <<'PY'
import json, math, sys
from pathlib import Path
from uuid import UUID

a, b = (json.loads(Path(p).read_bytes()) for p in sys.argv[1:])
boot, pid, _ = a["xray_epoch"].split(":")
assert a["xray_epoch"] == b["xray_epoch"] and int(pid) > 0
assert 0 < b["unix"] - a["unix"] <= 180
print(UUID(boot).hex, int(pid), math.floor(a["unix"]), math.ceil(b["unix"]) + 1)
PY
  ) || return
  read -r boot pid begin end <<<"$bounds"
  local -a args=(-q --no-pager -b "$boot" -u xgw-xray.service "_PID=$pid"
                 --since "@$begin" --until "@$end" -n 5000 -o json
                 --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT)
  if ! timeout -k 2 12 journalctl "${args[@]}" >"$D/route-journal.jsonl" ||
     [[ ! -s "$D/route-journal.jsonl" ]]; then
    timeout -k 2 12 sudo -n journalctl "${args[@]}" >"$D/route-journal.jsonl" || return
  fi
  [[ -s "$D/route-journal.jsonl" ]] || return 2
  xgw_python -m docs.helpers.selective_flow_evidence --observe-applied-change \
    --player "$D/play-samples.jsonl" --before "$D/route-before.out" \
    --after "$D/route-after.out" <"$D/route-journal.jsonl"
}

if [[ $READY == 1 ]]; then
  PROOF=0
  if run snapshot-tools xgw_prepare_snapshots && run route-before xgw_play_snapshot; then
    PROOF=1
  fi
  run play-900 timeout -k 4 980 env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P \
    -m docs.helpers.headless_playback "$D/format.json" play --seconds 900 \
    --strict --peers --samples "$D/play-samples.jsonl" &
  PLAY_JOB=$!
  if [[ $PROOF == 1 ]]; then
    for tick in {1..30}; do
      kill -0 "$PLAY_JOB" 2>/dev/null || break
      sleep 5
    done
    run route-after xgw_play_snapshot || PROOF=0
  fi
  wait "$PLAY_JOB"
  if [[ $PROOF == 1 && -s "$D/play-samples.jsonl" ]]; then
    run flow-start xgw_play_flow
  fi
fi
```

Прими `PLAY_900=PASS` только при `acceptance.ok=true` и `outcome=elapsed`.
Первая полная фаза длится 900 с от начала воспроизведения. Пороги —
720p ≥99% измеренного времени, прогресс ≥98%, сумма остановок ≤9 с,
наибольшая наблюдаемая остановка ≤5 с и пропуски измерения ≤5 с.
Укажи все метрики `acceptance`, а также минимальный буфер и медиану
чтения mpv. Оценка остановок основана на положении видео и флаге кеша
в секундных выборках.

Отдельно укажи `FLOW_START`. При `state=observed`, хотя бы одном
сопоставленном потоке и `client_zapret2_rule=false` запиши группы
`xray` и `sing-box`, если они наблюдались. При неполном
сопоставлении укажи `unmatched`. `inconclusive` сохраняет этот
вердикт даже при наличии диагностических совпадений. Снимки охватывают
только стартовое окно. Они не описывают все подключения за 900 с.

## 3. Конечный контроль и публикация

Проверь off/off, HTTPS через прежний HTTP-вход и SHA настроек,
если начальный контроль прошёл. Закрой свой lock.

```bash
if [[ ${CONTROL_READY:-0} == 1 ]]; then
  run vpn-after xgw_readonly_vpn
  run https-after xgw_https_control
  if run settings-after xgw_checksum /etc/xgw/config.toml /etc/xgw/panel.json; then
    run settings-unchanged cmp -s "$D/settings-before.out" "$D/settings-after.out"
  fi
fi
exec 9>&-
```

Опубликуй один обезличенный отчёт при любом исходе по §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) с суффиксом
`_selective-vpn-playback-900.md` в `integration/zapret2-batch1`.
Укажи SHA инструмента, тесты, `PLAY_900`, `FLOW_START`, состояние
шлюза и значения контрольных проверок. Не публикуй URL, IP, PID,
хэши файла и исходные журналы. Проверь коммит в удалённой ветке и верни ссылку.
