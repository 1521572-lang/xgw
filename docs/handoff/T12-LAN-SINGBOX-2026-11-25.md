# ThinkCentre · HTTPS через мост под штатным UID sing-box, r3

**Ubuntu 24.04 LTS.** Flash сама выполняет готовые команды и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
sudo, pytest, установленного ядра или GitHub запроси доступ. Остальные
фазы выполни независимо. Код и тесты подготовлены Codex.

[Отчёт r2](../reports/2026-11-25T001317Z_t12-lan-singbox-r2.md) подтвердил
порт 443 и маршрут клиента до моста. На стенде собственный UDP туннеля
снова попал в `tproxy-in`. Стендовая служба запускала sing-box от root,
а штатный выход из перехвата применяется к UID `xgw-singbox`. Для r3
тест запускает временный процесс моста от штатного UID и GID, без
capabilities и с `NoNewPrivileges`. Приёмка проверяет оба HTTPS-сеанса,
серверный dial и отсутствие повторного захвата UDP. Правила действующего
шлюза в этом проходе не меняются.

## Запуск

Начни из обычной рабочей копии. При необходимости задай интерпретатор
с pytest через `XGW_TEST_PYTHON` и пройди `sudo -v`. Если ядра уже
установлены в нестандартных местах, укажи абсолютные пути через
`XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`. Для сценария моста также нужны
`setpriv`, `ss` и установленные учётная запись и группа `xgw-singbox`.
При отсутствии зависимости укажи пропуск и выполни остальные фазы.
Стенд использует
изолированные процессы и короткий `--basetemp` в своём `/run`.
Каталог `kernel-private` открывается для стенда внутри его mount namespace,
поэтому диагностические файлы сохраняются при выходе из пространства.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=c814b1589d0e392c331d8ca1de0d044e83d38f40
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY_BIN=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SB_BIN=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-lan-singbox.XXXXXXXX")
mkdir "$D/tree" "$D/kernel-private"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui packaging pyproject.toml \
  | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests:$D/tree/tests/stand"
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
  tail -n 18 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

kernel() {
  local name
  for name in ip nft unshare curl openssl; do
    command -v "$name" >/dev/null || { printf 'STAND_DEPENDENCY_MISSING %s\n' "$name"; return 3; }
  done
  [[ $XRAY_BIN == /* && -x $XRAY_BIN ]] || { printf 'STAND_XRAY_UNAVAILABLE\n'; return 3; }
  if [[ $SB_BIN == /* && -x $SB_BIN ]]; then
    "$SB_BIN" version | head -n 1 || true
  else
    printf 'STAND_SINGBOX_UNAVAILABLE\n'
    SB_BIN=''
  fi
  "$XRAY_BIN" version | head -n 1 || true
  nft --version || true
  sudo -n timeout -k 5 180 unshare --mount --propagation private --pid --fork \
    --kill-child --mount-proc /bin/sh -c '
      mount -t tmpfs -o nosuid,nodev,mode=0755 tmpfs /run || exit 3
      mkdir /run/lan-artifacts || exit 3
      mount --bind "$1" /run/lan-artifacts || exit 3
      shift
      exec "$@"
    ' sh "$D/kernel-private" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$PYTHONPATH" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    XGW_XRAY_BIN="$XRAY_BIN" XGW_SINGBOX_BIN="$SB_BIN" \
    "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider --color=no -v -rs -s --tb=short \
    --basetemp /run/lan-artifacts/p \
    tests/stand/test_stand_lan.py::test_lan_https_attributes_real_tproxy_socket
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 120 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short --portable \
  --basetemp "$D/pytest" tests/test_desync_vpn_control.py tests/test_desync_lan_control.py \
  tests/test_desync_route_evidence.py || true
run_phase PREVIEW sudo -n timeout -k 2 15 /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  "PYTHONPATH=$D/tree/src" "$PY" -B -P -m xgw.desync.vpn_control || true
run_phase KERNEL kernel || true
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T12_GATEWAY_UNCHANGED\n'
  else
    printf 'T12_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T12_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Итоги фаз

- **CONTRACTS** — результаты по числу прошедших, пропущенных и упавших
  проверок и времени. `applied_members` показывает число участников из
  применённой конфигурации. `no_applied_member` означает отсутствие
  участника данного ядра, `no_pinned_probe` — участник есть, однозначного
  локального пробного входа нет. Чтение сохраняет только агрегаты.
- **PREVIEW** — состояние штатного входа и обоих ядер. Если в рабочей
  конфигурации нет моста, зафиксируй причину и число участников.
  `available` означает подходящую конфигурацию, доступность внешней сети
  подтверждается отдельным запросом. PREVIEW таких запросов не делает.
- **KERNEL** — результаты `[xray]` и `[sing-box]`. В обоих ожидаются
  HTTP 200 с проверкой сертификата, точный сокет в `tproxy-in`, порт 443
  и соответствующая категория выхода. Для sing-box укажи `BRIDGE_IDENTITY`, `BRIDGE_OUTPUT_RULE`,
  `bridge_udp_recaptured`, `pinned_bridge`, `bridge_lan`, `bridge_pinned`.
  Ожидается ноль повторно захваченных UDP-сеансов и HTTPS через
  закреплённый вход. Серверный dial сверить по `trace_443` или сохранённой
  записи подтверждённого запроса. `health_8080` указывает на фоновый адрес.
  При сбое зафиксируй первый неподтверждённый этап и приложи только метки
  и агрегаты. При отсутствии признака оставь этап открытым.
- **Шлюз** — снимки до и после и категории отличий. Живой проход LAN
  остаётся открытым до получения доступа к отдельному устройству.
  Живая проверка sing-box ждёт рабочего участника через мост.
  [ТЗ LAN](T12-LAN-HTTPS-2026-11-25.md)

## Автоматическая публикация

Сырые журналы, настройки, адреса, теги, ключи и пути оставь на машине.
Подставь абсолютный путь к обезличенному Markdown в `REPORT_SRC`,
выполни блок из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-lan-singbox-r3-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-lan-singbox-r3.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre LAN bridge under the sing-box service identity'
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
