# ТЗ Flash: wave3ad — 130 source-hook cases за один заход, без установки

## 1. Основание, результат и максимальный объём

ACreport04a21bdc003493dc0c6bfacb360ee43856ccfcc6 принят:51/51,A28/B16/D7,
workingHEALTHY/on/pool/versions/связь прежние. REVIEW-REAL-MACHINE-0.2.0-wave3ac.md.
AC51/AB32/AA22/Z19/Y6/X26/W25 иoldbatches не повторять. FakeDвэтомпрогонеНЕисполняется.
Yrootmaterial не читать/не копировать. УточнениеAсводки:10COMPLETED/2REFUSED/14UNKNOWN/
2terminalcases, не11/15; общий51PASSнеизменён, старыйreportнепереписывать.

Максимальныйготовыйsafeобъём:38вариантовреальныхметодов×LEGACY/OWNED/FENCED=114cases
плюс16контекстных/error/readerпроверок. Всего130, одинstart/автопереходы/одинreport.
Casefail→остальные независимыеcases безмикровопросов. Audit/scope/source/baseline/privacy/
непригодныйFS — globalSTOP. Неготовыеliveэтапы радиобъёма НЕдобавлять.

Новыеметоды вызываются из privateкопииsource, сFakeRunner/API/service/TUN. Сетевые
команды лишь регистрируются заглушками, **не исполняются**. Dummycorefiles меняются
тольковuserfixture. Это не install/systemd/netns/VPNprobe. ADR-REC-C-OPT-IN-SOURCE-HOOKS.md.

ТОЛЬКОThinkCentre. WorkingLAN/HEALTHY/on baseline; hostнеLANUDP/IPv6/DNS/E4proof.
PreserveWAN/LAN/Tailscale/pin/pool/config/services/rules. Always_off запрещён;
incomingoutage>1мин следующаякомандамоделинеисправит. ADне вызываетсетевойотказ.

## 2. Точная sourceidentity и допустимые эффекты

Baselinepin351fb54e074f4a7b497a8a4244fc74c6088788d7. Противнего source diff **ровно4A+7M**:
четыреownership*.pyдобавлены, Capture/Backend/Applier/SingboxCore/Job/ApiClient/managed
получилиopt-inhooks. Existingcallers всёещёНЕпередаютcoordinator. Noneсохраняетlegacy,
**не обеспечиваетfence**. Mandatoryactorbinding/realverifier/bootstrapне реализованы.
InstalledXGW/units/config/WAN/LAN/TSне меняются. Неpipinstall/xgwinstall/restart/reload.

| Артефакт | SourceSHA256 |
|---|---|
| tests/stand/wave3_source_hooks.py → batch.py |9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
| tests/stand/wave3_hook_manifest.json → manifest.json |69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091|

Manifestфиксирует114.pysourcefiles; их exactSHA проверяется приfreeze иstart. Не
installed110tree, неаттестация114живыхмодулей. Snapshotsource используетсякакprivate
packagefrozen_ad. Freezeтолькодваартефакта и114sourcefiles в ~/xgw-w3ad0700;
source/freeze/registry/reportfiles0600, directories0700. ДанныеUI/.so/pycache не нужны.
Dummyproductoutputs могут иметьsource-expected0640/0644 и0755дляdummycore внутрипPrivatefixture0700;
неchmodпродукт радиPASS. Реальныхсекретов вfixtures нет; rawfiles всёравнонепубликовать.

WorkerдоsourceimportsставитCPythonauditguard: process/socket/fork/exec/kill/ctypes иwrite
внеnotesrefused. Guardпроверяетсобственнуюрегистрацию двумяmanualauditeventsбез запуска
процесса/сокета. Этоregressionguardtrustedcode, неsecuritysandboxотhostilecode.
UnexpectedblockedIO→failedcase+globalSTOP/остальныеNOT_RUN, безповтора/ослабленияguard.
Start/status/show — управляющиекоманды вне workerguard; workloadsubprocessesвworker0.

