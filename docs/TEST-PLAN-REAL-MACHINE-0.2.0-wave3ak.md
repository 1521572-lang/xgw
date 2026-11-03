# ТЗ Flash: wave3ak — 437 новых проверок одним запуском

04.11.2026. Максимальный ГОТОВЫЙ объём за один заход: четыре независимых блока,
437 новых cases, один start, автоматическое продолжение, один итоговый report.
На109 cases/33,2% больше AJ328. Нет старых batch reruns или искусственного ожидания.

## 1. Принятый AJ и границы этого задания

AJreport63c9c413930eb348d46b2ff986bef46dd2e423d4 принят:328/328/summary,
CODE_HANDSHAKE ещё не выполнялся. AJ marker LIFECYCLE_FLOW_BATCH_RECORDED, batch71180мс,
суммаcaseelapsed59282мс. Это разные метрики. 82LEGACY/82OWNED(65COMPLETED17UNKNOWN)/
82FENCED, B36/C22/D24; C19UNKNOWN3preadmission, D4positive19UNKNOWN1fenced.
Публичный prefix восстановлен pinned pure formatter байт-в-байт. Tested446e0efe0fa37f495d9b4e3059bf3dff5830af08,
treec91195c0b904bb8019dd682887f1a6a15c00c764. HEALTHY_ON/poolOFF/linkALIVE/versionssame/
owneractions0/NNP0/sudo0/start0/monitor0/show0/report0. WorkerexitNOT_COLLECTED.
Все7runtimegatesfalse. AJ328/AI78/AG129/AF145/AE112/AD130/AC51/... и AH386 не повторять.

ТОЛЬКОThinkCentre, LAN-клиента нет/не спрашивать. WorkingLAN/HEALTHY/on baseline.
Host не LAN UDP/IPv6/DNS/E4 proof. No off/install/G1/newSSHinventory/WAN/LAN/TS/pin/
pool/config/service/live rules/API writes/nft/ip/curl/SOCKS/DNS/ping/SSH/scans/pcap/
netns/speedtest/coreversion/newunits/timers/guardian/arm/replay/fault. Always_off запрещён.
До install/fault нужен independent original-on/code/unit rescue. Incoming outage>1мин
следующей командой модели не исправить. AK НЕ разрешает C/D/E/runtime activation.

## 2. Подготовленный код и точная интерпретация

Pin351fb54e074f4a7b497a8a4244fc74c6088788d7:11A11M/121source.
Против AJ ровно3A(ownership_identity/seal/surface.py)+2M(ownership.py/diagnostics.py).
Остальные116 source, packaging8/config/pyproject/старые helpers и manifests UNCHANGED.
Installedruntime не обновлялся и здесь не устанавливается. Source121 ≠ installed121.

Registry(code_identity=None) сохраняет schema1/старые state/token/summary без миграции.
Явный exact CodeIdentity включает protocol2 и три digest source/units/declaredsurface.
Schema2 атомарно хранит code record в том же state.json/state.next, token содержит digest.
Different code/schema/boot/context отказывает до операции; retainedreceipt не исключение.
Нет implicit upgrade/downgrade/repair/перезаписи старого registry. Это cooperative namespace:
caller всё ещё может неверно объявить digest или игнорировать preflight. НЕ global handshake.
Legacyref — байт-в-байт public ownership.py@63c9, загружается отдельным модулем, не installed.
Шесть bridge cases проверяют объекты в одном процессе, НЕ IPC/rollout/boot compatibility.

CodeSeal readonly: explicit absolute root/owner/1–256 paths/modes/SHA, exact full inventory;
NOFOLLOW anchored traversal, regular/nlink1/owner/mode,2MiB/file16MiBtotal/metadata+hash,
root+dir identity rechecks. FIFO не блокирует, symlink/hardlink/extras/drift отказываются.
Ancestors NOFOLLOW, но не полная ancestorDAC/mount policy. Sequential reads не atomic
multi-file snapshot. checked — подтверждённый prefix, не full PASS. Нет chmod/install/repair.

SurfaceCatalog проверяет65declared surfaces (50actor methods+15lifecycle) без actor/body calls.
Закреплены function/code/wrappers/defaults/function-default code/closure references/signature,
role/dependency metadata/bindingtable identities. Не arbitrary moduleglobals/fullcallgraph/
malicious-code sandbox. Surface failure checked0 не означает конкретный пройденный prefix.
CodePreflight заново читает source+units+surface, сохраняет independent partial booleans/
counts/nulls; no cachedPASS. Ordinary mismatch не отменяет другие наблюдения. Contextdrift/
providerexception → PREFLIGHT_REFUSED с фактически собранным prefix. Evidence НЕ Verification,
не lease/repair/activation. CodeIdentity seal digests включают path/mode/SHA и отличаются
от SHA сырых manifest.json/units.json; surface.json canonicalbytes SHA совпадает surface digest.

