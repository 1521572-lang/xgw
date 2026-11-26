# ThinkCentre · частичный каталог FreePool F13/R13

Ubuntu 24.04 LTS, кандидат `ff26a68eeedce56e30f656c5f93d4ad99d624b68`.
Проверить, что срок каждого пропавшего из частичного ответа варианта считается
по последней публикации именно этого варианта.
[Отчёт о сроке каталога](https://github.com/1521572-lang/xgw/blob/06e6d96c774d2c58c79bbe72187ac5f0262efe1e/docs/reports/2026-11-26T184641Z_freepool-f13-catalog-lease.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-f13-partial-catalog.bundle)

Flash сама запускает команды обычным пользователем. При недоступности терминала
запросить доступ. Прогон использует временный префикс, тестовые данные, локальный HTTP-сервер
и часы внутри процесса. Состояние рабочих служб считывается до и после.

## Прогон

Запуск из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Если pytest в отдельном окружении, задать `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=ff26a68eeedce56e30f656c5f93d4ad99d624b68
D=$(mktemp -d /tmp/xgw-f13-partial.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-f13-partial-catalog.bundle >"$D/code.bundle"
printf '%s  %s\n' '421b80a6a4e09fe68c53c4b85035ee2da4cdb7b000ef61afb621f398033557d1' "$D/code.bundle" | sha256sum --check -
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
  printf 'F13_PARTIAL_CONTRACTS=PASS\n'
else
  printf 'F13_PARTIAL_CONTRACTS=FAIL\n'
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
from xgw.freepool import pool, providers
from xgw.freepool.models import Status
from xgw.freepool.probe import Outcome
from xgw.freepool.store import SOURCE_LEASE
from xgw.paths import Paths

start = 1_800_000_000.0
clock = [start]
provider = providers.IGARECK
paths = Paths.from_env()
paths.ensure()
paths.config_file.write_text(
    '[free_pool]\nmode = "observe"\nproviders = ["igareck"]\n', encoding="utf-8",
)
cfg, warnings = config.load(paths.config_file)
assert not warnings
blocked = set()
requests = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        slot = {"/a": 10, "/b": 11}[self.path]
        status = 429 if self.path in blocked else 200
        requests.append((self.path, status))
        payload = (
            f"vless://f54e6dfd-33d8-4ed0-b546-07aef5327f2f@198.51.100.{slot}:443"
            f"?security=tls&type=tcp&sni=example.test#fixture-{slot}\n"
        ).encode() if status == 200 else b"retry later"
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def download(url, **kwargs):
    assert url in urls
    return fetch.fetch_url(url, **kwargs, allow_private=True, backoffs=())


def inspect(command):
    output = io.StringIO()
    with patch("xgw.cli.time.time", lambda: clock[0]), contextlib.redirect_stdout(output):
        assert cli.main(["pool", command, "--json"]) == 0
    return json.loads(output.getvalue())


def worker_at_clock():
    return pool.FreePool(cfg, paths, clock=lambda: clock[0], fetcher=download, sleep=lambda _: None)


with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
    urls = tuple(f"http://127.0.0.1:{server.server_port}/{part}" for part in ("a", "b"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with (
            patch.dict(providers.ORIGINS, {provider: {"127.0.0.1"}}),
            patch.dict(providers.LIST_URLS, {provider: urls}),
        ):
            worker = worker_at_clock()
            [first] = worker.refresh_due(via=None, mark=None)
            assert first.status == Status.SUCCESS and len(first.variants) == 2
            clock[0] = start + SOURCE_LEASE - 1
            for variant in first.variants:
                worker._record(variant, Outcome("OK", 0.5, 500_000, "DE"))
            blocked.add("/b")
            [partial] = worker.refresh_due(via=None, mark=None, force=True)
            assert partial.status == Status.PARTIAL and len(partial.variants) == 1

            worker = worker_at_clock()
            snap = worker.store.snapshot(provider)
            [carried] = snap["carried_variants"]
            assert len(snap["variants"]) == 1 and carried["last_seen"] == start
            assert inspect("candidates")["by_reason"] == {"eligible": 2}
            print("F13_PARTIAL_PRESERVES_PRIOR_VARIANT")

            clock[0] += 1
            for variant in worker.store.variants(provider):
                worker._record(variant, Outcome("OK", 0.5, 500_000, "DE"))
            [source] = inspect("sources")["sources"]
            assert source["status"] == "PARTIAL" and not source["stale"]
            assert inspect("candidates")["by_reason"] == {"eligible": 1, "catalog_stale": 1}
            print("F13_PARTIAL_EXPIRES_ONLY_OMITTED_VARIANT")

            blocked.clear()
            clock[0] += 1
            [full] = worker.refresh_due(via=None, mark=None, force=True)
            assert full.status == Status.SUCCESS
            assert "carried_variants" not in worker.store.snapshot(provider)
            assert inspect("candidates")["by_reason"] == {"eligible": 2}
            assert requests == [("/a", 200), ("/b", 200), ("/a", 200), ("/b", 429),
                                ("/b", 429), ("/a", 200), ("/b", 200)]
            print("F13_PARTIAL_REAPPEARANCE_RESTORES_ADMISSION")
    finally:
        server.shutdown()
        thread.join(timeout=2)
PYTHON
then
  printf 'F13_PARTIAL_LOOPBACK=PASS\n'
else
  printf 'F13_PARTIAL_LOOPBACK=FAIL\n'
  status=1
fi
tail -n 25 "$D/loopback.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'F13_PARTIAL_HOST_FIELDS_MATCH\n'
else
  printf 'F13_PARTIAL_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `F13_PARTIAL_CATALOG=PASS` требует профильных контрактов, трёх меток loopback
  и совпадения состояния штатных служб. Указать количество тестов и пропуски.
- В loopback один из двух файлов источника реально отвечает 429. Сохранение
  старой строки проверяется после переоткрытия кеша. Через ровно 24 ч пропущенный
  вариант получает `catalog_stale`, опубликованный сосед остаётся доступен.
  Новый полный ответ снова публикует оба. Результаты проверки выхода заданы фикстурой.
- Команды проверяют учёт частичных каталогов. Для подтверждённого снятия варианта
  из полных каталогов, истечения учётных данных, рабочих соединений и М3 указать `NOT_RUN`.
- При любом исходе Flash публикует только обезличенный
  `docs/reports/<UTC>_freepool-f13-partial-catalog.md` обычным push в
  `docs/flash-proton-ui-manifest`. Включить SHA кандидата и ТЗ, ОС и Python.
  Полный лог и состояние служб хранить локально. При обновлении ветки
  перенести только отчёт. Системный код Flash не редактирует.
