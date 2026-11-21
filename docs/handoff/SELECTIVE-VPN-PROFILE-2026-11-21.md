# ThinkCentre — профиль длительной загрузки CDN через действующий VPN

**Read-Only, Ubuntu 24.04 LTS.** Flash сама запускает команды и публикует
один отчёт при любом исходе. При недоступном терминале, панели или праве
чтения запроси доступ. Рабочий режим этого опыта — off/off. Используй
штатный HTTP-вход Xray с loopback. В каталоге опыта остаются приватные
исходники, формат и контрольные хэши.

Последний частичный A/B дал 3,40 и 4,20 МБ/с на одиночных 4 МиБ и
1,54 МБ/с в одном полном проходе с четырьмя запросами. Другой проход
прервался на HTTP 302. Новый опыт измеряет длинный непрерывный Range
в двух окнах, чтобы проверить, падает ли скорость внутри одного ответа
после первых 5 секунд. [Отчёт A/B](../reports/2026-11-21T092740Z_selective-replay-vpn-range.md)

## 1. Подготовка

Запусти скрипт из checkout XGW в Bash как обычный пользователь. Если
pytest установлен в отдельном окружении, задай `XGW_TEST_PYTHON`
абсолютным путём. Команда не запускает тесты вне закреплённого worktree.

```bash
set -uo pipefail
umask 077
BR=integration/zapret2-batch1
CODE=c5ed602c5ebfba5f81d388862fe414320a71bec3
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-vpn-profile.XXXXXXXX") || exit 2
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
xgw_profile_tests() (
  cd "$SRC" || exit 2
  env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest -q -o addopts='' \
    -p no:cacheprovider tests/test_selective_vpn_range.py
)
run profile-unit xgw_profile_tests
```

## 2. Два одиночных запроса

Продолжай в том же Bash после `profile-unit=0`. Проверь, что слот
эксперимента свободен. При отказе исходного контроля заверши отчётом.
Снимаются хэш применённого Xray и PID только на границах каждого запроса.
Эти поля нужны для интерпретации и остаются приватными.

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
with open(sys.argv[1]) as stream:
    inbounds = json.load(stream)["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PY
}
xgw_https_control() {
  curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$PORT" --output /dev/null --write-out '%{http_code}\n' \
    https://example.org/
}
xgw_checksum() {
  local file
  for file in "$@"; do
    if [[ -r $file ]]; then sha256sum "$file" || return
    else sudo -n sha256sum "$file" || return
    fi
  done
}
xgw_identity() {
  local pid
  pid=$(systemctl show xgw-xray.service -p MainPID --value) || return
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
  printf '%s\n' "$pid"
  xgw_checksum /etc/xgw/xray/config.json
}
if exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run vpn-lock flock -n 9 && run vpn-before xgw_readonly_vpn &&
   PORT=$(xgw_http_port) && run https-before xgw_https_control &&
   run settings-before xgw_checksum /etc/xgw/config.toml /etc/xgw/panel.json; then
  VIDEO=8plwv25NYRo
  if timeout -k 2 65 yt-dlp --ignore-config --proxy "http://127.0.0.1:$PORT" --no-playlist \
      --socket-timeout 10 --retries 1 --extractor-retries 1 \
      -f 'bv[height=720][protocol=https]' --dump-single-json \
      "https://www.youtube.com/watch?v=$VIDEO" >"$D/format.json" 2>"$D/resolve.err"; then
    for label in profile-1 profile-2; do
      if [[ $label == profile-2 ]]; then sleep 20; fi
      run "$label-off" xgw_readonly_vpn || break
      run "$label-before" xgw_identity || break
      run "$label" xgw_python -m docs.helpers.selective_vpn_range "$D/format.json" \
        --proxy-port "$PORT" --profile
      if run "$label-after" xgw_identity; then
        run "$label-same-xray" cmp -s "$D/$label-before.out" "$D/$label-after.out"
      fi
    done
  else
    echo VPN_PROFILE_RESOLVE_BLOCKED
  fi
  run vpn-after xgw_readonly_vpn
  run https-after xgw_https_control
  if run settings-after xgw_checksum /etc/xgw/config.toml /etc/xgw/panel.json; then
    run settings-unchanged cmp -s "$D/settings-before.out" "$D/settings-after.out"
  fi
else
  echo VPN_PROFILE_BLOCKED
fi
exec 9>&-
```

Один запрос ограничен 24 МиБ и 135 секундами, весь замер — 48 МиБ.
Скорость считается по полным пятисекундным интервалам после первых
байт ответа. Нулевые интервалы внутри измерения учитываются. Опубликуй
оба профиля, включая `http`, `bytes`, `curl_rc`, `content_range_ok`,
TTFB, время тела, байты каждого полного интервала и запас к битрейту,
если он рассчитан.

- `profiled` означает, что есть первая полная корзина и ещё минимум
  три полных интервала. Сравни первый интервал и медиану последних
  трёх. Если HTTP 206 с нужным диапазоном достиг дедлайна, укажи
  `curl_rc=28` и сколько успело доставиться.
- `short` означает, что корректный ответ закончился слишком быстро для
  оценки поздней скорости. Для `partial` запиши наблюдавшийся блокер.
  HTTP 302 не измеряет скорость тела, поле Location в отчёт не включай.
- Отметь, совпало ли состояние Xray на границах каждого замера.
  Прокси и URL зафиксированы, CDN IP и выбор VPN-сервера за прокси
  отдельным измерением не подтверждаются. Исторические 200 КБ/с
  относятся к темпу чтения mpv в других окнах.

## 3. Публикация

Опубликуй один обезличенный отчёт при любом исходе по §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) с суффиксом
`_selective-vpn-profile.md` в `integration/zapret2-batch1`.
Укажи SHA инструмента, тесты, `VPN_PROFILE`, режим и HTTPS до/после,
контроль SHA настроек и два результата. Приватные URL, IP, PID,
хэши файлов и данные панели хранятся на ThinkCentre.
Проверь наличие коммита в удалённой ветке и верни ссылку.