| Artifact → private frozen file | SHA256 |
|---|---|
|tests/stand/wave3_code_handshake.py → batch.py|927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55|
|tests/stand/wave3_source_hooks.py → support.py|9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
|tests/stand/wave3_code_manifest.json → manifest.json|d83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13|
|tests/stand/wave3_units_manifest.json → units.json|373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4|
|tests/stand/wave3_surface_catalog.json → surface.json|8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe|
|tests/stand/wave3_schema1_reference.py → legacy.py|2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5|

Freeze6+121source+8packaging в~/xgw-w3ak0700; files0600/dirs0700. Packaging только
public copies, не installed unit attestation и НИКОГДА не execute/install/source shell.
Unchanged ADsupport только fixtures/loader/accepted auditguard ДО sourceimports; старыеCLI/
batches не вызывать. Privatefrozen_ad imports real source __init__, без installedXGW.
Constructor I/O нет; registry boot/clock synthetic/expectedUID текущегоowner, не rootDAC.
Dummy product files600/640/644 разрешены внутри700; не chmod product радиPASS.

| Блок | Cases | Содержимое |
|---|---:|---|
| A |225|24identity/120operations×mismatch/21role×outcome/4legacyshape/36badtoken/14stage/6oldcodebridge|
| B |50|16constructor refusals/24file-tree scenarios/8contextdrift/2full frozen inventories|
| C |146|65surfaces×shadow/role=130 и16code/default/closure/signature/dependency/table cases|
| D |16|combined fresh preflight, independentpartial/prefix, provider/contextdrift, schema2 admission/filecompletion/full build|

A21positive completions — private registry receipts, не network applies. J_SAME только
STAGE_VALID_UNPROVEN, не recovery/repair; остальные13refused/unrelated. Любой stage
оставляет admit INTERRUPTED_COMMIT; diagnostic сохраняется отдельно от последнего refusal.
BRIDGE read positives только schema1 bookkeep. I_WRITER_FENCE получает один PANEL file
receipt после private fileverification; ранний lease отказывает пока writerLIVE, не45sproof.
code_bound=true означает только исходный частный schema2registry; не peer accepted,
не runtime fence. Если summary заблокирована, generation/counters могут быть null.
Данные не подставлять из имен cases. NegativecasePASS не ExecutionCOMPLETED.

Ordinary caseFAIL → следующие independent cases автоматически. UnexpectedOSError/
ScopeStop/audit/source/baseline/privacy →globalSTOP/remainingNOT_RUN. Частичные details
16whitelistedfields сохраняются, отсутствующее null не0. Никаких новых threads/workload
subprocess/network/liveops. All7flagsfalse всегда. Accepted guard — trustedregressionguard,
НЕhostilecode sandbox; coarse dirfd limitations прежние. Readrecord bounded512KiB только
новые progress/summary/report-record, старый support unchanged. Нет rawexceptions/paths/
privatehashes/argv/registryids в public report. Ошибка — whitelist class/publicrepo:line.

Локально19узкихtests/RuffPASS: schema1shape/schema2tokens/context/privatefiles/surface/
partialpreflight плюс8representative helper contracts и большой JSON/duplicate-key read.
Полный437/реальныйThinkCentre/
oldbatches/broadVM/kernel/services/network нами NOT_RUN. Полный AK выполняет Flash.

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
notes=Path.home()/'xgw-w3ak'
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

### S2.1. Чистаяfreepool/FF/11A+11M и publicsourceManifest

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
git('merge-base','--is-ancestor','63c9c413930eb348d46b2ff986bef46dd2e423d4','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/ownership_completion.py': 'A', 'src/xgw/ownership_entrypoints.py': 'A', 'src/xgw/ownership_identity.py': 'A', 'src/xgw/ownership_seal.py': 'A', 'src/xgw/ownership_surface.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M', 'src/xgw/freepool/pool.py': 'M', 'src/xgw/freepool/store.py': 'M', 'src/xgw/actions.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_11A_11M')
manifest=repo/'tests/stand/wave3_code_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='d83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==121,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_code_handshake.py').read_bytes()).hexdigest()=='927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')

for rel,frozen,digest in [('tests/stand/wave3_code_handshake.py', 'batch.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:
    require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'ARTIFACT_SHA')
pack=json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())
require(type(pack) is dict and len(pack)==8,'PACKAGING_COUNT')
require(set(pack)=={p.relative_to(repo).as_posix() for p in (repo/'packaging').iterdir() if p.is_file()},'PACKAGING_INVENTORY')
for name,digest in pack.items():require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PACKAGING_BYTES')
require(json.loads((repo/'tests/stand/wave3_surface_catalog.json').read_bytes())['schema']==1,'SURFACE_MANIFEST')
print('ARTIFACTS_AND_PACKAGING_MATCHED',6,8,65)

