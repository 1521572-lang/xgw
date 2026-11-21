# ThinkCentre — локальный обзор zapret2 через IPC

**Ubuntu 24.04 LTS.** Flash сама выполняет проверку и публикует
обезличенный отчёт при любом исходе. Если недоступны терминал,
сессия панели или sudo, запроси доступ и продолжи сама. Код и
команды подготовил Codex. Для этого прогона допустимы только
временные файлы и сокет, локальные запросы и две контрольные
проверки HTTPS через штатный Xray. Установленный пакет, службы,
настройки, правила маршрутизации и политики zapret2 остаются в
исходном состоянии.

В r5 первый авторизованный ответ занял 1 249 мс вместо 16 843 мс
в r4. Страны появились у 66 из 66 строк. Одноразовый вход и откат
прошли. На шлюзе после отката работает исходный пакет.
[Отчёт r5](../reports/2026-11-21T135851Z_panel-login-installed-trial-r5.md)

Первый контракт P2.1 отдаёт пять полей карточки zapret2 отдельному
непривилегированному клиенту. Скрипт поднимает временный Unix-сокет
на root, читает реальный снимок XGW и запускает два процесса с
разными UID и одинаковым GID. Сверка с действующей HTTP-панелью
проводится в режиме off/off. Отказ бэкенда проверяется в памяти
тестового процесса.

## 1. Запуск

Выполни блок из checkout репозитория, как пользователь рабочей
сессии XGW. Подтверди sudo с помощью `sudo -v` в интерактивном
терминале. Если pytest находится в отдельном окружении, укажи в
`XGW_TEST_PYTHON` абсолютный путь к интерпретатору.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf '%s | %s\n' "$PRETTY_NAME" "$(uname -r)"
sudo -n true
BR=integration/zapret2-batch1
CODE=7c4e405a407b24569b621abfa250cdb2d36769f7
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-panel-read-ipc.XXXXXXXX")
SRC="$WORK/source"
TOOLS=
BASELINE=no
printf 'Private run: %s\n' "$WORK"

capture_state() {
  local dir="$WORK/$1" unit pid
  mkdir -- "$dir" || return
  for unit in xgw.service xgw-xray.service; do
    systemctl is-active --quiet "$unit" || return
    pid=$(systemctl show "$unit" --property=MainPID --value) || return
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done > "$dir/pids" || return
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json \
    /var/lib/xgw/panel-token > "$dir/settings" || return
  timeout -k 2 15 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json, sys
view = json.load(sys.stdin)
keys = ("mode", "engine_mode", "state", "fresh", "policy_matched")
safe = {key: view.get(key) for key in keys}
assert safe == dict(zip(keys, ("off", "off", "off", True, True)))
print(json.dumps(safe, sort_keys=True))' > "$dir/status" || return
}

