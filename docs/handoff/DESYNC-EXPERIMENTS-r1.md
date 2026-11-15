# T06/T08/T09/T10/T12 — парные опыты, а не обещание обхода

Запускается **только на Ubuntu 24.04** после подготовки из NEXT_STEP. Переменные
REPO/D/SOURCE/CODE берутся оттуда. Самостоятельно используй терминал и vision. Сначала
прочитай весь документ. Лимит одного прохода: 3 часа, 48 коротких media-проб (не более
8 MiB каждая), два финалиста по 15+5 минут видео, общий дополнительный трафик ≤3 GiB.
Недостающую часть честно отметь NOT_RUN. Один дефект окружения не отменяет независимые проверки.

Цель: установить, дают ли **конкретные реализации** выигрыш на этой линии, либо только
меняют параметры/создают ложноположительный тест. Отрицательный вывод допустим и полезен.
Большие C/Lua изменения из ROADMAP, которых пока нет в коде, невозможно проверить как готовые.

## 1. Проверки до вмешательства

Найди действующие PY/PACKAGE/CFG по ExecStart, `/usr/local/bin/xgw` и `/proc/<PID>/exe`.
Не подменяй их Python из тестового venv. Сохрани приватно версии/хэши:

```bash
sudo systemctl show xgw.service -p ExecStart -p MainPID -p ActiveState > "$D/xgw-before.txt"
sudo systemctl cat xgw.service > "$D/unit-before.txt"
sudo cat /usr/local/bin/xgw > "$D/launcher-before.txt"
PID=$(systemctl show xgw.service -p MainPID --value)
test "$PID" -gt 0
PY=$(sudo readlink -f "/proc/$PID/exe")
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
sudo test -f "$CFG"
sudo test -f "$PANEL"
sudo nft -j list ruleset > "$D/nft-before.json"
ip -j rule > "$D/rules-before.json"
ip -j route show table all > "$D/routes-before.json"
sudo sha256sum "$CFG" "$PANEL" > "$D/config-before.sha256"
sudo systemctl show xgw-xray.service xgw-nfqws2.service xgw-zapret2.service \
  -p Id -p ActiveState -p MainPID > "$D/workers-before.txt"
```

Подтверди, что эти пути действительно используются. Определи BIN и LUA из эффективной
конфигурации, разреши symlink BIN/LUA до root-owned реальных путей, проверь версии/хэши
относительно 1.0.7. Сохрани `ethtool -k` фактического WAN, nf_conntrack_acct, правила и
`/proc/net/netfilter/nfnetlink_queue`. Вначале selected mode и engine должны быть off,
очередь свободна. Иначе BLOCKED_CURRENT_STATE: без согласования с активной работой не выключай
чужой режим. BIN не должен быть оставшимся launcher. Не меняй bundle в этом проходе.

Используй dev-venv с pytest/ruff; при отсутствии создай в D. Никаких сетевых проверок в WSL.

```bash
python3 -m venv "$D/test-env"
"$D/test-env/bin/python" -m pip install pytest ruff
"$D/test-env/bin/python" -m pytest --portable \
  tests/test_desync_experiment.py tests/test_desync_schema.py
"$D/test-env/bin/python" -m pytest -q tests/test_nfqws2.py tests/test_nfq_lab.py tests/test_config.py
"$D/test-env/bin/python" -m ruff check src/xgw/desync/experiment.py \
  src/xgw/desync/schema.py src/xgw/nfqws2.py docs/helpers/nfq_lab.py tests/test_desync_experiment.py
"$D/test-env/bin/python" -m ruff check --select F,E9 docs/helpers/make_flowseal.py docs/helpers/flowseal_lab.py
mkdir "$D/generated"
python3 docs/helpers/make_flowseal.py docs/helpers/flowseal-youtube-source.json "$D/generated"
cmp "$D/generated/flowseal_lab.py" docs/helpers/flowseal_lab.py
cmp "$D/generated/translation.json" docs/helpers/flowseal-translation.json
PYTHONPATH="$SOURCE/src" python3 -m xgw.desync.experiment --help
```

Не переустанавливай весь рабочий пакет. `nfqws2.py`/schema с новыми профилями пока остаются
в checkout; тот же argv передаётся через лабораторный launcher, который понимает старый
установленный engine. Так GUI/backend приёмка не смешивается с опытом обхода.

