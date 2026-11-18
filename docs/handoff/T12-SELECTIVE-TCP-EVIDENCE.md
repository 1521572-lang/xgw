# T12 — ответные данные на соединении Selective

ThinkCentre, Ubuntu 24.04 LTS. Код для проверки — `78e15cdea7a74379103bb3b2a5d4253c2755dbc2`.
Последний отчёт принял обновление панели. В одной попытке TLS к странице
`/t/terms` истёк за 10,1 с. В другой страница прошла, а обе попытки CDN
истекли за 20,2 с суммарно. Во время проб разрешение выхода было открыто,
обработчик оставался жив, счётчик NFQUEUE рос и дропы не наблюдались.
Обычные GET с хоста прошли, фактические IP и пути двух запросов не сопоставлены.
[Отчёт замера очереди](../reports/2026-11-18_desync-t12-selective-probe-watch.md).

Сборщик из checkout добавляет счётчики TCP-сокетов, которые совпали с меткой
выхода XGW и портом 443. На ThinkCentre остаются принятые Python и JS.
Flash сама проводит техническую проверку, открывает Chrome, сверяет экран
через vision, выполняет возврат и публикует отчёт. При отсутствии терминала,
sudo или GUI запроси доступ. Код и испытательные скрипты подготовлены Codex.
Сбор использует метаданные `ss` и счётчики ядра без захвата пакетов.
[Документация ss](https://man7.org/linux/man-pages/man8/ss.8.html).

## 1. Подготовь проверку и возврат

Начни в чистом checkout и проверь штатный VPN, панель, off/off и остановленные
воркеры. Подготовь обычный Chrome с выключенным QUIC и DevTools. Контрольный
сайт вне списка YouTube должен открываться через наблюдаемый VPN-выход.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=78e15cdea7a74379103bb3b2a5d4253c2755dbc2
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-tcp.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
python3 -m pytest -q tests/test_selective_probe_watch.py tests/test_desync_route_evidence.py
bash -n docs/helpers/t11_management_restore.sh
ss -V
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
sudo cmp "$PACKAGE/zapret2.py" src/xgw/zapret2.py
sudo cmp "$PACKAGE/watch/checks.py" src/xgw/watch/checks.py
sudo cmp "$PACKAGE/ui/zapret2.js" src/xgw/ui/zapret2.js
```

Для pytest подойдёт имеющийся dev-venv. При расхождении установленного слоя,
падении целевых тестов или недоступности исходного VPN запиши блокер и
опубликуй отчёт по §4. Перед изменением настроек поставь таймер возврата.

```bash
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
UNIT="xgw-selective-tcp-$(date +%s)"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-tcp.XXXXXXXX)
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 docs/helpers/t11_management_restore.sh "$BACKUP/restore.sh"
sudo touch "$BACKUP/network-test-started"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  "$PY" -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
QUEUE=200
watch_probe() {
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds "$2" --socket-stats >"$D/$1.jsonl" &
  WATCH_PID=$!
}
```

Укажи в `QUEUE` фактический номер, если он отличается. Локальные JSONL содержат
IP и идентификаторы сокетов. Для отчёта обозначай адреса как A, B и так далее.
Граница времени одного сбора — до 180 с.

## 2. Соотнеси таймаут с TCP

1. Сохрани в панели `multisplit`, шесть доменов из подстановки, повторную
   проверку через 120 с, HTTPS-опцию, страницу `/t/terms` и актуальный CDN из
   DevTools. Дождись off/off и пустого `blockers.selective`. Закрой плеер,
   чтобы проба оставалась единственным тестовым источником соединений YouTube
   при старте. Зафиксируй начало фонового окна. Выполни `snap vpn-before` и
   `watch_probe start-1 90`. После первой строки запусти Selective кнопкой.
2. При **active** сразу начни §3, пока сборщик работает. При **fallback** сразу
   запиши результат контрольного GET с хоста для того же URL. Затем дождись
   конца сбора командой `wait "$WATCH_PID"`. Сопоставь время probe
   (`started_at` и `elapsed_ms`, у CDN также `first_tls_timeout_ms`) с `tcp_at`.
   В окне пробы ищи новый socket cookie, признаки приёма, подтверждения отправки
   и ретрансляции. Сохрани состояние TCP, `bytes_sent`, `bytes_acked`,
   `bytes_received`, `data_segs_in`, `bytes_retrans`, `retrans_total` и
   одновременно наблюдавшиеся gate, очередь и дропы. Встроенный повтор CDN
   выдели в отдельное окно. При нескольких кандидатах либо смене адреса запиши
   привязку как неоднозначную. Быстрая успешная проба может целиком пройти между
   двумя замерами.
3. Если у таймаута найден один подходящий сокет, для контрольного запроса
   используй тот же целевой IP и тот же HTTPS-хост. Пример ниже сохраняет полную
   ссылку внутри терминала и передаёт её curl через stdin. Выполняй при свежем
   URL и после закрытия прямого правила. Если сопоставить IP нельзя, запиши
   контроль как GET по тому же URL с недоказанным совпадением IP.

   ```bash
   read -r -p 'HTTPS host: ' TARGET_HOST
   read -r -p 'IPv4 from the matching socket: ' TARGET_IP
   read -rs -p 'Private HTTPS URL: ' TARGET_URL
   printf '\n'
   if [[ "$TARGET_HOST" =~ ^[a-zA-Z0-9.-]+$ &&
         "$TARGET_IP" =~ ^[0-9.]+$ && "$TARGET_URL" == "https://$TARGET_HOST/"* &&
         "$TARGET_URL" != *'"'* && "$TARGET_URL" != *\\* ]]; then
     CURL_RC=0
     printf 'url = "%s"\n' "$TARGET_URL" |
       curl -q --config - --noproxy '*' --http1.1 --max-time 12 --silent \
         --resolve "$TARGET_HOST:443:$TARGET_IP" --output /dev/null \
         --write-out 'http=%{http_code} tls=%{time_appconnect}s total=%{time_total}s\n' ||
       CURL_RC=$?
     printf 'curl_rc=%s\n' "$CURL_RC"
   fi
   unset TARGET_URL TARGET_HOST TARGET_IP
   ```

   Для срочного контроля, пока результат сборщика разбирается, достаточно
   обычного запроса к URL. Контроль с конкретным IP сохрани отдельной строкой.
   Укажи способ проверки маршрута хоста, иначе отметь его как неизвестный.
   Запиши время между таймаутом и контролем. При ошибке curl зафиксируй код
   и продолжи опыт. Проверь один новый сеанс после off со свежей CDN-ссылкой,
   сохрани в `start-2.jsonl`. После двух неудачных запусков перейди к §4.

Для результата по каждому таймауту выбери наблюдение из таблицы. Эти выводы
относятся к сокету ядра в момент замера. Причина отсутствия принятого ответа
может лежать на разных участках маршрута.

| Наблюдение в окне TLS | Что указать в отчёте |
| --- | --- |
| Один новый сокет, `bytes_received` и `data_segs_in` равны нулю, есть ретрансляции | TCP-данные ответа на наблюдаемом сокете не появились. Отдельно укажи, росло ли число подтверждённых байтов. |
| `bytes_received` или `data_segs_in` растут, TLS всё равно истекает | Ответные данные дошли до сокета. Для следующей работы нужны граница TLS и обработка ответа дальше по цепочке. |
| Пустая выборка, неизвестные счётчики, несколько кандидатов или недоступный `ss` | `TCP_EVIDENCE=INCONCLUSIVE`, укажи точный пробел. |

## 3. Если режим стал активен

Сразу сними короткую пару Xray с очередью и свежим запросом CDN. Проверь
параллельный VPN-выход для отдельного сайта. Используй CDP и запись
плеера в обычном Chrome. Укажи применённую ревизию и фактическое правило.
[Критерии подтверждения маршрута](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).

Дождись двух перепроверок на той же ревизии и сохрани применённый итог проб.
Для замера TCP вокруг каждой перепроверки запускай `watch_probe recheck-1 90`
и затем `watch_probe recheck-2 90` за 25–30 с до ожидаемой пробы. Для каждой
записи дождись завершения сборщика перед следующим запуском. При устойчивом пути и остатке
≥35 минут проверь 15 минут пригодного просмотра в 720p, перемотку на ≥6 минут
и ещё 5 минут. Отметь фазы с новыми CDN-запросами, паузы, падение качества
и факт просмотра через vision. [Телеметрия плеера](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome).

## 4. Возврат и автоматическая публикация

Выключи режим в панели, подтверди новый сеанс YouTube через VPN. Дождись
остановки сборщика. Оставь не менее 10 минут на возврат. Если таймер уже
сработал, проверь `restore-completed` и состояние ниже без повторного запуска
скрипта.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

После подтверждения off/off, VPN, панели и исходных хэшей останови таймер
`sudo systemctl stop "$UNIT.timer"`. Закрой тестовый Chrome. При потере терминала
сведения для возврата есть в `restore-location.txt`.

Автоматически опубликуй только обезличенный технический отчёт даже при блокере.
Укажи SHA, результаты §1–4, новые TCP-наблюдения по каждой пробе, совпадение
IP с контролем, `RETRY_LIVE`, `MEDIA_PATH`, пригодные секунды видео и возврат
шлюза. Оставь URL, сырые JSONL, IP и данные браузера только в приватном каталоге.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-tcp-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-tcp-evidence.md"
test ! -e "$REPORT"
# Заполни отчёт по выполненным шагам, включая блокеры.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify TCP evidence for Selective probes on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch, rebase и обычный push. Сообщи ссылку и состояние шлюза.
