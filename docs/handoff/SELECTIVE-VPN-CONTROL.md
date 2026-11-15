# Selective — результат служебной VPN-пробы после возврата на VPN

[Отчёт ThinkCentre от 16 ноября](../reports/2026-11-16_desync-t04-telemetry-compare.md)
подтвердил обычный Chrome с телеметрией YouTube через Standalone и четыре успешные пробы
Compare. Новый клиентский запрос после отказа Selective прошёл через VPN. Служебная проба
дважды наблюдалась как `not_run`, хотя `probe_failed` входит в условия её вызова.

В новой версии Selective сохраняет результат на протяжении ожидания повтора при закрытом
маршруте. Для попытки есть `vpn_control_at` и `vpn_control_reason`, включая причины пропуска.
Проверь это на Ubuntu **24.04 LTS**. Все команды, браузер и публикацию выполняет сама модель.
При отсутствии терминала, sudo или графической сессии запроси доступ. Видео 15+5 и Compare уже
приняты. Здесь достаточно проверить новое соединение браузера после отказа Selective.

## Подготовка и установка с возвратом

Начни с рабочего VPN, режима off/off и пустой очереди. Сверь ExecStart и путь установленного
пакета и Python с командами ниже. Работай из чистого checkout, закрепи полный SHA. Если
текущая установка отличается от базы, укажи расхождение и проверь его до изменения файлов.
Для pytest используй существующий dev-venv или установи dev-зависимости в отдельный venv.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=7fa7ffb
git merge-base --is-ancestor "$BASE" "$CODE"
git show "$CODE:src/xgw/zapret2.py" | grep -n 'def _fallback_vpn_control'
D=$(mktemp -d "$HOME/xgw-vpn-control.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
python3 -m pytest --portable tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_desync_standalone.py tests/test_desync_schema.py

PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/desync-vpn-control-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-vpn-control-$CODE"
FILES=(src/xgw/zapret2.py src/xgw/watch/zapret2_control.py)
UNIT=xgw-desync-vpn-control-rollback
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" "$HELPER" prepare --vpn-control --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" >"$D/config-before.sha256"
sudo install -m 0700 /dev/stdin "$BACKUP/restore.sh" <<'SH'
#!/bin/bash
set -euo pipefail
py=$1
helper=$2
backup=$3
panel=$4
mode=$5
exec 9>"$backup/restore.lock"
flock 9
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-vpn-control.XXXXXXXX")
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
if [ "$mode" = rollback ]; then
  "$py" "$helper" rollback --vpn-control --backup "$backup"
else
  systemctl start xgw.service
fi
if [ -e "$backup/network-test-started" ]; then
  timeout 180 /usr/local/bin/xgw apply --now
fi
SH
sudo systemd-run --unit="$UNIT" --on-active=25m /bin/bash "$BACKUP/restore.sh" \
  "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply --vpn-control --backup "$BACKUP"
sudo sha256sum -c "$D/config-before.sha256"
```

Проверь оба SHA установленного слоя по `new_sha` в манифесте, состояние служб и доступ
из штатного браузера. Перед изменением политики коснись маркера и перезаряди таймер:

```bash
sudo touch "$BACKUP/network-test-started"
sudo systemctl restart "$UNIT.timer"
sudo systemctl list-timers "$UNIT.timer"
```

## Сценарий Selective и критерии

В отдельной сессии запусти сбор до переключения политики. Для стандартной установки статус
лежит в `/run/xgw/status.json`. Сохраняй новые снимки с временем watchdog:

```bash
sudo "$PY" -u - /run/xgw/status.json <<'PY' | tee "$D/status.jsonl"
import json
from pathlib import Path
import sys
import time

path = Path(sys.argv[1])
last = None
for _ in range(600):
    try:
        snap = json.loads(path.read_text())
        stamp = snap.get("updated")
        if stamp is not None and stamp != last:
            selected = snap.get("zapret2", {})
            keys = ("state", "reason", "gate_closed", "vpn_control", "vpn_control_reason",
                    "vpn_control_at")
            print(json.dumps({"updated": stamp, **{key: selected.get(key) for key in keys}}))
            last = stamp
    except (OSError, ValueError):
        pass
    time.sleep(1)
PY
```

Предварительно проверь указанный GET через VPN с телом ≥16 KiB и без редиректа, а также свободу
очереди 201. При замене URL подставь его имя и используй ASCII с процентным кодированием.

```bash
URL='https://ru.wikipedia.org/wiki/%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F'
sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$URL" <<'PY'
from dataclasses import asdict
from pathlib import Path
import sys
from urllib.parse import urlsplit

from xgw import config, managed
from xgw.desync import schema

path, url = Path(sys.argv[1]), sys.argv[2]
current, _ = config.load(path)
policy = schema.migrate(asdict(current.zapret2))
policy["selected"].update(mode="selective", strategy="multisplit",
                          domains=["full:" + urlsplit(url).hostname], probe_urls=[url],
                          retry_seconds=300)
policy["runtime"]["queue_num"] = 201
policy["engine"]["engine"] = "off"
managed.set_desync(managed.path_for(path), policy)
actual, _ = config.load(path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
```

1. Если прямая проба проходит и виден `active/probes_ok`, заверши только MainPID
   `xgw-zapret2.service` через `systemctl kill --kill-whom=main --signal=SIGKILL`.
   Если раньше приходит `fallback/probe_failed`, используй этот исход для проверки статуса.
   Запиши код причины, закрытие gate, снятие клиентского правила и освобождение очереди.
2. Сними минимум три **разных** `updated` в одном окне ожидания, до новой попытки. При закрытом
   gate и снятом маршруте `vpn_control`, `vpn_control_reason` и `vpn_control_at` должны
   сохраняться. Подтверди новый клиентский запрос из браузера и фактический VPN-выход.
   В API панели сверь `zapret2.evidence` с сырым статусом. Поля доказательств должны исчезнуть
   при переходе в off или на другую политику.
3. Для служебной пробы **PASS** требует `vpn_control=pass`. При `fail/request_failed` запиши
   условия запроса. При `not_run` запиши точную причину и сверь конкретное условие: живой
   участник с loopback probe-входом по данным observatory, наличие учётных данных, бюджет
   или шаг очистки. Один повтор после исправления найденного условия достаточен.
   Сохранение статуса и прохождение служебной пробы отмечай отдельно. Не выводи пароли,
   URL с токенами, сырые конфиги или полный журнал в отчёт.

## Восстановление и отчёт

Вызови `restore.sh` штатно до истечения таймера. Аргумент `accept` оставляет две проверенные
замены, `rollback` возвращает базу. Используй `rollback`, если слой внёс регрессию
или результат установки нельзя проверить. При срабатывании таймера прекрати сетевую фазу
и сначала проверь фактическое состояние.

```bash
ACTION=accept  # задай rollback при регрессии
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$ACTION"
sudo sha256sum -c "$D/config-before.sha256"
# Проверь штатный VPN, off/off, API, службы, offload и пустую очередь.
sudo systemctl stop "$UNIT.timer"

cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/selective-vpn-control-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-selective-vpn-control.md"
# Сама создай REPORT с SHA кода, исходом каждого шага и оставленным состоянием.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: verify Selective VPN control on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Публикуй автоматически даже при частичном результате. При гонке сделай fetch/rebase и обычный
push. В итоговом сообщении укажи SHA отчёта и фактический режим шлюза.
