# ТЗ Flash: wave3s — локальная сверка REALITY без запросов

## 1. Результат R и задача S

Рабочая схема XGW → Wi-Fi-роутер → устройства — baseline. Сохранять HEALTHY/on,
WAN/LAN/Tailscale/pin/pool/службы/правила. Не выключать VPN, не install/G1/новая SSH-опись.

ReportRbd512410a5515692a3870c8aba153535c742a0d2: CURRENT_BRIDGE_RECORDED/rc0,
request1/bodyfalse/curl97/HTTP0/bytes0/.977с/SOCKSreply1. В новом journal одна related
строка с литералом reality_verification_failed и ведущим уровнемERROR. Контекст/ownerboth/
currentconfigdigest/process/6PID/settings3/boot/pin сохранены. Это принятый отрицательный
факт нового текущего входа, не BODY_PASS. Npartial/Pblocked0/Qreadonly сохраняются.
HistoricalidentityN→R не доказана. Нельзя утверждать, что в N уже был тот же literalREALITY,
или что сеть/сервер/ТСПУ виноваты; endpoint-specific defect также не исключён.
Отсутствие authfailuretext не доказывает отсутствие всех проблем авторизации.

S отвечает на один статический вопрос: согласуются ли поля текущего appliedREALITY
с доступными локальными источниками ПОСЛЕ штатного парсера и корректна ли их базовая форма?
Это проверка передачи parsedsource→appliedconfig, не доказательство корректности исходной
подписки/парсера/сервера. Повтор GET/скана не нужен. Никаких изменений по обнаруженномуфлагу.

Сначала проверить oldRsourceSHA/summaryshape/plan. Если текущий SBconfigdigest совпал с
сохранённым Rplan — contract_relation_to_R=CONFIG_DIGEST_MATCHES_R_PLAN. Если не совпал —
CURRENT_ONLY_NOT_R_CONTRACT: S анализирует только современный вход по сохранённому ключу,
не выдаёт его параметры за старые R. Не откатывать конфиг и не пересоздавать R.
Доступный sourcecache тоже ТЕКУЩИЙ: не утверждать, что именно эта версия породила R.

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7. Runtime не устанавливать/не менять.
Записать testedHEAD/tree. Пять frozen файлов:
- wave3_reality_contract.py: SHA256 `3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c`;
- wave3_single_bridge.py: SHA256 `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Единственный CLI — новыйwave3_reality_contract.py. P/O/N/L только библиотеки context/
selector/reader; их request/journal/main НЕ вызывать. Старый Rsource читается по SHA
38b40524dad5aa76742100cea46b07853b9c9d06940ffc17da3094384bdd59f4, не импортируется/не запускается.

## 2. Эффекты, запреты, STOP, приватность

Разрешены Gitfetch/FF/публикацияодногоMarkdown, readonlyconfig/proc/sys/nft/systemctl/
pinфиксированнымSELECTSQLite mode=ro; oldRsource/summary/plan root700/600.
Источники: только bodyкэш настроенных подписок в фиксированном /var/lib/xgw/cache,
файлы root600, regular/non-symlink, и links из ТЕКУЩЕГО config.manual в памяти.
Никаких URLfetch/чтения file://оригиналов/refresh/engine.load/Store/schema/APIwrites.
Штатные parse_body/parse_links_text — чистый разбор локальных bytes, без загрузчиков.
Отдельная проверка полного установленного .pyдерева перед S обязательна (S2.4).

Пределы:32cacheисточника,≤2MiB на body,≤8MiB принятых cachebytes суммарно,
manual≤2MiB отдельно; после накопления>5000узлов дальнейшие источники не разбираются.
Один источник может дать больше5000узлов — это не строгий предел итогового количества.
Нет/ошибка/публичныйmode/слишкомбольшойcache→coverage counters, не загрузка заново.
Кэш read-only через O_NOFOLLOW/O_NONBLOCK, не Store/SubscriptionCache.load/save.
Digest прочитанных cachebody сравнивается до/после S, без публикации значений.

Запрещены любые curl/--version/GET/SOCKS/DNS/ping/SSH/journal/scan/rescan/health запросы,
новые listeners/netns, pin/unpin/rotation/другойузел/цель, enable/disable/install/apply/
netupdown/restart/reload/kill/loglevel, nft/ip/NM/sysctl/config/pool/Tailscale/WAN/LAN мутации.
Не запускать N/O/P/Q/R/Srun повторно/старые permission/fault/guardian/offrollback.
Шлюз продолжает обычную работу, S инициирует НОЛЬ новых соединений.

STOP останавливает только тест. Off→WAIT_OWNER_ON, модель его не включает. Нет Rданных/
sourceSHA/treeidentity→BLOCKED, зависимые этапыNOT_RUN, данные не восстанавливатьдогадкой.
Новые files только /run/xgw-w3s(root700/600) и ~/xgw-w3s. Exclusive started запрещает retry
даже после краша. Не удалить/переименоватькаталоги/создаватьдругиерадиPASS/не reboot.
Обрывсвязи→послевозвратаshow/status/отчёт, не run/переключения. Recoverytimer не нужен:
нет сетевых мутаций, always_off guardian запрещён, возвратсети не зависит от следующейкоманды.

В Git/чат только summary нового helper и обезличенныйMarkdown. Никаких rawsource/cache/
config/URI/URL/IP/MAC/UUID/ключей/паролей/SNI/портов/имён/fp/тегов/PID/NIC/DBrows/logs/
исключений/privateplan/config+targethashes/скриншотов. ИсходникиSHA/GitHEAD разрешены.
Даже публичныйREALITYkey тут не выводить. Не cat старыйplan/cache для ручнойсверки.

Одна команда/целыйблок на шаг, ждатьrc/marker; не вводить код в sudo prompt.
Unknownrc писатьUNKNOWN. STOP→раздел7 с NOT_RUN зависимых проверок; продукт не трогать.

## 3. S1: терминал и заметки

### S1.1. Проверить среду

```bash
uname -s
```

Ожидается Linux на ThinkCentre. Это не Windows/PowerShell и не локальная VM разработчика.

#### S1.1b. Shell владельца

```bash
test "$(id -u)" -ne 0 && test -d "$HOME/zcod/xgw/.git" && printf 'OWNER_SHELL_OK\n'
```

Нужен OWNER_SHELL_OK: обычный shell владельца, не root-shell. Все последующие `$HOME`
относятся к владельцу. Если маркера нет — STOP, не угадывать путь/пользователя.

### S1.2. Создать новые заметки и заранее проверить sudo

```bash
python3 -I -B - <<'PY'
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
root=Path.home()/'xgw-w3s'
if root.is_symlink():
    raise SystemExit('STOP_NOTES_SYMLINK')
