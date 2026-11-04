# ТЗ Flash AP — ресурсные контракты и dry bootstrap,211сценариев одним запуском

04.11.2026. AP-1…4 реализованы source-only. Все gates false, installedruntime не обновлять.
Документы: API-CONTRACT-WAVE3AP.md, RESOURCE-TABLE-WAVE3AP.md (65exactanchors),
ADR-REC-C-AP-RESOURCE-CONTRACTS.md. Это не новыйnetworkcollector и не C/D/Eactivation.
База ee79093dd200595d98b0b3006e8430b2ff3b47f6/source122. Добавленытолько2sourceмодуля
ownership_resources.py/ownership_resource_catalog.py; source124/pin35114A11M.
Старые122source/units8/config/pyproject/старыеhelpers неизменны; новыйAPrunner отдельно.

AO66 принят, обаANfixturedefects закрыты actualAO, originalAN850/852непереписан.
СтарыеAO/AN/AL/AK/всеoldbatchesНЕповторять. FullAP211НАМИNOT_RUN.
Локально16узкихresource-tests/RuffPASS+2real frozenloader/checkpointtests. Никакого
full211/broadVM/kernel/services/networkпрогонаархитекторнепроводил.

ResourceContract/Requirement/Observation—immutablevalidatedtypedboundedinputs.
domains=FILES/KERNEL/API/PROCESSES/MODE/ROUTES/MARKERS;до128requirements/states,
до14observations/128charsperidentifier. Internal schema1/state identifiers,неLinuxwire.
JSON ingestion/actualcollector/trustedprovenanceNOT_IMPLEMENTED. No callbacks какsource.
Толькоsimulation origin/schema1/COMPLETE/samebinding можетMATCH. Missing/truncated/
timeout/binding/type/conflict UNKNOWN;unknownschema/actual/unbound UNSUPPORTED.
checked=actualcontiguousMATCHprefix;optionalunmatchedнеrequiredsuccess.
Aggregate сохраняетdomainsindependently; missingrequireddomain/completenessUNKNOWN
непревращаетсявMATCH. Все65catalogcontracts требуютвсе7domains/completenessUNKNOWN:
таблицаdirectcalls/domainкандидатовНЕglobalgraph/доказанныйcompleteeffectset.

Bootstrapfacts caller-supplied simulation namespace,неactualboot/code/rescueattestation.
Inventory writer_total1unknown0→WRITERS_LIVE, unknown1приunknownTotal→WRITERS_UNKNOWN+
WRITERS_UNOBSERVED. Stage/ack/rescue/originalon/graph/domainunknown блокируютdryplan.
READY_FOR_REVIEWтолькоописаниеsimulateddrydata. live_activation_authorized/repairfalse
ВСЕГДА. Facade связываетaggregate+plan:required domainfailureдобавляетdomainblocker.
runtime_verification()ВСЕГДАUNKNOWNVerification,дажеallMATCH/READYsimulation.
РеальныйproducerнеиспользуетAP; Nonelegacyunfenced/globalcompositionещёнеwired.

ВЕСЬготовыйобъёмв1worker:
|Group|Cases|Meaning|
|---|---:|---|
|C|91|7domains×13MATCH/mismatch/unknown/provenance/absence/optional branches|
|P|20|Contract/observation/state constructorpolicyrefusals|
|A|14|Aggregation,missing/conflicting/partial/optional/unsupported inputs|
|B|17|Drybootstrapready/identity/graph/domain/writer/stage/ack/rescue/refusals|
|T|65|Каждыйdeclaredsurface→7required domains+completenessUNKNOWN|
|I|4|3privateRegistryadapterrefusals+instrumentedpureconstructors/inspectwithoutos.open|

