# ТЗ Flash: wave3ah — сверить сохранённые AG/AF/AE данные без повторных тестов

## 1. Причина и решение HOLD

AGreport62ae684af177b60e8e52683251caacab771c5760 заявляет129/129, но его таблица
содержит54 строки с source-incompatible expected_return и88 приближённых времён.
Примеры: S_UNAVAILABLE ожидаетFALSE, S_PRUNE/LIST, SAVE_CANDIDATES/NONE; refresh/LIST,
refresh_backend/EMPTY_TEXT, proxy/OUTCOME, check_some/ONEилиZERO. Подставлять source
ожидания вместо actual readout запрещено. Не обвинять источник данных и не делать
вывод о причине: пока неизвестно, ошибочна таблица или сохранённый результат.

AG129 НЕ ПРИНЯТ до сверки, продуктовые изменения и следующая source wave остановлены.
Нужно ОДНИМ readback собрать exact поля уже существующих AG129/AF145/AE112 (386строк,
не386новыхtests). AF/AE независимые архивы, при отсутствии/metadata mismatch показать
UNAVAILABLE/REFUSED и продолжить остальные. Это НЕ повтор accepted batches и не Yroot.
При отсутствии AG summary сохранить partial/unavailable, не перезапускать AG.

Никакого start/_batch/startnewsession/worker/fixture/probe/kill/repair/cleanup. Не
запускать импорт старых helpers или productpackage. Читать только3заранееизвестных
usernotes, их frozen sources/manifests и summary/progress/runmarkers. Не читать casefiles/
configs/logs/registry state/private fingerprints/installedsource. Сеть/службы не трогать.

## 2. Identitу, границы и весь готовый safe объём

Source runtime не меняется:pin351fb54e074f4a7b497a8a4244fc74c6088788d7/diff6A10M/116.
Всеsrc/packaging/config/pyproject и прежние stand artifacts байт-в-байт AG8045d3a.
Устанавливать/активировать ничего нельзя. Текущая source9/50bindingcandidate неglobalfence.

| Новый readback artifact → freeze | SHA256 |
|---|---|
| tests/stand/wave3_evidence_readout.py → readout.py |9c05fe10c35783382c1764728fd98e59c1fec695ea8a05fa3f5e09e4d9428afe|
| tests/stand/wave3_evidence_contract.json → contract.json |4a1af46f22d444e0f1a352f43d5a596ab904e167cd667e1cce80c43a060a9eec|

Contract закрепляет исходные IDs, источник ожиданий, public report fields и SHA
старых artifacts. Collector не исполняет source/helper AST и не выполняет source cases.
Он проверяет owner/mode/nlink/NOFOLLOW/boundedread/stable inode/content hash для
frozen3+116 каждого архива. Только source SHA публичны; private fingerprints не читаются.
Started/claimed должны быть strict boolTrue. AG/AF/AE root — user0700/files0600.
Summary предпочтителен; progress только если summary отсутствует (не если corrupt).
Duplicate JSON/unknown fields/types/symlink/hashdrift отказываются без сырого текста.

Нормализуются ТОЛЬКОknown caseIDs/enums/bools/counts/exact elapsed_ms/publicerrorclass/
publicrepo:line. Unknown private fields не печатать. Missing/nullableactual не заменять
ожиданием или0; source_expected_return показан ОТДЕЛЬНО. Source control/runtime flags
берутся из actual JSON, не hardcodefalse радиPASS. Summary/profile_all_checks/полнота/
report differences отдельно. Flags/IO mismatch — не permission продолжать activation.

Автоматический report-data.md содержит всю таблицу без ручного копирования; receipt
связывает sanitizedreadout и preview от случайного изменения, НЕ authentication against
владельца/root. Mutableownerfiles сами по себе не доказывают происхождение worker.
Collector rc0 = readback attempt записан, НЕ129PASS/неAGaccepted. Workerexitrcпопрежнему
NOT_COLLECTED. CLIforeground readback имеет собственный фактический rc исполнителя.