print('SOURCE_DIFF_ELEVEN_ADD_ELEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
notes=Path.home()/'xgw-w3ak'
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

Нужныrc0/SOURCE_DIFF_ELEVEN_ADD_ELEVEN_MODIFY/SOURCE_MANIFEST_MATCHED121/SOURCE_PREFLIGHT_OK.
ActualHEAD/treeзаписать. Dirty/mismatch/nonFF→STOP, неreset/rebase/force/install.
121sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced. Шесть artifacts и восемь public packaging копий проверены отдельно, installed units не читались.

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

### S2.4. Freeze шести artifacts, 121 source и восьми packaging-копий

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3ak'
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

artifacts=[('tests/stand/wave3_code_handshake.py', 'batch.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]
for rel,frozen,digest in artifacts:freeze(notes/frozen,(repo/rel).read_bytes(),digest)
for frozen,folder,count in [('manifest.json','source',121),('units.json','units',8)]:
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
print('CODE_HANDSHAKE_FROZEN',6,121,8)

PY
```

Нужен CODE_HANDSHAKE_FROZEN 6 121 8/rc0. Resume допускается только ДОstart с теми же байтами. Никаких chmod/install/execute для packaging. Затем обязательный S2.4b.

#### S2.4b. Exact freeze и unused перед единственным start

```bash
python3 -I -B - <<'PY'

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ak'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_code_handshake.py', 'batch.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',121),('units.json','units',8)]:
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
print('CODE_HANDSHAKE_READY')

PY
```

Только CODE_HANDSHAKE_READY/rc0 →S3.1. Afterstarted →S3.2/S3.3, безfreeze/start/worker повторно.

## 5. S3 — 437 проверок одного source-пакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ak/batch.py" start
```

НужныCODE_HANDSHAKE_BATCH_STARTED/rc0. Это Popencollector, не437PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AI78/AG129/AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ak/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ak/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['A_source_sha256__TYPE', 'A_source_sha256__SHORT', 'A_source_sha256__UPPER', 'A_source_sha256__NONHEX', 'A_source_sha256__EMPTY', 'A_units_sha256__TYPE', 'A_units_sha256__SHORT', 'A_units_sha256__UPPER', 'A_units_sha256__NONHEX', 'A_units_sha256__EMPTY', 'A_surface_sha256__TYPE', 'A_surface_sha256__SHORT', 'A_surface_sha256__UPPER', 'A_surface_sha256__NONHEX', 'A_surface_sha256__EMPTY', 'A_PROTOCOL_BOOL', 'A_PROTOCOL_ONE', 'A_PROTOCOL_THREE', 'A_PROTOCOL_TEXT', 'A_PROTOCOL_FLOAT', 'A_OBJECT', 'A_SUBCLASS', 'A_VALID', 'A_CANONICAL', 'R_ADMIT__SOURCE', 'R_ADMIT__UNITS', 'R_ADMIT__SURFACE', 'R_ADMIT__LEGACY', 'R_ADMIT__OLD_STORE', 'R_ADMIT__MISSING', 'R_ADMIT__EXTRA', 'R_ADMIT__PROTOCOL', 'R_ADMIT__BOOL_SCHEMA', 'R_ADMIT__TYPE', 'R_ADMIT__CONTEXT', 'R_ADMIT__BOOT', 'R_COMPLETE__SOURCE', 'R_COMPLETE__UNITS', 'R_COMPLETE__SURFACE', 'R_COMPLETE__LEGACY', 'R_COMPLETE__OLD_STORE', 'R_COMPLETE__MISSING', 'R_COMPLETE__EXTRA', 'R_COMPLETE__PROTOCOL', 'R_COMPLETE__BOOL_SCHEMA', 'R_COMPLETE__TYPE', 'R_COMPLETE__CONTEXT', 'R_COMPLETE__BOOT', 'R_UNKNOWN__SOURCE', 'R_UNKNOWN__UNITS', 'R_UNKNOWN__SURFACE', 'R_UNKNOWN__LEGACY', 'R_UNKNOWN__OLD_STORE', 'R_UNKNOWN__MISSING', 'R_UNKNOWN__EXTRA', 'R_UNKNOWN__PROTOCOL', 'R_UNKNOWN__BOOL_SCHEMA', 'R_UNKNOWN__TYPE', 'R_UNKNOWN__CONTEXT', 'R_UNKNOWN__BOOT', 'R_RECEIPT__SOURCE', 'R_RECEIPT__UNITS', 'R_RECEIPT__SURFACE', 'R_RECEIPT__LEGACY', 'R_RECEIPT__OLD_STORE', 'R_RECEIPT__MISSING', 'R_RECEIPT__EXTRA', 'R_RECEIPT__PROTOCOL', 'R_RECEIPT__BOOL_SCHEMA', 'R_RECEIPT__TYPE', 'R_RECEIPT__CONTEXT', 'R_RECEIPT__BOOT', 'R_ACQUIRE__SOURCE', 'R_ACQUIRE__UNITS', 'R_ACQUIRE__SURFACE', 'R_ACQUIRE__LEGACY', 'R_ACQUIRE__OLD_STORE', 'R_ACQUIRE__MISSING', 'R_ACQUIRE__EXTRA', 'R_ACQUIRE__PROTOCOL', 'R_ACQUIRE__BOOL_SCHEMA', 'R_ACQUIRE__TYPE', 'R_ACQUIRE__CONTEXT', 'R_ACQUIRE__BOOT', 'R_BEGIN__SOURCE', 'R_BEGIN__UNITS', 'R_BEGIN__SURFACE', 'R_BEGIN__LEGACY', 'R_BEGIN__OLD_STORE', 'R_BEGIN__MISSING', 'R_BEGIN__EXTRA', 'R_BEGIN__PROTOCOL', 'R_BEGIN__BOOL_SCHEMA', 'R_BEGIN__TYPE', 'R_BEGIN__CONTEXT', 'R_BEGIN__BOOT', 'R_UNUSED__SOURCE', 'R_UNUSED__UNITS', 'R_UNUSED__SURFACE', 'R_UNUSED__LEGACY', 'R_UNUSED__OLD_STORE', 'R_UNUSED__MISSING', 'R_UNUSED__EXTRA', 'R_UNUSED__PROTOCOL', 'R_UNUSED__BOOL_SCHEMA', 'R_UNUSED__TYPE', 'R_UNUSED__CONTEXT', 'R_UNUSED__BOOT', 'R_RESTORED__SOURCE', 'R_RESTORED__UNITS', 'R_RESTORED__SURFACE', 'R_RESTORED__LEGACY', 'R_RESTORED__OLD_STORE', 'R_RESTORED__MISSING', 'R_RESTORED__EXTRA', 'R_RESTORED__PROTOCOL', 'R_RESTORED__BOOL_SCHEMA', 'R_RESTORED__TYPE', 'R_RESTORED__CONTEXT', 'R_RESTORED__BOOT', 'R_SUMMARY__SOURCE', 'R_SUMMARY__UNITS', 'R_SUMMARY__SURFACE', 'R_SUMMARY__LEGACY', 'R_SUMMARY__OLD_STORE', 'R_SUMMARY__MISSING', 'R_SUMMARY__EXTRA', 'R_SUMMARY__PROTOCOL', 'R_SUMMARY__BOOL_SCHEMA', 'R_SUMMARY__TYPE', 'R_SUMMARY__CONTEXT', 'R_SUMMARY__BOOT', 'R_DIAGNOSTIC__SOURCE', 'R_DIAGNOSTIC__UNITS', 'R_DIAGNOSTIC__SURFACE', 'R_DIAGNOSTIC__LEGACY', 'R_DIAGNOSTIC__OLD_STORE', 'R_DIAGNOSTIC__MISSING', 'R_DIAGNOSTIC__EXTRA', 'R_DIAGNOSTIC__PROTOCOL', 'R_DIAGNOSTIC__BOOL_SCHEMA', 'R_DIAGNOSTIC__TYPE', 'R_DIAGNOSTIC__CONTEXT', 'R_DIAGNOSTIC__BOOT', 'W_CAPTURE__COMMITTED', 'W_CAPTURE__NOOP', 'W_CAPTURE__ROLLED_BACK', 'W_PANEL__COMMITTED', 'W_PANEL__NOOP', 'W_PANEL__ROLLED_BACK', 'W_PEERS__COMMITTED', 'W_PEERS__NOOP', 'W_PEERS__ROLLED_BACK', 'W_CORE__COMMITTED', 'W_CORE__NOOP', 'W_CORE__ROLLED_BACK', 'W_API__COMMITTED', 'W_API__NOOP', 'W_API__ROLLED_BACK', 'W_TUN_HOOK__COMMITTED', 'W_TUN_HOOK__NOOP', 'W_TUN_HOOK__ROLLED_BACK', 'W_LIFECYCLE__COMMITTED', 'W_LIFECYCLE__NOOP', 'W_LIFECYCLE__ROLLED_BACK', 'L_STATE', 'L_WRITER', 'L_RECOVERY', 'L_SUMMARY', 'T_COMPLETE__DIGEST', 'T_COMPLETE__MISSING', 'T_COMPLETE__EXTRA', 'T_COMPLETE__BOOL', 'T_COMPLETE__REGISTRY', 'T_COMPLETE__BOOT', 'T_UNKNOWN__DIGEST', 'T_UNKNOWN__MISSING', 'T_UNKNOWN__EXTRA', 'T_UNKNOWN__BOOL', 'T_UNKNOWN__REGISTRY', 'T_UNKNOWN__BOOT', 'T_RECEIPT__DIGEST', 'T_RECEIPT__MISSING', 'T_RECEIPT__EXTRA', 'T_RECEIPT__BOOL', 'T_RECEIPT__REGISTRY', 'T_RECEIPT__BOOT', 'T_BEGIN__DIGEST', 'T_BEGIN__MISSING', 'T_BEGIN__EXTRA', 'T_BEGIN__BOOL', 'T_BEGIN__REGISTRY', 'T_BEGIN__BOOT', 'T_UNUSED__DIGEST', 'T_UNUSED__MISSING', 'T_UNUSED__EXTRA', 'T_UNUSED__BOOL', 'T_UNUSED__REGISTRY', 'T_UNUSED__BOOT', 'T_RESTORED__DIGEST', 'T_RESTORED__MISSING', 'T_RESTORED__EXTRA', 'T_RESTORED__BOOL', 'T_RESTORED__REGISTRY', 'T_RESTORED__BOOT', 'J_SAME', 'J_SOURCE', 'J_UNITS', 'J_SURFACE', 'J_PROTOCOL', 'J_LEGACY', 'J_MISSING', 'J_EXTRA', 'J_BAD_SHA', 'J_TRUNCATED', 'J_DUPLICATE', 'J_SYMLINK', 'J_REVISION', 'J_BOOT', 'BRIDGE_OLD_V2_ADMIT', 'BRIDGE_OLD_V2_SUMMARY', 'BRIDGE_OLD_V2_COMPLETE', 'BRIDGE_OLD_V2_BEGIN', 'BRIDGE_OLD_V1_READ_NEW', 'BRIDGE_NEW_V1_READ_OLD', 'P_RELATIVE', 'P_ANCHOR', 'P_PARENT', 'P_UID_BOOL', 'P_UID_NEGATIVE', 'P_EMPTY', 'P_LIST', 'P_OVER_LIMIT', 'P_TYPE', 'P_TRAVERSAL', 'P_ABSOLUTE', 'P_DUPLICATE', 'P_COLLISION', 'P_BAD_HASH', 'P_BOOL_MODE', 'P_WRITABLE', 'F_PRESENT', 'F_PUBLIC_DIR', 'F_PUBLIC_FILE', 'F_NESTED', 'F_EMPTY', 'F_MISSING', 'F_EXTRA_FILE', 'F_EXTRA_DIR', 'F_CONTENT', 'F_MODE', 'F_ROOT_MODE', 'F_CHILD_MODE', 'F_OWNER', 'F_HARDLINK', 'F_SYMLINK', 'F_PARENT_SYMLINK', 'F_ROOT_SYMLINK', 'F_FIFO', 'F_OVERSIZE', 'F_TOTAL_SIZE', 'F_DIRECTORY', 'F_DANGLING', 'F_MAX_FILES', 'F_TOO_DEEP', 'K_ROOT', 'K_UID', 'K_EXPECTATIONS', 'K_MANIFEST', 'K_READ', 'K_DIRECTORY', 'K_PID', 'K_THREAD', 'FULL_SOURCE', 'FULL_UNITS', 'S_actions.apply_network__SHADOW', 'S_actions.apply_network__ROLE', 'S_actions.disable__SHADOW', 'S_actions.disable__ROLE', 'S_actions.enable__SHADOW', 'S_actions.enable__ROLE', 'S_actions.enable_checked__SHADOW', 'S_actions.enable_checked__ROLE', 'S_actions.house_after_boot__SHADOW', 'S_actions.house_after_boot__ROLE', 'S_actions.pin__SHADOW', 'S_actions.pin__ROLE', 'S_actions.set_core__SHADOW', 'S_actions.set_core__ROLE', 'S_actions.set_pool_mode__SHADOW', 'S_actions.set_pool_mode__ROLE', 'S_actions.set_pool_pin__SHADOW', 'S_actions.set_pool_pin__ROLE', 'S_actions.unpin__SHADOW', 'S_actions.unpin__ROLE', 'S_api.add_inbounds__SHADOW', 'S_api.add_inbounds__ROLE', 'S_api.add_outbounds__SHADOW', 'S_api.add_outbounds__ROLE', 'S_api.pin__SHADOW', 'S_api.pin__ROLE', 'S_api.remove_inbound__SHADOW', 'S_api.remove_inbound__ROLE', 'S_api.remove_outbound__SHADOW', 'S_api.remove_outbound__ROLE', 'S_api.replace_routing__SHADOW', 'S_api.replace_routing__ROLE', 'S_api.unpin__SHADOW', 'S_api.unpin__ROLE', 'S_capture._load__SHADOW', 'S_capture._load__ROLE', 'S_capture._save__SHADOW', 'S_capture._save__ROLE', 'S_capture.close__SHADOW', 'S_capture.close__ROLE', 'S_capture.disable__SHADOW', 'S_capture.disable__ROLE', 'S_capture.down__SHADOW', 'S_capture.down__ROLE', 'S_capture.enable__SHADOW', 'S_capture.enable__ROLE', 'S_capture.open__SHADOW', 'S_capture.open__ROLE', 'S_capture.restore_tun__SHADOW', 'S_capture.restore_tun__ROLE', 'S_capture.tailscale_direct__SHADOW', 'S_capture.tailscale_direct__ROLE', 'S_capture.tailscale_fallback__SHADOW', 'S_capture.tailscale_fallback__ROLE', 'S_capture.tidy__SHADOW', 'S_capture.tidy__ROLE', 'S_capture.up__SHADOW', 'S_capture.up__ROLE', 'S_cores._event__SHADOW', 'S_cores._event__ROLE', 'S_cores._reject__SHADOW', 'S_cores._reject__ROLE', 'S_cores._save__SHADOW', 'S_cores._save__ROLE', 'S_cores._stage__SHADOW', 'S_cores._stage__ROLE', 'S_cores.rollback__SHADOW', 'S_cores.rollback__ROLE', 'S_cores.run__SHADOW', 'S_cores.run__ROLE', 'S_cores.update__SHADOW', 'S_cores.update__ROLE', 'S_engine._save_fingerprints__SHADOW', 'S_engine._save_fingerprints__ROLE', 'S_engine.apply_all__SHADOW', 'S_engine.apply_all__ROLE', 'S_engine.collect__SHADOW', 'S_engine.collect__ROLE', 'S_engine.persist__SHADOW', 'S_engine.persist__ROLE', 'S_engine.save_inventory__SHADOW', 'S_engine.save_inventory__ROLE', 'S_panel.update__SHADOW', 'S_panel.update__ROLE', 'S_peers._nft_element__SHADOW', 'S_peers._nft_element__ROLE', 'S_peers._save_peers__SHADOW', 'S_peers._save_peers__ROLE', 'S_peers.prepare__SHADOW', 'S_peers.prepare__ROLE', 'S_peers.reconcile__SHADOW', 'S_peers.reconcile__ROLE', 'S_peers.stop__SHADOW', 'S_peers.stop__ROLE', 'S_pool._check_proxy__SHADOW', 'S_pool._check_proxy__ROLE', 'S_pool._note_handshake__SHADOW', 'S_pool._note_handshake__ROLE', 'S_pool._prune_candidates__SHADOW', 'S_pool._prune_candidates__ROLE', 'S_pool._prune_retired__SHADOW', 'S_pool._prune_retired__ROLE', 'S_pool._record__SHADOW', 'S_pool._record__ROLE', 'S_pool.check_some__SHADOW', 'S_pool.check_some__ROLE', 'S_pool.refresh_backend__SHADOW', 'S_pool.refresh_backend__ROLE', 'S_pool.refresh_due__SHADOW', 'S_pool.refresh_due__ROLE', 'S_pool_store._ensure__SHADOW', 'S_pool_store._ensure__ROLE', 'S_pool_store.commit__SHADOW', 'S_pool_store.commit__ROLE', 'S_pool_store.prune__SHADOW', 'S_pool_store.prune__ROLE', 'S_pool_store.retire_openvpn__SHADOW', 'S_pool_store.retire_openvpn__ROLE', 'S_pool_store.save_candidates__SHADOW', 'S_pool_store.save_candidates__ROLE', 'S_singbox.apply__SHADOW', 'S_singbox.apply__ROLE', 'S_singbox.restart__SHADOW', 'S_singbox.restart__ROLE', 'S_singbox.rollback__SHADOW', 'S_singbox.rollback__ROLE', 'S_xray.apply__SHADOW', 'S_xray.apply__ROLE', 'S_xray.rollback__SHADOW', 'S_xray.rollback__ROLE', 'H_DEFAULT', 'H_CODE', 'H_WRAPPED', 'H_CLOSURE', 'H_SIGNATURE', 'H_DIGEST', 'H_ARGUMENT', 'H_EXPECTED', 'H_PID', 'H_THREAD', 'H_SPECS', 'H_FUNCTIONS', 'H_DEPENDENCIES', 'H_DEFAULT_CODE', 'H_CYCLE', 'H_PRIVATE_SIGNATURE', 'I_OK', 'I_SOURCE_BAD', 'I_UNITS_BAD', 'I_SURFACE_BAD', 'I_BOTH_BAD', 'I_SOURCE_EXTRA', 'I_UNITS_LINK', 'I_SHADOW', 'I_PROVIDER', 'I_IDENTITY', 'I_PID', 'I_PREFIX', 'I_MODE', 'I_ADMIT', 'I_WRITER_FENCE', 'I_FULL_BUILD']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','unit_files','declared_surfaces','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='CODE_IDENTITY_ARTIFACTS_AND_DECLARED_SURFACES_ONLY' and data.get('expected')==437
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==437-len(rows) and len(rows)<=437 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='CODE_HANDSHAKE_BATCH_RECORDED' and data.get('completed')==437
      and data.get('passed')==437 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==121 and data.get('unit_files')==8 and data.get('declared_surfaces')==65 and data.get('remaining_not_run')==0
      and data.get('global_scope_stop') is False)
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

