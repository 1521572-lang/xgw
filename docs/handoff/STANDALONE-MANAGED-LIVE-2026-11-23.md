# ThinkCentre — один живой цикл Standalone и возврат sing-box

**Ubuntu 24.04 LTS.** Flash сама запускает закреплённые команды и
автоматически публикует обезличенный отчёт при любом исходе. Запроси
доступ при недоступности терминала, sudo, панели или GitHub. Для живого
цикла используй согласованное короткое окно. Установка и откат могут
дважды перезапустить `xgw.service`.

Контракты исходников и точечный патч на копии принятой базы прошли.
В исходном наборе добавлен пропущенный каталог `packaging`. На копии
тестируются шесть контрактов Standalone и три контракта возврата.
Два из них проверяют отмену до запроса остановки и во время остановки
VPN-мостов. Тесты хелпера панели идут на полном дереве с его
зависимостями. Рабочий
шлюз после r2 уже восстановил `blue` штатной пересборкой. Живой этап
проверяет, что именно новый механизм вернёт поколение сразу после
базового VPN.

[Отчёт по контрактам](../reports/2026-11-23T115805Z_standalone-managed-return.md) · [Отчёт по установленной копии](../reports/2026-11-23T124447Z_standalone-managed-return.md)

## 1. Запуск

Войди в штатную панель из сессии рабочего пользователя и выполни
`sudo -v`. Если pytest находится в venv, экспортируй абсолютный путь
`XGW_TEST_PYTHON`. Затем один раз выполни блок из рабочей копии XGW.
Если предыдущая редакция уже запустила живой цикл, заверши его с тем же
SHA и выполни новый шаг на копии для проверки отмены.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=947cf7236f5a7466c49d0630699ceb6167c95d80
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/standalone_return_preflight.sh" | bash -s -- "$CODE"
git show "$CODE:docs/helpers/standalone_return_live.sh" | bash -s -- "$CODE"
BASH
~~~

Сценарий требует свежий `off/off`, свободный lock, стабильное поколение
`blue` или `green` и HTTPS 200 через локальный Xray. Затем он применяет
патч к пяти файлам установленного пакета через манифест, с независимым
таймером возврата на 25 минут. После сверки кандидата сценарий один раз
включает Standalone и один раз возвращает `off` по квитанции. Он сравнивает
состояния поколений и ищет запись о целевом применении через API. Рабочие
файлы и настройки возвращаются после завершения цикла. Живой этап ограничен
проверкой возврата VPN. Если любой этап завершился ошибкой, сохрани вывод
и опубликуй отчёт без повторного включения.

## 2. Критерии и результат

| Этап | Что подтверждает результат |
|---|---|
| Копия | `COPY_PATCHED` либо `ALREADY_PRESENT`, компиляция пяти файлов, 6+3 контрактов, исходный пакет совпал |
| База и временная установка | Стабильный `blue`/`green`, маркер managed, HTTPS 200 через локальный Xray. Все пять установленных файлов совпали с пропатченной копией |
| Standalone | Хелпер подтвердил `active/without_vpn`. Файл состояния содержит `legacy` и `resume_managed=true`, маркер снят. Остановка мостов завершена, `standalone_stopping=false` |
| Возврат | Свежий `off/off`, HTTPS 200 через локальный Xray. До 240 с на `blue`/`green` с активным юнитом, маркером managed и очищенным `resume_managed` |
| Атрибуция | `STANDALONE_LIVE_RETURN_ATTRIBUTED` подтверждает запись в journald о применении целевого возврата через API в том же окне. `STANDALONE_LIVE_MANAGED_RETURN_OK` ставится после этого шага |
| Восстановление | `STANDALONE_LIVE_FILES_AND_VPN_RESTORED` подтверждает прежние байты, настройки и HTTPS 200. `STANDALONE_LIVE_FINAL_MANAGED` отдельно подтверждает управляемое поколение после отката |

Запиши SHA, Ubuntu, исходы этапов, поколения до и после и состояния
`resume_managed` и `standalone_stopping`. Различай целевой возврат, штатный переход без
подтверждённой причины и разрыв после отката. При недоступном
журнале зафиксируй ожидаемую фразу и отсутствие атрибуции. Публикуй
только обезличенную сводку. Приватные файлы, сырые записи и пути
остаются на ThinkCentre.

## 3. Независимый возврат

Обычно сценарий выполняет возврат сам. При обрыве терминала открой
обычный терминал, получи sudo и укажи абсолютный `XGW_STANDALONE_RUN`,
напечатанный живым сценарием в `PRIVATE_ARTIFACTS`. Сначала дай
таймеру или блоку ниже завершить возврат. При отсутствии sudo
запроси доступ для финальной сверки.

~~~bash
bash <<'BASH'
set -euo pipefail
[[ $XGW_STANDALONE_RUN == /* ]]
mapfile -t restore <"$XGW_STANDALONE_RUN/restore-location"
[[ ${#restore[@]} == 3 && ${restore[0]} == /var/lib/xgw/handoff/standalone-live.* ]]
if sudo -n test ! -e "${restore[0]}/overlay-apply-started"; then
  sudo -n systemctl stop xgw-standalone-return-rollback.timer
  exit 0
fi
sudo -n /bin/bash "${restore[0]}/guard.sh" \
  "${restore[0]}" /usr/bin/python3 "${restore[1]}" "${restore[2]}" --standalone-return
sudo -n test -f "${restore[0]}/restore-completed"
sudo -n sha256sum --check --status "${restore[0]}/config-before.sha256"
systemctl is-active xgw.service
sudo -n systemctl stop xgw-standalone-return-rollback.timer
BASH
~~~

Если установка ещё не запускалась, guard выходит без действий. Проверь
`overlay-apply-started` в приватном каталоге и состояние таймера.

## 4. Автоматическая публикация

Задай абсолютный путь к обезличенному отчёту в `REPORT_SRC` и выполни
блок из рабочей копии при любом исходе. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-standalone-live-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_standalone-managed-live.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report one live Standalone managed sing-box return'
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
