# ТЗ Flash: wave3t — расширенный автоматический пакет, один итоговый отчёт

## 1. Новое требование владельца и результат S

Владелец требует максимально укрупнить безопасную работу, чтобы не выдавать новое ТЗ
после каждого маленького результата. Выполнить весь этот пакет в одном сеансе по таблице
переходов ниже. Не останавливаться для вопроса разработчику после отдельного mismatch,
UNAVAILABLE или отсутствующего источника. Дойти до остальных разрешённых этапов и
опубликовать ОДИН консолидированный отчёт. Исключения — общие STOP безопасности/идентичности.
Новых разрешений на сетевые изменения, отключение VPN или WAN эта укрупнённость не даёт.

Рабочая схема XGW→Wi-Fi-роутер→устройства — baseline HEALTHY/on. Не выключать её ради
подготовки. WAN/LAN/Tailscale/pin/pool/службы/правила сохраняются. Входящий адаптер не менять.
Не install/G1, не новая SSH-инвентаризация. Старый always_off guardian запрещён.

Получен отчёт S a7482377b5cb0d85a015d8a7fcc747743b8e7e94: REALITY_CONTRACT_RECORDED/rc0,
полное установленное Python-дерево110/110 равно исходникам; Rconfigdigest совпал;
формаREALITY6/6; трикэша прочитаны безошибок, один parsedview, все12полей равны;
контекст/кэш/on сохранены. Принято только parsedsource→appliedconfig, не parser/serverPASS.
Текст отчёта ошибочно относит исходную запись до парсера к недоступным данным: cachedbody
доступно локально. T читает его в памяти и разбирает отдельной реализацией, без вызова
parse_body/parse_links_text/convert XGW. Это не доступ к актуальному серверу подписки.

R остаётся отрицательным (curl97/0body/relatedREALITYliteral); Npartial1/2/Pblocked0/
Qreadonly/M6/6/L608с/Jshort-host+loaded/SB2positive не переписывать и не повторять.
ТСПУ/падение сервера/дефект изоляции не назначены. Цель T шире одного старого узла:
все доступные defaultVLESS контракты, все найденные SBмосты d/f/m и их ссылки из Xray,
сохранённая история health, свежие общие ошибки и пассивное наблюдениеLAN.

## 2. Состав единого пакета и автономные переходы

| Этап | Объём | При неполных данных |
|---|---|---|
| T1_history | Проверить сохранённый S и referencekeyR; обозначить связь currentconfig→R | UNAVAILABLE; остальные этапы продолжаются, referencecaseнеприписыватьR |
| T2_independent_sources | Все configuredcache до32, plain/base64links/nativeSBJSON/XrayJSON TCP VLESS +manual | Сохранить ошибки/unsupported/ambiguity; остальные источники и этапы продолжить |
| T3_all_default_vless_contracts | Каждый текущий defaultVLESSoutbound: сравнить12полей со всеми однозначными supportedrecords; отдельный referencecase | Нетоднозначногозаписа→NOT_RUNдляэтойсверки, не выбратьлучшийвариант; остальные узлы продолжить |
| T4_all_profile_graph | Все SB inbounds d/f/m, route/outbound/listener/auth/duplicateports, ссылкиXraySOCKS/auth/mark, форма всехREALITY | Сохранить counts mismatch; не чинить и не прекращать остальные чтения |
| T5_persisted_health | До5000 сохранённых scans: verdict/возраст/короткиеOKbody/coverage; SQLitemode=ro | queryfalse→NOT_RUNhealth, без scan/DBrepair, этапT6продолжить |
| T6_recent_journal_counts | xgw и xgw-singbox: по одному query за10мин до этогоэтапа, максимум2001строка/3с каждый | Ошибки/пустота/обрезка как coverage, без raw/увеличенияloglevel; T7продолжить |
| T7_passive_LAN | 12автоматических отсчётов через30с, всего≈6мин: LANrx/txdelta/carrier и on/process/settings | Изменилсяконтекст→закончить только наблюдение, собратьafter/отчёт; никаких сетевыхвозвратов |

Контроль до/после: SBconfig/Xrayconfig/cacheinputs/settings3/process/boot/6PID/pin/on.
Коллектор сам последовательно выполняет T1–T7, сохраняет progress и partial после этапов.
Модель не запускает отдельные тесты вручную и не запрашивает новое ТЗ между этапами.
Пока worker работает, можно читать это ТЗ и готовить пустую структуру Markdown-отчёта;
не трогать сеть/продукт и не запускать параллельный сборщик.

