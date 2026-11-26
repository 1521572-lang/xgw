# ThinkCentre · восстановление выхода FreePool R39

Ubuntu 24.04 LTS. Кандидат `64a7ee5c4c8d89d466557fa5e5e1f53ca9d5360a`. Проверить нарастающую паузу
перед повторной проверкой ранее пригодного выхода. В прогонах
используются только синтетический каталог, локальный HTTP-сервер и
отдельный непривилегированный Xray установленной версии.
[Отчёт по публичному IPv4](https://github.com/1521572-lang/xgw/blob/3aa800b7f24bba8518e8c9e9e16a6ca398d54ca6/docs/reports/2026-11-26T182128Z_freepool-r39-public-wan.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-recovery.bundle)

Flash выполняет команды сама. При недоступном терминале запросить
доступ. Отдельный Xray обращается только к loopback-источнику.
Шлюз, реальный каталог и назначения клиентов для прогона не меняются.

## Прогон

От обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. При необходимости указать
пути через `XGW_TEST_PYTHON` и `XGW_TEST_XRAY`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=64a7ee5c4c8d89d466557fa5e5e1f53ca9d5360a
D=$(mktemp -d /tmp/xgw-r39-recovery.XXXXXXXX)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-recovery.bundle >"$D/code.bundle"
printf '%s  %s\n' '34f1b064f7cd2e75f6c76ed8bddad4375e54f9d93b08e30c513f790e56487c3f' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
if [[ -x "$XRAY" ]]; then
  export XGW_TEST_FREEPOOL_XRAY="$XRAY"
else
  unset XGW_TEST_FREEPOOL_XRAY
fi
cd "$D/tree"
status=0
if timeout -k 5 160 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_targeted.py tests/test_freepool_traffic.py tests/test_freepool.py \
    tests/test_freepool_cancel.py tests/test_freepool_candidates.py \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_RECOVERY_CONTRACTS=PASS\n'
else
  printf 'R39_RECOVERY_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if [[ -x "$XRAY" ]]; then
  if timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1; then
    head -n 1 "$D/xray-version.txt"
  else
    printf 'R39_RECOVERY_XRAY_VERSION=FAIL\n'
    status=1
  fi
  if timeout -k 5 45 "$PY" -B -P - "$D" "$XRAY" >"$D/loopback.log" 2>&1 <<'PYTHON'
import http.server
import sys
import threading
from pathlib import Path

from xgw.config import Config
from xgw.freepool import pool, traffic
from xgw.freepool.models import Backend, ProviderResult, Status, Variant
from xgw.paths import Paths

root, xray = map(Path, sys.argv[1:])
paths = Paths(root=root / "control")
cfg = Config()
cfg.capture.mark_bypass = 0
cfg.free_pool.mode = "observe"
cfg.free_pool.providers = ["vpnbook"]
cfg.free_pool.checks_per_step = 1
failed = threading.Event()
failed.set()
seen = []


class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        seen.append(self.path)
        body = b"loc=DE\n" if self.path == "/trace" else b"fixture" * 512
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body[:29] if failed.is_set() and self.path == "/probe" else body)

    def log_message(self, *_args):
        pass


with http.server.HTTPServer(("127.0.0.1", 0), Origin) as origin:
    base = f"http://127.0.0.1:{origin.server_address[1]}"
    cfg.probe.url, cfg.probe.trace_url = base + "/probe", base + "/trace"
    server = threading.Thread(target=origin.serve_forever, daemon=True)
    server.start()
    try:
        clock = [1_800_000_000.0]
        variant = Variant(
            provider="vpnbook", backend=Backend.XRAY, protocol="fixture", host="",
            address="198.51.100.10", port=443, transport="tcp", name="fixture",
            country_hint="DE", outbound={"protocol": "freedom"},
        )
        key = variant.variant_id
        worker = pool.FreePool(cfg, paths, clock=lambda: clock[0])
        worker.refresh_backend = lambda: "fixture"
        worker.store.commit(ProviderResult("vpnbook", Status.SUCCESS, [variant], clock[0]))
        worker.store.save_candidates({key: {
            "checked_at": clock[0] - pool.CHECK_EVERY - 1, "verdict": "OK", "egress_country": "DE",
        }})
        assert worker.check_some(mark=None, xray_bin=xray) == 1
        first = worker.store.candidates()[key]
        assert first["stage"] == "download" and first["probe_kind"] in pool.RECOVERY_KINDS
        due = first["recovery"]["until"]
        assert first["recovery"]["failures"] == 1 and 48 <= due - clock[0] <= 72
        assert traffic.admitted(cfg, paths, clock[0]) == []
        assert seen == ["/probe"]

        worker = pool.FreePool(cfg, paths, clock=lambda: clock[0])
        worker.refresh_backend = lambda: "fixture"
        worker.store.queue_test(key)
        clock[0] = due - 1
        assert worker.check_some(mark=None, xray_bin=xray) == 0 and seen == ["/probe"]
        assert worker.store.test_request() == key
        clock[0] = due
        failed.clear()
        assert worker.check_some(mark=None, xray_bin=xray) == 1
        final = worker.store.candidates()[key]
        assert final["verdict"] in ("OK", "SLOW") and "recovery" not in final
        assert [item.variant.variant_id for item in traffic.admitted(cfg, paths, clock[0])] == [key]
        assert seen == ["/probe", "/probe", "/trace"] and worker.store.test_request() is None
    finally:
        origin.shutdown()
        server.join()
print("R39_RECOVERY_XRAY=PASS")
PYTHON
  then
    cat "$D/loopback.log"
  else
    printf 'R39_RECOVERY_XRAY=FAIL\n'
    status=1
  fi
else
  printf 'R39_RECOVERY_XRAY=NOT_RUN\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_RECOVERY_HOST_FIELDS_MATCH\n'
else
  printf 'R39_RECOVERY_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `R39_RECOVERY=PASS` требует зелёных контрактов, результата
  `R39_RECOVERY_XRAY=PASS` и совпавших полей рабочих служб.
  При доступном Xray контракты также выполняют проверку отмены
  через ядро. При недоступности ядра указать `NOT_RUN`.
- Контракты проверяют базовые интервалы 1, 2, 4, 8, 16, 32 и 60
  минут, верхнюю границу, паузу действующего участника, сохранение
  записи после отмены, учёт байтов и невозможность обойти ожидание
  через ручную очередь. У неизвестного кандидата и при HTTP-ошибке
  прежнее расписание. Указывать фактические статусы.
- В loopback получить временный сбой при чтении тела через Xray,
  затем успешно повторить запрос после наступления срока по
  подменённым часам. Проверить возврат общего допуска по свежей
  проверке страны и отсутствие выхода до неё.
- Рабочий трафик, подбор состава с реальным сервером, влияние
  истечения учётных данных и сутки M3 в этом проходе открыты.
  При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-recovery.md` обычным push в
  `docs/flash-proton-ui-manifest`. Указать SHA кандидата и ТЗ,
  ОС и версию ядра. При расхождении ветки перенести только отчёт.
  Конфиги, PID и полные журналы остаются локально.
  Системный код Flash не меняет.