РазрешеныGitFF/NNP/sudo/status/poolreadonly, sourcefreeze/casefiles/flock/fsync/rename,
одинcollector иоднаthreadfixture. Registryboot/clocksynthetic, реальныеkernel/API/service
не вызываются. НикакихROOTY/runXGW/installedsource/controlsocket/DBreadsвworker.
Запрещеныoff/install/G1/enable/disable/WAN/LAN/TS/pin/pool/config/services/rules/APIwrites/
nft-c/nft/ip/GET/curl/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtest/coreversionprobes/
новаяопись/newunits/timers/guardian/arm/replay/real faults. GitdeliveryнеVPNprobe.

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
notes=Path.home()/'xgw-w3ad'
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

### S2.1. Чистаяfreepool/FF/4A+7M и publicsourceManifest

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
git('merge-base','--is-ancestor','04a21bdc003493dc0c6bfacb360ee43856ccfcc6','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_4A_7M')
manifest=repo/'tests/stand/wave3_hook_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==114,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','BATCH_SHA')
print('SOURCE_DIFF_FOUR_ADD_SEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужныrc0/SOURCE_DIFF_FOUR_ADD_SEVEN_MODIFY/SOURCE_MANIFEST_MATCHED114/SOURCE_PREFLIGHT_OK.
ActualHEAD/treeзаписать. Dirty/mismatch/nonFF→STOP, неreset/rebase/force/install.
114sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced.

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

### S2.4. Freezehelper/manifest и114исходников однимблоком

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3ad'
repo=Path.home()/'zcod/xgw'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o7777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('started.json','worker-claimed.json','progress.json','summary.json','cases')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
def freeze(target,raw,digest):
    if hashlib.sha256(raw).hexdigest()!=digest:
        raise SystemExit('STOP_SOURCE_SHA')
    relative=target.relative_to(notes)
    parent=notes
    for component in relative.parts[:-1]:
        parent=parent/component
        if not parent.exists() and not parent.is_symlink():
            parent.mkdir(mode=0o700)
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o7777!=0o700:
            raise SystemExit('STOP_FREEZE_PARENT_METADATA')
    if target.exists() or target.is_symlink():
        info=target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o7777!=0o600 or info.st_nlink!=1 or target.read_bytes()!=raw:
            raise SystemExit('STOP_PARTIAL_FREEZE_MISMATCH')
        return
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw)
raw=(repo/'tests/stand/wave3_hook_manifest.json').read_bytes()
freeze(notes/'manifest.json',raw,'69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091')
freeze(notes/'batch.py',(repo/'tests/stand/wave3_source_hooks.py').read_bytes(),'9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917')
data=json.loads(raw)
if type(data) is not dict or len(data)!=114:
    raise SystemExit('STOP_MANIFEST_SHAPE')
total=0
for name,digest in data.items():
    parts=PurePosixPath(name).parts
    if parts[:2]!=('src','xgw') or '..' in parts or not name.endswith('.py'):
        raise SystemExit('STOP_MANIFEST_PATH')
    source=repo/name
    if not stat.S_ISREG(source.lstat().st_mode):
        raise SystemExit('STOP_SOURCE_TYPE')
    body=source.read_bytes()
    total+=len(body)
    if len(body)>2097152 or total>16777216:
        raise SystemExit('STOP_SOURCE_LIMIT')
    freeze(notes/'source'/name,body,digest)
