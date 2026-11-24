# ThinkCentre — сравнение страницы YouTube и CDN в одном цикле Standalone

**Ubuntu 24.04 LTS.** Flash сама выполняет проверку и публикует обезличенный
отчёт при любом исходе. При недоступности терминала, sudo, панели или GitHub
запроси доступ. Проведи проверку в согласованное окно. Временная установка
и откат перезапускают `xgw.service`, Standalone на время приостанавливает VPN.

Ожидающий возврат из `legacy` в `blue` уже подтверждён за 39 секунд.
Прежний проверочный сценарий вернул код 2 из-за поиска устаревшей фразы
в журнале. Новый маркер фиксирует реально применённый слот и способ
применения после успешного сохранения поколения. В предыдущем сетевом
проходе `fake_md5` получил свежую ссылку, но три запроса к CDN остановились
по таймауту TLS. В этом задании сначала выясняем, воспроизводится ли эта
разница для страницы и медиа при заданном адресе назначения.

[Возврат sing-box](../reports/2026-11-24T162825Z_standalone-pending-resume.md) · [Предыдущая CDN-проверка](../reports/2026-11-23T110026Z_t09-live-worker-timing.md)

## 1. Запуск одного прохода

Войди в панель из сессии рабочего пользователя, выполни `sudo -v`. Для pytest
в venv экспортируй его абсолютный путь в `XGW_TEST_PYTHON`. Сценарий использует
установленные `curl` и `yt-dlp`. При недоступности исходного ролика согласованную
замену задай один раз через `XGW_T09_VIDEO` до этого запуска. Выполни блок
из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=b16271db236a756fc646fb81e6af1ebf6598007c
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/standalone_return_preflight.sh" | bash -s -- "$CODE"
git show "$CODE:docs/helpers/standalone_return_live.sh" | bash -s -- "$CODE" cdn
BASH
~~~

Предпроверка меняет только копию установленного пакета. Сверь результаты
`status`, `managed`, `watchdog`, `observation` и `INSTALLED_UNCHANGED`.
Живой запуск допускается из свежего off/off с устойчивым `blue` или `green`
и HTTPS 200 через локальный Xray. Если эта предпосылка или сверка патча не
выполнена, опубликуй конкретный блокер. Режимы вручную не переключай.

Сценарий проверяет страницу в off/off и в `active` с `without_vpn=true`.
Он заранее пробует получить запасной URL в off/off, затем в Standalone
пробует получить собственный свежий URL. При его отсутствии используется
сохранённый URL из off/off. Выбранный профиль `fake_md5` закреплён на весь
цикл. Сценарий берёт один HTTPS Range размером 64 КиБ без перехода по
редиректам. После возврата off/off выполняет такой же запрос с той же
подписанной ссылкой и закреплённым IPv4. Каждый сетевой шаг ограничен
таймаутом. Снимки Xray снимаются в границах фаз.

## 2. Что записать

1. Версии системы и инструментов, SHA, коды шагов, стартовую и конечную
   топологию. Возьми переходы Standalone из `standalone-on.out`. Сопоставь
   `off-page.out` и `direct-page.out` по HTTP, TCP, TLS и объёму. Укажи
   результат получения формата в каждой фазе без сырых ошибок `yt-dlp`.
2. Из `cdn-comparison.out` возьми источник URL, совпадение запрошенного
   IPv4 и URL, подтверждение фактического IP, время TCP/TLS/первого байта,
   HTTP, объём и исход диапазона по каждому плечу. Если IPv4 был запрошен,
   но curl не сообщил адрес установленного соединения, оставь это различие
   в отчёте. Истечение ссылки, HTTP 403 и транспортный таймаут учитывай
   раздельно. HTTP 403 при смене выхода допускает привязку подписанной
   ссылки к исходному адресу клиента.
3. Сопоставь подтверждение ревизии до и после Standalone и агрегаты из
   `direct-counters-delta.out` и `off-counters-delta.out`. Подтверждение пути
   отдельного запроса требует его привязки к outbound по уже имеющимся
   данным шлюза. Если такой записи нет, укажи подтверждённый режим и
   `NOT_VERIFIED` для маршрута запроса. Новый захват пакетов не запускай.
4. Приведи `STANDALONE_LIVE_RETURN_ATTRIBUTED` и точную короткую метку
   `sing-box resume committed: slot=… mode=…`, если они есть. Вариант `api`
   подтверждает применение через API. `unchanged` подтверждает сохранение
   поколения при совпавшем конфиге Xray. Сверь слот с активным юнитом,
   наличие маркера managed и очищение `resume_managed`. Отдельно укажи
   HTTPS после возврата и результаты `FILES_AND_VPN_RESTORED`, `FINAL_MANAGED`.
5. Диапазон `206/65536` на обоих плечах при подтверждённом пути даёт
   основание переходить к допуску Selective. При таймауте укажи последний
   подтверждённый этап и результат контрольного плеча. Матрицу, подбор
   других профилей и длинное воспроизведение оставь для решения по отчёту.

При обрыве терминала используй [независимый возврат](STANDALONE-MANAGED-LIVE-2026-11-23.md#3-независимый-возврат)
по каталогу этого прогона. Опубликуй только агрегаты и короткие метки.
Подписанные URL, адреса, сырые логи и настройки остаются на ThinkCentre.

## 3. Автоматическая публикация

После проверки и сверки возврата укажи абсолютный путь к обезличенному
отчёту в `REPORT_SRC`. Выполни блок даже при неполном результате и верни
ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-standalone-cdn-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_standalone-cdn-comparison.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Standalone CDN and VPN comparison'
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
