# ThinkCentre — штатный запуск и визуальная сверка смены выхода, UI06 r3

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарий в графическом
сеансе и автоматически публикует один обезличенный отчёт при любом
исходе. При недоступности терминала, sudo, GUI, сеанса XGW или GitHub
запроси доступ. Код и команды подготовил Codex.

В UI06 r2 оба порядка Qt-тестов прошли по 2/2. Штатная команда
остановилась на импорте соседнего модуля при запуске с `-P`.
При повторном запуске с каталогом помощников в PYTHONPATH
подтверждены смена страны и публичного IP, возврат исходного IP,
совпадение PID и настроек, снятие таймера. Новый маркер на
единственном снимке после закрепления оказался плохо различим.
[Отчёт UI06 r2](../reports/2026-11-21T215719Z_gui-map-switch.md)

UI06 r3 проверяет штатную команду через `--help` ещё до живых
проверок. При переключении фиксируются разные позиции панорамы,
после её завершения сохраняются два кадра с различными фазами
пульса. Настройки установленного GUI сценарий не меняет.

## 1. Общий прогон

Выполни блок от вошедшего пользователя рабочего стола. Если Qt и
pytest в отдельном окружении, выставь абсолютный `XGW_GUI_TEST_PYTHON`.
Блок сначала проверяет импорт штатной командой и запускает оба
порядка тестов на копии установленного GUI.

Для одного повторного переключения используй интервал, который
владелец согласовал для краткой смены общего VPN-выхода. Запускай
из локального терминала ThinkCentre. В это время другие операторы
не меняют pin. Для согласованного окна экспортируй
`XGW_MAP_SWITCH_WINDOW=1`, выполни `sudo -v` и запусти блок.
Если согласованного окна нет, выполни первый этап и отметь
`MAP_SWITCH_NOT_RUN`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=87f78d2076cea495cdee7bf6ee23c2133a30e367
BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
GUI="/opt/xgw/gui/releases/$BASE"
PY=${XGW_GUI_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import pytest, PyQt6.QtWidgets, PyQt6.QtSvg'
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git cat-file -e "$BASE^{commit}" || git fetch origin "$BASE"
test -r "$GUI/vpn_ui/main_xgw.py"
D=$(mktemp -d "$HOME/xgw-map-switch.XXXXXXXX")
cp -R "$GUI/vpn_ui" "$GUI/src" "$D/"
git archive "$CODE" vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py \
  src/xgw/gui/client.py docs/helpers/gui_map_visibility.py docs/helpers/gui_map_switch.py \
  tests/test_vpn_ui_map_visibility.py | tar -x -C "$D"
git archive "$BASE" tests/test_vpn_ui_xgw.py tests/fixtures/gui/state-work.json |
  tar -x -C "$D"
mkdir -m 0700 "$D/qt-config"
printf 'PINNED %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$D"
export PYTHONPATH="$D:$D/src" XGW_UI_QT=PyQt6 XDG_CONFIG_HOME="$D/qt-config"
cd "$D"
MAP_ENTRY=(env "PYTHONPATH=$D/docs/helpers:$PYTHONPATH" \
  "$PY" -B -P "$D/docs/helpers/gui_map_switch.py")
"${MAP_ENTRY[@]}" --help >/dev/null
printf 'MAP_ENTRY_OK\n'
for first in tests/test_vpn_ui_map_visibility.py tests/test_vpn_ui_xgw.py; do
  second=tests/test_vpn_ui_xgw.py
  if [[ $first == "$second" ]]; then second=tests/test_vpn_ui_map_visibility.py; fi
  QT_QPA_PLATFORM=offscreen timeout -k 3 45 "$PY" -B -P -m pytest -p no:cacheprovider -q \
    "$first" "$second" -k 'map_'
done
printf 'MAP_CONTRACT_ORDERS_OK\n'
if [[ ${XGW_MAP_SWITCH_WINDOW:-0} != 1 ]]; then
  printf 'MAP_SWITCH_NOT_RUN no_maintenance_window\n'
  exit 0
fi
[[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]
sudo -n true
exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
[[ -z $(systemctl list-units --type=timer --state=active --no-legend 'xgw-map-return-*.timer') ]]
services() {
  local unit pid
  for unit in xgw.service xgw-xray.service; do
    pid=$(systemctl show "$unit" -p MainPID --value) || return 2
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done
}
before=$(services)
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.sha256"
rc=0
timeout -k 5 255 "${MAP_ENTRY[@]}" "$D" --maintenance-window || rc=$?
after=$(services)
[[ $after == "$before" ]]
sudo -n sha256sum --check --status "$D/settings.sha256"
printf 'MAP_SERVICES_AND_SETTINGS_UNCHANGED\n'
exit "$rc"
BASH
~~~

## 2. Живой этап

Сценарий продолжает работу из текущего подтверждённого
автоматического выхода без ручного pin и с выключенными режимами
zapret2. Для переключения нужен живой участник подписки с известной
страной IP, отличной от текущей. Сценарий проверяет один кандидат
штатным `xgw probe` и ещё раз сверяет свежий снимок. При отсутствии
пригодного кандидата отметь `BLOCKED_DEPENDENCY`.

Переключение выполняется только после подтверждения независимого
таймера на 120 с. Штатный pin ограничен 90 с. Тестовое окно читает
API и блокирует действия записи. Штатный CLI возвращает автовыбор.
Таймер снимается после подтверждённого возврата и успешного HTTPS.
При аварийном завершении проверь динамический таймер
`xgw-map-return-*.timer`. Если он активен, дождись срабатывания
и проверь возврат автовыбора и доступность HTTPS.

| Признак | Критерий |
|---|---|
| MAP_ENTRY_OK | Тот же запуск с -P, который будет использован в живой части, дошёл до парсера аргументов. |
| MAP_CONTRACT_ORDERS_OK | В каждом порядке два теста прошли в одном процессе pytest. |
| MAP_SWITCH_PREFLIGHT_OK | Одна штатная проба второго сервера прошла, свежий снимок сохранил исходный автовыбор. |
| MAP_SWITCH_ROLLBACK_ARMED | Таймер вооружён до CLI pin. |
| MAP_PAN_OK | После выбора новой страны анимация прошла не меньше двух разных позиций. Обе фотографии новой страны сделаны после завершения панорамы, на разных фазах пульса. |
| MAP_SWITCH_OK | Выбранный Xray тег и конечная страна совпали с картой, пульс активен на другой стране, новый HTTPS-сеанс прошёл. Запиши только признак изменения публичного IP. |
| MAP_AUTO_RESTORED_OK | Свежий снимок подтвердил автовыбор, карта активна и совпадает с текущим выходом, HTTPS прошёл. Запиши только признак возврата исходного IP. |
| MAP_SERVICES_AND_SETTINGS_UNCHANGED | PID XGW и Xray и контрольные суммы настроек совпали. |

Через vision сравни `switch-before.png`, `switch-pinned.png`,
`switch-pinned-second.png` и `switch-restored.png` в частном каталоге.
В двух средних кадрах проверь один и тот же новый маркер и разные
радиусы кольца. В отчёте опиши положение маркера и состояние.
Публикуй обезличенные признаки, тайминги и результат возврата.
Теги, IP, конфиги и снимки оставь в закрытом каталоге. При ошибке
укажи последний успешный этап, первую ошибку и результат срабатывания
или снятия таймера.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`,
выполни блок и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-map-switch-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_gui-map-switch.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Qt application lifetime and map switch acceptance'
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