print('SOURCE_HOOK_FROZEN',len(data))
PY
```

НуженSOURCE_HOOK_FROZEN114/rc0. Existingmatchingfiles допускаютсятолькодляresumeподготовки
доstart; mismatch→STOP_IDENTITY, безoverwrite/newnotes. ЗатемS2.4bобязателен.

#### S2.4b. Полнаяпроверкаfreeze/unused передstart

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ad'
def valid(path,digest):
    info=path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
ok=ok and valid(notes/'batch.py','9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917') and valid(notes/'manifest.json','69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091')
data=json.loads((notes/'manifest.json').read_bytes())
ok=ok and len(data)==114
source=notes/'source'
ok=ok and not source.is_symlink() and source.is_dir() and source.stat().st_uid==os.getuid() and source.stat().st_mode&0o7777==0o700
seen=set()
for path in (notes/'source').rglob('*'):
    info=path.lstat()
    if stat.S_ISDIR(info.st_mode):
        ok=ok and info.st_uid==os.getuid() and info.st_mode&0o7777==0o700
    else:
        relative=path.relative_to(notes/'source').as_posix()
        ok=ok and relative in data and valid(path,data.get(relative,''))
        seen.add(relative)
ok=ok and seen==set(data)
unused=not any((notes/name).exists() or (notes/name).is_symlink() for name in ('started.json','worker-claimed.json','progress.json','summary.json','cases'))
print('SOURCE_HOOK_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

ТолькоREADY/rc0→S3.1. Afterstarted→S3.2/S3.3, никакихповторовfreeze/start/worker.

## 5. S3 —130проверок одногоsourceпакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ad/batch.py" start
```

НужныSOURCE_HOOK_BATCH_STARTED/rc0. Это Popencollector, не130PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нетworkloadsubprocess/netprobe/fakeD/service/timer/guardian.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ad/batch.py'
limit=time.monotonic()+300
previous=None
while time.monotonic()<limit:
    try:
        proc=subprocess.run([sys.executable,'-I','-B',str(model),'status'],capture_output=True,text=True,timeout=8,check=False)
        if proc.returncode!=0:
            print('MONITOR_READ_FAILED',proc.returncode)
            raise SystemExit(3)
        value=json.loads(proc.stdout)
        if value.get('file')=='summary.json':
            print('BATCH_FINISHED',value['data'].get('marker'),value['data'].get('passed'),value['data'].get('expected'))
            raise SystemExit(0)
        completed=value.get('data',{}).get('completed')
        if completed!=previous:
            print('BATCH_PROGRESS',completed)
            previous=completed
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise SystemExit('MONITOR_READ_UNAVAILABLE') from None
    time.sleep(5)