## 2. Независимый откат до любых изменений настроек

Создай root-owned каталог вне noexec `/run` (прежний отчёт это уже выявил). R ниже только
для этого прохода. Снимок настроек восстанавливается целиком: во время опыта не редактируй
в GUI подписки/другие настройки; при обнаружении сторонней правки останови опыт и согласуй
возврат изменённых полей, не затирай её молча. Не восстанавливай весь старый nft ruleset.

```bash
RUN=$(date -u +%Y%m%dT%H%M%SZ)
R="/var/lib/xgw/handoff/desync-ab-$RUN"
sudo install -d -o root -g root -m 700 "$R"
sudo cp -a -- "$CFG" "$R/config.before"
sudo cp -a -- "$PANEL" "$R/panel.before"
sudo sysctl -n net.netfilter.nf_conntrack_acct | sudo tee "$R/acct.before" >/dev/null
sudo install -m 700 /dev/stdin "$R/restore.sh" <<'SH'
#!/bin/bash
set -euo pipefail
R=$1
CFG=$2
PANEL=$3
exec 9>"$R/restore.lock"
flock 9
test ! -e "$R/restored" || exit 0
systemctl stop xgw.service
systemctl stop xgw-nfqws2.service xgw-zapret2.service || true
# Same-directory rename: original modes/owner are retained.
for pair in config panel; do
  if [ "$pair" = config ]; then target=$CFG; else target=$PANEL; fi
  temp=$(mktemp "$(dirname "$target")/.xgw-ab-restore.XXXXXXXX")
  cp --preserve=mode,ownership -- "$R/$pair.before" "$temp"
  mv -fT -- "$temp" "$target"
done
sysctl -q -w "net.netfilter.nf_conntrack_acct=$(cat "$R/acct.before")"
systemctl start xgw.service
timeout 180 /usr/local/bin/xgw apply --now > "$R/restore-apply.log" 2>&1
touch "$R/restored"
SH
sudo systemd-run --unit="xgw-ab-rollback-$RUN" --on-active=30m \
  /bin/bash "$R/restore.sh" "$R" "$CFG" "$PANEL"
sudo systemctl is-active "xgw-ab-rollback-$RUN.timer"
```

**До первой правки** вызови этот restore вручную как no-op rehearsal, сверь исходные хэши,
API и сеть. Он штатно перезапустит daemon и применит исходную конфигурацию — запиши PID.
Если восстановление/доступ не прошли, не продолжай. Удали только флаг `R/restored`, перезапусти
этот timer и подтвердись через `systemctl list-timers`; резервные копии не меняй.
Перед каждым блоком/20-минутным видео заранее перезапускай этот timer и сверяй новый deadline.
Если timer уже выполнил возврат, текущий опыт INVALID: сначала проверить состояние и заново
подготовить фазу. При исключении/потере доступа немедленный возврат тем же restore; независимый
timer остаётся страховкой. После опыта отдельно убери только созданные тобой trace-объекты.

## 3. Управляемый launcher и прямой путь

1. По r3 §3/§4 и Flowseal §3/§4 (ссылки ниже) проверь ранний bypass `0x40000000` **до capture**,
   effective direct outbound без VPN chaining и физический WAN. Эти инварианты обязательны.
2. Временно добавь ровно YouTube-домены (`youtube.com`, `googlevideo.com`,
   `youtubei.googleapis.com`, `youtube-nocookie.com`, `ytimg.com`, `ggpht.com`) в direct.
   Сохрани старые записи. Изменение TOML делай через временный файл, tomllib, установленный
   `config.load`, проверку diff только routing.direct_domains и подтверждённых конфликтующих
   YouTube-правил; атомарный replace с исходными mode/uid/gid. Модель сама готовит и исполняет
   этот локальный редактор по фактическому TOML, не использует слепой sed и не просит владельца.
3. Отключи для тестовых потоков автоматический VPN fallback. Остальная маршрутизация,
   сервер VPN, подписки, Tailscale и LAN остаются исходными. Применяй штатный `xgw apply --now`.
4. Подтверди effective applied JSON и **наблюдаемый** media TCP tuple на WAN; no-proxy у curl
   не доказывает отсутствие прозрачного Xray/VPN. Xray может быть включён только как
   маршрутизатор direct. Без этих доказательств DIRECT=UNCONFIRMED и BENEFIT=INCONCLUSIVE.

