# T05 — первые ответы TCP и проверка AutoTTL

На ThinkCentre с Ubuntu **24.04 LTS** уже принят IPv4 SYN/ACK для выбранного маршрута.
Слой установлен, исходная политика off/off и VPN восстановлены. [Отчёт SYN/ACK](../reports/2026-11-16_desync-t05-synack.md).
Продолжение проверяет ограниченный входящий диапазон и фактический TTL пакетов.
Исполнитель сама работает в терминале и браузере, использует vision и публикует отчёт.
Если не хватает доступа к терминалу, sudo или GUI, запроси его.

## 1. Короткий опыт на ядре ThinkCentre до изменения шлюза

В чистом checkout закрепи полный SHA после fetch ветки `integration/zapret2-batch1`.
Создай отдельный worktree. На машине используй существующий dev-venv. Сохрани исходное
значение `nf_conntrack_acct`, offload, состояние служб и очереди в основном namespace.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=aca8fa8
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t05-replies.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
python3 -m pytest --portable tests/test_zapret2.py tests/test_desync_schema.py \
  tests/test_zapret2_panel.py tests/test_desync_standalone.py tests/test_desync_worker.py
sudo timeout --kill-after=15s 180s bash docs/helpers/desync_t05_ttl_lab.sh "$D/ttl-lab"
```

Скрипт создаёт четыре временных сетевых пространства на реальной машине с двумя
маршрутизаторами между тестовым клиентом и HTTPS-сервером. Маршрутов в интернет нет.
Используется установленный nfqws2 1.0.7, Lua проверяется через `--intercept=0`. Скрипт
загружает настоящий nft в клиентском namespace и сверяет каждый загруженный ответ побайтово.
Перед продолжением проверь очистку namespaces `xgwttl-*` этого запуска и отсутствие изменений
основной сети. Если скрипт остановился, сохрани этап и только необходимые обезличенные строки.

В приватных `*.worker.log` сравни `XGW_T05_TTL`: поле `track_ttl` населено из conntrack
zapret2, `predicted` — расчёт Lua, ноль обозначает отсутствие значения. По PCAP клиента и
сервера сверяй реальный TTL, направление, SYN/ACK, TCP MD5 option и доставку fake-сегмента.
Для `warm_off` Lua остаётся в `cold_on.worker.log`, отличай попытки по счётчику `hello` и
отдельным PCAP. Можно читать их локальным `tcpdump -nn -vv -r`; фиксируй агрегаты.

| Фаза | Контроль, который нужно подтвердить по данным |
|---|---|
| md5 | Базовый hostfakesplit с TCP MD5. Зафиксируй TTL и появление fake на стороне сервера |
| cold_off | Новый worker, SYN/ACK проходит мимо очереди. Проверь отсутствие TTL в Lua и сохранение MD5 |
| cold_on | Новый worker, начальный TTL сервера 64 и два hop. Сверь ответ 62, ожидаемый fake TTL 1 и факт доставки |
| warm_off | Тот же worker и IP, входная цепочка очищена, начальный TTL сервера 60. Сравни реальный входящий TTL и TTL из Lua, чтобы выявить использование кэша |
| changed_ttl | Новый worker, SYN/ACK снова в очереди, начальный TTL 60. Проверь ответ 58 и ожидаемый fake TTL 5. Если fake дошёл до сервера, это граница эвристики: реальный путь всё ещё два hop |
| early_reply8 | Целое тело 256 KiB, счётчик очереди ответов после SYN/ACK в пределах 1–8, дальнейшая передача проходит, потери отдельно |

Если фактические TTL расходятся с ожиданием, публикуй измеренные значения и объясни по
контролям. Рост счётчика NFQUEUE или расчёт Lua сам по себе не подтверждает доставку
fake-сегмента. Сравнение AutoTTL выполняется только в лабораторной сети. Пользу на линии
YouTube этот опыт не оценивает. Код ядра zapret2 может брать TTL из IP-кэша; это проверяется
контролем `warm_off`. [Источники включены в закреплённый код](../../third_party/zapret2).

## 2. Проверка входящего диапазона в XGW

Используй [порядок установки T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат)
с закреплёнными `BASE=aca8fa8` и `CODE` этого задания. Helper заменяет **пять** файлов:

```bash
FILES=(src/xgw/config.py src/xgw/desync/schema.py src/xgw/net/nft.py \
       src/xgw/net/capture.py src/xgw/zapret2.py)