print('BATCH_OBSERVATION_TIMEOUT')
raise SystemExit(3)
PY
```

Monitor0=summaryнайден, неcasePASS;300с неnetworkdeadline. Обрыв/rc3/timeout→S3.3/after/
report, безstart/retry/newnotes/killcollector/сети. Разрешенытолькоstatus/show.

### S3.3. Одинfullreadout+формальнаяпроверка

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys
from pathlib import Path
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ad/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['C_SAVE__LEGACY', 'C_SAVE__OWNED', 'C_SAVE__FENCED', 'C_LOAD_OFF__LEGACY', 'C_LOAD_OFF__OWNED', 'C_LOAD_OFF__FENCED', 'C_UP__LEGACY', 'C_UP__OWNED', 'C_UP__FENCED', 'C_ENABLE__LEGACY', 'C_ENABLE__OWNED', 'C_ENABLE__FENCED', 'C_DISABLE__LEGACY', 'C_DISABLE__OWNED', 'C_DISABLE__FENCED', 'C_OPEN__LEGACY', 'C_OPEN__OWNED', 'C_OPEN__FENCED', 'C_CLOSE__LEGACY', 'C_CLOSE__OWNED', 'C_CLOSE__FENCED', 'C_DOWN__LEGACY', 'C_DOWN__OWNED', 'C_DOWN__FENCED', 'C_TUN__LEGACY', 'C_TUN__OWNED', 'C_TUN__FENCED', 'C_TIDY__LEGACY', 'C_TIDY__OWNED', 'C_TIDY__FENCED', 'C_TS_DIRECT__LEGACY', 'C_TS_DIRECT__OWNED', 'C_TS_DIRECT__FENCED', 'C_TS_EARLY__LEGACY', 'C_TS_EARLY__OWNED', 'C_TS_EARLY__FENCED', 'C_TS_FALLBACK__LEGACY', 'C_TS_FALLBACK__OWNED', 'C_TS_FALLBACK__FENCED', 'B_SAVE__LEGACY', 'B_SAVE__OWNED', 'B_SAVE__FENCED', 'B_ELEMENT__LEGACY', 'B_ELEMENT__OWNED', 'B_ELEMENT__FENCED', 'B_PREPARE__LEGACY', 'B_PREPARE__OWNED', 'B_PREPARE__FENCED', 'B_STOP__LEGACY', 'B_STOP__OWNED', 'B_STOP__FENCED', 'B_RECONCILE__LEGACY', 'B_RECONCILE__OWNED', 'B_RECONCILE__FENCED', 'X_APPLY__LEGACY', 'X_APPLY__OWNED', 'X_APPLY__FENCED', 'X_ROLLBACK__LEGACY', 'X_ROLLBACK__OWNED', 'X_ROLLBACK__FENCED', 'S_APPLY__LEGACY', 'S_APPLY__OWNED', 'S_APPLY__FENCED', 'S_EQUAL__LEGACY', 'S_EQUAL__OWNED', 'S_EQUAL__FENCED', 'S_REMOVE__LEGACY', 'S_REMOVE__OWNED', 'S_REMOVE__FENCED', 'S_DEFER__LEGACY', 'S_DEFER__OWNED', 'S_DEFER__FENCED', 'S_ROLLBACK__LEGACY', 'S_ROLLBACK__OWNED', 'S_ROLLBACK__FENCED', 'S_RESTART__LEGACY', 'S_RESTART__OWNED', 'S_RESTART__FENCED', 'API_ADD_OUT__LEGACY', 'API_ADD_OUT__OWNED', 'API_ADD_OUT__FENCED', 'API_RM_OUT__LEGACY', 'API_RM_OUT__OWNED', 'API_RM_OUT__FENCED', 'API_ADD_IN__LEGACY', 'API_ADD_IN__OWNED', 'API_ADD_IN__FENCED', 'API_RM_IN__LEGACY', 'API_RM_IN__OWNED', 'API_RM_IN__FENCED', 'API_ROUTING__LEGACY', 'API_ROUTING__OWNED', 'API_ROUTING__FENCED', 'API_PIN__LEGACY', 'API_PIN__OWNED', 'API_PIN__FENCED', 'API_UNPIN__LEGACY', 'API_UNPIN__OWNED', 'API_UNPIN__FENCED', 'P_UPDATE__LEGACY', 'P_UPDATE__OWNED', 'P_UPDATE__FENCED', 'P_NOOP__LEGACY', 'P_NOOP__OWNED', 'P_NOOP__FENCED', 'K_UPDATE__LEGACY', 'K_UPDATE__OWNED', 'K_UPDATE__FENCED', 'K_REPLACE__LEGACY', 'K_REPLACE__OWNED', 'K_REPLACE__FENCED', 'K_ROLLBACK__LEGACY', 'K_ROLLBACK__OWNED', 'K_ROLLBACK__FENCED', 'H_NO_VERIFIER', 'H_NESTED_ROLES', 'H_TAINT', 'H_EXCEPTION', 'H_TERMINAL', 'H_GENERATOR', 'H_NESTED_GENERATOR', 'H_THREAD', 'H_FOREIGN_CONTEXT', 'E_BACKEND_COMPENSATION', 'E_FAILED_OUTCOME', 'E_SINGBOX_ROLLBACK', 'R_ADDRESS', 'R_OUTBOUNDS', 'R_INBOUNDS', 'R_BALANCER']
rows=data.get('cases',[])
shape=(data.get('scope')=='OPT_IN_SOURCE_HOOKS_FAKE_EFFECTS_ONLY' and data.get('expected')==130
       and data.get('completed')==len(rows) and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='SOURCE_HOOK_BATCH_RECORDED' and data.get('completed')==130
      and data.get('passed')==130 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==114)
print('FINAL_SHAPE_VALID',shape)
print('ALL_CASES_PASSED',good)
raise SystemExit(0 if good else 3)
PY
```

