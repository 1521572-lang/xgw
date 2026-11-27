# ThinkCentre · подтверждение процесса sing-box после перезапуска

Ubuntu 24.04 LTS amd64. Кандидат `7927a8aa1118c5e049474fb46126c26d42076251`. R3 принял смену двух временных юнитов через настоящий API Xray и полное окно drain. Теперь проверяется, что подтверждение прав и процесса относится к конкретному запуску sing-box. При перезапуске того же слота старое подтверждение должно исчезнуть. [Отчёт R3](https://github.com/1521572-lang/xgw/blob/4087486ee014b8267de0e1425ec5e4eebaf23ff8/docs/reports/2026-11-27T230545Z_singbox-systemd-handoff-r3.md)

Flash сама выполняет команды и публикует один обезличенный отчёт при любом исходе. При недоступности терминала или разрешённого sudo запросить доступ. При блокере пройти доступные проверки и указать причину. Оба сценария запускают временные юниты в отдельной сети только с `lo` и перезапускают только временный green. Рабочие юниты только наблюдаются.

## 1. Команды

Из полного клона XGW выполнить блок. При нестандартном расположении ядер задать абсолютные `XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`. Для регрессий можно задать `XGW_TEST_PYTHON` с pytest. `PRIVATE_ARTIFACTS`, `PRIVATE_SYSTEMD_ROOT` и строка `PRIVATE_UNITS` в журнале указывают на временные ресурсы. Сценарии before и after используют отдельные пространства и каталоги.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=7927a8aa1118c5e049474fb46126c26d42076251
BUNDLE=docs/handoff/artifacts/xgw-singbox-systemd-identity.bundle
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '1d48560d79a656d4046fe6570719a01e011249cb3ff888c7d352d5adae33baf0' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
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

run REGRESSIONS timeout -k 5 240 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no tests/test_singbox_generations.py \
    tests/test_standalone_topology.py tests/test_desync_standalone.py tests/test_singbox.py \
    tests/test_runtime.py tests/test_standalone_cdn_compare.py tests/test_dualcore.py
tail -n 14 "$D/REGRESSIONS.log"

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
if [[ ! -x "$XRAY" || ! -x "$SINGBOX" ]] ||
   ! timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1 ||
   ! timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1; then
    echo 'SYSTEMD=NOT_RUN missing or non-executable core' | tee -a "$D/status"
elif [[ ! -d /run/systemd/system ]] || ! getent passwd xgw-singbox >/dev/null ||
     ! getent group xgw-singbox >/dev/null; then
    echo 'SYSTEMD=NOT_RUN missing system manager or installed service identity' | tee -a "$D/status"
elif [[ ! -x /usr/bin/unshare ]] || ! command -v ip >/dev/null; then
    echo 'SYSTEMD=NOT_RUN missing unshare or ip' | tee -a "$D/status"
elif ! sudo -n true 2>/dev/null; then
    echo 'SYSTEMD=NOT_RUN sudo access unavailable' | tee -a "$D/status"
else
    for phase in before after; do
        LAB_ROOT="/opt/xgw-systemd-${D##*.}-$phase"
        label="RESTART_${phase^^}"
        printf 'PRIVATE_SYSTEMD_ROOT %s %s\n' "$phase" "$LAB_ROOT"
        run "$label" sudo -n /usr/bin/timeout -s INT -k 20 80 /usr/bin/env -i \
            PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD:$PWD/src" \
            /usr/bin/python3 -B -P -m docs.helpers.singbox_systemd_handoff \
            "$LAB_ROOT" "$XRAY" "$SINGBOX" --restart-check "$phase"
        grep -E '^SYSTEMD_[A-Z_]+=PASS( |$)' "$D/$label.log" || true
        if [[ ! -e $LAB_ROOT && ! -L $LAB_ROOT ]]; then
            printf '%s_ROOT_ABSENT=YES\n' "$label"
        else
            printf '%s_ROOT_ABSENT=NO\n' "$label"
        fi
    done
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
| `REGRESSIONS` | Привести числа тестов и точный этап первого сбоя. Контракты проверяют исчезновение `identity_ok` при смене времени запуска с тем же PID, чтение старого формата состояния и восстановление после записи API. |
| `RESTART_BEFORE`, `SYSTEMD_RESTART_BEFORE` | Временный green прошёл подготовку и перезапущен с другим идентификатором запуска. XGW отклонил коммит через API, конфиг Xray не сменился, green снят. Старый и новый запросы через blue получают A, Xray сохранил процесс. |
| `RESTART_AFTER`, `SYSTEMD_RESTART_AFTER` | Green принят через API. `identity_ok=true` подтверждает прошедший проверку запуск. После перезапуска слота значение `null`, хотя новый запрос через green получает B. Старое соединение через blue продолжает получать A. Запуск Xray сохранён. |
| `SYSTEMD_CLEAN`, `SYSTEMD_ROOT_CLEAN`, `HOST_FIELDS` | В обоих опытах два временных юнита удалены, тестовые Xray завершены, оба каталога удалены. Для пяти рабочих юнитов сопоставить `LoadState`, `ActiveState` и `MainPID`. |

Зафиксировать оба исхода независимо, включая последнюю подтверждённую метку при сбое. Штатное 300-секундное окно принято в R3. Автоматический перезапуск политикой systemd, рабочее переключение, физический LAN и внешний трафик остаются отдельными этапами.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-systemd-identity.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre sing-box process identity after restart')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
