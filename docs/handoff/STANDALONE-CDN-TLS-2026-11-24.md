# ThinkCentre — TLS и контрольный CDN-диапазон после возврата VPN

**Ubuntu 24.04 LTS.** Flash сама запускает проверку и автоматически публикует
один обезличенный отчёт при любом исходе. При недоступности терминала, sudo,
панели или GitHub запроси нужный доступ. В согласованное окно выполни один
временный цикл. Установка и откат перезапускают `xgw.service`. Standalone
приостанавливает VPN до выхода из режима.

В последнем отчёте страница и получение формата прошли в обоих режимах.
CDN на общей ссылке и IPv4 принял TCP, но прямое плечо остановилось на TLS
через 10 с. Через VPN TLS занял 0,588 с, затем пришёл `302` без тела.
Возврат в `blue` подтверждён новой меткой и пережил откат. В предпроверке
сбор тестов зависел от отсутствующего в установленной версии модуля
`route_evidence`. Импорт убран из обычного чтения формата и пробы.
[Отчёт](../reports/2026-11-24T170246Z_standalone-cdn-comparison.md)

## Один проход

Войди в панель из сессии рабочего пользователя и выполни `sudo -v`. Если
pytest запускается из venv, экспортируй абсолютный путь `XGW_TEST_PYTHON`.
При недоступности ролика задай согласованную замену через `XGW_T09_VIDEO`
до начала прохода. Выполни блок из рабочей копии.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=0f28d423fc54e78046c4432a2dd2f31c2404130b
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/standalone_return_preflight.sh" | bash -s -- "$CODE"
git show "$CODE:docs/helpers/standalone_return_live.sh" | bash -s -- "$CODE" cdn
BASH
~~~

Запиши результаты `status`, `managed`, `watchdog`, `observation` и сверки
установленных файлов. При ошибке предпроверки опубликуй точный блокер.
Живой сценарий требует off/off, стабильного `blue` или `green`, HTTPS 200
через Xray и готового таймера отката. Профиль `fake_md5` закреплён. Помощник
не пересобирает пакет и не открывает новый захват пакетов.

Сценарий сравнивает страницу и CDN по TCP, TLS, первому байту и размеру тела.
Он сохраняет только число событий `ClientHello`, `ServerHello` и входящих
TLS alert из диагностического вывода curl. Поле `tls_events=null` означает,
что распознаваемых событий не было. Счётчики отражают работу TLS-клиента
и сами по себе не измеряют доставку пакета на WAN. Для HTTP-ответа `302`
на контрольном плече сценарий делает ровно один новый запрос на том же
URL и запрошенном IPv4, без перехода по `Location`. [Сообщения TLS в curl/OpenSSL](https://github.com/curl/curl/blob/curl-8_5_0/lib/vtls/openssl.c#L2497-L2546)

## Что включить в отчёт

1. Версии ОС, ядра и первую строку `curl --version` с используемой TLS-библиотекой.
   Укажи SHA, коды шагов, готовность Standalone и проверки ревизии до и после.
2. Для страницы сравни `off-page.out` и `direct-page.out`. Для
   диапазона перенеси агрегаты из `cdn-comparison.out`. Укажи источник URL,
   совпадение запрошенного и наблюдаемого IPv4, статус, байты и времена.
   Для каждой попытки укажи наличие `ClientHello`, `ServerHello`, входящего
   TLS alert и результат. Данные контрольного повтора запиши отдельной строкой.
3. Возьми результат `direct-route.out` и `off-route.out`. `observed` означает
   единственную запись о принятии этого сокета и назначении outbound в той
   же эпохе Xray. `no_access_record`, неоднозначное совпадение, отсутствие
   локального сокета или изменение снимков означают `NOT_VERIFIED` для пути
   конкретного запроса. Агрегаты из `*-counters-delta.out` укажи отдельно.
4. Сверь `STANDALONE_LIVE_RETURN_ATTRIBUTED`, активный слот, off/off,
   `STANDALONE_LIVE_FILES_AND_VPN_RESTORED` и `STANDALONE_LIVE_FINAL_MANAGED`.
   Запиши итоговые проверки HTTPS и таймера. При обрыве терминала используй
   [независимый возврат](STANDALONE-MANAGED-LIVE-2026-11-23.md#3-независимый-возврат).
5. Для допуска Selective нужны `206/65536` на обоих плечах и подтверждение
   пути. При повторном `302` или `403` в контроле запиши статус и результат
   TLS отдельными полями. При
   повторяемом сбое до `ServerHello` укажи это как наблюдение клиента без
   вывода о месте потери. Матрица и длительное воспроизведение ожидают
   решения по отчёту.

Оставь на машине подписанные ссылки, адреса, порты, исходную конфигурацию
и журнал. В отчёт включи только короткие метки, результаты и агрегаты.

## Автоматическая публикация

Задай `REPORT_SRC` с абсолютным путём к законченному обезличенному отчёту.
Выполни блок из рабочей копии после проверки восстановления, в том числе
при частичном результате или блокере до включения. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-standalone-cdn-tls-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_standalone-cdn-tls.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Standalone CDN TLS and control retry'
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
