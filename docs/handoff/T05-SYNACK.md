# T05 — проверка SYN/ACK выбранного маршрута zapret2

Ubuntu **24.04 LTS**, ThinkCentre. База на машине подтверждена
[отчётом Selective](../reports/2026-11-16_desync-selective-vpn-control.md). Исполнитель сама
запускает терминал, браузер и проверки, использует vision и автоматически публикует отчёт.
Если недоступны терминал, sudo или рабочий стол, запроси доступ. Оставь оба режима исходно
off/off до начала фаз. В этом проходе проверяем отдельный флаг `selected.observe_synack`.

При включённом флаге исходящий IPv4 SYN локального соединения на TCP/443 с меткой
`xgw-zapret2` и открытым gate взводит бит conntrack на этапе postrouting. На INPUT правило
отбирает обратный tracked SYN/ACK с этим битом и живым gate, сбрасывает бит, увеличивает
счётчик и передаёт пакет в ту же NFQUEUE. Ограничитель входа — 256 пакетов/с с запасом 128.
Остальные входящие пакеты обходят это правило. В ранней IPv6-цепочке метка выбранного выхода
сохраняется до fail-closed барьера. Выбранный внешний маршрут остаётся IPv4. Стратегия
`hostfakesplit_md5` и Lua в этом опыте прежние.

