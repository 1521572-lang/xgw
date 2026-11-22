# ThinkCentre — ранние паузы тела HTTPS, T07/T09/T12

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает сценарий и
публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo или GitHub запроси доступ. Код и команды подготовлены
Codex.

A7 подтвердил 22 BAT, 10 контрактов, версию 1.0.7 и dry-run ALT9.
В опубликованной строке `AUDIT_POS` есть лишнее число по сравнению
с выводом закреплённого выражения. Повтори только этот короткий
контроль и перенеси сырую строку без ручного исправления.
[Отчёт A7](../reports/2026-11-22T223005Z_flowseal-a7-catalog.md)

## 1. Запуск

В терминале ThinkCentre выполни `sudo -v`. Если pytest находится в
отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
Если под рукой есть сохранённый приватный JSON из `experiment probe`,
укажи его абсолютный путь в `XGW_EARLY_PAUSE_RECORD`. Остальные
проверки выполняются и без этой записи.

Из имеющейся рабочей копии запусти блок. Код берётся из закреплённого
checkout. TLS-сервер слушает только loopback на временных портах.
Контроль A7 запускается с `--intercept=0` в отдельном сетевом
пространстве. Снимки FIB и настройки сверяются до и после.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=01816a5e9eb92cc2d0eec19e5ab3e0634c5e0d4b
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-early-pauses.XXXXXXXX")
printf 'EARLY_PAUSE_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir -p "$D/tree" "$D/results"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"

fib() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
}
fib >"$D/fib.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"

if timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    "$TEST_PY" -B -P -m pytest --portable -o addopts= -p no:cacheprovider \
    -q --tb=short tests/test_desync_experiment.py >"$D/contracts.out" 2>&1 &&
    grep -Eq '^52 passed in ' "$D/contracts.out"; then
  grep -E '^52 passed in ' "$D/contracts.out"
  printf 'EARLY_PAUSE_CONTRACTS_OK\n'
else
  printf 'EARLY_PAUSE_CONTRACTS_FAILED\n'
fi

lab_rc=0
timeout -k 3 75 "$PY" -B -P docs/helpers/early_media_pause_check.py \
  --out "$D/results" >"$D/lab.out" 2>"$D/lab.err" || lab_rc=$?
cat "$D/lab.out"
printf 'EARLY_PAUSE_LAB_EXIT %s\n' "$lab_rc"
if [[ -f "$D/results/flat_20k.json" ]]; then
  "$PY" -B -P -m xgw.desync.experiment analyze-pauses \
    --record "$D/results/flat_20k.json" | tee "$D/cli.json" || printf 'EARLY_PAUSE_CLI_FAILED\n'
fi

if [[ -v XGW_EARLY_PAUSE_RECORD ]]; then
  printf 'EARLY_PAUSE_SAVED_RECORD\n'
  "$PY" -B -P -m xgw.desync.experiment analyze-pauses \
    --record "$XGW_EARLY_PAUSE_RECORD" | tee "$D/saved.json" || printf 'EARLY_PAUSE_SAVED_FAILED\n'
else
  printf 'EARLY_PAUSE_SAVED_NOT_AVAILABLE\n'
fi

NF=/opt/xgw/zapret2/1.0.7/nfqws2
if [[ -x $NF ]] && timeout -k 2 5 "$NF" --version >"$D/nfq-version.out" 2>&1 &&
    grep -Eq '^github version v?1\.0\.7 \(038c97e[0-9a-f]*\) lua_compat_ver ' "$D/nfq-version.out"; then
  LUA='local s="ABCDE"; local p=resolve_pos(s,"unknown","2"); local z=resolve_pos(s,"unknown","2",true); print("AUDIT_POS",resolve_pos(s,"unknown","1"),p,z,#s:sub(1,p-1),resolve_pos(s,"unknown","99")==nil)'
  a7_rc=0
  sudo -n /usr/bin/timeout -k 2 15 unshare --net "$NF" --qnum=201 --intercept=0 \
    "--lua-init=$LUA" >"$D/a7-position.out" 2>&1 || a7_rc=$?
  printf 'A7_POSITION_EXIT %s\n' "$a7_rc"
  grep -E '^AUDIT_POS[[:space:]]' "$D/a7-position.out" || true
  if [[ $a7_rc == 0 ]] &&
      grep -Eq '^AUDIT_POS[[:space:]]+2[[:space:]]+3[[:space:]]+2[[:space:]]+2[[:space:]]+true[[:space:]]*$' "$D/a7-position.out"; then
    printf 'A7_POSITION_MATCH\n'
  else
    printf 'A7_POSITION_UNCONFIRMED\n'
  fi
else
  printf 'A7_POSITION_BUNDLE_UNAVAILABLE\n'
fi

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'EARLY_PAUSE_GATEWAY_UNCHANGED\n'
else
  printf 'EARLY_PAUSE_GATEWAY_CHANGED\n'
fi
BASH
~~~

## 2. Ожидаемые результаты

| Случай | HTTP | Код curl | Пауза |
|---|---:|---:|---|
| full | 200 | 0 | `NO_PAUSE`, принято 128 КиБ |
| flat_16k | 206 | 28 | 16 КиБ, пороги 3 и 5 с, `flat_at_end` |
| flat_20k | 206 | 28 | 20 КиБ, пороги 3 и 5 с, `flat_at_end` |
| resume_16k | 200 | 0 | 16 КиБ, только порог 3 с, `resumed` |
| resume_20k | 200 | 0 | 20 КиБ, пороги 3 и 5 с, `resumed` |
| short_20k | 200 | 0 | `NO_PAUSE`, короткое тело завершено |
| no_content | 204 | 0 | `NOT_APPLICABLE`, 0 байт |

- Маркер `A7_POSITION_MATCH` относится к проверке
  числовой позиции. Зафиксируй код выхода и точную строку
  `AUDIT_POS 2 3 2 2 true` при совпадении. Сохрани фактическую
  строку и маркер при расхождении.
- Для ранних пауз нужны `52 passed`, `EARLY_PAUSE_CASES 7/7`
  и `EARLY_PAUSE_LAB_EXIT 0`. Для каждого случая укажи HTTP, код
  curl, результат и наблюдавшиеся байты, длительность, пороги и исход
  паузы. Для `full`, `short_20k` и `no_content` явно запиши
  число ложных срабатываний.
- Для `flat_20k` сверь результат CLI с выводом сценария. Режим
  буферизации указан в `output_buffering`. У новой записи ожидается
  `disabled`. Длительность `observed_s` получена между первым и
  последним замером с тем же числом байтов, до наблюдения роста.
  Рост в последней точке старого замера может быть записью буфера
  при выходе. Отмечай его как `growth_at_exit`.
- Приведи исход анализа сохранённого JSON или
  `EARLY_PAUSE_SAVED_NOT_AVAILABLE`. Пауза отражает доставку тела
  до измерителя. Для этого прогона `playback=NOT_RUN`.
- Укажи версию ОС, SHA кода и результат сверки шлюза. В публичный
  отчёт перенеси только вывод по проверкам и агрегаты. Подписанные
  URL, адреса, локальные пути, сырые записи и настройки оставь на машине.

## 3. Публикация

Укажи абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-early-media-pauses-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_early-media-pauses.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre early media pause checks'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
