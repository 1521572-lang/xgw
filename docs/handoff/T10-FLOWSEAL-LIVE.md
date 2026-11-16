# T10 — сравнение Flowseal ALT9 и multisplit на живом YouTube

ThinkCentre, Ubuntu 24.04 LTS. Прочитай [приёмку импорта](../reports/2026-11-17_desync-t10-flowseal-import.md)
и [матрицу T09](../reports/2026-11-17_desync-t09-tournament.md). Импорт 44/44
и лаборатория HTTP/TLS 9/9 приняты. В первом опыте Flowseal ALT9 показал короткое
1080p, а прохождение самого медиа через очередь осталось недоказанным. Сейчас
нужно измерить воспроизведение и путь через штатный контроллер XGW.

Исполнитель сама запускает команды и обычный Chrome, проверяет видео через vision
и публикует отчёт автоматически. Если терминал, sudo или GUI недоступны, запроси
доступ. При блокере продолжи независимые проверки и опубликуй частичный результат.

## 1. Подготовка

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=$(git rev-parse 7f2628e)
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t10-live.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_flowseal.py tests/test_zapret2.py \
  tests/test_desync_schema.py tests/test_desync_worker.py
```

До установки сними хэши config.toml и panel.json, состояние очереди, worker и Xray,
offload, acct, доступность панели и VPN. Ожидаются off/off и свободная очередь.
Проверь свободное место и статус старого WAN-захвата. Используй CDP и счётчики,
новый WAN-захват не требуется. Возьми приватный исходный снимок `FLOW` из T10.
При отсутствии данных используй [подготовку из первого ТЗ](T10-FLOWSEAL-IMPORT.md#1-получение-кода-и-снимка-flowseal).

Подготовь ALT9 в области YouTube. В рантайм попадают проверяемые каталоги и ассеты
из снимка. Файл `plan.json` нужен для сверки и остаётся в приватном каталоге.

```bash
FLOW_SHA=2401b7a13837139b0265632464ba563dddbf80d8
LIVE_ROOT="/opt/xgw/flowseal/$FLOW_SHA"
python3 -m xgw.desync.flowseal --catalog-dir docs/helpers prepare \
  --source-dir "$FLOW" --profile 'general (ALT9)' --scope youtube --output "$D/alt9"
BASE_FILES=(src/xgw/desync/schema.py src/xgw/zapret2.py)
FILES=("${BASE_FILES[@]}" src/xgw/desync/flowseal.py src/xgw/desync/experiment.py)
```

Установи ассеты в новый каталог под root. Если каталог `LIVE_ROOT` уже был
подготовлен, оставь его на месте и проверь через preflight ниже. При неизвестном
владельце, ссылке или расхождении байтов не подменяй существующий комплект.

```bash
if ! sudo test -e "$LIVE_ROOT"; then
  sudo install -d -m 0755 /opt/xgw/flowseal
  stage=$(sudo mktemp -d /opt/xgw/flowseal/.t10.XXXXXXXX)
  sudo install -d -m 0755 "$stage/alt9/assets"
  sudo install -m 0644 docs/helpers/flowseal-youtube-source.json \
    docs/helpers/flowseal-translation.json "$stage/"
  sudo install -m 0644 "$D/alt9/LICENSE.txt" "$stage/alt9/"
  for asset in "$D/alt9/assets/"*; do
    test -f "$asset" && test ! -L "$asset"
    sudo install -m 0644 "$asset" "$stage/alt9/assets/"
  done
  sudo chmod 0755 "$stage"
  sudo mv -nT -- "$stage" "$LIVE_ROOT"
  sudo test ! -e "$stage"
fi
```

## 2. Установка слоя с независимым возвратом

Сверь фактические `PACKAGE`, `PY`, `CFG` и `PANEL` по запущенному сервису. Используй
[схему prepare/apply/restore T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат)
с флагом `--flowseal-t10` и переменными ниже. Подставь флаг во всех действиях,
включая rollback в `restore.sh`. Не удаляй прежние baseline-файлы.

```bash
PAYLOAD="/opt/xgw/handoff/desync-t10-flowseal-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t10-flowseal-$CODE"
UNIT=xgw-desync-t10-flowseal-rollback
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
for rel in src/xgw/desync/flowseal.py src/xgw/desync/experiment.py; do
  if sudo test -e "$PACKAGE/${rel#src/xgw/}"; then
    BASE_FILES+=("$rel")
  fi
done
git archive "$BASE" "${BASE_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
```

Helper должен принять только известное установленное состояние. Если два ранее
принятых файла отличаются от BASE, сначала определи их происхождение. При
неизвестном расхождении опубликуй блокер вместо обхода контроля. Перед apply
сохрани исходный panel, запусти таймер на 45 минут и проверь, что он активен.
После apply сверь хэши слоя, начальный off/off и рабочий VPN.

До смены режима сделай preflight ALT9 штатным кодом и обоими флагами `preflight.check`.
Выполни проверку в отдельном network namespace от root, как подтвердил отчёт T10.
Сверь, что worker argv совпадает с приватным снимком с переносом только путей
ассетов. Исполнитель может выполнить этот блок сразу после установки.

```bash
QUEUE=201  # если занята, задай свободную очередь до preflight
sudo unshare --net -- env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - \
  "$CFG" "$D/alt9/plan.json" "$LIVE_ROOT/alt9/assets" "$QUEUE" <<'PY'
import json
import sys
from pathlib import Path

from xgw import config, zapret2
from xgw.desync import flowseal, preflight
from xgw.net import cmd

