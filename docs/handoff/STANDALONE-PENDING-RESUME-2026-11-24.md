# ThinkCentre — проверка ожидающего возврата sing-box

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарий и публикует обезличенный
отчёт при любом исходе. Запроси доступ при недоступности терминала, sudo,
панели или GitHub. Для временной установки используй согласованное окно.
Установка и откат перезапускают `xgw.service`.

В живом цикле обычный VPN восстановился, но за 240 с шлюз остался на
`legacy` с `resume_managed=true`. Оба варианта ранней отмены затем прошли
на копии установленного пакета. Точное условие, задержавшее возврат в
живом цикле, по старому журналу установить не удалось.

Новый код подключает проверку поколения к готовой штатной сборке
watchdog, если конфиг sing-box уже совпадает с рабочим. При отказе моста
штатная сборка сохраняет свой обычный путь. Демон публикует
`sing-box resume: …` при смене этапа. Этот проход использует уже
существующий `resume_managed=true` и текущий режим off/off. Включение
Standalone, CDN-пробы и матрица в этот проход не входят.

[Живой цикл](../reports/2026-11-24T115803Z_standalone-managed-live.md) · [Проверка копии](../reports/2026-11-24T120015Z_standalone-managed-live.md)

## 1. Запуск

Войди в панель из сессии рабочего пользователя и выполни `sudo -v`.
Если pytest установлен в venv, экспортируй абсолютный путь
`XGW_TEST_PYTHON`. Выполни блок из рабочей копии один раз.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=80ba6823796a83cfdc8f2121e256cdb658c1a7d5
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/standalone_return_preflight.sh" | bash -s -- "$CODE"
git show "$CODE:docs/helpers/standalone_return_live.sh" | bash -s -- "$CODE" resume
BASH
~~~

Предпроверка применяет точечный патч к пяти файлам на копии и проверяет
шесть контрактов Standalone, три контракта возврата и два прохода
watchdog с уже занятой сборкой. Один из них проверяет отказ моста.

Для установки нужен исходный `legacy` с активным базовым юнитом,
`resume_managed=true`, свежим off/off и HTTPS 200 через Xray. Если
штатная пересборка уже вернула `blue`/`green`, зафиксируй это и
опубликуй результат предпроверки. Сценарий сам завершится на
`baseline-topology` до установки.

## 2. Критерии и возврат

- Укажи SHA, исходы трёх наборов на копии и стадию временной установки.
- При установке в течение 240 с наблюдай `blue`/`green`, активный юнит,
  маркер managed и очищенный `resume_managed`. Успех целевого
  переключения подтверждают `STANDALONE_LIVE_MANAGED_RETURN_OK` и
  запись о применении через API в том же окне.
- При ожидании или отказе приведи конечное состояние и хронологию
  меток `sing-box resume:` из приватного `return-journal.out`, если
  этап его снял. Различай ожидание сборки, начало проверки, отклонение
  кандидата и факт применения. Отмечай состояние HTTPS отдельно.
- Сценарий возвращает исходные файлы и настройки. После подтверждённого
  перехода он дополнительно проверяет сохранность managed-топологии
  после отката. При недостигнутом переходе фиксируется наблюдаемая
  топология, а проверка файлов и HTTPS оценивается отдельно.
- При обрыве терминала используй [независимый возврат](STANDALONE-MANAGED-LIVE-2026-11-23.md#3-независимый-возврат)
  по каталогу этого прогона. Публикуй агрегаты и метки. Исходные
  настройки, SHA настроек, PID и сырые журналы оставь на ThinkCentre.

## 3. Автоматическая публикация

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC`. Выполни
блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-managed-resume-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_standalone-pending-resume.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre pending managed sing-box recovery'
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
