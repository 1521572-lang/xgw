# T11.3 r2 — техническая приёмка опубликованного управления zapret2

Раунд завершён. [Отчёт r2](../reports/2026-11-17_desync-zapret2-management-r2.md)
подтвердил управление и Standalone. Повтор Selective выполняется по
[ТЗ r3](T11-ZAPRET2-SELECTIVE-R3.md).

Исполнитель — Flash на ThinkCentre, Ubuntu 24.04 LTS. Код, тесты и установочные
скрипты написал Codex. **Flash только исполняет этот план**. Не изменять исходники,
тесты, helper, пороги или критерии. При дефекте записать диагностику, выполнить
указанный возврат и опубликовать отчёт для Codex. Команды и браузер запускай сама,
используй vision. При отсутствии терминала, sudo или GUI запроси доступ.
Владельцу запуск скриптов не делегировать. Публикация отчёта уже разрешена.

**Код для проверки — `f3de0052a4a41a549980a3264d8084887bf4c9b4`.** Проверять именно этот SHA.
Документация задания может быть новее. Готовый дистрибутив не нужен.
Прежний [BLOCKED_BUILD](../reports/2026-11-17_desync-zapret2-management.md)
относится к версии без реализации. По отчёту после перезагрузки старый tcpdump
исчез, свободно 46 ГБ, веб-обзор установлен, политика off/off, VPN работает.
Это задание заменяет предыдущую приёмку T11.3.

## 1. Контракт и границы

Проверяем настройки стратегии, доменов, интервалов, бюджета и проб, режимы off,
Standalone и Selective через один backend веба/Proton. Сравнение, ALT9, импорт,
фоновые задания и pin/reset в этот слой не входят. `evidence.playback=not_tested`
остаётся корректным даже после отдельного успешного опыта с видео. Сохранение
не подтверждает применение маршрута. Не менять очередь, движок, nft или sysctl.

| POST | Тело JSON | Поведение |
|---|---|---|
| `/api/zapret2/settings` | `{expected, settings}` | Разрешённые поля, без смены режима |
| `/api/zapret2/mode` | `{expected, mode}` | Только режим выбранных доменов |

Ответ содержит `ok`, `text`, `notes`, `code`. `saved` — записано, `unchanged` —
ничего не переписано, `conflict` — устаревшая ревизия, `invalid` — неверные данные,
`blocked` — не выполнены условия включения. `invalid_config`, `storage_error`,
`busy` — ошибки хранения/блокировки. Для совместимости Proton ошибки команд идут
JSON с HTTP 200. Отказы HTTP-защиты отдельно 401/403. expected брать из config_key GET.

## 2. Получение и тесты до установки

Из чистого checkout на шлюзе, в одном bash-сеансе:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=f3de0052a4a41a549980a3264d8084887bf4c9b4
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t11-management.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
df -h /home /var/lib/xgw
systemctl show xgw.service -p MainPID -p ActiveState -p ExecStart
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
sudo cat /proc/net/netfilter/nfnetlink_queue
sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json > "$D/config-original.sha256"
python3 -m pytest -q tests/test_zapret2_management.py \
  tests/test_zapret2_management_linux.py tests/test_zapret2_panel.py \
  tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state \
  tests/test_panel.py::test_zapret2_commands_require_session_origin_and_revision \
  tests/test_desync_schema.py::test_deploy_refuses_drift_before_stopping_service \
  tests/test_desync_schema.py::test_partial_deploy_failure_restores_old_files_and_restarts
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_install.sh
bash -n docs/helpers/t11_management_restore.sh
```

Если pytest в прежнем dev-venv, использовать его Python и записать путь. Не
устанавливать зависимости в окружение демона. При недоступности — BLOCKED_TEST_ENV.
Любое падение целевых тестов останавливает установку. Сохранить stdout/stderr.
Тесты используют временные файлы и локальный тестовый HTTP-сервер. Linux-тест
запускает два независимых процесса с настоящим flock и проверяет права 0600.

До установки подтвердить рабочий VPN/панель, off/off, пустую очередь, inactive
обоих воркеров. Сверить ExecStart и dispatcher с путями §3. Если режим после
отчёта изменил владелец, запросить окно проверки, самостоятельно его не выключать.
При неизвестной базе — BLOCKED_BASE. Новых WAN/pcap-захватов не запускать.

## 3. Установка с независимым откатом

Установщик сравнивает базу с `6f69cc278868bae07ae58c484b8f5b728ada1c29`
побайтово, проверяет владельца/права и исходный режим. Он создаёт резервную копию
и включает таймер возврата на 45 минут **до замены файлов**. Не исправлять
расхождения и не подменять базу текущими файлами машины.

| Файл относительно `/opt/xgw/lib/xgw` | Изменение |
|---|---|
| `watch/panel.py` | POST-команды |
| `watch/zapret2_control.py` | Возможности и причины недоступности |
| `watch/zapret2_management.py` | Новый обработчик записи |
| `ui/zapret2.html`, `ui/zapret2.css`, `ui/zapret2.js` | Форма, режимы, конфликт |

Седьмая строка манифеста — `src/xgw/gui/zapret2.py` внутри принятого GUI-релиза
`/opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64`.
Карта и каталог не заменяются. Дополнительно сравниваются config.py, managed.py,
paths.py, desync/schema.py и zapret2.py. Источники всех замен — файлы `src/xgw`
из CODE. Для нового management.py старая SHA должна быть null.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/zapret2-management-$CODE"
BACKUP="/var/lib/xgw/handoff/zapret2-management-$CODE"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
UNIT=xgw-zapret2-management-rollback
bash docs/helpers/t11_management_install.sh "$CODE"
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" - "$BACKUP" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads((Path(sys.argv[1]) / "manifest.json").read_text())
assert len(rows) == 7
for row in rows:
    actual = hashlib.sha256(Path(row["target"]).read_bytes()).hexdigest()
    assert actual == row["new_sha"], row["target"]
    print(row["target"], actual)
PY
sudo sha256sum -c "$D/config-original.sha256"
```

