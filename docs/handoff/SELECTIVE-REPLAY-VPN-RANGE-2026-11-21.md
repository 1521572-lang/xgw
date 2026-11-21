# ThinkCentre — разбор маршрутов по журналу и замер HTTP Range через VPN

**Read-Only, Ubuntu 24.04 LTS.** Flash сама запускает команды.
Если недоступен терминал, панель или право чтения нужного файла, запроси
доступ. Выполни каждую доступную часть и опубликуй один обезличенный отчёт.
Установленная база остаётся в off/off. ТЗ записывает только приватные
файлы прогона и новый отчёт в GitHub.

Два штатных допуска на базе дали прямой TLS-таймаут, снятие прямого
правила и проверенный возврат. В архивном `flow-r2b` указаны
`qualified=1, accepted=0, unconfirmed=0`. В версии того прогона
`unconfirmed=qualified−accepted`, поэтому нужно пересчитать сырые
артефакты. Новый вывод учитывает точное совпадение на другом outbound,
отдельные причины отсутствия совпадений и доступные записи Xray
с числовыми TCP-адресами в окне. [Последний отчёт](../reports/2026-11-21T082230Z_selective-recovery-replay.md)

## 1. Подготовка

Запусти из checkout XGW обычным пользователем в Bash. Сохрани этот Bash
до конца. Тесты не обращаются к сети. Если pytest в отдельном окружении,
укажи абсолютный путь к его интерпретатору в `XGW_TEST_PYTHON`.

```bash
set -uo pipefail
umask 077
BR=integration/zapret2-batch1
CODE=feea23c0a8eb7115652775e33b17cc61274f972a
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-vpn-range.XXXXXXXX") || exit 2
SRC="$D/source"
printf 'Private run: %s\n' "$D"
if git -C "$REPO" fetch origin "$BR" &&
   git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
   git -C "$REPO" worktree add --detach "$SRC" "$CODE"; then
  echo SOURCE_READY
else
  echo SOURCE_BLOCKED
fi
run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}
xgw_python() { env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P "$@"; }
```

Выполни после `SOURCE_READY`:

```bash
run helpers env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -m pytest -q -o addopts='' \
  -p no:cacheprovider "$SRC/tests/test_selective_vpn_range.py" \
  "$SRC/tests/test_selective_probe_watch.py"
```

## 2. Архивы и контроль журналирования

Сначала попробуй штатный доступ к журналу от своего пользователя.
Если журнал пуст или неполон из-за прав, повтори чтение соответствующего
окна с `sudo -n journalctl` при доступном sudo. Найди сохранённую пару
для каждой метки и сверь времена с исходным опытом. Для контролей
`flow-selective` и `flow-vpn` ожидается известное положительное
совпадение. [Исходный отчёт о контролях](../reports/2026-11-20T111437Z_selective-flow-evidence.md)

```bash
xgw_replay() {
  local prefix=$1 label=$2 bounds boot pid begin end
  bounds=$("$PY" -I - "${prefix}-route-before.json" "${prefix}-route-after.json" <<'PY'
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
  local journal="$D/$label-journal.jsonl"
  if ! timeout -k 2 12 journalctl "${args[@]}" >"$journal" || [[ ! -s "$journal" ]]; then
    timeout -k 2 12 sudo -n journalctl "${args[@]}" >"$journal" || return
  fi
  [[ -s "$journal" ]] || return 2
  xgw_python -m docs.helpers.selective_flow_evidence --observe-applied-change \
    --player "${prefix}-player.jsonl" --before "${prefix}-route-before.json" \
    --after "${prefix}-route-after.json" <"$journal"
}

if [[ -d "$SRC" ]]; then
  for label in flow-selective flow-vpn writer-media flow-r2b; do
    saved=$(find "$HOME" -maxdepth 3 -type f -path "*/xgw-*/$label-route-before.json" -print -quit)
    if [[ -n $saved ]]; then
      run "replay-$label" xgw_replay "${saved%-route-before.json}" "$label"
    else
      printf '%s\tNOT_AVAILABLE\n' "$label" | tee -a "$D/steps.tsv"
    fi
  done
fi
```

В отчёт идут первичные агрегаты из `replay-*.out`. Для сравнимых
контролей укажи `groups` и `unmatched`. Для изменившихся окон укажи
`logged_zapret2`. Сверь
`qualified = accepted_flows + accepted_other_outbound_flows + sum(unmatched.values())`
и `unconfirmed_flows = qualified − accepted_flows`.
`capture_accept_records` — количество подходящих по журналу записей
в окне с валидными TCP-адресами, включая чужие соединения и повторы.
Совпадение с другим outbound означает, что Xray выбрал другой тег
для этого сокета. У изменившегося окна нет данных для вывода о сервере
за таким тегом. Если создалось несколько приватных пар для метки,
используй пару с временем из отчёта и отметь это. При утрате архивов
или журнала запиши `NOT_AVAILABLE`. Смена процесса или конфигурации
сохраняет исходный вердикт всего окна.

