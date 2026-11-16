# T09/H09 — полная матрица и сокращённый отбор на YouTube

Исходное ТЗ. Результаты опубликованы в [отчёте T09](../reports/2026-11-17_desync-t09-tournament.md).
Для сохранённых записей с несколькими CDN используйте [повторный импорт](T09-CDN-REPLAY.md).

ThinkCentre, Ubuntu **24.04 LTS**. Прочитай [последний отчёт](../reports/2026-11-16_desync-t08-event-socket.md),
`9829345`. Рабочий контроль `hostfakesplit_md5` дал 213 с 720p без VPN, из которых
204,8 с подтвердились импортом Chrome. Старые ряды давали недостаточный прогресс
или снижение качества. Используй обычный Chrome и реальные SABR POST.

Исполнитель сама выполняет команды, запускает браузер, использует vision, сверяет
состояние и публикует отчёт. Если недоступны терминал, sudo или GUI, запроси доступ.
При блокере опубликуй независимые проверки и точный статус по каждому подпункту.

## 1. Подготовка и безопасное временное обновление

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=9829345
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t09.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_tournament.py tests/test_desync_cache.py \
  tests/test_zapret2.py tests/test_desync_schema.py tests/test_desync_worker.py
T09=(python3 -m xgw.desync.tournament)
"${T09[@]}" plan >"$D/plan.json"
printf '[]\n' >"$D/ledger.json"
JOB=(--ledger "$D/ledger.json" --budget-seconds 3600 --cancel-file "$D/cancel")
"${T09[@]}" next "${JOB[@]}"
```

До любых изменений сверь off/off, исходные хэши, PID, очередь, offload, acct и штатный VPN.
Проверь свободное место на разделе старого WAN-захвата и статус обращения к администратору.
По последнему отчёту файл уже превышал 11 ГБ. Для матрицы используй CDP/Network и счётчики,
без нового WAN-захвата.

Для установки двух файлов используй [prepare/apply/restore T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат)
со следующими переменными и флагом `--tournament-t09` во всех трёх действиях, в том числе
в restore.sh. Сверь PACKAGE, PY, CFG и PANEL с рабочей службой. При расхождении SHA
проверь историю установленных слоёв. При неизвестной базе не применяй замену.

```bash
FILES=(src/xgw/desync/schema.py src/xgw/zapret2.py)
UNIT=xgw-desync-t09-tournament-rollback
PAYLOAD="/opt/xgw/handoff/desync-t09-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t09-$CODE"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
```

Подготовь манифест и копию panel, запусти 45-минутный таймер до apply. После установки
сверь SHA двух файлов и исходное состояние. Из установленного пакета получи argv
`zapret2.arguments` для каждого профиля при mode standalone. Проверь оба флага
предварительной проверки штатным `preflight.check` до первого включения. В argv
с подменой проверь равенство fake и параметры геометрии. Сами argv сохрани локально.

```bash
sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" <<'PY'
import sys
from pathlib import Path
from xgw import config, zapret2
from xgw.desync import preflight
from xgw.net import cmd

cfg, _ = config.load(Path(sys.argv[1]))
cfg.zapret2.mode = "standalone"
for name in ("multisplit", "multidisorder", "fake_md5_split", "fake_md5",
             "fake_seq_split", "fake_seq", "hostfakesplit_md5"):
    cfg.zapret2.strategy = name
    argv = preflight.check(zapret2.arguments(cfg), cmd.run)
    print(name, "preflight OK", [arg for arg in argv if arg.startswith("--lua-desync=")])
PY
```

## 2. Последовательный прогон

Используй [baseline и переключение Standalone](T06-H05.md#2-установка-и-пары-в-обычном-chrome).
Все фазы идут с тем же scope из шести доменов, engine off, свободной общей очередью,
параметрами перехвата, probe_urls и observe off как в H05. Профиль меняй через
`managed.set_desync`; дождись нового generation с владельцем очереди и подтверждённого
gate. Предыдущая фаза должна освободить воркер, Chrome и очередь до следующего старта.

В общем каталоге рабочего пользователя возьми один lock на всю живую матрицу:

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
"${T09[@]}" next "${JOB[@]}"
```

До матрицы и после каждого окна запусти короткий контроль `hostfakesplit_md5` ≥120 с.
Убедись, что через тот же маршрут пришёл свежий SABR и видео играет. Если контроль
потерял работоспособность или условия сменились, пометь участок, восстанови сеть
и сохрани уже измеренное. В каждом окне шесть фаз в порядке `plan.json`.
Перезаряди 45-минутный таймер перед каждым окном и проверь дедлайн перед фазой.

Для каждой попытки получи `round`, `candidate` и `limit_seconds` из `next`.
Одна фаза получает до 300 с с момента смены политики, включая запуск и остановку.
Запускай свежий профиль обычного Chrome с QUIC off, без прокси, ролик `8plwv25NYRo`,
720p, 1×. Собери ≥150 с измеренного просмотра, чтобы осталось ≥120 с пригодной записи.
Отдельно фиксируй старт, ABR/разрешение по времени, остановки и возможные ошибки плеера.
Съёмка — [обычный Chrome](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome), проверка кадра и
скорости продвижения через vision. Выхлоп CDP и NetLog оставляй на машине.

