# T08/H06 — локальное чтение истории воркера

ThinkCentre, Ubuntu **24.04 LTS**. Основа — [отчёт T08/H06](../reports/2026-11-16_desync-t08-worker-events.md),
`430c866`. Исполнитель сама запускает команды, использует Chrome и vision и публикует отчёт.
Если недоступны терминал, sudo или GUI для соответствующего опыта, запроси доступ.

Прототип читает атомарный `/run/xgw/status.json`. Доступ проверяется с обеих сторон по
UID через `SO_PEERCRED`. Каталог сокета принадлежит запускающему пользователю, права
0700, сокет 0600. Один запрос и один ответ на соединение. Лимиты — 8 параллельных
клиентов, 16 допусков/с, 2 с на соединение, до 512 Б запроса и 24 КиБ ответа.
При переполнении соединение закрывается. Снимку старше 90 с соответствует `unavailable`.
Команды управления отсутствуют. [Linux unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html#SO_PEERCRED)

## 1. Подготовка

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor 430c866 "$CODE"
D=$(mktemp -d "$HOME/xgw-event-accept.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_event_socket.py tests/test_desync_worker.py \
  tests/test_desync_cache.py tests/test_youtube_telemetry.py
T=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/xgw-es.XXXXXXXX")
PROTO=(python3 -m xgw.desync.event_socket)
```

Сверь исходные policy off/off, MainPID, очередь, VPN, acct, offload и хэши конфигов.
Если прежний tcpdump ещё растит файл, укажи состояние и статус обращения к администратору.
Для этого задания новый WAN-захват не нужен. Из checkout запускай временные процессы
от пользователя рабочего стола. Код демона и установленного zapret2 уже был принят в T08.

## 2. Локальный transport на ядре Ubuntu

Создай автономный журнал. Он нужен для проверки курсора и лимитов с заполненным кольцом.
Данные запрашиваются через настоящий Linux AF_UNIX. Существующий `status.json` этот блок
не пишет.

```bash
python3 - "$T/status.json" <<'PY'
import sys
import time
from pathlib import Path
from xgw.desync import worker
from xgw.paths import atomic_write_json

slot = worker.WorkerSlot()
for _ in range(30):
    lease = slot.reserve(worker.ENGINE_UNIT, 201, policy_key="a" * 64)
    slot.observe_owner(lease, True)
    slot.release(lease)
atomic_write_json(Path(sys.argv[1]), {
    "daemon": True, "updated": time.time(), "zapret2_worker_events": slot.snapshot()[1],
}, mode=0o600)
PY
"${PROTO[@]}" serve --socket "$T/fixture.sock" --status "$T/status.json" >"$D/fixture.log" 2>&1 &
BROKER=$!
trap 'kill -TERM "$BROKER" 2>/dev/null || :; wait "$BROKER" || :' EXIT
for i in {1..40}; do
  if [[ -S "$T/fixture.sock" ]]; then break; fi
  kill -0 "$BROKER"
  sleep 0.1
done
test -S "$T/fixture.sock"
stat -c '%a %U' "$T" "$T/fixture.sock"
```

С тем же процессом выполни курсор, перегрузку, повтор после восстановления и недоступный
снимок. `gap` возвращает сохранённый хвост журнала, `reset` начинает чтение новой эпохи,
`ok` с пустыми событиями означает, что новых событий пока нет.

```bash
python3 - "$T/fixture.sock" "$T/status.json" <<'PY'
import contextlib
import json
import socket
import sys
import time
from pathlib import Path
from xgw.desync import event_socket as es
from xgw.desync.worker import WorkerSlot
from xgw.paths import atomic_write_json

path, status = map(Path, sys.argv[1:])
base = json.loads(status.read_text())
base["updated"] = time.time()
atomic_write_json(status, base, mode=0o600)

def read(epoch=None, after=0):
    frame = json.dumps({"version": 1, "epoch": epoch, "after": after}).encode() + b"\n"
    return es.request(path, frame)

first = read()
assert first["state"] == "snapshot" and first["discarded"] == 26
assert first["last_seq"] == 90 and len(first["events"]) == 64
epoch = first["epoch"]
assert read(epoch, 89) == read(epoch, 89)
assert [e["seq"] for e in read(epoch, 89)["events"]] == [90]
assert read(epoch, 90)["events"] == []
assert read(epoch, 20)["state"] == "gap"
assert read(epoch, 91)["state"] == "invalid_cursor"
assert es.request(path, b'{"version":1,"epoch":null,"after":0,"action":"pin"}\n')[
    "state"] == "invalid_request"
assert es.request(path, b"x" * es.MAX_REQUEST)["state"] == "invalid_request"
print("snapshot/replay/gap/future/oversize PASS")

time.sleep(1.05)
with socket.socket(socket.AF_UNIX) as slow:
    slow.settimeout(2)
    slow.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    slow.connect(str(path))
    slow.sendall(b'{"version":1,"epoch":null,"after":0}\n')
    assert read(epoch, 90)["state"] == "ok"
time.sleep(es.DEADLINE_SECONDS + 0.3)
with contextlib.ExitStack() as stack:
    for _ in range(es.MAX_CLIENTS):
        partial = stack.enter_context(socket.socket(socket.AF_UNIX))
        partial.settimeout(2)
        partial.connect(str(path))
        partial.sendall(b"{")
    try:
        read()
    except (OSError, ValueError):
        print("busy connection refused or closed")
    else:
        raise AssertionError("connection cap was not observed with slow clients")
    time.sleep(es.DEADLINE_SECONDS + 0.3)
    assert read(epoch, 90)["state"] == "ok"
with socket.socket(socket.AF_UNIX) as gone:
    gone.connect(str(path))
    gone.sendall(b"{")
assert read(epoch, 90)["state"] == "ok"

time.sleep(1.05)
passes = dropped = 0
start = time.monotonic()
for _ in range(2 * es.REQUESTS_PER_SECOND):
    try:
        assert read(epoch, 90)["state"] == "ok"
        passes += 1
    except (OSError, ValueError):
        dropped += 1
elapsed = time.monotonic() - start
print(f"rate trial: admitted={passes} dropped={dropped} elapsed_s={elapsed:.3f}")
assert passes > 0
if elapsed < 1:
    assert passes <= es.REQUESTS_PER_SECOND and dropped > 0
time.sleep(1.05)
assert read(epoch, 90)["state"] == "ok"

atomic_write_json(status, base | {"updated": time.time() - 91}, mode=0o600)
assert read()["state"] == "unavailable"
base.update(updated=time.time(), zapret2_worker_events=WorkerSlot().snapshot()[1])
atomic_write_json(status, base, mode=0o600)
assert read(epoch, 90)["state"] == "reset"
assert read()["last_seq"] == 0
print("slow/disconnect/recovery/stale/reset PASS")
PY
```

Медленный reader проверяет доступность второго клиента. Восемь частичных запросов
отдельно удерживают слоты до дедлайна. Если rate-цикл занял ≥1 с и вытеснений нет,
лимит скорости остаётся непроверенным. Проверь число потоков и FD у брокера до,
во время нагрузки и после неё.

Проверь UID отдельно, пока брокер пользователя активен. При connect от root ожидается
EOF или reset без JSON. Если файловая система отклонила connect, зафиксируй этот
уровень отдельно. Сверка SO_PEERCRED требует успешного connect с другим UID.

```bash
sudo python3 - "$T/fixture.sock" <<'PY'
import socket
import sys
with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(2)
    try:
        client.connect(sys.argv[1])
    except PermissionError:
        print("DAC_DENIED; peer check not reached")
    else:
        try:
            client.sendall(b'{"version":1,"epoch":null,"after":0}\n')
            assert not client.recv(1024)
        except (BrokenPipeError, ConnectionResetError):
            pass
        print("CONNECT_OK; no worker events received")
PY
"${PROTO[@]}" read --socket "$T/fixture.sock"
kill -TERM "$BROKER"
wait "$BROKER"
test ! -e "$T/fixture.sock"
trap - EXIT
```

## 3. Работающий демон и Chrome

Создай отдельный сокет в том же 0700 каталоге:

```bash
"${PROTO[@]}" serve --socket "$T/live.sock" >"$D/live.log" 2>&1 &
BROKER=$!
trap 'kill -TERM "$BROKER" 2>/dev/null || :; wait "$BROKER" || :' EXIT
for i in {1..40}; do
  if [[ -S "$T/live.sock" ]]; then break; fi
  kill -0 "$BROKER"
  sleep 0.1
done
"${PROTO[@]}" read --socket "$T/live.sock" >"$D/live-off.json"
```

Сопоставь epoch и last_seq с текущим `/run/xgw/status.json`. Используй
[резервную копию и таймер возврата](YOUTUBE-TELEMETRY.md#standalone-на-уже-установленном-t04).
Под активным таймером пройди off → Standalone `hostfakesplit_md5` → off. Одновременно читай
сокет курсором из предыдущего ответа, обновляя after только после успешного разбора
всего ответа. Сверь `reserved`, `owner_verified`, `released`, отсутствие дубликатов
после запроса на last_seq, текущую политику и владельца очереди. Прерывай только клиенты
сокета. Во время Standalone собери ≥120 с реального 720p с vision, свежим SABR,
очередью и дельтой `xgw-zapret2`. После штатного restore можешь проверить `reset` по
сохранённому курсору при смене epoch. Если таймер перезагружает xgw, брокер может увидеть
короткое `unavailable` до записи нового снимка.

Для трёх исходных захватов A′/B′/S из предыдущих отчётов и свежей записи, если у неё
подтверждён один CDN, запусти импорт того же файла с `--diagnostics`. Политика и
критерии замера берутся из [H02/H03](T07-T08-CACHE.md). Сохрани отдельно stdout и stderr.

```bash
rc=0
python3 -m docs.helpers.desync_playback_observation --diagnostics \
  --capture "$TRIAL_DIR/player.json" --metadata "$TRIAL_DIR/context.json" \
  >"$D/$TRIAL_LABEL.result.json" 2>"$D/$TRIAL_LABEL.diagnostics.json" || rc=$?
printf 'observation rc=%s\n' "$rc"
```

Для прежнего S укажи точную причину из `reason`, долю 720p с исключёнными интервалами,
суммарный прогресс и пороги starvation. Сопоставь с визуальной оценкой. Если причина
низкого качества или прогресса остаётся неизвестной, сохрани этот статус. H02 ждёт
независимых наблюдений других адресов CDN.

## 4. Возврат и публикация

Подтверди исходные конфиги, off/off, очередь, offload/acct и VPN. Останови таймер после
сверки. Заверши только временный брокер и проверь, что его сокеты исчезли. Записи status,
Network и адреса оставь на стенде. В отчёт внеси агрегаты и коды, точный SHA, оставленное
состояние и блокеры. Автоматически публикуй и частичную приёмку.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t08-event-socket-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t08-event-socket.md"
# Сама создай REPORT и проверь, что в нём только агрегаты.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify Unix worker event socket on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push.
