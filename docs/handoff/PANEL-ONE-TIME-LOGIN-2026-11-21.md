# ThinkCentre — вход в панель XGW по одноразовой ссылке

**Ubuntu 24.04 LTS.** Flash сама запускает команды и проверяет
интерфейс браузером с vision. При недоступном терминале, браузере
или sudo запроси доступ. После проверки сама опубликуй один
обезличенный отчёт при любом исходе.

Приняты контракты nftables и Tailscale. Кандидат T11 меняет выдачу
ссылок в CLI и установщике. Старая закладка очищает адрес переходом
на `/`. Действующая cookie продолжает открывать панель, чистый
профиль получает инструкцию для входа.
[Отчёт nftables](../reports/2026-11-21T115710Z_nft-rules-gate.md)

## 1. Подготовка и контракты

Запусти блок в Bash из текущего checkout обычным пользователем.
При необходимости укажи абсолютный `XGW_TEST_PYTHON` для pytest.
Запиши ОС, ядро, браузер и версию PyQt6. Приватный каталог
напечатает первая команда. Используй его как `RUN_DIR` в следующих
блоках, в том числе при новом вызове терминала.

```bash
bash <<'BASH'
set -uo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
BR=integration/zapret2-batch1
CODE=f6ebbb021d5132daf0b86bee46d69a3efc99d1b3
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-panel-login.XXXXXXXX") || exit 2
SRC="$D/source"
printf 'RUN_DIR=%s\n' "$D"
git -C "$REPO" fetch origin "$BR" &&
  git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
  git -C "$REPO" worktree add --detach "$SRC" "$CODE" || exit 2

cat >"$D/control.sh" <<'CONTROL'
set -euo pipefail
systemctl is-active --quiet xgw.service
systemctl is-active --quiet xgw-xray.service
timeout -k 2 12 env PYTHONPATH=/opt/xgw/lib /usr/bin/python3 -B -P -m xgw.desync.client status |
  /usr/bin/python3 -I -c 'import json, sys
view = json.load(sys.stdin)
assert view["fresh"] and view["policy_matched"]
assert view["mode"] == view["engine_mode"] == view["state"] == "off"
print("off/off fresh matched")'
timeout -k 2 12 sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
CONTROL

run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}
tests() (
  cd "$SRC" || exit 2
  [[ $TEST_PY == /* && -x $TEST_PY ]] || exit 2
  timeout -k 4 240 env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -B -P -m pytest \
    -q -o addopts='' -p no:cacheprovider "$@"
)

run control-before bash "$D/control.sh"
run cli-install tests tests/test_ops.py tests/test_install.py -k 'panel or gui_login'
run auth tests tests/test_panel.py tests/test_tailscale_t2.py tests/test_gui_model.py
run clients tests tests/test_notify_page.py tests/test_tray.py tests/test_appapi.py
run rules tests tests/test_nft.py tests/test_zapret2.py \
  tests/test_tailscale.py tests/test_tailscale_t2.py
BASH
```

Контроль использует установленный CLI статуса. Если проверка SHA
отказала из-за sudo, подтверди права интерактивным `sudo -v`
и выполни `bash "$RUN_DIR/control.sh" >"$RUN_DIR/control-before.out"`
перед браузерной фазой. При ошибке запиши имя блока и первую
обезличенную диагностику. Локальный стенд запускается отдельно от
установленной службы, с временной базой, тестовым токеном и случайным
портом на 127.0.0.1.

## 2. Запуск отдельной панели

Укажи полученный абсолютный `RUN_DIR` и выполни блок.

```bash
bash -s -- "$RUN_DIR" <<'BASH'
set -euo pipefail
umask 077
D=$1
SRC="$D/source"
mkdir "$D/firefox"
timeout -k 4 600 env "PYTHONPATH=$SRC/src:$SRC/tests:$SRC" \
  /usr/bin/python3 -B -P - "$D" >"$D/lab.out" 2>"$D/lab.err" <<'PY' &
import sys
import time
from pathlib import Path

from panel_demo import build
from xgw.watch.panel import ensure_token

directory = Path(sys.argv[1])
demo = build(directory / "root", 8781, "empty")
demo.token = ensure_token(demo.paths)
demo.app_port = None
demo.port = 0
demo.start()
try:
    demo.paths.config_file.write_text(f"[panel]\nport = {demo.port}\n", encoding="ascii")
    (directory / "port").write_text(str(demo.port), encoding="ascii")
    while not (directory / "stop-demo").exists():
        time.sleep(0.3)
finally:
    demo.stop()
PY
for trial in {1..20}; do
  if [[ -s "$D/port" ]]; then
    printf 'LAB_READY\n'
    exit 0
  fi
  sleep 0.5
done
exit 2
BASH
```