### S4.3. Зафиксировать автоматический exact report snapshot

```bash
python3 -I -B "$HOME/xgw-w3ak/batch.py" report
```

Нужны CODE_HANDSHAKE_REPORT_READY/rc0. Это НЕновыйworker/неPASS. Выбирает finalsummary,
илиprogress при отсутствииsummary; всеactualполя/nulls/точныеms проходятwhitelist.
Создаёт EXCL report-record.json (sanitizedprivatecheckpoint) иreport-data.md.
Snapshot сохраняет именно прочитанныйprefix даже при последующемprogress; не подменять
его новойsummary. Повторreport разрешён только как readonlydeterministicverification
этогоsnapshot, НЕповторstart. Unknownfields/privacy/typeerror→STOPreport; не обходить.
Если ниsummaryниprogress нет, AH-stylepartialfailure: NOT_COLLECTED/remainingNOT_RUN;
не выполнятьS4.4/S4.5/F3/не выдумывать437rows. Сообщитьsafe fixedfailure иactualrc.

### S4.4. Прочитать весь обезличенный Markdown

```bash
python3 -I -B - <<'PY'
from pathlib import Path
lines=(Path.home()/'xgw-w3ak/report-data.md').read_text(encoding='utf-8').splitlines()
if len(lines)>480:raise SystemExit('STOP_UNEXPECTED_REPORT_LENGTH')
print('SANITIZED_REPORT_LINES',len(lines))
PY
```

