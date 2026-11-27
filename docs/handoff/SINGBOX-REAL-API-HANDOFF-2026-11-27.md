# ThinkCentre · смена поколения sing-box через настоящий API Xray

Ubuntu 24.04 LTS amd64. Кандидат `aef4a27b7831b39ec2c36b110c520ecf3302281c`. На предыдущем проходе два перезапуска кандидата были отклонены, а стабильный запуск прошёл подготовку. Прокси sing-box был настоящим, API Xray представлял тестовый объект. В этом ТЗ два sing-box и Xray работают отдельными процессами, а применение идёт через API выделенного Xray. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/eb7510c6cfe311eeb557f85d402f32eb2ffbfc9e/docs/reports/2026-11-27T191845Z_singbox-checked-run.md)

Flash сама выполняет команды и публикует один обезличенный отчёт при любом исходе. При недоступности терминала или GitHub запросить доступ и продолжить доступные этапы. Стенд с локальными адресами запускается обычным пользователем. Состояние пяти штатных юнитов сверяется чтением до и после запуска. Для установленного sing-box и Xray использовать имеющиеся версии. При необходимости задать абсолютные пути `XGW_TEST_SINGBOX`, `XGW_TEST_XRAY` и `XGW_TEST_PYTHON` с pytest.

## 1. Команды

Из полного клона XGW выполнить блок. Путь в `PRIVATE_ARTIFACTS` нужен для чтения приватных журналов.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=aef4a27b7831b39ec2c36b110c520ecf3302281c
BUNDLE=docs/handoff/artifacts/xgw-singbox-loopback-handoff.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'bd1d914d55d72fde94c1d7e222b07804606424a6fab77f1a2af67fd682859873' "$D/code.bundle" | sha256sum --check --status -
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
    run HANDOFF timeout -k 10 70 "$TEST_PY" -B -P -m docs.helpers.singbox_loopback_handoff \
        "$D/lab/handoff" "$XRAY" "$SINGBOX"
    grep -E '^HANDOFF_[A-Z_]+=(PASS|RETAINED|CLOSED|TIMEOUT)$' "$D/HANDOFF.log" || true
else
    echo 'HANDOFF=NOT_RUN core unavailable' | tee -a "$D/status"
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
| `HANDOFF_BLUE_PATH` | Реальный HTTP CONNECT до переключения проходит через старый мост. Снять идентичность сокета в процессе blue. При подготовке green текущий файл Xray по-прежнему указывает на прежний порт. |
| `HANDOFF_MEASUREMENT_CONTEXT` | При коммите через API Xray сохраняет свой запуск. Слот green становится активным, blue — завершающим. Из контекстов замера исчезает старый порт, а для того же ID появляется новый порт и новый ключ поколения. |
| `HANDOFF_GREEN_PATH` | Новое соединение получает байты. У отдельного процесса green есть установленный сокет этого моста. В конфиге Xray сохраняется тег выхода и меняется порт. |
| `HANDOFF_HELD` | `RETAINED` требует обмена байтами по прежней сессии и того же сокета в blue. Если видны EOF или TCP reset, указать `CLOSED` и считать сохранение потока до срока неподтверждённым. При таймауте указать `TIMEOUT`. |
| `HANDOFF_CLEANUP` и `HANDOFF_OLD_AFTER_CLEANUP` | До срока blue сохраняется. Для одного прохода дедлайн меняется в приватном файле состояния стенда, после чего используется штатный reap под общей блокировкой. blue остановлен, green и Xray сохраняют запуск, соединение green отвечает. Старая сессия показывает `CLOSED` либо `TIMEOUT` по фактическому наблюдению. |
| Регрессии и штатный шлюз | `COMPILE`, `REGRESSIONS`, `WATCHDOG` и `HOST_FIELDS`. Указать итоги и первый сбой по точному этапу. |

Процессы стенда стартуют как дочерние. Контракты отдельно проверяют systemd, полномочия служебной учётной записи и дедлайн. Живой переход рабочих юнитов, полная длительность drain и внешний трафик получают `NOT_RUN`. При любом сбое сохранить доступные результаты и пройти к публикации.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-real-api-handoff.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre sing-box handoff through the Xray API')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
