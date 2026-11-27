# ThinkCentre · смена поколения sing-box через временные юниты systemd

Ubuntu 24.04 LTS amd64. Кандидат `6099f949c99855833ad8501cce19681727b7fcb1`. Приняты восстановление после прерывания Xray и полное окно drain на дочерних процессах. В этом проходе sing-box запускает и останавливает менеджер systemd. Оба временных экземпляра используют рабочую учётную запись sing-box и правила песочницы из ревизии кандидата. Xray и источники тестовых данных отдельные, все адреса на loopback. [Последний отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/e45494363754dea244e39dd7c490f0131e7e1cb4/docs/reports/2026-11-27T210506Z_xray-apply-recovery.md)

Flash сама запускает команды и публикует один обезличенный отчёт при любом исходе. Сценарий с временными юнитами требует разрешённого sudo. При недоступности терминала или прав запросить доступ. При отсутствии sudo выполнить остальные фазы и отметить системную `NOT_RUN`. Рабочие службы и их процессы только читаются. Использовать установленные Xray и sing-box. При необходимости задать абсолютные пути `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX` и `XGW_TEST_PYTHON` с pytest.

## 1. Команды

Из полного клона XGW выполнить блок. `PRIVATE_ARTIFACTS` и `PRIVATE_SYSTEMD_ROOT` указывают на локальные материалы. `PRIVATE_UNITS` в журнале перечисляет два имени этого запуска. Стенд назначает им `Restart=no`, время работы до 420 секунд и отдельный лимит остановки. Общий лимит привилегированной команды 395 секунд перед прерыванием. Тестовые порты выбираются заново, сетевые настройки шлюза не меняются.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=6099f949c99855833ad8501cce19681727b7fcb1
BUNDLE=docs/handoff/artifacts/xgw-singbox-systemd-handoff.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'abc78e4324a81cc25a247050554b3197396fdffe7ec206a1738ce851f29b8367' "$D/code.bundle" | sha256sum --check --status -
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
run COMPILE env "PYTHONPYCACHEPREFIX=$D/pycache" "$TEST_PY" -m compileall -q src/xgw/apply src/xgw/xraycore docs/helpers/singbox_loopback_handoff.py docs/helpers/singbox_systemd_handoff.py
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
    run HANDOFF_CONTROL timeout -k 10 70 "$TEST_PY" -B -P \
        -m docs.helpers.singbox_loopback_handoff "$D/lab/control" "$XRAY" "$SINGBOX"
    grep -E '^HANDOFF_[A-Z_]+=(PASS|RETAINED|CLOSED|TIMEOUT)$' "$D/HANDOFF_CONTROL.log" || true
    if [[ ! -d /run/systemd/system ]] || ! getent passwd xgw-singbox >/dev/null ||
       ! getent group xgw-singbox >/dev/null; then
        echo 'SYSTEMD=NOT_RUN missing system manager or installed service identity' | tee -a "$D/status"
    elif ! sudo -n true 2>/dev/null; then
        echo 'SYSTEMD=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    else
        LAB_ROOT="/var/tmp/xgw-systemd-${D##*.}"
        printf 'PRIVATE_SYSTEMD_ROOT %s\n' "$LAB_ROOT"
        run SYSTEMD sudo -n /usr/bin/timeout -s INT -k 20 395 /usr/bin/env -i \
            PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD:$PWD/src" \
            /usr/bin/python3 -B -P -m docs.helpers.singbox_systemd_handoff \
            "$LAB_ROOT" "$XRAY" "$SINGBOX"
        grep -E '^SYSTEMD_[A-Z_]+=PASS( |$)' "$D/SYSTEMD.log" || true
    fi
else
    echo 'SYSTEMD=NOT_RUN missing core' | tee -a "$D/status"
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
| `SYSTEMD_BLUE_POLICY`, `SYSTEMD_GREEN_POLICY` | У каждого временного юнита есть `MainPID` и идентичность запуска. Проверка процесса видит рабочие UID/GID sing-box, пустые capabilities и `NoNewPrivs=1`. Менеджер systemd показывает `ProtectSystem=strict`, `ReadOnlyPaths` с `/run` и ожидаемые семейства адресов. Указать фазу, если реальная проверка прав недоступна. |
| `SYSTEMD_HANDOFF` | До подготовки старый поток возвращает маркер A. Green готов и проходит запрос через мост; до коммита файл Xray указывает на blue. После коммита API файл указывает на green, Xray сохраняет запуск, новый поток возвращает B, прежний продолжает возвращать A. Для обоих слотов источник разрешён их собственным конфигом. |
| `SYSTEMD_GRACE`, `SYSTEMD_REAP` | Штатное окно 300 секунд без подмены часов или значения в файле. Оба потока регулярно отвечают, слоты сохраняют свои запуски до срока. После срока штатный `recover` дожидается подтверждения остановки blue от systemd, старый поток закрывается и green отвечает. Указать число выборок. |
| `SYSTEMD_CLEAN` | Оба временных юнита удалены менеджером, `LoadState=not-found` и `MainPID=0` для обоих, Xray стенда завершён. При сбое сверить только имена из `PRIVATE_UNITS` и описать очистку. |
| `REGRESSIONS`, `WATCHDOG`, `APPLIER`, `API_REAL`, `HANDOFF_CONTROL`, `COMPILE`, `HOST_FIELDS` | Указать коды завершения, числа тестов и фазу первого сбоя. Для контроля показать новый путь, итог старого потока и очистку. Для пяти рабочих юнитов сверить `LoadState`, `ActiveState` и `MainPID`. |

Для `SYSTEMD=PASS` нужны код 0 и все метки системной фазы. Поведение автоматического перезапуска, переход штатных юнитов, физический LAN, внешний трафик и сутки остаются отдельной приёмкой. Если какая-либо фаза недоступна, запиши `NOT_RUN` с причиной и опубликуй результаты выполненных фаз.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-systemd-handoff.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre handoff across temporary systemd units')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