UNIT=xgw-desync-t05-replies-rollback
PAYLOAD="/opt/xgw/handoff/desync-t05-replies-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t05-replies-$CODE"
```

Во всех вызовах helper используй `--nft-t05-replies`, включая rollback внутри restore.sh.
До запуска таймера сохрани исходное `sudo sysctl -n net.netfilter.nf_conntrack_acct` в
root-owned `"$BACKUP/acct.before"`. Добавь в начало restore.sh после получения блокировки
EXIT trap, восстанавливающий его даже при ошибке apply:

```bash
trap 'sysctl -qw "net.netfilter.nf_conntrack_acct=$(cat "$backup/acct.before")"' EXIT
```

Проверь исходный VPN, отсутствие занятых очередей, хэши конфигов и конфликты битов conntrack
`0x10000000` и `0x08000000`. Сверь манифест 5/5. Держи таймер активным. В функции
`set_probe` исходного T05 выбери `hostfakesplit_md5`, `mode=standalone`, тот же выбранный
HTTPS URL, `observe_synack=true`, `retry_seconds=60` для короткой проверки отказа, а также
`policy["selected"]["observe_reply_packets"]=8`. Сохраняй нормализованный `schema.migrate(policy)`.

1. При исходном `acct=0` проверь, что живой SYN/ACK сохраняется, предупреждение содержит
   `nf_conntrack_acct=1`, а выражений `ct reply packets` в основном ruleset нет. Если учёт
   на стенде исходно включён, проверка этого условия покрыта переносимым тестом.
2. После PASS лаборатории и только на время сетевой фазы включи учёт в основном namespace
   через `sudo sysctl -w net.netfilter.nf_conntrack_acct=1` либо используй уже включённый
   учёт. Сними гарантированно новый снимок правил переключением off → standalone. Открой
   три новых TCP/443-соединения к выбранному HTTPS endpoint с телом ≥256 KiB. Сними
   `nft -a list chain inet xgw_guard zapret2_reply` до и после каждого соединения.
   Для `ct reply packets 2-9` ожидается ≤8 пакетов на соединение, с ненулевой дельтой при
   наличии ответов в окне. ACK и другие ранние TCP-пакеты занимают позиции в бюджете;
   опиши, была ли в них полезная нагрузка. Длинная передача должна завершаться штатно
   после заполнения окна. Запиши CPU/RSS, queue drops и результат контрольного домена.
3. Через обычный Chrome проверь короткий YouTube 720p с тем же списком доменов T04.
   Сверь воспроизведение и свежую передачу на `xgw-zapret2`, затем верни off.
   При проблеме сравни тем же роликом с `observe_reply_packets=0`.
4. На контрольном HTTPS домене проверь закрытие gate при отказе worker и нулевой прирост
   очереди ответов после закрытия. Проверь штатный путь, восстановление и смену поколения.
   Сними `acct` до/после, offload, очередь и правила. Живой IPv6 отмечай только при наличии WAN IPv6.

## 3. Возврат и публикация

Выполни restore.sh с `accept` при PASS и `rollback` при регрессии. Сверь хэши, исходный VPN,
off/off, `acct`, offload и отсутствие worker, очереди и временных правил. Затем останови
`"$UNIT.timer"`. Если сетевую фазу пришлось сократить, публикуй результат лаборатории и
конкретный блокер. Пакетные записи и полный журнал оставь на стенде.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t05-replies-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t05-replies-autottl.md"
# Сама создай отчёт с SHA, измерениями по всем фазам и фактическим итоговым состоянием.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: verify bounded replies and AutoTTL on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Публикуй автоматически. При гонке сделай fetch/rebase и обычный push. Укажи SHA отчёта,
оставленный слой и состояние шлюза. Отдельно укажи, хватило ли захвата для следующих
гипотез H01 и H04.
