# ThinkCentre · каталоги FreePool, R50

Ubuntu 24.04 LTS. Кандидат `b0b1e18643a4b93f5bbf2db73cae4e4865d0363c`. Этот короткий проход проверяет
`xgw pool sources` независимо от суточного дневника M3.
Команда показывает состав настроенных источников, время принятого каталога,
время и итог последней попытки, число вариантов и признак устаревания.

Flash выполняет команды сама. При недоступности терминала или требуемого
чтения конфигурации и каталогов запросить доступ. Использовать существующее
состояние шлюза. Сценарий неудачного обновления выполняется контрактом во
временном каталоге pytest. [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-sources.bundle)

## Проверка

Открыть полный клон XGW с базовой ревизией `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Если pytest установлен в отдельном окружении, задать `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-freepool-r50.XXXXXXXX")
CODE=b0b1e18643a4b93f5bbf2db73cae4e4865d0363c
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-sources.bundle >"$D/code.bundle"
printf '%s  %s\n' 'fc63c8241c83f2032917c543024bea49af04eed1c22eef54f9d2a151ed1e971a' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
(
  cd "$D/tree"
  "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider --portable \
    tests/test_freepool_sources.py tests/test_freepool_stats.py
  "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool.py::test_pool_command_shows_the_summary_and_switches_the_mode \
    tests/test_freepool.py::test_pool_command_prefers_the_daemon_summary
) >"$D/contracts.log" 2>&1 || { tail -n 24 "$D/contracts.log"; exit 1; }
tail -n 8 "$D/contracts.log"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
candidate() {
  sudo -n timeout -k 2 15 /usr/bin/env -i "PYTHONPATH=$PYTHONPATH" "$PY" \
    -B -P -m xgw.cli pool sources "$@"
}
host_fields >"$D/before.txt"
candidate --json >"$D/sources.json"
candidate >"$D/sources.txt"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
fi

"$PY" -I -B - "$D/sources.json" "$D/sources.txt" <<'PYTHON'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_bytes())
text = Path(sys.argv[2]).read_text()
assert set(data) == {"mode", "sources"} and data["mode"] in {"off", "observe", "on"}
for row in data["sources"]:
    assert set(row) == {"id", "status", "retrieved_at", "attempted_at", "variants", "stale"}
    assert type(row["variants"]) is int and row["variants"] >= 0
    assert type(row["stale"]) is bool
    for key in ("retrieved_at", "attempted_at"):
        assert row[key] is None or type(row[key]) in (int, float)
    assert row["id"] in {"vpngate", "vpnbook", "igareck", "mahdibland"}
assert len({row["id"] for row in data["sources"]}) == len(data["sources"])
assert text.strip()
print("R50_SOURCES_JSON_OK", len(data["sources"]))
print("R50_SAVED_CATALOGS", sum(row["retrieved_at"] is not None for row in data["sources"]))
PYTHON
BASH
```

`R50_SOURCES=PASS` требует прохода контрактов и обоих форматов на ThinkCentre.
Если сохранённых каталогов нет, записать `CATALOG_EMPTY` отдельно. Контракт
подтверждает, что неудачная попытка сохраняет предыдущий каталог,
его дату и число вариантов. В живом выводе сверить, что даты принятия
и попытки различаются при естественном сбое, если такой уже зафиксирован.
При изменении полей шлюза сохранить оба приватных снимка и записать
известную причину или статус `STATE_UNCONFIRMED`.

Опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-sources.md` в ветке
`docs/flash-proton-ui-manifest` при любом исходе. Указать SHA кода и ТЗ, ОС, результаты
контрактов, число источников и сохранённых каталогов, итог сверки.
Публикуются только агрегаты. Выбор кандидата, запросы обновления и пауза
фоновой работы проверяются отдельно.