Это211cases,не211networkoperations. I_MATCH/I_ACTUAL/I_UNKNOWN выполняютdirectprivate
Registrycallback(lambdaTrue)подLIFECYCLE, facadeverifierUNKNOWN→writerUNKNOWN1/receipt0.
Этоне реальныйlifecycle/operationbody/networkproof. I_CONSTRUCTOR_IOвоfinallyвозвращает
os.openпослеpureconstructor/inspectinstrumentation;есливызовFSпопытался→FAIL.
Остальныеcasespureinmemory,никакихactors/businessbody/registrywrites. Boot/clock/UID
фикстурыsynthetic/currentowner,неrootDAC/realboot. Sourcefreeze124неinstalledattestation.

OrdinarycaseFAIL→independentcontinue;source/baseline/privacy/audit/OSError/restorefailure
globalSTOP/remainingNOT_RUN. Emptycheckpointпослеclaimпередimports,started/claim/firstcase/
finalsummaryразличать. Отказдоfirstcase→actualemptyprogressreport еслионесть;еслинет
дажеprogress→NOF3/fixedfailureвчат,неinvent211rows/flags. Не обходитьprivacy/prefix.
All7runtimeflagsfalseВСЕГДА;SourcePassнеactualprovenance/DOMAINverificationpermission.
No newthreads/workloadsubprocess/network/liveops. AcceptedADguardbeforeimports/
selfregistration+2manualprobes;trustedregressionguardНЕhostilecodesandbox.

ONLYThinkCentre/workingLAN/HEALTHYonbaseline/LANclientнет/не спрашивать. HostнеLANUDP/
IPv6/DNS/E4proof. Nooff/install/G1/newSSHinventory/WAN/LAN/TS/pin/pool/config/services/
live rules/APIwrites/nft/ip/curl/DNS/ping/SSH/scans/pcap/netns/speedtest/newunits/timers/
guardian/arm/fault. Always_offзапрещён. Independentoriginalon/code/unitrescueДОinstall/
fault;incomingoutage>1миннеfixnextcommand. Нетдажеreadonlyhost/kernel/unit/APIcollectors
вAPscope. Onlyxgwstatus/poolreadonlybookendsниже,каквстаромпротоколе;неcontinuousproof.
LiveCBLOCKED_BOOTSTRAP;realAPещёNOT_RUN. 600smonitorНЕnetworkrescue/hardrealtimebudget.

|Artifact→frozenfile|SHA256|
|---|---|
|tests/stand/wave3_resource_batch.py→batch.py|49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708|
|tests/stand/wave3_code_handshake.py→ak.py|927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55|
|tests/stand/wave3_source_hooks.py→support.py|9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
|tests/stand/wave3_resources_manifest.json→manifest.json|2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b|
|tests/stand/wave3_units_manifest.json→units.json|373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4|
|tests/stand/wave3_surface_catalog.json→surface.json|8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe|
|tests/stand/wave3_schema1_reference.py→legacy.py|2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5|


Freeze7artifacts+124source+8publicpackagingcopies700/files600,NOFOLLOW/noextras/nlink1/
owner/SHA. PackagingНИКОГДАНЕexecute/install/source;нетinstalledunitattestation.
PinnedAKonlybootstrap/sourcefixtures;егоCLI/batchesнеисполнять. Newmanifest124SHA
явноoverrideAK.MANIFEST_SHAдоbootstrap. Privatefrozen_adimports,неinstalledXGW.
OneREADY/start/auto600s5smonitor/oneSHOW+shape/afterbookends/onereport6pages/F3.
Newreport15nullablefixedfields,controlsactualcounts/7gatesfalse. Decision/status/completeness
fixedenums;privateIDs/statevalues/paths/boot/codecontexttokensнепубликовать.
PublicknowncaseIDs/domainenums/bools/counts/ms/rc/Git/publicSHA/publicrepo:lineonly.
No rawconfig/status/log/kernel/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/registryid/
privatehashes/argv/resulttexts/exceptions/screenshots. Readall6pagesbeforeONEpublication.

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
notes=Path.home()/'xgw-w3ap'
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