if root.exists():
    if not root.is_dir() or root.stat().st_uid!=__import__('os').getuid():
        raise SystemExit('STOP_NOTES_OWNER')
    if {p.name for p in root.iterdir()}-{'plan.md'}:
        raise SystemExit('STOP_NOTES_ALREADY_USED')
    root.chmod(0o700)
else:
    root.mkdir(mode=0o700,exist_ok=False)
stamp=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
with (root/'run-start.txt').open('x') as stream:
    stream.write(stamp+'\n')
print('NOTES_CREATED',stamp)
PY
```

Допустим новый каталог или заранее созданный свой каталог только сplan.md. Сохранить plan,
не удалять/пересоздавать. Другие файлы/run-start означают уже начатый опыт — STOP, не новый
каталог радиPASS. Run-start создаётся эксклюзивно. После NOTES_CREATED:

#### S1.2b. Проверка sudo

```bash
sudo -n true
```

Код0 означает, что этот инструментальный канал уже может выполнять sudo без запроса пароля.
Если нужен пароль/нет кэша, новых sudo-команд модель не запускает. Владелец в своём настоящем
терминале может выполнить `sudo -v` и ввести пароль непосредственно туда. После его сообщения
повторить ТОЛЬКО read-only проверку `sudo -n true` в том же инструментальном канале.
TTY/timestamp sudo разных терминалов могут различаться: успех владельца не заменяет код0
этой проверки. Если снова отказ — STOP до проверок; отчёт S1=BLOCKED_TOOL_SUDO,
зависимые этапы NOT_RUN. Не менять sudoers, не передавать пароль через stdin/команду/заметки.
Это заранее предусмотренный путь подготовки. Сетевые изменения запрещены.
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3s/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: рабочий on и идентичность

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Ожидается SOURCE_PREFLIGHT_OK. Сохранить фактические HEAD/tree в заметках. Любая ошибка,
грязный клон, другая ветка или runtime diff — STOP. Не reset/checkout/rebase/force и не
переносить старые файлы поверх нового Git-кода. Загрузка нового ТЗ не устанавливает продукт.

### S2.2. Прочитать режим, не переключать его

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются HEALTHY и включённый перехват. Если off — WAIT_OWNER_ON по разделу2;
нет ожидаемых строк/traceback — STOP_READ. Код pipeline не заменяет чтение результата.
Сохранить буквальные строки версий. Не выводить весь статус.

### S2.2b. Сохранить текущий режим пула

```bash
sudo -n xgw pool | head -1
```

Это фиксация текущего выбора, не требование переключить пул в off. Режим до/после
должен остаться тем же. При неизвестности — STOP_READ без изменения настроек.

### S2.3. Проверить реально установленный код

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
repo=Path(sys.argv[1])
ok=True
for rel in ('install.py','net/sysctl.py','diag.py','net/nft.py'):
    try:
        wanted=(repo/'src/xgw'/rel).read_bytes()
        actual=(Path('/opt/xgw/lib/xgw')/rel).read_bytes()
        equal=hashlib.sha256(wanted).digest()==hashlib.sha256(actual).digest()
    except OSError:
        equal=False
    print(rel,'installed_equals_pinned_source=',equal)
    ok=ok and equal
print('INSTALLED_SOURCE_OK' if ok else 'STOP_INSTALLED_SOURCE_MISMATCH')
raise SystemExit(0 if ok else 3)
PY
```