Ожидаемо: около6–10мин сбора плюс подготовка одного подробного отчёта. Локальный worker
продолжает работу при обрыве сеанса модели; он не зависит от следующей команды модели.
Проверка бюджета600с между пассивными отсчётами — мягкий предел worker, не обещание
жёсткого deadline для любых действий ОС. Dispatcher прекращает ожидание через15мин.
Не превращать таймаут ожидания в команду kill/restart или повтор опыта.

## 3. Идентичность, эффекты и общие STOP

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7, runtime не устанавливается/не меняется.
Записать actualtestedHEAD/tree. Шесть frozen файлов в root700/run/xgw-w3t, каждый root600:
- wave3_extended_batch.py: SHA256 `9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb`;
- wave3_reality_contract.py: SHA256 `3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c`;
- wave3_single_bridge.py: SHA256 `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

CLI только wave3_extended_batch.py start/status/show. Внутренний _worker вручную НЕ вызывать.
Пять старых файлов — библиотеки; их main/run/request/journal не запускать. Новая реализация
T читает журнал сама; source.read_source/contract/syntax_flags — чтение/выборкаполей,
не parser. Наличие импортированного модуля productparser в старой библиотеке не означает
его вызова: T2 не вызывает функции парсера/конвертера XGW.

Разрешены: чистый Gitfetch/FF/публикацияодногоMarkdown; config/proc/sys/nft/systemctlчтения,
SQLite SELECT mode=ro, чтение oldSsource/summary и Rplan, локальныхcachedbody/manuallinks;
ограниченные journalqueries; пассивные чтения LANсчётчиков. Ни packetcapture, ни promiscuous,
ни открытие NIC на передачу не используются. WAN читается только существующим contextreader,
никаких WANпрофилей/адресов/маршрутов/состояний не менять. Backgroundworker — обычный
дочерний Pythonпроцесс, не новая systemdслужба/таймер/guardian.
Новые файлы только /run/xgw-w3t и ~/xgw-w3t; baseline-private.json с digest/key/identity
остаётся root600, не cat/не Git. Запуск Python с -I -B, без записей __pycache__ в продукт.

Запрещены curl/--version/GET/SOCKS/DNS/ping/SSH/healthscan/rescan/speedtests, любыеAPIwrites,
сменыузлов/профилей/pin/unpin/rotation/pool/Tailscale/capture/VPN, install/apply/netupdown/
enable/disable/restart/reload/kill, nft/ip/NM/sysctlмутации/loglevel/новыеlisteners/netns,
старые permission/fault/guardian/offrollback. Не повторять старые принятые опыты.
Ни одного нового соединения или активной проверки сервера этот пакет не инициирует.
Обычная работа шлюза продолжается. No faults/D1-oninstall/E4packetattribution/activeUDP/
IPv6/DNS/allTailscale/performance: для них здесь нет безопасно подготовленного исполнителя
и независимого восстановленияon; они остаются NOT_RUN, не превращать объём в фиктивныйPASS.

Общие STOP до worker: грязныйGit/другойruntime/неравенствоустановки/SHA/modes/нетsudo/
нет исходногоon/ужеиспользованкаталог. Off→WAIT_OWNER_ON, модельне включает.
Общий STOP внутри worker: исходный on/context/config не прочитан; снимаются доступныеafter,
сохраняетсяpartial. Отдельный этапUNAVAILABLE/mismatch не является общимSTOP.
Приватность нарушена→не публиковать черновик, исправить только Markdown, не продукт.

Никакого offrollback: incomingoutage>1мин модель не восстановит следующейкомандой.
Worker не меняет сеть; не запускать recoverytimer. При обрывесвязи дождатьсявозврата,
потом только status/show/отчёт; start/_worker/подготовку не повторять. Started/workerclaimed
блокируют второй запуск, в том числе после краша. Не чистить/переименовать/пересоздаватькаталог.

Одна команда/целый блок на шаг. Дождатьсяrc/marker; неизвестныйrc записатьUNKNOWN.
В Git/чат только publicsummary/обезличенныйMarkdown: no rawlogs/cache/config/URI/URL/IP/
MAC/UUID/keys/passwords/SNI/порты/имена/fp/теги/PID/NIC/privateplan/privatehashes/screenshots.
ИсходникиSHA/GitHEAD/bools/counts/фиксированныеenums разрешены.

## 4. S1: терминал и заметки

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
root=Path.home()/'xgw-w3t'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3t/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 5. S2: рабочий on и установленный код

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

## 6. P1: однократная заморозка

### P1.1. Подготовить шесть файлов

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_extended_batch.py': '9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb', 'wave3_reality_contract.py': '3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c', 'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3t')
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
print('EXTENDED_BATCH_FROZEN',expected)
PY
```

