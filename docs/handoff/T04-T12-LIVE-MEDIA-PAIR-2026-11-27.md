# ThinkCentre · один прямой медиазапрос YouTube и контроль через VPN

**Рабочее ТЗ T04/T12 для одной Flash на Ubuntu 24.04 LTS amd64.** Проверить, получает ли шлюз байты свежего видео через zapret2 в Standalone при паузе рабочего VPN. Контроль — тот же подписанный URL, IPv4 и диапазон через штатный VPN после возврата. При успешной паре проверить воспроизведение и маршрут в Selective. В предыдущем окне прямое соединение осталось в SYN-SENT, а VPN вернул HTTP 206 и 65 536 байт. [Отчёт 25 ноября](../reports/2026-11-25T171831Z_t04-tcp-connect-phase.md)

Flash сама открывает терминал рабочего пользователя, входит в панель и выполняет готовые команды. При отсутствии терминала, sudo, доступа к графическому сеансу или GitHub запросить соответствующий доступ и продолжить самостоятельно. Для изменения работающего шлюза нужно окно владельца с явным разрешением на временную паузу VPN, проверку и восстановление. Для Selective отдельно уточнить, входят ли в окно просмотр и один контролируемый отказ воркера. Предыдущее окно относилось к предыдущему прогону. Код и тесты готовит Codex.

## 1. Подготовка

Выполнить из полного клона XGW в одном Bash. Сохранить приватный путь `D` между вызовами терминала. Помощники закреплены на публичном коммите `fa09d5cc9a6de7ead7098fbc52aa777f94177218`, который уже применялся в живой проверке. Сценарий репетирует совместимость патча на копии установленного пакета. Версии установленных Xray и sing-box записать как есть. Если владелец ещё не дал окно, выполнить подготовку и зафиксировать доступность живой фазы.

```bash
umask 077
REPO=$(git rev-parse --show-toplevel)
CODE=fa09d5cc9a6de7ead7098fbc52aa777f94177218
D=$(mktemp -d "$HOME/xgw-media-pair.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
prepare_pair() (
  set -euo pipefail
  . /etc/os-release
  [[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
  cd "$REPO"
  git fetch --no-tags origin refs/heads/integration/zapret2-batch1
  git merge-base --is-ancestor "$CODE" FETCH_HEAD
  mkdir "$D/tree"
  git archive "$CODE" src docs/helpers | tar -x -C "$D/tree"
  command -v yt-dlp curl ss systemd-run >/dev/null
  sudo -n true
  bash "$D/tree/docs/helpers/standalone_return_preflight.sh" "$CODE" >"$D/preflight.log" 2>&1
  grep -Fxq STANDALONE_OVERLAY_INSTALLED_UNCHANGED "$D/preflight.log"
  sudo -n timeout -k 3 60 /usr/bin/python3 -I -B - snapshot \
    <"$D/tree/docs/helpers/audit_host_observe.py" >"$D/state.before"
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/config.before"
  touch "$D/prepared"
)
prepare_pair
```

При ошибке прочитать свой журнал и указать первый остановившийся шаг. Если требуется авторизация sudo, выполнить `sudo -v` в доступном терминале. Для pytest вне системного Python перед подготовкой экспортировать абсолютный `XGW_TEST_PYTHON`. Если подготовка остановилась из-за доступов, повторить её в новом приватном каталоге после получения доступа. При несовместимой установленной базе опубликовать `BLOCKED_BASE` с именем не прошедшего шага.

## 2. Один цикл на реальном шлюзе

После согласования окна выставить в текущем Bash `export XGW_CDN_LIVE=1`. Отсутствие окна даёт `LIVE=NOT_RUN`. Бюджет — один цикл Standalone → off, один ролик (по умолчанию `8plwv25NYRo`), диапазон 0–65535 на плечо. Сценарий получает свежий адрес через yt-dlp, проверяет диапазон до временной установки и использует встроенные ограниченные повторы при HTTP 302. При прямом таймауте повторного цикла нет. Для временной установки пяти файлов помощник назначает независимый откат через systemd на 25 минут. Самостоятельно проверить возврат после любого исхода.

