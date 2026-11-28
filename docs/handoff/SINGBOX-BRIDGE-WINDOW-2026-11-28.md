# ThinkCentre · рабочее окно моста Xray и sing-box

Ubuntu 24.04 LTS amd64. Кандидат `396a4d4ecadc5e88fda8bd9c4648fac773f1c91b`. На ThinkCentre через прямой вход green получен HTTP 200 и 57 620 байт, прошли 122 контракта, рабочие юниты и файлы совпали. В Xray по-прежнему нет рабочего моста. Следующий критерий — провести HTTPS через Xray и текущий sing-box, затем повторить через следующий слот и дождаться окончания дренирования. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/0e1e58f132b8773a34364c717a223c5a6b194285/docs/reports/2026-11-28T050257Z_singbox-bridge-https.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. При недоступности терминала или sudo запросить доступ. Начать с этапа A. Этап B требует явно согласованного с владельцем окна на временное закрепление ядра за одним участником, одну смену поколения и возврат настройки. При отсутствии окна отправить отчёт со статусом `WINDOW=NOT_RUN` и результатами A.

## A. Контракты, API и исходный HTTPS

Выполнить из полного клона XGW. `XGW_TEST_XRAY` при необходимости задаёт путь к уже установленному Xray. Использовать установленную версию и записать её в отчёт. Стенд API открывает отдельные порты loopback и завершает свои процессы. `PRIVATE_ARTIFACTS` указывает на закрытый каталог. HTTPS к настроенному адресу пробы проходит через существующий вход sing-box.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=396a4d4ecadc5e88fda8bd9c4648fac773f1c91b
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-window.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '00ab8a7dd64b154e79cb2bbd7fbe8ed5e04665b95c0e4a5356a6972ff21488d8' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"

run() {
    local label=$1 rc=0
    shift
    "$@" >"$D/$label.log" 2>&1 || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/status"
}

host_fields() {
    local unit fields
    for unit in xgw.service xgw-xray.service xgw-singbox.service \
                xgw-singbox-blue.service xgw-singbox-green.service; do
        fields=$(timeout -k 1 4 systemctl show "$unit" -p LoadState -p ActiveState -p MainPID) ||
            [[ "$fields" == *'LoadState=not-found'* ]] || return 1
        [[ "$fields" == *'LoadState='* && "$fields" == *'ActiveState='* && "$fields" == *'MainPID='* ]] ||
            return 1
        printf '%s\n%s\n' "$unit" "$fields"
    done
}

run CONTRACTS timeout -k 5 240 env "TMPDIR=$D/tmp" "PYTHONPATH=$PWD:$PWD/src:$PWD/tests" \
    "XGW_ROOT=$D/test-root" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_singbox_generations.py tests/test_dualcore.py
if [[ -x $XRAY ]]; then
    XRAY=$(readlink -f "$XRAY")
    run API_REAL timeout -k 5 120 env "TMPDIR=$D/tmp" "PYTHONPATH=$PWD:$PWD/src:$PWD/tests" \
        "XGW_ROOT=$D/test-root" "XGW_XRAY_BIN=$XRAY" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
        "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --color=no -q -rs -rfE --tb=short --show-capture=no \
        tests/test_api_integration.py -k socks_bridge_matches
else
    echo 'API_REAL=NOT_RUN installed Xray is unavailable' | tee -a "$D/status"
fi
tail -n 14 "$D/CONTRACTS.log"

