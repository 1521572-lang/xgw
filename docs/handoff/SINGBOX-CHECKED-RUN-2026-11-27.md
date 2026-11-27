# ThinkCentre · привязка проверки моста к процессу sing-box

Ubuntu 24.04 LTS amd64, кандидат `a880cdfcd5f56692dd49de4055e9f5e812899a58`. Предыдущий проход принял матрицу 212/212 и 12 проверок watchdog. Теперь проверяется один переход blue → green на отдельных процессах и два отказа при замене кандидата. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/4df22a3191500d5661befb38932ab186db43089d/docs/reports/2026-11-27T183247Z_dualcore-regression-matrix.md)

Flash сама выполняет готовые команды, запрашивает доступ к терминалу или GitHub при необходимости и публикует обезличенный отчёт при любом исходе. Стенд запускается обычным пользователем и работает только на loopback. Поля пяти штатных юнитов сверяются чтением до и после.

## 1. Запуск

Из полного клона XGW. При нестандартных путях заранее задать абсолютные `XGW_TEST_PYTHON` (с pytest) и `XGW_TEST_SINGBOX`. Записать путь к приватному каталогу из первого вывода.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=a880cdfcd5f56692dd49de4055e9f5e812899a58
BUNDLE=docs/handoff/artifacts/xgw-singbox-checked-run.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-checked-run.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'b0cbd27e57982ed88d639f831f613d4604c6cca553925c846c7d7aeb8563b51b' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/lab" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src:$PWD/tests" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
unset XGW_XRAY_BIN XGW_SINGBOX_BIN XGW_TEST_FREEPOOL_XRAY PYTHONOPTIMIZE

run() {
    local label=$1 rc=0
    shift
    "$@" >"$D/$label.log" 2>&1 || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/status"
}

