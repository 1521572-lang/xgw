# ThinkCentre · допуск кандидатов FreePool, R50

Ubuntu 24.04 LTS. Кандидат `c26d04e35c8d26b09ec8e5d0d9b45027e49eb43c`. Предыдущее ТЗ подтвердило четыре свежих
каталога с 640 вариантами. В окне M3 трафик устройств через пул отсутствовал.
Проверь, сколько бесплатных вариантов из действующих каталогов проходит
критерий допуска новых участников и какие причины дают остальные.
[Отчёт каталогов](https://github.com/1521572-lang/xgw/blob/46e028b2095c3c61e9902fb751d1fe9d47cb6087/docs/reports/2026-11-26T114713Z_freepool-r50-sources.md) · [Отчёт M3](https://github.com/1521572-lang/xgw/blob/46e028b2095c3c61e9902fb751d1fe9d47cb6087/docs/reports/2026-11-26T114713Z_freepool-m3-diary.md)

Flash сама выполняет команды. При недоступности терминала или чтения
файлов XGW запросить доступ. Использовать текущую конфигурацию и сохранённые
итоги её фоновых проверок. Обращение к провайдерам, перезапуск служб и
переключение маршрутов в проверку не входят. Частные файлы остаются в
каталоге 0700. [Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-candidates.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. При необходимости задать
`XGW_TEST_PYTHON` с путём к интерпретатору, где уже есть pytest.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=c26d04e35c8d26b09ec8e5d0d9b45027e49eb43c
D=$(mktemp -d "$HOME/xgw-freepool-candidates.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-candidates.bundle >"$D/code.bundle"
printf '%s  %s\n' '9cceb34b426e284e5c324683e7702349c2c87049e8d902a3b9f27a32b9f4cf79' "$D/code.bundle" | sha256sum --check -
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
    tests/test_freepool_candidates.py tests/test_freepool_sources.py tests/test_freepool_stats.py
  "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py::test_admitted_are_fresh_working_servers_of_the_region_with_an_address \
    tests/test_freepool_traffic.py::test_panel_rows_tell_why_a_pool_server_is_not_admitted \
    tests/test_freepool_traffic.py::test_pool_member_keeps_its_place_with_an_old_check
) >"$D/contracts.log" 2>&1 || { tail -n 24 "$D/contracts.log"; exit 1; }
tail -n 8 "$D/contracts.log"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
candidate() {
  sudo -n timeout -k 2 15 /usr/bin/env -i "PYTHONPATH=$PYTHONPATH" "$PY" \
    -B -P -m xgw.cli pool candidates "$@"
}
host_fields >"$D/before.txt"
code=0
candidate --explain --json >"$D/configured.json" 2>"$D/configured.err" &&
  candidate --region EU --explain --json >"$D/eu.json" 2>"$D/eu.err" &&
  candidate --region EU --explain >"$D/eu.txt" 2>"$D/eu-text.err" || code=$?
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
fi
if [[ $code != 0 ]]; then
  printf 'R50_READ_FAILED %s\n' "$code"
  exit "$code"
fi

"$PY" -I -B - "$D" <<'PYTHON'
import json
import re
import sys
from collections import Counter
from pathlib import Path

path = Path(sys.argv[1])
reasons = {"eligible", "pool_off", "unsupported_backend", "no_ipv4",
           "unchecked", "check_failed", "stale_check", "outside_region"}
assert (path / "eu.txt").read_text().strip()
for label in ("configured", "eu"):
    data = json.loads((path / f"{label}.json").read_bytes())
    assert set(data) == {"mode", "region_policy", "regions", "found",
                         "eligible", "by_reason", "groups"}
    if label == "eu":
        assert data["region_policy"] == "strict" and data["regions"] == ["EU"]
    assert data["mode"] in {"off", "observe", "on"}
    grouped = Counter()
    for cell in data["groups"]:
        assert set(cell) == {"source", "reason", "country", "count"}
        assert cell["source"] in {"vpngate", "vpnbook", "igareck", "mahdibland"}
        assert cell["reason"] in reasons
        assert cell["country"] is None or re.fullmatch("[A-Z]{2}", cell["country"])
        assert type(cell["count"]) is int and cell["count"] > 0
        grouped[cell["reason"]] += cell["count"]
    assert dict(grouped) == data["by_reason"]
    assert sum(grouped.values()) == data["found"] and grouped["eligible"] == data["eligible"]
    print(json.dumps({key: value for key, value in data.items() if key != "groups"},
                     sort_keys=True))
print("R50_CANDIDATES_OK")
PYTHON
BASH
```

## Итог

- `R50_CANDIDATES=PASS` при зелёных контрактах, успешных обоих форматах, выполненных
  инвариантах подсчёта и совпавших снимках шлюза. Если оба снимка пусты,
  укажи `CACHE_EMPTY`. Ошибка чтения кеша имеет отдельный исход `CACHE_READ_FAILED`.
- Укажи количество пригодных и ведущие причины отказа для настроенной
  политики и строгого EU. Прогоны читают отдельные снимки, поэтому при
  фоновом обновлении каталога их размеры могут различаться. Не приписывай
  такое изменение региональному фильтру.
- Пригодность нового участника основана на сохранённой проверке за
  последние три часа. Число пригодных и число живых участников применённой
  конфигурации описывают разные факты. При `M3_DAY=NOT_RUN` в отчёте запиши, что
  суточный запуск по-прежнему зависит от реального использования пула.
- Опубликуй один обезличенный `docs/reports/<UTC>_freepool-r50-candidates.md` в ветке `docs/flash-proton-ui-manifest` при любом исходе.
  Включи SHA кода и ТЗ, ОС, контракты, агрегаты из скрипта и исход сверки.
  Оставь исходные кеши, адреса, идентификаторы, конфиги и журналы локально.
  При конфликте ветки перенеси только отчёт поверх её актуальной вершины.