Нужны четыре True и INSTALLED_SOURCE_OK. Иначе STOP; не копировать файлы/не запускать installer.

### S2.4. Проверить установленное Python-дерево для чистого локального парсера

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
wanted=Path(sys.argv[1])/'src/xgw'
actual=Path('/opt/xgw/lib/xgw')
left={p.relative_to(wanted).as_posix():hashlib.sha256(p.read_bytes()).digest() for p in wanted.rglob('*.py')}
right={p.relative_to(actual).as_posix():hashlib.sha256(p.read_bytes()).digest() for p in actual.rglob('*.py')}
same=bool(left) and left==right
print('installed_python_tree_equal=',same,'source_module_count=',len(left),'installed_module_count=',len(right))
print('INSTALLED_PARSER_TREE_OK' if same else 'STOP_INSTALLED_PARSER_TREE_MISMATCH')
raise SystemExit(0 if same else 3)
PY
```

Нужны True/INSTALLED_PARSER_TREE_OK/rc0. Mismatch→STOP, не копировать/не чинить установку.
Это только байтовое чтение .py; не импорт/запуск широких тестов/установка. Сохранитьcounts.

## 5. P1: только заморозка тестовых файлов

### P1.1. Подготовить пять файлов один раз

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_reality_contract.py': '3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c', 'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3s')
if root.exists() or root.is_symlink():
    raise SystemExit('STOP_ALREADY_PREPARED')
root.mkdir(mode=0o700,exist_ok=False)
for name,data in payload.items():
    fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data)
    path=root/name
    assert path.stat().st_uid==0 and path.stat().st_mode&0o777==0o600
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected[name]
assert root.stat().st_uid==0 and root.stat().st_mode&0o777==0o700
print('REALITY_CONTRACT_FROZEN',expected)
PY
```

Нужны REALITY_CONTRACT_FROZEN/rc0/5SHA. Уже существует/ошибка/неполнаяподготовка→STOP,
не удалять/дополнять/переименовать, не /optinstall. Старые /runартефакты только читать.

## 6. D1: однократная сверка

### D1.1. Единственный запуск

```bash
sudo -n python3 -I -B /run/xgw-w3s/wave3_reality_contract.py run
```

Порядок: started→beforecontext→Rsource/summary/plan→currentcontract/syntax→локальныекэши/
manual→сравнениеparsedviews→aftercontext/cachehashes. Stage указывает границу при ошибке,
READ_OR_SCHEMA_ERROR+класс без rawmessage. AFTER_READ_ERROR — afterнеполон, не подставлятьbefore.
CACHE_INPUTS_CHANGED или AFTER_CONTEXT_UNCONFIRMED — данные менялись/контекст не подтверждён,
не пересобирать опыт радиPASS. Интерпретировать каждое поле отдельно.

syntax_flags — только форма: publickeyстрогийbase64url/32bytes, shortIDevenhex≤8bytes,
пустойshortID допустим, tls/reality/utlsenabled, SNIpresent. Это не подтверждение, что
сервер ожидает именно эти значения/что ключ правильный. Не генерировать новые ключи!

Source match ищется среди разобранных локальных views по vless/address/port/credential;
значения не выводятся. Несколько одинаковых contract схлопываются, разные — ambiguity.
Сравниваются server/port/uuid/flow/SNI/TLSenabled/REALITYenabled/publickey/shortID/
uTLSenabled/fingerprint/transport только как field_equalbool. Не выбрать лучший совпавший
вариант, если есть разные. Не пытаться исправить отрицательныйbool вручную.

source_boundary=AFTER_PRODUCT_PARSER_NOT_ORIGINAL_WIRE означает, что парсер мог уже
преобразовать исходный формат. Равенство не является независимой проверкой URIparser,
достоверности подписки/сервера и всех полейконфига. Сравнивается заданное подмножество,
не полныйsemanticcontract: DNSstaticIPs/bind/socketoptions/extras не покрыты.

