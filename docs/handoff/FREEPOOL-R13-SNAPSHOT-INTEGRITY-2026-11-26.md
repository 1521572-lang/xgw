# ThinkCentre · целостность кеша FreePool R13

Ubuntu 24.04 LTS, кандидат `4f1df2be693fcfa6795cfcb2ad3945d8bdd24ac0`. Один проход проверяет SHA-256 и три
архивных поколения, повреждение и восстановление после HTTP 429, запись
предыдущей версией, регрессию живого Xray и готовность M3.
[Сводный отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/8ffe3e785d656d547c1e5923d232663aabf273a0/docs/reports/2026-11-26T193656Z_freepool-m3-runtime.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r13-snapshot-integrity.bundle)

Flash выполняет команды обычным пользователем самостоятельно. При недоступном
терминале запросить доступ. Каждая запись относится к отдельному префиксу.
Сетевые сценарии используют loopback. Поля штатных служб считываются до и после.
При отдельном окружении pytest указать `XGW_TEST_PYTHON`. При нестандартном
пути установленного Xray указать `XGW_TEST_XRAY`.

## 1. Прогон из полного клона

Требуется база `9e4c025efb5404086ae601f3dc535a9e881521dd`. Старый писатель
берётся из `b7765fe` в отдельном дереве.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=4f1df2be693fcfa6795cfcb2ad3945d8bdd24ac0
D=$(mktemp -d /tmp/xgw-freepool-snapshot-integrity.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r13-snapshot-integrity.bundle >"$D/code.bundle"
printf '%s  %s\n' 'f58b7c4cfb6cc50dd077a8e1901e5c3d96ca669b8edd17f8dbae6f0e484a2d02' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree" "$D/previous"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml \
    docs/helpers/freepool_lifecycle.py | tar -x -C "$D/tree"
git -C "$REPO" archive b7765feb5dde58c96be1dae93b37ad8176b654f6 src | tar -x -C "$D/previous"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
status=0
host_read_ok=0
if host_fields >"$D/before.txt"; then
  host_read_ok=1
fi
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
export XGW_ROOT="$D/isolated"
cd "$D/tree"
core_ok=0
unset XGW_XRAY_BIN XGW_TEST_FREEPOOL_XRAY
if [[ -x "$XRAY" ]] && timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1; then
  core_ok=1
  head -n 1 "$D/xray-version.txt"
  export XGW_XRAY_BIN="$XRAY" XGW_TEST_FREEPOOL_XRAY="$XRAY"
fi

if timeout -k 5 240 "$TEST_PY" -B -m pytest -o addopts= -q -rs -p no:cacheprovider \
    tests/test_freepool.py tests/test_freepool_sources.py tests/test_freepool_refresh.py \
    tests/test_freepool_traffic.py tests/test_freepool_candidates.py \
    tests/test_freepool_selection.py tests/test_freepool_targeted.py tests/test_freepool_cancel.py \
    tests/test_freepool_backend.py tests/test_freepool_stats.py tests/test_api_integration.py \
    tests/test_config.py tests/test_fetch.py::test_parse_userinfo >"$D/contracts.log" 2>&1; then
  printf 'F13_CONTRACTS=PASS\n'
else
  printf 'F13_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 30 "$D/contracts.log"

if XGW_ROOT="$D/cache-fixture" timeout -k 5 40 /usr/bin/python3 -B -P - \
    >"$D/integrity.log" 2>&1 <<'PYTHON'
import contextlib
import http.server
import io
import json
import stat
import threading
import time
from unittest.mock import patch

from xgw import cli, config, fetch
from xgw.freepool import pool, providers, traffic
from xgw.freepool.models import Status
from xgw.freepool.probe import Outcome
from xgw.freepool.store import SNAPSHOT_SHA256
from xgw.paths import Paths, atomic_write_json

source = providers.MAHDIBLAND
clock = [int(time.time()) - 300]
expiry = clock[0] + 1800
paths = Paths.from_env()
paths.ensure()
paths.config_file.write_text(
    '[free_pool]\nmode = "observe"\nproviders = ["mahdibland"]\n', encoding="utf-8",
)
cfg, warnings = config.load(paths.config_file)
assert not warnings
status = [200]
slots = [10, 11]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = "".join(
            f"vless://f54e6dfd-33d8-4ed0-b546-07aef5327f2f@198.51.100.{slot}:443"
            f"?security=tls&type=tcp&sni=example.test#fixture-{slot}\n"
            for slot in slots
        ).encode()
        if status[0] != 200:
            body = b"retry later"
        self.send_response(status[0])
        if status[0] == 200 and len(slots) == 2:
            self.send_header("Subscription-Userinfo", f"expire={expiry}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def download(url, **kwargs):
    assert url == origin
    return fetch.fetch_url(url, **kwargs, allow_private=True, backoffs=())


def inspect_sources():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli.main(["pool", "sources", "--json"]) == 0
    return json.loads(output.getvalue())


with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
    origin = f"http://127.0.0.1:{server.server_port}/catalog"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with (
            patch.dict(providers.ORIGINS, {source: {"127.0.0.1"}}),
            patch.dict(providers.LIST_URLS, {source: (origin,)}),
        ):
            worker = pool.FreePool(cfg, paths, clock=lambda: clock[0], fetcher=download)
            for _ in range(4):
                clock[0] += 1
                [success] = worker.refresh_due(via=None, mark=None, force=True)
                assert success.status == Status.SUCCESS
            store = worker.store
            assert all(len(store.snapshot(source, i, strict=True)[SNAPSHOT_SHA256]) == 64
                       for i in range(4))
            assert all(stat.S_IMODE(store.snapshot_path(source, i).stat().st_mode) == 0o600
                       for i in range(4))
            target = next(item for item in worker.variants() if item.address.endswith(".10"))
            worker._record(target, Outcome("OK", 0.5, 500_000, "DE"))
            assert traffic.admitted(cfg, paths, clock[0])
            print("R13_SNAPSHOT_THREE_ARCHIVES=PASS")

            current = store.snapshot_path(source)
            tampered = store.snapshot(source)
            tampered["variants"][0]["credential_expires_at"] = 0
            atomic_write_json(current, tampered, mode=0o600)
            store.snapshot_path(source, 1).write_bytes(b"{broken")
            damaged = current.read_bytes()
            archives = [store.snapshot_path(source, i).read_bytes() for i in range(1, 4)]
            [row] = inspect_sources()["sources"]
            assert row["status"] == "CACHE_INVALID" and row["variants"] == 0
            assert not traffic.admitted(cfg, paths, clock[0], members={target.variant_id[:8]})
            status[0] = 429
            clock[0] += 1
            [failed] = worker.refresh_due(via=None, mark=None, force=True)
            assert failed.status == Status.RATE_LIMITED and current.read_bytes() == damaged
            print("R13_SNAPSHOT_CORRUPT_AND_429=PASS")

            status[0] = 200
            slots[:] = [10]
            clock[0] = worker.next_refresh[source] + 1
            [recovered] = worker.refresh_due(via=None, mark=None)
            assert recovered.status == Status.SUCCESS
            assert [store.snapshot_path(source, i).read_bytes() for i in range(1, 4)] == archives
            [target] = store.variants(source)
            assert target.credential_expires_at == expiry
            assert not traffic.admitted(cfg, paths, clock[0])
            worker._record(target, Outcome("OK", 0.5, 500_000, "DE"))
            assert traffic.admitted(cfg, paths, clock[0])
            [row] = inspect_sources()["sources"]
            assert row["status"] == "SUCCESS" and row["variants"] == 1
            print("R13_SNAPSHOT_RECOVERY_REQUIRES_FRESH_CHECK=PASS")
    finally:
        server.shutdown()
        thread.join(timeout=3)
PYTHON
then
  grep -E '^R13_SNAPSHOT_' "$D/integrity.log"
  if XGW_ROOT="$D/cache-fixture" PYTHONPATH="$D/previous/src" \
      timeout -k 2 10 /usr/bin/python3 -B -P - >"$D/previous.log" 2>&1 <<'PYTHON'
import time

from xgw.freepool.models import ProviderResult, Status
from xgw.freepool.store import PoolStore
from xgw.paths import Paths

store = PoolStore(Paths.from_env())
assert len(store.variants("mahdibland")) == 1
result = ProviderResult("mahdibland", Status.RATE_LIMITED, retrieved_at=time.time())
assert not store.commit(result)
PYTHON
  then
    if XGW_ROOT="$D/cache-fixture" timeout -k 2 10 /usr/bin/python3 -B -P - \
        >"$D/upgrade.log" 2>&1 <<'PYTHON'
from xgw.freepool.store import SNAPSHOT_SHA256, PoolStore
from xgw.paths import Paths

snapshot = PoolStore(Paths.from_env(), strict_reads=True).snapshot("mahdibland")
assert len(snapshot[SNAPSHOT_SHA256]) == 64
assert snapshot["status"] == "SUCCESS" and snapshot["last_attempt"]["status"] == "RATE_LIMITED"
assert len(snapshot["variants"]) == 1
PYTHON
    then
      printf 'R13_SNAPSHOT_PREVIOUS_WRITER=PASS\n'
    else
      printf 'R13_SNAPSHOT_PREVIOUS_WRITER=FAIL (upgrade)\n'
      status=1
    fi
  else
    printf 'R13_SNAPSHOT_PREVIOUS_WRITER=FAIL (previous writer)\n'
    status=1
  fi
else
  printf 'R13_SNAPSHOT_LOOPBACK=FAIL\n'
  printf 'R13_SNAPSHOT_PREVIOUS_WRITER=NOT_RUN\n'
  status=1
fi

for scenario in rotation certificate api-switch; do
  if [[ "$core_ok" != 1 ]]; then
    printf '%s=NOT_RUN (Xray unavailable)\n' "$scenario"
    continue
  fi
  if [[ "$scenario" == certificate ]] && ! command -v openssl >/dev/null; then
    printf '%s=NOT_RUN (OpenSSL unavailable)\n' "$scenario"
    continue
  fi
  if timeout -k 5 75 /usr/bin/python3 -B -P docs/helpers/freepool_lifecycle.py \
      "$scenario" --xray "$XRAY" --root "$D/$scenario" >"$D/$scenario.log" 2>&1; then
    printf '%s=PASS\n' "$scenario"
  else
    printf '%s=FAIL\n' "$scenario"
    status=1
  fi
  grep -E -e '^OBSERVED ' -e '^F13_' "$D/$scenario.log" || true
done

if [[ "$host_read_ok" == 1 ]] && host_fields >"$D/after.txt"; then
  if cmp -s "$D/before.txt" "$D/after.txt"; then
    printf 'F13_HOST_FIELDS_MATCH\n'
  else
    printf 'F13_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'F13_HOST_FIELDS_NOT_RUN\n'
fi

/usr/bin/python3 -I -B - <<'PYTHON'
import json
import time
from pathlib import Path

try:
    state = json.loads(Path("/run/xgw/status.json").read_bytes())
    fresh = 0 <= time.time() - float(state["updated"]) <= 180
    free_pool = state.get("free_pool") or {}
    flow = free_pool.get("traffic") or {}
    capture = state.get("capture") or {}
    mode = free_pool.get("mode")
    devices = len(flow["devices"]) if isinstance(flow.get("devices"), list) else 0
    alive = flow.get("alive") if type(flow.get("alive")) is int else 0
    whole = flow.get("all") is True
    ready = (fresh and capture.get("mode") == "on" and capture.get("loaded") is True
             and capture.get("blocked") is False and (whole or devices > 0)
             and alive > 0 and flow.get("closed") is False)
    print(json.dumps({"check": "M3_PREFLIGHT", "fresh": fresh, "ready": ready,
                      "mode": mode if mode in ("off", "observe", "on") else "unknown",
                      "devices": devices, "alive": alive, "whole": whole}))
except (OSError, ValueError, TypeError, AttributeError, KeyError):
    print("M3_PREFLIGHT=NOT_RUN (status unavailable)")
PYTHON
exit "$status"
BASH
```

## 2. Приёмка

| Блок | Критерий |
| --- | --- |
| Контракты | Записать число тестов и пропуски. Контрольная сумма стабильна при перестановке ключей и обновлении `last_attempt`. Покрыты старый снимок без суммы, несовпадение SHA-256 и невалидный JSON. |
| Повреждение и восстановление | Нужны `R13_SNAPSHOT_THREE_ARCHIVES`, `R13_SNAPSHOT_CORRUPT_AND_429` и `R13_SNAPSHOT_RECOVERY_REQUIRES_FRESH_CHECK`. Сверить три архива, права 0600, отсутствие допуска из повреждённого текущего файла и сохранение этого файла при 429. После HTTP 200 из архива берётся известный срок, а в каталог входит только опубликованная строка. Перед допуском требуется свежая проверка. Результат проверки выхода задан фикстурой. |
| Совместимость писателя | `R13_SNAPSHOT_PREVIOUS_WRITER=PASS`. Предыдущий код читает новый снимок и записывает попытку 429. Новый код после этого проверяет сумму и читает принятый каталог. |
| Регрессия Xray | Ротация ключа, отказ и восстановление TLS, переключение и откат API на установленном ядре. Записать отдельно судьбу удерживаемого соединения и совпадение полей штатных служб. |
| M3 | Записать свежесть статуса, готовность и числа из preflight. Для долгого дренирования, рабочих соединений и суток указать `NOT_RUN`. |

Если блок недоступен или завершился с ошибкой, выполнить остальные доступные.
Для `R13_SNAPSHOT_INTEGRITY=PASS` требуются контракты, три маркера loopback
и запись старым писателем. Результаты Xray, сравнения служб и M3 указать отдельно.

## 3. Публикация

Flash сама публикует один обезличенный
`docs/reports/<UTC>_freepool-r13-snapshot-integrity.md` обычным push в
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кандидата и ТЗ,
ОС, Python, версию ядра и результат каждого блока. Снимки, их суммы, PID
и полные журналы оставить локально. При изменении вершины перенести только отчёт.
Системный код Flash не редактирует.