host_fields() {
    local unit fields
    for unit in xgw.service xgw-xray.service xgw-singbox.service \
                xgw-singbox-blue.service xgw-singbox-green.service; do
        fields=$(timeout -k 1 4 systemctl show "$unit" -p LoadState -p ActiveState -p MainPID) ||
            [[ "$fields" == *'LoadState=not-found'* ]] || return 1
        [[ "$fields" == *'LoadState='* && "$fields" == *'ActiveState='* && "$fields" == *'MainPID='* ]] ||
            return 1
        printf '%s\n%s\n' "$unit" "$fields"
    done
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q src/xgw/apply
pytest_run() {
    timeout -k 5 240 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --color=no -q -rs -rfE --tb=short --show-capture=no "$@"
}
run REGRESSIONS pytest_run tests/test_singbox_generations.py tests/test_standalone_topology.py \
    tests/test_desync_standalone.py tests/test_singbox.py tests/test_runtime.py \
    tests/test_standalone_cdn_compare.py tests/test_dualcore.py
run WATCHDOG pytest_run tests/test_daemon.py -k 'background_build or pending_singbox_resume'
tail -n 14 "$D/REGRESSIONS.log" "$D/WATCHDOG.log"

if [[ -x "$SINGBOX" ]] && timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1; then
    run CHECKED_RUN timeout -k 10 80 "$TEST_PY" -B -P - "$D/lab" "$SINGBOX" <<'PYTHON'
import http.server
import json
import socket
import sys
from contextlib import ExitStack
from pathlib import Path

import pytest

from docs.helpers.freepool_lifecycle import serving
from test_singbox_generations import gateway
from xgw.apply import singbox_generation as generations
from xgw.apply import singbox_process as processes
from xgw.paths import atomic_write_json
from xgw.xraycore.service import ProcessXrayService

LOCAL = "127.0.0.1"

class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits += 1
        body = b"local-bridge-check"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def case(root, binary, variant):
    root.mkdir()
    real_generation_run = processes.generation_run
    real_bridge_check = generations.bridge_check
    with ExitStack() as stack:
        patch = stack.enter_context(pytest.MonkeyPatch.context())
        w = gateway.__wrapped__(root, patch)
        server = http.server.HTTPServer((LOCAL, 0), Origin)
        server.hits = 0
        origin_port = stack.enter_context(serving(server))
        w.core.cfg.probe.url = f"http://{LOCAL}:{origin_port}/sample"
        with socket.socket() as old, socket.socket() as new:
            old.bind((LOCAL, 0))
            new.bind((LOCAL, 0))
            old_port, new_port = old.getsockname()[1], new.getsockname()[1]
        w.old["inbounds"][0]["listen_port"] = old_port
        w.xray["outbounds"][0]["settings"]["servers"][0]["port"] = old_port
        w.core.cfg.core.port_base = new_port
        atomic_write_json(w.paths.singbox_config_file, w.old)
        atomic_write_json(w.paths.xray_config_file, w.xray)
        w.api.items = {w.xray["outbounds"][0]["tag"]: w.xray["outbounds"][0].copy()}
        processes.write(w.paths, {"active": "blue", "pending": None, "draining": None})
        w.alive.clear()
        services = {}

        def start(core, slot, config):
            path = root / f"{slot}.json"
            atomic_write_json(path, {
                "log": {"level": "error"},
                "inbounds": config["inbounds"],
                "outbounds": [{"type": "direct", "tag": "fixture"}],
                "route": {"rules": [
                    {"ip_cidr": [LOCAL + "/32"], "port": [origin_port],
                     "action": "route", "outbound": "fixture"},
                    {"action": "reject"},
                ]},
            })
            service = ProcessXrayService(binary, path)
            stack.callback(service.stop)
            service.start()
            services[slot] = service
            w.alive.add(processes.unit(slot))

        def stop(slot):
            services[slot].stop()
            w.alive.discard(processes.unit(slot))

        def main_pid(slot):
            service = services.get(slot)
            return service._proc.pid if service is not None and service.is_active() else 0

        def restart_candidate():
            previous = real_generation_run("green")
            assert previous is not None
            services["green"].restart()
            current = real_generation_run("green")
            assert current is not None and current != previous

        def check_bridge(*args, **kwargs):
            hits = server.hits
            result = real_bridge_check(*args, **kwargs)
            assert result and server.hits == hits + 1
            if variant == "DURING_PROOF":
                restart_candidate()
            return result

        patch.setattr(processes, "start", start)
        patch.setattr(processes, "stop", stop)
        patch.setattr(processes, "main_pid", main_pid)
        patch.setattr(processes, "generation_run", real_generation_run)
        patch.setattr(generations, "bridge_check", check_bridge)
        start(w.core, "blue", w.old)
        old_run = real_generation_run("blue")
        assert old_run is not None
        if variant == "DURING_PROOF":
            with pytest.raises(ValueError, match="во время проверки моста"):
                generations.prepare(w.core, w.old, w.xray)
        else:
            prepared = generations.prepare(w.core, w.old, w.xray)
            if variant == "BEFORE_COMMIT":
                restart_candidate()
            outcome = generations.finish(w.core, w.applier, prepared)
            if variant == "BEFORE_COMMIT":
                assert outcome.mode == "rejected" and "после проверки моста" in outcome.detail
            else:
                state = processes.read(w.paths)
                assert outcome.mode == "api" and state["active"] == "green" and w.api.calls
                assert state["draining"]["slot"] == "blue"
                assert real_generation_run("green") == prepared.run
        assert real_generation_run("blue") == old_run
        if variant != "STABLE":
            state = processes.read(w.paths)
            assert state["active"] == "blue" and state["pending"] is None and not w.api.calls
            assert real_generation_run("green") is None
            assert json.loads(w.paths.xray_config_file.read_bytes()) == w.xray
            assert w.core.read() == w.old
        print("CHECKED_RUN_" + variant + "=PASS", flush=True)


root, binary = map(Path, sys.argv[1:])
for variant in ("DURING_PROOF", "BEFORE_COMMIT", "STABLE"):
    case(root / variant.lower(), binary, variant)
PYTHON
    grep -E '^CHECKED_RUN_(DURING_PROOF|BEFORE_COMMIT|STABLE)=PASS$' "$D/CHECKED_RUN.log" || true
else
    echo 'CHECKED_RUN=NOT_RUN sing-box unavailable' | tee -a "$D/status"
fi

after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

## 2. Критерии

- `CHECKED_RUN_DURING_PROOF`. Реальный прокси возвращает ответ HTTP. При замене кандидата до окончания проверки старый слот остаётся активен, API-вызовов нет.
- `CHECKED_RUN_BEFORE_COMMIT`. Кандидат готов, затем его процесс заменён. Вызов finish отклонён, исходные конфиги остаются на месте, API-вызовов нет.
- `CHECKED_RUN_STABLE`. Реальный запрос проходит через тот же кандидат. Переход blue → green принят в приватном префиксе. Старый процесс остаётся на время drain. Для этих сценариев используется запись API в тестовом объекте. Проверка полномочий служебной учётной записи покрыта контрактами, а отслеживание MainPID и времени старта использует дочерние процессы и настоящий procfs.
- `REGRESSIONS`, `WATCHDOG`, `HOST_FIELDS`. Указать фактическое число прошедших, пропущенных и упавших тестов. Пять штатных юнитов сравнить по LoadState, ActiveState и MainPID, привести только итог и категории различий.
- Штатный переход, внешний YouTube и сутки отметить `NOT_RUN`. Все сценарии в изолированном сеансе. При техническом блокере указать точный этап и продолжить доступные проверки.

## 3. Публикация

Указать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest и sing-box, UTC, исходы этапов и причины пропусков. Приватные пути, адреса, порты, PID, конфиги и сырые логи оставить на ThinkCentre. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-checked-run.md
  export GIT_INDEX_FILE="$pub/index"
  blob=$(git -C "$repo" hash-object -w -- "$REPORT_SRC")
  local_ref=refs/xgw-report/$(basename "$pub")
  trap 'git -C "$repo" update-ref -d "$local_ref"' EXIT
  for i in 1 2 3; do
    git -C "$repo" fetch --quiet --no-tags --no-write-fetch-head origin "$ref:$local_ref"
    tip=$(git -C "$repo" rev-parse "$local_ref")
    if prev=$(git -C "$repo" rev-parse --verify "$tip:$file" 2>/dev/null); then
      [[ $prev == "$blob" ]] || exit 1
      printf 'PUBLISHED %s %s\n' "$tip" "$file"
      exit 0
    fi
    git -C "$repo" read-tree "$tip"
    git -C "$repo" update-index --add --cacheinfo "100644,$blob,$file"
    tree=$(git -C "$repo" write-tree)
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre verified sing-box process handoff')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

Если публикация требует прав записи, запросить доступ и повторить с тем же отчётом. Вернуть ссылку на коммит.
