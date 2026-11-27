# ThinkCentre · матрица регрессий Xray и sing-box

Ubuntu 24.04 LTS amd64. Кандидат `20069a0f1d08df7a0a01d57d0e5c69a276693f06`, контроль `a1513402062653683eb097d6f3c710d90afc9524`. В предыдущем проходе финальная выборка и статус sing-box прошли. В полной матрице было 205 PASS и семь одинаковых падений на двух ревизиях. Этот проход проверяет обновлённые тесты двух ядер и сохраняет прежние проверки рабочего статуса. [Отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/5ffc1b76075b0f27c7bcb3e8218807d74bf9973f/docs/reports/2026-11-27T175600Z_singbox-drain-deadline-status.md)

Flash сама выполняет запуски и публикует один обезличенный отчёт при любом исходе. При недоступности терминала, прав чтения или GitHub запросить нужный доступ и продолжить доступные этапы. Тесты работают в двух приватных деревьях. Состояние штатных служб сверяется системными чтениями. Изменения тестов выполняет Codex.

## 1. Команды

Использовать полный клон XGW. Если pytest установлен отдельно, перед запуском задать абсолютный путь `XGW_TEST_PYTHON`. Обе ревизии проверять одним Python. Сохранить приватный путь напечатанного каталога.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=20069a0f1d08df7a0a01d57d0e5c69a276693f06
BASE=a1513402062653683eb097d6f3c710d90afc9524
BUNDLE=docs/handoff/artifacts/xgw-dualcore-regression-matrix.bundle
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-dualcore.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nCONTROL %s\nOS %s\n' "$D" "$CODE" "$BASE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '24bc95c7813acd75777e013077ebfc78c8f90032c08cf908c87475b138416508' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
git -C "$REPO" merge-base --is-ancestor "$BASE" "$CODE"
for revision in "$BASE" "$CODE"; do
    mkdir "$D/$revision"
    git -C "$REPO" archive "$revision" src tests packaging docs/helpers pyproject.toml config.example.toml |
        tar -x -C "$D/$revision"
done
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
unset XGW_XRAY_BIN XGW_SINGBOX_BIN XGW_TEST_FREEPOOL_XRAY PYTHONOPTIMIZE

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

run_matrix() (
    local label=$1 revision=$2 rc=0
    shift 2
    cd "$D/$revision"
    export PYTHONPATH="$PWD:$PWD/src" XGW_ROOT="$D/$label-root"
    timeout -k 5 240 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
        --basetemp "$D/$label-tmp" --color=no -q -rs -rfE --tb=short --show-capture=no \
        --junitxml "$D/$label.xml" "$@" >"$D/$label.log" 2>&1 || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/status"
    tail -n 22 "$D/$label.log"
)

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
"$TEST_PY" --version

run_matrix CONTROL "$BASE" tests/test_dualcore.py -k \
    'pinned_to_xray or middle_of_a_trial or daily_recheck_returns or new_sing_box_config_waits or deferred_sing_box_config or when_nothing_answers or whole_probe_file'
run_matrix CANDIDATE "$CODE" tests/test_singbox_generations.py tests/test_standalone_topology.py \
    tests/test_desync_standalone.py tests/test_singbox.py tests/test_runtime.py \
    tests/test_standalone_cdn_compare.py tests/test_dualcore.py
run_matrix WATCHDOG "$CODE" tests/test_daemon.py -k 'background_build or pending_singbox_resume'

after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

## 2. Критерии

| Этап | Что проверить и зафиксировать |
| --- | --- |
| `CONTROL` | Семь выбранных прежних сценариев. Ожидаются семь assertion/fixture failures, как в предыдущем отчёте. Записать имена и фактический первый сбой. Ошибку среды или неполный сбор указать отдельно. |
| `CANDIDATE` | Полная матрица семи файлов. Указать passed/failed/skipped. Отдельно сверить исключение sing-box-only узла из новой сборки при закреплении за Xray, восстановление проб профиля, порядок очереди и выбор полного файла пробы. Оба сценария смены состава должны подтвердить сохранение исходных конфигов до проверки моста. Положительный сценарий должен применить состав после готовности, отрицательный — сохранить оба исходных файла. |
| `WATCHDOG` | Проверки фоновой сборки, устаревших входов и штатного возврата через отдельное поколение. |
| `HOST_FIELDS` | Итог сопоставления LoadState, ActiveState и MainPID пяти штатных юнитов. Публиковать только категории различий. Рабочее переключение, прямой CDN и сутки остаются `NOT_RUN`. |

При неожиданном исходе сохранить приватные stdout, stderr и XML. В отчёте указать короткую причину и точный node ID. При техническом сбое среды повторить только затронутую фазу после устранения причины и записать оба исхода.

## 3. Автоматическая публикация

Сохранить один обезличенный Markdown с SHA задания и обеих ревизий, версиями Ubuntu, Python и pytest, UTC и исходами фаз. Адреса, PID, конфиги, полные логи, XML и локальные пути остаются на ThinkCentre. Задать абсолютный путь отчёта в `REPORT_SRC`. Выполнить из клона также при частичном результате.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_dualcore-regression-matrix.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre dual-core regression matrix')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При отказе из-за прав записи запросить доступ и опубликовать тот же отчёт. Вернуть ссылку на коммит.