ТолькоThinkCentre/workingLAN/HEALTHY/on, отдельногоLANclientнет. HostнеLANUDP/IPv6/DNS/E4.
Nooff/install/G1/newSSHinventory/WAN/LAN/TS/pin/pool/config/service/live rules/newunits/
timers/guardian/arm/replay/fault/nft/ip/curl/SOCKS/DNS/ping/pcap/netns/speedtest/APIwrites.
Always_off запрещён, incomingoutage>1мин следующаякоманда неrescue. GitFF/readonly sudo
status/pool — толькоbookends; collectorнеиспользуетsubprocess/socket/xgwimports.
NNP0/sudo prerequisites не ослаблять. При baseline/privacy/source общаяостановка,
сохранитьдоступныеданные, не придумывать восстановление (сеть не меняется).

## 3. S1 — владелец, заметки и канал чтения

### S1.1. Терминал ThinkCentre, обычный владелец

```bash
test "$(uname -s)" = Linux && test "$(id -u)" -ne 0 && test -d "$HOME/zcod/xgw/.git" && printf 'OWNER_SHELL_OK\n'
```

Ожидается OWNER_SHELL_OK/rc0. Иначе STOP: не root-shell, не Windows/VM разработчика,
путь не угадывать, пользователя и $HOME не переназначать.

### S1.2. Эксклюзивные заметки

```bash
python3 -I -B - <<'PY'
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
notes=Path.home()/'xgw-w3ah'
if notes.is_symlink():
    raise SystemExit('STOP_NOTES_SYMLINK')
if notes.exists():
    if not notes.is_dir() or notes.stat().st_uid!=os.getuid() or {p.name for p in notes.iterdir()}-{'plan.md'}:
        raise SystemExit('STOP_NOTES_ALREADY_USED')
    notes.chmod(0o700)
else:
    notes.mkdir(mode=0o700)
stamp=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
fd=os.open(notes/'run-start.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    out.write(stamp+'\n')
print('NOTES_CREATED',stamp)
PY
```

Нужны NOTES_CREATED/rc0. Уже использованный каталог не чистить/не переименовывать ради
нового прогона. Если исполнение прервано после запуска модели, переходить к S3.2/S4,
не запускать её снова. При остановке ДО модели допускается продолжить незавершённую
подготовку после устранения общей блокировки, не пересоздавая notes/run-start.

### S1.3. NoNewPrivs канала до sudo

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

Нужен EXECUTOR_NNP_OK/rc0. При1/UNKNOWN общий STOP доsudo. Это канал исполнителя;
NNP1 у sing-box ожидаем. Не менять sudoers/prctl/изоляцию службы. Владелец предоставляет
обычный рабочий терминальный канал; после его действия продолжить S1.1→S1.3→S1.4,
НЕ повторять создание notes. Модель самостоятельно канал/приложение не перенастраивает.

### S1.4. Проверка sudo

```bash
sudo -n true
```

Нужен rc0. Если требуется пароль/кэш, модель не продолжает sudo-команды. Владелец может
ввести пароль непосредственно в своём терминале при sudo -v; после его сообщения
повторить только sudo -n true в инструментальном канале. Успех другого TTY не равен
успеху здесь. Повторный отказ → BLOCKED_TOOL_SUDO/NOT_RUN. Не секрет в stdin/чат/заметки.

## 4. S2 — исходный on и точный код модели

### S2.1. Чистаяfreepool/FF/6A+10M и publicsourceManifest

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess
from pathlib import Path
repo=Path.home()/'zcod/xgw'
if os.geteuid()==0:
    raise SystemExit('STOP_OWNER_REQUIRED')