Start/monitor/show/shapecommandrc отдельно; collector_exit_rcNOT_COLLECTED. Summary
финальный, progressfinalfalseтолькоcheckpoint; remainingNOT_RUN. НетданныхUNKNOWNне0.
Unexpectedauditdenial→GLOBAL_SCOPE_STOP/оставшиесяNOT_RUN, неразрешениеослабитьguard.

## 6. S4 — конечные наблюдения и интерпретация

### S4.1. Конечный статус

```bash
bash -o pipefail -c 'sudo -n xgw status | grep -E "^Состояние|Перехват:|^Xray|^sing-box"'
```

Ожидается исходный HEALTHY/on и прежние версии. Иное записать, режим не менять.
Нет связи → ждать возврата; не пытаться rescue следующей сетевой командой.

### S4.2. Конечный режим пула

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

Ожидается исходный статус. Никаких pin/rotation/pool/Tailscale изменений.
Status bookends не являются непрерывным наблюдением или проверкой route/шести PID.
Подробные Y/V context flags здесь не собираются: не переносить их как новый after.

### S4.3.130cases и семантика результатов

Каждая строка матрицы содержит3отдельныхcaseID: VARIANT__LEGACY/__OWNED/__FENCED.
LEGACY:реальныйbodyбезcoordinator, businessreturnпроверен/receipts0. OWNED:тотжеbody,
ожидаемыйreturnclass/одинreceipt, nestedhelpersнепубликуютпромежуточноеgeneration.
FENCED:refusalдоbodyeffects, fixturebytesunchanged/FakeRunnertrace0/receipts0.
Nonelegacy неfenceproof. Операции зафиксированызаглушками и auditguard, не shellкоманды.

| Variant | 3режима обязательны |
|---|---|
|C_SAVE|LEGACY / OWNED / FENCED|
|C_LOAD_OFF|LEGACY / OWNED / FENCED|
|C_UP|LEGACY / OWNED / FENCED|
|C_ENABLE|LEGACY / OWNED / FENCED|
|C_DISABLE|LEGACY / OWNED / FENCED|
|C_OPEN|LEGACY / OWNED / FENCED|
|C_CLOSE|LEGACY / OWNED / FENCED|
|C_DOWN|LEGACY / OWNED / FENCED|
|C_TUN|LEGACY / OWNED / FENCED|
|C_TIDY|LEGACY / OWNED / FENCED|
|C_TS_DIRECT|LEGACY / OWNED / FENCED|
|C_TS_EARLY|LEGACY / OWNED / FENCED|
|C_TS_FALLBACK|LEGACY / OWNED / FENCED|
|B_SAVE|LEGACY / OWNED / FENCED|
|B_ELEMENT|LEGACY / OWNED / FENCED|
|B_PREPARE|LEGACY / OWNED / FENCED|
|B_STOP|LEGACY / OWNED / FENCED|
|B_RECONCILE|LEGACY / OWNED / FENCED|
|X_APPLY|LEGACY / OWNED / FENCED|
|X_ROLLBACK|LEGACY / OWNED / FENCED|
|S_APPLY|LEGACY / OWNED / FENCED|
|S_EQUAL|LEGACY / OWNED / FENCED|
|S_REMOVE|LEGACY / OWNED / FENCED|
|S_DEFER|LEGACY / OWNED / FENCED|
|S_ROLLBACK|LEGACY / OWNED / FENCED|
|S_RESTART|LEGACY / OWNED / FENCED|
|API_ADD_OUT|LEGACY / OWNED / FENCED|
|API_RM_OUT|LEGACY / OWNED / FENCED|
|API_ADD_IN|LEGACY / OWNED / FENCED|
|API_RM_IN|LEGACY / OWNED / FENCED|
|API_ROUTING|LEGACY / OWNED / FENCED|
|API_PIN|LEGACY / OWNED / FENCED|
|API_UNPIN|LEGACY / OWNED / FENCED|
|P_UPDATE|LEGACY / OWNED / FENCED|
|P_NOOP|LEGACY / OWNED / FENCED|
|K_UPDATE|LEGACY / OWNED / FENCED|
|K_REPLACE|LEGACY / OWNED / FENCED|
|K_ROLLBACK|LEGACY / OWNED / FENCED|

