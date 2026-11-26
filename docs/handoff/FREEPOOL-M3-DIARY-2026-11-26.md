# ThinkCentre · FreePool M3, суточный дневник

Ubuntu 24.04 LTS. Кандидат `15409237aaa1de4daef19e54605e9f184a09baf0`. Последнее окно M3 завершилось без
пользовательского трафика через пул. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/9e4c025efb5404086ae601f3dc535a9e881521dd/docs/reports/2026-11-19_combined-open-blocks.md)

Flash сама выполняет команды. Если нет терминала или разрешённого чтения
SQLite, запросить доступ. До суточного запуска установить, что пользователь
**уже** пользуется пулом на согласованном устройстве либо в обычном режиме
дома и согласен на пассивный сбор. Для отдельного устройства сверить
действующее назначение приватно в панели. Записать согласие и два времени
подтверждённой обычной активности, в начале и ближе к концу окна. В этом
задании используются существующие настройки и службы. При любом исходе
опубликовать обезличенный отчёт.

## 1. Кандидат и контракты

Выполнить из полного клона XGW с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Код извлекается в приватный
каталог. При необходимости заранее задать `XGW_TEST_PYTHON` с путём к Python, в
котором уже установлен pytest. [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-m3-diary.bundle)

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=15409237aaa1de4daef19e54605e9f184a09baf0
D=$(mktemp -d "$HOME/xgw-freepool-m3.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-m3-diary.bundle >"$D/code.bundle"
printf '%s  %s\n' 'cbe682c2ba339779f035b9c77aa89b6d23c8278fe99d4f0d40c6837b9f7014ac' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml docs/helpers/audit_host_observe.py |
  tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
(
  cd "$D/tree"
  PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider --portable tests/test_freepool_stats.py
) >"$D/contracts.log" 2>&1 || { tail -n 20 "$D/contracts.log"; exit 1; }
tail -n 4 "$D/contracts.log"

sudo -n timeout -k 2 15 /usr/bin/env -i "PYTHONPATH=$D/tree/src" \
  "$PY" -B -P -m xgw.cli pool stats --json --days 3 >"$D/preflight.json"
"$PY" -B - "$D/preflight.json" <<'PYTHON'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_bytes())
assert data["schema"] == 1 and len(data["days"]) == 3
assert all(type(row["pool_up"]) is int and type(row["pool_down"]) is int for row in data["days"])
print("M3_JSON_OK")
PYTHON
BASH
```

При ошибке чтения SQLite или контрактов остановить задание и записать
причину. Ошибка чтения оставляет наличие трафика неизвестным.

## 2. Готовность и наблюдение

Подставить путь `D` из §1. Значение `RUN=1` допускается после согласования
окна и подтверждения, что пользователь уже использует пул. С `RUN=0`
блок только читает состояние. При отсутствии пригодного маршрута или
согласованного использования записать `M3_TRAFFIC=NOT_RUN` и закончить без ожидания суток.
Задание использует приватный каталог с правами 0700.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
D='<PRIVATE_ARTIFACTS из §1>'
RUN=0
test -d "$D/tree/src/xgw"
PY=/usr/bin/python3
cat >"$D/observe.py" <<'PYTHON'
import json
import math
import subprocess
import sys
import time
from pathlib import Path


def routing():
    try:
        data = json.loads(Path("/run/xgw/status.json").read_bytes())
        if not 0 <= time.time() - float(data["updated"]) <= 180:
            return {"state": "status_stale"}
        pool = data.get("free_pool") or {}
        flow = pool.get("traffic") or {}
        mode = pool.get("mode")
        mode = mode if mode in ("off", "observe", "on") else "unknown"
        devices = len(flow["devices"]) if isinstance(flow.get("devices"), list) else 0
        whole = flow.get("all") is True
        alive = flow.get("alive")
        alive = alive if type(alive) is int and alive >= 0 else 0
        capture = data.get("capture") or {}
        ready = (capture.get("mode") == "on" and capture.get("loaded") is True
                 and capture.get("blocked") is False and (whole or devices > 0)
                 and alive > 0 and flow.get("closed") is False)
        return {"state": "ready" if ready else "not_ready", "mode": mode,
                "whole": whole, "devices": devices, "alive": alive}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return {"state": "status_unavailable"}


if sys.argv[1:] == ["preflight"]:
    state = routing()
    print(json.dumps(state))
    raise SystemExit(0 if state["state"] == "ready" else 3)

begin = time.monotonic()
while True:
    elapsed = time.monotonic() - begin
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-P", "-m", "xgw.cli", "pool", "stats", "--json", "--days", "3"],
            capture_output=True, check=True, timeout=10,
        )
        snapshot = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        snapshot = None
    print(json.dumps({"elapsed_s": round(elapsed, 3), "routing": routing(),
                      "snapshot": snapshot}), flush=True)
    if elapsed >= 86400:
        break
    next_sample = min(86400, (math.floor(elapsed / 900) + 1) * 900)
    time.sleep(max(0, begin + next_sample - time.monotonic()))
PYTHON

if ! "$PY" -I -B "$D/observe.py" preflight >"$D/routing-before.json"; then
  cat "$D/routing-before.json"
  printf 'M3_DAY_NOT_STARTED\n'
  exit 0
fi
cat "$D/routing-before.json"
if [[ $RUN != 1 ]]; then
  printf 'M3_DAY_NOT_STARTED\n'
  exit 0
fi
test ! -e "$D/day.jsonl"
sudo -n timeout -k 2 40 "$PY" -I -B - snapshot \
  <"$D/tree/docs/helpers/audit_host_observe.py" >"$D/gateway-before.json"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings-before.sha256"
touch "$D/day.jsonl" "$D/day.err"
unit="xgw-m3-observe-$(date +%s)"
sudo -n systemd-run --unit="$unit" --collect \
  --property=RuntimeMaxSec=25h --property=UMask=0077 \
  --property=ProtectSystem=strict --property=ProtectHome=read-only \
  --property=PrivateNetwork=yes --property=NoNewPrivileges=yes \
  --property="StandardOutput=append:$D/day.jsonl" \
  --property="StandardError=append:$D/day.err" \
  /usr/bin/env -i "PYTHONPATH=$D/tree/src" "$PY" -B -P "$D/observe.py"
printf '%s\n' "$unit" >"$D/unit"
printf 'M3_DAY_STARTED %s\n' "$unit"
BASH
```