def git(*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(value,reason):
    if not value:
        raise SystemExit('STOP: '+reason)
require(git('branch','--show-current')=='freepool','SOURCE_BRANCH')
require(not git('status','--porcelain'),'SOURCE_DIRTY')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor','62ae684af177b60e8e52683251caacab771c5760','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M', 'src/xgw/freepool/pool.py': 'M', 'src/xgw/freepool/store.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_6A_10M')
manifest=repo/'tests/stand/wave3_pool_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==116,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_pool_flow.py').read_bytes()).hexdigest()=='d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')
print('SOURCE_DIFF_SIX_ADD_TEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
require(hashlib.sha256((repo/'tests/stand/wave3_evidence_readout.py').read_bytes()).hexdigest()=='9c05fe10c35783382c1764728fd98e59c1fec695ea8a05fa3f5e09e4d9428afe','AH_READER_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_evidence_contract.json').read_bytes()).hexdigest()=='4a1af46f22d444e0f1a352f43d5a596ab904e167cd667e1cce80c43a060a9eec','AH_CONTRACT_SHA')
notes=Path.home()/'xgw-w3ah'
context=json.dumps({'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}')},sort_keys=True).encode()+b'\n'
target=notes/'source-current.json'
if target.exists() or target.is_symlink():
    import stat
    info=target.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and target.read_bytes()==context,'AH_CONTEXT_CHANGED')
else:
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(context)
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужныrc0/SOURCE_DIFF_SIX_ADD_TEN_MODIFY/SOURCE_MANIFEST_MATCHED116/SOURCE_PREFLIGHT_OK.
ActualHEAD/treeзаписать. Dirty/mismatch/nonFF→STOP, неreset/rebase/force/install.
116sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced.

### S2.2. Исходный режим

```bash
bash -o pipefail -c 'sudo -n xgw status | grep -E "^Состояние|Перехват:|^Xray|^sing-box"'
```

Ожидаются HEALTHY и включённый перехват, rc0. Читать слова: «НЕ ВКЛЮЧЁН», «СНЯТ» и
«ВРЕМЕННО СНЯТ» не являются on. Off → WAIT_OWNER_ON, модель не включает. Иное/unknown
→ STOP_READ, не recovery. Версии записать буквально. Raw status не сохранять/не публиковать.

### S2.3. Исходный режим пула

```bash
python3 -I -B - <<'PY'
import subprocess
try:
    result=subprocess.run(['sudo','-n','xgw','pool'],capture_output=True,text=True,timeout=10,check=False)
except (OSError,subprocess.TimeoutExpired):
    raise SystemExit('POOL_READ_UNAVAILABLE') from None
rows=result.stdout.splitlines()
if result.returncode!=0 or not rows:
    print('POOL_READ_FAILED',result.returncode)
    raise SystemExit(3)
print(rows[0])
print('POOL_READ_OK')
PY
```

Это чтение, не требование pool off. Сохранить первый фиксированный статус, rc0. Если
непонятный результат/ошибка — STOP_READ. Pin/profile/Tailscale не трогать.

### S2.4. Заморозить ТОЛЬКО2 readback файла, старые notes не изменять

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ah';repo=Path.home()/'zcod/xgw'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
info=notes.lstat()
require(os.geteuid()!=0 and stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o700,'OWNER_NOTES')
require(not any((notes/n).exists() or (notes/n).is_symlink() for n in ('collection-started.json','readout.json','report-data.md','receipt.json')),'AH_ALREADY_STARTED_USE_SHOW')
for rel,name,digest in [('tests/stand/wave3_evidence_readout.py','readout.py','9c05fe10c35783382c1764728fd98e59c1fec695ea8a05fa3f5e09e4d9428afe'),('tests/stand/wave3_evidence_contract.json','contract.json','4a1af46f22d444e0f1a352f43d5a596ab904e167cd667e1cce80c43a060a9eec')]:
    source=repo/rel
    require(stat.S_ISREG(source.lstat().st_mode),'SOURCE_TYPE')
    raw=source.read_bytes();require(hashlib.sha256(raw).hexdigest()==digest and b'\r\n' not in raw,'SOURCE_SHA_LF')
    target=notes/name
    if target.exists() or target.is_symlink():
        info=target.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and target.read_bytes()==raw,'PARTIAL_FREEZE_MISMATCH')
    else:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(raw)
