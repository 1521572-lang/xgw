# T06 — проверка установленного nfqws2 и загрузки Lua

ThinkCentre, Ubuntu **24.04 LTS**. [Отчёт T05](../reports/2026-11-16_desync-t05-replies-autottl.md)
принял входящее окно. Слой из пяти файлов оставлен, рабочая политика off/off и
`nf_conntrack_acct=0` восстановлены. В AutoTTL холодное измерение 62 → 1 отбросило fake
на пути к серверу; при ответе 58 → 5 fake с MD5 дошёл до сервера. Прошлые PCAP фаз
пересеклись. Контроль `warm_off` требует чистого повтора, чтобы подтвердить происхождение TTL.

Исполнитель сама запускает команды и выполняет видимую проверку браузера с vision.
При отсутствии терминала, sudo или GUI запроси доступ. В конце опубликуй отчёт автоматически.

## 1. Подготовка и короткий изолированный повтор T05

Начни с off/off, штатного VPN и пустой очереди. Сними состояние служб и хэши конфигов.
Прочитай последний отчёт. Проверь, остался ли упомянутый процесс tcpdump на WAN. При
совпадении PID сверяй команду, время старта и её файл захвата со старым опытом. Если это
прежний процесс в D, зафиксируй состояние и изменение размера файла за 10 секунд.
Если это обычный процесс того же опыта, останови только его и проверь, что он завершился.
При отсутствии процесса укажи, что следов незавершённого захвата нет. Для текущей проверки
короткой трёхфазной маршрутизации новый tcpdump на рабочем WAN не нужен.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
BASE=6de8375
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-t06.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
# Активируй существующий dev-venv, если pytest установлен в нём.
python3 -m pytest --portable tests/test_zapret2.py tests/test_desync_schema.py \
  tests/test_zapret2_panel.py tests/test_desync_standalone.py tests/test_desync_worker.py
python3 -m pytest -q tests/test_nfqws2.py tests/test_zapret2_bundle.py
sudo timeout --kill-after=20s 480s bash docs/helpers/desync_t05_ttl_lab.sh "$D/ttl-lab"
```

Захват в лаборатории идёт через AF_PACKET с неблокирующим чтением, ограничением 20 секунд
на фазу и явным файлом остановки. Код копирует только Lua-прибор в доступный для nfqws2
каталог в `/run`. Сделай сверку из [прежнего ТЗ](T05-REPLIES-AUTOTTL.md#1-короткий-опыт-на-ядре-thinkcentre-до-изменения-шлюза).
Для `warm_off` нужны пустая входная цепочка, отдельные client/server PCAP одной фазы,
TTL реального SYN/ACK и запись Lua от того же worker. Проверь отсутствие оставшихся
процессов захвата, namespaces и временного Lua этого запуска. Предыдущие PCAP на месте.

## 2. Проверка готовности комплекта без запуска очереди

По фактическим путям из установленных настроек найди бинарник и обе библиотеки.
Новые функции используют штатные пути `/opt/xgw/zapret2/1.0.7` или явно заданные
администратором внешние файлы с доверенными правами. Штатные Lua сверяются с SHA-256 из
закреплённого upstream. Для штатного бинарника с `bundle.json` проверяется его SHA и
метаданные. Для штатного бинарника без манифеста проверяется строка версии и ревизия,
которую сообщает сам бинарник. Запиши, какая ветвь проверки сработала. Строка версии
вручную установленного бинарника не подтверждает его воспроизводимую сборку.

```bash
sudo env PYTHONPATH="$D/source/src" python3 - <<'PY'
from xgw import config, nfqws2, zapret2
from xgw.desync import preflight
from xgw.net import cmd
from xgw.paths import Paths

cfg, _ = config.load(Paths.from_env().config_file)
cases = [("selected", zapret2.arguments(cfg))]
installation = nfqws2.find_installation(cfg)
if installation:
    cases.append(("engine", nfqws2.arguments(cfg, installation, "seqovl")))
else:
    print("engine unavailable")
for label, args in cases:
    preflight.check(args, cmd.run)
    print(label, "parse=ok lua_init=ok")
PY
```

Если Engine installation отсутствует, зафиксируй причину. На выделенной доверенной копии
комплекта проверь отрицательный сценарий
с изменённым Lua. В коротком Python-скрипте укажи `preflight.MANAGED_ROOT` только на
этот отдельный root-owned каталог в `/run`. Ожидается `bundle_mismatch` до запуска
бинарника. Параметры с неизвестным флагом на исходном комплекте должны дать
`bad_worker_options`. Для ошибки Lua добавь только в проверочный argv
`--lua-init=error('xgw_t06_control')`. Ожидается `lua_init_failed`; при иной классификации
зафиксируй поведение pinned nfqws2. Все три проверки вызывают только функции preflight,
реальные файлы под `/opt/xgw/zapret2` сохраняются. Сравни состояние очереди и PID до/после.

## 3. Установка и живые проверки двух воркеров

Возьми [порядок установки T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат)
с базой `BASE=6de8375`, следующим списком и флагом `--preflight-t06` во всех командах
install helper, включая rollback внутри restore.sh. Новый `desync/preflight.py`
архивируй только в `$PAYLOAD/code`. Три остальных файла архивируй в `code` и `base`:

```bash
FILES=(src/xgw/nfqws2.py src/xgw/zapret2.py src/xgw/watch/zapret2_control.py)
UNIT=xgw-desync-t06-rollback
PAYLOAD="/opt/xgw/handoff/desync-t06-$CODE"
BACKUP="/var/lib/xgw/handoff/desync-t06-$CODE"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" src/xgw/desync/preflight.py \
  docs/helpers/desync_batch1_install.py | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
```

Сверь фактическую базу побайтово. Держи таймер активным и сохрани штатный VPN до сетевой фазы.
После установки сверь 4/4 хэша и обе службы в off. На реальном стенде:

1. Включи Standalone с привычным списком YouTube и `hostfakesplit_md5`. Зафиксируй PID,
   очередь, gate и время до active. В обычном Chrome проверь минимум две минуты видео
   720p и свежие медиабайты на `xgw-zapret2`. Это контроль запуска и трафика. Точные
   отличия fake-пакетов между clone и static относятся к следующему H05.
2. Верни off и штатный VPN. Включи Engine auto с профилем seqovl только на короткое окно,
   чтобы подтвердить запуск второго воркера и обработку нового соединения. Сверь MainPID,
   netlink и очередь. При регрессии верни исходную политику и запиши точное условие.
3. Оцени исходы по трём уровням: разбор аргументов, исполнение Lua при инициализации,
   обработка реального трафика. Для различий режимов укажи отдельные результаты.
   `zapret-auto.lua` в установленный комплект не добавляется в этом проходе.

Выполни restore.sh с `accept` при PASS и `rollback` при регрессии. До остановки таймера
сверь хэши, off/off, VPN, рабочие службы и очередь. Публикуй частичный отчёт и при блокере.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t06-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t06-preflight.md"
# Сама создай REPORT с SHA, измерениями, состоянием стенда и ветвью проверки комплекта.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: verify T06 preflight on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch/rebase и обычный push. Публикуй агрегаты и коды, исходные записи
и содержимое приватных настроек оставляй на стенде.
