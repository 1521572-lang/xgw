# ТЗ Flash AO: две исправленные проверки AN и все позиции остановки операции

04.11.2026. AN выполнил852cases,850passed/2fixtureFAIL, не повторять850пройденных.
Report296d2a062eae3a521860b7f099ee3ca245ea4a7e; tested755a5f0/treec0ff6c10d5ae4947c9e803bae2cd2987eef172e2.
Загрузчик исправлен и реально прошёл. Batch263577ms/casesum214706ms; интервал13:58:59–
14:10:36MSK697s не времяworker. Publicprefix восстановлен pinnedpureformatter byteexact.
AN_HEALTHY_ONbeforeafter/poolOFF/linkALIVE/versionssame/owneractions0/NNP0/sudo0/start0/
monitor0/show0/report0,shape3. WorkerexitNOT_COLLECTED. Auditreadytrue/violations0/
workloadprocess0/network0/liveops0/7runtimeflagsfalse. Новыхkernel/LAN/installedproofнет.

F_CHECKER_RAISE/F_BODY_RAISE намеренно бросают RuntimeError("PRIVATE_FIXTURE").
Coordinator правильно rethrow, writerUNKNOWN1/receipt0/gen0/restoretrue. Ошибка сборщика:
refuse() принимал только MutationBlocked/Refused/SystemExit. Product122files менять
не нужно. Теперь ONLYдля этих2fixtureflags exactRuntimeError+exactfixtureargs принимается
как ожидаемый operationerror; прочиеRuntimeError/subclasses/message остаютсяFAIL.
Operationerror отдельно operation_error_observed=true, НЕподменяетсяrefused=true.

AO выполняетОДНИМstart66cases:2исправленных исходных одноступенчатыхсценария+64новых
POSITION_BODY_01…32/POSITION_CHECKER_01…32. Каждаяposition—32stepплан, намеренныйfault
вточкеN. ПолныйAN852/старыеAL/AK/AJбольшеНЕзапускать. Source122/packaging8/config/
pyprojectUNCHANGED; helperизменённаместе, ANplanсоOLD_SHAбольшеНЕвыполнять.
Новый~/xgw-w3ao; старыйANнеclean/overwrite/restart. Scopeготовойработыобъединёнполностью,
нераздуватьповтором850PASS/несвязаннымипрогонами/искусственнымиожиданиями.

Каждыйcase:bodycalls=N;checkercalls=N−1дляBODYилиNдляCHECKER;finalcalls0;writer_total1/
unknown1/receipt0/gen0/usedtrue;operation_error_observedtrue;targetrestoredtrue.
BODY_N=1:panelотсутствует. BODY_N>1иCHECKER_N:panelприсутствуеткакpartialfileeffect.
Послеfaultникакихследующихsteps/finalchecker. Это НЕrollback/atomictransaction/recovery.
failure_step/panel_present/operation_error_observed—новыеactualполя, nullableне0.
Все20details whitelist; errorsfixedclass+publicfile:line, безrawexceptions/defaults/paths.
OneREADY/start/auto600s/show+shape/partial/3pages/oneF3report. PositivePASSозначает
правильноеотклонениеоперации, неcompletedpublication. All7runtimeflagsfalse/Cblocked.

ТолькоThinkCentre/workingLAN/HEALTHY/on, LANclientнет/не спрашивать. Nooff/install/G1/
newSSHinventory/WAN/LAN/TS/pin/pool/config/services/live rules/APIwrites/nft/ip/curl/DNS/
ping/SSH/scans/pcap/netns/speedtest/newunits/timers/guardian/arm/fault. Always_offзапрещён.
Independentoriginalon/code/unitrescueДОinstall/fault;incomingoutage>1миннеfixnextcommand.
OnlyprivatePanelWriter/managedfiles/privatecode/unitseals/registry, остальныеblankactors
безbody. NOactualnetwork/Coreactors. Constructors/sealбезI/O; codebound/source-only/
cooperativeнеmandatoryglobalgraph/domainverification/loadedcodeattestation.
OrdinarycaseFAILсprovenrestore→independentcontinue;source/baseline/privacy/audit/OSError/
restorefailure→globalSTOP/remainingNOT_RUN. No retries/repair/compensation/снятияgates.
AcceptedADguardbeforeimports, trustedregressionguardнеhostilecodesandbox.

Локально7targetedtests/RuffPASS:двеошибки,positions16/32body+checker инеожиданныйRuntimeError.
Full66/ThinkCentreNOT_RUN. Старые22/852/broadVMНЕповторялись. Sourceparent296d2a0/
PRODUCTDIFFEMPTY/pin35112A11M/122source. Из семиartifactSHA изменёнтолькоbatch:
840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652

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
notes=Path.home()/'xgw-w3ao'
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

