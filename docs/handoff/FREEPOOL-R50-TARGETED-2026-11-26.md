# ThinkCentre · целевая проверка кандидата FreePool R50

Ubuntu 24.04 LTS. Кандидат `f81960a451cfee33500fa6c20358407290b17b79`. Приёмка опроса выбранного источника
завершена. Этот проход проверяет команду `xgw pool test <variant-id> --bounded`, одной заявкой через
обычное расписание, очередь и лимиты FreePool. [Отчёт опроса](https://github.com/1521572-lang/xgw/blob/944da543c46948f9d08442a0ecb457825549cc80/docs/reports/2026-11-26T151941Z_freepool-r50-source-refresh.md)

Flash сама выполняет команды. При недоступности терминала или чтения
полей рабочего шлюза запросить доступ. Для команд используется отдельный
`XGW_ROOT`, с кандидатом из фикстуры и подменённым результатом пробы.
Штатные службы и маршруты работают в прежнем режиме. Идентификатор
варианта в отчёт не включать. [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-targeted.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest установлен
в отдельном окружении, задать путь через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=f81960a451cfee33500fa6c20358407290b17b79
D=$(mktemp -d "$HOME/xgw-freepool-targeted.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
unset XGW_TEST_FREEPOOL_XRAY
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-targeted.bundle >"$D/code.bundle"
printf '%s  %s\n' 'e1cf76c04dbd8d4f9cf34862e191411c7d7f5f541952056f8ef9fff51fd8bb94' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
host_fields >"$D/before.txt"
status=0
timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider --portable \
  tests/test_freepool_background.py tests/test_freepool_candidates.py \
  tests/test_freepool_sources.py tests/test_freepool_stats.py \
  >"$D/portable.log" 2>&1 || status=1
tail -n 20 "$D/portable.log"
timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
  tests/test_freepool_targeted.py tests/test_freepool_traffic.py tests/test_freepool_backend.py \
  tests/test_freepool_refresh.py tests/test_freepool_cancel.py \
  tests/test_panel.py::test_free_pool_card_switches_observation \
  >"$D/scheduler.log" 2>&1 || status=1
tail -n 20 "$D/scheduler.log"

isolated() (
  local root="$D/control" id
  export XGW_ROOT="$root"
  install -d "$root/etc/xgw" "$root/run/xgw" || return
  printf '[free_pool]\nmode = "observe"\nproviders = ["vpnbook"]\nchecks_per_step = 1\n' \
    >"$root/etc/xgw/config.toml" || return
  printf '{"updated":%s,"free_pool":{"mode":"observe"}}\n' "$(date +%s)" \
    >"$root/run/xgw/status.json" || return
  cat >"$D/fixture.py" <<'PYTHON' || return
import sys
import time
from unittest.mock import patch

from xgw import config
from xgw.freepool.models import Backend, ProviderResult, Status, Variant
from xgw.freepool.pool import FreePool
from xgw.freepool.probe import Outcome
from xgw.freepool.store import PoolStore
from xgw.paths import Paths

paths = Paths.from_env()
store = PoolStore(paths)
if sys.argv[1] == "seed":
    variant = Variant(provider="vpnbook", backend=Backend.XRAY, protocol="fixture",
                      host="", address="198.51.100.10", port=443, transport="tcp",
                      name="fixture", country_hint="DE")
    assert store.commit(ProviderResult("vpnbook", Status.SUCCESS, [variant], time.time()))
    print(variant.variant_id)
else:
    variant_id = sys.argv[2]
    cfg, _ = config.load(paths.config_file)
    worker = FreePool(cfg, paths)
    with patch.object(worker, "refresh_backend", return_value="fixture"), patch.object(
        worker, "_check_proxy", return_value=Outcome("TIMEOUT", stage="download", probe_phase="tls")
    ) as mock:
        assert worker.check_some(mark=None, xray_bin=None) == 1
    assert mock.call_count == 1 and store.test_request() is None
    record = store.candidates()[variant_id]
    assert (record["verdict"], record["probe_phase"]) == ("TIMEOUT", "tls")
    print("R50_TARGET_FIXTURE_RESULT_OK")
PYTHON
  id=$("$PY" -B -P "$D/fixture.py" seed) || return
  "$PY" -B -P -m xgw.cli pool test "$id" --bounded &&
    "$PY" -B -P -m xgw.cli pool test "$id" --bounded &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/pending.json" || return
  [[ $(stat -c %a "$root/var/lib/xgw/freepool/test-request.json") == 600 ]] || return 1
  "$PY" -B -P "$D/fixture.py" run "$id" &&
    "$PY" -B -P -m xgw.cli pool status --json >"$D/finished.json" || return
  "$PY" -I -B - "$D" <<'PYTHON'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
for name, expected in (("pending", True), ("finished", False)):
    data = json.loads((run / f"{name}.json").read_bytes())
    assert data["mode"] == "observe" and data["test_pending"] is expected
print("R50_TARGET_CLI_OK")
PYTHON
)
isolated >"$D/isolated.log" 2>&1 || status=1
tail -n 12 "$D/isolated.log"

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Итог

- `R50_TARGETED=PASS` требует прохода наборов, меток `R50_TARGET_CLI_OK` и `R50_TARGET_FIXTURE_RESULT_OK`,
  совпадения полей шлюза. Пропуск ранее принятого Xray loopback-кейса
  ожидается. Указать отдельно ожидание обычного срока и приоритет
  действующего участника, действие паузы, расход слота и учёт байтов
  при отмене, ограничение каталожного бюджета и квоту SSTP.
- `TIMEOUT` в фикстуре проверяет только сохранение результата и снятие
  заявки. Фазы рабочих таймаутов остаются отдельной приёмкой после
  согласованного обновления штатного демона.
- Опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-targeted.md` в ветке `docs/flash-proton-ui-manifest` обычным push
  при любом исходе. Указать SHA кандидата и задания, ОС, исходы и сверку.
  Идентификаторы, конфиги, исходные записи и журналы оставить локально.
  При конфликте перенести только отчёт поверх актуальной вершины.