Launcher устанавливается в root-owned `/opt/xgw/lib`, не в пользовательский checkout:

```bash
LAB=$(sudo mktemp -d /opt/xgw/lib/xgw-desync-ab.XXXXXXXX)
sudo chmod 755 "$LAB"
sudo install -o root -g root -m 755 "$SOURCE/docs/helpers/nfq_lab.py" "$LAB/nfqws2"
sudo python3 - "$LAB/nfqws2.json" "$BIN" <<'PY'
import json, os, sys
from pathlib import Path
settings = dict(binary=str(Path(sys.argv[2]).resolve(strict=True)), strategy="pass",
                reassembly="standard", debug=False,
                domains=["youtube.com", "googlevideo.com", "youtubei.googleapis.com",
                         "youtube-nocookie.com", "ytimg.com", "ggpht.com"])
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(settings, stream)
PY
```

Для engine используй **установленный T02 API** `managed.set_desync`, а не редактирование
двух конкурирующих zapret2-секций. В одной Bash-сессии определи:

```bash
set_engine() {
  sudo test ! -e "$R/restored"
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$LAB/nfqws2" "$LUA" "$1" <<'PY'
import sys
from dataclasses import asdict
from pathlib import Path
from xgw import config, managed
from xgw.desync import schema
cfg, warnings = config.load(sys.argv[1])
policy = schema.migrate(asdict(cfg.zapret2), source="gui-light")
policy["selected"]["mode"] = "off"
policy["engine"].update(engine=sys.argv[4], engine_profile="seqovl", engine_offload=False)
policy["runtime"].update(binary=sys.argv[2], lua_dir=sys.argv[3])
managed.set_desync(managed.path_for(Path(sys.argv[1])), policy)
actual, warnings = config.load(sys.argv[1])
assert actual.zapret2.engine == sys.argv[4]
assert actual.zapret2.binary == sys.argv[2] and not actual.zapret2.engine_offload
assert actual.zapret2.mode == "off"
PY
  sudo /usr/local/bin/xgw apply --now
}
```

Смена кандидата: `set_engine off` → дождись inactive и освобождения именно своей queue
→ атомарно замени только strategy/debug в LAB/nfqws2.json (права 0600)
→ **preflight** → `set_engine auto` → actual argv/PID/queue → новый поток. Нельзя просто
поменять JSON и считать, что работающий процесс перечитал его. Learned profile может
подменять engine_profile, поэтому launcher задаёт фактическую TLS-цепочку независимо от него.
Для preflight получи argv `nfqws2.arguments` из установленного пакета и передай его через
`subprocess.run([...args, '--intercept=0'], timeout=15)` без shell. `--dry-run` проверяй
отдельно. `intercept=0` исполняет lua-init, но не packet handlers. Нужен ещё живой trace.

## 4. Проверить сам прибор и получить воспроизводимый media URL

`desync.experiment` не меняет worker/маршрут и не доказывает путь. Один запуск: HTTPS GET,
один IP через resolve, без proxy env/curlrc/redirect/retry, лимит 128 KiB/s и 45s.
PASS требует фактического media Content-Type, нужного HTTP протокола, ≥1 MiB и ≥44s,
без паузы ≥10s после первых 64 KiB. Код curl 28 допускается **только** на этой временной
границе при выполненных условиях. Это проверка устойчивости при заданной скорости,
**не максимальная скорость канала и не воспроизведение видео**.

Из обычного видимого браузера на том же direct-пути сама получи в Network свежий URL
`videoplayback` длинного публичного ролика, IP и кодек. Signed URL/headers/pcap не публикуй.
Выбирай URL без ограничения маленьким сегментом и с достаточным телом для 45s.
Не удаляй подписанные query-параметры наугад. Если доступен лишь короткий сегмент, выбери
другой допустимый запрос; SHORT_TRANSFER не считать отказом обхода. URL должен быть получен
с того же выхода: YouTube может привязать его к IP. URL, полученный через VPN, может дать
403 на direct; это не свидетельство DPI. Не пытайся обходить авторизацию ролика.

