# ThinkCentre · восстановление после прерванного применения Xray

Ubuntu 24.04 LTS amd64. Кандидат `6e7fac57a01139b89374b00a48fb7250a09308f5`. Прежняя проверка подтвердила три исхода отката при смене поколения sing-box. В этом проходе проверяется обычное применение Xray. После изменения маршрута через API стенд прерывает операцию до или сразу после записи конфига. Повтор с конфигом с диска должен назначить восстановление в окне и подтвердить фактический маршрут после запуска. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/5ee1d0f05e9829f3be95f431a6171d65cce63f92/docs/reports/2026-11-27T205248Z_xray-api-rollback.md)

Flash сама запускает команды и публикует один обезличенный отчёт при любом исходе. При недоступности терминала или GitHub запросить доступ и выполнить доступные этапы. Обычная учётная запись, новый приватный префикс, соединения на loopback. Штатные службы только читаются. Использовать установленные Xray и sing-box. При необходимости задать абсолютные пути `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON` с pytest.

## 1. Команды

Из полного клона XGW выполнить блок. `PRIVATE_ARTIFACTS` указывает на приватные журналы. Интервалы 12:00 и 03:15 в интеграционном тесте подаются в часы Applier, системные часы не меняются.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=6e7fac57a01139b89374b00a48fb7250a09308f5
BUNDLE=docs/handoff/artifacts/xgw-xray-apply-recovery.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '91487e706286cda55bd773dd724a1cb8401cab31ccb2c621b5654463a6be9b35' "$D/code.bundle" | sha256sum --check --status -
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
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q src/xgw/apply src/xgw/xraycore docs/helpers/singbox_loopback_handoff.py
pytest_run() {
    timeout -k 5 240 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --color=no -q -rs -rfE --tb=short --show-capture=no "$@"
}
run REGRESSIONS pytest_run tests/test_singbox_generations.py tests/test_standalone_topology.py \
    tests/test_desync_standalone.py tests/test_singbox.py tests/test_runtime.py \
    tests/test_standalone_cdn_compare.py tests/test_dualcore.py
run WATCHDOG pytest_run tests/test_daemon.py -k 'background_build or pending_singbox_resume'
run APPLIER pytest_run tests/test_applier.py
tail -n 14 "$D/REGRESSIONS.log" "$D/WATCHDOG.log" "$D/APPLIER.log"

have_xray=0
if [[ -x "$XRAY" ]] && timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1; then
    have_xray=1
    XGW_XRAY_BIN="$XRAY" run API_REAL pytest_run -v tests/test_api_integration.py
    tail -n 14 "$D/API_REAL.log"
else
    echo 'API_REAL=NOT_RUN missing Xray' | tee -a "$D/status"
fi

if [[ $have_xray == 1 && -x "$SINGBOX" ]] &&
   timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1; then
    run ROLLBACK_CONTROL timeout -k 10 70 "$TEST_PY" -B -P \
        -m docs.helpers.singbox_loopback_handoff --rollback present \
        "$D/lab/rollback" "$XRAY" "$SINGBOX"
    grep -Fx "ROLLBACK_PRESENT=PASS" "$D/ROLLBACK_CONTROL.log" || true
    run HANDOFF_CONTROL timeout -k 10 70 "$TEST_PY" -B -P \
        -m docs.helpers.singbox_loopback_handoff "$D/lab/control" "$XRAY" "$SINGBOX"
    grep -E '^HANDOFF_[A-Z_]+=(PASS|RETAINED|CLOSED|TIMEOUT)$' "$D/HANDOFF_CONTROL.log" || true
else
    echo 'ROLLBACK_CONTROL=NOT_RUN missing core' | tee -a "$D/status"
    echo 'HANDOFF_CONTROL=NOT_RUN missing core' | tee -a "$D/status"
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

## 2. Что записать

| Метка | Критерий |
| --- | --- |
| `API_REAL / before_disk` | Новый HTTP CONNECT получает маркер B после записи API; на диске остаётся A, тот же Xray отвечает, маркер `api-dirty` сохранён. Повтор с A вне окна даёт `restart_deferred` и записывает отложенное применение. В окне новый процесс возвращает маркер A и очищает служебные файлы. |
| `API_REAL / after_disk` | Во время прерывания на диске уже B и новый CONNECT идёт через B. Остаётся `api-dirty`. Одинаковый конфиг B вне окна назначает восстановление. В окне новый процесс подтверждает B, маркер и отложенная заявка сняты, в last-good сохранился A. |
| `API_REAL / контракты API` | Добавление и снятие inbound/outbound, точные списки тегов, балансировщик и замена маршрута. Отдельно указать число тестов и результат каждого сценария прерывания. |
| `APPLIER` | Маркер создан до первого API-вызова и остаётся после прерывания между записью файла и запуском службы. При отказе запуска сохранённая предыдущая версия используется для отката. При окончательном отказе маркер остаётся. |
| `ROLLBACK_CONTROL`, `HANDOFF_CONTROL` | При оставшемся теге закрытие кандидата откладывается, прежний путь отвечает. Обычный переход подтверждает новый сокет и очистку предыдущего процесса после контролируемого окончания drain в приватном префиксе. |
| `COMPILE`, `REGRESSIONS`, `WATCHDOG`, `HOST_FIELDS` | Записать коды завершения, количество тестов, точную фазу первого сбоя. Сравнить `LoadState`, `ActiveState`, `MainPID` пяти штатных юнитов. |

Проверить, что дочерние процессы стенда завершились. Рабочие systemd-юниты, внешний трафик и сутки получают `NOT_RUN`. При блокере указать фактические выполненные этапы и опубликовать доступные результаты.

## 3. Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest, Xray и sing-box, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_xray-apply-recovery.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report recovery after interrupted Xray apply on ThinkCentre')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