Прочитать все строки, включая failed/nullable. Не ручнойперенос/округление/~N/подстановка
ожиданий. ДанныеALL_CASES_PASSED вS3.3 не заменяют actualcases. Не catcasefiles/config/
registry/fingerprints/logs/receipt/rawexceptions. Не публиковать rawstatus/screenshots.


Ниже12обязательныхстраниц по40строк. Читать все; outputtruncated не review. Пустые страницы после конца partial допустимы. Один report, не новые tests.

#### S4.4a. Строки 1–40

```bash
sed -n '1,40p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4b. Строки 41–80

```bash
sed -n '41,80p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4c. Строки 81–120

```bash
sed -n '81,120p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4d. Строки 121–160

```bash
sed -n '121,160p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4e. Строки 161–200

```bash
sed -n '161,200p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4f. Строки 201–240

```bash
sed -n '201,240p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4g. Строки 241–280

```bash
sed -n '241,280p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4h. Строки 281–320

```bash
sed -n '281,320p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4i. Строки 321–360

```bash
sed -n '321,360p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4j. Строки 361–400

```bash
sed -n '361,400p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4k. Строки 401–440

```bash
sed -n '401,440p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

#### S4.4l. Строки 441–480

```bash
sed -n '441,480p' "$HOME/xgw-w3ak/report-data.md"
```

Нужен rc0. Прочитать все показанные строки; таблицу не редактировать.

### S4.5. Создать draft с неизменным automatic prefix

```bash
python3 -I -B - <<'PY'
import os
from pathlib import Path
notes=Path.home()/'xgw-w3ak';repo=Path.home()/'zcod/xgw'
prefix=(notes/'report-data.md').read_bytes()
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ak-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(prefix+footer)
print('AK_DRAFT_CREATED')
PY
```

НуженAK_DRAFT_CREATED/rc0. Заполнить ТОЛЬКОfooterJSON послеAK_EXECUTION пофактически
наблюдённымданным. start/monitor/show/reportrc отдельно; workerexitNOT_COLLECTED.
NNP/sudo/health/pool/link/versions/owneractions actual, null/UNKNOWN если не собрано.
NNP1 службы не NNРканала; healthenumHEALTHY_ON требует оба признака. Не вставлять
privatebaseline/rawstatus/метки/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryids/
tokens/privatehashes/argv/resulttexts/exception/screenshots. PublicsourceSHA разрешены.
Таблицы/prefix не редактировать. CasePASS отрицательногоcase не ExecutionCOMPLETED.

## 7. Интерпретация, автоматический отчёт и одна публикация

Больший объём не даёт права ослабить source/baseline/privacySTOP или добавлять live
fault/install. Одно ожидание до300с — срок наблюдения usercollector, не networkrescue.
Отсутствие finalsummary не повод startagain/kill/newnotes. Show/status→partialreport.
Report фиксирует точный выбранныйsummary/checkpoint вsanitizedEXCLreport-record.json;
advancingprogress не меняет snapshot. Поля source/units/surface matched/checked, code_bound, registry counters и diagnostic
nullable и whitelisted. code_bound — лишь schema2 частного fixture, не runtime gate.
Private manifest digests/paths/registryidentity/trace/resulttexts не сериализуются.
Автотаблицу не редактировать/не округлять. ReadallMarkdownbeforeonepublish.

PubliconlyknownIDs/enums/bools/counts/exactms/commandrc/Git/publicsourceSHA/publicrepo:line.
No rawconfig/status/log/kernel/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryid/
tokens/privatehashes/argv/resulttexts/exceptions/screenshots. Baselineнаблюдения отдельно
отcaseданных. Installedkernel/SQLtransaction/LANUDP/IPv6/DNS/E4/performance/allTS неPASS.
Source/globalgates и bootstrap долг сохраняются. ТолькоThinkCentre, сеть не менять.

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый AKreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3ak'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(git('diff','--name-only','63c9c413930eb348d46b2ff986bef46dd2e423d4','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==['src/xgw/ownership.py', 'src/xgw/ownership_diagnostics.py', 'src/xgw/ownership_identity.py', 'src/xgw/ownership_seal.py', 'src/xgw/ownership_surface.py'],'PRODUCT_SOURCE_CHANGED')
for rel,frozen,digest in [('tests/stand/wave3_code_handshake.py', 'batch.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AK_SOURCE_SHA')
for name,digest in {**json.loads((repo/'tests/stand/wave3_code_manifest.json').read_bytes()),**json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())}.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ak'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_code_handshake.py', 'batch.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
for frozen,folder,count in [('manifest.json','source',121),('units.json','units',8)]:
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
require(proc.returncode==0 and proc.stdout.strip()=='CODE_HANDSHAKE_REPORT_READY','REPORT_SNAPSHOT_CHANGED')
preview=(notes/'report-data.md').read_bytes();draft=(notes/'report.md').read_bytes()
require(draft.startswith(preview),'AUTOMATIC_PREFIX_CHANGED')
tail=draft[len(preview):].decode('utf-8')
require(tail.startswith('\n<!-- AK_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
def pairs(items):
    data={}
    for k,v in items:
        require(k not in data,'FOOTER_DUPLICATE');data[k]=v
    return data
fields=json.loads(tail.split('```json\n',1)[1].rsplit('\n```',1)[0],object_pairs_hook=pairs)
required={'nnp','sudo_rc','start_rc','monitor_rc','show_rc','report_rc','before_health','after_health','before_pool','after_pool','before_link','after_link','versions_unchanged','owner_actions'}
require(type(fields) is dict and set(fields)==required,'FOOTER_FIELDS')
require(fields['nnp'] is None or type(fields['nnp']) is int and fields['nnp'] in (0,1),'NNP_TYPE')
for key in ('sudo_rc','start_rc','monitor_rc','show_rc','report_rc'):require(fields[key] is None or type(fields[key]) is int and -255<=fields[key]<=255,'COMMAND_RC')
for key in ('before_health','after_health'):require(fields[key] in ('HEALTHY_ON','OTHER','UNKNOWN'),'HEALTH_ENUM')
for key in ('before_pool','after_pool'):require(fields[key] in ('OFF','OBSERVE','ON','UNKNOWN'),'POOL_ENUM')
for key in ('before_link','after_link'):require(fields[key] in ('ALIVE','LOST','UNKNOWN'),'LINK_ENUM')
require(fields['versions_unchanged'] is None or type(fields['versions_unchanged']) is bool,'VERSION_BOOL')
require(fields['owner_actions'] is None or type(fields['owner_actions']) is int and 0<=fields['owner_actions']<=100,'OWNER_ACTIONS')
stamp=datetime.fromisoformat((notes/'run-start.txt').read_text().strip())
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ak-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AK start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3ak — code identity and artifact preflight')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AJ/AI/AH/AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. AKreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