```bash
mkdir -m 700 "$D/results"
# Создай $D/probe.json, mode 600, через редактор/скрипт модели; пример структуры ниже.
PYTHONPATH="$SOURCE/src" python3 -m xgw.desync.experiment probe \
  --spec "$D/probe.json" --out "$D/results" --curl /usr/bin/curl
```

Шаблон (значения URL/IP и SHA замени сама на наблюдаемые; это НЕ готовый сетевой адрес):

```json
{
  "url": "https://ACTUAL.googlevideo.com/videoplayback?PRIVATE_SIGNED_QUERY",
  "address": "ACTUAL_PUBLIC_IP",
  "network": "thinkcentre-wan-a",
  "policy_sha256": "64_HEX_DIGITS",
  "client": "ubuntu-curl",
  "protocol": "h2",
  "candidate": "fake-static-md5",
  "family": "fake-split",
  "route": "direct",
  "round": "window1-pair1"
}
```

`policy_sha256`: вычисли SHA-256 приватного JSON с CODE, bundle/Lua хэшами, effective
политикой маршрута/marks/offload/queue и параметрами проверки. Для пар A/B этот документ
одинаков; переменный candidate/JSON launcher из него исключён, их фактические хэши запиши
в приватный журнал каждого запуска. При смене сети/набора/политики — новый context.
`network`/`client` — обезличенные метки. SHA исполняемого curl также включается автоматически.
Для wrapper curl-impersonate дополнительно включи хэши его реального бинарника/библиотек
в policy-документ, а клиенту дай другое имя. Это разделит клиентские группы правильно.

Код возврата probe: 0 PASS, 1 измеренный иной исход, 2 ошибка ввода/среды. При `set -e`
вызывай probe внутри `if ...; then ...; else rc=$?; ...; fi`, чтобы сетевой FAIL не оборвал
всю матрицу. JSON результата содержит samples и непрозрачные ID, не URL/IP/домен.

Проверь: ранний EOF даёт SHORT_TRANSFER; 403 — HTTP_REFUSED_OR_STALE_URL; h2→h1.1 —
PROTOCOL_MISMATCH; неподдерживаемый h3-only — CLIENT_OPTIONS_UNSUPPORTED (не DPI FAIL).
При 403 получи свежий URL на **том же** выходе и повтори один раз. Не трать матрицу на
просроченный URL. Если валидный media URL получить нельзя, это BLOCKED_MEDIA_INPUT;
закончи независимые проверки Lua/перевода/GUI и опубликуй отчёт.

## 5. H05/H10: сравнение с одинаковыми условиями

Перед строкой фиксируй UTC, round, client hash, candidate, family, protocol, context_id,
target_id, реальный argv, окно захвата и доказательство direct. Одинаковые URL+IP+клиент
внутри пары. При истечении URL замени его **у обоих** и начни пару заново. Новый TCP-поток
обязателен; не очищай глобальный conntrack. После каждого блока сверяй offload и deadline.

| ID | Launcher strategy / условие | Что проверяется |
|---|---|---|
| A0 | engine off, direct | Нужен ли обход в данном окне |
| A1 | pass, engine auto | Влияние самого перехвата/reassembly |
| B | hostfakesplit-md5 | Ранее наблюдавшийся базовый кандидат |
| C | fake-static-md5 | Статический blob + rnd/rndsni + MD5 + multisplit 1,midsld |
| D | fake-clone-md5 | Clone реального CH; остальное как C |
| V | исходный VPN-путь, **свежий URL именно для VPN** | Контроль доступности сервиса, не парный URL-контроль DPI |

1. Один блок A0/A1/B/V. Для V временно восстанови только исходные YouTube-маршруты,
   проверь реальный VPN outbound, получи новый URL, после V верни подтверждённый direct.
2. Восемь валидных пар C/D: порядок CD, DC, CD, DC в первом окне и DC, CD, DC, CD во втором
   (между окнами ≥30 минут; займись Flowseal/анализом). Два запуска подряд одной тактики
   не являются двумя независимыми окнами. Это 16 проб, около 90 MiB.
3. Через каждые две пары повтори B и A0; если условия изменились у всех, не объединяй
   окна в один «процент успеха». Пиши результаты по каждому окну.
