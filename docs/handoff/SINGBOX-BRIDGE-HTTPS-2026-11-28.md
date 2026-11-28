# ThinkCentre · HTTPS через существующий вход sing-box

Ubuntu 24.04 LTS amd64. Кандидат `bc5642fcd853d18eef06dce961072d891033d4ef`. На `1a4e197` прошли 115 контрактов. Из пяти участников Xray найден один совместимый с обоими ядрами и с объявленным прямым входом sing-box. Файл активного green и 65 тегов Xray совпали с рабочим состоянием. Нужно проверить, проходит ли реальный HTTPS через этот уже запущенный вход. [Отчёт о кандидатах](https://github.com/1521572-lang/xgw/blob/06fe6ec6e8c226563fa14e0773a24b095f853930/docs/reports/2026-11-28T040304Z_singbox-bridge-candidates.md)

Flash сама выполняет команды и публикует обезличенный отчёт при любом исходе. При недоступности терминала или разрешённого sudo запросить доступ. На рабочем шлюзе запускается один ограниченный HTTPS GET к настроенному адресу пробы через существующий авторизованный loopback-вход. Установка, изменение настроек и переключение путей относятся к отдельному согласованному окну.

## 1. Команды

Из полного клона XGW выполнить блок. Для контрактов можно задать `XGW_TEST_PYTHON` с pytest. `PRIVATE_ARTIFACTS` указывает на закрытые журналы. До и после HTTPS-пробы сверяются поля служб и содержимое файлов, включая сохранённый список подписок.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=bc5642fcd853d18eef06dce961072d891033d4ef
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-https.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '54d8f700f62c28347a6ff41015942ad3a20eac0ac203a67f0f6af982dd309a45' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree" "$D/tmp"
git -C "$REPO" archive "$CODE" src tests packaging docs/helpers pyproject.toml config.example.toml |
    tar -x -C "$D/tree"
cd "$D/tree"

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

run CONTRACTS timeout -k 5 240 env "TMPDIR=$D/tmp" "PYTHONPATH=$PWD:$PWD/src:$PWD/tests" \
    "XGW_ROOT=$D/test-root" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
    --color=no -q -rs -rfE --tb=short --show-capture=no \
    tests/test_singbox_generations.py tests/test_dualcore.py
tail -n 14 "$D/CONTRACTS.log"

host_files() {
    sudo -n /usr/bin/timeout -k 2 12 /usr/bin/python3 -I -B - <<'PY'
from hashlib import sha256
from pathlib import Path

for name in (
    "/etc/xgw/config.toml",
    "/etc/xgw/panel.json",
    "/etc/xgw/xray/config.json",
    "/etc/xgw/sing-box/config.json",
    "/etc/xgw/sing-box/generation-blue.json",
    "/etc/xgw/sing-box/generation-green.json",
    "/run/xgw/singbox-generations.json",
    "/var/lib/xgw/inventory.json",
):
    try:
        print(sha256(Path(name).read_bytes()).hexdigest())
    except FileNotFoundError:
        print("absent")
PY
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
if sudo -n true 2>/dev/null; then
    files_before=0
    host_files >"$D/files.before" 2>"$D/files.before.err" || files_before=$?
    run PREVIEW sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw singbox preview
    if [[ $before == 0 && $files_before == 0 ]]; then
        run HTTPS sudo -n /usr/bin/timeout -k 2 105 /usr/bin/env -i \
            PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
            /usr/bin/python3 -B -P -m xgw singbox probe-bridge
    else
        echo 'HTTPS=NOT_RUN cannot verify initial host state' | tee -a "$D/status"
    fi
    run PREVIEW_AFTER sudo -n /usr/bin/timeout -k 2 55 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD/src" XGW_ROOT=/ \
        /usr/bin/python3 -B -P -m xgw singbox preview
    files_after=0
    host_files >"$D/files.after" 2>"$D/files.after.err" || files_after=$?
    if [[ $files_before == 0 && $files_after == 0 ]]; then
        if cmp -s "$D/files.before" "$D/files.after"; then echo HOST_FILES=MATCH; else echo HOST_FILES=DRIFT; fi
    else
        echo HOST_FILES=UNKNOWN
    fi
else
    echo 'HTTPS=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo 'PREVIEW=NOT_RUN sudo access unavailable' | tee -a "$D/status"
    echo HOST_FILES=UNKNOWN
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
| `CONTRACTS` | Число тестов и первый сбой. Контракты пробуют успешный HTTPS с заглушкой и проверяют отказ при смене процесса, неготовом состоянии и неподходящем входе. |
| `PREVIEW`, `PREVIEW_AFTER` | Сравнить `reason`, `active`, `candidate`, `bridge_ports` и `bridge_admission.prepared`. Исход предыдущего прогона — `no_active_bridge` при `prepared=1`. |
| `HTTPS` | Указать код команды и только `ok`, `attempted`, `reason`, `http_status`, `bytes`. PASS требует `ok=true`, ответа 2xx с телом и подтверждённого запуска активного слота. Для штатного адреса пробы ожидается HTTP 200 и 57 620 байт. При сетевом отказе записать его категорию. `attempted=false` означает, что проверка остановилась на предусловии. |
| `HOST_FIELDS`, `HOST_FILES` | Опубликовать MATCH, DRIFT или UNKNOWN. При расхождении указать тип поля или файла. Идентификаторы, хэши, названия, конфиги и журналы оставить в закрытом каталоге. |

Считать HTTPS через существующий вход подтверждённым при PASS, совпавших снимках и `MATCH` для обоих контролей. Успех даёт основание планировать подключение этого участника к Xray в согласованное окно. Если HTTPS завершился сетевым отказом, назвать этап и сохранить полный журнал локально. При нескольких кандидатах, несоответствии состояния или невозможности сверить шлюз остановиться. Публиковать один отчёт при любом исходе.

Для подключения моста к Xray, смены рабочих поколений, штатного HTTPS через Xray с подтверждённым участием моста и физического LAN указать `NOT_RUN`.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-bridge-https.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre HTTPS on existing sing-box bridge')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
