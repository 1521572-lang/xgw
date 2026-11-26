# ThinkCentre · срок каталога FreePool F13 / R13

Ubuntu 24.04 LTS. Кандидат `6625ffdd6a88376d39dc6a6eab4ccfc6d81dd8cf`. Проверить,
что через 24 часа после принятия последнего каталога XGW перестаёт добавлять
из него выходы. Профильные тесты проверяют сборку и политику сохранения участников.
Отдельный прогон проверяет загрузку каталога, кеш и CLI с настоящими ответами HTTP 200 и 429.
[Предыдущий отчёт R39](https://github.com/1521572-lang/xgw/blob/a7e16b824b8bafebd312f4ec3257fa8a1514ef96/docs/reports/2026-11-26T183215Z_freepool-r39-recovery.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-f13-catalog-lease.bundle)

Flash сама запускает команды из терминала. При недоступности терминала запросить доступ.
Команды выполняются обычным пользователем. Подменённые часы действуют только внутри прогона.
Временный каталог и сервер на loopback изолированы от рабочего XGW и внешних источников.
Состояние рабочих служб считывается до и после.

## Прогон

Из полного клона с коммитом `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Если pytest установлен в отдельном окружении, указать его интерпретатор через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=6625ffdd6a88376d39dc6a6eab4ccfc6d81dd8cf
D=$(mktemp -d /tmp/xgw-f13-lease.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-f13-catalog-lease.bundle >"$D/code.bundle"
printf '%s  %s\n' 'fc91d708dcf7a2bdaa616c642c2927d3f277a192407dc8de2561be05b7c5c820' "$D/code.bundle" | sha256sum --check -
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
cd "$D/tree"
status=0
if timeout -k 5 180 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py tests/test_freepool_candidates.py \
    tests/test_freepool_sources.py tests/test_freepool_selection.py \
    tests/test_freepool_targeted.py tests/test_freepool_refresh.py \
    tests/test_freepool_backend.py tests/test_freepool.py tests/test_config.py \
    >"$D/contracts.log" 2>&1; then
  printf 'F13_CONTRACTS=PASS\n'
else
  printf 'F13_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if XGW_ROOT="$D/fixture" timeout -k 5 30 /usr/bin/python3 -B -P - \
    >"$D/loopback.log" 2>&1 <<'PYTHON'
import contextlib
import http.server
import io
import json
import threading
from unittest.mock import patch

from xgw import cli, config, fetch
from xgw.freepool import pool, providers, traffic
from xgw.freepool.models import Status
from xgw.freepool.probe import Outcome
from xgw.freepool.store import SOURCE_LEASE
from xgw.paths import Paths

clock = [1_800_000_000.0]
source = providers.MAHDIBLAND
paths = Paths.from_env()
paths.ensure()
paths.config_file.write_text(
    '[free_pool]\nmode = "observe"\nproviders = ["mahdibland"]\n', encoding="utf-8",
)
cfg, warnings = config.load(paths.config_file)
assert not warnings
body = (
    'vless://f54e6dfd-33d8-4ed0-b546-07aef5327f2f@198.51.100.10:443'
    '?security=tls&type=tcp&sni=example.test#fixture\n'
).encode()
http_status = [200]
requests = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(http_status[0])
        payload = body if http_status[0] == 200 else b"retry later"
        self.send_response(http_status[0])
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def download(url, **kwargs):
    assert url == origin
    return fetch.fetch_url(url, **kwargs, allow_private=True, backoffs=())


def inspect(command):
    output = io.StringIO()
    with patch("xgw.cli.time.time", lambda: clock[0]), contextlib.redirect_stdout(output):
        assert cli.main(["pool", command, "--json"]) == 0
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
            [initial] = worker.refresh_due(via=None, mark=None)
            assert initial.status == Status.SUCCESS
            [variant] = worker.store.variants(source)
            good = Outcome("OK", 0.5, 500_000, "DE")
            clock[0] = initial.retrieved_at + SOURCE_LEASE - 1
            worker._record(variant, good)
            assert inspect("candidates")["eligible"] == 1

            http_status[0] = 429
            clock[0] += 1
            [failed] = worker.refresh_due(via=None, mark=None)
            assert failed.status == Status.RATE_LIMITED
            worker._record(variant, good)
            [listed] = inspect("sources")["sources"]
            assert listed["stale"] and listed["status"] == "RATE_LIMITED"
            assert listed["retrieved_at"] == initial.retrieved_at
            candidate = inspect("candidates")
            assert candidate["eligible"] == 0 and candidate["by_reason"] == {"catalog_stale": 1}
            assert traffic.admitted(cfg, paths, clock[0], members={variant.variant_id[:8]})
            cfg.free_pool.retain_active_on_catalog_stale = False
            assert traffic.admitted(cfg, paths, clock[0], members={variant.variant_id[:8]}) == []
            print("F13_AT_24H_429_NEW_DENIED_POLICY_OK")

            http_status[0] = 200
            worker = pool.FreePool(cfg, paths, clock=lambda: clock[0], fetcher=download)
            clock[0] = worker.next_refresh[source] + 1
            [renewed] = worker.refresh_due(via=None, mark=None)
            assert renewed.status == Status.SUCCESS
            [listed] = inspect("sources")["sources"]
            assert not listed["stale"] and listed["retrieved_at"] == clock[0]
            assert inspect("candidates")["eligible"] == 1
            assert requests == [200, 429, 429, 200]
            print("F13_FRESH_CATALOG_RESTORES_ADMISSION")
    finally:
        server.shutdown()
        thread.join(timeout=2)
PYTHON
then
  printf 'F13_LOOPBACK=PASS\n'
else
  printf 'F13_LOOPBACK=FAIL\n'
  status=1
fi
tail -n 20 "$D/loopback.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'F13_HOST_FIELDS_MATCH\n'
else
  printf 'F13_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Для `F13_CATALOG_LEASE=PASS` нужны зелёные контракты, оба маркера loopback
  и совпадение состояния служб. Указать количество тестов и причины пропусков.
- В отчёте указать SHA кандидата и ТЗ, версию ОС и Python. Зафиксировать отказ
  новому выходу ровно через 24 часа, сохранение последнего снимка при 429,
  сохранение уже применённого выхода по политике и восстановление допуска после 200.
  HTTP-ответы настоящие. Результат пробы выхода в этом сценарии задан фикстурой.
- Выходы рабочего FreePool, истечение учётных данных, дренирование соединений
  и сутки M3 идут отдельной приёмкой. Для них здесь поставить `NOT_RUN`.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-f13-catalog-lease.md` обычным push в
  `docs/flash-proton-ui-manifest`. При параллельном обновлении ветки перенести
  только отчёт. Полные журналы и PID остаются в приватном временном каталоге.
  Системный код Flash не меняет.