https_control() {
  local port code
  port=$(sudo -n "$PY" -I -B -c 'import json
with open("/etc/xgw/xray/config.json") as stream:
    inbounds = json.load(stream)["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)') || return
  code=$(curl -q -fsS --max-time 10 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" --output /dev/null --write-out '%{http_code}' \
    https://example.org/) || return
  [[ $code == 200 ]] || return 2
  printf 'HTTPS 200\n'
}

finish() {
  local rc=$?
  if [[ -n $TOOLS ]]; then
    if [[ $TOOLS =~ ^/tmp/xgw-panel-ipc\.[A-Za-z0-9]{8}$ ]] &&
       sudo -n rm -r -- "$TOOLS" && sudo -n test ! -e "$TOOLS"; then
      printf 'TOOLS_REMOVED\n'
    else
      printf 'TOOLS_CLEANUP_FAILED\n' >&2
      rc=1
    fi
  fi
  if [[ $BASELINE == yes ]]; then
    if capture_state after &&
       cmp -s "$WORK/before/pids" "$WORK/after/pids" &&
       cmp -s "$WORK/before/settings" "$WORK/after/settings" &&
       cmp -s "$WORK/before/status" "$WORK/after/status" && https_control; then
      printf 'GATEWAY_UNCHANGED\n'
    else
      printf 'GATEWAY_CONTROL_FAILED\n' >&2
      rc=1
    fi
  fi
  if [[ -d $SRC ]] && ! git -C "$REPO" worktree remove "$SRC"; then
    printf 'SOURCE_CLEANUP_FAILED\n' >&2
    rc=1
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" worktree add --detach "$SRC" "$CODE"
printf 'PINNED %s\n' "$CODE"
capture_state before
https_control
BASELINE=yes
printf 'BASELINE_OK\n'

test_rc=0
(
  cd "$SRC"
  timeout -k 4 300 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
    -o addopts='' -p no:cacheprovider -q tests/test_panel_ipc.py \
    tests/test_desync_event_socket.py tests/test_panel.py tests/test_t11_panel_login_check.py
) | tee "$WORK/tests.out" || test_rc=$?
printf 'CONTRACT_TESTS_RC %s\n' "$test_rc"

TOOLS=$(sudo -n mktemp -d /tmp/xgw-panel-ipc.XXXXXXXX)
[[ $TOOLS =~ ^/tmp/xgw-panel-ipc\.[A-Za-z0-9]{8}$ ]]
git -C "$REPO" archive --format=tar "$CODE" src/xgw docs/helpers/panel_ipc_lab.py |
  sudo -n tar --no-same-owner --no-same-permissions -xf - -C "$TOOLS"
sudo -n chmod 0711 "$TOOLS"
sudo -n chmod -R a+rX -- "$TOOLS/src" "$TOOLS/docs"
sudo -n timeout -k 3 45 "$PY" -I -B "$TOOLS/docs/helpers/panel_ipc_lab.py" |
  tee "$WORK/ipc.out"
"$PY" -I - "$WORK/before/status" "$WORK/ipc.out" <<'PYTHON'
import json
import sys
from pathlib import Path

baseline = json.loads(Path(sys.argv[1]).read_text())
lines = Path(sys.argv[2]).read_text().splitlines()
payload, = [line.removeprefix("allowed ") for line in lines if line.startswith("allowed ")]
assert json.loads(payload) == baseline, "IPC_HTTP_STATUS_MISMATCH"
print("IPC_HTTP_STATUS_MATCH")
PYTHON
exit "$test_rc"
BASH
```

## 2. Критерии отчёта

| Этап | Что зафиксировать |
|---|---|
| `PINNED`, `BASELINE_OK` | SHA кандидата, Ubuntu и ядро, off/off и исходный HTTPS 200. При отклонении зафиксируй текущий режим и оставь его как есть. |
| `CONTRACT_TESTS_RC` | Число passed/failed/skipped и имена упавших проверок при наличии. |
| `socket_permissions`, `allowed`, `IPC_HTTP_STATUS_MATCH` | Режим сокета 0660, успешное чтение из непривилегированного процесса, совпадение пяти полей с HTTP. |
| `other_uid`, `server_uid` | Соединение второго UID из той же группы закрыто без ответа. Клиент с ошибочным ожиданием UID сервера отклонил соединение. |
| `version`, `operation`, `length` | Получены `unsupported_version`, `unsupported_operation`, `request_too_large`. `only_valid_request_reached_backend` подтверждает, что до бэкенда дошёл один корректный запрос. |
| `backend_down`, `socket_cleanup`, `TOOLS_REMOVED` | Получен `unavailable`, сокет и временные файлы root удалены. При аварии до завершения скрипта проверь, какой этап успел отработать, и запиши результаты очистки. |
| `GATEWAY_UNCHANGED` | Обе службы активны, оба PID и три контрольных файла совпали, off/off fresh/matched сохранён, HTTPS 200. |

При `GATEWAY_CONTROL_FAILED` прочитай доступные файлы контроля в
приватном каталоге. Запиши, какой показатель изменился, и повтори
только чтение статуса и служб один раз. Оставь восстановление
исходной установки за владельцем, если оно требует изменения
работающего шлюза. В отчёт включи имена и итог этапов, первый код
ошибки и сведения о финальном состоянии. Вывод из приватного
каталога, значения PID, хэши настроек, адреса, URL сессии и токены
остаются на машине.

## 3. Автоматическая публикация

Создай один обезличенный Markdown-отчёт. Укажи его абсолютный путь
в `REPORT_SRC` и сама выполни блок из checkout. При параллельном
обновлении ветки блок один раз переносит коммит поверх свежего HEAD.
Верни ссылку на проверенный коммит отчёта.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-ipc-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-read-ipc.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre panel read IPC acceptance'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
```