4. Для C/D один короткий debug/pcap-сеанс отдельно от timing: реальный ClientHello,
   созданный clone, размер fake, MD5 option только на fake, точки split, входящий ответ.
   Убедись, что clone не был skipped. Отсутствие Lua error не доказывает вызов функции.
   Не публикуй сырые ClientHello/pcap. Исходный и фейковый JA3/JA4 можно сравнить локально,
   если есть достоверный инструмент; отсутствие инструмента = NOT_RUN, не совпадение.
5. curl-impersonate: используй имеющийся проверенный совместимый executable, запиши
   источник/версию/хэши. Не загружай случайный бинарник. Если его нет — BLOCKED_DEPENDENCY
   **только для клиентского подпункта**, основной браузерный тест продолжай. По две пары
   C/D с новым client context; h3 только при поддержке обеих сторон, отдельный context.

Текущее D **не** портит KeyShare и не гарантирует JA3/JA4-равенство/отбрасывание сервером.
Вывод относится к clone+MD5+split этой версии. Для «больше рандомизации» не меняй одновременно
SNI, geometry, offload и транспорт — это не проверка одной причины.

## 6. T10: проверить исправления Flowseal

Используй закреплённый каталог Flowseal `2401b7a`, не свежий master. Получение данных и
установка DATA по §2/§6 [предыдущего ТЗ](../TEST-PLAN-REAL-MACHINE-0.2.0-flowseal-youtube.md).
37 исходных файлов сверяй SHA-256/git blob; выполняемых BAT/EXE не запускай. Создай blob-файлы
по BLOB_DECLS и user/exclude списки по тому же ТЗ. DATA root:root 0755, файлы 0644;
launcher/root-settings в /opt/xgw/lib. Сохрани старый launcher из BASE как контроль отдельно.

- Все 22 конфигурации: parse и intercept=0 отдельно, по 15s максимум; без активной очереди.
- На коротком захвате проверь `scope=source` против `scope=youtube`: удалены ВСЕ положительные
  hostlist/ipset формы, сохранены excludes; нет двойного hostlist-domains. Явный исключённый
  домен не должен попасть в метод. NO_MATCH исходного списка не считать отказом DPI.
- HTTP/TLS на общих портах: новый HTTP-блок имеет `filter-l7=http`, TLS — `tls`.
  По debug подтвердить реально выбранный блок на новых соединениях к допустимому тестовому
  домену. Для HTTP нужен известный отвечающий HTTP endpoint и явный allowlist только его;
  если его нет, ветка HTTP NOT_RUN, а не выдуманный сетевой PASS по строкам argv.
- Проверь ALT9/G12 и один ранее затронутый general/SIMPLE FAKE вариант: старый/новый launcher,
  одинаковые данные/scope/URL/IP/клиент. Минимум две пары, порядок ON/NO, NO/ON. При другом
  выборе блока теперь это **исправление покрытия**, а не доказательство силы самой тактики.
- S09/syndata на SYN не считать проверенным в scope=youtube: до SNI hostname отсутствует.
  Этот опыт требует адресного pre-SYN допуска T05, здесь NOT_RUN_DEPENDENCY. Не расширяй
  очередь на весь интернет ради прохождения строки.

При недостатке времени приоритет C/D, проверка исправленного L7, затем ALT9. Не гоняй
все 22 конфигурации по 20 минут: для первого эффекта достаточно ограниченной парной выборки.

## 7. Видео и признаки late stall — H01/H10

Выбери максимум два финалиста по валидным пробам. Отдельный видимый браузерный профиль,
без расширений/прокси, TCP-фаза с disable-quic, cache disabled. Не используй no-sandbox
или ignore-certificate-errors. Не используй буфер от предыдущего кандидата.

Для каждого: YouTube 720p либо 1080p вручную, 15 минут непрерывного видео + seek вперёд
на 5–10 минут + ещё 5 минут. Vision: текущие кадры/звук, Current/Optimal Res, buffer health,
скорость продвижения, dropped frames; фиксируй наблюдения минимум раз в минуту.
Пауза 60s и заполненный буфер — отдельные короткие отрицательные контроли для будущего
watchdog, **не время зачётного непрерывного воспроизведения**. После pause возобнови видео.