Flash ведёт наблюдение сама. Проверять `systemctl show "$(cat "$D/unit")" -p ActiveState -p SubState` и `wc -l "$D/day.jsonl"`. Юнит читает один
снимок за 15 минут и завершается по достижении 24 ч. Если владелец просит
прекратить наблюдение, остановить только этот юнит. При укороченном окне
указать фактическую длительность. Если получено `M3_DAY_NOT_STARTED`, закончить отчёт
после короткой проверки.

## 3. Итог и публикация

После завершения юнита выполнить следующий блок. Дельты считаются отдельно
по локальным датам. Снимки и параметры шлюза остаются в приватном каталоге.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
D='<PRIVATE_ARTIFACTS из §1>'
test -s "$D/day.jsonl"
sudo -n timeout -k 2 40 /usr/bin/python3 -I -B - snapshot \
  <"$D/tree/docs/helpers/audit_host_observe.py" >"$D/gateway-after.json"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings-after.sha256"
if cmp -s "$D/settings-before.sha256" "$D/settings-after.sha256"; then
  printf 'M3_SETTINGS_MATCH\n'
else
  printf 'M3_SETTINGS_DIFFER\n'
fi
/usr/bin/python3 -I -B - "$D" <<'PYTHON'
import json
import sys
from collections import Counter
from pathlib import Path

run = Path(sys.argv[1])
rows = [json.loads(line) for line in (run / "day.jsonl").read_text().splitlines()]
samples = [row for row in rows if row["snapshot"] is not None]
gaps = [after["elapsed_s"] - before["elapsed_s"] for before, after in zip(rows, rows[1:])]
before_gw = json.loads((run / "gateway-before.json").read_bytes())
after_gw = json.loads((run / "gateway-after.json").read_bytes())
print(json.dumps({"elapsed_s": rows[-1]["elapsed_s"], "samples": len(rows),
                  "missing": len(rows) - len(samples), "max_gap_s": max(gaps, default=0),
                  "gateway_snapshot_match": before_gw == after_gw,
                  "routing_states": dict(Counter(row["routing"]["state"] for row in rows))}))
if len(samples) < 2:
    raise SystemExit(0)
before = samples[0]["snapshot"]
after = samples[-1]["snapshot"]
first_day = before["days"][-1]["day"]
after_days = {row["day"]: row for row in after["days"]}
if first_day not in after_days:
    print("M3_DIARY_DAYS_UNALIGNED")
    raise SystemExit(0)
before_days = {row["day"]: row for row in before["days"]}
delta = Counter()
for day in sorted(key for key in after_days if key >= first_day):
    old, new = before_days.get(day, {}), after_days[day]
    for key in (old.keys() | new.keys()) - {"day"}:
        change = new.get(key, 0) - old.get(key, 0)
        if change < 0:
            print("M3_DIARY_COUNTER_DECREASED")
            raise SystemExit(0)
        delta[key] += change
if delta["speed_dt"]:
    delta["average_lead_mbps"] = round(delta["speed_s"] / delta["speed_dt"], 2)
print(json.dumps({key: round(value, 2) for key, value in sorted(delta.items())}))
PYTHON
BASH
```

- `M3_JSON=PASS` после контрактов и чтения реальной базы.
- `M3_TRAFFIC=PASS` только при подтверждённой обычной активности в уже настроенном
  пуле и приросте байтов между снимками, охватывающими эти интервалы.
  Сопоставить UTC-время активности с `observed_at_unix` и состоянием
  `ready` в этих снимках. `active_s` включает ожидание
  и closed. Счётчики выходов включают служебные проверки и замеры.
  При наличии только таких счётчиков записать `M3_TRAFFIC=NOT_RUN`.
- `M3_DAY=PASS` при 86 400 с, разрывах ≤960 с, успешном чтении всех снимков,
  свежем статусе на каждом отсчёте, пригодном дневнике и `M3_TRAFFIC=PASS`.
  Указать секунды назначения и closed,
  смены по причинам, среднюю скорость и up/down. Естественное закрытие
  допустимо, если зафиксировано восстановление. Иной исход сопроводить
  фактическим покрытием и причиной.
- Записать итог сверки состояния и отметить изменения, если их выполнял
  владелец. Отказ, просроченные учётные данные, миграция, откат, R39 и
  полный R50 остаются отдельными проверками. Для R32/R35 нужны данные
  о качестве.

Создать ровно один `docs/reports/<UTC>_freepool-m3-diary.md` в ветке `docs/flash-proton-ui-manifest` и опубликовать обычным push
при любом исходе. Указать SHA кандидата и ТЗ, ОС, контракты, исходы, фактическую
длительность и достаточность доказательств. Адреса, теги выходов, имена устройств
и содержимое базы, конфигов и журналов оставить локально. При конфликте ветки
перенести только свой новый отчёт поверх её текущей вершины.