print('EVIDENCE_READBACK_READY')
PY
```

НуженREADY/rc0. Старые xgw-w3ag/af/ae не chmod/копировать/чистить/перезаписывать.
Никакого нового source snapshot или runtime install. Already started→S3.2, неcollectagain.

## 5. S3 — ОДИН сбор exact existing data, без workers

### S3.1. Единственныйforeground collect

```bash
python3 -I -B "$HOME/xgw-w3ah/readout.py" collect
```

Нужен EVIDENCE_READBACK_RECORDED/rc0. Это сбор файлов, не запуск тестов. Профили
AG→AF→AE независимы. READ_REFUSED/UNAVAILABLE внутри JSON допускают остальные профили.
Collect rc3/обрыв→S3.2 иreport, НЕповторятьcollect/непересоздаватьnotes/неoldstart.
Если readout/receipt не появились, фиксировать AH_COLLECTION_NOT_FINISHED/NOT_COLLECTED;
не угадывать причину по отсутствию артефакта и не искать PID.

### S3.2. Проверить результат и собственную целостность report-data

```bash
python3 -I -B "$HOME/xgw-w3ah/readout.py" show
```

Нуженrc0 и3профиля label/state/rows/expected/source_contract_consistent/reportdifferences.
Show0 не подтверждает workerexit/AGPASS. Если summary.json выбран и все129sourcechecks
true, это прямое readback evidence; окончательное принятие после review архитектора.
Если contractmismatch/False/missing/corrupt — сохранить exact данные, никаких reruns.
Record/source frozen identity error не исправлять chmod/hashes/JSON editing.

### S3.3. Открыть ТОЛЬКО автоматически обезличенный Markdown

```bash
cat "$HOME/xgw-w3ah/report-data.md"
```

Прочитать ВСЕ3раздела, exact времена без~. Не cat старых summary/casefiles/sourceconfigs/
registry или других notes files; preview содержит только whitelist поля. В AHreadout
должны быть фактические значения, не исправленные поля публичного AGreport.
При show3/preview отсутствует→STOPданных/partialreport изTEMPLATE, не использовать старый
preview каксвежий. Unknowncountsне0, отсутствующий архивне0tests/0failures.

## 6. S4 — конечное состояние и единый неизменённый data report

### S4.1. Конечный статус

```bash
bash -o pipefail -c 'sudo -n xgw status | grep -E "^Состояние|Перехват:|^Xray|^sing-box"'
```

Записать actualHEALTHY/on/версии/метку/rc. Не переносить before вместоafter. ЕслиOTHER/
UNKNOWN: отметить, неoff/enable/restart/repair. Смена HEALTHYtimestamp сама по себе не
доказывает рестарт/ТСПУ/причину. Обязательно отдельноот самих testdata.

### S4.2. Конечный режим пула

```bash
python3 -I -B - <<'PY'
import subprocess
try:r=subprocess.run(['sudo','-n','xgw','pool'],capture_output=True,text=True,timeout=10,check=False)
except (OSError,subprocess.TimeoutExpired):raise SystemExit('POOL_AFTER_UNAVAILABLE') from None
rows=r.stdout.splitlines()
if r.returncode!=0 or not rows:raise SystemExit('POOL_AFTER_READ_FAILED')
print(rows[0]);print('POOL_AFTER_READ_OK')
PY
```

Это readonly. Не требоватьpooloff, не менятьего. Model/terminal link alive — наблюдение
канала, не VPN/LAN end-to-end proof. Incoming loss не исправлять следующими сетевыми командами.

### S4.3. Создать draft с неизменённым автоматически сформированным prefix

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ah';repo=Path.home()/'zcod/xgw'
preview=(notes/'report-data.md').read_bytes();receipt=json.loads((notes/'receipt.json').read_bytes())
if hashlib.sha256(preview).hexdigest()!=receipt.get('report_data_sha256'):raise SystemExit('STOP_REPORT_DATA_CHANGED')
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(preview+footer)
print('AH_DRAFT_CREATED')
PY
```

Нуженrc0/AH_DRAFT_CREATED. Отредактировать ТОЛЬКО footer JSON после AH_EXECUTION:
заменитьnull/UNKNOWN исключительно actual observed данными. Не трогать preview/prefix,
tables/rows/values/issues. Если команда rc неизвестен — null, не0. Точное MSK начало из
run-start, end вF3. Все данныеtblrenderer не копировать/перепечатывать вручную.

При отсутствии readout/receipt/preview не выполнять S4.3/F3: сохранить partialfail по
TEMPLATE и сообщить безопасный fixed reason/actualcommands/режим, не выдумывать386rows.

