# ThinkCentre · недавние таймауты проверок FreePool R50

Ubuntu 24.04 LTS amd64. Кандидат `e560494320c8f8d619b4306dfd518463691b6781`. В предыдущей сводке 332 из 352 сохранённых отказов имели вердикт `TIMEOUT`, фазы в прежних записях отсутствовали. Новая команда `xgw pool candidates --checked-since UNIX` показывает последнюю сохранённую проверку каждого бесплатного варианта за выбранный интервал. Проверить, есть ли в текущем кеше недавние таймауты с известным этапом и фазой. [Предыдущая сводка R50](https://github.com/1521572-lang/xgw/blob/65d1b383757e530ec3f5b7426c550f87044c2fc8/docs/reports/2026-11-26T125249Z_freepool-r50-check-failures.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. При недоступности терминала или прав чтения запросить доступ. Стенд контрактов использует временный корень. На шлюзе команда читает кеш и настройки. Допустимы естественные обновления кеша работающим демоном. `PRIVATE_ARTIFACTS` содержит приватные журналы и идентификаторы снимка.

## Команды

Из полного клона XGW выполнить блок. Виртуальное окружение pytest можно выбрать через `XGW_TEST_PYTHON`, установленный бинарник для контракта отмены — через `XGW_TEST_XRAY`. Если есть известное время запуска установленного кода с записью фаз, дополнительно задать `XGW_FREEPOOL_SINCE` в секундах Unix. Это отдельное окно сравнения.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=e560494320c8f8d619b4306dfd518463691b6781
BUNDLE=docs/handoff/artifacts/xgw-freepool-r50-timeout-window.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'aaaf4a91df3dbc138a9efc8917b27872efbbb9bea0d2154ed03004f8e5fd77b3' "$D/code.bundle" | sha256sum --check --status -
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

xray_bin=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
if [[ -x $xray_bin ]]; then
    export XGW_TEST_FREEPOOL_XRAY
    XGW_TEST_FREEPOOL_XRAY=$(readlink -f "$xray_bin")
    run XRAY_VERSION timeout -k 2 8 "$XGW_TEST_FREEPOOL_XRAY" version
fi
run CONTRACTS timeout -k 4 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_freepool_candidates.py tests/test_freepool_sources.py \
    tests/test_freepool_targeted.py tests/test_freepool_cancel.py
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
    groups = window["timeout_groups"]
    assert sum(item["count"] for item in groups) == window["timeouts"] <= window["checked"]
    known = sum(item["count"] for item in groups if item["phase"] != "unknown")
    unknown = window["timeouts"] - known
    totals[name] = (window["checked"], window["timeouts"], known, unknown)
    print(json.dumps({"case": name, "mode": row["mode"], "known": known, "unknown": unknown,
                      **window}, ensure_ascii=False))

fixed = ("ALL_CACHED", "LAST_24H", "LAST_3H")
if status.get("POOL_CACHE") == "MATCH" and status.get("HOST_SETTINGS") == "MATCH":
    if all(name in totals for name in fixed):
        wide, day, recent = (totals[name] for name in fixed)
        assert all(a >= b >= c for a, b, c in zip(wide, day, recent, strict=True))
        print("WINDOW_INVARIANTS=MATCH")
    else:
        print("WINDOW_INVARIANTS=NOT_RUN missing_output")
else:
    print("WINDOW_INVARIANTS=NOT_RUN input_drift_or_unknown")
PY
    if grep -qx 'VERIFY=0' "$D/status"; then cat "$D/VERIFY.log"; fi
else
    echo 'LIVE=NOT_RUN sudo not available' | tee -a "$D/status"
fi
compare HOST_FIELDS "$fields_before" host_fields | tee -a "$D/status"
BASH
~~~

## Критерии отчёта

- `CONTRACTS`. Указать число тестов, первый сбой и пропуски. Контракты проверяют включение нижней границы, отсечение старых и будущих записей, отсутствие сырых данных и прежнюю форму вывода. Для контракта отмены указать версию установленного Xray, если он был доступен.
- `ORIGINAL`, `ALL_CACHED`, `LAST_24H`, `LAST_3H` и при наличии `SINCE_UPDATE`. Указать режим пула, границы, число проверенных вариантов, число таймаутов, распределение по ядру, этапу и фазе. `unknown` означает запись без известной фазы. Счётчики относятся к последнему сохранённому итогу на вариант.
- При `checked=0` записать отсутствие сохранённых недавних результатов. При `checked>0` и `timeouts=0` в этом окне нет сохранённых таймаутов. Если все недавние фазы неизвестны, уточнение причины потребует свежих записей установленного демона. Вывод `WINDOW_INVARIANTS=NOT_RUN` при изменении входов означает, что сравнение между окнами отложено до стабильного снимка.
- `HOST_FIELDS`, `HOST_SETTINGS`, `POOL_CACHE`. Указать совпадение, дрейф или недоступность. Если естественное обновление кеша выявлено, указать категорию файла без имени источника или хэша. Состояние и данные окна рабочего моста этим прогоном не проверяются.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_freepool-r50-timeout-window.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre FreePool timeout phases by age')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