### S2.1. Чистаяfreepool/FF/14A+11M и publicsourceManifest

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
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/ownership_completion.py': 'A', 'src/xgw/ownership_entrypoints.py': 'A', 'src/xgw/ownership_identity.py': 'A', 'src/xgw/ownership_seal.py': 'A', 'src/xgw/ownership_surface.py': 'A', 'src/xgw/ownership_composition.py': 'A', 'src/xgw/ownership_resources.py': 'A', 'src/xgw/ownership_resource_catalog.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M', 'src/xgw/freepool/pool.py': 'M', 'src/xgw/freepool/store.py': 'M', 'src/xgw/actions.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_14A_11M')
manifest=repo/'tests/stand/wave3_resources_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==124,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_resource_batch.py').read_bytes()).hexdigest()=='49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')

for rel,frozen,digest in [('tests/stand/wave3_resource_batch.py', 'batch.py', '49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_resources_manifest.json', 'manifest.json', '2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:
    require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'ARTIFACT_SHA')
pack=json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())
require(type(pack) is dict and len(pack)==8,'PACKAGING_COUNT')
require(set(pack)=={p.relative_to(repo).as_posix() for p in (repo/'packaging').iterdir() if p.is_file()},'PACKAGING_INVENTORY')
for name,digest in pack.items():require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PACKAGING_BYTES')
require(json.loads((repo/'tests/stand/wave3_surface_catalog.json').read_bytes())['schema']==1,'SURFACE_MANIFEST')
require(git('diff','--name-only','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==['src/xgw/ownership_resource_catalog.py', 'src/xgw/ownership_resources.py'],'PRODUCT_SOURCE_CHANGED')
print('ARTIFACTS_AND_PACKAGING_MATCHED',7,8,65)

print('SOURCE_DIFF_FOURTEEN_ADD_ELEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
notes=Path.home()/'xgw-w3ap'
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

Нужныrc0/SOURCE_DIFF_FOURTEEN_ADD_ELEVEN_MODIFY/SOURCE_MANIFEST_MATCHED124/SOURCE_PREFLIGHT_OK.
ActualHEAD/treeзаписать. Dirty/mismatch/nonFF→STOP, неreset/rebase/force/install.
124sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced. Семь artifacts и восемь public packaging копий проверены отдельно, installed units не читались.

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

### S2.4. Freeze семи artifacts, 124 source и восьми packaging-копий

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3ap'
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

artifacts=[('tests/stand/wave3_resource_batch.py', 'batch.py', '49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_resources_manifest.json', 'manifest.json', '2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]
for rel,frozen,digest in artifacts:freeze(notes/frozen,(repo/rel).read_bytes(),digest)
for frozen,folder,count in [('manifest.json','source',124),('units.json','units',8)]:
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
print('RESOURCE_CONTRACTS_FROZEN',7,124,8)

PY
```

Нужен RESOURCE_CONTRACTS_FROZEN 7 124 8/rc0. Resume допускается только ДОstart с теми же байтами. Никаких chmod/install/execute для packaging. Затем обязательный S2.4b.

#### S2.4b. Exact freeze и unused перед единственным start

```bash
python3 -I -B - <<'PY'

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ap'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_resource_batch.py', 'batch.py', '49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_resources_manifest.json', 'manifest.json', '2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',124),('units.json','units',8)]:
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
print('RESOURCE_CONTRACTS_READY')

PY
```

Только RESOURCE_CONTRACTS_READY/rc0 →S3.1. Afterstarted →S3.2/S3.3, безfreeze/start/worker повторно.

## 5. S3 — 211 проверок одного source-пакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ap/batch.py" start
```

НужныRESOURCE_CONTRACTS_BATCH_STARTED/rc0. Это Popencollector, не211PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AI78/AG129/AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до600с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ap/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ap/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
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
expected=['C_API_MATCH', 'C_API_MISMATCH', 'C_API_MISSING', 'C_API_TIMEOUT', 'C_API_TRUNCATED', 'C_API_SCHEMA', 'C_API_BINDING', 'C_API_ACTUAL', 'C_API_UNBOUND', 'C_API_DUPLICATE', 'C_API_ABSENCE_BAD', 'C_API_ABSENCE_OK', 'C_API_OPTIONAL', 'C_FILES_MATCH', 'C_FILES_MISMATCH', 'C_FILES_MISSING', 'C_FILES_TIMEOUT', 'C_FILES_TRUNCATED', 'C_FILES_SCHEMA', 'C_FILES_BINDING', 'C_FILES_ACTUAL', 'C_FILES_UNBOUND', 'C_FILES_DUPLICATE', 'C_FILES_ABSENCE_BAD', 'C_FILES_ABSENCE_OK', 'C_FILES_OPTIONAL', 'C_KERNEL_MATCH', 'C_KERNEL_MISMATCH', 'C_KERNEL_MISSING', 'C_KERNEL_TIMEOUT', 'C_KERNEL_TRUNCATED', 'C_KERNEL_SCHEMA', 'C_KERNEL_BINDING', 'C_KERNEL_ACTUAL', 'C_KERNEL_UNBOUND', 'C_KERNEL_DUPLICATE', 'C_KERNEL_ABSENCE_BAD', 'C_KERNEL_ABSENCE_OK', 'C_KERNEL_OPTIONAL', 'C_MARKERS_MATCH', 'C_MARKERS_MISMATCH', 'C_MARKERS_MISSING', 'C_MARKERS_TIMEOUT', 'C_MARKERS_TRUNCATED', 'C_MARKERS_SCHEMA', 'C_MARKERS_BINDING', 'C_MARKERS_ACTUAL', 'C_MARKERS_UNBOUND', 'C_MARKERS_DUPLICATE', 'C_MARKERS_ABSENCE_BAD', 'C_MARKERS_ABSENCE_OK', 'C_MARKERS_OPTIONAL', 'C_MODE_MATCH', 'C_MODE_MISMATCH', 'C_MODE_MISSING', 'C_MODE_TIMEOUT', 'C_MODE_TRUNCATED', 'C_MODE_SCHEMA', 'C_MODE_BINDING', 'C_MODE_ACTUAL', 'C_MODE_UNBOUND', 'C_MODE_DUPLICATE', 'C_MODE_ABSENCE_BAD', 'C_MODE_ABSENCE_OK', 'C_MODE_OPTIONAL', 'C_PROCESSES_MATCH', 'C_PROCESSES_MISMATCH', 'C_PROCESSES_MISSING', 'C_PROCESSES_TIMEOUT', 'C_PROCESSES_TRUNCATED', 'C_PROCESSES_SCHEMA', 'C_PROCESSES_BINDING', 'C_PROCESSES_ACTUAL', 'C_PROCESSES_UNBOUND', 'C_PROCESSES_DUPLICATE', 'C_PROCESSES_ABSENCE_BAD', 'C_PROCESSES_ABSENCE_OK', 'C_PROCESSES_OPTIONAL', 'C_ROUTES_MATCH', 'C_ROUTES_MISMATCH', 'C_ROUTES_MISSING', 'C_ROUTES_TIMEOUT', 'C_ROUTES_TRUNCATED', 'C_ROUTES_SCHEMA', 'C_ROUTES_BINDING', 'C_ROUTES_ACTUAL', 'C_ROUTES_UNBOUND', 'C_ROUTES_DUPLICATE', 'C_ROUTES_ABSENCE_BAD', 'C_ROUTES_ABSENCE_OK', 'C_ROUTES_OPTIONAL', 'P_DOMAIN', 'P_ID', 'P_EXPECTED', 'P_BOOL_REQUIRED', 'P_BOOL_ABSENT', 'P_EMPTY', 'P_LIST', 'P_MANY', 'P_DUPLICATE', 'P_OPTIONAL_ONLY', 'P_BINDING', 'P_COMPLETENESS', 'P_OBS_LIST', 'P_OBS_MANY', 'P_OBS_TYPE', 'P_SCHEMA_BOOL', 'P_STATUS', 'P_SIM_BOOL', 'P_ORIGIN', 'P_STATE_TYPE', 'A_ALL', 'A_MISSING', 'A_CONFLICT', 'A_WRONGTYPE', 'A_MISMATCH', 'A_ACTUAL', 'A_SCHEMA', 'A_BINDING', 'A_INCOMPLETE', 'A_OPTIONAL', 'A_EXTRA', 'A_LIMIT', 'A_EMPTY', 'A_MIXED', 'B_READY', 'B_NO_FACTS', 'B_CODE', 'B_CALLER', 'B_ACTUAL', 'B_LIVE', 'B_UNKNOWN_WRITER', 'B_BOTH_WRITERS', 'B_COUNTS_NONE', 'B_COUNTS_PARTIAL', 'B_STAGE', 'B_ACK', 'B_GRAPH', 'B_RESCUE', 'B_ORIGINAL_ON', 'B_FACT_DUP', 'B_COUNTS_BAD', 'T_00', 'T_01', 'T_02', 'T_03', 'T_04', 'T_05', 'T_06', 'T_07', 'T_08', 'T_09', 'T_10', 'T_11', 'T_12', 'T_13', 'T_14', 'T_15', 'T_16', 'T_17', 'T_18', 'T_19', 'T_20', 'T_21', 'T_22', 'T_23', 'T_24', 'T_25', 'T_26', 'T_27', 'T_28', 'T_29', 'T_30', 'T_31', 'T_32', 'T_33', 'T_34', 'T_35', 'T_36', 'T_37', 'T_38', 'T_39', 'T_40', 'T_41', 'T_42', 'T_43', 'T_44', 'T_45', 'T_46', 'T_47', 'T_48', 'T_49', 'T_50', 'T_51', 'T_52', 'T_53', 'T_54', 'T_55', 'T_56', 'T_57', 'T_58', 'T_59', 'T_60', 'T_61', 'T_62', 'T_63', 'T_64', 'I_MATCH', 'I_ACTUAL', 'I_UNKNOWN', 'I_CONSTRUCTOR_IO']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','unit_files','declared_surfaces','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='SIMULATED_RESOURCE_CONTRACTS_AND_DRY_BOOTSTRAP_ONLY' and data.get('expected')==211
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==211-len(rows) and len(rows)<=211 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='RESOURCE_CONTRACTS_BATCH_RECORDED' and data.get('completed')==211
      and data.get('passed')==211 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==124 and data.get('unit_files')==8 and data.get('declared_surfaces')==65 and data.get('remaining_not_run')==0
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
python3 -I -B "$HOME/xgw-w3ap/batch.py" report
```

Нужны RESOURCE_CONTRACTS_REPORT_READY/rc0. Это НЕновыйworker/неPASS. Выбирает finalsummary,
илиprogress при отсутствииsummary; всеactualполя/nulls/точныеms проходятwhitelist.
Создаёт EXCL report-record.json (sanitizedprivatecheckpoint) иreport-data.md.
Snapshot сохраняет именно прочитанныйprefix даже при последующемprogress; не подменять
его новойsummary. Повторreport разрешён только как readonlydeterministicverification
этогоsnapshot, НЕповторstart. Unknownfields/privacy/typeerror→STOPreport; не обходить.
Если ниsummaryниprogress нет, AH-stylepartialfailure: NOT_COLLECTED/remainingNOT_RUN;
не выполнятьS4.4/S4.5/F3/не выдумывать211rows. Сообщитьsafe fixedfailure иactualrc.

### S4.4. Прочитать весь обезличенный Markdown

```bash
python3 -I -B - <<'PY'
from pathlib import Path
lines=(Path.home()/'xgw-w3ap/report-data.md').read_text(encoding='utf-8').splitlines()
if len(lines)>240:raise SystemExit('STOP_UNEXPECTED_REPORT_LENGTH')
print('SANITIZED_REPORT_LINES',len(lines))
PY
```

Прочитать все строки, включая failed/nullable. Не ручнойперенос/округление/~N/подстановка
ожиданий. ДанныеALL_CASES_PASSED вS3.3 не заменяют actualcases. Не catcasefiles/config/
registry/fingerprints/logs/receipt/rawexceptions. Не публиковать rawstatus/screenshots.


Ниже6обязательныхстраниц по40строк, читатьвсе;пустойpartialхвостдопустим.

#### S4.4a. Строки 1–40

```bash
sed -n '1,40p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

#### S4.4b. Строки 41–80

```bash
sed -n '41,80p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

#### S4.4c. Строки 81–120

```bash
sed -n '81,120p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

#### S4.4d. Строки 121–160

```bash
sed -n '121,160p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

#### S4.4e. Строки 161–200

```bash
sed -n '161,200p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

#### S4.4f. Строки 201–240

```bash
sed -n '201,240p' "$HOME/xgw-w3ap/report-data.md"
```

Нуженrc0;таблицу/prefix не редактировать.

### S4.5. Создать draft с неизменным automatic prefix

```bash
python3 -I -B - <<'PY'
import os
from pathlib import Path
notes=Path.home()/'xgw-w3ap';repo=Path.home()/'zcod/xgw'
prefix=(notes/'report-data.md').read_bytes()
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ap-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(prefix+footer)
print('AP_DRAFT_CREATED')
PY
```

НуженAP_DRAFT_CREATED/rc0. Заполнить ТОЛЬКОfooterJSON послеAP_EXECUTION пофактически
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
advancingprogress не меняет snapshot. Поля decision/checked/required/optional/missing/blockers/simulation/authorization/
verification/receipt/writer/completeness/dryready nullable и whitelisted. MATCH и
READY_FOR_REVIEW относятсяТОЛЬКОsimulation/drydata, неruntimeactivation.
Автотаблицу не редактировать/не округлять. ReadallMarkdownbeforeonepublish.

PubliconlyknownIDs/enums/bools/counts/exactms/commandrc/Git/publicsourceSHA/publicrepo:line.
No rawconfig/status/log/kernel/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryid/
tokens/privatehashes/argv/resulttexts/exceptions/screenshots. Baselineнаблюдения отдельно
отcaseданных. Installedkernel/SQLtransaction/LANUDP/IPv6/DNS/E4/performance/allTS неPASS.
Source/globalgates и bootstrap долг сохраняются. ТолькоThinkCentre, сеть не менять.

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый APreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3ap'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(git('diff','--name-only','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==['src/xgw/ownership_resource_catalog.py', 'src/xgw/ownership_resources.py'],'PRODUCT_SOURCE_CHANGED')
for rel,frozen,digest in [('tests/stand/wave3_resource_batch.py', 'batch.py', '49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_resources_manifest.json', 'manifest.json', '2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AP_SOURCE_SHA')
for name,digest in {**json.loads((repo/'tests/stand/wave3_resources_manifest.json').read_bytes()),**json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())}.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ap'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_resource_batch.py', 'batch.py', '49c44421ec1b5e7464b14751151ccb82890b9fb0dd6abf18be7573865b948708'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_resources_manifest.json', 'manifest.json', '2abae55ab23815f156bc4628c10d2290fbb02402f175aaf5eda877139b703d9b'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',124),('units.json','units',8)]:
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
require(proc.returncode==0 and proc.stdout.strip()=='RESOURCE_CONTRACTS_REPORT_READY','REPORT_SNAPSHOT_CHANGED')
preview=(notes/'report-data.md').read_bytes();draft=(notes/'report.md').read_bytes()
require(draft.startswith(preview),'AUTOMATIC_PREFIX_CHANGED')
tail=draft[len(preview):].decode('utf-8')
require(tail.startswith('\n<!-- AP_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ap-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AP start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3ap — code-bound writer and FILES composition')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AL/AK/AJ/AI/AH/AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. APreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
