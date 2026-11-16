# T09/H09 — повторный импорт записей с делегированием CDN

На Ubuntu 24.04 LTS [исходный T09](../reports/2026-11-17_desync-t09-tournament.md)
выполнил все 12 слотов. Девять записей прошли импорт, три оставили `null`: обе
`multidisorder` и первая `fake_seq`. Аналогичное делегирование было в среднем
контроле. Слой профилей принят. `multisplit` и `fake_md5_split` выдержали
15+5 минут без VPN и остановок. Новое задание проверяет, что о смешанных записях
можно сказать после повторного импорта.

Исполнитель сама запускает команды на ThinkCentre. Если недоступны терминал или
приватные материалы исходного прогона, запроси доступ и укажи, какие сопоставления
без него выполнить нельзя. Используй vision, чтобы сверить сохранённые экраны
плеера с ходом записи. Опубликуй отчёт автоматически даже при частичных результатах.

## 1. Подготовка

В чистом checkout получи код. Закрепи SHA с доработкой `--tournament` в отчёте.
Запускай инструменты из checkout. Для этого этапа хватает сохранённых записей.
Службы, режимы, правила и конфиги рабочего шлюза менять не требуется.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor 5436792 "$CODE"
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-t09-cdn.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_cache.py tests/test_desync_tournament.py
mkdir "$D/trials"
```

Присвой переменной `OLD_LEDGER` абсолютный путь к исходному журналу `xgw-t09.mtx`.
Убедись, что
`report` на нём даёт 4/6 и 5/6. Отдельно проверь начальный и конечный статус панели,
воркеров и VPN доступными штатными командами чтения. Укажи статус старого
WAN-захвата и свободное место, если это доступно без переключений. Используй
сохранённые записи. Новый пакетный захват для этого задания не нужен.

## 2. Пересобрать контекст по исходной записи

Для каждого слота создай каталог `"$D/trials/01"` … `"$D/trials/12"`. Сопоставь его
с положением строки исходного журнала. Скопируй `player.json` той же фазы. Создай
`context.json` из прежнего контекста и полного набора `hostname/address/protocol`
по сохранённому CDP/Network/NetLog. Используй свежие запросы `videoplayback` SABR
из окна замера и их фактические адреса. Сверь отсутствие VPN-моста и подтверждение
нового поколения worker для всей фазы. Сверь, что все включённые запросы шли по
подтверждённому прямому пути. Данные vision подтверждают воспроизведение, адреса
подтверждает сетевой журнал. Не восстанавливай адрес или маршрут по памяти.
Исключи забракованный первый multisplit со старым поколением.

Шаблон со значениями-заполнителями, которые нужно заменить полями своего контекста:

```json
{
  "network": "thinkcentre-wan-a",
  "client": "chrome-stock",
  "client_sha256": "SHA256_CHROME",
  "policy_sha256": "SHA256_EFFECTIVE_POLICY",
  "candidate": "multidisorder",
  "round": "t09-1",
  "video_id": "8plwv25NYRo",
  "verified_direct_all_endpoints": true,
  "endpoints": [
    {"hostname": "primary.googlevideo.com", "address": "PRIMARY_IP", "protocol": "h1"},
    {"hostname": "secondary.googlevideo.com", "address": "SECONDARY_IP", "protocol": "h1"}
  ]
}
```

Включи и одноадресные фазы с одним элементом `endpoints`, чтобы весь новый журнал
пользовался одним форматом. Не отбрасывай второй endpoint из-за его малой доли.
Если полные исходники или независимое подтверждение маршрута для фазы отсутствуют,
оставь соответствующий `context.json` несозданным. Тогда строка останется
`null`. Не меняй пороги плеера. То же сделай отдельно для среднего контроля
`hostfakesplit_md5` вне матрицы, если хватает первичных данных.

## 3. Автоматический пересчёт

Сначала сверь защищённость исходных файлов. Созданные копии должны быть 0600,
каталоги — 0700. Команда ниже собирает новый журнал рядом с исходниками и
кладёт диагностику каждой фазы в её приватный каталог.

```bash
python3 -m xgw.desync.tournament report --ledger "$OLD_LEDGER" >"$D/before.json"
python3 - "$OLD_LEDGER" "$D/trials" "$D/ledger.json" <<'PY'
import json
import sys
from pathlib import Path