## 3. CDN по VPN без установки

Выполни после архива. Нужны исходный off/off, активный Xray, Ubuntu 24.04,
`curl` с `%header{content-range}` (на ThinkCentre был 8.5.0) и живой
обычный HTTPS через `http-in`. Активную политику и конфигурацию проверяем
до и после. При недоступном sudo чтение можно выполнить напрямую, если
у твоего пользователя есть права. При занятом lock или провале контроля
отметь, что A/B не запускался.

```bash
xgw_readonly_vpn() {
  systemctl is-active --quiet xgw.service || return
  systemctl is-active --quiet xgw-xray.service || return
  xgw_python -m xgw.desync.client status | "$PY" -I -c 'import json,sys
v=json.load(sys.stdin)
assert v["fresh"] and v["policy_matched"]
assert v["mode"] == v["engine_mode"] == v["state"] == "off"'
}
xgw_http_port() {
  local path=/etc/xgw/xray/config.json
  local -a python=("$PY" -I -B)
  [[ -r $path ]] || python=(sudo -n "${python[@]}")
  "${python[@]}" - "$path" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    inbounds = json.load(f)["inbounds"]
port, = [r["port"] for r in inbounds if r.get("tag") == "http-in"
         and r.get("listen") == "127.0.0.1" and r.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PY
}
xgw_https_control() {
  curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$PORT" --output /dev/null --write-out '%{http_code}\n' \
    https://example.org/
}
xgw_settings_hash() {
  local -a files=(/etc/xgw/config.toml /etc/xgw/panel.json)
  if [[ -r ${files[0]} && -r ${files[1]} ]]; then sha256sum "${files[@]}"
  else sudo -n sha256sum "${files[@]}"
  fi
}
if [[ -d "$SRC" ]] && exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run vpn-lock flock -n 9 && run vpn-before xgw_readonly_vpn &&
   PORT=$(xgw_http_port) && run https-before xgw_https_control &&
   xgw_settings_hash >"$D/settings-before.sha256"; then
  VIDEO=8plwv25NYRo
  if timeout -k 2 65 yt-dlp --ignore-config --proxy "http://127.0.0.1:$PORT" --no-playlist \
      --socket-timeout 10 --retries 1 --extractor-retries 1 \
      -f 'bv[height=720][protocol=https]' --dump-single-json \
      "https://www.youtube.com/watch?v=$VIDEO" >"$D/format.json" 2>"$D/resolve.err"; then
    run vpn-range xgw_python -m docs.helpers.selective_vpn_range "$D/format.json" --proxy-port "$PORT"
  else
    echo VPN_RANGE_RESOLVE_BLOCKED
  fi
  run vpn-after xgw_readonly_vpn
  run https-after xgw_https_control
  xgw_settings_hash >"$D/settings-after.sha256" &&
    run settings-unchanged cmp -s "$D/settings-before.sha256" "$D/settings-after.sha256"
else
  echo VPN_RANGE_BLOCKED
fi
exec 9>&-
```

A — один запрос на 4 МиБ. B — четыре последовательных запроса по
1 МиБ на тот же диапазон и URL. Порядок A–B–B–A, до 25 секунд на
вариант, общий медиабюджет до 16 МиБ. `comparable` требует
HTTP 206, точные `Content-Range` и число байт в каждом запросе.
Укажи скорости обоих замеров A и обоих B в Б/с, времена до первого
байта, а для неполных этапов — код, байты, причину и `curl_rc`.
Разброс по повторам оставь видимым. Опыт измеряет влияние дробления
Range на одном URL через VPN. Через локальный прокси фактический
CDN IP не атрибутируется. В отчёте не публикуй URL или исходящие IP.

## 4. Отчёт

Опубликуй один обезличенный Markdown-отчёт при любом исходе по §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) с суффиксом
`_selective-replay-vpn-range.md` в `integration/zapret2-batch1`.
Включи SHA инструмента, проверку счётчиков архива, `VPN_RANGE`,
VPN до/после и проверку SHA настроек. Сырые журналы, таймстампы
соединений, подписанный URL и настройки остаются на машине.
Проверь наличие коммита в удалённой ветке и верни ссылку.
