# ТЗ Flash: wave3u — расширенное покрытие источников и поколений конфигурации

## 1. Рабочая схема и принятое решение по T

Владелец подтвердил03.11: у исполнителя доступен ТОЛЬКО ThinkCentre с XGW; отдельного
управляемого клиента за роутером нет. Поэтому не выдавать запросы с самого ThinkCentre
за LAN-клиентские/сквозные UDP/IPv6/DNS/E4. Рабочая LAN через роутер считается работающей.
Сохранять HEALTHY/on, WAN/LAN/Tailscale/pin/pool/службы/правила. Неoff/install/G1/новаяSSHопись.
Always_off guardian запрещён; incomingoutage>1мин модель следующейкомандойне исправит.

Отчёт T8d208e9d25be2c0fee9dff2a6fa348db038150ae: семь этапов собраны за364.31с,
EXTENDED_BATCH_RECORDED/rc0/finalsummary, context/config/cache/onсохранены, requests0.
T3: 6из67VLESSсверены и равны;61NOT_RUN, неmismatch. T4:141мост(d71/f67/m3), badcounts0,
135REALITYформ корректны,3Xrayreferences без ошибок. T5:90старыхscans,38короткихOKbody;
core неизвестен. T7:12пассивныхточек, carrier1/contexttrue, LANсчётчики двигались.
Это принимается в указанном scope. Старое шестиминутное наблюдение/M/L/J/SB2 не повторять.

Найдена недоработка ТЕСТОВОГО T2: JSON-массив полных конфигов не раскрывался до вложенных
outbounds. T2мог возвращать0supported без ошибки на полноценный исходник. НовыйU расширяет
независимый containerwalk; productparser/convert не вызываются. Исторический T не менять
и не переписывать6/67 в полныйPASS. U сравнивает исправленный/старый тестовый разбор на
ОДНИХ современных bytes, чтобы показать эффект изменения без новой загрузки подписок.
Это не установленный дефект runtime XGW, продуктовыйпатч не нужен по одному coveragegap.

## 2. Один пакет, восемь автоматических этапов, один отчёт

| Этап | Объём |
|---|---|
| U1_T_evidence | Старый TsourceSHA/итог/baselineprivate, currentSB/Xraydigests относительно T, referencekey; аудит cumulativeLANцифр таблицы T безповторанаблюдения |
| U2_expanded_independent_sources | Все доступные configuredcache/manual: plain/base64, массивы полных конфигов, вложенныеoutbounds/endpoints; coverage/фиксированныеunsupportedпричины; старыйTна техжеbytes |
| U3_all_default_contracts | Все текущие defaultVLESSoutbounds и отдельныйreferencecase:12fieldbool/equal/mismatch/nounique |
| U4_current_all_profile_graph | Текущий граф всехнайденныхSBd/f/m и Xrayreferences, auth/marks/routes/формы; freshbaseline если конфиг сменился |
| U5_local_config_generations | ТекущийSB против доступных last-good/pending: semantic/byteразличия по категориям, совпадение с Tdigest, без вывода параметров |
| U6_keyed_persisted_health | Read-onlyсвязь текущихузлов→nodes→probe_tag→savedscan: aggregate+reference, core всёещёнеизвестен/неactivehealth |
| U7_effective_unit_properties | Только systemctlshow свойствSB/Xray: users/caps/NNP/ProtectSystem/Home/Tmp/ReadOnlyPaths/run/AF/restrictions, выводbools |
| U8_writer_journal_counts | Один общийboundedjournal двухслужб за24ч/последние3001строка/3с: фиксированныефразы apply/reload/deferred/rollback, не raw/неPIDwriterproof |

Все этапы запускаются одним worker. Ошибка/отсутствие входа в необязательном этапе →
UNAVAILABLE и переход к следующему разрешённому чтению. Mismatch/boolfalse/неподдержанный
record не повод спрашивать разработчика или чинить продукт. Общие STOP baseline/identity/
privacy остаются. По итогу один Markdown с полной матрицей, недостающим evidence и backlog.
Отдельный T7-пассивный интервал не повторяется: он уже принят. Основной объём — независимая
сверка множества записей/связей/поколений и разбор единого отчёта, без активных проб.

