# ThinkCentre · причины отсутствия рабочего моста sing-box

Ubuntu 24.04 LTS amd64. Кандидат `f59d5798ee41573f79732c350c9fd2cbbae2fcb3`. В предыдущем прогоне `preview` вернул `no_active_bridge` при нуле портов моста в текущем конфиге Xray. Совпали контрольные файлы и поля служб, прошли 109 контрактов. Этот ранний отказ происходил до опроса процессов и свободного слота. Теперь команда отдельно показывает число мостов в sing-box и Xray, режим ядра, агрегаты последнего сохранённого списка подписок и признак завершения проверок запуска. [Предыдущий отчёт](https://github.com/1521572-lang/xgw/blob/1c1f0f7c0bdd7e24db5ea29d5220978af4be5a0d/docs/reports/2026-11-28T020241Z_singbox-rotation-preview.md)

Flash сама выполняет команды и публикует обезличенный отчёт при любом исходе. При недоступности терминала или разрешённого sudo запросить доступ. Контракты используют временный `XGW_ROOT`, а `PREVIEW` читает рабочие файлы с явно заданным `XGW_ROOT=/`. Работа с реальным шлюзом в этом задании ограничена чтением. Ручной отказ `rotate` проверяется в контрактах с подставными службами.

## 1. Команды

Из полного клона XGW выполнить блок. Для контрактов можно задать `XGW_TEST_PYTHON` с pytest. `PRIVATE_ARTIFACTS` указывает на закрытые журналы. До и после просмотра сверяются поля служб и содержимое файлов, включая сохранённый список подписок.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=f59d5798ee41573f79732c350c9fd2cbbae2fcb3
BUNDLE=docs/handoff/artifacts/xgw-singbox-bridge-admission.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '2b41bc01e0a03d367e14ac1de29e4eb26ba28073fdcf433e8c1c28f330e40572' "$D/code.bundle" | sha256sum --check --status -
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
    files_after=0
    host_files >"$D/files.after" 2>"$D/files.after.err" || files_after=$?
    if [[ $files_before == 0 && $files_after == 0 ]]; then
        if cmp -s "$D/files.before" "$D/files.after"; then echo HOST_FILES=MATCH; else echo HOST_FILES=DRIFT; fi
    else
        echo HOST_FILES=UNKNOWN
    fi
else
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
| `CONTRACTS` | Число тестов, пропуски и первый сбой. При нуле рабочих мостов ручная команда отказывает до запуска кандидата и очистки поколений. Контракты также подтверждают отказ при устаревшем снимке и сохранение фонового пути подготовки. |
| `PREVIEW` | Привести `active`, `candidate`, `ready`, `reason`, `bridge_ports`, `configured_bridge_ports`, `runtime_checked`. При `no_active_bridge` ожидается `runtime_checked=false`, код 1. При готовом плане ожидаются код 0, `ready=true` и `runtime_checked=true`. |
| Инвентарь при `no_active_bridge` | Привести `core_mode` и только числовые категории `subscription_inventory`. `xray`, `singbox` и `dual` обозначают сохранённые сведения о совместимости. Среди поддерживающих sing-box отдельно выделены отключённые, закреплённые за Xray и исключённые сохранённым фильтром. `null` означает отсутствующий либо нечитаемый список. Числа не подтверждают текущую доступность серверов. |
| `HOST_FIELDS`, `HOST_FILES` | Опубликовать MATCH, DRIFT или UNKNOWN. При расхождении указать категорию поля или файла. Идентификаторы запусков, хэши, названия серверов и содержимое файлов оставить локально. |

Сопоставить найденное с будущим окном. Если в sing-box есть входы, а в Xray нет мостов, описать это по двум счётчикам. Если сохранённых совместимых узлов нет, указать отсутствие кандидата в наблюдаемом списке. Если они есть, указать их число как основание для будущего выбора при согласованной проверке. Настоящая проверка мостов, рабочая смена, физический LAN и внешний трафик имеют исход `NOT_RUN`.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-bridge-admission.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre bridge admission diagnosis')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
