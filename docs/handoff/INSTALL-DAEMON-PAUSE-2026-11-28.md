# ThinkCentre · подготовка пакета при работающем демоне

Ubuntu 24.04 LTS amd64. Кандидат `6a4c838aa0ac35b90bed7fb46b523120dd8435c4`. На `6113fc7` прошли 137 контрактов и проверка отдельного префикса. Установщик отклонил синтаксические ошибки в XGW и Proton до замены пакета. В новом кандидате подготовка и компиляция идут до остановки демона. Проверить штатный порядок, отказ при синтаксической ошибке и сохранение прежних файлов при отказе остановки. [Принятый отчёт](https://github.com/1521572-lang/xgw/blob/24caf5035a85bf11049e5d349592f4c2cb113cba/docs/reports/2026-11-28T110250Z_freepool-r50-install-preflight.md)

Flash сама запускает команды и публикует один обезличенный отчёт при любом исходе. При отсутствии терминала запросить доступ. Системные юниты шлюза проверяются чтением. Пользовательский стенд доступен при наличии пользовательского менеджера systemd. Он использует отдельный префикс и временную службу с ограниченным временем жизни.

## A. Установка и порядок остановки

Из полного клона выполнить блок. Для pytest можно задать абсолютный путь `XGW_TEST_PYTHON`. Строка `PRIVATE_ARTIFACTS` указывает на закрытые журналы.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=6a4c838aa0ac35b90bed7fb46b523120dd8435c4
BUNDLE=docs/handoff/artifacts/xgw-install-daemon-pause.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '2bf4d081566d310d1c74fedd9af1da3e639157404ba01ef34ce602329746b6f0' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging third_party vpn_ui README.md pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$PWD:$PWD/src:$PWD/tests" XGW_ROOT="$D/test-root" TMPDIR="$D/tmp"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
unset PYTHONOPTIMIZE XGW_XRAY_BIN XGW_SINGBOX_BIN XGW_TEST_FREEPOOL_XRAY

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

host_fields >"$D/host.before" 2>"$D/host.before.err" || echo HOST_FIELDS_BEFORE=UNKNOWN
run CONTRACTS timeout -k 5 360 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no tests/test_install.py \
    tests/test_build_release.py tests/test_freepool_candidates.py tests/test_freepool_sources.py
tail -n 12 "$D/CONTRACTS.log"
unit="xgw-accept-install-${D##*.}.service"
if timeout -k 1 5 systemctl --user list-jobs >"$D/user-manager.log" 2>&1; then
    trap 'timeout -k 1 8 systemctl --user stop "$unit" >>"$D/cleanup.log" 2>&1 || true' EXIT
    run USER_UNIT timeout -k 2 12 systemd-run --user --quiet --unit="$unit" \
        --property=RuntimeMaxSec=180s --property=Restart=no /usr/bin/sleep infinity
    if grep -qx 'USER_UNIT=0' "$D/status"; then
        run LIVE_ORDER timeout -k 5 150 /usr/bin/python3 -B -P - "$D" "$unit" <<'PY'
import subprocess
import sys
from pathlib import Path

from xgw.config import Config
from xgw.install import Installer
from xgw.net import cmd
from xgw.paths import Paths

work = Path(sys.argv[1])
unit = sys.argv[2]
assert unit.startswith("xgw-accept-install-") and unit.endswith(".service")
source = Path.cwd()
paths = Paths(root=work / "installed")

def pid():
    return int(subprocess.check_output(
        ["systemctl", "--user", "show", unit, "-p", "MainPID", "--value"],
        text=True, timeout=5,
    ).strip())

before = pid()
assert before > 0
calls = []

def runner(argv, **kwargs):
    if argv[0] == "systemctl":
        assert argv[2:] == ["xgw.service"]
        calls.append(argv[1])
        return cmd.run(["systemctl", "--user", argv[1], unit], **kwargs)
    assert "compileall" in argv
    assert pid() == before
    calls.append("compile")
    try:
        return cmd.run(argv, **kwargs)
    finally:
        assert pid() == before

Installer(Config(), paths, source_root=source)._code()
installer = Installer(Config(), paths, runner=runner, source_root=source)
qt = source / "vpn_ui/qt.py"
installed = paths.lib_dir / "xgw/_desktop/vpn_ui/qt.py"
original = qt.read_bytes()
launcher = paths.launcher.read_bytes()
try:
    qt.write_bytes(b"def broken(:\n")
    try:
        installer._code(before_switch=installer._pause_daemon)
    except cmd.CommandError as exc:
        assert "SyntaxError" in str(exc)
    else:
        raise AssertionError("invalid Python was installed")
    assert pid() == before and calls == ["compile"]
    assert installed.read_bytes() == original and paths.launcher.read_bytes() == launcher
    assert not (paths.lib_dir / "xgw.new").exists()
    print("INVALID_UNIT_PID_STABLE=PASS", flush=True)

    calls.clear()
    qt.write_bytes(original + b"\n# staged update fixture\n")
    installer._code(before_switch=installer._pause_daemon)
    assert calls == ["compile", "is-active", "stop", "is-active"]
    assert installed.read_bytes() == qt.read_bytes()
    assert not any((paths.lib_dir / name).exists() for name in ("xgw.new", "xgw.old"))
    print("COMPILE_BEFORE_SYSTEMD_STOP=PASS", flush=True)
finally:
    qt.write_bytes(original)
PY
        grep -xE '(INVALID_UNIT_PID_STABLE|COMPILE_BEFORE_SYSTEMD_STOP)=PASS' "$D/LIVE_ORDER.log" || true
    else
        echo 'LIVE_ORDER=NOT_RUN user unit failed' | tee -a "$D/status"
    fi
    timeout -k 1 8 systemctl --user stop "$unit" >"$D/cleanup.log" 2>&1 || true
    if timeout -k 1 5 systemctl --user list-units --all --plain --no-legend "$unit" \
        >"$D/unit.after" 2>>"$D/cleanup.log" && [[ ! -s $D/unit.after ]]; then
        echo 'USER_UNIT_CLEAN=PASS'
    else
        echo 'USER_UNIT_CLEAN=CHECK'
    fi
else
    echo 'LIVE_ORDER=NOT_RUN user systemd unavailable' | tee -a "$D/status"
fi

if host_fields >"$D/host.after" 2>"$D/host.after.err" &&
    [[ -s $D/host.before ]] && cmp -s "$D/host.before" "$D/host.after"; then
    echo HOST_FIELDS=MATCH
else
    echo HOST_FIELDS=DRIFT_OR_UNKNOWN
fi
BASH
~~~

- `CONTRACTS` — число прошедших тестов, пропуски и первое расхождение. Успех включает синтаксический отказ без stop/start и оба исхода попытки остановки после компиляции. При неудачной остановке проверить сохранение прежнего файла и очистку подготовки.
- `LIVE_ORDER` — две метки PASS при доступном пользовательском systemd. PID временной службы сохраняется до окончания компиляции и при синтаксической ошибке. На исправном пакете stop происходит после компиляции. Подтвердить очистку юнита. Если пользовательский systemd недоступен, указать это как отдельный блокер.
- `HOST_FIELDS` — результат сравнения полей пяти штатных юнитов.

## B. Свежий писатель FreePool

Кандидат `6113fc7` уже прошёл приёмку пакета и может использоваться в согласованном владельцем окне. После обновления этим кандидатом выполнять живую фазу из прежнего ТЗ. Она сверяет установленный код, свежую схему в статусе демона и обычные записи после его запуска. При отсутствии окна или обновления указать `WRITER/LIVE=NOT_RUN` и причину. [Принятый этап B](https://github.com/1521572-lang/xgw/blob/66fc0e8f20a56ed7d7cabdf37acc0e26ed1d75d1/docs/handoff/FREEPOOL-R50-INSTALL-PREFLIGHT-2026-11-28.md#b-чтение-после-согласованного-обновления)

## Автоматическая публикация

Сохранить SHA задания, SHA кандидата, SHA-256 бандла, версии Ubuntu, Python и pytest, время UTC и результаты всех фаз. Приватные пути, настройки, PID и полные журналы оставить на ThinkCentre. Из полного клона выполнить блок при любом исходе. Задать `REPORT_SRC` как абсолютный путь к готовому обезличенному Markdown.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_install-daemon-pause.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre staging before daemon pause')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
