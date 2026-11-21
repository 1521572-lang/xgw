# ThinkCentre — временный выбор VPN-сервера из окна XGW

**Ubuntu 24.04 LTS.** Flash сама запускает сценарий из терминала
графической сессии и автоматически публикует один обезличенный
отчёт при любом исходе. Если терминал, GUI, сеанс XGW, sudo или
GitHub недоступны, запроси доступ. Код и команды подготовил Codex.

Установка карты и Qt-клиента принята. Штатный `xgw gui` заменил
старое окно, страна и опрос после сворачивания подтверждены.
В UI06 r3 живое переключение выполнялось через CLI.
[Отчёт установки](../reports/2026-11-21T224914Z_gui-map-deploy-r2.md) · [Отчёт UI06 r3](../reports/2026-11-21T221346Z_gui-map-switch-r3.md)

Новый диалог предлагает «На 10 минут» или «Бессрочно» для общего
VPN-выхода. По умолчанию выбрана отмена. Если во время диалога
изменились страна, имя, источник или доступность сервера,
нужно подтвердить выбор заново. У бесплатного пула остаётся
свой существующий диалог.

## 1. Запуск

Работай от пользователя рабочего стола с действующим сеансом
XGW. Если PyQt6 и pytest установлены в отдельном окружении,
экспортируй абсолютный `XGW_GUI_TEST_PYTHON`. Блок использует
частную копию подтверждённого GUI и кандидатный диалог.

Живой этап один раз меняет общий VPN-выход. Выполняй его
из локального терминала только в согласованное владельцем окно,
в котором другие операторы не меняют pin. Для этого этапа
экспортируй `XGW_GUI_PIN_WINDOW=1` и выполни `sudo -v`.
Если согласованного окна нет, сценарий выполнит тесты и отметит
живой этап как NOT_RUN.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=37eb3b2e2e6a9ed9f35d3ac7d421d840ebf01585
INSTALLED=6c6918da9c3477b4a6aecbe7e0a3d75f79f5c103
GUI=/opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64
PY=${XGW_GUI_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import pytest, PyQt6.QtWidgets, PyQt6.QtSvg'
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
for rel in vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py src/xgw/gui/client.py; do
  cmp -s "$GUI/$rel" <(git show "$INSTALLED:$rel")
done
D=$(mktemp -d "$HOME/xgw-gui-pin.XXXXXXXX")
cp -R "$GUI/vpn_ui" "$GUI/src" "$D/"
git archive "$CODE" vpn_ui/xgw/sidebar.py docs/helpers/gui_map_switch.py \
  docs/helpers/gui_map_visibility.py tests/test_vpn_ui_sidebar.py | tar -x -C "$D"
mkdir -m 0700 "$D/qt-config"
printf 'GUI_PIN_BASE_OK %s | %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$PRETTY_NAME" "$D"
export PYTHONPATH="$D:$D/src" XGW_UI_QT=PyQt6 XDG_CONFIG_HOME="$D/qt-config"
cd "$D"
entry=(env "PYTHONPATH=$D/docs/helpers:$PYTHONPATH" "$PY" -B -P "$D/docs/helpers/gui_map_switch.py")
"${entry[@]}" --help >/dev/null
QT_QPA_PLATFORM=offscreen timeout -k 3 55 "$PY" -B -P -m pytest -p no:cacheprovider -q \
  tests/test_vpn_ui_sidebar.py -k 'server_confirm or header_clicks'
printf 'GUI_PIN_CONTRACTS_OK\n'
if [[ ${XGW_GUI_PIN_WINDOW:-0} != 1 ]]; then
  printf 'GUI_PIN_NOT_RUN no_maintenance_window\n'
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
timeout -k 5 255 "${entry[@]}" "$D" --maintenance-window --via-gui || rc=$?
[[ $(services) == "$before" ]]
sudo -n sha256sum --check --status "$D/settings.sha256"
printf 'GUI_PIN_GATEWAY_UNCHANGED\n'
exit "$rc"
BASH
~~~

## 2. Критерии

| Признак | Критерий |
|---|---|
| GUI_PIN_CONTRACTS_OK | Семь тестов. Временное и бессрочное закрепление, отмена, смена страны во время диалога, отдельный путь пула, два размера списка при сортировке. |
| MAP_SWITCH_PREFLIGHT_OK | Есть исходный автовыбор с одной подтверждённой страной и живой сервер подписки другой страны. Штатная проба успешна, новое состояние сохраняет исходную базу. |
| MAP_SWITCH_ROLLBACK_ARMED | Независимый таймер на 120 с активен до клика. |
| MAP_GUI_PIN_OK TTL_10M | Кнопка «Выбрать сервер» открыла обычное подтверждение. «На 10 минут» отправила один разрешённый POST. Сервер принял запрос, свежий снимок подтвердил конечный срок, выбранный Xray-тег и страну. |
| MAP_PAN_OK и MAP_SWITCH_OK | Карта переместилась к новому маркеру. Два кадра сняты после панорамы. Новый HTTPS-сеанс успешен. |
| MAP_GUI_UNPIN_OK и MAP_AUTO_RESTORED_OK | «Автовыбор XGW» отправил второй и последний разрешённый POST. Ответ и свежий снимок подтвердили автовыбор. Сеть вернулась, таймер снят. Зафиксируй отдельно признак возврата исходного IP. |
| GUI_PIN_GATEWAY_UNCHANGED | PID XGW и Xray и контрольные суммы настроек совпали. |

Бессрочное закрепление проверяется только в тесте без сети.
Если второго живого сервера другой страны нет, запиши
BLOCKED_DEPENDENCY. При отказе на живой стадии сценарий
вызывает штатный CLI возврата. Если он прерван, найди активный
`xgw-map-return-*.timer`, дождись срабатывания и подтверди
автовыбор и HTTPS. Отметь возврат через CLI отдельно от возврата
через GUI. Для второго пути нужен `MAP_GUI_UNPIN_OK`.

Используй vision для сверки снимков карты в частном каталоге.
Опиши смену положения и пульс маркера. При ошибке укажи
последний успешный этап, состояние таймера и результат возврата.
Снимки, теги, IP и конфиги оставь на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-gui-pin-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_gui-server-pin.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre timed GUI server selection'
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