- Подтверди отсутствие VPN-моста, нового владельца очереди, свежий POST
  `videoplayback`, весь реальный endpoint медиа и прирост байтов `xgw-zapret2`.
  Изменение hostname/IP/протокола между фазами отмечай и сохраняй фактический ID.
  Смешанные медиа внутри одного ряда, нерешённые ошибки запуска и неполный capture
  оставляют `observation: null`. Запиши конкретный блокер. Совпавший IP не доказывает
  одинаковые условия без сверки всей политики и браузера.
- Создай `context.json` по [шаблону H02/H03](T07-T08-CACHE.md#2-реальные-записи-chrome).
  Используй один policy_sha256 для сравнимых фаз. В него входят код, bundle, сеть,
  флаги браузера, очередь и параметры маршрута. Исключается только стратегия.
  `round` и `candidate` бери из `next`. Импортируй реальный `player.json`
  с `--diagnostics`. Сохрани фактические интервалы и причину `unconfirmed_playback`.
- Измеряй полное время попытки от переключения до закрытия её Chrome по
  `time.monotonic()`. При 300 с останови свою фазу, завершив только её тестовый
  профиль, и запиши фактическое время с `observation: null`. Контроли и паузы
  между окнами учитывай в общем wall time отдельно.

После каждой попытки добавь строку в журнал. `ROUND`, `CANDIDATE`, `ELAPSED` и
`OBSERVATION` ниже — параметры этой попытки. Последний — путь к JSON успешного
импорта или пустая строка. `playback_failed` от исправного импортера имеет валидную
строку observation и остаётся отрицательным результатом. План ограничен 12 попытками,
в бюджет входит фактическое время даже невалидных строк.

```bash
python3 - "$ROUND" "$CANDIDATE" "$ELAPSED" "${OBSERVATION:-}" >"$D/row.json" <<'PY'
import json
import sys
from pathlib import Path

round_id, candidate, elapsed, path = sys.argv[1:]
seconds = float(elapsed)
observation = json.loads(Path(path).read_text()) if path and seconds <= 300 else None
print(json.dumps({"round": round_id, "candidate": candidate, "elapsed_seconds": seconds,
                  "observation": observation}))
PY
"${T09[@]}" record "${JOB[@]}" --row "$D/row.json"
"${T09[@]}" next "${JOB[@]}"
```

Перед живой матрицей проверь отмену на пустом журнале через `touch "$D/cancel"`:
`next` выдаст `cancelled` без кандидата. Удали тестовый маркер. Отдельно проверь
`next --budget-seconds 299 --ledger "$D/ledger.json"` и получи `budget`.
При реальном прерывании создай маркер, заверши свой браузер и сразу вызови restore.
Маркер блокирует следующую попытку. Сам CLI состояния ничего не переключает.

## 3. Сравнение и повтор качества

```bash
"${T09[@]}" report --ledger "$D/ledger.json" >"$D/replay.json"
```

Приведи таблицу всех 12 фактических фаз и контролей, включая непригодные строки.
`compared` требует шесть валидных исходов внутри одного exact context. В replay
оба варианта сначала оплачивают две геометрии без fake. Сокращённый вариант затем
проверяет fake на тех геометриях, где baseline прошёл. Если оба baseline провалились,
он проверяет всю матрицу. Укажи число попыток, измеренную стоимость строк,
`first_pass_seconds`, `estimated_seconds_saved` и `missed_winners` для каждого окна.
Это оценка на одних и тех же замерах, полные живые прогоны нужны для её проверки.
Если контроль не прошёл, не делай вывод о пользе стратегии по этому окну.

Для максимум двух повторяемых кандидатов, если хватает времени и контроли стабильны,
проведи 15 минут + перемотка + 5 минут в Chrome. Перед каждым прогоном перезаряди
таймер. Фиксируй долю 720p и буфер по минутам, особенно после 530 с, чтобы проверить
поздний ABR из прежнего отчёта. Старайся измерить две стратегии с одинаковыми условиями.
При непригодных окнах опубликуй частичный итог. По одному адресу H02 остаётся открытым.

## 4. Возврат и автоматическая публикация

Восстанови исходный panel через таймер/restore. Сверь хэши, off/off, очередь, PID,
VPN, acct и offload. При успешном preflight и работе слоя можно принять два файла,
при регрессии используй rollback. Останови таймер после сверки, освободи lock.
Публикуй только агрегаты и статусы без IP, hostname CDN, сырых ссылок и capture.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t09-browser-matrix-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t09-tournament.md"
# Сама создай REPORT, включая точный SHA, блокеры и оставленное состояние.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: measure T09 YouTube strategy matrix on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push. Публикуй и частичную матрицу.
