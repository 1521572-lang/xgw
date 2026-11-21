# ThinkCentre — повторное чтение веб-панели после локального отказа, P2.11

**Ubuntu 24.04 LTS.** Flash сама запускает подготовленный сценарий
и публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo или GitHub запроси доступ и продолжи сама.
Код и команды подготовил Codex. Задача Flash ограничена приёмкой.

В двух прогонах P2.10 на системном Firefox 159 вкладка получала
hidden и приостанавливала опрос на 30 секунд. Черновик переживал
потерю транспорта. После синтетического online первый GET начинался
через 48 и 51 мс, HTTP 200 приходил через 148 и 139 мс.
В первом прогоне на Chromium ветка скрытия осталась NOT_VERIFIABLE.
[Первый отчёт](../reports/2026-11-21T200621Z_panel-web-resume.md) · [Повторный отчёт](../reports/2026-11-21T204722Z_panel-web-resume.md)

P2.11 проверяет локальный отказ, при котором браузер остаётся в сети
и не получает событие online. После отказа в заголовке страницы
появляется кнопка «Повторить загрузку». Она отправляет GET, сохраняет
черновик и скрывается после успешного ответа или 401.

## 1. Запуск

Используй системный Firefox, geckodriver и Xvfb, которые использовались
в повторном P2.10. При необходимости укажи абсолютные пути в
`XGW_TEST_PYTHON` для Python с Selenium и `XGW_GECKODRIVER` для
совместимого драйвера. Для Firefox из Snap используй драйвер из той
же среды при его наличии. Сценарий передаёт `--profile-root` в
закрытом каталоге под домашней директорией и сам завершает сессию.
[Документация Mozilla по geckodriver](https://firefox-source-docs.mozilla.org/testing/geckodriver/Usage.html#running-firefox-in-a-container-based-package)

Выполни `sudo -v` и запусти блок сама из рабочей копии.
Сценарий через штатный CLI создаёт одноразовый вход для чтения
обзора. Отдельный локальный HTTP-сервер отдаёт кандидатные HTML и JS,
а CSS и успешные ответы обзора берёт у рабочего XGW. Тестовый
браузер получает 503 и 401 только на этом локальном сервере.
Запросы записи туда запрещены. Файлы установки, настройки и службы
шлюза остаются в рабочем состоянии.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=00fa20340b92cab9262263585dbe1f834076417f
PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
[[ $PY == /* && -x $PY ]]
"$PY" -B -c 'import selenium'
DRIVER=${XGW_GECKODRIVER:-}
if [[ -z $DRIVER ]]; then
  for bundled in /snap/bin/geckodriver /snap/bin/firefox.geckodriver; do
    if [[ -x $bundled ]]; then
      DRIVER=$bundled
      break
    fi
  done
fi
if [[ -z $DRIVER ]]; then
  DRIVER=$(command -v geckodriver)
fi
[[ $DRIVER == /* && -x $DRIVER ]]
command -v xvfb-run >/dev/null
sudo -n true
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-panel-web-retry.XXXXXXXX")
git archive "$CODE" src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js \
  tests/test_zapret2_web_refresh.cjs docs/helpers/panel_web_retry_firefox.py | tar -x -C "$D"
printf 'PINNED %s | %s\n' "$CODE" "$PRETTY_NAME"
if command -v node >/dev/null && [[ $(node -p "process.versions.node.split('.')[0]") -ge 18 ]]; then
  node --test "$D/tests/test_zapret2_web_refresh.cjs"
  printf 'WEB_CONTRACTS_OK\n'
else
  printf 'WEB_CONTRACTS_NOT_AVAILABLE\n'
fi
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
env -u WAYLAND_DISPLAY -u MOZ_HEADLESS -u MOZ_ENABLE_WAYLAND \
  timeout -k 5 125 xvfb-run -a "$PY" -B "$D/docs/helpers/panel_web_retry_firefox.py" \
  "$D" "$DRIVER" || rc=$?
PID_AFTER=$(gateway_pids)
if [[ $PID_BEFORE == "$PID_AFTER" ]]; then
  printf 'WEB_SERVICES_UNCHANGED\n'
else
  printf 'WEB_SERVICE_PID_CHANGED\n'
  exit 2
fi
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
exit "$rc"
BASH
~~~

## 2. Критерии

| Признак | Что фиксировать |
|---|---|
| WEB_CONTRACTS_OK | Четыре контракта. При отсутствии Node отметь WEB_CONTRACTS_NOT_AVAILABLE и продолжи живую проверку. |
| WEB_BROWSER | Версия системного Firefox и тип установки, например Snap. |
| WEB_RETRY_OFFERED | После 503 виден баннер и доступна кнопка обновления. navigator.onLine остаётся true, черновик открыт, сохранение отключено. |
| WEB_RETRY_OK | Нажатие инициирует ровно один GET в пределах 3 с после восстановления пробного транспорта. После успешного ответа кнопка скрыта, черновик сохранён и отправка снова доступна. Запиши измерение в миллисекундах. |
| WEB_RETRY_AUTH_OK POST_0 | После отмены черновика тестовый ответ 401 требует входа и скрывает кнопку. Запросов записи не было. |
| WEB_SERVICES_UNCHANGED | PID обеих служб совпали до и после прогона. |

При доступном vision сравни два снимка в частном каталоге
`PRIVATE_ARTIFACTS`. Укажи, видна ли кнопка при отказе и сохраняется
ли значение формы после ответа. Публикуй числа и обезличенные
признаки без снимков, локальных URL и данных входа. При ошибке
укажи последний пройденный этап, первую ошибку и итог проверки PID.
Отметь, завершилась ли сессия Firefox и geckodriver.

## 3. Автоматическая публикация

Укажи абсолютный путь к готовому отчёту в `REPORT_SRC`,
выполни блок и верни ссылку на опубликованный коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-panel-web-retry-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_panel-web-retry.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre manual web refresh acceptance'
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
