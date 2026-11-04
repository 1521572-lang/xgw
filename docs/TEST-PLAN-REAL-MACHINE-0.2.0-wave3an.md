# ТЗ Flash AN: исправленный загрузчик, один прогон всех 852 сценариев

04.11.2026. Это повторная попытка незапущенного workload AM после исправления разработчика.
AM не имеет результатов cases и не считается PASS. Его отсутствие в Git объяснено
failure-сообщением исполнителя: claim, без summary/progress/cases; monitor3/shape1/report3.
Публикация через F3 была невозможна; исполнитель правильно не обходил prefix/privacy.
Старые ~/xgw-w3am/notes.md и все AM-артефакты оставить без изменений. НЕ запускать старый
AM повторно. Только новый ~/xgw-w3an и единственный start ниже разрешены этим ТЗ.

Дефект: AK.source импортировал ownership_binding транзитивно, но не добавлял ключ
в MODULES. AM.source обращался к отсутствующему M["ownership_binding"] до cases.mkdir.
Исправлено явным import_module в словарь. Source продукта122/units8/config/pyproject
не изменены. Изменён только сборщик: новый notesAN, явный import и progress0 сразу после
claim. Этот checkpoint содержит finalfalse/completed0/cases[], НЕPASS и НЕsummary.
Если startup снова оборвётся после progress0, status/show/report могут зафиксировать
пустой checkpoint; все852 NOT_RUN. Не вставлять ожидаемые flags/counts вместо null.
Если нет даже progress, по-прежнему НЕ S4.4/S4.5/F3 — только fixed failure/actualrc в чат.

Три узкие проверки: старый loader→точныйKeyError; новый real frozen loader122/50hooks
с auditregisteredtrue/violations0; injected pre-source failure→пустойcheckpoint/report.
Проверялся только bootstrap/source/report без запуска cases, actorbody или network.
RootUIDfixtures не rootDAC, исходный ThinkCentre startup traceback не получен:
это воспроизведённый дефект, соответствующий описанному месту остановки, а не rawtrace
реальной машины. Полный AN852/ThinkCentre НАМИ NOT_RUN.

Действуют ВСЕ ограничения AM: толькоThinkCentre/HEALTHY/on/workingLAN; LAN-клиента нет.
Nooff/install/G1/newSSHinventory/WAN/LAN/TS/pin/pool/config/service/live rules/APIwrites/
nft/ip/curl/DNS/ping/SSH/scans/pcap/netns/speedtest/newunits/timers/guardian/arm/fault.
Always_off запрещён; доinstall/fault independentoriginalon/code/unitrescue. При обрыве
входящего соединения>1мин следующая команда модели неrescue. GitFF неnetworkprobe.
All7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP. Product/source-only candidate не устанавливать.
ТолькоprivatePanelWriter/managed иfakecode/files/registry, остальные actors blank/no body.
Scope852 и критерии случаев — как в AM, целиком в helper и expectedS3.3 ниже.
Группы500/90/30/40/115/20/16/16/12/13. OrdinaryFAIL→independentcontinue, source/baseline/
privacy/audit/OSError/restorefailure→globalSTOP/remainingNOT_RUN. В Tlate возможенLIVE1/
UNKNOWN0/receipt0, смотретьwriter_total. Не считать этоidle илиразрешением retry.
600smonitor неnetworkrescuebudget. OneREADY/start/auto/SHOW+shape/partial/oneFFreport.
Полнаяволна3 не закрыта. AL756 и другие старые завершённые batches не повторять.

Ниже канонические команды AN; source pin12A11M, относительно AM PRODUCT DIFF EMPTY.
SHA всех семи artifacts остаются закреплены; новый SHA batch: 4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b

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
notes=Path.home()/'xgw-w3an'
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
require(hashlib.sha256((repo/'tests/stand/wave3_bound_composition.py').read_bytes()).hexdigest()=='4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')

for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:
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
notes=Path.home()/'xgw-w3an'
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
notes=Path.home()/'xgw-w3an'
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