Дополнительные16caseIDs:

- H_NO_VERIFIER
- H_NESTED_ROLES
- H_TAINT
- H_EXCEPTION
- H_TERMINAL
- H_GENERATOR
- H_NESTED_GENERATOR
- H_THREAD
- H_FOREIGN_CONTEXT
- E_BACKEND_COMPENSATION
- E_FAILED_OUTCOME
- E_SINGBOX_ROLLBACK
- R_ADDRESS
- R_OUTBOUNDS
- R_INBOUNDS
- R_BALANCER

Никаких AC51/AB32повторов. K_REPLACE/K_ROLLBACK работаютсdummycorefiles, нескачивают/
неисполняютбинарники. APIstub неAPIзапрос; FakeRunnerargv неисполненнаякоманда. Source
Capture.mode/rules/низкоуровневыеchecks synthetic, неLANpacketproof/actualkernelapply.
Fixtureverifiercallerassertions — не C-VERIFY. LegacycallersполучаютNone, нет mandatorybinding.

Ошибкисохраняютerrorclass и public_error_source/public_error_line (репозиторныйsourcepath,
неhomepath/traceback). При несовпадении businessreturn сохраняетсяfixedexpected/observed
returnclass. Partialcountsнеподменятьexpected. ПоauditglobalSTOPостальныеNOT_RUN.
Threadcaseпроверяетотдельныйticket, неdaemon/coreпроцесс. No workloadprocesses.
Status/poolafterтолькоbookends, неYkernel/PID/RPDB/configafter. Все7runtimegatesfalse
дажепри130/130. Runtimeactorbinding/verifier/fence/repair/recovery/bootstrapне реализованы.

## 7. Один отчёт и privacyreview

Заполнить TEMPLATE в ~/xgw-w3ad/report.md: actualHEAD/tree/source4A7M/helperSHA/manifestSHA/
114sourcefreeze, NNP/sudo/owneractions/before-afterHEALTHY/on/pool/версии/связь. Start/
monitor/show/shapecommandrc отдельно, collector_exit_rcNOT_COLLECTED. Все130casebools,
failedfixedfields, sourcefile:line, LEGACY/OWNED/FENCEDcounts и16extras. ТолькоодинMarkdown.
Приpartialпоказатьcompleted/remainingNOT_RUN, не считатьread0 илиshapevalidPASS.

НеGit/чат/скрин rawcasefiles/config/status/logs/kernel/URIs/IP/MAC/UUID/keys/passwords/
SNI/ports/fp/tags/PID/NIC/UID/homepaths/registryids/boot/tokens/privatehashes/rawexceptions/
argv/resulttexts. ТолькоfixedcaseIDs/enums/bools/counts/timingsms/rc/Git/sourceSHA и
публичныйrepofile:line. SourceManifestпубличный, но не вставлять114хешей вreport.
ВесьMarkdownпрочитатьдоединственнойпубликации. НикакогоinstallпоуспешномуТЗ.

Далееfixesпоevidenceлибоmandatorybinding/compositegeneration/verifiers/repair/bootstrap
вследующеммаксимальномготовомdryпакете. OnlyThinkCentre/workingLAN, hostнеLANclient.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты,неwave4/DAE.
РеальнаяAD NOT_RUN дофактическогоотчёта.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 7. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3ad'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ad-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M'}
require(git('diff','--name-status',code,'HEAD','--',*runtime).splitlines()==[expected[name]+'\t'+name for name in sorted(expected)],'source diff не4A7M')
require(hashlib.sha256((repo/'tests/stand/wave3_hook_manifest.json').read_bytes()).hexdigest()=='69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091','manifest SHA изменился')
for name,digest in json.loads((repo/'tests/stand/wave3_hook_manifest.json').read_bytes()).items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'source SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','helper SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3ad — source hooks fake-effects batch')
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
