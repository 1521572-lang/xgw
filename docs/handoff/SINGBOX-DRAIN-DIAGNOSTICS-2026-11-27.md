# ThinkCentre · причины ожидания при завершении поколения sing-box

**Ubuntu 24.04 LTS amd64. Кандидат `281d9dd62d9eff4ea310581306f1831a08696bfe`.** В последнем T04/T12 штатный VPN и конфиги восстановились. Первая проверка `stable` истекла через 330 с. Повтор подтвердил исходный blue и остановку legacy. Новый наблюдатель показывает предыдущий слот и условия, из-за которых он ещё сохраняется. [Отчёт T04/T12](https://github.com/1521572-lang/xgw/blob/35fc7fda8aa7d270ff710a51eadcfd6afcc02a3b/docs/reports/2026-11-27T172001Z_t04-t12-live-media-pair.md)

Flash самостоятельно выполняет команды из полного клона XGW и публикует один обезличенный отчёт при любом исходе. При отсутствии терминала, прав чтения или GitHub запрашивает нужный доступ и продолжает доступные этапы. Сценарий запускает два отдельных sing-box обычным пользователем, со случайными портами только на loopback. Штатный шлюз проверяется чтением. Закреплённый код испытания извлекается во временный каталог.

## 1. Подготовка и тесты

При нестандартном расположении задать абсолютные `XGW_TEST_PYTHON` и `XGW_TEST_SINGBOX`. Для чтения состояния root при необходимости предварительно выполнить `sudo -v` в своём терминале. Сохранить значение `D`, которое печатается в начале. Число тестов и версию ядра брать из фактического вывода.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=281d9dd62d9eff4ea310581306f1831a08696bfe
BUNDLE=docs/handoff/artifacts/xgw-singbox-drain-diagnostics.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-singbox-drain.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '20cdeb42ea71af7648cc1af46320d998dd541cd2465c1322a2ecc93fbad70c7a' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
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
        printf '%s\n%s\n' "$unit" "$fields"
    done
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q \
    src/xgw/apply/singbox_process.py docs/helpers/standalone_topology.py
run CONTRACTS timeout -k 5 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_singbox_generations.py tests/test_standalone_topology.py tests/test_desync_standalone.py \
    tests/test_singbox.py tests/test_runtime.py tests/test_standalone_cdn_compare.py
if [[ -x "$SINGBOX" ]] && timeout -k 1 8 "$SINGBOX" version >"$D/singbox-version.txt" 2>&1; then
  run LOOPBACK timeout -k 10 40 "$TEST_PY" -B -P - "$D/tmp" "$SINGBOX" <<'PYTHON'
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from docs.helpers.freepool_lifecycle import xray_running
from xgw.apply import singbox_process as processes
from xgw.generator.singbox import bridge_outbound
from xgw.paths import Paths, atomic_write_json


def config(port):
    return {"log": {"level": "warn"},
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1", "listen_port": port}],
            "outbounds": [{"type": "direct", "tag": "direct"}]}


root, binary = map(Path, sys.argv[1:])
with socket.socket() as first, socket.socket() as second:
    first.bind(("127.0.0.1", 0))
    second.bind(("127.0.0.1", 0))
    old_port, new_port = first.getsockname()[1], second.getsockname()[1]

paths = Paths(root / "test")
paths.run.mkdir(parents=True)
paths.xray_config_dir.mkdir(parents=True)
old = {"slot": "legacy", "until": 20, "ports": [old_port]}
processes.write(paths, {"active": "blue", "pending": None, "draining": old})
core = SimpleNamespace(paths=paths)

# sing-box uses the same local "run -c" process lifecycle as this runner.
with (xray_running(binary, root, "previous", config(old_port), old_port) as previous,
      xray_running(binary, root, "active", config(new_port), new_port) as active):
    def stop(slot):
        assert slot == "legacy"
        previous.terminate()
        previous.wait(timeout=5)

    def stopped(slot):
        assert slot == "legacy"
        return previous.poll() is not None

    def kept(label):
        assert processes.drain_phase(paths, old, now=20) == label
        assert processes.reap(core)["draining"] == old
        assert previous.poll() is None and active.poll() is None
        print("DRAIN_HELD " + label, flush=True)

    with (patch.object(processes, "stop", stop), patch.object(processes, "stopped", stopped),
          patch.object(processes.time, "monotonic", return_value=20)):
        paths.api_dirty_file.touch()
        kept("api_dirty")
        paths.api_dirty_file.unlink()
        atomic_write_json(paths.xray_config_file, None)
        kept("config_unavailable")
        atomic_write_json(paths.xray_config_file, {"outbounds": [bridge_outbound(old_port, "d", "fixture")]})
        kept("old_bridge_referenced")
        atomic_write_json(paths.xray_config_file, {"outbounds": [bridge_outbound(new_port, "d", "fixture")]})
        assert processes.drain_phase(paths, old, now=20) == "awaiting_cleanup"
        final = processes.reap(core)
        assert final["active"] == "blue" and final["draining"] is None
        assert previous.poll() is not None and active.poll() is None
        print("DRAIN_RELEASED_ONLY_PREVIOUS=PASS", flush=True)
PYTHON
  grep -E '^DRAIN_(HELD |RELEASED_ONLY_PREVIOUS=PASS$)' "$D/LOOPBACK.log" || true
else
  printf 'LOOPBACK=NOT_RUN core unavailable\n' | tee -a "$D/status"
fi

observer() {
    sudo -n timeout -k 5 25 env "PYTHONPATH=$PWD:$PWD/src" \
        /usr/bin/python3 -B -P -m docs.helpers.standalone_topology observed 5
}
run HOST_OBSERVED observer

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

- **CONTRACTS.** Записать число passed/failed/skipped. Указать удержание предыдущего поколения до срока, при `api-dirty`, при ссылке на прежний порт и при некорректном файле Xray. Состояние `draining` сохраняется до подтверждения остановки. Выполнить регрессии до конца доступных фаз.
- **LOOPBACK.** Установленный sing-box должен подтвердить три `DRAIN_HELD` и `DRAIN_RELEASED_ONLY_PREVIOUS=PASS`. Тест меняет снимок конфига в приватном префиксе. Остановка в тесте адресована дочернему процессу предыдущего поколения. Адреса и порты остаются локально.
- **HOST_OBSERVED.** Записать активный и предыдущий слоты, `draining`, `drain_phase` и состояние юнитов. При `drain_phase=none` проверено отображение покоя. Живой переход отмечается `NOT_RUN`, если он не происходил. При естественном drain в момент сеанса можно пассивно раз в 20 с повторить чтение в пределах 360 с и записать порядок фаз. `awaiting_cleanup` говорит, что условия по файлам выполнены, и требует последующего чтения для подтверждения остановки. Если прав не хватает, записать точный блокер чтения.
- **HOST_FIELDS.** Сравнить LoadState, ActiveState и MainPID пяти штатных юнитов до и после. Изменившиеся категории указать без значений PID и без гипотез о событиях между снимками.
- **T04/T12.** Живой прямой CDN, плеер, переключение штатных поколений и сутки в этом проходе имеют статус `NOT_RUN`.

## 3. Автоматическая публикация

В `REPORT_SRC` задать абсолютный путь к непустому Markdown с SHA задания и кандидата, версиями Ubuntu, Python, pytest, sing-box и обезличенными итогами. Адреса, PID, конфиги, полный журнал и локальные пути остаются на ThinkCentre. Выполнить из клона и вернуть ссылку на коммит.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-drain-diagnostics.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre sing-box drain diagnostics')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~