### S2.1. Чистаяfreepool/FF/12A+11M и publicsourceManifest

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
git('merge-base','--is-ancestor','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/ownership_completion.py': 'A', 'src/xgw/ownership_entrypoints.py': 'A', 'src/xgw/ownership_identity.py': 'A', 'src/xgw/ownership_seal.py': 'A', 'src/xgw/ownership_surface.py': 'A', 'src/xgw/ownership_composition.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M', 'src/xgw/freepool/pool.py': 'M', 'src/xgw/freepool/store.py': 'M', 'src/xgw/actions.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_12A_11M')
manifest=repo/'tests/stand/wave3_composition_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==122,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_bound_composition.py').read_bytes()).hexdigest()=='840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')

for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:
    require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'ARTIFACT_SHA')
pack=json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())
require(type(pack) is dict and len(pack)==8,'PACKAGING_COUNT')
require(set(pack)=={p.relative_to(repo).as_posix() for p in (repo/'packaging').iterdir() if p.is_file()},'PACKAGING_INVENTORY')
for name,digest in pack.items():require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PACKAGING_BYTES')
require(json.loads((repo/'tests/stand/wave3_surface_catalog.json').read_bytes())['schema']==1,'SURFACE_MANIFEST')
require(git('diff','--name-only','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==[],'PRODUCT_SOURCE_CHANGED')
print('ARTIFACTS_AND_PACKAGING_MATCHED',7,8,65)

print('SOURCE_DIFF_TWELVE_ADD_ELEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
notes=Path.home()/'xgw-w3ao'
context=json.dumps({'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}')},sort_keys=True).encode()+b'\n'
target=notes/'source-current.json'
if target.exists() or target.is_symlink():
    import stat
    info=target.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and target.read_bytes()==context,'SOURCE_CONTEXT_CHANGED')
else:
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(context)
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужныrc0/SOURCE_DIFF_TWELVE_ADD_ELEVEN_MODIFY/SOURCE_MANIFEST_MATCHED122/SOURCE_PREFLIGHT_OK.
ActualHEAD/treeзаписать. Dirty/mismatch/nonFF→STOP, неreset/rebase/force/install.
122sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced. Семь artifacts и восемь public packaging копий проверены отдельно, installed units не читались.

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

### S2.4. Freeze семи artifacts, 122 source и восьми packaging-копий

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3ao'
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

artifacts=[('tests/stand/wave3_bound_composition.py', 'batch.py', '840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]
for rel,frozen,digest in artifacts:freeze(notes/frozen,(repo/rel).read_bytes(),digest)
for frozen,folder,count in [('manifest.json','source',122),('units.json','units',8)]:
    data=json.loads((notes/frozen).read_bytes())
    if type(data) is not dict or len(data)!=count:raise SystemExit('STOP_MANIFEST_SHAPE')
    total=0
    for name,digest in data.items():
        parts=PurePosixPath(name).parts
        valid=(parts[:2]==('src','xgw') and name.endswith('.py')) if folder=='source' else (len(parts)==2 and parts[0]=='packaging')
        if not valid or '..' in parts:raise SystemExit('STOP_MANIFEST_PATH')
        source=repo/name
        cursor=repo
        for part in parts[:-1]:
            cursor=cursor/part
            if not stat.S_ISDIR(cursor.lstat().st_mode):raise SystemExit('STOP_SOURCE_PARENT')
        if not stat.S_ISREG(source.lstat().st_mode):raise SystemExit('STOP_SOURCE_TYPE')
        body=source.read_bytes();total+=len(body)
        if len(body)>2097152 or total>16777216:raise SystemExit('STOP_SOURCE_LIMIT')
        freeze(notes/folder/name,body,digest)
print('BOUND_COMPOSITION_FROZEN',7,122,8)

PY
```

Нужен BOUND_COMPOSITION_FROZEN 7 122 8/rc0. Resume допускается только ДОstart с теми же байтами. Никаких chmod/install/execute для packaging. Затем обязательный S2.4b.

#### S2.4b. Exact freeze и unused перед единственным start

```bash
python3 -I -B - <<'PY'

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ao'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',122),('units.json','units',8)]:
    data=json.loads((notes/frozen).read_bytes());require(type(data) is dict and len(data)==count,'MANIFEST_SHAPE')
    top=notes/folder;require(directory(top),'FROZEN_ROOT_METADATA');seen=set()
    for path in top.rglob('*'):
        info=path.lstat()
        if stat.S_ISDIR(info.st_mode):require(directory(path),'FROZEN_DIRECTORY_METADATA')
        else:
            name=path.relative_to(top).as_posix()
            require(name in data and valid(path,data.get(name,'')),'FROZEN_TREE_BYTES')
            seen.add(name)
    require(seen==set(data),'FROZEN_INVENTORY')

require(not any((notes/name).exists() or (notes/name).is_symlink() for name in ('started.json','worker-claimed.json','progress.json','summary.json','cases')),'ALREADY_STARTED_READ_S3_2')
print('BOUND_COMPOSITION_READY')

PY
```

Только BOUND_COMPOSITION_READY/rc0 →S3.1. Afterstarted →S3.2/S3.3, безfreeze/start/worker повторно.

## 5. S3 — 66 проверок одного source-пакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ao/batch.py" start
```

НужныBOUND_COMPOSITION_BATCH_STARTED/rc0. Это Popencollector, не66PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AI78/AG129/AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до600с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ao/batch.py'
limit=time.monotonic()+600
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

Monitor0=summaryнайден, неcasePASS;600с неnetworkdeadline. Обрыв/rc3/timeout→S3.3/after/
report, безstart/retry/newnotes/killcollector/сети. Разрешенытолькоstatus/show.

### S3.3. Одинfullreadout+формальнаяпроверка

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys
from pathlib import Path
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ao/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    print('SHOW_SUBCOMMAND_RC',proc.returncode)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print('SHOW_SELECTED',wrapper.get('file') if wrapper.get('file') in ('summary.json','progress.json') else 'UNKNOWN')
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['F_CHECKER_RAISE', 'F_BODY_RAISE', 'POSITION_BODY_01', 'POSITION_BODY_02', 'POSITION_BODY_03', 'POSITION_BODY_04', 'POSITION_BODY_05', 'POSITION_BODY_06', 'POSITION_BODY_07', 'POSITION_BODY_08', 'POSITION_BODY_09', 'POSITION_BODY_10', 'POSITION_BODY_11', 'POSITION_BODY_12', 'POSITION_BODY_13', 'POSITION_BODY_14', 'POSITION_BODY_15', 'POSITION_BODY_16', 'POSITION_BODY_17', 'POSITION_BODY_18', 'POSITION_BODY_19', 'POSITION_BODY_20', 'POSITION_BODY_21', 'POSITION_BODY_22', 'POSITION_BODY_23', 'POSITION_BODY_24', 'POSITION_BODY_25', 'POSITION_BODY_26', 'POSITION_BODY_27', 'POSITION_BODY_28', 'POSITION_BODY_29', 'POSITION_BODY_30', 'POSITION_BODY_31', 'POSITION_BODY_32', 'POSITION_CHECKER_01', 'POSITION_CHECKER_02', 'POSITION_CHECKER_03', 'POSITION_CHECKER_04', 'POSITION_CHECKER_05', 'POSITION_CHECKER_06', 'POSITION_CHECKER_07', 'POSITION_CHECKER_08', 'POSITION_CHECKER_09', 'POSITION_CHECKER_10', 'POSITION_CHECKER_11', 'POSITION_CHECKER_12', 'POSITION_CHECKER_13', 'POSITION_CHECKER_14', 'POSITION_CHECKER_15', 'POSITION_CHECKER_16', 'POSITION_CHECKER_17', 'POSITION_CHECKER_18', 'POSITION_CHECKER_19', 'POSITION_CHECKER_20', 'POSITION_CHECKER_21', 'POSITION_CHECKER_22', 'POSITION_CHECKER_23', 'POSITION_CHECKER_24', 'POSITION_CHECKER_25', 'POSITION_CHECKER_26', 'POSITION_CHECKER_27', 'POSITION_CHECKER_28', 'POSITION_CHECKER_29', 'POSITION_CHECKER_30', 'POSITION_CHECKER_31', 'POSITION_CHECKER_32']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','unit_files','declared_surfaces','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='OPERATION_FAULT_POSITION_QUALIFICATION_ONLY' and data.get('expected')==66
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==66-len(rows) and len(rows)<=66 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='BOUND_COMPOSITION_BATCH_RECORDED' and data.get('completed')==66
      and data.get('passed')==66 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==122 and data.get('unit_files')==8 and data.get('declared_surfaces')==65 and data.get('remaining_not_run')==0
      and data.get('global_scope_stop') is False)
