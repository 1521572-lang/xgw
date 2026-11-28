# ThinkCentre · доли таймаутов FreePool по ядрам

Ubuntu 24.04 LTS amd64. Кандидат `71cc29b9ee7411bdf7c73b09471fb3b13ee889c6`. ThinkCentre принял 14 контрактов, архив по манифесту, установку в тестовый префикс и схему записи фаз. Рабочее обновление ожидает согласованного окна. Пока доступен рабочий кеш, получить для каждого ядра число проверенных вариантов, число таймаутов и число известных фаз. Эти показатели нужны, чтобы оценить долю таймаутов в сохранённых результатах. [Отчёт о приёмке поставки](https://github.com/1521572-lang/xgw/blob/23117b0c01ec55fe8d5152ea83d762ba310a29bb/docs/reports/2026-11-28T100833Z_freepool-r50-writer-acceptance.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. Если нет доступа к терминалу или sudo для чтения, запросить его и выполнить доступные этапы. На ThinkCentre кандидат читает рабочий кеш. Контракты используют временный префикс.

## Команды

Из полного клона XGW выполнить блок. Для pytest можно выбрать интерпретатор через `XGW_TEST_PYTHON`. Если уже известно время запуска согласованного обновления писателя фаз, задать `XGW_FREEPOOL_SINCE` в секундах Unix. Будет добавлено отдельное окно после обновления.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=71cc29b9ee7411bdf7c73b09471fb3b13ee889c6
BUNDLE=docs/handoff/artifacts/xgw-freepool-r50-backend-coverage.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '606e3b02d73ded5d797a8f4427396564acb2f650a4fe500f9cb8507f97506b2a' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
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

host_settings() {
    sudo -n /usr/bin/timeout -k 2 8 /usr/bin/sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

pool_digest() {
    sudo -n /usr/bin/timeout -k 2 20 /usr/bin/python3 -I -B - <<'PY'
from hashlib import file_digest
from pathlib import Path

root = Path("/var/lib/xgw/freepool")
for path in [root / "candidates.json", *sorted((root / "snapshots").glob("*.json"))]:
    try:
        with path.open("rb") as file:
            checksum = file_digest(file, "sha256").hexdigest()
    except FileNotFoundError:
        checksum = "ABSENT"
    print(path.name, checksum)
PY
}

classify() {
    local label=$1
    shift
    if "$@" >"$D/$label.before" 2>"$D/$label.before.err"; then
        return 0
    fi
    return 1
}

compare() {
    local label=$1 before=$2
    shift 2
    if "$@" >"$D/$label.after" 2>"$D/$label.after.err" && [[ $before == 0 ]]; then
        if cmp -s "$D/$label.before" "$D/$label.after"; then
            printf '%s=MATCH\n' "$label"
        else
            printf '%s=DRIFT\n' "$label"
        fi
    else
        printf '%s=UNKNOWN\n' "$label"
    fi
}

candidate() {
    sudo -n /usr/bin/timeout -k 2 35 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw pool candidates --explain --json "$@"
}

run CONTRACTS timeout -k 4 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_freepool_candidates.py tests/test_freepool_sources.py
tail -n 12 "$D/CONTRACTS.log"

fields_before=0
classify HOST_FIELDS host_fields || fields_before=$?
if sudo -n true 2>/dev/null; then
    settings_before=0 pool_before=0
    classify HOST_SETTINGS host_settings || settings_before=$?
    classify POOL_CACHE pool_digest || pool_before=$?
    now=$(date -u +%s)
    run ORIGINAL candidate
    run ALL_CACHED candidate --checked-since 1
    run LAST_24H candidate --checked-since "$((now - 86400))"
    run LAST_3H candidate --checked-since "$((now - 10800))"
    if [[ -v XGW_FREEPOOL_SINCE ]]; then run SINCE_UPDATE candidate --checked-since "$XGW_FREEPOOL_SINCE"; fi
    compare HOST_SETTINGS "$settings_before" host_settings | tee -a "$D/status"
    compare POOL_CACHE "$pool_before" pool_digest | tee -a "$D/status"
    run VERIFY /usr/bin/python3 -I -B - "$D" <<'PY'
from collections import Counter
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
status = dict(row.strip().split("=", 1) for row in (root / "status").read_text().splitlines()
              if "=" in row)
totals = {}
for name in ("ORIGINAL", "ALL_CACHED", "LAST_24H", "LAST_3H", "SINCE_UPDATE"):
    if status.get(name) != "0":
        continue
    row = json.loads((root / (name + ".log")).read_text())
    if name == "ORIGINAL":
        assert "check_window" not in row
        print(json.dumps({"case": name, "mode": row["mode"], "found": row["found"]}))
        continue
    window = row["check_window"]
    expected_timeouts, expected_known = Counter(), Counter()
    for group in window["timeout_groups"]:
        expected_timeouts[group["backend"]] += group["count"]
        if group["phase"] != "unknown":
            expected_known[group["backend"]] += group["count"]
    backend_rows = window["by_backend"]
    observed = {entry["backend"]: entry for entry in backend_rows}
    assert len(observed) == len(backend_rows)
    assert expected_timeouts.keys() <= observed.keys()
    for backend, entry in observed.items():
        assert entry["timeouts"] == expected_timeouts[backend]
        assert entry["known_phase_timeouts"] == expected_known[backend]
        assert 0 <= entry["known_phase_timeouts"] <= entry["timeouts"] <= entry["checked"]
        assert 0 <= entry["schema_records"] <= entry["checked"]
    for key in ("checked", "timeouts", "schema_records"):
        assert sum(entry[key] for entry in backend_rows) == window[key]

    totals[name] = observed
    print(json.dumps({"case": name, "mode": row["mode"], **window}, ensure_ascii=False))

fixed = ("ALL_CACHED", "LAST_24H", "LAST_3H")
if (status.get("POOL_CACHE") == "MATCH" and status.get("HOST_SETTINGS") == "MATCH"
        and all(name in totals for name in fixed)):
    for outer, inner in (("ALL_CACHED", "LAST_24H"), ("LAST_24H", "LAST_3H")):
        for backend, entry in totals[inner].items():
            for key in ("checked", "timeouts", "known_phase_timeouts", "schema_records"):
                assert entry[key] <= totals[outer][backend][key]
    print("BACKEND_INVARIANTS=MATCH")
else:
    print("BACKEND_INVARIANTS=NOT_RUN input_drift_or_missing_output")
PY
    if grep -qx 'VERIFY=0' "$D/status"; then cat "$D/VERIFY.log"; fi
else
    echo 'LIVE=NOT_RUN sudo not available' | tee -a "$D/status"
fi
compare HOST_FIELDS "$fields_before" host_fields | tee -a "$D/status"
BASH
~~~

## Критерии

- `CONTRACTS` — количество тестов, пропуски и первый сбой. Проверяются записи на границах интервала, пустые группы, известная и неизвестная фаза, маркер схемы и отсутствие приватных данных.
- `ORIGINAL`, `ALL_CACHED`, `LAST_24H`, `LAST_3H`, при наличии `SINCE_UPDATE` — указать время отсечки, режим пула, число таймаутов из числа проверенных по каждому ядру, известные фазы и число записей текущей схемы. Это доля среди последних сохранённых результатов активного каталога. Для отсутствующего ядра указать отсутствие наблюдений.
- `VERIFY`, `BACKEND_INVARIANTS` — суммы по ядрам совпадают с общими счётчиками и группами фаз. Между окнами сравнивать вложенность только при совпавших снимках кеша и настроек.
- `HOST_FIELDS`, `HOST_SETTINGS`, `POOL_CACHE` — опубликовать результат сравнения. При естественном обновлении демоном указать категорию дрейфа без имени файла или его хэша.

При отсутствии свежих записей новой схемы оставить системную проверку писателя открытой. Когда рабочий демон будет обновлён в согласованное окно, пройти этап B принятого ТЗ поставки и повторить эту сводку с отсечкой по времени запуска. [Этап B FreePool](https://github.com/1521572-lang/xgw/blob/a09e6da1d0d029dab680af86a830331d132892f2/docs/handoff/FREEPOOL-R50-WRITER-ACCEPTANCE-2026-11-28.md#b-чтение-после-согласованного-рабочего-обновления)

## Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python и pytest, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_freepool-r50-backend-coverage.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre FreePool timeout coverage by backend')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
