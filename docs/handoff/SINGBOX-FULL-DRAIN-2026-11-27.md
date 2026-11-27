# ThinkCentre · два полных окна дренирования sing-box

Ubuntu 24.04 LTS amd64. Кандидат `b5c85dde25d40150aed299fb061706ce6bdfbada`. Предыдущий прогон подтвердил переход blue → green через настоящий API Xray и закрытие старой сессии после принудительного истечения срока. Этот проход проверяет два штатных окна по 300 секунд и повторное использование слота blue. Заложить около 15 минут. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/f91d1f879c99159c0044a1afb5a0aa1befca22df/docs/reports/2026-11-27T194137Z_singbox-real-api-handoff.md)

Flash сама выполняет команды, фиксирует результаты и публикует один обезличенный отчёт при любом исходе. При недоступности терминала или GitHub запросить доступ и выполнить доступные этапы. Сценарий запускается обычным пользователем в приватном префиксе. Все тестовые соединения на loopback. Для sing-box и Xray использовать уже установленные бинарники. При необходимости задать абсолютные пути `XGW_TEST_SINGBOX`, `XGW_TEST_XRAY` и `XGW_TEST_PYTHON` с pytest.

## 1. Команды

Из полного клона XGW выполнить блок. Путь в `PRIVATE_ARTIFACTS` указывает на локальные журналы и распакованный кандидат. Общее ограничение времени сценария с процессами — 700 секунд.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=b5c85dde25d40150aed299fb061706ce6bdfbada
BUNDLE=docs/handoff/artifacts/xgw-singbox-full-drain.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'f9cdc585b1f2231e16425fd584c1dc00a75d31330321732bd3328a5bfa1240c5' "$D/code.bundle" | sha256sum --check --status -
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
run REGRESSIONS pytest_run tests/test_singbox_generations.py tests/test_standalone_topology.py \
    tests/test_desync_standalone.py tests/test_singbox.py tests/test_runtime.py \
    tests/test_standalone_cdn_compare.py tests/test_dualcore.py
run WATCHDOG pytest_run tests/test_daemon.py -k 'background_build or pending_singbox_resume'
tail -n 14 "$D/REGRESSIONS.log" "$D/WATCHDOG.log"

if [[ -x "$SINGBOX" && -x "$XRAY" ]] &&
   timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1 &&
   timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1; then
    run FULL_DRAIN timeout -k 10 700 "$TEST_PY" -B -P -m docs.helpers.singbox_loopback_handoff \
        --full-drain "$D/lab/handoff" "$XRAY" "$SINGBOX"
    grep -E '^(HANDOFF_[A-Z_]+|BLUE_DRAIN_[A-Z_]+|GREEN_DRAIN_[A-Z_]+|RETURN_BLUE_PATH|FULL_DRAIN)=PASS( |$)' "$D/FULL_DRAIN.log" || true
else
    echo 'FULL_DRAIN=NOT_RUN core unavailable' | tee -a "$D/status"
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

| Метка | Критерий и свидетельство |
| --- | --- |
| `COMPILE`, `REGRESSIONS`, `WATCHDOG` | Указать код завершения, число пройденных, упавших и пропущенных тестов, а при сбое — фазу и обезличенную причину. Для контракта отсчёта значение в последние 0,25 с округляется до 1, на дедлайне — 0. |
| `HANDOFF_BLUE_PATH`, `HANDOFF_MEASUREMENT_CONTEXT`, `HANDOFF_GREEN_PATH` | Старое соединение атрибутировано blue. API сохраняет запуск Xray и переводит новые соединения на green. Сменяются порт и ключ контекста того же моста. |
| `BLUE_DRAIN_GRACE`, `BLUE_DRAIN_CLEANUP` | Штатный дедлайн первого перехода составляет 300 с без изменения часов или файла состояния. До срока старый и новый потоки регулярно обмениваются байтами. Первый сокет остаётся в blue и подготовка третьего поколения недоступна. В последнюю долю секунды статус показывает 1. После дедлайна путь восстановления останавливает blue, старая сессия закрывается, green отвечает. Привести число выборок. |
| `RETURN_BLUE_PATH` | После завершения blue используется повторно с новым запуском и портом. Xray сохраняет запуск, обновлённый ключ контекста отличается от обоих прежних. Одновременно подтверждены новый сокет в blue и прежний сокет в green. |
| `GREEN_DRAIN_GRACE`, `GREEN_DRAIN_CLEANUP` | Второе штатное окно длится 300 с. До срока сокет green и открытый поток в blue отвечают, в последнюю долю секунды видна 1. После срока прежний поток закрыт, активный blue и Xray продолжают работать. Привести число выборок. |
| `FULL_DRAIN`, `HOST_FIELDS` | Для `FULL_DRAIN=PASS` нужны обе пары `GRACE` / `CLEANUP`, подтверждённый возврат к blue и сохранённый запуск Xray. `HOST_FIELDS` сравнивает `LoadState`, `ActiveState`, `MainPID` пяти штатных юнитов. При расхождении указать только категории полей и юниты. |

Стенд использует дочерние процессы и вызов штатного восстановления под общей блокировкой. Рабочий переход systemd-юнитов, внешний трафик и сутки отметить `NOT_RUN`. Если сценарий завершился раньше времени, записать последний подтверждённый этап, а оставшиеся пометить `NOT_RUN`. По окончании проверить, что временные дочерние процессы больше не работают. Хранить приватные материалы с закрытыми правами до публикации.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-full-drain.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report full ThinkCentre sing-box generation drain')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