REALITY_CONTRACT_RECORDED/rc0 — статический сбор закончился при сохранномконтексте/cache.
Может включать syntaxfalse/mismatch/NO_UNIQUE_PARSED_CONTRACT/частичнонедоступныекэши;
это результат, неPASSузла/исправление. NO_UNIQUE_PARSED_CONTRACT=нетоднозначногоview,
а не «исходникнеправильный». Уникальность только среди прочитанных и разобранныхфайлов.
STOP_REALITY_CONTRACT/rc3 — частичные данные, stage/code/class. Нетsummary→INTERRUPTED_UNKNOWN,
не retry. EarlySTOPconfigdigestнепрочитан→bridge_config_unchangednull(неизмерено).

### D1.2. Публичная сводка

```bash
sudo -n python3 -I -B /run/xgw-w3s/wave3_reality_contract.py show
```

JSON/rc0 ожидается; show повторять можно, runнельзя. Show0 не означает PASSконтракта.
Нетsummary→STOP/UNKNOWN без catraw. Перенести ВСЕ coverage/flag/results независимо.
cache_inputs_unchangedtrue при0прочитанныхфайлов — пустое сравнение, не доказательствокэша.
Coverageerrors/limits/warnings означают неполноту; один найденный view не исключает
вариант в непрочитанном источнике. Manualчасть защищена settings3before/after.

### D1.3. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются HEALTHY/on/версиипрежние. Иное зафиксировать, без переключений/перезапусков.

### D1.4. Конечный режим пула

```bash
sudo -n xgw pool | head -1
```

Прежний режим, pinне менять. Всеcontextflags читаютсяраздельно, notmarkeronly.

## 7. Отчёт

Скопировать TEMPLATE редактором в `$HOME/xgw-w3s/report.md`. Включить testedHEAD/tree/pin/
installed4/полноеpyдеревоequal+counts/5SHA/modes, commandrc/marker/showrc/stage/codes,
relationcurrent→R, syntaxflags, ВСЕcoveragecounts/limits/manual, сравнениеparsedcontract
и каждыйfield_equal, before/aftercontext/settings3/SBconfig/process/boot/6PID/pin/cache,
UNKNOWN/NOT_RUN/STOP/отклонения/действиявладельца/связь. Никаких rawзначений/ключей.
Наблюдение→гипотеза→недостающийфакт, без причин «ТСПУ/сервермёртв/изоляцияисключена».
Равенствоparsedviews не объясняет REALITYfailure, mismatch может быть современным дрейфом
sourcecache/конфига и не доказывает ошибку генератора без установления lineage.

Rnegative приняткакфакт, oldNpartial1/2/Pblocked0/Qreadonly/M/L/J/SB2positive сохраняются.
Fullwave3/D1-on/E4/faults/LANUDP/IPv6/DNS/allTS открыты; wave4/DAE не начинать.
РабочаяLANработает, S ничего не отключает. РеальнаяS покаNOT_RUN. Privacyпросмотр ДОgitadd:
только разрешённыеbools/counts/enums/sourceSHA/Git, private/rawостаютсялокально.
Recoveryнепотребовалось/неoffrollback/неtimer. Никаких новых соединений, не повтор R.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 7. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3s'
code='351fb54e074f4a7b497a8a4244fc74c6088788d7'
runtime=['src','packaging','config.example.toml','pyproject.toml',
         'tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
def git(*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(value,message):
    if not value:
        raise SystemExit('STOP: '+message)
require(git('branch','--show-current')=='freepool','нужна freepool')
require(not git('status','--porcelain'),'клон/индекс не чист')
draft=(notes/'report.md').read_bytes()
require(len(draft)>200,'нет заполненного черновика')
stamp=datetime.fromisoformat((notes/'run-start.txt').read_text().strip())
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3s-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
require(not git('diff','--name-only',code,'HEAD','--',*runtime),'runtime изменён после ТЗ')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3s — локальная сверка REALITY без запросов')
git('push','origin','HEAD:freepool')
print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

Нужен REPORT_PUBLISHED с фактическим путём и commit. Если commit создался, а push не прошёл,
не запускать весь блок заново и не делать новый commit: сообщить фактический локальный SHA
и сбой отправки, сохранить состояние. Не git add., не force, не reset и не чистка чужих файлов.
Для установления локального состояния после сбоя публикации разрешены только чтения:

#### F3.1. Последний commit после сбоя

```bash
git -C "$HOME/zcod/xgw" log -1 --format='%H %s'
```

#### F3.2. Чистота после сбоя

```bash
git -C "$HOME/zcod/xgw" status --short
```

Финальное сообщение владельцу: что проверено/что осталось NOT_RUN, конечный режим и связь,
ссылка на реальный отчёт либо точная причина, почему публикация не состоялась.
