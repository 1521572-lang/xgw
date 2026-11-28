# ThinkCentre · повторная сверка обработчика Xray после HTTPS

Ubuntu 24.04 LTS amd64. Кандидат `ba1a968a63bef9ac8255752ed51d3954baebdcdd`. В прошлом стенде HTTPS прошёл через оба слота sing-box. Запрос HTTP 200 с нулевым приростом счётчика моста был отклонён. В новом проходе отдельный Xray удаляет обработчик после чтения подтверждённого прироста и проверка должна отклонить результат по повторному ответу API. Затем стенд восстанавливает обработчик и повторяет HTTPS. [Предыдущий отчёт моста](https://github.com/1521572-lang/xgw/blob/caa45a442d734ff421d03a07948314000969833e/docs/reports/2026-11-28T070107Z_singbox-bridge-handler-stability.md)

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
CODE=ba1a968a63bef9ac8255752ed51d3954baebdcdd
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-handler-stability.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'efef9abd9bc654daa5b2a6d8a6ff7a61e0a096cf28775b8c5f6d473ea93f8ec0' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/lab" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers third_party vpn_ui README.md pyproject.toml config.example.toml |
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
run CONTRACTS pytest_run tests/test_singbox_generations.py tests/test_dualcore.py tests/test_build_release.py
tail -n 14 "$D/CONTRACTS.log"

if [[ -x $SINGBOX && -x $XRAY ]] &&
   timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1 &&
   timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1; then
    SINGBOX=$(readlink -f "$SINGBOX")
    XRAY=$(readlink -f "$XRAY")
    export XGW_XRAY_BIN="$XRAY"
    run API_REAL pytest_run tests/test_api_integration.py::test_socks_bridge_matches_uses_real_handler_settings
    unset XGW_XRAY_BIN
    tail -n 8 "$D/API_REAL.log"
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
    echo 'API_REAL=NOT_RUN cores unavailable' | tee -a "$D/status"
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
| `COMPILE`, `CONTRACTS`, `API_REAL` | Код завершения, число контрактов и первый сбой. В `API_REAL` нужен один прошедший тест на установленном Xray. |
| `HTTPS_BLUE`, `HTTPS_GREEN` | Проверка до и после применения через настоящий API Xray. В обеих фазах ожидается HTTP 200, ровно 49 152 байта тела и прирост downlink выбранного SOCKS-выхода не меньше тела. |
| `HTTPS_BYPASS_REJECTED` | Стенд меняет только правило в памяти выделенного Xray и возвращает его сразу после пробы. HTTP 200 и 49 152 байта должны сопровождаться нулевым приростом счётчика моста и отказом `xray_traffic_unconfirmed`. |
| `HTTPS_HANDLER_CHANGE_REJECTED` | Стенд получает HTTP 200, 49 152 байта и достаточный прирост счётчика, затем снимает обработчик в своём Xray. Повторная сверка API возвращает `xray_bridge_changed`. |
| `HTTPS_HANDLER_RESTORED` | После возврата того же обработчика новый HTTPS снова проходит. |
| `HANDOFF_*` | Сверить путь до и после смены, измерительный контекст, исход старого сокета и очистку. В этом тесте дедлайн ускоряется только в состоянии стенда. |
| `CONTROL`, `HOST_FIELDS` | Прежний вызов стенда подтверждает прежний сценарий. Поля пяти штатных юнитов до и после должны совпасть. |

В отчёт включить метку и фазу первого сбоя. При наличии доступа к файлам шлюза сравнить их содержимое чтением, вывести только итог сравнения. Если доступ ограничен, достаточно сверки полей служб и пометки `HOST_FILES=NOT_RUN`. Оба настоящих ядра запускаются только в стенде. Смена рабочих слотов, клиентский LAN и рабочее окно имеют самостоятельный критерий. Этап B возобновить в согласованное окно по его инструкции. [ТЗ рабочего окна](https://github.com/1521572-lang/xgw/blob/32b8ab7848af5b1af18e910fe29f83678d76e6c2/docs/handoff/SINGBOX-BRIDGE-WINDOW-2026-11-28.md)

Рабочий писатель FreePool остаётся в принятом этапе B для `6113fc7`. Выполнить его после согласованного обновления. [Этап B FreePool](https://github.com/1521572-lang/xgw/blob/66fc0e8f20a56ed7d7cabdf37acc0e26ed1d75d1/docs/handoff/FREEPOOL-R50-INSTALL-PREFLIGHT-2026-11-28.md#b-чтение-после-согласованного-обновления)

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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre Xray bridge handler stability')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