artifacts=[('tests/stand/wave3_bound_composition.py', 'batch.py', '4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]
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
notes=Path.home()/'xgw-w3an'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
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

## 5. S3 — 852 проверок одного source-пакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3an/batch.py" start
```

НужныBOUND_COMPOSITION_BATCH_STARTED/rc0. Это Popencollector, не852PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AI78/AG129/AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до600с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3an/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3an/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
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
expected=['H_00_SHADOW_PREPARE', 'H_00_SHADOW_RUN', 'H_00_SHADOW_BODY', 'H_00_SHADOW_CHECKER', 'H_00_SHADOW_FINAL', 'H_00_ROLE_PREPARE', 'H_00_ROLE_RUN', 'H_00_ROLE_BODY', 'H_00_ROLE_CHECKER', 'H_00_ROLE_FINAL', 'H_01_SHADOW_PREPARE', 'H_01_SHADOW_RUN', 'H_01_SHADOW_BODY', 'H_01_SHADOW_CHECKER', 'H_01_SHADOW_FINAL', 'H_01_ROLE_PREPARE', 'H_01_ROLE_RUN', 'H_01_ROLE_BODY', 'H_01_ROLE_CHECKER', 'H_01_ROLE_FINAL', 'H_02_SHADOW_PREPARE', 'H_02_SHADOW_RUN', 'H_02_SHADOW_BODY', 'H_02_SHADOW_CHECKER', 'H_02_SHADOW_FINAL', 'H_02_ROLE_PREPARE', 'H_02_ROLE_RUN', 'H_02_ROLE_BODY', 'H_02_ROLE_CHECKER', 'H_02_ROLE_FINAL', 'H_03_SHADOW_PREPARE', 'H_03_SHADOW_RUN', 'H_03_SHADOW_BODY', 'H_03_SHADOW_CHECKER', 'H_03_SHADOW_FINAL', 'H_03_ROLE_PREPARE', 'H_03_ROLE_RUN', 'H_03_ROLE_BODY', 'H_03_ROLE_CHECKER', 'H_03_ROLE_FINAL', 'H_04_SHADOW_PREPARE', 'H_04_SHADOW_RUN', 'H_04_SHADOW_BODY', 'H_04_SHADOW_CHECKER', 'H_04_SHADOW_FINAL', 'H_04_ROLE_PREPARE', 'H_04_ROLE_RUN', 'H_04_ROLE_BODY', 'H_04_ROLE_CHECKER', 'H_04_ROLE_FINAL', 'H_05_SHADOW_PREPARE', 'H_05_SHADOW_RUN', 'H_05_SHADOW_BODY', 'H_05_SHADOW_CHECKER', 'H_05_SHADOW_FINAL', 'H_05_ROLE_PREPARE', 'H_05_ROLE_RUN', 'H_05_ROLE_BODY', 'H_05_ROLE_CHECKER', 'H_05_ROLE_FINAL', 'H_06_SHADOW_PREPARE', 'H_06_SHADOW_RUN', 'H_06_SHADOW_BODY', 'H_06_SHADOW_CHECKER', 'H_06_SHADOW_FINAL', 'H_06_ROLE_PREPARE', 'H_06_ROLE_RUN', 'H_06_ROLE_BODY', 'H_06_ROLE_CHECKER', 'H_06_ROLE_FINAL', 'H_07_SHADOW_PREPARE', 'H_07_SHADOW_RUN', 'H_07_SHADOW_BODY', 'H_07_SHADOW_CHECKER', 'H_07_SHADOW_FINAL', 'H_07_ROLE_PREPARE', 'H_07_ROLE_RUN', 'H_07_ROLE_BODY', 'H_07_ROLE_CHECKER', 'H_07_ROLE_FINAL', 'H_08_SHADOW_PREPARE', 'H_08_SHADOW_RUN', 'H_08_SHADOW_BODY', 'H_08_SHADOW_CHECKER', 'H_08_SHADOW_FINAL', 'H_08_ROLE_PREPARE', 'H_08_ROLE_RUN', 'H_08_ROLE_BODY', 'H_08_ROLE_CHECKER', 'H_08_ROLE_FINAL', 'H_09_SHADOW_PREPARE', 'H_09_SHADOW_RUN', 'H_09_SHADOW_BODY', 'H_09_SHADOW_CHECKER', 'H_09_SHADOW_FINAL', 'H_09_ROLE_PREPARE', 'H_09_ROLE_RUN', 'H_09_ROLE_BODY', 'H_09_ROLE_CHECKER', 'H_09_ROLE_FINAL', 'H_10_SHADOW_PREPARE', 'H_10_SHADOW_RUN', 'H_10_SHADOW_BODY', 'H_10_SHADOW_CHECKER', 'H_10_SHADOW_FINAL', 'H_10_ROLE_PREPARE', 'H_10_ROLE_RUN', 'H_10_ROLE_BODY', 'H_10_ROLE_CHECKER', 'H_10_ROLE_FINAL', 'H_11_SHADOW_PREPARE', 'H_11_SHADOW_RUN', 'H_11_SHADOW_BODY', 'H_11_SHADOW_CHECKER', 'H_11_SHADOW_FINAL', 'H_11_ROLE_PREPARE', 'H_11_ROLE_RUN', 'H_11_ROLE_BODY', 'H_11_ROLE_CHECKER', 'H_11_ROLE_FINAL', 'H_12_SHADOW_PREPARE', 'H_12_SHADOW_RUN', 'H_12_SHADOW_BODY', 'H_12_SHADOW_CHECKER', 'H_12_SHADOW_FINAL', 'H_12_ROLE_PREPARE', 'H_12_ROLE_RUN', 'H_12_ROLE_BODY', 'H_12_ROLE_CHECKER', 'H_12_ROLE_FINAL', 'H_13_SHADOW_PREPARE', 'H_13_SHADOW_RUN', 'H_13_SHADOW_BODY', 'H_13_SHADOW_CHECKER', 'H_13_SHADOW_FINAL', 'H_13_ROLE_PREPARE', 'H_13_ROLE_RUN', 'H_13_ROLE_BODY', 'H_13_ROLE_CHECKER', 'H_13_ROLE_FINAL', 'H_14_SHADOW_PREPARE', 'H_14_SHADOW_RUN', 'H_14_SHADOW_BODY', 'H_14_SHADOW_CHECKER', 'H_14_SHADOW_FINAL', 'H_14_ROLE_PREPARE', 'H_14_ROLE_RUN', 'H_14_ROLE_BODY', 'H_14_ROLE_CHECKER', 'H_14_ROLE_FINAL', 'H_15_SHADOW_PREPARE', 'H_15_SHADOW_RUN', 'H_15_SHADOW_BODY', 'H_15_SHADOW_CHECKER', 'H_15_SHADOW_FINAL', 'H_15_ROLE_PREPARE', 'H_15_ROLE_RUN', 'H_15_ROLE_BODY', 'H_15_ROLE_CHECKER', 'H_15_ROLE_FINAL', 'H_16_SHADOW_PREPARE', 'H_16_SHADOW_RUN', 'H_16_SHADOW_BODY', 'H_16_SHADOW_CHECKER', 'H_16_SHADOW_FINAL', 'H_16_ROLE_PREPARE', 'H_16_ROLE_RUN', 'H_16_ROLE_BODY', 'H_16_ROLE_CHECKER', 'H_16_ROLE_FINAL', 'H_17_SHADOW_PREPARE', 'H_17_SHADOW_RUN', 'H_17_SHADOW_BODY', 'H_17_SHADOW_CHECKER', 'H_17_SHADOW_FINAL', 'H_17_ROLE_PREPARE', 'H_17_ROLE_RUN', 'H_17_ROLE_BODY', 'H_17_ROLE_CHECKER', 'H_17_ROLE_FINAL', 'H_18_SHADOW_PREPARE', 'H_18_SHADOW_RUN', 'H_18_SHADOW_BODY', 'H_18_SHADOW_CHECKER', 'H_18_SHADOW_FINAL', 'H_18_ROLE_PREPARE', 'H_18_ROLE_RUN', 'H_18_ROLE_BODY', 'H_18_ROLE_CHECKER', 'H_18_ROLE_FINAL', 'H_19_SHADOW_PREPARE', 'H_19_SHADOW_RUN', 'H_19_SHADOW_BODY', 'H_19_SHADOW_CHECKER', 'H_19_SHADOW_FINAL', 'H_19_ROLE_PREPARE', 'H_19_ROLE_RUN', 'H_19_ROLE_BODY', 'H_19_ROLE_CHECKER', 'H_19_ROLE_FINAL', 'H_20_SHADOW_PREPARE', 'H_20_SHADOW_RUN', 'H_20_SHADOW_BODY', 'H_20_SHADOW_CHECKER', 'H_20_SHADOW_FINAL', 'H_20_ROLE_PREPARE', 'H_20_ROLE_RUN', 'H_20_ROLE_BODY', 'H_20_ROLE_CHECKER', 'H_20_ROLE_FINAL', 'H_21_SHADOW_PREPARE', 'H_21_SHADOW_RUN', 'H_21_SHADOW_BODY', 'H_21_SHADOW_CHECKER', 'H_21_SHADOW_FINAL', 'H_21_ROLE_PREPARE', 'H_21_ROLE_RUN', 'H_21_ROLE_BODY', 'H_21_ROLE_CHECKER', 'H_21_ROLE_FINAL', 'H_22_SHADOW_PREPARE', 'H_22_SHADOW_RUN', 'H_22_SHADOW_BODY', 'H_22_SHADOW_CHECKER', 'H_22_SHADOW_FINAL', 'H_22_ROLE_PREPARE', 'H_22_ROLE_RUN', 'H_22_ROLE_BODY', 'H_22_ROLE_CHECKER', 'H_22_ROLE_FINAL', 'H_23_SHADOW_PREPARE', 'H_23_SHADOW_RUN', 'H_23_SHADOW_BODY', 'H_23_SHADOW_CHECKER', 'H_23_SHADOW_FINAL', 'H_23_ROLE_PREPARE', 'H_23_ROLE_RUN', 'H_23_ROLE_BODY', 'H_23_ROLE_CHECKER', 'H_23_ROLE_FINAL', 'H_24_SHADOW_PREPARE', 'H_24_SHADOW_RUN', 'H_24_SHADOW_BODY', 'H_24_SHADOW_CHECKER', 'H_24_SHADOW_FINAL', 'H_24_ROLE_PREPARE', 'H_24_ROLE_RUN', 'H_24_ROLE_BODY', 'H_24_ROLE_CHECKER', 'H_24_ROLE_FINAL', 'H_25_SHADOW_PREPARE', 'H_25_SHADOW_RUN', 'H_25_SHADOW_BODY', 'H_25_SHADOW_CHECKER', 'H_25_SHADOW_FINAL', 'H_25_ROLE_PREPARE', 'H_25_ROLE_RUN', 'H_25_ROLE_BODY', 'H_25_ROLE_CHECKER', 'H_25_ROLE_FINAL', 'H_26_SHADOW_PREPARE', 'H_26_SHADOW_RUN', 'H_26_SHADOW_BODY', 'H_26_SHADOW_CHECKER', 'H_26_SHADOW_FINAL', 'H_26_ROLE_PREPARE', 'H_26_ROLE_RUN', 'H_26_ROLE_BODY', 'H_26_ROLE_CHECKER', 'H_26_ROLE_FINAL', 'H_27_SHADOW_PREPARE', 'H_27_SHADOW_RUN', 'H_27_SHADOW_BODY', 'H_27_SHADOW_CHECKER', 'H_27_SHADOW_FINAL', 'H_27_ROLE_PREPARE', 'H_27_ROLE_RUN', 'H_27_ROLE_BODY', 'H_27_ROLE_CHECKER', 'H_27_ROLE_FINAL', 'H_28_SHADOW_PREPARE', 'H_28_SHADOW_RUN', 'H_28_SHADOW_BODY', 'H_28_SHADOW_CHECKER', 'H_28_SHADOW_FINAL', 'H_28_ROLE_PREPARE', 'H_28_ROLE_RUN', 'H_28_ROLE_BODY', 'H_28_ROLE_CHECKER', 'H_28_ROLE_FINAL', 'H_29_SHADOW_PREPARE', 'H_29_SHADOW_RUN', 'H_29_SHADOW_BODY', 'H_29_SHADOW_CHECKER', 'H_29_SHADOW_FINAL', 'H_29_ROLE_PREPARE', 'H_29_ROLE_RUN', 'H_29_ROLE_BODY', 'H_29_ROLE_CHECKER', 'H_29_ROLE_FINAL', 'H_30_SHADOW_PREPARE', 'H_30_SHADOW_RUN', 'H_30_SHADOW_BODY', 'H_30_SHADOW_CHECKER', 'H_30_SHADOW_FINAL', 'H_30_ROLE_PREPARE', 'H_30_ROLE_RUN', 'H_30_ROLE_BODY', 'H_30_ROLE_CHECKER', 'H_30_ROLE_FINAL', 'H_31_SHADOW_PREPARE', 'H_31_SHADOW_RUN', 'H_31_SHADOW_BODY', 'H_31_SHADOW_CHECKER', 'H_31_SHADOW_FINAL', 'H_31_ROLE_PREPARE', 'H_31_ROLE_RUN', 'H_31_ROLE_BODY', 'H_31_ROLE_CHECKER', 'H_31_ROLE_FINAL', 'H_32_SHADOW_PREPARE', 'H_32_SHADOW_RUN', 'H_32_SHADOW_BODY', 'H_32_SHADOW_CHECKER', 'H_32_SHADOW_FINAL', 'H_32_ROLE_PREPARE', 'H_32_ROLE_RUN', 'H_32_ROLE_BODY', 'H_32_ROLE_CHECKER', 'H_32_ROLE_FINAL', 'H_33_SHADOW_PREPARE', 'H_33_SHADOW_RUN', 'H_33_SHADOW_BODY', 'H_33_SHADOW_CHECKER', 'H_33_SHADOW_FINAL', 'H_33_ROLE_PREPARE', 'H_33_ROLE_RUN', 'H_33_ROLE_BODY', 'H_33_ROLE_CHECKER', 'H_33_ROLE_FINAL', 'H_34_SHADOW_PREPARE', 'H_34_SHADOW_RUN', 'H_34_SHADOW_BODY', 'H_34_SHADOW_CHECKER', 'H_34_SHADOW_FINAL', 'H_34_ROLE_PREPARE', 'H_34_ROLE_RUN', 'H_34_ROLE_BODY', 'H_34_ROLE_CHECKER', 'H_34_ROLE_FINAL', 'H_35_SHADOW_PREPARE', 'H_35_SHADOW_RUN', 'H_35_SHADOW_BODY', 'H_35_SHADOW_CHECKER', 'H_35_SHADOW_FINAL', 'H_35_ROLE_PREPARE', 'H_35_ROLE_RUN', 'H_35_ROLE_BODY', 'H_35_ROLE_CHECKER', 'H_35_ROLE_FINAL', 'H_36_SHADOW_PREPARE', 'H_36_SHADOW_RUN', 'H_36_SHADOW_BODY', 'H_36_SHADOW_CHECKER', 'H_36_SHADOW_FINAL', 'H_36_ROLE_PREPARE', 'H_36_ROLE_RUN', 'H_36_ROLE_BODY', 'H_36_ROLE_CHECKER', 'H_36_ROLE_FINAL', 'H_37_SHADOW_PREPARE', 'H_37_SHADOW_RUN', 'H_37_SHADOW_BODY', 'H_37_SHADOW_CHECKER', 'H_37_SHADOW_FINAL', 'H_37_ROLE_PREPARE', 'H_37_ROLE_RUN', 'H_37_ROLE_BODY', 'H_37_ROLE_CHECKER', 'H_37_ROLE_FINAL', 'H_38_SHADOW_PREPARE', 'H_38_SHADOW_RUN', 'H_38_SHADOW_BODY', 'H_38_SHADOW_CHECKER', 'H_38_SHADOW_FINAL', 'H_38_ROLE_PREPARE', 'H_38_ROLE_RUN', 'H_38_ROLE_BODY', 'H_38_ROLE_CHECKER', 'H_38_ROLE_FINAL', 'H_39_SHADOW_PREPARE', 'H_39_SHADOW_RUN', 'H_39_SHADOW_BODY', 'H_39_SHADOW_CHECKER', 'H_39_SHADOW_FINAL', 'H_39_ROLE_PREPARE', 'H_39_ROLE_RUN', 'H_39_ROLE_BODY', 'H_39_ROLE_CHECKER', 'H_39_ROLE_FINAL', 'H_40_SHADOW_PREPARE', 'H_40_SHADOW_RUN', 'H_40_SHADOW_BODY', 'H_40_SHADOW_CHECKER', 'H_40_SHADOW_FINAL', 'H_40_ROLE_PREPARE', 'H_40_ROLE_RUN', 'H_40_ROLE_BODY', 'H_40_ROLE_CHECKER', 'H_40_ROLE_FINAL', 'H_41_SHADOW_PREPARE', 'H_41_SHADOW_RUN', 'H_41_SHADOW_BODY', 'H_41_SHADOW_CHECKER', 'H_41_SHADOW_FINAL', 'H_41_ROLE_PREPARE', 'H_41_ROLE_RUN', 'H_41_ROLE_BODY', 'H_41_ROLE_CHECKER', 'H_41_ROLE_FINAL', 'H_42_SHADOW_PREPARE', 'H_42_SHADOW_RUN', 'H_42_SHADOW_BODY', 'H_42_SHADOW_CHECKER', 'H_42_SHADOW_FINAL', 'H_42_ROLE_PREPARE', 'H_42_ROLE_RUN', 'H_42_ROLE_BODY', 'H_42_ROLE_CHECKER', 'H_42_ROLE_FINAL', 'H_43_SHADOW_PREPARE', 'H_43_SHADOW_RUN', 'H_43_SHADOW_BODY', 'H_43_SHADOW_CHECKER', 'H_43_SHADOW_FINAL', 'H_43_ROLE_PREPARE', 'H_43_ROLE_RUN', 'H_43_ROLE_BODY', 'H_43_ROLE_CHECKER', 'H_43_ROLE_FINAL', 'H_44_SHADOW_PREPARE', 'H_44_SHADOW_RUN', 'H_44_SHADOW_BODY', 'H_44_SHADOW_CHECKER', 'H_44_SHADOW_FINAL', 'H_44_ROLE_PREPARE', 'H_44_ROLE_RUN', 'H_44_ROLE_BODY', 'H_44_ROLE_CHECKER', 'H_44_ROLE_FINAL', 'H_45_SHADOW_PREPARE', 'H_45_SHADOW_RUN', 'H_45_SHADOW_BODY', 'H_45_SHADOW_CHECKER', 'H_45_SHADOW_FINAL', 'H_45_ROLE_PREPARE', 'H_45_ROLE_RUN', 'H_45_ROLE_BODY', 'H_45_ROLE_CHECKER', 'H_45_ROLE_FINAL', 'H_46_SHADOW_PREPARE', 'H_46_SHADOW_RUN', 'H_46_SHADOW_BODY', 'H_46_SHADOW_CHECKER', 'H_46_SHADOW_FINAL', 'H_46_ROLE_PREPARE', 'H_46_ROLE_RUN', 'H_46_ROLE_BODY', 'H_46_ROLE_CHECKER', 'H_46_ROLE_FINAL', 'H_47_SHADOW_PREPARE', 'H_47_SHADOW_RUN', 'H_47_SHADOW_BODY', 'H_47_SHADOW_CHECKER', 'H_47_SHADOW_FINAL', 'H_47_ROLE_PREPARE', 'H_47_ROLE_RUN', 'H_47_ROLE_BODY', 'H_47_ROLE_CHECKER', 'H_47_ROLE_FINAL', 'H_48_SHADOW_PREPARE', 'H_48_SHADOW_RUN', 'H_48_SHADOW_BODY', 'H_48_SHADOW_CHECKER', 'H_48_SHADOW_FINAL', 'H_48_ROLE_PREPARE', 'H_48_ROLE_RUN', 'H_48_ROLE_BODY', 'H_48_ROLE_CHECKER', 'H_48_ROLE_FINAL', 'H_49_SHADOW_PREPARE', 'H_49_SHADOW_RUN', 'H_49_SHADOW_BODY', 'H_49_SHADOW_CHECKER', 'H_49_SHADOW_FINAL', 'H_49_ROLE_PREPARE', 'H_49_ROLE_RUN', 'H_49_ROLE_BODY', 'H_49_ROLE_CHECKER', 'H_49_ROLE_FINAL', 'A_capture_NONE_PREPARE', 'A_capture_NONE_RUN', 'A_capture_NONE_BODY', 'A_capture_NONE_CHECKER', 'A_capture_NONE_FINAL', 'A_capture_FOREIGN_PREPARE', 'A_capture_FOREIGN_RUN', 'A_capture_FOREIGN_BODY', 'A_capture_FOREIGN_CHECKER', 'A_capture_FOREIGN_FINAL', 'A_peers_NONE_PREPARE', 'A_peers_NONE_RUN', 'A_peers_NONE_BODY', 'A_peers_NONE_CHECKER', 'A_peers_NONE_FINAL', 'A_peers_FOREIGN_PREPARE', 'A_peers_FOREIGN_RUN', 'A_peers_FOREIGN_BODY', 'A_peers_FOREIGN_CHECKER', 'A_peers_FOREIGN_FINAL', 'A_xray_NONE_PREPARE', 'A_xray_NONE_RUN', 'A_xray_NONE_BODY', 'A_xray_NONE_CHECKER', 'A_xray_NONE_FINAL', 'A_xray_FOREIGN_PREPARE', 'A_xray_FOREIGN_RUN', 'A_xray_FOREIGN_BODY', 'A_xray_FOREIGN_CHECKER', 'A_xray_FOREIGN_FINAL', 'A_singbox_NONE_PREPARE', 'A_singbox_NONE_RUN', 'A_singbox_NONE_BODY', 'A_singbox_NONE_CHECKER', 'A_singbox_NONE_FINAL', 'A_singbox_FOREIGN_PREPARE', 'A_singbox_FOREIGN_RUN', 'A_singbox_FOREIGN_BODY', 'A_singbox_FOREIGN_CHECKER', 'A_singbox_FOREIGN_FINAL', 'A_cores_NONE_PREPARE', 'A_cores_NONE_RUN', 'A_cores_NONE_BODY', 'A_cores_NONE_CHECKER', 'A_cores_NONE_FINAL', 'A_cores_FOREIGN_PREPARE', 'A_cores_FOREIGN_RUN', 'A_cores_FOREIGN_BODY', 'A_cores_FOREIGN_CHECKER', 'A_cores_FOREIGN_FINAL', 'A_api_NONE_PREPARE', 'A_api_NONE_RUN', 'A_api_NONE_BODY', 'A_api_NONE_CHECKER', 'A_api_NONE_FINAL', 'A_api_FOREIGN_PREPARE', 'A_api_FOREIGN_RUN', 'A_api_FOREIGN_BODY', 'A_api_FOREIGN_CHECKER', 'A_api_FOREIGN_FINAL', 'A_panel_NONE_PREPARE', 'A_panel_NONE_RUN', 'A_panel_NONE_BODY', 'A_panel_NONE_CHECKER', 'A_panel_NONE_FINAL', 'A_panel_FOREIGN_PREPARE', 'A_panel_FOREIGN_RUN', 'A_panel_FOREIGN_BODY', 'A_panel_FOREIGN_CHECKER', 'A_panel_FOREIGN_FINAL', 'A_pool_store_NONE_PREPARE', 'A_pool_store_NONE_RUN', 'A_pool_store_NONE_BODY', 'A_pool_store_NONE_CHECKER', 'A_pool_store_NONE_FINAL', 'A_pool_store_FOREIGN_PREPARE', 'A_pool_store_FOREIGN_RUN', 'A_pool_store_FOREIGN_BODY', 'A_pool_store_FOREIGN_CHECKER', 'A_pool_store_FOREIGN_FINAL', 'A_pool_NONE_PREPARE', 'A_pool_NONE_RUN', 'A_pool_NONE_BODY', 'A_pool_NONE_CHECKER', 'A_pool_NONE_FINAL', 'A_pool_FOREIGN_PREPARE', 'A_pool_FOREIGN_RUN', 'A_pool_FOREIGN_BODY', 'A_pool_FOREIGN_CHECKER', 'A_pool_FOREIGN_FINAL', 'R_API_NONE_PREPARE', 'R_API_NONE_RUN', 'R_API_NONE_BODY', 'R_API_NONE_CHECKER', 'R_API_NONE_FINAL', 'R_API_FOREIGN_PREPARE', 'R_API_FOREIGN_RUN', 'R_API_FOREIGN_BODY', 'R_API_FOREIGN_CHECKER', 'R_API_FOREIGN_FINAL', 'R_STORE_NONE_PREPARE', 'R_STORE_NONE_RUN', 'R_STORE_NONE_BODY', 'R_STORE_NONE_CHECKER', 'R_STORE_NONE_FINAL', 'R_STORE_FOREIGN_PREPARE', 'R_STORE_FOREIGN_RUN', 'R_STORE_FOREIGN_BODY', 'R_STORE_FOREIGN_CHECKER', 'R_STORE_FOREIGN_FINAL', 'R_BACKEND_NONE_PREPARE', 'R_BACKEND_NONE_RUN', 'R_BACKEND_NONE_BODY', 'R_BACKEND_NONE_CHECKER', 'R_BACKEND_NONE_FINAL', 'R_BACKEND_FOREIGN_PREPARE', 'R_BACKEND_FOREIGN_RUN', 'R_BACKEND_FOREIGN_BODY', 'R_BACKEND_FOREIGN_CHECKER', 'R_BACKEND_FOREIGN_FINAL', 'B_SOURCE_HASH_RUN', 'B_SOURCE_HASH_BODY', 'B_SOURCE_HASH_CHECKER', 'B_SOURCE_HASH_FINAL', 'B_SOURCE_MISSING_RUN', 'B_SOURCE_MISSING_BODY', 'B_SOURCE_MISSING_CHECKER', 'B_SOURCE_MISSING_FINAL', 'B_SOURCE_EXTRA_RUN', 'B_SOURCE_EXTRA_BODY', 'B_SOURCE_EXTRA_CHECKER', 'B_SOURCE_EXTRA_FINAL', 'B_SOURCE_MODE_RUN', 'B_SOURCE_MODE_BODY', 'B_SOURCE_MODE_CHECKER', 'B_SOURCE_MODE_FINAL', 'B_SOURCE_LINK_RUN', 'B_SOURCE_LINK_BODY', 'B_SOURCE_LINK_CHECKER', 'B_SOURCE_LINK_FINAL', 'B_UNITS_HASH_RUN', 'B_UNITS_HASH_BODY', 'B_UNITS_HASH_CHECKER', 'B_UNITS_HASH_FINAL', 'B_UNITS_MISSING_RUN', 'B_UNITS_MISSING_BODY', 'B_UNITS_MISSING_CHECKER', 'B_UNITS_MISSING_FINAL', 'B_UNITS_EXTRA_RUN', 'B_UNITS_EXTRA_BODY', 'B_UNITS_EXTRA_CHECKER', 'B_UNITS_EXTRA_FINAL', 'B_UNITS_MODE_RUN', 'B_UNITS_MODE_BODY', 'B_UNITS_MODE_CHECKER', 'B_UNITS_MODE_FINAL', 'B_UNITS_LINK_RUN', 'B_UNITS_LINK_BODY', 'B_UNITS_LINK_CHECKER', 'B_UNITS_LINK_FINAL', 'T_00_PREPARE', 'T_00_RUN', 'T_00_BODY', 'T_00_CHECKER', 'T_00_FINAL', 'T_01_PREPARE', 'T_01_RUN', 'T_01_BODY', 'T_01_CHECKER', 'T_01_FINAL', 'T_02_PREPARE', 'T_02_RUN', 'T_02_BODY', 'T_02_CHECKER', 'T_02_FINAL', 'T_03_PREPARE', 'T_03_RUN', 'T_03_BODY', 'T_03_CHECKER', 'T_03_FINAL', 'T_04_PREPARE', 'T_04_RUN', 'T_04_BODY', 'T_04_CHECKER', 'T_04_FINAL', 'T_05_PREPARE', 'T_05_RUN', 'T_05_BODY', 'T_05_CHECKER', 'T_05_FINAL', 'T_06_PREPARE', 'T_06_RUN', 'T_06_BODY', 'T_06_CHECKER', 'T_06_FINAL', 'T_07_PREPARE', 'T_07_RUN', 'T_07_BODY', 'T_07_CHECKER', 'T_07_FINAL', 'T_08_PREPARE', 'T_08_RUN', 'T_08_BODY', 'T_08_CHECKER', 'T_08_FINAL', 'T_09_PREPARE', 'T_09_RUN', 'T_09_BODY', 'T_09_CHECKER', 'T_09_FINAL', 'T_10_PREPARE', 'T_10_RUN', 'T_10_BODY', 'T_10_CHECKER', 'T_10_FINAL', 'T_11_PREPARE', 'T_11_RUN', 'T_11_BODY', 'T_11_CHECKER', 'T_11_FINAL', 'T_12_PREPARE', 'T_12_RUN', 'T_12_BODY', 'T_12_CHECKER', 'T_12_FINAL', 'T_13_PREPARE', 'T_13_RUN', 'T_13_BODY', 'T_13_CHECKER', 'T_13_FINAL', 'T_14_PREPARE', 'T_14_RUN', 'T_14_BODY', 'T_14_CHECKER', 'T_14_FINAL', 'T_15_PREPARE', 'T_15_RUN', 'T_15_BODY', 'T_15_CHECKER', 'T_15_FINAL', 'T_16_PREPARE', 'T_16_RUN', 'T_16_BODY', 'T_16_CHECKER', 'T_16_FINAL', 'T_17_PREPARE', 'T_17_RUN', 'T_17_BODY', 'T_17_CHECKER', 'T_17_FINAL', 'T_18_PREPARE', 'T_18_RUN', 'T_18_BODY', 'T_18_CHECKER', 'T_18_FINAL', 'T_19_PREPARE', 'T_19_RUN', 'T_19_BODY', 'T_19_CHECKER', 'T_19_FINAL', 'T_20_PREPARE', 'T_20_RUN', 'T_20_BODY', 'T_20_CHECKER', 'T_20_FINAL', 'T_21_PREPARE', 'T_21_RUN', 'T_21_BODY', 'T_21_CHECKER', 'T_21_FINAL', 'T_22_PREPARE', 'T_22_RUN', 'T_22_BODY', 'T_22_CHECKER', 'T_22_FINAL', 'C_GATE_PID', 'C_GATE_THREAD', 'C_REGISTRY', 'C_PREFLIGHT', 'C_FILES', 'C_GATE_BINDING', 'C_GATE_METHOD', 'C_GATE_CODE', 'C_REGISTRY_METHOD', 'C_REGISTRY_PATH', 'C_REGISTRY_UID', 'C_REGISTRY_CLOCK', 'C_REGISTRY_BOOT', 'C_COMPOSITION_BINDING', 'C_COMPOSITION_GATE', 'C_COMPOSITION_PID', 'C_PLAN_STEPS', 'C_PLAN_ACCEPT', 'C_CHECKER_CODE', 'C_CHECKER_DEFAULT', 'P_REGISTRY_TYPE', 'P_OLD_REGISTRY', 'P_EQUAL_IDENTITY', 'P_PREFLIGHT_TYPE', 'P_FILES_TYPE', 'P_DOMAIN', 'P_UNSEALED', 'P_DOUBLE_SEAL', 'P_FOREIGN_BINDING', 'P_BINDING_TYPE', 'P_VERIFIER_TYPE', 'P_ROLE_CONTRACT', 'P_GATE_SUBCLASS', 'P_BAD_PHASE', 'P_NO_CHECKER', 'P_ASYNC_CHECKER', 'D_EMPTY', 'D_LIST', 'D_MANY', 'D_TYPE', 'D_WRITER', 'D_METHOD', 'D_ARGS', 'D_KWARGS', 'D_DUPLICATE', 'D_OWNERSHIP', 'D_KEYTYPE', 'D_ROWTYPE', 'D_GENERATOR', 'D_ASYNCGEN', 'D_CALLABLE_OBJECT', 'D_BOOL_CHECKER', 'I_ONE', 'I_TWO', 'I_THREE', 'I_MAX', 'I_NOOP', 'I_ROLLBACK', 'I_EARLY_LEASE', 'I_REPLAY', 'I_FENCED', 'I_FULL_BUILD', 'I_FULL_NOOP', 'I_FULL_ROLLBACK', 'F_CHECKER_FALSE', 'F_CHECKER_BOOL', 'F_CHECKER_RAISE', 'F_BODY_RAISE', 'F_BODY_TERMINAL', 'F_FINAL_FALSE', 'F_FINAL_RAISE', 'F_FINAL_TERMINAL', 'F_FILE_HASH', 'F_FILE_MODE', 'F_FILE_MISSING', 'F_NESTED', 'F_SWAP_BOUNDARY_FINAL']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','unit_files','declared_surfaces','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='EXPLICIT_BUILD_BOUND_ACTORS_AND_PRIVATE_FILES_ONLY' and data.get('expected')==852
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==852-len(rows) and len(rows)<=852 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='BOUND_COMPOSITION_BATCH_RECORDED' and data.get('completed')==852
      and data.get('passed')==852 and all(r.get('passed') is True for r in rows)
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
python3 -I -B "$HOME/xgw-w3an/batch.py" report
```

Нужны BOUND_COMPOSITION_REPORT_READY/rc0. Это НЕновыйworker/неPASS. Выбирает finalsummary,
илиprogress при отсутствииsummary; всеactualполя/nulls/точныеms проходятwhitelist.
Создаёт EXCL report-record.json (sanitizedprivatecheckpoint) иreport-data.md.
Snapshot сохраняет именно прочитанныйprefix даже при последующемprogress; не подменять
его новойsummary. Повторreport разрешён только как readonlydeterministicverification
этогоsnapshot, НЕповторstart. Unknownfields/privacy/typeerror→STOPreport; не обходить.
Если ниsummaryниprogress нет, AH-stylepartialfailure: NOT_COLLECTED/remainingNOT_RUN;
не выполнятьS4.4/S4.5/F3/не выдумывать852rows. Сообщитьsafe fixedfailure иactualrc.

### S4.4. Прочитать весь обезличенный Markdown

```bash
python3 -I -B - <<'PY'
from pathlib import Path
lines=(Path.home()/'xgw-w3an/report-data.md').read_text(encoding='utf-8').splitlines()
if len(lines)>880:raise SystemExit('STOP_UNEXPECTED_REPORT_LENGTH')
print('SANITIZED_REPORT_LINES',len(lines))
PY
```

Прочитать все строки, включая failed/nullable. Не ручнойперенос/округление/~N/подстановка
ожиданий. ДанныеALL_CASES_PASSED вS3.3 не заменяют actualcases. Не catcasefiles/config/
registry/fingerprints/logs/receipt/rawexceptions. Не публиковать rawstatus/screenshots.


Ниже22обязательныхстраницы по40строк. Читать все; truncation неreview. Пустые страницы послеpartial допустимы. Один report, не новые tests.

#### S4.4a. Строки 1–40

```bash
sed -n '1,40p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4b. Строки 41–80

```bash
sed -n '41,80p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4c. Строки 81–120

```bash
sed -n '81,120p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4d. Строки 121–160

```bash
sed -n '121,160p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4e. Строки 161–200

```bash
sed -n '161,200p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4f. Строки 201–240

```bash
sed -n '201,240p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4g. Строки 241–280

```bash
sed -n '241,280p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4h. Строки 281–320

```bash
sed -n '281,320p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4i. Строки 321–360

```bash
sed -n '321,360p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4j. Строки 361–400

```bash
sed -n '361,400p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4k. Строки 401–440

```bash
sed -n '401,440p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4l. Строки 441–480

```bash
sed -n '441,480p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4m. Строки 481–520

```bash
sed -n '481,520p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4n. Строки 521–560

```bash
sed -n '521,560p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4o. Строки 561–600

```bash
sed -n '561,600p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4p. Строки 601–640

```bash
sed -n '601,640p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4q. Строки 641–680

```bash
sed -n '641,680p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4r. Строки 681–720

```bash
sed -n '681,720p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4s. Строки 721–760

```bash
sed -n '721,760p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4t. Строки 761–800

```bash
sed -n '761,800p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4u. Строки 801–840

```bash
sed -n '801,840p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4v. Строки 841–880

```bash
sed -n '841,880p' "$HOME/xgw-w3an/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

### S4.5. Создать draft с неизменным automatic prefix

```bash
python3 -I -B - <<'PY'
import os
from pathlib import Path
notes=Path.home()/'xgw-w3an';repo=Path.home()/'zcod/xgw'
prefix=(notes/'report-data.md').read_bytes()
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3an-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(prefix+footer)
print('AN_DRAFT_CREATED')
PY
```

НуженAN_DRAFT_CREATED/rc0. Заполнить ТОЛЬКОfooterJSON послеAN_EXECUTION пофактически
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

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый ANreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3an'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(git('diff','--name-only','7f72cdbb9a8d924e17880dac05e9b3d4d3cbeeaa','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==[],'PRODUCT_SOURCE_CHANGED')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AN_SOURCE_SHA')
for name,digest in {**json.loads((repo/'tests/stand/wave3_composition_manifest.json').read_bytes()),**json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())}.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3an'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_bound_composition.py', 'batch.py', '4dac556cbcaea1962c0efad33e080d93a53c266a455649bcccd0759430e7e43b'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_composition_manifest.json', 'manifest.json', 'dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
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
require(tail.startswith('\n<!-- AN_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3an-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AN start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3an — code-bound writer and FILES composition')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AL/AK/AJ/AI/AH/AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. ANreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
