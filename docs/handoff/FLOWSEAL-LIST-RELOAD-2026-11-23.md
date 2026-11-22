# ThinkCentre — обновление списков в изолированном zapret2, T03/T06/T10

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает готовые команды
и публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo или GitHub запроси доступ. Код подготовлен Codex.

На ThinkCentre анализ ранних пауз прошёл 52 контракта и все семь
HTTPS-сценариев. Повтор A7 дал `AUDIT_POS 2 3 2 2 true`.
Следующий этап проверяет поведение установленного zapret2 при
замене файлов, которые временный воркер читает из лабораторного
каталога. [Отчёт о ранних паузах](../reports/2026-11-22T224742Z_early-media-pauses.md)

По закреплённому исходнику SIGHUP заставляет заново прочитать списки.
Ошибка распаковки может завершить процесс с кодом 200. Если файл
невозможно открыть, движок сохраняет прежние данные в памяти.
Пустой положительный hostlist опасен при будущей публикации.
У движка при всех пустых include-списках проверка включения
пропускает любые имена, не попавшие в исключения. Это вывод из
исходника. Сценарий подтверждает загрузку пустого файла и реакцию
воркера, а проверка совпадения реального трафика идёт отдельным
этапом. [Код загрузки](../../third_party/zapret2/nfq2/hostlist.c) · [Обработка SIGHUP](../../third_party/zapret2/nfq2/nfqws.c)

## 1. Запуск на машине

В терминале ThinkCentre выполни `sudo -v`. Если pytest установлен
в отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
Запусти блок из рабочей копии XGW. Помощник проверит, что находится
в отдельном сетевом пространстве с одним loopback. Все сигналы
получают только его дочерние процессы с `--intercept=0`. Они
работают с синтетическими списками, используют отдельные каталоги
в `/run` и завершаются по ограниченному таймеру. Снимки состояния
рабочего шлюза снимаются до и после.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=0cb106cf40987a7d908bfe2de5511134e523edb3
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-reload.XXXXXXXX")
printf 'FLOWSEAL_RELOAD_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"

fib() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
}
fib >"$D/fib.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"

if timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest \
    --portable -o addopts= -p no:cacheprovider -q --tb=short \
    tests/test_desync_flowseal.py >"$D/contracts.out" 2>&1 &&
    grep -Eq '^10 passed in ' "$D/contracts.out"; then
  grep -E '^10 passed in ' "$D/contracts.out"
  printf 'FLOWSEAL_RELOAD_CONTRACTS_OK\n'
else
  printf 'FLOWSEAL_RELOAD_CONTRACTS_FAILED\n'
fi

LAB=$(sudo -n mktemp -d /run/xgw-list-reload.XXXXXXXX)
HOST_NETNS=$(stat -Lc %i /proc/self/ns/net)
printf 'ROOT_PRIVATE_ARTIFACTS %s\n' "$LAB"
lab_rc=0
git -C "$REPO" show "$CODE:docs/helpers/flowseal_reload_check.py" |
  sudo -n /usr/bin/timeout -k 3 75 /usr/bin/unshare --net "$PY" -I -B - \
    --out "$LAB" --host-netns "$HOST_NETNS" >"$D/lab.out" 2>"$D/lab.err" || lab_rc=$?
cat "$D/lab.out"
printf 'FLOWSEAL_RELOAD_LAB_EXIT %s\n' "$lab_rc"

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'FLOWSEAL_RELOAD_GATEWAY_UNCHANGED\n'
else
  printf 'FLOWSEAL_RELOAD_GATEWAY_CHANGED\n'
fi
BASH
~~~

## 2. Критерии и отчёт

| Случай | Что подтвердить |
|---|---|
| valid_repeat_rollback | Публикация проверенной копии, повтор, возврат исходной. Воркер загружает 3, 3 и 2 имени. Байты двух исключений совпадают. Жив тот же дочерний процесс. |
| blocked_staging | Отсутствующий, оборванный gzip, пустой, частичный и выходящий за область кандидат остановлены до замены. Исходный список имён и оба исключения прочитаны при следующем reload. |
| missing_active | Сигнал принят. В журнале маркер сохранения данных в памяти. После возврата файла прежние два имени читаются без смены процесса. |
| empty_active | Изолированный воркер принимает существующий пустой файл и остаётся жив. Число загруженных имён равно нулю. |
| corrupt_active_hostlist | Дочерний процесс завершается с кодом 200. Есть сигнатуры ошибки распаковки и fatal hostlists. |
| corrupt_active_ipset | Дочерний процесс завершается с кодом 200. Есть сигнатуры ошибки распаковки и fatal ipset. |

- Укажи ОС, версию ядра, SHA кодовой базы, результат десяти контрактов,
  шесть итогов и `FLOWSEAL_RELOAD_LAB_EXIT`. Если движок отличается
  от 1.0.7 / `038c97e` или недоступно отдельное сетевое пространство,
  укажи фазу блокировки. Сохрани результаты независимых проверок.
- Для ошибок старта укажи фазу и тип ошибки. Для диагностики просмотри
  `lab.err` или нужный `worker.log` из закрытых каталогов. Перенеси
  в отчёт краткую обезличенную причину и маркер.
- Укажи результат FIB, PID служб и сверку настроек. Испытание
  проверяет реакцию на локальные списки и не требует видео, packet
  capture или обновления рабочего ALT9. Сырые журналы, данные
  настроек и пути остаются на машине.

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
PUB=$(mktemp -d "$HOME/xgw-flowseal-list-reload-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_flowseal-list-reload.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Flowseal list reload behavior'
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
