# ThinkCentre · происхождение и фазы таймаутов FreePool R50

Ubuntu 24.04 LTS amd64. Кандидат `27ca37da9dfbe43d2cce846eb617909de324baa9`. На предыдущем проходе `--checked-since` принят. Из 303 проверенных вариантов за сутки 246 завершились таймаутом и у всех этап и фаза имели значение `unknown`. Нужно выяснить, отсутствуют ли поля в кеше, что умеет установленный на диске код и воспроизводятся ли таймауты с фазой отдельными процессами. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/3c0fa03d8a1b63fa1e71e9876610767c1d1957bc/docs/reports/2026-11-28T090101Z_freepool-r50-timeout-window.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. Если терминал или разрешённый sudo недоступны, запросить доступ. Контракты выполняются во временном корне. Контрольные пробы используют текущий настроенный HTTPS-адрес, до двух Xray и одного sing-box, только по публичным IPv4 из существующего каталога с недавним таймаутом. Дочерние ядра используют временные конфиги, результаты пишутся в одноразовый кеш. Для штатного шлюза предусмотрены чтение и сетевые пробы без установки, перезапуска и изменения настроек.

## Команды

Из полного клона XGW выполнить блок. Можно задать абсолютные пути `XGW_TEST_PYTHON`, `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX`. Использовать установленные ядра. `PRIVATE_ARTIFACTS` указывает на закрытые журналы.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=27ca37da9dfbe43d2cce846eb617909de324baa9
BUNDLE=docs/handoff/artifacts/xgw-freepool-r50-phase-sample.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'd69695dbfaeef1cf58dafc7d74b18ca55d735fe570632b26e1fe4b801779f0a9' "$D/code.bundle" | sha256sum --check --status -
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

probe_helper() {
    local seconds=$1
    shift
    sudo -n /usr/bin/timeout -k 5 "$seconds" /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD:$PWD/src" XGW_ROOT=/ \
        "XGW_XRAY_BIN=$XRAY" "XGW_SINGBOX_BIN=$SINGBOX" \
        /usr/bin/python3 -B -P -m docs.helpers.freepool_r50_phase_sample "$@"
}

installed() {
    local fields launched disk
    fields=$(timeout -k 2 8 systemctl show xgw.service -p ExecStart --value) || return 1
    if [[ $fields != *'path=/usr/local/bin/xgw ;'* ]] ||
       ! grep -Fq 'sys.path.insert(0, "/opt/xgw/lib")' /usr/local/bin/xgw; then
        echo 'STANDARD_LAUNCHER=UNKNOWN'
        return
    fi
    echo 'STANDARD_LAUNCHER=YES'
    launched=$(timeout -k 2 8 systemctl show xgw.service -p ExecMainStartTimestamp --value) ||
        return 1
    launched=$(date -d "$launched" +%s) || return 1
    disk=$(stat -c %Y /opt/xgw/lib/xgw/freepool/pool.py) || return 1
    if (( disk > launched )); then echo 'DISK_NEWER_THAN_DAEMON=YES'
    else echo 'DISK_NEWER_THAN_DAEMON=NO'; fi
}

run CONTRACTS timeout -k 4 180 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_freepool_candidates.py tests/test_freepool_targeted.py tests/test_checks.py \
    -k 'freepool or connect or tls_timeout'
tail -n 10 "$D/CONTRACTS.log"

fields_before=0
classify HOST_FIELDS host_fields || fields_before=$?
if sudo -n true 2>/dev/null; then
    settings_before=0 pool_before=0
    classify HOST_SETTINGS host_settings || settings_before=$?
    classify POOL_CACHE pool_digest || pool_before=$?
    run INSTALLED installed
    run RAW_METADATA probe_helper 30
    if grep -qx 'CONTRACTS=0' "$D/status" && grep -qx 'RAW_METADATA=0' "$D/status"; then
        mkdir -m 700 "$D/sample"
        run SAMPLE probe_helper 270 --sample "$D/sample"
    else
        echo 'SAMPLE=NOT_RUN preflight failed' | tee -a "$D/status"
    fi
    compare HOST_SETTINGS "$settings_before" host_settings | tee -a "$D/status"
    compare POOL_CACHE "$pool_before" pool_digest | tee -a "$D/status"
else
    echo 'HOST=NOT_RUN sudo unavailable' | tee -a "$D/status"
fi
compare HOST_FIELDS "$fields_before" host_fields | tee -a "$D/status"
BASH
~~~

## Критерии

| Метка | Результат |
| --- | --- |
| `CONTRACTS` | Число тестов и первый сбой. Локальный прокси принимает TCP и задерживает HTTP CONNECT. FreePool сохраняет `TIMEOUT / download / proxy_connect`. Прежняя классификация общей пробы остаётся `CONNECT_FAIL`. |
| `RAW_METADATA` | Число сохранённых таймаутов за сутки, количество записей без полей, с известной фазой и с полями без известной фазы. Привести статус `installed_writer_fields`. |
| `INSTALLED` | Привести категорию launcher и результат сравнения времени старта демона с временем файла на диске. Эти признаки помогают проверить версию, код работающего процесса по ним определить нельзя. При нестандартном unit путь установки считать неподтверждённым. |
| `SAMPLE` | Привести только агрегаты по ядру, вердикту, этапу, фазе и виду. Для `NOT_RUN` или неполного прохода указать причину. Повторно удачная проба означает, что старый таймаут сейчас не воспроизвёлся. Три пробы дают описание конкретных случаев. |
| `HOST_SETTINGS`, `POOL_CACHE`, `HOST_FIELDS` | Указать MATCH, DRIFT или UNKNOWN. Работающий демон может самостоятельно обновлять кеш в ходе прогона. При дрейфе сравнить приватные снимки и описать только категорию изменений. |

Сопоставить записи без полей с признаками установленного файла и результатами отдельной пробы. Таймаут `proxy_connect` локализует ожидание ответа CONNECT со стороны временного ядра. Причину задержки внутри его соединения с внешним сервером эта метка сама по себе не определяет. Публиковать обезличенный отчёт при любом исходе.

## Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest и использованных ядер, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_freepool-r50-phase-sample.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre FreePool phase sample')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
