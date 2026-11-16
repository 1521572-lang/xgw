# T07/H01 — остановки плеера и совместимость zapret-auto

Стенд — ThinkCentre, Ubuntu **24.04 LTS**. База отчёта H05 — `fbfe9a1`.
Исполнитель сама запускает команды, работает с Chrome через GUI и vision и публикует отчёт.
Если недоступны терминал, sudo или GUI, запроси доступ к нужному инструменту.

На этом этапе xgw-auto читает записи браузера. Он отмечает интервалы 15, 30 и 60 с после
подтверждённого начала воспроизведения, когда позиция не движется, готовых данных мало и
буфер ≤1 с. Пауза, перемотка, переход к другому видео и разрыв измерения закрывают интервал.
Причина сигнала остаётся `unknown`. При наличии CDP видно, оставались ли медиазапросы
активными без прироста полученных данных. Этот показатель относится ко вкладке.

## 1. Подготовка и прежний захват

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor fbfe9a1 "$CODE"
D=$(mktemp -d "$HOME/xgw-t07.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
python3 -m pytest --portable tests/test_desync_shadow.py tests/test_youtube_telemetry.py \
  tests/test_desync_experiment.py
```

Сними исходные PID и режимы, хэши конфигов, очередь, offload, acct и штатный VPN. Проверь
свободное место на разделе прежнего захвата и PID 1935908 по инструкции H05. Если совпали
время старта, команда и файл, проверь рост и доступ к процессу. `NSpid` сам по себе не
показывает user namespace. Сравни ссылки `/proc/1/ns/user`, `/proc/self/ns/user` и
`/proc/1935908/ns/user` из привилегированной консоли. Сигнал из нового контекста имеет
смысл, если появился доступ, которого не было в H05. Если файл растёт и доступ всё ещё
отклонён, запроси помощь администратора хоста с остановкой процесса и укажи текущий рост.
Не запускай служебный тест с большим логом, если для него мало места. Выводы о причине
`EPERM` привязывай к фактически проверенным правам. Новый WAN-захват не нужен.

## 2. Закреплённый Lua и пробел в диагностике H05

Проверь исходник по SHA-256 в UPSTREAM.json и два установленных Lua по тому же манифесту.
Запусти штатный бинарник с временной копией zapret-auto в отдельном сетевом namespace.
`--dry-run` проверяет аргументы, `--intercept=0` исполняет Lua и завершает процесс.
Рабочий комплект и `bundle.json` для этого шага остаются на своих путях, а новый файл
добавляется только во временный каталог.

```bash
VENDOR=$D/source/third_party/zapret2
BUNDLE=$(realpath /opt/xgw/zapret2/1.0.7)
(
  cd "$VENDOR"
  python3 -c 'import json; m=json.load(open("UPSTREAM.json")); p="lua/zapret-auto.lua"; print(m["files"][p], p)' |
    sha256sum -c -
)
(
  cd "$BUNDLE"
  python3 -c '
import json, sys
with open(sys.argv[1]) as source:
    files = json.load(source)["files"]
for name in ("lua/zapret-lib.lua", "lua/zapret-antidpi.lua"):
    print(files[name], name)
' "$VENDOR/UPSTREAM.json" | sha256sum -c -
)
"$BUNDLE/nfqws2" --version
(
  STAGE=$(sudo mktemp -d /run/xgw-t07-lua.XXXXXXXX)
  trap 'sudo rm -f -- "$STAGE/zapret-auto.lua"; sudo rmdir -- "$STAGE"' EXIT
  sudo chmod 0755 "$STAGE"
  sudo install -m 0644 "$VENDOR/lua/zapret-auto.lua" "$STAGE/zapret-auto.lua"
  sudo sha256sum "$STAGE/zapret-auto.lua"
  LUA=("--lua-init=@$BUNDLE/lua/zapret-lib.lua"
       "--lua-init=@$BUNDLE/lua/zapret-antidpi.lua"
       "--lua-init=@$STAGE/zapret-auto.lua"
       '--lua-init=assert(type(circular)=="function" and type(automate_host_record)=="function"); assert(standard_detector_defaults({}).inseq==4096); print("XGW_T07_LUA_OK")')
  sudo unshare --net -- timeout 15s "$BUNDLE/nfqws2" --qnum=201 "${LUA[@]}" --dry-run
  sudo unshare --net -- timeout 15s "$BUNDLE/nfqws2" --qnum=201 "${LUA[@]}" --intercept=0 |
    tee "$D/lua-init.log"
  grep -Fx XGW_T07_LUA_OK "$D/lua-init.log"
)
```

Сверь SHA временной копии с манифестом. При несовпадении исходного бинарника/библиотек
с закреплённым комплектом зафиксируй причину и отдельно продолжи браузерную часть.
Загрузка проверяет Lua API. Сам `circular` импортируется, его запуск на потоке и ротация
профилей остаются для следующих этапов. [Исходник upstream](https://github.com/bol-van/zapret2/blob/038c97e5819df10f8e8c22a2f1fffe57f2f7379b/lua/zapret-auto.lua).

Повтори изолированный H05 с обычным и уменьшенным MTU:

```bash
for mode in h05 h05-small-mtu; do
  sudo timeout --kill-after=20s 240s bash docs/helpers/desync_t05_ttl_lab.sh "$D/$mode" "$mode"
done
```

Проверь оба источника fake и контроль тела HTTPS. Сопоставь `XGW_H05 reassembled=0/1`
с клиентским PCAP и fake с TCP MD5 на серверном интерфейсе. Поле теперь берётся из
`desync.replay`: в закреплённом C `reasm_data` заполняется и для обычного пакета.
Старые строки H05 сами по себе не различают эти случаи. Ожидаемые исходы — полный
ClientHello в обычной фазе и TCP reassembly в фазе MTU 400. Если два пути не получилось
разделить, зафиксируй фактические сегменты и не записывай полное покрытие. После каждого
запуска сверь возврат acct и отсутствие остатков процессов/изолированных namespaces.

## 3. Chrome на реальном YouTube

Используй [сценарий обычного Chrome](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome) и ролик
`8plwv25NYRo`, скорость 1×, 720p. Делай новый профиль на режим, папку на каждую запись.
Метки ставь тем же `__xgwCapture.mark(...)`. Через vision сверь момент остановки,
прогресс и показанный буфер. В DevTools оставь вкладку активной и открытую панель
Network. Измерь время CPU/максимум RSS анализатора при наличии `/usr/bin/time`.

- **Штатный VPN, отрицательный контроль.** Отметь минимум минуту стабильного просмотра,
  фазу с полным буфером и отсутствием запросов, паузу ≥65 с, возобновление, перемотку,
  нормальный конец видео. Если был переход между CDN, сравни время смены запроса с
  буфером и прогрессом. Изменение CDN естественно; при одном CDN оставь сценарий открытым.
- **Контролируемое истощение буфера.** В отдельной тестовой вкладке после начала
  воспроизведения отметь `network_off`, включи Offline в её Network, отметь
  `visible_wait` при фактической остановке, оставь вкладку видимой. Дождись до 70 с
  после остановки, затем верни No throttling и отметь `network_on`. Если плеер раньше
  показал конечную ошибку, запиши длительность ожидания и какие пороги удалось
  проверить. При возможности повтори с ограничением скорости вместо Offline.
  Для сравнения используй время низкого буфера и отсутствия прогресса, а также
  независимые метки/vision. В обычном Chrome без CDP ожидаем `media_network=unavailable`.
- **Standalone без VPN.** На уже установленном H05 подготовь копию panel и
  [таймер возврата](YOUTUBE-TELEMETRY.md#standalone-на-уже-установленном-t04).
  Используй [условия Chrome для H05](T06-H05.md#2-установка-и-пары-в-обычном-chrome). Сначала
  используй `hostfakesplit_md5` ≥2 мин, затем `fake_clone_md5` 15 мин + перемотка + 5 мин.
  Подтверди свежий SABR, счётчики `xgw-zapret2`, владельца очереди и VPN-мосты inactive.
  Обработай запись каждой фазы. Если доступ к возврату режима отсутствует, запроси его и
  опубликуй VPN-калибровку отдельно. Применяй только временную политику; восстанови
  исходную перед остановкой таймера.

Для каждого сохранённого `player.json` из Snippet:

```bash
export PYTHONPATH="$D/source/src"
python3 -m xgw.desync.shadow "$TRIAL_DIR/player.json" --video 8plwv25NYRo \
  >"$TRIAL_DIR/shadow.json"
```

Если на стенде есть текущие записи `samples.jsonl` от [CDP-коллектора](YOUTUBE-TELEMETRY.md),
проверь второй формат той же командой. `pending_without_data` означает наличие
активных запросов и отсутствие прироста данных в наблюдаемых точках всего интервала;
`mixed` означает смену доступности или состояния. Сопоставь сигналы с сетевым логом
на шкале того же опыта. При неполной записи причина остаётся `unknown`.

Для каждого порога отдельно укажи длительные окна с истинной остановкой и без неё,
TP/FP/FN, задержку от начала ожидания, время отсутствующих наблюдений и объём выборки.
Если окно прервалось до порога или плеер скрыл измерение, пометь его как непроверенное.
Отчёт должен разделять результат Lua smoke, H05 packet replay и метрики H01. Один WAN
даёт результат для измеренного окна. Службы, пакетные таймеры и политики ротации
анализатор не вызывает. Поздний TCP RST и контексты кэша H02/H03 относятся к
следующему этапу измерения.

## 4. Возврат и автоматическая публикация

Подтверди исходные mode/engine, пустую очередь, PID, хэши, acct/offload, выход VPN и
состояние старого захвата. Полные браузерные записи, pcap, IP, URL и конфиги оставь на
машине. В Git опубликуй обезличенные метрики, точный SHA, блокеры и оставленное состояние,
даже если часть проверок не состоялась.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-t07-shadow-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t07-shadow.md"
# Сама создай REPORT с итогом каждого этапа.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify T07 playback shadow on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Если ветка продвинулась, сделай fetch/rebase и обычный push.
