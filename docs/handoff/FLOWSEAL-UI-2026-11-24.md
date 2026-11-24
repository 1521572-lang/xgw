# ThinkCentre — исключения ALT9 в панели и Qt

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и публикует один
обезличенный отчёт при любом исходе. При недоступности терминала, sudo,
среды браузера или GitHub запроси доступ. Сценарии используют установленный
nfqws2 в отдельном netns и временную панель на демонстрационных данных.

В последнем отчёте закреплённая проверка остановилась на синтаксисе nftables.
С многострочным ruleset двигатель подтвердил все 18 решений, а HTTPS-тела
дошли во всех случаях. Скобки исправлены в репозитории. Следующий проход
проверяет ровно закреплённый код и добавленные формы редактирования
исключений ALT9. [Отчёт 18/18](../reports/2026-11-24T180802Z_flowseal-tls-match.md)

## 1. Запуск на ThinkCentre

Выполни `sudo -v`. Для отдельных виртуальных окружений укажи абсолютные
пути `XGW_TEST_PYTHON` для pytest, `XGW_WEB_PYTHON` для Selenium и
`XGW_QT_PYTHON` для pytest с PyQt6. Если нужен особый geckodriver,
укажи его в `XGW_GECKODRIVER`. Используй Firefox и Xvfb, уже применявшиеся
для P2.11. Запусти целиком из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=ff37134a3a581918a0475621fdbf0b2266860c24
REPO=$(git rev-parse --show-toplevel)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
WEB_PY=${XGW_WEB_PYTHON:-$TEST_PY}
QT_PY=${XGW_QT_PYTHON:-$TEST_PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-ui.XXXXXXXX")
printf 'PINNED %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml | tar -x -C "$D"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
export PYTHONPATH="$D:$D/src:$D/tests"

snapshot() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n timeout -k 3 60 /usr/bin/python3 -I -B - snapshot
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

sudo -n true
snapshot >"$D/state.before"
match_rc=0
(cd "$REPO" && bash "$D/docs/helpers/flowseal_policy_trial.sh" "$CODE") \
  >"$D/match.out" 2>"$D/match.err" || match_rc=$?
cat "$D/match.out"
printf 'FLOWSEAL_MATCH_EXIT %s\n' "$match_rc"
cd "$D"

contracts_rc=0
timeout -k 3 100 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
  -q --tb=short --portable tests/test_zapret2_panel.py tests/test_zapret2_management.py \
  >"$D/contracts.out" 2>&1 || contracts_rc=$?
tail -n 6 "$D/contracts.out"
printf 'FLOWSEAL_CONTRACTS_EXIT %s\n' "$contracts_rc"
if command -v node >/dev/null; then
  node_rc=0
  timeout -k 2 25 node --test tests/test_zapret2_web_refresh.cjs >"$D/node.out" 2>&1 || node_rc=$?
  tail -n 9 "$D/node.out"
  printf 'FLOWSEAL_NODE_EXIT %s\n' "$node_rc"
else
  printf 'FLOWSEAL_NODE_NOT_AVAILABLE\n'
fi

DRIVER=${XGW_GECKODRIVER:-}
if [[ -z $DRIVER ]]; then
  for candidate in /snap/bin/geckodriver /snap/bin/firefox.geckodriver; do
    if [[ -x $candidate ]]; then DRIVER=$candidate; break; fi
  done
fi
if [[ -z $DRIVER ]]; then DRIVER=$(command -v geckodriver || true); fi
if command -v xvfb-run >/dev/null && [[ -x $DRIVER && -x $WEB_PY ]] &&
   "$WEB_PY" -B -c 'import selenium'; then
  web_rc=0
  env -u WAYLAND_DISPLAY -u MOZ_HEADLESS -u MOZ_ENABLE_WAYLAND \
    timeout -k 5 145 xvfb-run -a "$WEB_PY" -B -P "$D/docs/helpers/flowseal_ui_firefox.py" \
    "$D" "$DRIVER" >"$D/web.out" 2>"$D/web.err" || web_rc=$?
  cat "$D/web.out"
  printf 'FLOWSEAL_WEB_EXIT %s\n' "$web_rc"
else
  printf 'FLOWSEAL_WEB_NOT_AVAILABLE\n'
fi

if [[ -x $QT_PY ]] && "$QT_PY" -B -c 'import PyQt6.QtWidgets, pytest'; then
  qt_rc=0
  QT_QPA_PLATFORM=offscreen timeout -k 3 60 "$QT_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider -q --tb=short \
    tests/test_gui_qt.py::test_alt9_settings_dialog_preserves_saved_exclusions_and_sends_intentional_clear \
    >"$D/qt.out" 2>&1 || qt_rc=$?
  tail -n 6 "$D/qt.out"
  printf 'FLOWSEAL_QT_EXIT %s\n' "$qt_rc"
else
  printf 'FLOWSEAL_QT_NOT_AVAILABLE\n'
fi

snapshot >"$D/state.after"
if cmp -s "$D/state.before" "$D/state.after"; then
  printf 'FLOWSEAL_UI_GATEWAY_UNCHANGED\n'
else
  printf 'FLOWSEAL_UI_GATEWAY_STATE_DIFFERED\n'
fi
BASH
~~~

## 2. Критерии

- Закреплённая лаборатория даёт `FLOWSEAL_POLICY_MATCH 18/18`, нулевой код
  и `FLOWSEAL_POLICY_HTTPS_200`. При ошибке перенеси краткое обезличенное
  описание из `match.err` или указанного `lab.err`.
- Firefox сохраняет замену и пустой список. При неверном имени и конфликте
  ревизии остаются введённый черновик и прежние сохранённые настройки.
  В имитации Standalone поле доступно для чтения. Укажи четыре метки
  браузера и версию Firefox. Через vision просмотри `alt9-off.png` и
  `alt9-active.png`. Сверь, что название поля и подсказка читаемы, текст
  исключений виден, а активный режим отражён в интерфейсе. Скриншоты
  остаются в закрытом каталоге.
- Qt-тест подтверждает чтение, изменение, явную очистку и отсутствие записи
  из поля в режиме чтения. Укажи его код. При `NOT_AVAILABLE` запиши, какой
  зависимости не хватает.
- Снимки маршрутов, процессов и настроек рабочего шлюза совпадают.
  Записывай результаты обеих фаз независимо. Исходники и сценарии для
  этого прохода изменяет Codex.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`. Выполни блок
также при частичном результате. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-flowseal-ui-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_flowseal-ui.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Flowseal ALT9 exclusions in Web and Qt'
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