Нужны EXTENDED_BATCH_FROZEN/rc0/6SHA. Любая ошибка/существующийкаталог→общийSTOP,
не повторятьподготовку/не удалять. В /opt/systemd ничего не копируется.

## 7. O1: один start, автоматическое ожидание, один show

### O1.1. Запустить один раз

```bash
sudo -n python3 -I -B /run/xgw-w3t/wave3_extended_batch.py start
```

Нужен EXTENDED_BATCH_STARTED/rc0: запущен worker, НЕ завершён пакет. Он detached от
терминала; stdin/stdout/stderr worker идут в /dev/null, только безопасные JSON в/run.
Launcherror/rc3→стартнеподтверждён, status/show разрешены, startнеповторять.
Сразу перейти к O1.2. Не ждать указания разработчика после вывода стартмаркера.

### O1.2. Автоматический dispatcher наблюдения — один блок

```bash
python3 -I -B - <<'PY'
import json,subprocess,time
began=time.monotonic()
while time.monotonic()-began < 900:
    try:
        p=subprocess.run(['sudo','-n','python3','-I','-B','/run/xgw-w3t/wave3_extended_batch.py','status'],capture_output=True,text=True,timeout=10,check=False)
    except subprocess.TimeoutExpired:
        print('MONITOR_READ_TIMEOUT_NO_RESTART')
        break
    if p.returncode != 0:
        print('MONITOR_READ_UNAVAILABLE',p.returncode)
        break
    try:
        wrapper=json.loads(p.stdout)
        name,data=wrapper['file'],wrapper['data']
    except (ValueError,KeyError,TypeError):
        print('MONITOR_FORMAT_UNKNOWN_NO_RESTART')
        break
    if name=='summary.json':
        print('BATCH_FINISHED',data.get('marker','UNKNOWN'))
        break
    print('BATCH_PROGRESS',data.get('stage','UNKNOWN'),'samples',data.get('completed_samples','N/A'),flush=True)
    time.sleep(30)
else:
    print('MONITOR_BUDGET_REACHED_NO_RESTART')
PY
```

Ожидаются progress и BATCH_FINISHED через≈6–10мин. EXTENDED_BATCH_PARTIAL тоже завершённый
сбор: продолжить O1.3 и отчёт, не новоеТЗ/не повторstart. Мониторне запускаетworker,
не восстанавливает сеть и не читает rawstderr. MONITOR.../истёкbudget→workerможетпродолжаться;
перейти O1.3, сохранитьpartial/UNKNOWN, не kill/restart/сменарежимов. Sudoотказ не обходить
паролемвкоманде/sudoers. При потересвязи после еёвозврата разрешён только O1.3/O1.4/O1.5.

### O1.3. Прочитать итог или последнее partial

```bash
sudo -n python3 -I -B /run/xgw-w3t/wave3_extended_batch.py show
```

Show0 означаетпрочитанJSON, неPASS. В wrapper.file обязательно указано, что прочитано:
summary.json — завершённыйитог; partial.json — последнийcheckpoint(не финальныйafter);
progress.json — толькоход. Если summaryнет, не объявлять after/context/выполненныеэтапы
по старым данным. Не переносить beforeвafter. При progress-only/нетдоступа→INTERRUPTED_UNKNOWN/
BLOCKED_READOUT, всё ещё не новоеstart. Сохранитькакойфайлпрочитан и фактическиеrc.
Допустимо повторять status/show для чтения, запрещеноstart/_worker.

### O1.4. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

ОжидаютсяHEALTHY/on/прежниеверсии. Иное записать без переключений. При потересвязи ждатьвозврата.

### O1.5. Конечный режим пула

```bash
sudo -n xgw pool | head -1
```

Прежнийрежим, pin/Tailscale/captureне менять. Не требовать off.

## 8. Как трактовать весь пакет, не останавливаясь на каждом результате

EXTENDED_BATCH_RECORDED означает: семь этапов собраны, плановое наблюдение закончено,
before/afterконтекст/config/cacheсохранны. Не означает, что полявсехпроверокправильны:
внутри могутбытьmismatch, unsupported, queryfalse, нулевойтрафик. Отдельно читать data.
EXTENDED_BATCH_PARTIAL — не всё собрано/контекстсмешан/наблюдениепрервано; сохранитьвесь
успевшийматериал однимотчётом. collectionRECORDED — полученответэтапа, не семантическийPASS.
collectionUNAVAILABLE — ошибкаэтапа, остальные безопасныечтения уже выполнены автоматически.