## 3. Идентичность и допустимые эффекты

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7. Runtime/packaging/config не устанавливать
и не менять. Записать actualHEAD/tree. Семь замораживаемых файлов:
- wave3_coverage_batch.py: SHA256 `f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48`;
- wave3_extended_batch.py: SHA256 `9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb`;
- wave3_reality_contract.py: SHA256 `3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c`;
- wave3_single_bridge.py: SHA256 `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Единственный CLI — новыйwave3_coverage_batch.py start/status/show; _worker вручнуюнельзя.
Шесть старых — библиотеки. Их CLI/request/journal/worker не запускать. ИзT используются
чистые independent_record/compare_record/whole_graph/write; productparser невызывается.
Старый /run/xgw-w3t только читается; Tsource9e467188...проверяется, не переисполняется.
Новые files только /run/xgw-w3u(root700/600) и ~/xgw-w3u. Python-I-B, без pycзаписей.

Разрешены Gitfetch/FF/публикацияодногоMarkdown, readonlyconfig/proc/sys/nft/systemctl/
SQLiteSELECTmode=ro, локальныекэши/manual/last-good/pending, boundedjournal.
Backgroundworker — обычный собственный Pythonпроцесс, неsystemd/guardian/служба.
Новые baseline/progress/partial/summary файлы защищены; privatebaselineнеcat/неGit.
Сравнениепоколений — только чтение, ни один pending/last-good не применяется.

ЗАПРЕЩЕНЫ curl/GET/--version/SOCKS/DNS/ping/SSH/scan/rescan/speedtests/packet-capture/
promiscuous/новыеlisteners/netns/APIwrites, pin/unpin/rotation/сменыпрофиля/узла/pool/
Tailscale/capture/VPN/WAN/LAN/config/NM/sysctl/rules, install/apply/netupdown/enable/
disable/restart/reload/killслужб/loglevel/старыеguardians/fault/permissionпробы/offrollback.
U инициирует0новыхсоединений. systemctlshow/journalctl не означают reload/start/stop.

Нет исходногоon/rootконтекста/configidentity→общийSTOP, толькоafter/partialеслидоступны.
Off→WAIT_OWNER_ON, модельего не включает. НетстарогоT/поколения/скана/свойства→локальный
UNAVAILABLE/availablefalse/NOT_RUN, остальныеэтапыпродолжаются. Не создавать историю заново,
не копировать текущийконфиг вместо старого и не применять конфиг ради совпадения digest.
Первый start/каталог только один. Exclusive started/workerclaimed не обходить новымименем.
Никаких restart/kill даже при зависшем мониторинге; worker только читает. При обрывесвязи
после еёвозврата status/show/отчёт, не start/_worker/переключения. Recoverytimer не нужен.

Приватность: только bool/count/fixedenum/sourceSHA/Git в Git/чат. Нельзя rawJSON/cache/
config/logs/URI/URL/IP/MAC/UUID/keys/passwords/SNI/порты/имена/fp/теги/PID/NIC/DBrows/
исключения/privateplan/config+targethashes/screenshots. Строки ошибок не публикуются,
только фиксированныекоды/классы. Не вручную cat для выяснения причины.
Одна команда/целый блок на шаг, ждатьrc/marker, unknownrc так и записатьUNKNOWN.

## 4. S1: терминал, заметки и канал sudo

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
root=Path.home()/'xgw-w3u'
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

#### S1.2a. Проверить NoNewPrivs именно канала исполнителя

```bash
python3 -I -B - <<'PY'
from pathlib import Path
rows=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
value=rows.get('NoNewPrivs','UNKNOWN').strip()
print('EXECUTOR_NoNewPrivs=',value)
print('EXECUTOR_NNP_OK' if value=='0' else 'BLOCKED_EXECUTOR_NNP')
raise SystemExit(0 if value=='0' else 3)
PY
```

Нужны EXECUTOR_NNP_OK/rc0. При1/UNKNOWN — общий STOP ДОsudo/worker. Это свойство
дерева процессов исполнителя, не дефект шлюза и не NNP ядра sing-box(там1 ожидается).
Пароль/sudo-v не исправляют наследуемыйNNP1. Не менять sudoers/prctl/политику приложения,
не пробовать альтернативные способы повышения. Требуется действие владельца: предоставить
обычный терминальный канал с рабочимsudo; при перезапуске ZCode самим владельцем
возобновить с S1.1b→S1.2a→S1.2b, НЕ повторять создание notes/run-start/каталога.
[Свойства флага в документации ядра](https://docs.kernel.org/userspace-api/no_new_privs.html).

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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3u/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 5. S2: рабочий on и sourceidentity

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

### P1.1. Подготовить семь файлов

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_coverage_batch.py': 'f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48', 'wave3_extended_batch.py': '9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb', 'wave3_reality_contract.py': '3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c', 'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3u')
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
print('COVERAGE_BATCH_FROZEN',expected)
PY
```