print('FINAL_SHAPE_VALID',shape)
print('ALL_CASES_PASSED',good)
print('SHAPE_COMMAND_RC',0 if good else 3)
print('FAILED_KNOWN_CASES',[r['case'] for r in rows if type(r) is dict and r.get('case') in expected and r.get('passed') is False])
raise SystemExit(0 if good else 3)
PY
```

Записать SHOW_SUBCOMMAND_RC как show_rc, фактический rc всего S3.3 как shape_rc.
Они НЕ одно поле: при caseFAIL show0/shape3. При unavailable actualshape может1/null;
не подставлять ожидаемыйrc. Start/monitor/report отдельно; worker_exit_rcNOT_COLLECTED. Summary
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

### S4.3. Зафиксировать автоматический exact report snapshot

```bash
python3 -I -B "$HOME/xgw-w3ao/batch.py" report
```

Нужны BOUND_COMPOSITION_REPORT_READY/rc0. Это НЕновыйworker/неPASS. Выбирает finalsummary,
илиprogress при отсутствииsummary; всеactualполя/nulls/точныеms проходятwhitelist.
Создаёт EXCL report-record.json (sanitizedprivatecheckpoint) иreport-data.md.
Snapshot сохраняет именно прочитанныйprefix даже при последующемprogress; не подменять
его новойsummary. Повторreport разрешён только как readonlydeterministicverification
этогоsnapshot, НЕповторstart. Unknownfields/privacy/typeerror→STOPreport; не обходить.
Если ниsummaryниprogress нет, AH-stylepartialfailure: NOT_COLLECTED/remainingNOT_RUN;
не выполнятьS4.4/S4.5/F3/не выдумывать66rows. Сообщитьsafe fixedfailure иactualrc.

### S4.4. Прочитать весь обезличенный Markdown

```bash
python3 -I -B - <<'PY'
from pathlib import Path
lines=(Path.home()/'xgw-w3ao/report-data.md').read_text(encoding='utf-8').splitlines()
if len(lines)>120:raise SystemExit('STOP_UNEXPECTED_REPORT_LENGTH')
print('SANITIZED_REPORT_LINES',len(lines))
PY
```

Прочитать все строки, включая failed/nullable. Не ручнойперенос/округление/~N/подстановка
ожиданий. ДанныеALL_CASES_PASSED вS3.3 не заменяют actualcases. Не catcasefiles/config/
registry/fingerprints/logs/receipt/rawexceptions. Не публиковать rawstatus/screenshots.


Ниже3обязательные страницы по40строк, прочитать все. Пустойхвостpartial допустим.

#### S4.4a. Строки 1–40

```bash
sed -n '1,40p' "$HOME/xgw-w3ao/report-data.md"
```

Нуженrc0, прочитатьвсё, prefix/таблицу не редактировать.

#### S4.4b. Строки 41–80

```bash
sed -n '41,80p' "$HOME/xgw-w3ao/report-data.md"
```

Нуженrc0, прочитатьвсё, prefix/таблицу не редактировать.

#### S4.4c. Строки 81–120

```bash
sed -n '81,120p' "$HOME/xgw-w3ao/report-data.md"
```

Нуженrc0, прочитатьвсё, prefix/таблицу не редактировать.

### S4.5. Создать draft с неизменным automatic prefix

```bash
python3 -I -B - <<'PY'
import os
from pathlib import Path
notes=Path.home()/'xgw-w3ao';repo=Path.home()/'zcod/xgw'
prefix=(notes/'report-data.md').read_bytes()
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ao-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(prefix+footer)
print('AO_DRAFT_CREATED')
PY
```

НуженAO_DRAFT_CREATED/rc0. Заполнить ТОЛЬКОfooterJSON послеAO_EXECUTION пофактически
наблюдённымданным. start/monitor/show/shape/reportrc отдельно; workerexitNOT_COLLECTED.
NNP/sudo/health/pool/link/versions/owneractions actual, null/UNKNOWN если не собрано.
NNP1 службы не NNРканала; healthenumHEALTHY_ON требует оба признака. Не вставлять
privatebaseline/rawstatus/метки/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryids/
tokens/privatehashes/argv/resulttexts/exception/screenshots. PublicsourceSHA разрешены.
Таблицы/prefix не редактировать. CasePASS отрицательногоcase не ExecutionCOMPLETED.

## 7. Интерпретация, автоматический отчёт и одна публикация

Больший объём не даёт права ослабить source/baseline/privacySTOP или добавлять live
fault/install. Одно ожидание до600с — срок наблюдения usercollector, не networkrescue.
Отсутствие finalsummary не повод startagain/kill/newnotes. Show/status→partialreport.
Report фиксирует точный выбранныйsummary/checkpoint вsanitizedEXCLreport-record.json;
advancingprogress не меняет snapshot. Поля calls/receipt/generation/unknown/observations/phase/build/files/used/refused/restored
nullable и whitelisted. Lastbuildmatchedtrue не finalcompletion; смотреть phase иreceipt.
Private callbacks/paths/hashes/values/registryids не сериализуются.
Автотаблицу не редактировать/не округлять. ReadallMarkdownbeforeonepublish.

PubliconlyknownIDs/enums/bools/counts/exactms/commandrc/Git/publicsourceSHA/publicrepo:line.
No rawconfig/status/log/kernel/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryid/
tokens/privatehashes/argv/resulttexts/exceptions/screenshots. Baselineнаблюдения отдельно
отcaseданных. Installedkernel/SQLtransaction/LANUDP/IPv6/DNS/E4/performance/allTS неPASS.
Source/globalgates и bootstrap долг сохраняются. ТолькоThinkCentre, сеть не менять.

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый AOreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3ao'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(git('diff','--name-only','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==[],'PRODUCT_SOURCE_CHANGED')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AO_SOURCE_SHA')
for name,digest in {**json.loads((repo/'tests/stand/wave3_composition_manifest.json').read_bytes()),**json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())}.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ao'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '840c0be07b3e1432f3c76f2bcb201d90ad12d076088c9cb2cc257938556b4652'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',122),('units.json','units',8)]:
    data=json.loads((notes/frozen).read_bytes());require(type(data) is dict and len(data)==count,'MANIFEST_SHAPE')
    top=notes/folder;require(directory(top),'FROZEN_ROOT_METADATA');seen=set()
    for path in top.rglob('*'):
        info=path.lstat()
        if stat.S_ISDIR(info.st_mode):require(directory(path),'FROZEN_DIRECTORY_METADATA')
        else:
            name=path.relative_to(top).as_posix()
            require(name in data and valid(path,data.get(name,'')),'FROZEN_TREE_BYTES')
            seen.add(name)
    require(seen==set(data),'FROZEN_INVENTORY')

proc=subprocess.run(['python3','-I','-B',str(notes/'batch.py'),'report'],capture_output=True,text=True,timeout=10,check=False)
require(proc.returncode==0 and proc.stdout.strip()=='BOUND_COMPOSITION_REPORT_READY','REPORT_SNAPSHOT_CHANGED')
preview=(notes/'report-data.md').read_bytes();draft=(notes/'report.md').read_bytes()
require(draft.startswith(preview),'AUTOMATIC_PREFIX_CHANGED')
tail=draft[len(preview):].decode('utf-8')
require(tail.startswith('\n<!-- AO_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
def pairs(items):
    data={}
    for k,v in items:
        require(k not in data,'FOOTER_DUPLICATE');data[k]=v
    return data
fields=json.loads(tail.split('```json\n',1)[1].rsplit('\n```',1)[0],object_pairs_hook=pairs)
required={'nnp','sudo_rc','start_rc','monitor_rc','show_rc','shape_rc','report_rc','before_health','after_health','before_pool','after_pool','before_link','after_link','versions_unchanged','owner_actions'}
require(type(fields) is dict and set(fields)==required,'FOOTER_FIELDS')
require(fields['nnp'] is None or type(fields['nnp']) is int and fields['nnp'] in (0,1),'NNP_TYPE')
for key in ('sudo_rc','start_rc','monitor_rc','show_rc','shape_rc','report_rc'):require(fields[key] is None or type(fields[key]) is int and -255<=fields[key]<=255,'COMMAND_RC')
for key in ('before_health','after_health'):require(fields[key] in ('HEALTHY_ON','OTHER','UNKNOWN'),'HEALTH_ENUM')
for key in ('before_pool','after_pool'):require(fields[key] in ('OFF','OBSERVE','ON','UNKNOWN'),'POOL_ENUM')
for key in ('before_link','after_link'):require(fields[key] in ('ALIVE','LOST','UNKNOWN'),'LINK_ENUM')
require(fields['versions_unchanged'] is None or type(fields['versions_unchanged']) is bool,'VERSION_BOOL')
require(fields['owner_actions'] is None or type(fields['owner_actions']) is int and 0<=fields['owner_actions']<=100,'OWNER_ACTIONS')
stamp=datetime.fromisoformat((notes/'run-start.txt').read_text().strip())
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ao-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AO start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3ao — code-bound writer and FILES composition')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AL/AK/AJ/AI/AH/AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. AOreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
