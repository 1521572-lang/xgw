# ThinkCentre — область ALT9 и сохранность локальных исключений

**Ubuntu 24.04 LTS.** Flash сама выполняет проверку и публикует обезличенный
отчёт при любом исходе. Запроси доступ, если недоступны терминал, sudo или
GitHub. Используй закреплённую версию кода. Испытание сохраняет рабочий
шлюз в исходном режиме, а запись и запуск nfqws2 ограничены копией настроек
в сетевом пространстве с одним loopback.

В последнем CDN-проходе Xray подтвердил оба выхода. У прямого плеча есть
`ClientHello`, но нет `ServerHello` или входящего alert. Через VPN TLS
завершился в обеих попытках, HTTP `302` повторился. Возврат `blue/api`
и откат прошли. Допуск Selective остаётся открытым. Здесь проверяем
независимый блок T03/T06/T10. Предыдущая лаборатория показала, что рабочий
nfqws2 принимает пустой положительный файл и завершает процесс при ошибке
распаковки. Новый ALT9 получает положительный список и локальные исключения
в аргументах поколения из одной атомарно сохранённой политики.
[CDN-отчёт](../reports/2026-11-24T172518Z_standalone-cdn-tls.md) · [Отчёт списков](../reports/2026-11-22T231433Z_flowseal-list-reload.md)

## Запуск

В терминале ThinkCentre выполни `sudo -v`. Если pytest находится в venv,
экспортируй абсолютный путь `XGW_TEST_PYTHON`. Запусти блок из рабочей копии.
Если проверенные каталог ALT9, бинарник или Lua отсутствуют, зафиксируй
конкретную зависимость. Установка рабочих пакетов для этого этапа не нужна.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=caff6a5c4d41da6168292d17bfc8a14659669de1
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-policy.XXXXXXXX")
printf 'FLOWSEAL_POLICY_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"

state() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
  sudo -n /bin/bash -ec '
    file=/proc/net/netfilter/nfnetlink_queue
    if [[ -r $file ]]; then awk "{print \$1, \$2}" "$file" | sort; fi
  '
}

vpn() {
  local port status
  port=$(sudo -n "$PY" -I -B - <<'PY'
import json
from pathlib import Path

inbounds = json.loads(Path("/etc/xgw/xray/config.json").read_bytes())["inbounds"]
port, = [row["port"] for row in inbounds if row.get("tag") == "http-in"
         and row.get("listen") == "127.0.0.1" and row.get("protocol") == "http"]
assert type(port) is int and 0 < port < 65536
print(port)
PY
  ) || return
  status=$(curl -q -4fsS --max-time 12 --max-filesize 131072 --noproxy '' \
    --proxy "http://127.0.0.1:$port" -o /dev/null -w '%{http_code}' https://example.org/) || return
  printf '%s\n' "$status"
  [[ $status == 200 ]]
}

state >"$D/before.state"
vpn >"$D/before.https" || true
if timeout -k 2 8 /opt/xgw/zapret2/1.0.7/nfqws2 --version >"$D/engine.out" 2>&1; then
  head -n 1 "$D/engine.out"
fi
tests=0
timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
  PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest \
  --portable -o addopts= -p no:cacheprovider -q --tb=short \
  tests/test_desync_flowseal.py tests/test_desync_schema.py \
  tests/test_zapret2_management.py tests/test_desync_standalone.py \
  >"$D/contracts.out" 2>&1 || tests=$?
tail -n 6 "$D/contracts.out"
printf 'FLOWSEAL_POLICY_CONTRACTS_EXIT %s\n' "$tests"

LAB=$(sudo -n mktemp -d /run/xgw-flowseal-policy.XXXXXXXX)
sudo -n mkdir "$LAB/code"
git -C "$REPO" archive "$CODE" src docs/helpers/flowseal_policy_check.py |
  sudo -n tar --no-same-owner --no-same-permissions -x -C "$LAB/code"
HOST_NETNS=$(stat -Lc %i /proc/self/ns/net)
lab=0
sudo -n /usr/bin/timeout -k 3 100 /usr/bin/unshare --net /usr/bin/env \
  "PYTHONPATH=$LAB/code/src" "$PY" -B -P "$LAB/code/docs/helpers/flowseal_policy_check.py" \
  --out "$LAB" --host-netns "$HOST_NETNS" >"$D/lab.out" 2>"$D/lab.err" || lab=$?
cat "$D/lab.out"
printf 'FLOWSEAL_POLICY_LAB_EXIT %s\n' "$lab"

state >"$D/after.state"
vpn >"$D/after.https" || true
if cmp -s "$D/before.state" "$D/after.state"; then
  printf 'FLOWSEAL_POLICY_GATEWAY_UNCHANGED\n'
else
  printf 'FLOWSEAL_POLICY_GATEWAY_STATE_DIFFERED\n'
fi
if grep -Fxq 200 "$D/before.https" && grep -Fxq 200 "$D/after.https"; then
  printf 'FLOWSEAL_POLICY_HTTPS_200\n'
else
  printf 'FLOWSEAL_POLICY_HTTPS_NOT_VERIFIED\n'
fi
BASH
~~~

## Критерии

- Контракты проходят. Они содержат подмену сбоя перед `os.replace`,
  повтор записи и проверку, что прежняя ревизия и байты переживают отказ.
- `FLOWSEAL_POLICY_BASE_OK` фиксирует, что текущий установленный nfqws2
  принял исходную область. `FLOWSEAL_POLICY_NARROW_OK` фиксирует два
  положительных домена и два локальных исключения во всех блоках.
  Обе фазы проходят штатный `--dry-run` и `--intercept=0`. Помощник также
  сверяет ревизию запуска воркера с ревизией настроек.
- Запись при включённом режиме, устаревший ключ и имя вне области
  отклоняются. Исключение всей области блокирует переход в Standalone.
  Возврат исходных аргументов и ревизии даёт `FLOWSEAL_POLICY_ROLLBACK_OK`.
  Повторный импорт сохраняет выбранную область и пользовательский список.
- Укажи, совпали ли параметры маршрутизации, настройки, процессы и
  владельцы очередей до и после, и вернул ли контроль Xray `200` дважды.
  При естественном изменении состояния укажи только категорию изменения.
  Лаборатория проверяет политику и preflight установленного воркера.
  Рабочее переключение профиля и видео в этот проход не входят.

В отчёт включи SHA, версию ОС и движка, итоги фаз, точку отказа при наличии
и итоговое состояние. Сырые пути, адреса, PID, журналы и отпечатки настроек
остаются на ThinkCentre.

## Автоматическая публикация

Экспортируй абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок также при блокере или неполном результате. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-flowseal-policy-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_flowseal-policy-scope.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre ALT9 scope and local exclusions'
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
