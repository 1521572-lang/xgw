# ThinkCentre — проверка выбора ALT9 для локальных TLS-соединений

**Ubuntu 24.04 LTS.** Flash сама запускает готовый сценарий и публикует один
обезличенный отчёт при любом исходе. При недоступности терминала, sudo
или GitHub запроси нужный доступ. Рабочий шлюз остаётся в исходном режиме.

В предыдущем проходе прошли 122 контракта. Установленный nfqws2 принял
пять блоков исходной и суженной политики в `--dry-run` и `--intercept=0`.
Откат вернул исходные аргументы и ревизию. Теперь требуется подтвердить
выбор профиля по SNI реальных TLS-соединений. [Отчёт предпроверки](../reports/2026-11-24T174429Z_flowseal-policy-scope.md)

## Запуск

В терминале ThinkCentre выполни `sudo -v`. Если pytest в отдельном venv,
экспортируй абсолютный путь `XGW_TEST_PYTHON`. Запусти из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=985422e11fbbb069330bb23e8e1aa1c0a78998b2
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/flowseal_policy_trial.sh" | bash -s -- "$CODE"
BASH
~~~

Сценарий снова проверит контракт сохранения и пройдёт штатную предпроверку
установленного комплекта. Затем поднимет отдельный HTTPS-сервер с тестовым
сертификатом и локальную очередь в netns с единственным интерфейсом `lo`.
Все цели имеют адреса `127.0.0.x`. SNI передаётся прямо в TLS-клиент,
обращений к DNS для тестовых имён нет. В фазе выбора профиля Lua-обработчики
заменены на `VERDICT_PASS`. Файлы списков, условия фильтрации и их порядок
взяты из аргументов трёх ревизий XGW. Журнал каждого процесса ограничен
1 МиБ. Проба работает с новым дочерним процессом для каждой ревизии.

## Ожидаемые результаты

| Контроль | Исходная | Суженная | После отката |
|---|---:|---:|---:|
| Хост страницы внутри `youtube.com` | 2 | 2 | 2 |
| Хост медиа внутри `googlevideo.com` | 2 | 2 | 2 |
| Точное локальное исключение CDN | 2 | 0 | 2 |
| Поддомен локального исключения страницы | 2 | 0 | 2 |
| Хост домена, убранного из положительной области | 2 | 0 | 2 |
| Внешнее имя с похожей строкой домена | 0 | 0 | 0 |

`2` означает выбор TLS-блока ALT9. `0` означает, что после распознавания
нужного TLS-имени выбрано поведение по умолчанию. Пустой список `profiles`
означает отсутствие доказательства. Для каждого из 18 соединений обязателен
`https_body_ok=true`, в том числе в отрицательных контролях. Итоговая
метка `FLOWSEAL_POLICY_MATCH 18/18` требует совпадения всех решений.

Укажи ОС, версию ядра и движка, SHA, коды контрактов и лаборатории. Сведи
18 строк по фазам, затем укажи совпадение FIB, настроек, служб и владельцев
очереди и оба контроля HTTPS через Xray. Если шаг завершится ошибкой,
запиши фазу и конкретный блокер из приватного `lab.err` или короткой метки.
Сырые логи, конфиги, IP, PID и каталоги остаются на ThinkCentre. Проверка
полезности профиля в интернете остаётся отдельным этапом.

## Автоматическая публикация

Укажи абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок после проверки, включая неполный результат, и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-flowseal-match-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_flowseal-tls-match.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre ALT9 TLS profile matching'
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