```bash
run_pair() (
  set -euo pipefail
  [[ ${XGW_CDN_LIVE:-0} == 1 && -f "$D/prepared" ]]
  cd "$REPO"
  (set -C; : >"$D/live-started")
  live_rc=0
  bash "$D/tree/docs/helpers/standalone_return_live.sh" "$CODE" cdn-pair \
    >"$D/live.log" 2>&1 || live_rc=$?
  printf '%s\n' "$live_rc" >"$D/live.rc"
  settle_rc=0
  sudo -n timeout -k 3 350 env "PYTHONPATH=$D/tree:$D/tree/src" /usr/bin/python3 -B -P \
    -m docs.helpers.standalone_topology stable 330 >"$D/settled.log" 2>&1 || settle_rc=$?
  snapshot_rc=0
  sudo -n timeout -k 3 60 /usr/bin/python3 -I -B - snapshot \
    <"$D/tree/docs/helpers/audit_host_observe.py" >"$D/state.after" || snapshot_rc=$?
  hashes_rc=0
  sudo -n sha256sum --check --status "$D/config.before" || hashes_rc=$?
  printf 'LIVE=%s SETTLED=%s SNAPSHOT=%s CONFIG_HASHES=%s\n' "$live_rc" "$settle_rc" "$snapshot_rc" "$hashes_rc" | tee "$D/exits"
)
run_pair
```

Из строки `PRIVATE_ARTIFACTS` в `$D/live.log` взять каталог самого помощника. Прочитать `steps`, `vpn-prepare.out`, `direct-verdict.out`, `pair-verdict.out`, `cdn-comparison.out` и файлы отдельных плеч, если они появились. Указать оба HTTP-кода, фактические байты, `content_range_ok`, совпадение цели/подключённого IPv4, атрибуцию маршрута и выбранную попытку. При таймауте привести фазу curl, наблюдаемые состояния исходящего сокета, число опросов и доступные ретрансляции. Окончательный статус пары берётся из данных помощника. Код выхода оболочки сам по себе оценивает выполнение процедуры.

В том же Bash выполнить проверку срока выбранного подписанного ресурса. Код учитывает фактическую попытку на каждом плече. В отчёт вынести только итог. При `PAIR_TTL=UNKNOWN` или `EXPIRED` итог пары — `INCONCLUSIVE`.

```bash
PAIR_RUN=$(sed -n 's/^PRIVATE_ARTIFACTS //p' "$D/live.log" | head -n 1)
PYTHONPATH="$D/tree/src" /usr/bin/python3 -B -P - "$PAIR_RUN" <<'PY'
import json
import sys
from pathlib import Path
from xgw.desync.schema import youtube_cdn_expiry

root = Path(sys.argv[1])
def read(name):
    return json.loads((root / name).read_bytes())

try:
    if not root.is_absolute():
        raise ValueError("missing live directory")
    pair = read("pair-verdict.out")
    direct = read("direct-retry-cdn.out" if pair.get("direct_attempt") == "retry" else "direct-cdn.out")
    vpn = read("off-cdn.out")
    if pair["vpn_attempt"] == "retry":
        vpn = vpn["retry"]
    expiry = youtube_cdn_expiry(read("pair-format.json")["url"])
    windows = [(r["started"], r["finished"]) for r in (direct, vpn)]
    if expiry is None or not all(0 < a <= b for a, b in windows):
        raise ValueError("missing time")
    result = "OK" if all(b < expiry for _, b in windows) else "EXPIRED"
except (OSError, KeyError, TypeError, ValueError):
    result = "UNKNOWN"
print("PAIR_TTL=" + result)
PY
```

