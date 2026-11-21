# ThinkCentre — карта при сворачивании и возврате окна, UI06

**Ubuntu 24.04 LTS.** Flash сама запускает проверку в рабочей
графической сессии и публикует один обезличенный отчёт при любом
исходе. При недоступности терминала, рабочего стола, сеанса
панели или GitHub запроси доступ и продолжи сама. Код и сценарий
подготовил Codex.

P2.11 принят в Firefox. Ручное обновление после локального 503
отправило один GET за 454 мс, черновик сохранился, 401 остановил
опрос, PID XGW и Xray совпали до и после теста.
[Отчёт P2.11](../reports/2026-11-21T205918Z_panel-web-retry.md)

Карта отслеживает события показа и скрытия. При сворачивании
пульс, панорама и подсветка останавливаются. Новые данные могут
обновить страну в фоне, а после возврата окна пульс показывает
актуальный подтверждённый выход. Qt может сохранять
`isVisible()` после события сворачивания.
[Документация Qt о hideEvent](https://doc.qt.io/qt-6/qwidget.html#hideEvent)

## 1. Запуск

Работай в терминале графического пользователя с авторизованным
сеансом XGW. При истёкшей сессии сначала войди в обычном окне.
`XGW_GUI_TEST_PYTHON` указывает на Python с pytest и системным
PyQt6, если они в отдельном окружении. Сценарий снимает копию
установленного GUI и заменяет в ней два модуля карты и окна.
Клиент опроса берётся из принятого P2.9. Тестовое окно читает
рабочий API, блокирует действия записи и использует частное
окружение Qt. Установка и VPN остаются в рабочем состоянии.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
[[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]
BR=integration/zapret2-batch1
CODE=8ed2c2c55c2d39c976e98dd753f3cd1c19b5b487
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
test -r "$GUI/src/xgw/gui/client.py"
D=$(mktemp -d "$HOME/xgw-map-visibility.XXXXXXXX")
cp -R "$GUI/vpn_ui" "$GUI/src" "$D/"
git archive "$CODE" vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py \
  src/xgw/gui/client.py docs/helpers/gui_map_visibility.py tests/test_vpn_ui_map_visibility.py |
  tar -x -C "$D"
git archive "$BASE" tests/test_vpn_ui_xgw.py tests/fixtures/gui/state-work.json |
  tar -x -C "$D"
mkdir -m 0700 "$D/qt-config"
printf 'PINNED %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$D"
export PYTHONPATH="$D:$D/src" XGW_UI_QT=PyQt6 XDG_CONFIG_HOME="$D/qt-config"
cd "$D"
QT_QPA_PLATFORM=offscreen timeout -k 3 45 "$PY" -B -P -m pytest -p no:cacheprovider -q \
  tests/test_vpn_ui_map_visibility.py tests/test_vpn_ui_xgw.py -k 'map_'
gateway_pids() {
  local unit pid
  for unit in xgw.service xgw-xray.service; do
    pid=$(systemctl show "$unit" -p MainPID --value) || return 2
    [[ $pid =~ ^[1-9][0-9]*$ ]] || return 2
    printf '%s\n' "$pid"
  done
}
PID_BEFORE=$(gateway_pids)
rc=0
timeout -k 4 125 "$PY" -B -P "$D/docs/helpers/gui_map_visibility.py" "$D" || rc=$?
PID_AFTER=$(gateway_pids)
if [[ $PID_BEFORE == "$PID_AFTER" ]]; then
  printf 'MAP_SERVICES_UNCHANGED\n'
else
  printf 'MAP_SERVICE_PID_CHANGED\n'
  exit 2
fi
exit "$rc"
BASH
~~~

## 2. Критерии

| Признак | Что фиксировать |
|---|---|
| Два контракта Qt | При скрытии движение останавливается, обновление в фоне запоминает последнюю страну. Контракт закреплённой базы проверяет смену фокуса на страну IP, неизменность фокуса после просмотра списка и сброс маркера при прямом режиме на фикстуре. |
| MAP_LIVE_COUNTRY_OK | В рабочем окне страна карты совпала с endpoint_country подтверждённого текущего выхода из API. |
| MAP_MINIMIZED_IDLE_OK | В свёрнутом окне API вернул новый снимок. Пульс, движение и подсветка остались остановлены. |
| MAP_RESTORED_OK | При возврате пришёл свежий снимок. Фокус соответствует текущему выходу, пульс снова меняет фазу. |
| MAP_HIDE_SHOW_OK POST_0 | Программное скрытие и показ также обновляют видимость опроса. Попыток записи нет. |
| MAP_SERVICES_UNCHANGED | PID XGW и Xray совпали. |

С помощью vision сопоставь два снимка карты в частном каталоге.
Опиши положение точки и видимость маркера, снимки и данные подписок
в отчёт не включай. Если живой API не дал подтверждённый активный
выход с GeoIP, отметь `NOT_VERIFIABLE` для живого этапа
и сохрани результат контрактов. Укажи фактическую первую ошибку,
если испытание прервалось. Подмена страны в контракте проверяет
логику GUI. Фактическое переключение между двумя VPN-серверами
остаётся отдельным открытым сценарием UI06.

## 3. Автоматическая публикация

Укажи абсолютный путь к готовому обезличенному отчёту в
`REPORT_SRC`, выполни блок и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-map-visibility-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_gui-map-visibility.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre map visibility acceptance'
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
