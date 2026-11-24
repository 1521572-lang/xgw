# ThinkCentre — исключения ALT9 в панели и Qt

**Ubuntu 24.04 LTS.** Flash сама выполняет сценарии и публикует один
обезличенный отчёт при любом исходе. При недоступности терминала, sudo,
среды браузера или GitHub запроси доступ. Сценарии используют установленный
nfqws2 в отдельном netns и временную панель на демонстрационных данных.

В последнем отчёте закреплённая проверка остановилась на синтаксисе nftables.
С многострочным ruleset движок подтвердил все 18 решений, а HTTPS-тела
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
BR=integration/zapret2-batch1
CODE=3e65eaa7057d2deae14dc4ca9194f4795b509c88
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/flowseal_ui_trial.sh" | bash -s -- "$CODE"
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
