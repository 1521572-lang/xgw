# T08/H06 — история очереди и повторный импорт Chrome

Стенд — ThinkCentre, Ubuntu **24.04 LTS**. Прочитай [отчёт кэша](../reports/2026-11-16_desync-t08-cache.md)
и [проверку передачи очереди T03](../reports/2026-11-15_desync-t03.md). Исполнитель сама
запускает команды, пользуется Chrome и vision, сверяет результаты и публикует отчёт.
При отсутствии терминала, sudo или GUI запроси доступ к нужному инструменту.

## 1. Подготовка и переоценка T08

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=fea0e66
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t08-events.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_cache.py tests/test_desync_worker.py \
  tests/test_zapret2.py tests/test_desync_standalone.py tests/test_zapret2_panel.py
```

Сверь исходные mode/engine, PID, очередь, хэши конфигов, offload, acct и доступность VPN.
Для открытого tcpdump пользуйся [порядком T07](T07-SHADOW.md#1-подготовка-и-прежний-захват).
Если он остаётся активным, укажи состояние и действия администратора. Новый WAN-захват не нужен.

Возьми сохранённые сырые записи A′ и B′ из T08 и их локальные `context.json`. Сверь
распределение интервалов `t_s` и временные метки Network. В отчёте фигурирует
15-секундная гранулярность, а непрерывный ряд импортера допускает интервалы до 2,5 с.
Проверь, к какой записи относилось число. Сохраняй реальные пропуски и временные метки.
Повтори импорт в новый приватный каталог по [командам T08](T07-T08-CACHE.md#2-реальные-записи-chrome).

Сравни показанный браузером прогресс и 720p с `content_progress_seconds`,
`eligible_seconds`, `estimated_playing_seconds`, сигналами shadow и новым исходом.
Импорт v2 при скорости 1× учитывает суммарный прогресс. Недостаточное покрытие или
неподтверждённый слабый прогресс исключают строку, а подтверждённое истощение
≥15 с или качество ниже порога дают `playback_failed`. Проверь, что старые записи
без `measurement_version` игнорируются при rebuild и что тот же исходный захват
можно переимпортировать в v2. У каждого профиля в предыдущем отчёте по одному раунду,
поэтому даже два удачных переимпорта не должны вместе дать подсказку одному профилю.
H02 остаётся открытым, если новых адресов CDN нет.

## 2. Установка журнала

Слой включает только четыре файла. Пути сверь с ExecStart и рабочим PID. Используй
[порядок установки и restore T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат),
заменив `--nft-t05` на `--worker-events` **включая restore.sh** и пути на следующие.
Перед продолжением таймер должен быть активен, а исходные конфиги сохранены.

```bash
FILES=(src/xgw/daemon.py src/xgw/desync/worker.py src/xgw/nfqws2.py src/xgw/zapret2.py)
UNIT=xgw-desync-t08-events-rollback
PAYLOAD="/opt/xgw/handoff/desync-t08-events-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t08-events-$CODE"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
```

Если проверка SHA установленной базы не проходит, укажи конкретный файл. Сверь его
происхождение с манифестами принятых слоёв. Рабочий код при неизвестном расхождении
оставь как есть, а независимый переимпорт заверши. После установки сверь 4 SHA, panel
и VPN. В свежем `/run/xgw/status.json` сними исходный журнал:

```bash
events() {
  python3 -c '
import json
from pathlib import Path
data = json.loads(Path("/run/xgw/status.json").read_text())
print(json.dumps({key: data[key] for key in
    ("updated", "zapret2_policy_key", "zapret2_reservation", "zapret2_worker_events")}))
'
}
events >"$D/events-off.json"
```

## 3. Приёмка на работающем шлюзе

Как в T03, переключай настройки через `managed.set_desync` с резервированием на
активном таймере. Для сравнения Epoch используй свежий снимок после того, как демон
обработал изменение. Подтверждай очередь цепочкой service MainPID → inode →
NETLINK_NETFILTER → NFQUEUE; поле событий отражает результат проверки, отдельный
вход в журнал ещё не подтверждает воспроизведение видео.

1. **Off → Engine.** Включи engine auto при selected off, `hostfakesplit-md5`,
   очередь 200 или 201, если свободна. Проверь `reserved` и `owner_verified` с тем же
   generation и revision. Идентичная перезапись policy и несколько опросов не дают
   повторной записи. Если разрешена другая свободная очередь, переключи номер и
   подтверди `released` перед `reserved` следующего поколения.
2. **Отказ владеющего воркера.** После проверки PID и очереди вызови SIGKILL только
   для MainPID экспериментального `xgw-nfqws2.service` по процедуре T03.
   Проверь `owner_unverified` при первой наблюдённой потере, новый generation и
   `owner_verified` после восстановления. Если контроллер снял воркер по другому
   подтверждённому пути до очередной проверки владельца, укажи это отдельно.
   Основной xgw и Xray не являются целью сигнала.
3. **Engine → Standalone → Off.** Передай ту же очередь `xgw-zapret2.service`
   с `hostfakesplit_md5` по [порядку H05](T06-H05.md#2-установка-и-пары-в-обычном-chrome).
   Сними переходы и цепочку владельцев. В обычном Chrome подтверди ≥120 с YouTube
   без VPN, свежий SABR и дельту `xgw-zapret2`. При наличии чистого одноконечного
   ряда можно переимпортировать его в v2, сохранив отдельный контекст контроля.
   Верни off/off и проверь `released`, пустую резервацию и штатный VPN.
4. **Предел и перезапуск.** Проверь максимум 64 события, монотонный `seq` и счётчик
   `discarded` переносимым тестом. Живые переключения оставь ограниченными указанной
   матрицей. Сверь, что в событиях только phase, seq, at, unit, queue, generation и
   policy_key, без доменов, PID клиентов или сырых логов. После штатного restore
   с остановкой и стартом демона сверь новый `epoch`; повторное использование
   номеров generation относится уже к новому запуску. `policy_key` события относится
   к конфигурации на момент резервирования; при совместимом reload текущая ревизия
   в status может измениться, а прежний worker сохраниться.

История публикуется в существующем атомарном снимке. Скорость и пригодность для
UDS, backlog и pin/reset проверяются отдельным этапом.

## 4. Восстановление и автоматическая публикация

Используй restore `accept` только после успешной проверки слоя, при регрессии —
`rollback`. Сверь хэши, off/off, VPN, пустую очередь, acct/offload и таймер. Полный
status, Network, адреса, настройки и снимки оставь локально. Опубликуй наблюдённые
переходы, результат переимпорта, сетевой контроль и блокеры, включая частичные итоги.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t08-worker-events-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t08-worker-events.md"
# Сама создай REPORT с проверенным SHA и оставленным состоянием.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify worker event history and Chrome reimport on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push.