host_files() {
    sudo -n /usr/bin/timeout -k 2 12 /usr/bin/python3 -I -B - <<'PY'
from hashlib import sha256
from pathlib import Path

for name in (
    "/etc/xgw/config.toml",
    "/etc/xgw/panel.json",
    "/etc/xgw/xray/config.json",
    "/etc/xgw/sing-box/config.json",
    "/etc/xgw/sing-box/generation-blue.json",
    "/etc/xgw/sing-box/generation-green.json",
    "/run/xgw/singbox-generations.json",
    "/var/lib/xgw/inventory.json",
):
    try:
        print(sha256(Path(name).read_bytes()).hexdigest())
    except FileNotFoundError:
        print("absent")
PY
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
if sudo -n true 2>/dev/null; then
    files_before=0
    host_files >"$D/files.before" 2>"$D/files.before.err" || files_before=$?
    run PREVIEW sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw singbox preview
    if [[ $before == 0 && $files_before == 0 ]] && grep -qx "CONTRACTS=0" "$D/status"; then
        run HTTPS sudo -n /usr/bin/timeout -k 2 105 /usr/bin/env -i \
            PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
            /usr/bin/python3 -B -P -m xgw singbox probe-bridge
    else
        echo 'HTTPS=NOT_RUN cannot verify initial host state' | tee -a "$D/status"
    fi
    run PREVIEW_AFTER sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw singbox preview
    files_after=0
    host_files >"$D/files.after" 2>"$D/files.after.err" || files_after=$?
    if [[ $files_before == 0 && $files_after == 0 ]]; then
        if cmp -s "$D/files.before" "$D/files.after"; then echo HOST_FILES=MATCH; else echo HOST_FILES=DRIFT; fi
    else
        echo HOST_FILES=UNKNOWN
    fi
else
    echo 'HTTPS=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo 'PREVIEW=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo HOST_FILES=UNKNOWN
fi

after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

## B. Подключение, смена и восстановление

Начинать после успешных A и с одобрением владельцем всей последовательности, включая остановку старого слота штатным дренированием. Согласовать время с запасом под 300 секунд дренирования и возврат. Задать `XGW_LIVE_UNTIL` как UTC-конец этого окна и `XGW_PRIVATE_ARTIFACTS` как путь из A. Терминал остаётся подключённым до завершения отката. По завершении теста настройка ядра возвращается в `auto`, успешно переключённый слот продолжает работать. Восстановление выполняется и при ошибке. При неполном возврате сообщить владельцу и сохранить диагностику.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
D=$XGW_PRIVATE_ARTIFACTS
[[ $D == /* && -d $D/tree && -O $D && -f $D/status ]]
for phase in CONTRACTS API_REAL HTTPS; do grep -qx "$phase=0" "$D/status"; done
grep -q '1 passed' "$D/API_REAL.log"
until=$(date -u -d "$XGW_LIVE_UNTIL" +%s)
(( until - $(date -u +%s) >= 900 ))
cd "$D/tree"

root() {
    local limit=$1
    shift
    sudo -n /usr/bin/timeout -k 2 "$limit" /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P "$@"
}
xgw() {
    local limit=$1
    shift
    root "$limit" -m xgw "$@"
}
save() {
    local label=$1 rc=0
    shift
    "$@" >"$D/$label.log" 2>"$D/$label.err" || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/window.status"
    return "$rc"
}
field() {
    /usr/bin/python3 -I -B -c 'import json,sys
data = json.load(open(sys.argv[1]))
value = data[sys.argv[2]]
print(json.dumps(value) if type(value) is not str else value)' "$1" "$2"
}
services() {
    timeout -k 2 8 systemctl show -p LoadState -p ActiveState -p MainPID -p InvocationID \
        xgw.service xgw-xray.service
}
boundary() {
    services >"$D/services.current" || return 1
    cmp -s "$D/services.before" "$D/services.current"
}
report_policy() {
    root 40 -m xgw status --json | /usr/bin/python3 -I -B -c 'import json,sys
x = json.load(sys.stdin)
print(json.dumps({key: x.get(key) for key in ("pin", "capture")}, sort_keys=True))'
}

cat >"$D/window-input.py" <<'PY'
import hashlib
import json
import sys
from urllib.parse import urlsplit

from xgw import config, engine, managed
from xgw.apply import singbox_process as processes
from xgw.generator import singbox as sb
from xgw.paths import Paths

paths = Paths.from_env()
cfg, warnings = config.load(paths.config_file)
panel, error = managed.load(managed.path_for(paths.config_file))
assert not error
xray = engine.read_json(paths.xray_config_file)
current = engine.read_json(paths.singbox_config_file)
assert xray and current
state = processes.read(paths)
active = state["active"]
assert active in processes.SLOTS and not state["pending"]
assert not paths.api_dirty_file.exists() and not paths.pending_config_file.exists()
if sys.argv[1] == "state":
    print(json.dumps({"bridges": len(processes.xray_ports(xray)),
                      "draining": bool(state["draining"]), "active": active,
                      "config": hashlib.sha256(paths.config_file.read_bytes()).hexdigest(),
                      "panel": panel}, sort_keys=True))
else:
    candidates = engine.singbox_direct_candidates(cfg, paths, xray, current)
    assert candidates and len(candidates) == 1
    fp = candidates[0]
    assert cfg.core.mode == "auto" and cfg.zapret2.mode != "standalone"
    expected_pin = "sing-box" if sys.argv[1] == "linked" else "auto"
    assert cfg.managed.core.get(fp, "auto") == expected_pin
    assert cfg.fragment.mode != "always" or (fp, "f") not in sb.bridge_ports(current)
    url = urlsplit(cfg.probe.url)
    assert url.scheme == "https" and url.hostname and url.username is None
    if sys.argv[1] == "linked":
        assert fp == sys.argv[2]
    else:
        assert not state["draining"] and not processes.xray_ports(xray)
        assert 1024 <= cfg.xray.http_port < 65536
        print(json.dumps({"target": fp, "active": active, "url": cfg.probe.url,
                          "http_port": cfg.xray.http_port}))
PY

root 15 "$D/window-input.py" original >"$D/target.private" 2>"$D/target.err"
target=$(field "$D/target.private" target)
[[ $target =~ ^[a-f0-9]{8,32}$ ]]
old=$(field "$D/target.private" active)
new=blue
if [[ $old == blue ]]; then new=green; fi
url=$(field "$D/target.private" url)
http_port=$(field "$D/target.private" http_port)

vpn() {
    local response code bytes
    response=$(curl -q -fsS --noproxy '' --connect-timeout 5 --max-time 16 --max-filesize 131072 \
        --proxy "http://127.0.0.1:$http_port" -o /dev/null -w '%{http_code} %{size_download}' \
        -- "$url") || return 1
    read -r code bytes <<<"$response"
    [[ $code =~ ^2[0-9][0-9]$ && $bytes =~ ^[0-9]+$ && $bytes -gt 0 ]] || return 1
    printf 'HTTP %s, %s bytes\n' "$code" "$bytes"
}
root 15 "$D/window-input.py" state >"$D/state.before" 2>"$D/state.before.err"
services >"$D/services.before"
[[ $(grep -cx 'ActiveState=active' "$D/services.before") == 2 ]]
report_policy >"$D/policy.before"
save VPN_BEFORE vpn

restore() {
    local initial_rc=$1 rc=0 wait_until
    trap - EXIT HUP INT TERM
    set +e
    save CORE_RESTORE xgw 30 core "$target" auto
    [[ $? == 0 ]] || rc=1
    wait_until=$(( SECONDS + 120 ))
    while ! root 15 "$D/window-input.py" state >"$D/state.after" 2>"$D/state.after.err" ||
          [[ $(field "$D/state.after" bridges) != 0 ]]; do
        if (( SECONDS >= wait_until )); then rc=1; break; fi
        sleep 5
    done
    /usr/bin/python3 -I -B - "$D/state.before" "$D/state.after" <<'PY' || rc=1
import json
import sys
with open(sys.argv[1]) as f, open(sys.argv[2]) as g:
    before, after = json.load(f), json.load(g)
assert before["panel"] == after["panel"] and before["config"] == after["config"]
PY
    boundary || rc=1
    report_policy >"$D/policy.after" && cmp -s "$D/policy.before" "$D/policy.after" || rc=1
    save VPN_AFTER vpn || rc=1
    printf 'RESTORE=%s\n' "$rc" | tee -a "$D/window.status"
    if (( initial_rc != 0 )); then exit "$initial_rc"; fi
    exit "$rc"
}
trap 'restore "$?"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

save CORE_ATTACH xgw 30 core "$target" sing-box
stamp=$(( SECONDS + 100 ))
until xgw 24 singbox preview >"$D/ready.log" 2>"$D/ready.err" &&
      [[ $(field "$D/ready.log" ready) == true ]]; do
    boundary
    (( SECONDS < stamp ))
    sleep 5
done
[[ $(field "$D/ready.log" active) == "$old" && $(field "$D/ready.log" candidate) == "$new" ]]
boundary
root 15 "$D/window-input.py" linked "$target" 2>"$D/linked.err"
save XRAY_BEFORE xgw 105 singbox probe-bridge --via-xray
save VPN_ATTACHED vpn
(( until - $(date -u +%s) >= 540 ))
save ROTATE xgw 150 singbox rotate
boundary
save DRAIN_START xgw 24 singbox status
[[ $(field "$D/DRAIN_START.log" active) == "$new" &&
   $(field "$D/DRAIN_START.log" draining) == "$old" &&
   $(field "$D/DRAIN_START.log" identity_ok) == true ]]
drain_left=$(field "$D/DRAIN_START.log" drain_left_s)
[[ $drain_left =~ ^[0-9]+$ && $drain_left -gt 0 && $drain_left -le 300 ]]
drain_deadline=$(( SECONDS + drain_left ))
root 15 "$D/window-input.py" linked "$target" 2>"$D/linked-after.err"
save XRAY_AFTER xgw 105 singbox probe-bridge --via-xray
save VPN_ROTATED vpn

stamp=$(( SECONDS + 385 ))
while :; do
    boundary
    xgw 24 singbox status >"$D/drain.current" 2>"$D/drain.err"
    printf 'UTC %s\n' "$(date -u +%FT%TZ)" >>"$D/drain.samples"
    cat "$D/drain.current" >>"$D/drain.samples"
    [[ $(field "$D/drain.current" active) == "$new" &&
       $(field "$D/drain.current" identity_ok) == true ]]
    drained=$(field "$D/drain.current" draining)
    if [[ $drained == null ]]; then break; fi
    [[ $drained == "$old" ]]
    (( SECONDS < stamp ))
    sleep 10
done
(( SECONDS + 2 >= drain_deadline ))
timeout -k 2 8 systemctl show "xgw-singbox-$old.service" \
    -p LoadState -p MainPID -p ActiveState >"$D/old-unit" || [[ -s $D/old-unit ]]
grep -qx 'MainPID=0' "$D/old-unit"
grep -qxE 'ActiveState=(inactive|failed)' "$D/old-unit"
printf 'DRAIN=0\n' | tee -a "$D/window.status"
BASH
~~~

В пределах согласованного окна и при доступе к отдельному физическому LAN-клиенту проверить обычный HTTPS на нём до теста и после возврата по фазе HTTPS из действующего ТЗ LAN. Результат указать отдельной меткой. Атрибуция пробы Xray из `--via-xray` относится к loopback ThinkCentre. [ТЗ физического LAN](https://github.com/1521572-lang/xgw/blob/0e1e58f132b8773a34364c717a223c5a6b194285/docs/handoff/T12-LAN-HTTPS-R2-2026-11-26.md)

## Итоги для отчёта

- `CONTRACTS` и `API_REAL`. Число прошедших и первый сбой. На установленном Xray подтвердить форму ответа `lso` с SOCKS-портом и учётной записью через контракт.
- `HTTPS`. Прямой контроль A. Записать код, статус и байты. Ожидаемый штатный ответ — HTTP 200 и 57 620 байт.
- `WINDOW`, `CORE_ATTACH`, `XRAY_BEFORE`, `ROTATE`, `XRAY_AFTER`. Указать исходы фаз и причину отказа. Для каждой пробы через Xray — HTTPS-статус, размер и прирост downlink, без тегов или параметров маршрута. Фаза PASS требует возврата тела HTTP 2xx, совпавшего SOCKS-обработчика из живого API и прироста downlink не меньше тела. Если первая такая проба не прошла, восстановление запускается до попытки ротации.
- `DRAIN`. Сравнить длительность и конечный статус, исходный и новый слоты и факт остановки старого. Жизненный цикл юнитов и ответы через новый слот подтверждаются отдельно от удержания старого TCP-потока. Удержание старого потока в рабочем окружении отметить `NOT_RUN`.
- `RESTORE` и `VPN_BEFORE` / `VPN_AFTER`. Указать исход возврата исходного core pin, совпадение панели, настроек, перехвата, pin и запусков Xray и демона. Старое поколение после штатного drain отражать отдельным полем. При сбое возврата опубликовать фактическое состояние и сообщить владельцу.

## Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest, Xray и sing-box, UTC, исходы фаз и факт согласования окна. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-bridge-window.md
  export GIT_INDEX_FILE="$pub/index"
  blob=$(git -C "$repo" hash-object -w -- "$REPORT_SRC")
  local_ref=refs/xgw-report/$(basename "$pub")
  trap 'git -C "$repo" update-ref -d "$local_ref"' EXIT
  for i in 1 2 3; do
    git -C "$repo" fetch --quiet --no-tags --no-write-fetch-head origin "$ref:$local_ref"
    tip=$(git -C "$repo" rev-parse "$local_ref")
    if prev=$(git -C "$repo" rev-parse --verify "$tip:$file" 2>/dev/null); then
      [[ $prev == "$blob" ]] || exit 1
      printf 'PUBLISHED %s %s\n' "$tip" "$file"
      exit 0
    fi
    git -C "$repo" read-tree "$tip"
    git -C "$repo" update-index --add --cacheinfo "100644,$blob,$file"
    tree=$(git -C "$repo" write-tree)
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre Xray bridge maintenance window')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