Сверить `state.before` и `state.after` приватно по категориям (службы и их идентичность, слушатели, маршруты и правила), одинаковые хеши конфигураций, итог HTTPS через штатный VPN, конечный слот и окончание drain. Для успешного временного применения нужны `STANDALONE_LIVE_FILES_AND_VPN_RESTORED`, `STANDALONE_LIVE_FINAL_MANAGED`, успешный `SETTLED` и исходный слот. При расхождении установить, начиналось ли применение. Если возврат после применения не подтверждён, выполнить §3 закреплённой инструкции с каталогом именно этого живого запуска, повторить сверку и сразу сообщить владельцу остаток. [Возврат при обрыве терминала](https://github.com/1521572-lang/xgw/blob/fa09d5cc9a6de7ead7098fbc52aa777f94177218/docs/handoff/STANDALONE-MANAGED-LIVE-2026-11-23.md)

| Наблюдение | Действие исполнителя |
|---|---|
| Истёк URL, нет положительного VPN-контроля, различаются цели или отсутствует атрибуция | Указать конкретное условие и статус `INCONCLUSIVE`. Завершить сверку шлюза и опубликовать. |
| Один адрес и оба маршрута подтверждены, VPN получил точный диапазон, прямой запрос завершился ошибкой или неполным ответом | `DIRECT_RANGE=FAIL` для этого ресурса и окна. Завершить серию, указать `PLAYBACK/SEEK/DAY=NOT_RUN`. |
| Оба плеча получили HTTP 206, точный Content-Range и 65 536 байт, `same_target`, `same_connected_peer`, оба маршрута подтверждены, `state=pair_verified` | `PAIR=PASS`. После подтверждённого восстановления перейти к §3 в согласованном окне. |

## 3. Воспроизведение при успешной паре

Использовать ту же закреплённую копию `$D/tree`, установленный шлюз и один публичный ролик с 720p и достаточной длительностью (>35 минут). Если из §2 использовался другой ролик, указать это. Перед началом сохранить сведения о паре в прежнем каталоге. Для измерения плеера использовать отдельный приватный каталог. Дать на фазы плеера и возврата до 60 минут рабочего окна. При недостатке разрешённого времени сохранить результат пары и причину `NOT_RUN`.

1. В обычной графической сессии задать `PAIR_DIR=$D`, `D=$(mktemp -d "$HOME/xgw-selective-watch.XXXXXXXX")`, `cd "$PAIR_DIR/tree"`, `export PYTHONPATH="$PWD:$PWD/src"`, `PY=/usr/bin/python3`, `CHROME=$(command -v google-chrome || command -v google-chrome-stable)`, `VIDEO=${XGW_T09_VIDEO:-8plwv25NYRo}`, `PROFILE=fake_md5`. Создать отдельный профиль Chrome, получить обычный VPN-контроль и проверить запись плеера по §2 инструкции по Chrome. Использовать функции `open_run`, `vpn_address`, `verify_run` и расширение из закреплённого дерева. [Измерение плеера и NetLog](https://github.com/1521572-lang/xgw/blob/fa09d5cc9a6de7ead7098fbc52aa777f94177218/docs/handoff/PLAYBACK-2026-11-20.md)
2. Из §3 той же инструкции выполнить **только блок сохранения конфигов, lock, таймера и функции `live`**. Проверить успешный захват общего lock, активный независимый таймер, наличие резервной копии и сохранённых хешей до изменения политики. При свежем off/off взять абсолютный путь к `pair-format.json` из каталога помощника §2 как `FORMAT`. При истечении ссылки записать `ADMISSION=NOT_RUN (expired)`. Пока `live` успешен, выполнить `"$PY" -B -P -m docs.helpers.selective_admission admit "$D/receipt" --format "$FORMAT" --checks 1 --timeout 180 >"$D/admission.log" 2>&1`. Нужен успешный допуск на текущей ревизии и применённое правило Selective (проверить `client_zapret2_rule` в снимке `xgw.desync.route_evidence snapshot` под sudo). При отказе сразу перейти к восстановлению по §5 инструкции Chrome. Используется один профиль без перебора.
3. При допуске выполнить §4 инструкции Chrome, от начала §4 до конца анализа двух окон, включая параллельный контроль обычного сайта. Единственный опыт с отказом описан в п. 4 ниже. Для старта собрать 900 пригодных секунд, после перемотки за пределы буфера ≥400 с — ещё 300 пригодных секунд. Порог прогресса ≥98%, 720p ≥95%, разрыв ≤5 с, свежие медиаданные ≥1 МиБ в каждом окне. Работать с Chrome через vision. Численные выводы брать из записи плеера, NetLog и результата проверки. В каждом окне сверить время медиабайт с помеченным сокетом к тому же CDN, ростом downlink и очереди сверх фона вне служебной пробы, параллельным обычным сайтом через исходный VPN. При нехватке поля указать `MEDIA_PATH=PARTIAL` или `UNKNOWN`.
4. Один контролируемый отказ допустим только в согласованном окне при успешных фазах, живом таймере, подтверждённой ревизии и владельце очереди. Flash выполняет единственную остановку MainPID по §4 инструкции Chrome. Для измерения сохранить до/после GET свежую карточку fallback той же ревизии, снятое клиентское правило, точный диапазон нового соединения и его VPN-маршрут. Если доказательное окно пропущено, поставить `FALLBACK=PARTIAL`. Вторично останавливать воркер не требуется. [Критерии нового соединения, §4](https://github.com/1521572-lang/xgw/blob/fa09d5cc9a6de7ead7098fbc52aa777f94177218/docs/handoff/MEDIA-PROOF-2026-11-20-R2.md)
5. Завершить §5 инструкции Chrome, вернуть исходную политику и подтвердить итоговые конфиги, состояние служб, поколение после drain и HTTPS обычного VPN. Провести это также после частичного результата. За этот проход оформить один отчёт. Для суток Selective указать, какие из условий допуска выполнены. Сами сутки имеют отдельное ТЗ и окно. [Суточная проверка](https://github.com/1521572-lang/xgw/blob/fa09d5cc9a6de7ead7098fbc52aa777f94177218/docs/handoff/T12-SELECTIVE-DAY-2026-11-25.md)

## 4. Один отчёт, автоматическая публикация

Записать SHA карточки и инструментов, фактические UTC и Ubuntu, версии ядер, разрешённые фазы, исход подготовки, результат каждой попытки, восстановление и состояния PAIR, PLAYBACK, SEEK, MEDIA_PATH, ORDINARY_VPN, FALLBACK, DAY. Для пропуска указать причину. Опубликовать только агрегаты. URL с подписью, IP, cookies, конфиги, сырые журналы и файлы NetLog остаются в приватных каталогах машины.

Flash сама пишет Markdown по фактическим данным и указывает его абсолютный путь в `REPORT_SRC`. Затем выполняет блок из полного клона XGW, в том числе после блокера или отказа. При отсутствии права записи запросить доступ и повторить публикацию того же отчёта.

```bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git -C "${REPO:-.}" rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_t04-t12-live-media-pair.md
  export GIT_INDEX_FILE="$pub/index"
  blob=$(git -C "$repo" hash-object -w -- "$REPORT_SRC")
  local_ref=refs/xgw-report/$(basename "$pub")
  trap 'git -C "$repo" update-ref -d "$local_ref"' EXIT
  for i in 1 2 3; do
    git -C "$repo" fetch --quiet --no-tags --no-write-fetch-head origin "$ref:$local_ref"
    tip=$(git -C "$repo" rev-parse "$local_ref")
    if prev=$(git -C "$repo" rev-parse --verify "$tip:$file" 2>/dev/null); then
      [[ $prev == "$blob" ]] || exit 1
      printf 'PUBLISHED %s %s\n' "$tip" "$file"
      exit 0
    fi
    git -C "$repo" read-tree "$tip"
    git -C "$repo" update-index --add --cacheinfo "100644,$blob,$file"
    tree=$(git -C "$repo" write-tree)
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre T04/T12 live media pair')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
```

Вернуть ссылку на коммит и одной строкой ответить, прошли ли реальные байты напрямую и удалось ли подтвердить маршрут воспроизведения.
