# ThinkCentre · снятие из каталога FreePool F13/R13

Ubuntu 24.04 LTS, кандидат `42ff097df4f7f91122452322224d117c36ead5db`.
Проверить переход в `WITHDRAWN` после двух полных каталогов и возврат после повторной публикации.
[Отчёт по частичному каталогу](https://github.com/1521572-lang/xgw/blob/d17af6305d32bfd74630b44bdf409b346f81f41c/docs/reports/2026-11-26T185607Z_freepool-f13-partial-catalog.md)
· [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-f13-withdrawal.bundle)

Flash сама выполняет команды обычным пользователем. При недоступности терминала запросить доступ.
Сценарий использует отдельный префикс, тестовые ссылки и локальный HTTP-сервер. Состояние штатных
служб считывается до и после. Подменённые часы действуют внутри прогона.

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
CODE=42ff097df4f7f91122452322224d117c36ead5db
D=$(mktemp -d /tmp/xgw-f13-withdrawal.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-f13-withdrawal.bundle >"$D/code.bundle"
printf '%s  %s\n' '1b15e9757928a9e9858c274e104d869c0d8bbbf73d2a3d89591ed4bb3b1ae13b' "$D/code.bundle" | sha256sum --check -
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
  printf 'F13_WITHDRAWAL_CONTRACTS=PASS\n'
else
  printf 'F13_WITHDRAWAL_CONTRACTS=FAIL\n'
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
from xgw.paths import Paths

clock = [1_800_000_000.0]
provider = providers.IGARECK
paths = Paths.from_env()
paths.ensure()
paths.config_file.write_text(
    '[free_pool]\nmode = "observe"\nproviders = ["igareck"]\n', encoding="utf-8",
)
cfg, warnings = config.load(paths.config_file)
assert not warnings
mode = ["both"]
responses = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        slot = 11 if self.path == "/a" else (10 if mode[0] == "both" else 12)
        status = 429 if self.path == "/b" and mode[0] == "limited" else 200
        payload = (
            f"vless://f54e6dfd-33d8-4ed0-b546-07aef5327f2f@198.51.100.{slot}:443"
            f"?security=tls&type=tcp&sni=example.test#fixture-{slot}\n"
        ).encode()
        if self.path == "/b" and mode[0] == "unusable":
            payload = b"<html>not a catalog</html>"
        if status == 429:
            payload = b"retry later"
        responses.append((mode[0], self.path, status))
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def download(url, **kwargs):
    assert url in urls
    return fetch.fetch_url(url, **kwargs, allow_private=True, backoffs=())


def candidates():
    output = io.StringIO()
    with patch("xgw.cli.time.time", lambda: clock[0]), contextlib.redirect_stdout(output):
        assert cli.main(["pool", "candidates", "--explain", "--json"]) == 0
    return json.loads(output.getvalue())


def new_worker():
    return pool.FreePool(cfg, paths, clock=lambda: clock[0], fetcher=download, sleep=lambda _: None)


def refresh(worker, phase):
    mode[0] = phase
    clock[0] += 60
    [result] = worker.refresh_due(via=None, mark=None, force=True)
    return result


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
            first = refresh(worker, "both")
            assert first.status == Status.SUCCESS and first.complete_response
            target = next(v for v in first.variants if v.address.endswith(".10"))
            key = target.variant_id
            healthy = Outcome("OK", 0.5, 500_000, "DE")
            worker._record(target, healthy)
            assert candidates()["eligible"] == 1

            first_missing = refresh(worker, "absent")
            assert first_missing.status == Status.SUCCESS and first_missing.complete_response
            assert worker.store.snapshot(provider)["missing_since"] == {key: clock[0]}
            assert candidates()["eligible"] == 1
            worker = new_worker()
            for phase in ("limited", "unusable"):
                partial = refresh(worker, phase)
                assert partial.status == Status.PARTIAL and not partial.complete_response
                assert "withdrawn" not in candidates()
                assert candidates()["eligible"] == 1
            assert ("limited", "/b", 429) in responses and ("unusable", "/b", 200) in responses
            print("F13_WITHDRAWAL_FIRST_MISS_AND_PARTIAL_KEEP")

            second_missing = refresh(worker, "absent")
            assert second_missing.status == Status.SUCCESS and second_missing.complete_response
            assert worker.store.withdrawn(provider) == {key: clock[0]}
            assert key not in worker.store.candidates()
            assert traffic.admitted(cfg, paths, clock[0], members={key[:8]}) == []
            report = candidates()
            assert report["eligible"] == 0 and report["withdrawn"] == {provider: 1}
            assert key not in json.dumps(report)
            print("F13_WITHDRAWAL_SECOND_FULL_EXCLUDES")

            received = refresh(worker, "both")
            assert received.status == Status.SUCCESS and not worker.store.withdrawn(provider)
            assert candidates()["eligible"] == 0
            worker._record(target, healthy)
            assert candidates()["eligible"] == 1
            print("F13_WITHDRAWAL_REPUBLISH_REQUIRES_NEW_CHECK")
    finally:
        server.shutdown()
        thread.join(timeout=2)
PYTHON
then
  printf 'F13_WITHDRAWAL_LOOPBACK=PASS\n'
else
  printf 'F13_WITHDRAWAL_LOOPBACK=FAIL\n'
  status=1
fi
tail -n 25 "$D/loopback.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'F13_WITHDRAWAL_HOST_FIELDS_MATCH\n'
else
  printf 'F13_WITHDRAWAL_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Для `F13_WITHDRAWAL=PASS` нужны профильные тесты, три метки loopback и совпадение состояния служб.
  Указать число тестов и причины пропусков. Контракты покрывают повторы одной метки опроса,
  ошибку записи текущего снимка, старый по времени снимок и пределы разбора.
- После первого полного пропуска и двух частичных ответов выход ещё пригоден при действующем
  сроке. Частичные ответы включают HTTP 429 и непригодный файл с HTTP 200. После второго полного
  пропуска выводится агрегированный `WITHDRAWN`, а выход исключается из нового состава.
  После повторной публикации требуется новая проверка. HTTP-ответы настоящие, результаты
  проверки выхода заданы фикстурой.
- Для истечения учётных данных, дренирования реального соединения и суток M3 указать `NOT_RUN`.
- При любом исходе Flash сама публикует обезличенный
  `docs/reports/<UTC>_freepool-f13-withdrawal.md` обычным push в
  `docs/flash-proton-ui-manifest`. Указать SHA кандидата и ТЗ, ОС и Python.
  При параллельном обновлении ветки перенести только отчёт. PID и полные журналы остаются
  в приватном префиксе. Системный код Flash не редактирует.
