# ThinkCentre · объявленный срок учётных данных FreePool F13/R13

Ubuntu 24.04 LTS, кандидат `e7ea7dc1a22bc1f614bb72b95622f30e6e8c0106`.
Проверить, как `Subscription-Userinfo: expire=…` влияет на допуск, расписание
проверок и состав FreePool.
[Отчёт о снятии из каталога](https://github.com/1521572-lang/xgw/blob/3dd221ffa0561b3099e12861b2ca40eb3f903d74/docs/reports/2026-11-26T190536Z_freepool-f13-withdrawal.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-f13-credential-expiry.bundle)

Flash сама выполняет команды обычным пользователем. При недоступности терминала запросить доступ.
Опрос использует временный префикс и локальный HTTP-сервер. Часы подменяются только в процессе.
Поля штатных служб считываются до и после.

## Прогон

Из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
При отдельном окружении pytest указать его интерпретатор в `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=e7ea7dc1a22bc1f614bb72b95622f30e6e8c0106
D=$(mktemp -d /tmp/xgw-f13-credential-expiry.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-f13-credential-expiry.bundle >"$D/code.bundle"
printf '%s  %s\n' 'bafccf0c93b3f2c4f05076f9255a779b2388d7a14d89e9a5e0db596123aa3db1' "$D/code.bundle" | sha256sum --check -
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
    tests/test_fetch.py::test_parse_userinfo \
    >"$D/contracts.log" 2>&1; then
  printf 'F13_CREDENTIAL_CONTRACTS=PASS\n'
else
  printf 'F13_CREDENTIAL_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if XGW_ROOT="$D/fixture" timeout -k 5 30 /usr/bin/python3 -B -P - \
    >"$D/loopback.log" 2>&1 <<'PYTHON'
import contextlib
import http.server
import io
import json
import logging
import threading
from unittest.mock import patch

from xgw import actions, cli, config, engine, fetch
from xgw.freepool import pool, providers
from xgw.freepool.models import Status
from xgw.freepool.probe import Outcome
from xgw.paths import Paths

clock = [1_800_000_000.0]
deadline = int(clock[0] + 120)
extended = deadline + 600
provider = providers.IGARECK
paths = Paths.from_env()
paths.ensure()
paths.config_file.write_text(
    '[free_pool]\nmode = "observe"\nproviders = ["igareck"]\n', encoding="utf-8",
)
cfg, warnings = config.load(paths.config_file)
assert not warnings
link = (
    "vless://f54e6dfd-33d8-4ed0-b546-07aef5327f2f@198.51.100.10:443"
    "?security=tls&type=tcp&sni=example.test#fixture\n"
).encode()
headers = {"/a": extended, "/b": deadline}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        expiry = headers.get(self.path)
        status = 429 if expiry == 429 else 200
        payload = b"retry later" if status == 429 else link
        self.send_response(status)
        if status == 200 and expiry is not None:
            self.send_header("Subscription-Userinfo", f"expire={expiry}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def download(url, **kwargs):
    assert url in urls
    return fetch.fetch_url(url, **kwargs, allow_private=True, backoffs=())


def new_worker():
    return pool.FreePool(cfg, paths, clock=lambda: clock[0], fetcher=download, sleep=lambda _: None)


def refresh(worker, expected):
    [result] = worker.refresh_due(via=None, mark=None, force=True)
    assert result.status == expected
    [candidate] = worker.variants()
    return candidate


def inspect(candidate):
    output = io.StringIO()
    applied = {"outbounds": [{"tag": f"pool-de-{candidate.variant_id[:8]}"}]}
    with patch("time.time", lambda: clock[0]):
        with contextlib.redirect_stdout(output):
            assert cli.main(["pool", "candidates", "--json"]) == 0
        chosen, _hosts = engine._pool_servers(
            cfg, paths, engine.Inventory(), applied, None, logging.getLogger("acceptance"),
            active=True,
        )
    return json.loads(output.getvalue())["by_reason"], chosen


with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
    urls = tuple(f"http://127.0.0.1:{server.server_port}/{part}" for part in ("a", "b"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with (
            patch.dict(providers.ORIGINS, {provider: {"127.0.0.1"}}),
            patch.dict(providers.LIST_URLS, {provider: urls}),
        ):
            worker = new_worker()
            candidate = refresh(worker, Status.SUCCESS)
            assert candidate.credential_expires_at == deadline
            key = candidate.variant_id
            good = Outcome("OK", 0.5, 500_000, "DE")
            worker._record(candidate, good)
            clock[0] = deadline - 1
            reasons, chosen = inspect(candidate)
            assert reasons == {"eligible": 1} and len(chosen) == 1
            worker.store.queue_test(key)
            clock[0] = deadline
            reasons, chosen = inspect(candidate)
            assert reasons == {"credentials_expired": 1} and not chosen
            assert not worker.next_checks(None, requested=key) and worker.store.test_request() is None
            with patch("time.time", lambda: clock[0]):
                assert actions.request_pool_test(paths, cfg, key).code == 2
            print("F13_CREDENTIAL_BOUNDARY_EXCLUDES_APPLIED_AND_TEST")

            worker = new_worker()
            clock[0] += 1
            headers["/b"] = 429
            candidate = refresh(worker, Status.PARTIAL)
            assert candidate.credential_expires_at == deadline
            clock[0] += 1
            headers.clear()
            candidate = refresh(worker, Status.SUCCESS)
            assert candidate.credential_expires_at == deadline
            assert inspect(candidate) == ({"credentials_expired": 1}, [])
            print("F13_CREDENTIAL_PARTIAL_AND_MISSING_PRESERVE_EXPIRY")

            clock[0] += 1
            headers.update({"/a": extended, "/b": extended})
            candidate = refresh(worker, Status.SUCCESS)
            assert candidate.variant_id == key and candidate.credential_expires_at == extended
            assert inspect(candidate) == ({"credentials_recheck": 1}, [])
            assert worker.next_checks(None) == [candidate]
            worker._record(candidate, good)
            reasons, chosen = inspect(candidate)
            assert reasons == {"eligible": 1} and len(chosen) == 1
            print("F13_CREDENTIAL_NEW_DEADLINE_NEEDS_FRESH_CHECK")
    finally:
        server.shutdown()
        thread.join(timeout=2)
PYTHON
then
  printf 'F13_CREDENTIAL_LOOPBACK=PASS\n'
else
  printf 'F13_CREDENTIAL_LOOPBACK=FAIL\n'
  status=1
fi
tail -n 25 "$D/loopback.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'F13_CREDENTIAL_HOST_FIELDS_MATCH\n'
else
  printf 'F13_CREDENTIAL_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Для `F13_CREDENTIAL_EXPIRY=PASS` нужны зелёные профильные тесты, три метки loopback
  и совпадение полей штатных служб. Указать число тестов и причины пропусков.
- В двух HTTP-ответах с тем же вариантом проверить выбор раннего срока. Ровно на его границе
  CLI выдаёт `credentials_expired`, сборка исключает даже применённый выход, а тест нового
  подключения с просроченными данными не ставится в очередь.
- Проверить переоткрытие кеша, ответ с 429 у одного файла, полный ответ без срока
  и явное продление. Старая успешная проба не даёт допуск после продления до новой проверки.
  Заголовки HTTP настоящие, результат проверки выхода задан фикстурой.
- Для источников, которые не объявляют срок, фактический отказ учётных данных проверяется
  отдельно. Рабочее переключение, закрытие действующих соединений, срок сертификата
  туннеля и сутки M3 в этом прогоне `NOT_RUN`.
- При любом исходе Flash сама публикует один обезличенный
  `docs/reports/<UTC>_freepool-f13-credential-expiry.md` обычным push в
  `docs/flash-proton-ui-manifest`. Указать SHA кандидата и ТЗ, ОС и Python.
  При параллельном обновлении перенести только отчёт. Полные журналы и PID оставить
  в приватном префиксе. Системный код Flash не редактирует.