На Linux правило `ct packets` может само включать учёт conntrack при загрузке. Для проверки
рукопожатия используются флаги TCP и бит conntrack. Параметр `nf_conntrack_acct` и offload
снимай до и после, без штатного переключения. Начальные пакеты с данными, IPv6 WAN и
измерение пользы AutoTTL остаются отдельными опытами T05/H01/H04.
[Код Linux nft_ct](https://raw.githubusercontent.com/torvalds/linux/master/net/netfilter/nft_ct.c),
[приоритеты nftables](https://wiki.nftables.org/wiki-nftables/index.php/Netfilter_hooks).

## Подготовка и проверка правил на ядре стенда

Проверь рабочий VPN, исходное состояние off/off, пустую очередь, службы и локальный доступ
для отката. Сохрани приватно nft/марки включая сторонние таблицы, ip rules, счётчики очередей,
`ethtool -k` реального WAN, `nf_conntrack_acct` и хэши конфигов. Убедись, что сторонние
правила conntrack не используют бит `0x10000000` для этих соединений. Используй dev-venv.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=157a6fd
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-desync-t05.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
python3 -m pytest --portable tests/test_zapret2.py tests/test_desync_schema.py \
  tests/test_zapret2_panel.py tests/test_desync_standalone.py tests/test_desync_worker.py
PYTHONPATH="$D/source/src" python3 - > "$D/synack-check.nft" <<'PY'
from xgw.zapret2 import guard_blocks

print("table inet xgw_t05_check {")
for block in guard_blocks(201, observe_synack=True):
    print("\n".join(block))
print("}")
PY
sudo unshare --net nft --check -f "$D/synack-check.nft"
```

Парсинг здесь выполняет реальное ядро ThinkCentre в отдельном сетевом namespace. Если
`nft --check` возвращает ошибку, сохрани строку и пока не устанавливай слой. После проверки
убедись, что таблицы `xgw_t05_check` в основном namespace нет.

## Установка четырёх файлов и независимый возврат

Сверь пути с ExecStart и рабочим PID. Слой рассчитан на T04 с принятым VPN-control. Проверь
исходный off/off. Не используй старые каталоги бэкапа для нового манифеста.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
PID=$(systemctl show xgw.service -p MainPID --value)
PY=$(sudo readlink -f "/proc/$PID/exe")
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/desync-t05-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t05-$CODE"
FILES=(src/xgw/config.py src/xgw/desync/schema.py src/xgw/net/nft.py src/xgw/zapret2.py)
UNIT=xgw-desync-t05-rollback
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
sudo "$PY" "$HELPER" prepare --nft-t05 --payload "$PAYLOAD" --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" > "$D/config-before.sha256"
sudo install -m 0700 /dev/stdin "$BACKUP/restore.sh" <<'SH'
#!/bin/bash
set -euo pipefail
py=$1
helper=$2
backup=$3
panel=$4
mode=$5
exec 9>"$backup/restore.lock"
flock 9
systemctl stop xgw.service
temp=$(mktemp "$(dirname "$panel")/.xgw-t05.XXXXXXXX")
cp --preserve=mode,ownership -- "$backup/panel.before" "$temp"
mv -fT -- "$temp" "$panel"
if [ "$mode" = rollback ]; then
  "$py" "$helper" rollback --nft-t05 --backup "$backup"
else
  systemctl start xgw.service
fi
if [ -e "$backup/network-test-started" ]; then
  timeout 180 /usr/local/bin/xgw apply --now
fi
SH
sudo systemd-run --unit="$UNIT" --on-active=45m /bin/bash "$BACKUP/restore.sh" \
  "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply --nft-t05 --backup "$BACKUP"
sudo sha256sum -c "$D/config-before.sha256"
sudo touch "$BACKUP/network-test-started"
sudo systemctl restart "$UNIT.timer"
sudo systemctl list-timers "$UNIT.timer"
```

Проверь SHA всех четырёх файлов по манифесту, отсутствие `zapret2_reply`, штатные службы и
VPN до первого изменения политики. Если таймер сработал, прерви опыт и проверь состояние.

## A/B в Standalone и отрицательные контроли

Проверь, что очередь 201 свободна. Выбери один HTTPS endpoint с подтверждённым телом и
отдельный контрольный домен. Рекомендуемая пара — URL Википедии из отчёта Selective и
другой HTTPS домен. Сначала флаг off, затем on, затем снова off. Для включения:

```bash
set_probe() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$1" <<'PY'
from dataclasses import asdict
from pathlib import Path
import sys

from xgw import config, managed
from xgw.desync import schema

path, phase = Path(sys.argv[1]), sys.argv[2]
assert phase in {"off", "baseline", "synack"}
current, _ = config.load(path)
policy = schema.migrate(asdict(current.zapret2))
policy["selected"].update(mode="off" if phase == "off" else "standalone",
                          domains=["full:ru.wikipedia.org"], probe_urls=[],
                          strategy="hostfakesplit_md5", observe_synack=phase == "synack")
policy["runtime"]["queue_num"] = 201
policy["engine"]["engine"] = "off"
policy = schema.migrate(policy)
managed.set_desync(managed.path_for(path), policy)
actual, _ = config.load(path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
```

1. Запусти `set_probe baseline`. Дождись активного gate и очереди. Выполни минимум три новых
   TCP-соединения к выбранному домену и одно к контрольному. Запиши результат HTTPS,
   счётчики исходящей очереди, worker PID/CPU/RSS и значения в
   `/proc/net/netfilter/nfnetlink_queue`. Подтверди отсутствие входной цепочки.
2. Запусти `set_probe synack`. Дождись новой политики, gate и подтверждённого владельца
   той же очереди по цепочке T03. Выполни минимум три новых TCP-соединения, без переиспользования
   сессии. Сними дельты двух правил в `zapret2_queue` и правила в `zapret2_reply` по
   `nft -a list chain inet xgw_guard ИМЯ`. На WAN запиши короткий приватный захват SYN/SYN/ACK
   по фактическому IPv4 endpoint, с TTL, флагом и портами. Сверь время, количество и успешное
   продолжение TLS. Зафиксируй дельты queue drops и CPU/RSS тем же способом, что в A.
3. С полностью загруженной страницей или длинным HTTPS-ответом проверь, что поступающие
   данные не двигают счётчик SYN/ACK. Повтори соединения к контрольному домену, чужой
   входящий трафик и IPv6 при доступности тестового IPv6 endpoint. У входной цепочки ожидается
   нулевая дельта на этих контролях. При отсутствии IPv6 WAN запиши `NOT_RUN` для живой фазы.
   Проверь на снимке структуры, что ранняя IPv6-цепочка оставляет метку до guard, без
   перенаправления пакета в Xray. Обратный повторный SYN/ACK отметь отдельно, если он реально
   наблюдался. Для синтетической проверки не посылай поддельные пакеты в рабочую сеть.
4. Прерви только MainPID выбранного worker и сверь исчезновение очереди, закрытие gate,
   остановку прямого пути к домену и доступность контрольного сайта. Сними счётчики после
   закрытия и подтверждение восстановления с новым поколением. Верни `set_probe off`.
5. Если пункты 1–4 прошли, на короткой проверке используем тот же YouTube и обычный Chrome,
   что в [прошлом отчёте](../reports/2026-11-16_desync-t04-telemetry-compare.md). Вместо одного
   `full:` подставь из T04 список YouTube-доменов и включи `observe_synack`. Проверь ≥2 минут
   720p, новый поток media и outbound `xgw-zapret2`, SYN/ACK и отсутствие VPN-мостов.
   Если темп воспроизведения ухудшился, повтори коротко с флагом off и теми же условиями.
   Сохрани раздельно воспроизведение, маршрут и пакетную приёмку. AutoTTL/late stall не
   оценивай по одному счётчику.

## Возврат и автопубликация

Заверши опыт до истечения таймера. При PASS оставь установленный слой с исходной политикой.
При регрессии выбери `rollback`. Сверь SHA, off/off, VPN, службы, очередь, отсутствие цепочки
ответа, sysctl и offload. Затем останови таймер.

```bash
ACTION=accept  # при регрессии подставь rollback
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$ACTION"
sudo sha256sum -c "$D/config-before.sha256"
# Сверь VPN, off/off, очередь, sysctl и offload перед следующей командой.
sudo systemctl stop "$UNIT.timer"
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t05-synack-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t05-synack.md"
# Сама заполни REPORT, даже если приёмка частичная или остановилась.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: verify T05 SYN ACK on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

В отчёте укажи SHA, исход каждой фазы, дельты и размер выборки, оставленный режим и что
подтвердилось на стенде. Публикуй агрегаты, полные сетевые записи оставь приватно. При гонке
выполни fetch/rebase и обычный push. В итоговом сообщении укажи SHA отчёта.