## 7. Privacy, смысл принятия и публикация

Один report AH содержит3readbacks, а не3прогона. No new cases executed. Все129AG+145AF+
112AE rows толькоесли реальнопрочитаны. Reportdifference не равен testfailure; actual
source_contract_mismatch или missingresult не PASS. Не применять ожидание к actualfield.
Metadata/hashchecks неcryptographicauthenticationотroot/user, collectorнепривилегированный.
AGHOLD остаётся до рассмотрениянового отчёта. Продуктовыхизменений/runtimeactivationнет.

НеGit/чат/скрин rawstatus/config/log/kernel/URIs/IP/MAC/UUID/keys/passwords/SNI/ports/fp/
tags/PID/NIC/UID/home/registryids/boot/tokens/privatehashes/fingerprints/exception/argv/
privatecasefiles/receipt.json. Publicdata толькоknownids/enums/bools/counts/ms/rc/Git/
publicsourceSHA/sourcefile:line. Contract/reportdata публичныеполя; oldsourceполныеhashes
вreportнеперечислять. FooterJSONтольковwhitelist, весьMarkdownпрочитатьпередпубликацией.

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый AHreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3ah'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(not git('diff','--name-only','8045d3a34020e201e0d8c744236bd0e65896264b','HEAD','--','src','packaging','config.example.toml','pyproject.toml'),'PRODUCT_SOURCE_CHANGED')
for rel,digest in [('tests/stand/wave3_evidence_readout.py','9c05fe10c35783382c1764728fd98e59c1fec695ea8a05fa3f5e09e4d9428afe'),('tests/stand/wave3_evidence_contract.json','4a1af46f22d444e0f1a352f43d5a596ab904e167cd667e1cce80c43a060a9eec')]:
    require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AH_SOURCE_SHA')
for name,digest in json.loads((repo/'tests/stand/wave3_pool_manifest.json').read_bytes()).items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')
preview=(notes/'report-data.md').read_bytes();receipt=json.loads((notes/'receipt.json').read_bytes());draft=(notes/'report.md').read_bytes()
require(hashlib.sha256(preview).hexdigest()==receipt.get('report_data_sha256') and draft.startswith(preview),'AUTOMATIC_PREFIX_CHANGED')
tail=draft[len(preview):].decode('utf-8')
require(tail.startswith('\n<!-- AH_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
def pairs(items):
    data={}
    for k,v in items:
        require(k not in data,'FOOTER_DUPLICATE');data[k]=v
    return data
fields=json.loads(tail.split('```json\n',1)[1].rsplit('\n```',1)[0],object_pairs_hook=pairs)
required={'nnp','sudo_rc','collect_rc','show_rc','before_health','after_health','before_pool','after_pool','before_link','after_link','versions_unchanged','owner_actions'}
require(type(fields) is dict and set(fields)==required,'FOOTER_FIELDS')
require(fields['nnp'] is None or type(fields['nnp']) is int and fields['nnp'] in (0,1),'NNP_TYPE')
for key in ('sudo_rc','collect_rc','show_rc'):require(fields[key] is None or type(fields[key]) is int and -255<=fields[key]<=255,'COMMAND_RC')
for key in ('before_health','after_health'):require(fields[key] in ('HEALTHY_ON','OTHER','UNKNOWN'),'HEALTH_ENUM')
for key in ('before_pool','after_pool'):require(fields[key] in ('OFF','OBSERVE','ON','UNKNOWN'),'POOL_ENUM')
for key in ('before_link','after_link'):require(fields[key] in ('ALIVE','LOST','UNKNOWN'),'LINK_ENUM')
require(fields['versions_unchanged'] is None or type(fields['versions_unchanged']) is bool,'VERSION_BOOL')
require(fields['owner_actions'] is None or type(fields['owner_actions']) is int and 0<=fields['owner_actions']<=100,'OWNER_ACTIONS')
stamp=datetime.fromisoformat((notes/'run-start.txt').read_text().strip())
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AH start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3ah — exact existing AG AF AE readback')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. AHreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