Нужны COVERAGE_BATCH_FROZEN/rc0/7SHA. Ошибка/каталогсуществует→общийSTOP, не чистка/
пересоздание/новоеимя. Старые/run и /opt не меняются.

## 7. O1: один start, автоматический dispatcher, общий show

### O1.1. Запустить один раз

```bash
sudo -n python3 -I -B /run/xgw-w3u/wave3_coverage_batch.py start
```

Нужен COVERAGE_BATCH_STARTED/rc0: запущен worker, НЕ завершён пакет. Он detached от
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
        p=subprocess.run(['sudo','-n','python3','-I','-B','/run/xgw-w3u/wave3_coverage_batch.py','status'],capture_output=True,text=True,timeout=10,check=False)
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

Ожидаются progress и BATCH_FINISHED после завершения восьми этапов. COVERAGE_BATCH_PARTIAL тоже завершённый
сбор: продолжить O1.3 и отчёт, не новоеТЗ/не повторstart. Мониторне запускаетworker,
не восстанавливает сеть и не читает rawstderr. MONITOR.../истёкbudget→workerможетпродолжаться;
перейти O1.3, сохранитьpartial/UNKNOWN, не kill/restart/сменарежимов. Sudoотказ не обходить
паролемвкоманде/sudoers. При потересвязи после еёвозврата разрешён только O1.3/O1.4/O1.5.

### O1.3. Прочитать итог или последнее partial