path, snapshot, installed = map(Path, sys.argv[1:4])
cfg, _ = config.load(path)
cfg.zapret2.mode = "standalone"
cfg.zapret2.domains = list(flowseal.YOUTUBE_DOMAINS)
cfg.zapret2.strategy = flowseal.LIVE_STRATEGY
cfg.zapret2.queue_num = int(sys.argv[4])
desired = zapret2.arguments(cfg)
plan = json.loads(snapshot.read_text(encoding="utf-8"))
prefix = str(snapshot.parent / "assets") + "/"
expected = [arg.replace(prefix, str(installed) + "/") for arg in plan["arguments"]]
assert desired[5:] == expected
assert preflight.check(desired, cmd.run)[5:] == expected
print("ALT9 plan and both preflight stages OK")
PY
```

Если preflight не прошёл или SHA не совпали, не запускай браузер с кандидатом.
Запиши первое реальное сообщение и выполни возврат.

## 3. A/B/B/A на реальном YouTube

Запусти короткий контроль `hostfakesplit_md5` до первой фазы. Затем проведи
A=`multisplit`, B=`flowseal_alt9`, B, A. Используй одну свободную очередь
в preflight и во всех фазах. Возьми общий lock для опыта и перед первым
переключением создай `"$BACKUP/network-test-started"`. Перезаряди таймер перед
серией. Убедись, что до истечения осталось время для возврата.

В каждой фазе меняй политику через проверенный entry point `managed.set_desync`.
Для второй B выключи выбранный режим между попытками, чтобы проверить независимый
запуск. Перед каждым браузером дождись нового поколения, зарегистрированного
владельца NFQUEUE, активного gate и точной выбранной стратегии.

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9

set_phase() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$1" "$QUEUE" <<'PY'
import sys
from dataclasses import asdict
from pathlib import Path

from xgw import config, managed
from xgw.desync import flowseal, schema

path, phase = Path(sys.argv[1]), sys.argv[2]
assert phase in {"off", "multisplit", "flowseal_alt9", "hostfakesplit_md5"}
cfg, _ = config.load(path)
policy = schema.migrate(asdict(cfg.zapret2))
selected = policy["selected"]
selected.update(mode="off" if phase == "off" else "standalone",
                domains=list(flowseal.YOUTUBE_DOMAINS), probe_urls=[],
                observe_synack=False, observe_reply_packets=0, retry_seconds=60)
if phase != "off":
    selected["strategy"] = phase
policy["runtime"]["queue_num"] = int(sys.argv[3])
policy["engine"]["engine"] = "off"
managed.set_desync(managed.path_for(path), policy)
actual, _ = config.load(path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
```

1. Используй обычный Chrome со свежим тестовым профилем, QUIC off, без браузерного
   прокси. Ролик `8plwv25NYRo`, 720p, 1×. На фазу до 300 с с переключением,
   включая закрытие своего тестового Chrome. Дай до 60 с на первый кадр контента.
   При старте собери 150–180 с телеметрии. Проверь кадры и продвижение через vision.
2. Подтверди свежие SABR POST, прямой маршрут без VPN, приращение байтов
   `xgw-zapret2`, поколение и владельца очереди. Маршрут и прохождение медиа
   подтверждай по фактическим соединениям и счётчикам, как в T09. При одном
   общем счётчике без привязки к медиа пометь доказательство как неполное.
3. Сохрани первичные записи по [телеметрии](YOUTUBE-TELEMETRY.md). Импортируй
   `--tournament --diagnostics` по [формату CDN](T09-CDN-REPLAY.md#2-пересобрать-контекст-по-исходной-записи).
   Оставь все фактические CDN endpoints и протоколы. У фаз A/B должен быть один
   policy SHA без поля стратегии. Сравни совпадающие условия, смешанные отметь
   отдельно. Отсутствие старта за 60 с, ошибка страницы, реклама или неполный
   capture описываются отдельно от подтверждённого истощения буфера.
4. После серии повтори короткий штатный контроль. Если обе B дали пригодный
   pass и соседние A/контроли здоровы, перезаряди таймер и измерь ALT9 15 минут +
   перемотка + 5 минут. Зафиксируй время первого кадра, долю 720p, буфер,
   остановки и восстановление после перемотки. Длинный прогон подтверждает
   устойчивость кандидата в этих условиях. Для утверждения о преимуществе
   нужны сравнимые замеры. Если обе B не стартуют при здоровых контролях,
   опубликуй этот исход, сохрани диагностику и заверши сетевую фазу.

Все сетевые опыты этого задания ограничены TCP/443 в Standalone. QUIC и SYN
остаются отдельными этапами. Принятие параметров воркером, MEDIA_PATH и качество
воспроизведения отражай отдельными полями.

## 4. Возврат и автоматический отчёт

После сетевой фазы вызови `set_phase off` и убедись, что воркер освободил очередь.
Выполни `restore.sh` с `rollback` и верни исходный panel побайтово. Это временная
приёмка до решения по результатам A/B. Сверь хэши до/после, off/off, работающий VPN,
panel, очередь, acct, offload и останови таймер после подтверждения. Проверенные
ассеты можно оставить в фиксированном каталоге для повторного опыта, указав факт
в отчёте.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo sha256sum -c "$D/config-before.sha256"
# Сверь исходное состояние и работу VPN перед остановкой таймера.
sudo systemctl stop "$UNIT.timer"
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t10-flowseal-live-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t10-flowseal-live.md"
# Сама запиши REPORT, включая частичный результат или блокер.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: measure Flowseal ALT9 on live YouTube through XGW"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

В отчёте укажи SHA, результаты preflight, все попытки и контроли, цепочку пути
медиа, итог длинного опыта, восстановление и блокеры. IP, hostname CDN, URL с
подписью и полные захваты остаются приватными. При гонке сделай fetch/rebase и
обычный push.