Сопоставь short HTTP, 45s media и реальный playback. Если первые два PASS, а браузер FAIL,
это воспроизводимый ложноположительный критерий отбора. Это не «реализация плохая» без
проверки TLS fingerprint/CDN/протокола/маршрута. Если все PASS, не объявляй HTTP достаточным.
При late stall собери ограниченные seq/ACK/RST/time и Network-события (максимум 60s/50 MiB),
раздели закрытие, нормальное окончание/паузы, потерю пакетов и ожидание ответа. ACK сам по себе
не означает demand. Пакетный trace должен включать входящее направление: без него H01/H04
INCONCLUSIVE. Нынешний probe — активный измеритель, он **не** пассивный Lua watchdog.

## 8. H02/H03/H09 и вердикты

### Уже доступный слой истории

Перезапусти CLI, убедись, что результаты сохранились и shortlist воспроизводится:

```bash
# CONTEXT — фактический context_id одного direct client/IP/protocol набора.
PYTHONPATH="$SOURCE/src" python3 -m xgw.desync.experiment shortlist \
  --results "$D/results" --context "$CONTEXT" > "$D/shortlist.json"
```

Выбираются не более трёх семейств с двумя последними PASS из разных round; новый FAIL
аннулирует старые победы. Это **не** auto cache/circular и не команда применить профиль.
На копии журнала проверь: TTL24h, future timestamps, другой context/network/client/IP,
повреждённый JSON, доступ не 0600/0700, >2048 записей. Ошибка не должна включить профиль.
Запусти две независимые probe одновременно **только для проверки уникальных файлов**, на
нейтральном контролируемом media endpoint; их нельзя использовать как timing A/B-данные.
Если такого endpoint нет — concurrency NOT_RUN. Не меняй часы шлюза для TTL-теста.

Если доступны два IP в одном /24 и в разных префиксах, запиши отличия результатов;
prefix_context совпадает в одной подсети, exact context различается. На одном IP польза
prefix-key не измеряется. Не принуждай другой CDN обслуживать URL, для которого он не предназначен.

### Турнир

В этом батче нет реализации blockcheck2 pruning. Можно сохранить матрицу для его будущего
replay, но нельзя честно подтвердить «5–8x ускорение» или orthogonal fooling без cross-product
опыта. H09 = NOT_IMPLEMENTED; T09 должен сравнить time-to-first-success, полный budget и
потерянных победителей. Три семейства shortlist сами по себе этого не доказывают.

### Решение по C/D

Покажи таблицу всех валидных пар: A pass/B fail, A fail/B pass, оба pass, оба fail, invalid.
Не скрывай invalid и не выбирай удобные часы. Для предварительного преимущества нужны
однонаправленные различия в **обоих** окнах, совпадение пути и подтверждённое исполнение
метода. Если ≥7 discordant пар в пользу D и ни одной в пользу C, двусторонний exact sign
test даёт p≤0.015625 (при условии независимости); временная корреляция уменьшает силу вывода.
Это ограниченное свидетельство на данной линии, не универсальное доказательство.
Мало discordant пар/оба одинаковы/меняющийся baseline → INCONCLUSIVE либо NO_BENEFIT_OBSERVED
с числом пар; воспроизводимое ухудшение → REGRESSION. Продвижение в default запрещено по
одному удачному 45s GET. Для production дополнительно нужны T03–T07 и длинное видео.

## 9. Возврат и отчёт

Закрой тестовый браузер. Выполни root restore вручную, затем проверь byte-identical CFG/PANEL,
исходный acct/offload, API/GUI/HTTPS, selected/engine off, отсутствие worker и своей очереди,
возврат исходных YouTube rules. Удали только свои trace rules/table по сохранённым handles,
не делай `flush ruleset`, не останавливай сторонние службы. Сохрани D/R для разбора приватно.
После успешного возврата останови именно свой rollback timer/service. При проблеме отката
сначала восстанови доступ и зафиксируй причину. Заполни TEMPLATE и автоматически опубликуй.

Дополнительные ранее проверенные процедуры:
[r3 — маршрут, launcher и trace](../TEST-PLAN-REAL-MACHINE-0.2.0-nfqws2-youtube-live-r3.md),
[Flowseal — данные и соответствие](../TEST-PLAN-REAL-MACHINE-0.2.0-flowseal-youtube.md).
Их требования о старом CODE заменены текущим NEXT_STEP; непроверенные архитектурные изменения
из старой широкой матрицы не являются поручением к массовому редактированию в этом проходе.