```bash
sudo -n python3 -I -B /run/xgw-w3u/wave3_coverage_batch.py show
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

## 8. Как трактовать результаты восьми этапов

COVERAGE_BATCH_RECORDED — восемь сборов/сохранныйcontext/config/cache/доступные поколения,
не семантическийPASS. Внутри могутбытьavailablefalse/queryfalse/mismatch/unsupported.
COVERAGE_BATCH_PARTIAL — сохранить всёуспевшее однимотчётом, не новыйstart/не микрозадание.
CollectionRECORDED — естьответэтапа, не успешнаяпроверкаего содержимого. UNAVAILABLE —
локальнаяошибка, остальныечтения workerвыполняет автоматически. GlobalbaselineSTOP и
aftererror сохранятьотдельно; partial/progress не выдавать за финальныйafter.

U2: ограниченная рекурсия до6уровней/20000visited/5000leaves наbody, плюс32источника/
2MiBeach/8MiBacceptedtotal/manual2MiB. Всеlimits/counters читать. JSONduplicatekeys →
источникнеоднозначен/UNAVAILABLE, не выбратьlastvalue. Неизвестныеконтейнеры/неVLESS/
служебныезаписи/unsupportedtransport раздельны. TCP/rawподмножество не расширено до всех
форматов; codeвыводит фиксированныеreasoncounts, не сыройтекстexception.
Legacy_T_supported_on_same_bytes — запуск ТОЛЬКО чистой функцииразбора старогоT, не Tworker.
Сравнение наоднихbytes доказывает эффект containerwalkfix; не переписывает историческийT.
Исходникиcurrent, связьихсстарымT/Rнеустановлена, еслиcurrentcache/digestне совпали.
Absentfp=явная конвенцияchrome, не доказанноеявноеполеисточника. NativeSBиспользуетобщую
выборкуполейsource.contract, это не независимая проверка всейсемантикиэтихполей.

U3: equality12полей несервер/health/DNS/bind/extras/socketoptions/всеcasevariants.
U1 дополнительно читает сохранённые T7samples: last_cumulative_value — последняя дельта
от началаT. Sum_of_cumulative_values_NOT_total_traffic — только контроль ошибочного
суммирования, НЕ реальный трафик. Сравнения reported_table_matches_last/sum показывают,
какому способу соответствуют RX35774669/TX924284684 из таблицыT. Еслиобаfalse/None,
цифраотчёта не подтверждена имеющимисяsamples, не придумывать основание/неповторятьT7.
Даже подтверждённыйlastcounter не VPNскорость/клиентскаяатрибуция.
No_unique≠mismatch, ambiguityнеbestmatch. Oldreferenceпо8hex не полнаяисторическаяидентичность.
U4: граф файлов, не живоеXrayAPI/работавсехпрофилей/packetproof. Неисправныесвязи не чинить.
UnknownlocalSOCKSreference можетбытьлегитимнымдругимproxy. Формаключа несерверноеожидание.

U5: difference_current_vs_file направление: added_in_current = естьсейчас, не в peerfile.
json_values_equaltrue при bytesdifferent означает различие сериализации, не полевая смена.
Другиеcounts указывают классыизменений(serverobjects/ports/auth/dns/route/experimental/log),
не выводятзначения и не устанавливают автора/точноевремя. Last-good/pending могутотсутствовать,
бытьсвежееT/другойгенерации. Matches_T_digesttrue — совпалсохранённыйполныйTdigest;
прочиефайлы не объявлять поколениямиT/R по одному имени. Не применять/неоткатыватьих.
По коду XGW семантическиравный config не записывается: blanketгипотеза «каждая регенерация
обязанаменятьdigest» неверна. Writeridentity изметаданных НЕ устанавливается.

U6: в nodesестьfingerprint/tag, scansсвязаны черезprobe_tag; отсутствует КОНКРЕТНЫЙCORE,
а не всяидентичностьузла. JoinreadonlyоднимSELECT, максимум5000rows. Проверяется форма
tag/prefix, неоднозначность не выбираетсяслучайно. Referencepersistedscan — современная
сохранённаястрока, не новыйhealth/необязательнототжеcore/profile/source. Age неping,
secondsнеRTT/скорость, OKкороткоетело неBODY32769. Freshactive_checkfalse всегда.

U7: свойстваeffectiveunit читаютсябезreload. Missingproperty/false/queryfalse неPASS;
сверять properties_seen и каждоеbool. Ожидается SBбезcapabilities, Xrayсnetadmin/bind,
NNPобоихядерtrue. NNP0 ожидается в обычномканалеZCode доsudo, а не в SBservice — ролине смешивать.
ReadWritePathsempty только данныйпараметр, не доказательство отсутствиявсех writablemounts.
U8: last24h ограниченоtail3001rows/3с, анализ3000; truncated≠полныйдень. Фразы могутбыть
цитатой/неуспешнымсобытием. Countsне PIDwriterproof/не cause/не точнаяисторияR/T.
Пустой/queryfalse/parseerrors не«никогда не перечитывалось». Неувеличиватьлогирование.

Всеbefore/afterflags settings3/SBconfig/Xrayconfig/process/boot/6PID/pin/cache/generationfiles
отдельны. Непрочитанныйbaselineнеподменятьchanged, пустой watchedcompare нереальноеevidence.
Другой Tdigest — нормальнаявозможностьновойбазы, не дефект/действия владельца поумолчанию.
Никаких повторных6мин LAN/новыхзапросов/восстановительныхрежимов по текущимрезультатам.

## 9. Один итоговый отчёт с приоритетным backlog

Скопировать TEMPLATE редактором в `$HOME/xgw-w3u/report.md`. Пройти все8строк и заполнить
collection/data/semanticdecision/limits. Отдельноstart/monitor/showrc, какойfile(finalsummary/
partial/progress), время, globals/afterstop, sourceidentity/NNPканала/ownerдействия/режим/связь.
Включить: изменениепокрытияlegacyT→Uнасамыхbytes; totalVLESS/equal/mismatch/nounique;
reference12bool; staticgraph; какиеgenerationfilesдоступны икатегорииdiff; mappingnodes/scans
безcoreатрибуции; unitpropertybool; writerjournalcoverage. Contextкаждыйflag, privacy.

В этом же отчёте, безследующегозадания:
1. Принять только подтверждённыеscope, сохранитьнепроверенные и отрицательныефакты N–T.
2. Отделить исправленныйдефект тестовогоcoverage от возможного runtimebug (не назначать).
3. Составить приоритетные atomicfixspecs по КОНКРЕТНОМУ mismatch с trigger/evidence/
   предполагаемымместом/минимальнойпроверкой; еслиruntimebugнеобоснован, такнаписать.
4. Для LAN-клиентских/UDP/IPv6/DNS/E4 отметить подтверждённоедоступенТОЛЬКОThinkCentre;
   неназыватьпроверкиссамогошлюзаLANклиентскими. Не предлагать внешнееустройствокакфакт.
5. ДолгD1-on/faults/performance/allTS сохранить: нетнезависимоговосстановленияon/нужного
   активногоплана вэтойзадаче. Не создавать netns/сервис/отказысамостоятельно.
6. Просмотретьprivacyчерновик и опубликоватьОДИНMarkdown. Не останавливатьсядляразработчика
   после U1/U2/... . УведомитьвконцеилиприобщемSTOP/необходимомдействиивладельца.

Реальнаяwave3u покаNOT_RUN. Полнуюwave3 не закрывать, wave4/DAE не начинать.
Шлюз остаётся HEALTHY/on; продукт/сетьне менять. Одинбольшойпакет, не сериямикрозаданий.

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
notes=Path.home()/'xgw-w3u'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3u-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3u — расширенное покрытие источников и поколений конфигурации')
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