Если установщик отказал, не запускать его поверх прежнего каталога. Проверить,
был ли armed таймер и существует ли restore.sh. Если apply начался — rollback
по §7. Если остановился до apply — сохранить блокер и убедиться в работе старой
версии. При prepare-отказе службы не должны быть остановлены. Бэкапы не удалять.
Проверить VPN/панель и заново открыть `xgw gui` от пользователя, без sudo.

## 4. Проверки управления при off/off

Войти штатно в XGW, открыть `/zapret2` в вкладках A/B. DevTools Network держать
приватным. Готовые функции для Console авторизованной вкладки:

```js
const zget = async () => (await (await fetch('/api/zapret2/overview',
  {cache: 'no-store', credentials: 'same-origin'})).json()).zapret2;
const zpost = async (action, body) => (await (await fetch('/api/zapret2/' + action, {
  method: 'POST', credentials: 'same-origin',
  headers: {'Content-Type': 'application/json', 'X-XGW-Panel': '1'},
  body: JSON.stringify(body)
})).json());
```

Каждый пункт выполнить отдельно, после записи сверять off/off и inactive воркеров.

| № | Действие | Ожидается |
|---|---|---|
| M01 | В приватном окне до входа GET overview, POST settings с `{}` | 401, политика прежняя |
| M02 | После входа POST без X-XGW-Panel | 403, файл прежний. Чужой Host/Origin проверены опубликованным HTTP-тестом |
| M03 | Сравнить API state/overview и Proton | Совпадают config_key, can_edit/can_off, blockers, режим/домены. Compare недоступен с причиной |
| M04 | Открыть настройки A/B. В A сохранить retry=120 (если уже 120 — 180). В B изменить домены, выждать два опроса, сохранить | A saved. B сохраняет введённый текст и старый expected, получает conflict, A не перезаписана |
| M05 | В B нажать «Перечитать настройки», подтвердить | Поля из текущей политики, конфликт снят, URL пустые |
| M06 | K=(await zget()).config_key, R=(await zget()).retry_seconds; zpost('settings',{expected:K,settings:{retry_seconds:R}}) | unchanged, mtime_ns и SHA panel одинаковы до/после, новых worker нет |
| M07 | С текущим expected отдельно отправить settings с engine:'off', binary:'/tmp/tool', queue_num:201, retry_seconds:true, domains:[], mode:'standalone' | Каждый invalid, SHA прежняя. mode:'compare' в команду mode тоже invalid |
| M08 | При off сохранить два синтетических URL `https://www.youtube.com/watch?v=xgw-test-secret` и `https://r1.googlevideo.com/videoplayback?sig=xgw-test-secret` | Только запись. В POST-ответе, GET state/overview и localStorage нет xgw-test-secret |
| M09 | При пустых полях URL изменить retry, сохранить. Потом явно удалить URL | Сначала probe_count=2, потом 0. Неполная пара отклоняется формой |
| M10 | Двойной клик Сохранить, затем обновление страницы | Только один POST, обновление его не повторяет |
| M11 | DevTools Offline, сохранение, возврат Online | Сообщение об ошибке/неизвестном результате и перечитывание GET, без повторного POST. Для реального таймаута допускается throttling, без остановок служб |
| M12 | Во время правки скрыть/вернуть вкладку; две темы, 390 px, клавиатура | Опрос сохраняет ввод/expected, скрытая вкладка не делает периодических GET, форма/фокус/ошибки читаемы |
| M13 | Proton Настройки, сверить selected_strategy API, сохранить допустимую правку | Стратегия доменов не заменена seqovl общего движка. Веб видит запись. Каталог, сортировка, анимация карты работают |

