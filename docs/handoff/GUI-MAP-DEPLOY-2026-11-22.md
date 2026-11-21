# ThinkCentre — обновление карты в установленном XGW

**Ubuntu 24.04 LTS.** Flash сама выполняет утверждённый сценарий
в терминале графической сессии и автоматически публикует один
обезличенный отчёт. При недоступности sudo, терминала, рабочего
стола, сессии XGW или GitHub запроси доступ и продолжи сама.
Исходники и установочный сценарий подготовил Codex.

В UI06 r3 штатный запуск, два порядка Qt-тестов и живое переключение
прошли. Карта показала Нидерланды, затем США и возврат. Панорама
зафиксировала шесть позиций, два кадра показали пульс на новом выходе.
Исходный IP восстановлен. Проверка использовала частную копию GUI.
[Отчёт UI06 r3](../reports/2026-11-21T221346Z_gui-map-switch-r3.md)

Этот проход доставляет проверенные файлы в установленный релиз
`7c20f59`. Карта и окно обновляются из UI06, клиент опроса — из
P2.9. Проверка читает текущее состояние шлюза. Диспетчер запуска,
настройки, VPN и сетевые службы остаются в рабочем состоянии.

## 1. Установка и автоматическая проверка

Убедись, что в обычном окне XGW есть действующий пользовательский
сеанс. При необходимости войди заново. В терминале этой же
графической сессии выполни `sudo -v`. Если PyQt6 и pytest доступны
из отдельного окружения, экспортируй абсолютный
`XGW_GUI_TEST_PYTHON`. Запусти блок сама из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=012b859c3a6e1ad84775dbce017b366efe01df25
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_gui_map_refresh.sh" | bash -s -- "$CODE"
BASH
~~~

Сценарий сначала запускает три контракта установки. Затем он
сверяет путь штатного диспетчера и предварительные байты карты
и окна с `3c4ae6b`, клиента с `7c20f59`. При трёх совпадениях
с исходной версией ставится независимый таймер отката на 10 минут.
Перед заменой записывается признак начатого обновления.
При полном совпадении с кандидатом сценарий запускает только
проверку установленного окна. При неизвестной или смешанной базе
зафиксируй несовпадение и не выполняй установку из другой ревизии.

| Признак | Критерий |
|---|---|
| MAP_DEPLOY_CONTRACTS_OK | Три теста прошли. Они проверяют установку и восстановление байтов и прав, отказ на смешанной базе, возврат после прерывания записи. |
| MAP_DEPLOY_ROLLBACK_ARMED | Таймер активен до записи первого файла. Для ранее обновлённого релиза ставится только результат проверки установленной версии. |
| MAP_INSTALLED_MODULES_OK | Карта, окно и клиент импортированы из установленного релиза. |
| MAP_LIVE_COUNTRY_OK, MAP_MINIMIZED_IDLE_OK | Страна совпадает с endpoint_country рабочего выхода. В свёрнутом окне пришёл новый снимок, пульс, движение и подсветка остановлены. |
| MAP_RESTORED_OK, MAP_HIDE_SHOW_OK POST_0 | После возврата окна получен свежий снимок и возобновился пульс. Скрытие и показ меняют видимость опроса. Попыток записи нет. |
| MAP_GATEWAY_UNCHANGED HTTPS_200 | PID обеих служб, контрольные суммы настроек и контроль HTTPS совпали с базой. |
| MAP_DEPLOYED_AND_VERIFIED или MAP_ALREADY_INSTALLED_AND_VERIFIED | Три файла кандидата подтверждены, живое окно прошло проверку. При новой установке таймер снят. |

После успешной установки вызови `xgw gui` обычным способом.
В рабочем окне сверь карту и страну, сверни и верни окно,
проверь, что панель получила свежие данные. Используй vision
для сверки штатного окна и двух частных снимков из
`PRIVATE_ARTIFACTS`. Сохрани обновление при успешной проверке.

## 2. Возврат и отчёт

При сбое сценарий пытается вернуть три файла. При
`MAP_DEPLOY_ROLLED_BACK` зафиксируй итог. При
`MAP_DEPLOY_ROLLBACK_PENDING` проверь таймер
`xgw-gui-map-refresh-rollback.timer`. Если он активен, дождись
срабатывания и проверь файлы и состояние служб. Для возврата
после ошибки штатного окна присвой переменной `ROLLBACK_PAYLOAD`
абсолютный путь из одноимённой строки сценария. Это применимо
к установке, начатой текущим проходом.

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/gui_home_install.py" rollback --map-refresh
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/gui_home_install.py" check --map-refresh
~~~

Ожидаются `RESTORED` и `READY changed files: 3`. После возврата
вновь открой обычное окно `xgw gui`. В отчёте укажи SHA кандидата,
результаты команд, состояние таймера и какой GUI остался в работе.
При ошибке запиши последний успешный этап и результат возврата.
Снимки, локальные пути и данные подписок оставь на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`,
выполни блок при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-gui-map-deploy-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_gui-map-deploy.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre installed map and Qt polling acceptance'
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
