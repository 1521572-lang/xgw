# ThinkCentre · HTTPS через Xray до и после смены sing-box в стенде

Ubuntu 24.04 LTS amd64. Кандидат `487ff8b805730ed531d72da0132f1e99c5fd33e7`. Этап A рабочего ТЗ принят на ThinkCentre. Прошли 128 контрактов и один тест на установленном Xray 26.11.9, прямой HTTPS через green вернул HTTP 200 и 57 620 байт. Рабочему этапу B требуется согласованное окно. Здесь проверяется связка настоящих Xray, счётчика downlink и двух sing-box на временных процессах. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/2f466004e5a4a2c669cfb752f0a75a0bd25aeaa0/docs/reports/2026-11-28T060307Z_singbox-bridge-window.md)

Flash сама запускает стенд от обычного пользователя и публикует обезличенный отчёт при любом исходе. При недоступности терминала или GitHub запросить доступ. Стенд слушает только loopback, origin использует временный доверенный TLS-сертификат. Рабочие настройки и службы сверяются чтением. Запустить доступные фазы с установленными версиями ядер. При необходимости задать абсолютные пути `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON` с pytest.

## Команды

Из полного клона XGW выполнить блок. Путь из `PRIVATE_ARTIFACTS` сохранить локально. Требуется `openssl` для сертификата стенда.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=487ff8b805730ed531d72da0132f1e99c5fd33e7
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-https-isolated.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '82be098d0c3a3e7d230e39114a8a8d5f99132fd73ff4c61e1da52796a0649b64' "$D/code.bundle" | sha256sum --check --status -
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
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q src/xgw/apply docs/helpers/singbox_loopback_handoff.py
pytest_run() {
    timeout -k 5 240 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --color=no -q -rs -rfE --tb=short --show-capture=no "$@"
}
run CONTRACTS pytest_run tests/test_singbox_generations.py -k probe_bridge
tail -n 14 "$D/CONTRACTS.log"

if [[ -x $SINGBOX && -x $XRAY ]] &&
   timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1 &&
   timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1; then
    SINGBOX=$(readlink -f "$SINGBOX")
    XRAY=$(readlink -f "$XRAY")
    if command -v openssl >/dev/null; then
        run HTTPS_ISOLATED timeout -k 5 90 "$TEST_PY" -B -P \
            -m docs.helpers.singbox_loopback_handoff "$D/lab/https" "$XRAY" "$SINGBOX" --https-proof
        grep -E '^(HTTPS_|HANDOFF_)' "$D/HTTPS_ISOLATED.log" || true
    else
        echo 'HTTPS_ISOLATED=NOT_RUN openssl unavailable' | tee -a "$D/status"
    fi
    run CONTROL timeout -k 5 70 "$TEST_PY" -B -P -m docs.helpers.singbox_loopback_handoff \
        "$D/lab/control" "$XRAY" "$SINGBOX"
    grep -E '^HANDOFF_' "$D/CONTROL.log" || true
else
    echo 'HTTPS_ISOLATED=NOT_RUN cores unavailable' | tee -a "$D/status"
    echo 'CONTROL=NOT_RUN cores unavailable' | tee -a "$D/status"
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

## Критерии

| Метка | Критерий |
| --- | --- |
| `COMPILE`, `CONTRACTS` | Код завершения, число контрактов и первый сбой. |
| `HTTPS_BLUE`, `HTTPS_GREEN` | Проверка до и после применения через настоящий API Xray. В обеих фазах ожидается HTTP 200, ровно 49 152 байта тела и прирост downlink выбранного SOCKS-выхода не меньше тела. |
| `HTTPS_BYPASS_REJECTED` | Стенд меняет только правило в памяти выделенного Xray и возвращает его сразу после пробы. HTTP 200 и 49 152 байта должны сопровождаться нулевым приростом счётчика моста и отказом `xray_traffic_unconfirmed`. |
| `HANDOFF_*` | Сверить путь до и после смены, измерительный контекст, исход старого сокета и очистку. В этом тесте дедлайн ускоряется только в состоянии стенда. |
| `CONTROL`, `HOST_FIELDS` | Прежний вызов стенда подтверждает прежний сценарий. Поля пяти штатных юнитов до и после должны совпасть. |

В отчёт включить метку и фазу первого сбоя. При наличии доступа к файлам шлюза сравнить их содержимое чтением, вывести только итог сравнения. Если доступ ограничен, достаточно сверки полей служб и пометки `HOST_FILES=NOT_RUN`. Смена рабочих слотов, клиентский LAN и рабочее окно имеют самостоятельный критерий. Этап B возобновить в согласованное окно по его инструкции. [ТЗ рабочего окна](https://github.com/1521572-lang/xgw/blob/32b8ab7848af5b1af18e910fe29f83678d76e6c2/docs/handoff/SINGBOX-BRIDGE-WINDOW-2026-11-28.md)

## Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest, Xray и sing-box, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-bridge-https-isolated.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre isolated HTTPS bridge attribution')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