T2 поддерживает явно ограниченное подмножество: VLESS plain/base64 links, nativeSB JSON,
XrayJSON, толькоTCP/raw безмаскировки/chain. WebSocket/gRPC/прочиеформаты/двойныеquerykeys/
multiusers не додумываются: unsupported/ambiguity/NOT_RUN. Не загрузитьдругойисточниквзамен.
Если fpнет, используется явнообозначеннаяконвенцияchrome; это не «fp явно было в источнике».
JSONкорень — list/singleoutbound/outbounds; другие структуры не объявлять корректно проверенными.
Источникидо32/2MiBeach/8MiBacceptedtotal+manual2MiB, до5000records наисточник. Это может
бытьнеполноепокрытие, не оригинальныйответсерверасейчас/неpacketwire/неfreshhealth.

T3 выводит только counts и12equalbool дляreferencecase. Нетоднозначногозаписа не mismatch;
несколькоконтрактов не выбираются по лучшемусовпадению. Равенствоподмножестваполей не
семантикаDNS/staticIPs/bind/extras/socketoptions/всехпротоколов. Mismatchнеавтоматический
runtimebug: contemporarycache/configlineageне установлена. ЕслиRdigestне совпал — толькоCURRENT.

T4 — граф ФАЙЛОВ, не чтение живого XrayAPIсостояния и не packetproof. Нулевыеbadcounts
полезны, но не доказываютработувсехпрофилей. unmatchedlocalSOCKSreference можетбыть другим
легитимнымлокальнымпрокси; не удалять. Сопоставленныепароли сравниваются толькоbool/count,
значения невыводятся. ФормаключаREALITY/shortID не правильностьсерверныхожиданий.

T5: scansнехранятидентичностьcoreвсхеме, core_identityUNSPECIFIED. OK305bytes неBODY32769,
fresh≤300с — только возрастзаписи, не новыйуспех. Ниsecondsскана, ниLANdelta неping/скоростьVPN.
Truncated/queryfalse/futuretime/invalidtime — неполнота, не доказательствоhealth.
T6: recentобщиеkeywordcounts, пересекаются/могутбытьINFO; не приписыватьстаромуR/SB1.
Пустой/queryfalse/truncated/parseerrors не«ошибокнет». Не раскрывать rawjournal.
T7: LANbyteсчётчикивключаютслужебныйтрафик. Positiveне VPNegress/конкретныйклиент/E4,
нулевыеdeltaне поломкарабочейLAN. None — неизвестно/reset, не0. Наблюдение не повтор
старогоL608с: здесь другойвопрос — пассивныесчётчикиврасширенномпакете, безновыхпроб.

## 9. Один консолидированный отчёт и подготовка следующей работы

Скопировать TEMPLATE редактором в `$HOME/xgw-w3t/report.md`. Одна таблицаT1–T7: фактический
collection, важныеcounts/flags, semanticdecision(SCOPED_MATCH/MISMATCH/NOT_RUN/UNKNOWN),
ограничения. Не писатьавтоматическийPASS по rc0/marker. Отдельноcommandstart/monitor/show,
какойJSONпрочитан/finalилиpartial, elapsed/samples, stage/globalstop/afterstop.
Контекствсеflagsраздельно; privacy/действиявладельца/отклонения/конечнаясвязь/режим.

В этом же отчёте закончить безновогоТЗ:
1. Свести принятые S/M/L/J/SB2 факты и сохранённые Npartial/Pblocked/Qreadonly/Rnegative.
2. Выписать каждый обнаруженный staticmismatch/coveragegap, безrawданных/безремонта.
3. Сформировать упорядоченный backlog: defectevidence → чтоизмерено → чего не хватает →
   минимальныйбудущийпатч/безопаснаяпроверка. Еслинетдефекта, так и написать, не выдумывать.
4. Отдельнаястрока для каждого NOT_RUN: faults/D1-on/E4/UDP/IPv6/DNS/allTS/performance.
   Указатьпричину: нетсогласованногоклиентскогоопыта/независимоговозвратаon, не «LANсломана».
5. Финальноеacceptanceрешение толькопоscope. Wave3 целиком не закрывать, wave4/DAE не начинать.
6. Просмотретьprivacyчерновик и опубликовать ОДИН Markdown. Не отправлять промежуточные
   отчёты/просьбыразработчику после T1/T2/... . Уведомить владельца после финальнойпубликации
   либо при общемSTOP/необходимомего действии. Остальныечастичныеисходы включитьвобщийотчёт.

Реальнаяwave3t покаNOT_RUN. Runtimepatchне обоснован однимSсовпадением; gatewayне менять.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 9. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3t'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3t-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3t — расширенный автоматический пакет из семи этапов')
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
