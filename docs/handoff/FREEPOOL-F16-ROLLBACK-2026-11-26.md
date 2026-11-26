# ThinkCentre · откат настроек FreePool F16

Ubuntu 24.04 LTS. Кандидат `7f743f4eb8f222a5abfa91d0a91e6d100cc77639`, версия до `pool select` — `c0095a1792192e1fd10e3d1c388f48b363e99ed0`.
Проверить переход между двумя версиями на одном изолированном префиксе.
[R50 на ThinkCentre](https://github.com/1521572-lang/xgw/blob/5d5ef07f92c0684f3196ee7fd73b4a32d84a8083/docs/reports/2026-11-26T162945Z_freepool-r50-selection.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-f16-rollback.bundle)

Flash сама выполняет технический прогон. При недоступности сеанса либо
чтения полей рабочего шлюза запросить доступ. Используются синтетические
подписки, адреса и `XGW_ROOT` в приватном каталоге 0700. Допустимые действия
на штатном шлюзе — только чтение свойств служб и хэшей двух конфигов.
Код обоих выпусков ставится лишь в тестовый префикс, вызывается только
этап `Installer._code()`. Настоящие ядра, клиенты и трафик в сценарий не входят.

## Прогон

Запустить от обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest установлен в
отдельном окружении, указать путь через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=7f743f4eb8f222a5abfa91d0a91e6d100cc77639
OLD=c0095a1792192e1fd10e3d1c388f48b363e99ed0
D=$(mktemp -d "$HOME/xgw-freepool-f16.XXXXXXXX")
TEST_PY=/usr/bin/python3
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\nBASELINE %s\n' "$D" "$PRETTY_NAME" "$CODE" "$OLD"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-f16-rollback.bundle >"$D/code.bundle"
printf '%s  %s\n' '7e19acfa1d1bf7ef64f9bc24af38243c42a157158390551402f05abb66d14fbe' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
git -C "$REPO" merge-base --is-ancestor "$OLD" "$CODE"
mkdir "$D/old" "$D/new"
git -C "$REPO" archive "$OLD" src vpn_ui packaging config.example.toml | tar -x -C "$D/old"
git -C "$REPO" archive "$CODE" src vpn_ui packaging config.example.toml tests pyproject.toml | tar -x -C "$D/new"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
host_fields >"$D/before.txt"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
status=0
(
  cd "$D/new"
  PYTHONPATH="$D/new/src" timeout -k 3 150 "$TEST_PY" -B -m pytest \
    -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_selection.py tests/test_freepool_traffic.py \
    tests/test_config.py tests/test_managed.py \
    tests/test_install.py::test_proton_update_uses_manifest_and_keeps_previous_code_on_error
) >"$D/contracts.log" 2>&1 || status=1
tail -n 20 "$D/contracts.log"

cat >"$D/matrix.sh" <<'MATRIX'
set -euo pipefail
D=$1
PY=/usr/bin/python3
export XGW_ROOT="$D/control"
ETC="$XGW_ROOT/etc/xgw"
LAUNCH="$XGW_ROOT/usr/local/bin/xgw"
mkdir -p "$ETC"
cat >"$ETC/config.toml" <<'TOML'
[free_pool]
mode = "observe"
region = "EU"
region_policy = "preferred"
fallback_regions = ["ASIA"]

[[subscriptions]]
name = "toml-fixture"
url = "https://config.example.test/sub"
TOML
cat >"$ETC/panel.json" <<'JSON'
{"free_pool_mode":"observe","subscriptions":[{"name":"panel-fixture","url":"https://panel.example.test/sub","headers":{"X-Example":"fixture"}}]}
JSON

install_code() {
  PYTHONPATH="$D/$1/src" "$PY" -B -P - "$D/$1" <<'PYTHON'
import sys
from pathlib import Path

from xgw import config
from xgw.install import Installer
from xgw.paths import Paths

def code_only(argv, **kwargs):
    assert argv[:4] == [sys.executable, "-m", "compileall", "-q"], argv
    assert Path(argv[4]).resolve().is_relative_to(paths.root.resolve())
    return ""

source = Path(sys.argv[1])
paths = Paths.from_env()
cfg, _ = config.load(paths.config_file)
Installer(cfg, paths, source_root=source, runner=code_only)._code()
assert (paths.lib_dir / "xgw/cli.py").read_bytes() == (source / "src/xgw/cli.py").read_bytes()
PYTHON
}

installed_py() {
  PYTHONPATH="$XGW_ROOT/opt/xgw/lib" "$PY" -B -P "$@"
}

assert_settings() {
  installed_py - "$@" <<'PYTHON'
import sys
from xgw import config
from xgw.paths import Paths

region, policy = sys.argv[1:]
cfg, _ = config.load(Paths.from_env().config_file)
assert (cfg.free_pool.region, cfg.free_pool.region_policy) == (region, policy)
assert cfg.free_pool.mode == "observe" and cfg.free_pool.fallback_regions == ["ASIA"]
assert not cfg.managed.routes
subs = {item.name: (item.url, item.headers) for item in cfg.subscriptions}
assert subs == {
    "toml-fixture": ("https://config.example.test/sub", {}),
    "panel-fixture": ("https://panel.example.test/sub", {"X-Example": "fixture"}),
}
PYTHON
}

check_settings() {
  local code=0
  "$LAUNCH" pool rollback-check --json >"$D/$1.json" || code=$?
  test "$code" = "$2"
  "$PY" -B - "$D/$1.json" "$3" "$4" <<'PYTHON'
import json
import sys
from pathlib import Path

path, region, expected = sys.argv[1:]
report = json.loads(Path(path).read_bytes())
assert report["rollback_selection"] == {"region": "EU", "policy": "preferred"}
assert report["saved_selection"] == ({"region": region, "policy": "strict"} if region else None)
assert report["blockers"] == (expected.split(",") if expected else [])
assert report["assigned_devices"] == int("assigned_devices" in report["blockers"])
assert report["mode"] == ("on" if "whole_house" in report["blockers"] else "observe")
PYTHON
}

sha256sum "$ETC/config.toml" >"$D/toml.sha"
install_code old
assert_settings EU preferred
sha256sum "$ETC/panel.json" >"$D/initial-panel.sha"
install_code new
sha256sum -c "$D/initial-panel.sha"
check_settings initial 0 '' ''
"$LAUNCH" pool select --region US --policy strict
assert_settings US strict
check_settings selection 2 US saved_selection
sha256sum "$ETC/panel.json" >"$D/selected-panel.sha"

# На том же префиксе сравнить чтение и запись старой версией.
install_code old
sha256sum -c "$D/selected-panel.sha"
assert_settings EU preferred
cp "$ETC/panel.json" "$D/old-panel-write.json"
installed_py - "$D/old-panel-write.json" <<'PYTHON'
import json
import sys
from pathlib import Path
from xgw import managed

panel = Path(sys.argv[1])
assert managed.set_sticky(panel, True)
data = json.loads(panel.read_bytes())
assert "free_pool_selection" not in data and data["sticky"] is True
PYTHON
sha256sum -c "$D/selected-panel.sha"
install_code new
assert_settings US strict
check_settings restored 2 US saved_selection
printf 'F16_LEGACY_BEHAVIOR_OK\n'

# Проверить срабатывание предохранителя для режима on и назначения устройства.
installed_py - <<'PYTHON'
from xgw import managed
from xgw.paths import Paths

panel = managed.path_for(Paths.from_env().config_file)
assert managed.set_free_pool_mode(panel, "on")
assert managed.set_route(panel, "02:00:00:00:00:01", "192.0.2.20", "fixture", "pool")
PYTHON
check_settings whole-and-device 2 US whole_house,assigned_devices,saved_selection
installed_py - <<'PYTHON'
from xgw import managed
from xgw.paths import Paths

panel = managed.path_for(Paths.from_env().config_file)
assert managed.set_free_pool_mode(panel, "observe")
PYTHON
check_settings device-only 2 US assigned_devices,saved_selection
installed_py - <<'PYTHON'
from xgw import managed
from xgw.paths import Paths

panel = managed.path_for(Paths.from_env().config_file)
assert managed.set_route(panel, "02:00:00:00:00:01", "192.0.2.20", "fixture", "")
PYTHON
"$LAUNCH" pool select --reset
check_settings ready 0 '' ''
sha256sum "$ETC/panel.json" >"$D/ready-panel.sha"
install_code old
assert_settings EU preferred
install_code new
assert_settings EU preferred
check_settings final 0 '' ''
sha256sum -c "$D/toml.sha"
sha256sum -c "$D/ready-panel.sha"
test "$(stat -c %a "$ETC/panel.json")" = 600
printf 'F16_PREPARED_ROLLBACK_OK\n'
MATRIX
timeout -k 5 180 bash "$D/matrix.sh" "$D" >"$D/matrix.log" 2>&1 || status=1
tail -n 25 "$D/matrix.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'F16_HOST_FIELDS_MATCH\n'
else
  printf 'F16_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `F16_SELECTOR_ROLLBACK=PASS` требует зелёных контрактов и трёх меток
  `F16_LEGACY_BEHAVIOR_OK`, `F16_PREPARED_ROLLBACK_OK`,
  `F16_HOST_FIELDS_MATCH`. Указать оба SHA, SHA ТЗ, ОС, число тестов,
  коды `rollback-check` и сохранение TOML, панели и подписок по матрице.
- При несовпадении или недоступности указать фазу и `FAIL` или `NOT_RUN`
  с причиной. Установка и откат действующего шлюза с пользовательским
  трафиком, проверка реальных подписок и сутки M3 в любом случае `NOT_RUN`.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-f16-rollback.md` обычным push в
  `docs/flash-proton-ui-manifest`. При расхождении ветки перенести только
  отчёт поверх актуальной вершины. Конфиги, хэши рабочего шлюза и полные
  логи оставить локально. Системный код Flash не меняет.
