# T07/T08 — кэш замеров Chrome и перенос результата между IP CDN

Основание — [отчёт T07/H01](../reports/2026-11-16_desync-t07-shadow.md), `29e10fd`.
Clone 15+5 минут прошёл без остановок, качество после ~530 с снизилось до 480p
при буфере 63–84 с. Повторяем замер в паре со static. Кэш сохраняет подсказки по
реальным наблюдениям и всегда возвращает `apply:false`.

Исполнитель сама запускает команды на ThinkCentre с Ubuntu **24.04 LTS**, управляет
Chrome и использует vision. При отсутствии терминала, sudo или GUI запроси доступ.
Даже если сетевой этап частичный, запусти независимую проверку кэша и опубликуй отчёт.

## 1. Исходное состояние

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor 29e10fd "$CODE"
D=$(mktemp -d "$HOME/xgw-t08-cache.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_desync_cache.py tests/test_desync_shadow.py \
  tests/test_desync_experiment.py tests/test_youtube_telemetry.py
CACHE=(python3 -m xgw.desync.cache)
mkdir -m 700 "$D/observations" "$D/state" "$D/storage-test"
```

Возьми установленный слой H05, проверь режимы, PID, конфиги, очередь, acct, offload и VPN.
Проверь свободное место и состояние старого `tcpdump` по [T07](T07-SHADOW.md). Если он
по-прежнему пишет и прежний доступ даёт EPERM, передай остановку администратору хоста
и зафиксируй изменение размера файла. Для этого задания WAN-захват не нужен.

## 2. Реальные записи Chrome

Используй [обычный Chrome](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome) с роликом
`8plwv25NYRo`, свежим профилем на попытку, скоростью 1×, 720p и без эмуляции сети.
Подготовь [таймер возврата](YOUTUBE-TELEMETRY.md#standalone-на-уже-установленном-t04)
с исходной копией panel. Применяй временную политику через [порядок H05](T06-H05.md#2-установка-и-пары-в-обычном-chrome).
Перед каждым раундом проверяй gate, владельца очереди, свежий SABR, дельту outbound
`xgw-zapret2` и выключенные VPN-мосты. До первых пар проверь `hostfakesplit_md5` ≥2 мин.

- Два окна с противоположным порядком static/clone, отдельный Chrome на фазу.
  В каждом собери ≥3 минут наблюдения на профиль. Если есть время, сравни обе стратегии
  на длинном 15+5 с одинаковой перемоткой и отметь разброс ABR. Для длинного замера
  записывай качество по минутам, буфер, скорость, дропы и долю времени в 720p.
  После каждого переключения сверь политику, маршрут и остаток таймера. При необходимости
  перезаряди таймер перед длинной фазой.
- Зафиксируй реальный протокол, hostname и Remote Address успешных SABR POST в
  DevTools или CDP. Одну чистую фазу засчитывай для кэша, когда все зачётные медиаданные
  относятся к одному hostname/IP/протоколу и независимые признаки подтверждают direct.
  Сетевые заголовки и адреса сохраняй локально. Многоточечную фазу оставь в отчёте
  воспроизведения без импорта. Неполный вывод Network, прокси, VPN и контролируемое
  отключение сети исключаются из выборки.
- Ищи естественные повторения одного адреса и разные адреса того же hostname.
  Для переноса нужен хотя бы один проверочный IP, который отсутствует в обучающих
  наблюдениях данного кандидата. Отдельно оцени другие /24 для IPv4 и /48 для IPv6.
  H2 и H3 проводи отдельными сериями при наличии реальных маршрутов, QUIC и endpoint.
  Не перенаправляй подписанные запросы на неподтверждённые IP и не переигрывай их через GET.
  Если смены IP или подтверждения H3 нет, оставь соответствующую проверку открытой.
  У ThinkCentre WAN IPv6 отсутствует по подтверждению владельца от 18 ноября:
  живая IPv6-фаза NOT_APPLICABLE_ON_THIS_HOST, она не блокирует IPv4-приёмку.

Сохрани для каждой пригодной фазы `player.json` по инструкции Chrome. Запись должна
содержать `unix` и минимум 120 с измеренного воспроизведения для положительного исхода.
Затянувшийся startup, ручная пауза и смешанный маршрут не дают положительного результата.
Импорт записывает `playback_failed` при подтверждённом ≥15 с истощении после старта
либо при ≥120 с с недостаточной долей 720p. Отрыв суммарного прогресса от времени
измерения без такого сигнала оставляет запись непригодной для кэша. Причина неизвестна.
Сохраняй исходный секундный ряд. Серии с искусственной потерей сети не импортируй.

Рядом с записью создай приватный `context.json` (0600). Ниже шаблон, замени значения
результатами той же фазы. `verified_direct_single_endpoint:true` ставь после независимой
сверки по Network, маршруту и очереди. Для paired A/B `policy_sha256` — SHA-256 одного
эффективного route/worker policy-документа без поля стратегии, с SHA кода и bundle,
сетью, параметрами Chrome, QUIC, режимом и очередью. Хэш браузера — реального бинарника.
Разные раунды обозначай отдельно, повтор одного файла независимым раундом не считается.

```json
{
  "hostname": "observed.googlevideo.com",
  "address": "OBSERVED_IP",
  "network": "thinkcentre-wan-a",
  "protocol": "h2",
  "client": "chrome-stock",
  "client_sha256": "SHA256_CHROME",
  "policy_sha256": "SHA256_EFFECTIVE_POLICY",
  "candidate": "fake_clone_md5",
  "round": "wan-window-2",
  "video_id": "8plwv25NYRo",
  "verified_direct_single_endpoint": true
}
```

```bash
chmod 0600 "$TRIAL_DIR/player.json" "$TRIAL_DIR/context.json"
OBS="$D/observations/$TRIAL_LABEL.json"
if python3 -m docs.helpers.desync_playback_observation \
    --capture "$TRIAL_DIR/player.json" --metadata "$TRIAL_DIR/context.json" >"$OBS.tmp"; then
  mv -- "$OBS.tmp" "$OBS"
else
  cat "$OBS.tmp"
  rm -- "$OBS.tmp"
fi
```

Повтори для разных фаз с отдельными `TRIAL_LABEL`, затем собери журнал из готовых строк.
Разделяй в выводе реальные исходы воспроизведения и способность по ним подсказать профиль.

```bash
python3 - "$D/observations" >"$D/history.json.tmp" <<'PY'
import json, sys
from pathlib import Path
print(json.dumps([json.loads(p.read_text()) for p in sorted(Path(sys.argv[1]).glob("*.json"))]))
PY
mv -- "$D/history.json.tmp" "$D/history.json"
"${CACHE[@]}" compare --history "$D/history.json" | tee "$D/compare.json"
"${CACHE[@]}" rebuild --history "$D/history.json" --state-dir "$D/state"
CONTEXT=$(python3 -c 'import json,sys; rows=json.load(open(sys.argv[1])); print(rows[0]["context_id"] if rows else "")' "$D/history.json")
if [[ -n "$CONTEXT" ]]; then
  "${CACHE[@]}" lookup --history "$D/history.json" --state-dir "$D/state" --context "$CONTEXT"
fi
```

Сравнение пустой выборки даёт `inconclusive`. Для сравнения укажи число endpoint/префиксов,
`correct_hit`, `false_hit`,
abstentions, число исходов с более ранней историей. У `prefix_other_ip` и `host_other_ip`
история берётся только от других IP. У `host_other_prefix` ещё и другой префикс.
Только подходы, закончившиеся до начала проверочного раунда, участвуют в подсказке.
Чтобы подтвердить пользу укрупнения ключа, нужны и пригодные переносы, и опыт на адресах,
для которых перенос мог ошибиться. Без такой выборки оставь H02 открытым.

## 3. Атомарность и TTL на файловой системе ThinkCentre

Выполни этот блок независимо от результатов YouTube. В искусственной истории используй
только фиктивные хэши. Её результаты проверяют хранение и нигде не считаются сетевыми замерами.

```bash
STORE="$D/storage-test"
RECORDS="$STORE/history.json"
SNAPSHOT="$STORE/playback-shadow.json"
CTX=$(python3 - "$RECORDS" <<'PY'
from pathlib import Path
import json, sys, time
now = int(time.time())
rows = []
for i, offset in enumerate((800, 400)):
    rows.append({"measurement_version": 2,
                 "context_id": "a"*64, "prefix_context_id": "b"*64, "host_context_id": "c"*64,
                 "recording_id": f"{i:064x}", "candidate": "static", "round": f"fixture-{i}",
                 "started": now-offset-150, "finished": now-offset, "outcome": "pass"})
Path(sys.argv[1]).write_text(json.dumps(rows))
print("a"*64)
PY
)
STORAGE=(--history "$RECORDS" --state-dir "$STORE")
"${CACHE[@]}" lookup "${STORAGE[@]}" --context "$CTX"
"${CACHE[@]}" rebuild "${STORAGE[@]}"
"${CACHE[@]}" lookup "${STORAGE[@]}" --context "$CTX"
"${CACHE[@]}" rebuild "${STORAGE[@]}" & A=$!
"${CACHE[@]}" rebuild "${STORAGE[@]}" & B=$!
for i in {1..5}; do "${CACHE[@]}" lookup "${STORAGE[@]}" --context "$CTX"; done
wait "$A"
wait "$B"
sha256sum "$SNAPSHOT" >"$D/before-fault.sha256"
for fault in enospc kill; do
  rc=0
  python3 - "$RECORDS" "$STORE" "$fault" <<'PY' || rc=$?
import errno, os, signal, sys
from pathlib import Path
from xgw import paths
from xgw.desync import cache
history, store, fault = sys.argv[1:]
replace = paths.os.replace
def fail_at_commit(src, dst):
    if Path(dst) == Path(store) / "playback-shadow.json":
        if fault == "kill":
            os.kill(os.getpid(), signal.SIGKILL)
        raise OSError(errno.ENOSPC, "injected at snapshot commit")
    return replace(src, dst)
paths.os.replace = fail_at_commit
sys.argv[1:] = ["rebuild", "--history", history, "--state-dir", store]
raise SystemExit(cache.main())
PY
  if [[ "$fault" == enospc ]]; then test "$rc" = 2; else test "$rc" = 137; fi
  sha256sum -c "$D/before-fault.sha256"
  "${CACHE[@]}" lookup "${STORAGE[@]}" --context "$CTX"
done
"${CACHE[@]}" rebuild "${STORAGE[@]}"
test -z "$(find "$STORE" -maxdepth 1 -name '.playback-shadow.json.*.tmp' -print -quit)"
```

Проверь дополнительно изменённый context (miss), добавленный свежий FAIL (старый снимок
stale_history, после rebuild miss), повреждённый JSON и правку срока в корректном JSON
(ошибка чтения либо invalid_snapshot, подсказок нет). TTL и откат часов проверь вызовом
`cache.lookup` с тестовым `now`, часы машины оставь в покое. Срок заканчивается по
возрасту более старого из двух успешных раундов. При SIGKILL остаток temp должен
убраться следующим rebuild. Отдельно укажи, что ENOSPC инъецирован на rename,
физический раздел не заполнялся. На приватных файлах проверь 0600, на каталогах 0700.

## 4. Возврат и автоматическая публикация

Восстанови исходный panel и политику таймером T04, проверь хэши, off/off, пустую очередь,
acct, offload и VPN. Останови таймер после проверки. Измерения делаются из checkout.
Оставь полный Network, player.json, IP, адреса, снимок кэша и config только на стенде.
В отчёт внеси SHA, агрегаты качества и сравнения, исходы хранения и состояние шлюза.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t08-cache-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t08-cache.md"
# Сама создай REPORT с результатами и оставшимся состоянием.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify playback context cache on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push. Опубликуй и частичный результат.