from docs.helpers.desync_playback_observation import ObservationError, observation
from xgw.desync import shadow, tournament
from xgw.desync.experiment import private_path
from xgw.paths import atomic_write_json

old, trials, out = map(Path, sys.argv[1:])
private_path(old)
with old.open("rb") as stream:
    raw = stream.read(32769)
if len(raw) > 32768:
    raise SystemExit("ledger_size")
ledger = tournament.validate_ledger(json.loads(raw))
for index, row in enumerate(ledger, 1):
    trial = trials / f"{index:02d}"
    original = row["observation"]
    row["observation"] = None
    capture, context = trial / "player.json", trial / "context.json"
    if not capture.is_file() or not context.is_file():
        print(index, row["candidate"], "evidence_missing")
        continue
    detail = {}
    private_path(trial, directory=True)
    private_path(capture)
    private_path(context)
    with capture.open("rb") as stream:
        raw = stream.read(shadow.MAX_BYTES + 1)
    with context.open("rb") as stream:
        metadata = stream.read(8193)
    if len(metadata) > 8192:
        raise SystemExit("metadata_size")
    try:
        result = observation(raw, json.loads(metadata), diagnostics=detail, for_tournament=True)
    except ObservationError as exc:
        detail["reason"] = str(exc)
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        detail["reason"] = "invalid_input"
    else:
        if original and any(result[key] != original[key]
                            for key in ("recording_id", "started", "finished", "outcome")):
            raise SystemExit(f"original_observation_mismatch at slot {index}")
        row["observation"] = result
    atomic_write_json(trial / "diagnostics.json", detail, mode=0o600)
    print(index, row["candidate"], detail.get("reason", "unavailable"))
atomic_write_json(out, tournament.validate_ledger(ledger), mode=0o600)
PY
python3 -m xgw.desync.tournament report --ledger "$D/ledger.json" >"$D/after.json"
```

Для среднего контроля с отдельными файлами используй `python3 -m
docs.helpers.desync_playback_observation --tournament --diagnostics --capture PLAYER
--metadata CONTEXT`. Укажи число endpoint и исход. При недоступных данных запиши
точную причину.

## 4. Интерпретация и публикация

- Сверь до и после по каждому слоту: число endpoint, исход или причину пропуска,
  время, долю 720p, прогресс и сигналы остановок. Для девяти учтённых фаз ожидается
  тот же исход. Время забракованного старта укажи отдельно, если сохранилось.
- `compared` требует шесть пригодных измерений с одним точным набором endpoint и
  одним контекстом сети, браузера, политики и ролика. При разных наборах ожидается
  `mixed_context`. `mixed_endpoint_replay` показывает пересчёт на тех же записях,
  если все шесть исходов пригодны и совпадают прочие условия, включая набор
  протоколов. Его оценки времени и пропущенных победителей относятся к этим
  записям. Для причинного вывода о стратегиях важны контролируемые условия,
  потому что доля запросов к разным адресам могла влиять на исход.
- Не переносить запись с набором адресов в кэш точного IP. H02 остаётся отдельным
  опытом. Укажи, есть ли наблюдаемый контрпример для отсечения fake на геометрии,
  где профиль без fake не прошёл. Если не хватает исходов или контексты смешаны,
  сохрани частичный результат с названием причины.
- Публикуй агрегаты и статусы. IP, hostname CDN, идентификаторы хэшей, ссылки,
  содержимое захватов и приватные пути остаются на машине. Укажи точный SHA кода,
  доступность исходников, сравнение с `before.json`, статус шлюза и блокеры.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t09-cdn-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t09-cdn-replay.md"
# Сама запиши отчёт, включая частичные результаты или блокер.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: replay T09 captures with multiple CDN endpoints"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch, rebase и обычный push.