Для M01/M02 точные запросы из Console соответствующего окна:

```js
await fetch('/api/zapret2/overview').then(r => r.status);
await fetch('/api/zapret2/settings', {method:'POST',
  headers:{'Content-Type':'application/json'}, body:'{}'}).then(r => r.status);
```

Для M06 до/после снять метаданные без вывода содержимого:

```bash
sudo "$PY" - "$PANEL" <<'PY'
import hashlib, sys
from pathlib import Path
p = Path(sys.argv[1])
print(p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
PY
```

Не включать режимы с синтетическими URL. Нарушение доступа, целостности или
повторная команда — FAIL, rollback без сетевого опыта. Если таймаут воспроизвести
не удалось, отметить NOT_RUN именно таймаута, не выдавать за его проверку Offline.

## 5. Живые режимы через интерфейс

Подтвердить, что тестовый Chrome без прокси захватывается XGW, QUIC отклоняется,
правило устройства/пула не перекрывает выбранные домены. В том же браузере
открыть `https://example.com/` и прежний контроль определения VPN-выхода.
Адреса выхода остаются приватными. Не заменять браузерный контроль общим счётчиком.

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
sudo touch "$BACKUP/network-test-started"
sudo systemctl restart "$UNIT.timer"
sudo systemctl is-active "$UNIT.timer"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" python3 -m xgw.desync.route_evidence snapshot > "$D/$1.json"
}
delta() {
  python3 -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
snap initial
```

1. **Standalone.** В форме сохранить hostfakesplit_md5, выключенную HTTPS-опцию,
   пустые пробы и шесть доменов: domain:youtube.com, domain:googlevideo.com,
   domain:youtubei.googleapis.com, domain:youtube-nocookie.com, domain:ytimg.com,
   domain:ggpht.com. Нажать «Без VPN», сначала отменить подтверждение — POST нет.
   Затем подтвердить. Предупреждение объясняет остановку VPN и прямой выход
   остального трафика. Ждать свежие policy_matched/active максимум 120 с.
   Сверить without_vpn=true, локальный Xray, отсутствие VPN-мостов, владельца
   очереди. Провести короткое видео по §6. Выключить режим кнопкой, дождаться
   освобождения очереди и проверить **новое** соединение через VPN.
2. **Selective.** В off выбрать multisplit, включить HTTPS-проверку YouTube/CDN,
   сохранить реальные свежие URL страницы и CDN `/videoplayback` из DevTools
   того же Chrome. Страница первая, CDN второй. URL из Standalone передавать
   только приватно, проверить свежесть. SABR POST не воспроизводить как GET тела
   ролика. В этой опции служебный gate проверяет завершённый HTTPS 200/204 CDN,
   не объём медиа. Нажать «Домены через zapret2», ждать active максимум 120 с.
   При youtube_cdn_probe_failed разрешена **одна** замена CDN-ссылки свежей
   через форму и повтор после off. Пороги не менять. Если ссылки нет — BLOCKED_PROBE.
3. При active Selective провести короткое видео и **одновременный** браузерный
   контроль через VPN. Раздельно записать доступность сайта и его маршрут.
   Веб не должен объявлять успех видео на основании HTTPS-gate.
4. Выключить кнопкой. До нового снимка off не подтверждён. Дождаться
   policy_matched/off и пустой очереди, открыть новый сеанс YouTube через VPN.
   В этом задании SIGKILL worker не нужен — проверяется команда off.

Все переключения только через кнопки/API этого задания. Не выполнять
set_phase/set_standalone из архивных ТЗ. Исходный engine=off сохраняется.
При engine=auto off может возобновить общий обработчик, что должно быть объяснено
в подтверждении. Эту ветку покрывает опубликованный тест, на рабочем шлюзе engine не менять.
При невосстановлении сети — сразу §7.

## 6. Видео и доказательства

Ролик `8plwv25NYRo`, обычный видимый Chrome, вручную 720p, 1×, без автоперехода.
Использовать [готовый сниппет и команду сводки](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome),
только раздел замера, без его команд установки/маршрутизации. Сборщик не менять.
Flash сама запускает JS, нажимает Play и сохраняет телеметрию.

Перед Play запустить сниппет и поставить метку play. Vision подтвердить кадр,
отсутствие рекламы/диалога и движение позиции. Через 30 с проверить новые rows
с продвижением позиции. Для **каждого режима ≥150 с пригодного просмотра**.
Пауза UI не является просмотром или сетевым отказом.

Снять `snap standalone-before`/`snap standalone-after` и аналогично Selective,
сохранить `delta standalone-before standalone-after` и соответствующую вторую
дельту. Снимки делать до закрытия Chrome/перезапуска Xray. DevTools Network/CDP
должен показать свежие SABR GET/POST, время, HTTP, протокол и полученные байты.
HAR/NetLog, подписанные URL и IP остаются приватными. При недостаточной привязке,
перезапуске счётчиков или мешающем фоне — `MEDIA_PATH=PARTIAL`, даже при хорошем видео.
Рост общего Xray сам по себе не доказывает VPN-маршрут контрольного сайта.
Для Selective отсутствие одновременного контроля — отдельный FAIL/BLOCKED,
его не закрывать данными прошлого отчёта.

Если оба коротких режима прошли и окно позволяет, Selective 15 минут пригодного
просмотра + перемотка минимум на 6 минут + 5 минут просмотра. Перед началом
обновить таймер. Фазы разделить метками/снимками/сводками. Иначе длинный опыт NOT_RUN.
Без tcpdump. Сбор сниппета ограничен 30 минутами. После экспорта закрыть тестовый
Chrome через GUI, убедиться, что фоновых записей не осталось.

## 7. Обязательный возврат

Если терминальный сеанс потерян или установщик остановился после apply, восстановить
переменные так (python.path создаётся до таймера/замены). Отсутствие python.path
при прежних файлах означает, что apply ещё не начинался:

```bash
CODE=f3de0052a4a41a549980a3264d8084887bf4c9b4
BACKUP="/var/lib/xgw/handoff/zapret2-management-$CODE"
HELPER="/opt/xgw/handoff/zapret2-management-$CODE/code/docs/helpers/desync_batch1_install.py"
PANEL=$(readlink -f /etc/xgw/panel.json)
PY=$(sudo cat "$BACKUP/python.path")
UNIT=xgw-zapret2-management-rollback
```

При PASS оставить код, вернуть panel побайтово:

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" accept
```

При регрессии вернуть код и конфигурацию:

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
```

При истечении таймера прекратить опыт, проверить restore-completed и фактическое
состояние. Не продолжать тестирование откатившегося слоя. Если возврат завершился
ошибкой, таймер не отменять, запросить доступ/помощь по конкретному отказу.

```bash
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
sudo cat /proc/net/netfilter/nfnetlink_queue
df -h /home /var/lib/xgw
```

Ожидаются off/off, inactive обоих worker, пустая очередь, VPN, новый браузерный
контроль и панель 200. Сверить файлы по new_sha при accept или old_sha при rollback,
включая GUI. Перезапустить только окно GUI от пользователя. После сверки остановить
`sudo systemctl stop "$UNIT.timer"`, убедиться в inactive. Бэкап оставить.

## 8. Автопубликация только отчёта

Результаты отдельно для подготовки, установки, M01–M13, Standalone, Selective,
короткого/длинного видео, маршрута, VPN-контроля, возврата. В каждом PASS/FAIL/
BLOCKED/NOT_RUN и конкретное свидетельство. Указать CODE, 7 хэшей, ревизии,
пригодные секунды 720p, паузы/stalls/буфер/дельты и финальную политику. Через vision
описать обе темы/390 px. Секреты из JSON, журналов и снимков не публиковать.

Даже при блокере создать новый отчёт, не перезаписывать старый BLOCKED_BUILD.
Flash изменяет только отчёт, планы по результатам обновляет Codex.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t11-management-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-zapret2-management-r2.md"
# Flash сама заполняет только REPORT фактическими результатами.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify published zapret2 management on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке fetch/rebase и обычный push, без force. Сверить удалённый SHA, сообщить
ссылку и состояние машины. Не писать о принятии управления/обхода, если нужные
шаги не выполнены.
