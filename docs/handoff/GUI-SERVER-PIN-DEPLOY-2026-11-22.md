# ThinkCentre — установка диалога временного выбора сервера

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарий из терминала
графической сессии и автоматически публикует один обезличенный отчёт
при любом исходе. При недоступности sudo, терминала, рабочего стола,
сессии XGW или GitHub запроси доступ. Код подготовил Codex.

На частной копии GUI прошли семь тестов и живое переключение.
Действие «На 10 минут» отправило первый разрешённый POST, изменились
страна и публичный IP. «Автовыбор XGW» отправил второй POST и вернул
исходный IP. PID и настройки сохранились.
[Отчёт живого прогона](../reports/2026-11-21T230207Z_gui-server-pin.md)

Сценарий доставляет принятый `vpn_ui/xgw/sidebar.py` в установленный
релиз `7c20f59`. Проверка диалога использует отмену и читает
состояние панели. VPN-выход сохраняется на протяжении установки
и проверки.

## 1. Установка и проверка

Убедись, что обычное окно XGW авторизовано. Из терминала
этой же графической сессии выполни `sudo -v`. Если Qt и pytest
в отдельном окружении, экспортируй абсолютный
`XGW_GUI_TEST_PYTHON`.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=f901ed8213f648dd111e2808df70cb38e38400d2
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/run_gui_map_refresh.sh" | bash -s -- "$CODE" --pin-refresh
BASH
~~~

До замены сценарий запускает контракты, проверяет диспетчер и
базовый HTTPS, а затем сверяет sidebar с `dfccea8`. Если в
релизе уже лежит точный кандидат, выполняется проверка окна.
При неизвестных байтах зафиксируй несовпадение. После сверки
исходного файла сценарий ставит независимый таймер на 10
минут, записывает маркер начатой установки и заменяет файл.

| Признак | Критерий |
|---|---|
| PIN_DEPLOY_CONTRACTS_OK | 10 тестов. Проверки установщика и HTTPS, включая замену одного файла и возврат. |
| MAP_HTTPS_CONTROL_OK baseline и installed | Базовый и итоговый HTTPS вернули конечный 2xx. Переходы ограничены двумя HTTPS-редиректами. |
| PIN_DEPLOY_ROLLBACK_ARMED | Таймер активен до новой установки. |
| PIN_INSTALLED_MODULES_OK | Sidebar импортирован из штатного релиза. |
| PIN_INSTALLED_DIALOG_OK POST_0 | Доступны «На 10 минут», «Бессрочно», «Отмена». Enter по умолчанию и Esc соответствуют «Отмена». Помощник нажал «Отмена», попыток записи нет. |
| PIN_GATEWAY_UNCHANGED | PID XGW и Xray и контрольные суммы настроек совпали с базой. |
| PIN_DEPLOYED_AND_VERIFIED или PIN_ALREADY_INSTALLED_AND_VERIFIED | Байты принятого файла подтверждены, тест диалога прошёл. При новой установке таймер снят. |

После успешной проверки открой окно штатной командой `xgw gui`.
Выдели один доступный сервер подписки, открой «Выбрать сервер»
и закрой диалог клавишей Esc. Через vision сравни увиденное
со снимком `pin-installed-dialog.png` в `PRIVATE_ARTIFACTS`.
Оставь проверенное обновление установленным.

## 2. Откат

При сбое сценарий возвращает файл. При
`PIN_DEPLOY_ROLLED_BACK` запиши итог восстановления и отдельный
HTTPS-результат. При `PIN_DEPLOY_ROLLBACK_PENDING` проверь
`xgw-gui-pin-refresh-rollback.timer` и дождись его срабатывания,
если он ещё активен. При сбое повторного запуска обычного окна
присвой `ROLLBACK_PAYLOAD` значение из одноимённой строки вывода.
Используй этот возврат для обновления, начатого текущим проходом.

~~~bash
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/gui_home_install.py" rollback --pin-refresh
sudo /usr/bin/python3 -I -B "$ROLLBACK_PAYLOAD/gui_home_install.py" check --pin-refresh
~~~

После возврата ожидаются `RESTORED` и `READY changed files: 1`.
Открой штатное окно и сверяй файл, PID и HTTPS. Укажи итоговый
статус установки, последний успешный шаг и состояние таймера.
Снимки, данные серверов и локальные пути оставь на машине.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`.
Выполни блок и верни ссылку на опубликованный коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-pin-deploy-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_gui-server-pin-deploy.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre installed timed server dialog'
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