- Открой старую закладку в пустом профиле, например командой
  `firefox --no-remote --profile "$RUN_DIR/firefox" "http://127.0.0.1:$(cat "$RUN_DIR/port")/?token=retired-bookmark"`.
  Если Firefox недоступен, используй отдельный пустой профиль
  установленного браузера. Cookie завязана на хост, общий профиль
  с рабочей панелью перезапишет её даже на другом порту.
- В этом профиле по vision проверь чистый адрес и страницу входа:
  видны `sudo xgw panel` и подсказка про минуту. Поле для постоянного
  токена отсутствует. Сними только обезличенный экран при необходимости.
- Выполни следующую команду сама. Она выдаёт ссылку для отдельной
  панели обычной командой CLI с тестовым корнем. Открой её в том же
  профиле до истечения минуты и дождись главной страницы. Обнови
  страницу, затем ещё раз открой старую закладку и проверь, что
  действующая сессия открывает главную страницу по чистому адресу.

```bash
env "XGW_ROOT=$RUN_DIR/root" "PYTHONPATH=$RUN_DIR/source/src" \
  /usr/bin/python3 -B -P -m xgw panel
```

## 3. Qt, отказ повторного входа и конечный контроль

Пока стенд работает, запусти следующий блок. Он использует штатный
метод Qt обмена кода на cookie и возвращает только коды проверок.
Контрактные тесты §1 отдельно проверяют просроченный код, Host,
Origin, POST без сессии, pkexec, ветку Tailscale Secure-cookie и
вход на страницу LAN-статуса. Добавь к результату старую закладку
в чистом профиле и с активной сессией из §2.

```bash
bash -s -- "$RUN_DIR" <<'BASH'
set -uo pipefail
umask 077
D=$1
timeout -k 2 20 env "PYTHONPATH=$D/source/src" /usr/bin/python3 -B -P - "$D" <<'PY'
import http.client
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QTimer

from xgw.gui.client import ApiClient
from xgw.paths import Paths
from xgw.watch.panel import new_login

d = Path(sys.argv[1])
port = int((d / "port").read_text())
code = new_login(Paths(d / "root"))
app = QCoreApplication([])
client = ApiClient(None)


def finished(session, message):
    if session is None:
        app.exit(2)
        return
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("GET", f"/?login={code}")
        response = conn.getresponse()
        valid = response.status == 403 and response.getheader("Set-Cookie") is None
        response.read()
    finally:
        conn.close()
    app.exit(0 if valid and session.port == port else 2)


QTimer.singleShot(0, lambda: client.exchange(port, code, finished))
QTimer.singleShot(7000, lambda: app.exit(2))
rc = app.exec()
client.close()
sys.exit(rc)
PY
printf 'qt-exchange\t%s\n' "$?" | tee -a "$D/steps.tsv"
touch "$D/stop-demo"
bash "$D/control.sh" >"$D/control-after.out" 2>"$D/control-after.err"
control_rc=$?
printf 'control-after\t%s\n' "$control_rc" | tee -a "$D/steps.tsv"
if [[ $control_rc == 0 && -s "$D/control-before.out" ]]; then
  cmp -s "$D/control-before.out" "$D/control-after.out"
  printf 'control-unchanged\t%s\n' "$?" | tee -a "$D/steps.tsv"
fi
BASH
```

Закрой тестовый профиль. По завершении удали рабочее дерево
`git worktree remove "$RUN_DIR/source"` из основного checkout
и оставь обезличенные коды этапов. Лабораторная панель имеет
предельное время 600 с. При истечении этого окна зафиксируй
результаты успевших проверок.

## 4. Отчёт и публикация

Укажи SHA, ОС, результаты четырёх групп pytest, начальный и конечный
контроль. Отдельные исходы — браузер, CLI, Qt, старый bookmark,
HEAD, истечение, повторное использование, отказ Host/Origin и
действующая сессия. Пометь блокер для непройденного шага. Сценарии
кандидата относятся к отдельной панели. Установленный шлюз проверяется
контрольными GET и сравнением хэшей перед завершением.

Для приёмки нужны код 0 у всех групп, открытие главной страницы после
одноразовой ссылки, чистый адрес после старой закладки в обеих
сессиях и код 0 у Qt. Отметь root-зависимые пропуски отдельной строкой.

Сохрани один обезличенный отчёт при любом исходе. Исключи ссылки
входа, cookie, токены, хэши настроек и исходный вывод. Укажи абсолютный
путь в `REPORT_SRC` и сама выполни блок публикации из checkout XGW.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-login-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-one-time-login.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "Report ThinkCentre one-time panel login acceptance"
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
