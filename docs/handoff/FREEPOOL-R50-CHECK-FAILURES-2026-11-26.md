# ThinkCentre · причины неудачных проверок FreePool R50

Ubuntu 24.04 LTS. Кандидат `72c69f26d038c88ab24b0d9381b80dcadf246207`. На старой ревизии из 641 бесплатного
варианта пригодны три. У 455 записей был общий отказ `check_failed`.
Сними разбивку по фактическим сохранённым вердиктам в текущем кеше.
[Отчёт допуска](https://github.com/1521572-lang/xgw/blob/b08910e23bbdec337dd50edbf15cb0d4ff442991/docs/reports/2026-11-26T115848Z_freepool-r50-candidates.md)

Flash выполняет команды сама. При недоступности терминала или необходимых
прав чтения запросить доступ. Использовать существующий кеш шлюза.
Блок проверяет новые записи на фикстуре в pytest, а старые — чтением рабочей
базы каталогов. Штатный демон в этом проходе остаётся на установленной версии.
[Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-check-failures.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest находится в отдельном
окружении, задать `XGW_TEST_PYTHON` с путём к его Python.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=72c69f26d038c88ab24b0d9381b80dcadf246207
D=$(mktemp -d "$HOME/xgw-freepool-failures.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-check-failures.bundle >"$D/code.bundle"
printf '%s  %s\n' '26fac07e2429e422cc26e2ced553361947b6dbbfefa4746cd44365026e445807' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
(
  cd "$D/tree"
  "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider --portable \
    tests/test_freepool_candidates.py tests/test_freepool_sources.py tests/test_freepool_stats.py
  "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool.py::test_probe_core_failure_is_told_without_secrets \
    tests/test_freepool_traffic.py::test_admitted_are_fresh_working_servers_of_the_region_with_an_address \
    tests/test_freepool_traffic.py::test_panel_rows_tell_why_a_pool_server_is_not_admitted \
    tests/test_freepool_traffic.py::test_pool_member_keeps_its_place_with_an_old_check \
    tests/test_target.py
) >"$D/contracts.log" 2>&1 || { tail -n 24 "$D/contracts.log"; exit 1; }
tail -n 8 "$D/contracts.log"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
candidate() {
  sudo -n timeout -k 2 15 /usr/bin/env -i "PYTHONPATH=$PYTHONPATH" "$PY" \
    -B -P -m xgw.cli pool candidates --explain "$@"
}
host_fields >"$D/before.txt"
code=0
candidate --json >"$D/report.json" 2>"$D/report.err" &&
  candidate >"$D/report.txt" 2>"$D/text.err" || code=$?
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
fi
if [[ $code != 0 ]]; then printf 'R50_CACHE_READ_FAILED %s\n' "$code"; exit "$code"; fi

"$PY" -I -B - "$D" <<'PYTHON'
import json
import sys
from collections import Counter
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads((path / "report.json").read_bytes())
assert (path / "report.txt").read_text().strip()
assert sum(data["by_reason"].values()) == data["found"]
assert data["by_reason"].get("eligible", 0) == data["eligible"]
verdicts = Counter()
backends = Counter()
sources = Counter()
stages = Counter()
stale = 0
for entry in data["failed_checks"]:
    assert set(entry) == {"source", "backend", "verdict", "stage", "phase", "kind",
                          "http_status", "stale", "count"}
    assert entry["source"] in {"vpngate", "vpnbook", "igareck", "mahdibland"}
    assert entry["backend"] in {"xray", "sing-box"}
    assert entry["verdict"] in {"UNTESTED", "FROZEN", "BODY_RESET", "STALL_BEFORE_BODY",
                                "CONNECT_FAIL", "TIMEOUT", "CANCELLED", "unknown"}
    assert entry["stage"] in {"endpoint_validation", "core_missing", "core_config",
                               "core_start", "download", "unknown"}
    assert entry["phase"] in {"connect", "tls", "request", "headers", "body", "unknown"}
    assert entry["kind"] in {"connect", "proxy", "tls", "http", "range", "stall", "truncated",
                              "timeout", "reset", "io", "cancelled", "unknown"}
    status = entry["http_status"]
    assert type(status) is int and (status == 0 or 100 <= status <= 599)
    count = entry["count"]
    assert type(count) is int and count > 0 and type(entry["stale"]) is bool
    verdicts[entry["verdict"]] += count
    backends[entry["backend"]] += count
    sources[entry["source"]] += count
    stages[entry["stage"]] += count
    if entry["stale"]:
        stale += count
assert sum(verdicts.values()) == data["by_reason"].get("check_failed", 0)
print(json.dumps({"found": data["found"], "eligible": data["eligible"], "mode": data["mode"],
                  "admission_reasons": data["by_reason"], "failure_verdicts": verdicts,
                  "failure_backends": backends, "failure_sources": sources,
                  "failure_stages": stages, "older_than_3h": stale}, sort_keys=True))
print("R50_CHECK_FAILURES_OK")
PYTHON
BASH
```

## Итог

- `R50_CHECK_FAILURES=PASS` при проходе контрактов, чтении рабочего кеша, выполнении
  инвариантов и совпавших снимках шлюза. Если записей `check_failed` нет,
  отдельно отметить `FAILURE_CACHE_EMPTY`. При ошибке чтения указать `CACHE_READ_FAILED`.
- Указать число пригодных на момент чтения, разбивку неудач по
  вердиктам, долю записей старше трёх часов и число записей без этапа.
  Изменение количества относительно предыдущего отчёта сопоставить
  с моментом снимка, поскольку каталоги обновляются в фоне.
- `unknown` корректен для старых записей. `UNTESTED` допускает отказ
  до сетевой пробы. `phase=connect` охватывает подключение к локальному прокси
  и согласование туннеля. `egress_unverified` означает, что страна выхода не
  подтверждена, а `outside_region` — что известная страна вне региона.
- При любом исходе опубликуй один обезличенный `docs/reports/<UTC>_freepool-r50-check-failures.md` в ветке `docs/flash-proton-ui-manifest`
  обычным push. Укажи SHA кандидата и ТЗ, ОС, контракты, агрегаты скрипта
  и итог сверки. Исходные кеши, журналы, URL, адреса и ключи оставить
  локально. При конфликте ветки перенеси только отчёт поверх её актуальной
  вершины.
