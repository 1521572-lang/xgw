# ThinkCentre · срок подтверждения региона FreePool R16

Ubuntu 24.04 LTS, кандидат `0d367795377fdc793c716a8b35c2283e2516b091`.
Один проход проверяет срок подтверждения страны, изменение адреса выхода,
расхождение сведений, смену геоисточника и регрессии FreePool.
[Отчёт о целостности кеша](https://github.com/1521572-lang/xgw/blob/1e64a5014ef797448e2982790c5cecc5ef4bb8d0/docs/reports/2026-11-26T195244Z_freepool-r13-snapshot-integrity.md) · [Бандл с кодом](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r16-region-evidence.bundle)

Flash выполняет команды самостоятельно обычным пользователем. Если терминал
недоступен, запросить доступ. Использовать установленный Xray и записать его
версию. Все записи и процессы тестов относятся к изолированному префиксу.
Сценарии используют только loopback. Исполнитель считывает состояние штатных
служб до и после проверки.

## 1. Подготовка и запуск

Из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest
в отдельном окружении, задать `XGW_TEST_PYTHON`. Для нестандартного пути к
установленному Xray задать `XGW_TEST_XRAY`. Значения должны быть абсолютными
путями. Сохранить вывод и каталог, указанный в `PRIVATE_ARTIFACTS`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=0d367795377fdc793c716a8b35c2283e2516b091
D=$(mktemp -d /tmp/xgw-freepool-r16-region-evidence.XXXXXXXX)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
/usr/bin/python3 --version

git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r16-region-evidence.bundle >"$D/code.bundle"
printf '%s  %s\n' '08f5df36412c25dcb4e742316e5ec6efef0c72ca9f428e3a03c5180a5e1dfc68' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml \
    docs/helpers/freepool_lifecycle.py | tar -x -C "$D/tree"

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
  printf 'R16_CONTRACTS=PASS\n'
else
  printf 'R16_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 30 "$D/contracts.log"

if [[ "$core_ok" != 1 ]]; then
  printf 'R16_XRAY_TRACE=NOT_RUN (Xray unavailable)\n'
else
  if timeout -k 5 70 env XGW_ROOT="$D/region-fixture" /usr/bin/python3 -B -P - "$XRAY" \
      >"$D/region.log" 2>&1 <<'PYTHON'
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from xgw.config import Config
from xgw.freepool import pool, probe, traffic
from xgw.freepool.models import Backend, ProviderResult, Status, Variant
from xgw.paths import Paths


class LocalOrigin(BaseHTTPRequestHandler):
    trace = (200, b"loc=DE\nip=8.8.8.8\n")

    def do_GET(self):
        code, body = self.trace if self.path.startswith("/trace") else (200, b"x" * 65536)
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def run(url, xray):
    cfg = Config()
    cfg.capture.mark_bypass = 0
    cfg.free_pool.mode = "observe"
    cfg.free_pool.providers = ["mahdibland"]
    cfg.probe.url = url + "/probe"
    cfg.probe.trace_url = url + "/trace"
    clock = [1_800_000_000.0]
    t0 = clock[0]
    paths = Paths.from_env()
    assert paths.root.is_absolute() and paths.root != Path("/"), "isolated XGW_ROOT required"
    paths.ensure()
    worker = pool.FreePool(cfg, paths, clock=lambda: clock[0])
    variant = Variant("mahdibland", Backend.XRAY, "fixture", "", "198.51.100.10", 443,
                      "tcp", "loopback fixture", "DE", outbound={"protocol": "freedom"})
    worker.store.commit(ProviderResult("mahdibland", Status.SUCCESS, [variant], t0,
                                       complete_response=True))

    def sample(code, body):
        LocalOrigin.trace = (code, body)
        outcome = probe.check_xray(variant, cfg, xray, paths.run)
        assert outcome.verdict in ("OK", "SLOW"), (outcome.verdict, outcome.probe_kind)
        worker._record(variant, outcome)
        return worker.store.candidates()[variant.variant_id]

    def reasons():
        report = traffic.candidate_report(cfg, paths, clock[0], explain=True)
        assert all(ip not in json.dumps(report) for ip in ("8.8.8.8", "9.9.9.9"))
        assert report["failed_checks"] == [], report["failed_checks"]
        return report["by_reason"]

    first = sample(200, b"loc=DE\nip=8.8.8.8\n")
    assert first["geo_checked_at"] == t0 and first["egress_ip_key"]
    assert reasons() == {"eligible": 1}
    clock[0] = t0 + cfg.free_pool.geo_ttl_seconds - 1
    saved = sample(503, b"trace unavailable")
    assert saved["checked_at"] == clock[0] and saved["geo_checked_at"] == t0
    assert reasons() == {"eligible": 1}
    clock[0] += 1
    worker = pool.FreePool(cfg, paths, clock=lambda: clock[0])
    assert worker.store.candidates()[variant.variant_id]["geo_checked_at"] == t0
    assert reasons() == {"region_evidence_expired": 1}
    assert traffic.admitted(cfg, paths, clock[0], members={variant.variant_id}) == []
    print("R16_TTL=PASS")

    assert sample(200, b"loc=DE\nip=8.8.8.8\n")["geo_checked_at"] == clock[0]
    assert reasons() == {"eligible": 1}
    clock[0] += 1
    sample(200, b"ip=9.9.9.9\n")
    assert reasons() == {"egress_unverified": 1}
    sample(200, b"loc=DE\nloc=US\nip=9.9.9.9\n")
    assert reasons() == {"egress_conflict": 1}
    sample(200, b"loc=US\nip=9.9.9.9\n")
    assert reasons() == {"outside_region": 1}
    current = sample(200, b"loc=DE\nip=9.9.9.9\n")
    assert reasons() == {"eligible": 1}
    assert current["egress_ip_key"] != first["egress_ip_key"]
    assert all(ip not in json.dumps(current) for ip in ("8.8.8.8", "9.9.9.9"))
    print("R16_CHANGE_AND_RECOVERY=PASS")

    cfg.probe.trace_url += "-new"
    assert reasons() == {"egress_unverified": 1}
    sample(503, b"new trace unavailable")
    assert reasons() == {"egress_unverified": 1}
    sample(200, b"loc=DE\nip=9.9.9.9\n")
    assert reasons() == {"eligible": 1}
    print("R16_TRACE_SOURCE=PASS")


with ThreadingHTTPServer(("127.0.0.1", 0), LocalOrigin) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run(f"http://127.0.0.1:{server.server_port}", Path(sys.argv[1]))
    finally:
        server.shutdown()
        thread.join()
PYTHON
  then
    printf 'R16_XRAY_TRACE=PASS\n'
  else
    printf 'R16_XRAY_TRACE=FAIL\n'
    status=1
  fi
  grep '^R16_' "$D/region.log" || true
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
    printf 'R16_HOST_FIELDS_MATCH\n'
  else
    printf 'R16_HOST_FIELDS_DIFFER\n'
    status=1
  fi
else
  printf 'R16_HOST_FIELDS_NOT_RUN\n'
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

## 2. Что проверить и записать

| Блок | Критерий |
| --- | --- |
| Контракты | `R16_CONTRACTS=PASS`. Число тестов и пропусков с причинами. Охватить повреждение снимка, сроки каталога и учётных данных, выбор региона, раннее обновление геодоказательства, частичный ответ, отмену и панель/API. |
| Срок страны | `R16_TTL=PASS`. Реальная HTTP-загрузка через отдельный Xray проходит до и после отказа геоисточника с HTTP 503. На секунду до границы прежняя страна ещё даёт допуск. На границе после перечитывания кеша `region_evidence_expired`, включая ранее применённый вариант. Время здоровья обновляется, время подтверждения страны сохраняется. |
| Изменение и восстановление | `R16_CHANGE_AND_RECOVERY=PASS`. При смене адреса без страны появится `egress_unverified`, при двух разных странах — `egress_conflict`. Подтверждённая страна вне EU даёт `outside_region`, последующий ответ с DE восстанавливает допуск. Диагностика не публикует адрес выхода и не добавляет отказов загрузки к этим исходам. |
| Смена источника trace | `R16_TRACE_SOURCE=PASS`. Старое подтверждение неприменимо сразу после смены URL, новое принимается после успешного ответа. |
| Регрессии Xray | Три независимых исхода `rotation`, `certificate`, `api-switch`. Записать итоги проверки и краткий исход `F13_HELD_STREAM` с причиной. |
| Штатный шлюз | `R16_HOST_FIELDS_MATCH` и снимок `M3_PREFLIGHT`. Записать режим, свежесть, число устройств и живых выходов. Рабочий WAN, пользовательские соединения, долгий дренаж и суточный M3 указать как `NOT_RUN` для этого прохода. |

При сбое отдельного блока завершить остальные доступные проверки. Описать
наблюдаемую ошибку или причину пропуска. Если проверка кода остановилась на
загрузке бандла, сверить ветку, контрольную сумму и наличие базового SHA,
затем повторить подготовку один раз.

## 3. Публикация

Flash автоматически публикует один обезличенный отчёт
`docs/reports/<UTC>_freepool-r16-region-evidence.md` обычным push в ветку
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кода и ТЗ,
Ubuntu, Python, версию Xray и таблицу результатов. При обновлении ветки
перенести свой отчёт на актуальную вершину. Полные логи, данные узлов и PID
остаются в приватном каталоге. Системные правки по отчёту готовит разработчик.
