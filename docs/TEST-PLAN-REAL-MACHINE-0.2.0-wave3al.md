# ТЗ Flash: wave3al — исправление двух AK fixtures и 756 проверок одним запуском

04.11.2026. Это продолжение незакрытого AK, не новая продуктовая волна. Максимальный
готовый safe объём:756cases/одинstart/автопереходы/partial/одинreport. На319больше AK,
но435пройденных AKcases НЕ повторяются. Нет новых продуктовых изменений или liveэтапа.

## 1. Фактический AK:435/437 и две незакрытые проверки

Report625ac2a043a0003a6f36d1d42f997df1d5f6375c, tested69adb641768cf501de67f9d787708b90691dcec9/
tree730e351d133f8c6f4496a5af71a76784a2613f3b. Controls:summary/437completed/435passed/
remaining0/CODE_HANDSHAKE_BATCH_PARTIAL/globalstopfalse/auditregisteredtrue/violations0/
source121/unit8/surfaces65/workloadprocess0/network0/liveops0/7runtimegatesfalse.
A225/225,B50/50,C144/146,D16/16. Batch65475ms/casesum47693ms/интервал02:04:18–02:11:11MSK
413секунд — разные метрики. Publicprefix восстановлен pinnedpureformatter byteexact.
FailedH_DEFAULT/H_DEFAULT_CODE:TypeError в AKhelper974/977 ДО изменения target.
Причина: одно __wrapped__ выбрало промежуточную функцию, __kwdefaults__ у неёNone.
ИсходныйXGW не виновен в этих двух ошибках; production121files UNCHANGED.

FooterHEALTHY_ON/poolOFF/linkALIVE/versionssame/owneractions0/NNP0/sudo0/start0/monitor0/
show0/report0. worker_exit_rcNOT_COLLECTED. show_rc0 — допустимо для subcommandshow,
но не для всего S3.3: по записаннойpartialsummary checker обязан был вернуть3.
Actualoverallshape_rc НЕсобран. Не придумыватьrc3какфакт/непереписыватьoriginalreport.
AL footer добавляет shape_rc пятнадцатым полем, S3.3 печатает SHOW_SUBCOMMAND_RC отдельно.
AKполностьюНЕпринят,435casesпринимаютсяscoped; двеregressionsзакрываютсятолькоactualAL.

ТОЛЬКОThinkCentre/LANclientнет/не спрашивать. WorkingLAN/HEALTHY/on baseline; hostнеLAN
UDP/IPv6/DNS/E4proof. Nooff/install/G1/newSSHinventory/WAN/LAN/TS/pin/pool/config/service/
live rules/APIwrites/nft/ip/curl/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtest/coreversion/
newunits/timers/guardian/arm/replay/fault. Always_offзапрещён. Independentoriginalon/code/
unitrescue ДОinstall/fault; incomingoutage>1мин следующаякоманда модели неrescue.
Все7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP. ALнеC/D/Eactivationpermission.
AJ328/AI78/AG129/AF145/AE112/AD130/AC51/.../AH386/полныйAK437 НЕповторять.

## 2. Весь готовый пакет и точные границы

Source121/pin351fb54e074f4a7b497a8a4244fc74c6088788d7diff11A11M неизменён сtestedAK.
Productdiffпротивreport625ac2=EMPTY. Packaging8/config/pyproject/старыеstandfiles тоже
UNCHANGED, включая исходный AKhelper с его failedcases: егоCLI/cases НЕ запускаются.
НовыйALhelper загружает pinnedAK ТОЛЬКОbootstrap/source/acceptedADguard/make_seal;
legacyregistryreference по старомуloader импортируется, егоcases НЕисполняются.
Новые файлы лишьALhelper/publicslotcatalog/test/docs. Installedruntime не обновлять.

chain() явно проходит всеFunctionType wrappers max8/no cycles. default_target()
ищет единственное объявление keyword по всей цепочке; zero/multiple→FAIL, не guessing.
REPAIR_H_DEFAULT:engine.apply_all.force_now наdepth2 False→True.
REPAIR_H_DEFAULT_CODE:actions.apply_network.runner наdepth2 меняетсяТОЛЬКОcodeidentity
черезco_firstlineno, не исполняется runner. Обаtargetтеперь фактически достигаются.

Publicslotcatalog306описаний:33KWdefault+2POSdefault+1functiondefaultcode+80innercode+
190closurecells. Это объявленные65surfaces, НЕ306новыхwriters/globalcallgraph.
Catalogтолькоpublicsurface/depth/kind/parameter/index, безdefaultvalues/cellcontents/code.
FrozenSHAзакрепляетразметку; workerзаново выводитcatalogизfrozen121sourceи требуетexact.
Все35directdefaultslots проверяются тремя разными изменениями:validliteral/remove/
opaqueobject. Innercode80 иclosurecells190 проверяютсяпоодномуdrift. Callabledefault1
отдельноcodeidentity. Businessfunctions/actorconstruction/service/network НЕисполняются.

| Блок на каждом из двух путей | Cases всего | Смысл |
|---|---:|---|
| Две repair-проверки ×CATALOG/PREFLIGHT |4|Закрытие двух AKfixturedefects по факту|
|35defaultslots×3mutations×2paths|210|Value identity/removal/unsupporteddefault handling|
|80innercode×2paths|160|Каждый вложенный wrapper/body code identity, без выполненияbody|
|190closurecells×2paths|380|Каждая declaredcell identity; не deep mutableobject attestation|
|1callabledefaultcode×2paths|2|Связь defaultfunctioncode с каталогом иpreflight|

Всего756cases. CATALOG:baseline65true→mutationfalse/0→restore65true→freshcatalog65true.
PREFLIGHT:те же операции черезCodePreflight с двумяprivateonefileCodeSeals; примутации
surfacefalse/0, source+unitstrue/1каждый. Публиковатьтолькоactualwhitelisted rows.
Каталог/составнойpreflight независимыепути, не повтор всегостарогоbatch.
Перечень756IDs закреплён helper иS3.3.

Никаких операцийреестра/новыхreceipts/recoverylease вALcases. Sourceбайты не меняются,
меняетсяТОЛЬКОfunctionmetadata/cellcontents вprivateworkerprocess. contextfinally
возвращаетoriginalobject/value; snapshotfunctionstate+старыйиfreshobserver подтверждают
восстановлениеДОследующегоcase. TargetRestoreStop/невернувшийсяbaseline→globalSTOP,
непоследующие contaminatedcases. OrdinarycaseFAILсдоказаннымrestore→прочиеindependent
cases auto. OSError/ScopeStop/audit/source/privacy/baseline STOP/remainingNOT_RUN.
Еслиexceptionраньшеobserve, mutationdetailsnullable, неexpectedfalse/0.

SurfaceCatalogнеfullruntimegraph/arbitrarymoduleglobals/aliaspolicy/hostilecodesandbox.
Closurecellidentity не deepmutableobjectsnapshot. CodePreflightcooperative/explicit,
неmandatoryruntimecomposition/loadedcodeattestation/Verification/lease/activation.
ExpectedUIDowner/bootclocksyntheticуsupport,неrootDAC/realboot. CodeSealobservations
sequentialнеatomicfilesystemsnapshot. No kernel/API/process/routesverifierclaims.

| Artifact → private frozen file | SHA256 |
|---|---|
|tests/stand/wave3_defaults_closure.py → batch.py|3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a|
|tests/stand/wave3_code_handshake.py → ak.py|927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55|
|tests/stand/wave3_source_hooks.py → support.py|9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
|tests/stand/wave3_code_manifest.json → manifest.json|d83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13|
|tests/stand/wave3_units_manifest.json → units.json|373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4|
|tests/stand/wave3_surface_catalog.json → surface.json|8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe|
|tests/stand/wave3_schema1_reference.py → legacy.py|2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5|
|tests/stand/wave3_defaults_catalog.json → slots.json|ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72|

Freeze8artifacts+121source+8packagingcopies в~/xgw-w3al0700; всеfiles0600/dirs0700.
PublicpackagingкопииНИКОГДАНЕexecute/install/source; неinstalledunitproof. Strictsource/
inventory/NOFOLLOW/owner/nlink/modes/SHA иfrozenpartialsamebytes, безoverwrite/newnotes.
AcceptedADauditguard ДОsourceimports/selfregistration/2manualprobes, no process/socket/
fork/exec/kill/ctypes/outofnoteswrite; trustedregressionguardНЕhostilecode sandbox/coarse
dirfdlimitationsпрежние. No newthreads/workloadsubprocess/network/livegatewayops.
7runtimeflagsfalseВСЕГДА;756casePASSне756applies/неCinstallationpermission.
Новыйrecordreaderbounded1MiB толькоALsummary/progress/report-record, oldAK/ADнеизменны.
16bool/intnullable details,publicerrorclass+file:line безrawexceptions/paths/values.
Immutablepartialreport сохраняетодинпрочитанныйprefix при advancingprogress.

Локально17narrowtests/RuffPASS:точное воспроизведениеобоихстарыхTypeError,4repairroutes,
6representativedefault/code/cellcases,catalogchain/cycle; observererrorrestore/globalbaselineSTOP/largeJSON650K+duplicatepolicy. Full756/ThinkCentre/oldbatches/
broadVM/network/kernel/services НАМИNOT_RUN. Выполнитьвесь756однимstartчерезFlash.

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
notes=Path.home()/'xgw-w3al'
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
git('merge-base','--is-ancestor','625ac2a043a0003a6f36d1d42f997df1d5f6375c','HEAD')
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
require(hashlib.sha256((repo/'tests/stand/wave3_defaults_closure.py').read_bytes()).hexdigest()=='3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')

for rel,frozen,digest in [('tests/stand/wave3_defaults_closure.py', 'batch.py', '3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), ('tests/stand/wave3_defaults_catalog.json', 'slots.json', 'ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72')]:
    require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'ARTIFACT_SHA')
pack=json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())
require(type(pack) is dict and len(pack)==8,'PACKAGING_COUNT')
require(set(pack)=={p.relative_to(repo).as_posix() for p in (repo/'packaging').iterdir() if p.is_file()},'PACKAGING_INVENTORY')
for name,digest in pack.items():require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PACKAGING_BYTES')
require(json.loads((repo/'tests/stand/wave3_surface_catalog.json').read_bytes())['schema']==1,'SURFACE_MANIFEST')
require(len(json.loads((repo/'tests/stand/wave3_defaults_catalog.json').read_bytes())['slots'])==306,'SLOT_COUNT')
require(not git('diff','--name-only','625ac2a043a0003a6f36d1d42f997df1d5f6375c','HEAD','--','src','packaging','config.example.toml','pyproject.toml'),'PRODUCT_SOURCE_CHANGED')
print('ARTIFACTS_AND_PACKAGING_MATCHED',8,8,65)

print('SOURCE_DIFF_ELEVEN_ADD_ELEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
notes=Path.home()/'xgw-w3al'
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
121sourcefiles неInstalled110повтор. Наличиеhooks неactivation; Nonepathsнеfenced. Восемь artifacts и восемь public packaging копий проверены отдельно, installed units не читались.

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

### S2.4. Freeze восьми artifacts, 121 source и восьми packaging-копий

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3al'
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

artifacts=[('tests/stand/wave3_defaults_closure.py', 'batch.py', '3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), ('tests/stand/wave3_defaults_catalog.json', 'slots.json', 'ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72')]
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
print('DEFAULTS_CLOSURE_FROZEN',8,121,8)

PY
```

Нужен DEFAULTS_CLOSURE_FROZEN 8 121 8/rc0. Resume допускается только ДОstart с теми же байтами. Никаких chmod/install/execute для packaging. Затем обязательный S2.4b.

#### S2.4b. Exact freeze и unused перед единственным start

```bash
python3 -I -B - <<'PY'

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3al'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_defaults_closure.py', 'batch.py', '3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), ('tests/stand/wave3_defaults_catalog.json', 'slots.json', 'ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
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
print('DEFAULTS_CLOSURE_READY')

PY
```

Только DEFAULTS_CLOSURE_READY/rc0 →S3.1. Afterstarted →S3.2/S3.3, безfreeze/start/worker повторно.

## 5. S3 — 756 проверок одного source-пакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3al/batch.py" start
```

НужныDEFAULTS_CLOSURE_BATCH_STARTED/rc0. Это Popencollector, не756PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AI78/AG129/AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3al/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3al/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
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
expected=['REPAIR_H_DEFAULT__CATALOG', 'REPAIR_H_DEFAULT__PREFLIGHT', 'REPAIR_H_DEFAULT_CODE__CATALOG', 'REPAIR_H_DEFAULT_CODE__PREFLIGHT', 'SLOT_000_DRIFT__CATALOG', 'SLOT_000_DRIFT__PREFLIGHT', 'SLOT_001_DRIFT__CATALOG', 'SLOT_001_DRIFT__PREFLIGHT', 'SLOT_002_DRIFT__CATALOG', 'SLOT_002_DRIFT__PREFLIGHT', 'SLOT_003_DRIFT__CATALOG', 'SLOT_003_DRIFT__PREFLIGHT', 'SLOT_004_DRIFT__CATALOG', 'SLOT_004_DRIFT__PREFLIGHT', 'SLOT_005_DRIFT__CATALOG', 'SLOT_005_DRIFT__PREFLIGHT', 'SLOT_006_DRIFT__CATALOG', 'SLOT_006_DRIFT__PREFLIGHT', 'SLOT_007_DRIFT__CATALOG', 'SLOT_007_DRIFT__PREFLIGHT', 'SLOT_008_LITERAL__CATALOG', 'SLOT_008_LITERAL__PREFLIGHT', 'SLOT_008_REMOVE__CATALOG', 'SLOT_008_REMOVE__PREFLIGHT', 'SLOT_008_OPAQUE__CATALOG', 'SLOT_008_OPAQUE__PREFLIGHT', 'SLOT_009_LITERAL__CATALOG', 'SLOT_009_LITERAL__PREFLIGHT', 'SLOT_009_REMOVE__CATALOG', 'SLOT_009_REMOVE__PREFLIGHT', 'SLOT_009_OPAQUE__CATALOG', 'SLOT_009_OPAQUE__PREFLIGHT', 'SLOT_010_DRIFT__CATALOG', 'SLOT_010_DRIFT__PREFLIGHT', 'SLOT_011_DRIFT__CATALOG', 'SLOT_011_DRIFT__PREFLIGHT', 'SLOT_012_DRIFT__CATALOG', 'SLOT_012_DRIFT__PREFLIGHT', 'SLOT_013_DRIFT__CATALOG', 'SLOT_013_DRIFT__PREFLIGHT', 'SLOT_014_DRIFT__CATALOG', 'SLOT_014_DRIFT__PREFLIGHT', 'SLOT_015_DRIFT__CATALOG', 'SLOT_015_DRIFT__PREFLIGHT', 'SLOT_016_DRIFT__CATALOG', 'SLOT_016_DRIFT__PREFLIGHT', 'SLOT_017_DRIFT__CATALOG', 'SLOT_017_DRIFT__PREFLIGHT', 'SLOT_018_DRIFT__CATALOG', 'SLOT_018_DRIFT__PREFLIGHT', 'SLOT_019_LITERAL__CATALOG', 'SLOT_019_LITERAL__PREFLIGHT', 'SLOT_019_REMOVE__CATALOG', 'SLOT_019_REMOVE__PREFLIGHT', 'SLOT_019_OPAQUE__CATALOG', 'SLOT_019_OPAQUE__PREFLIGHT', 'SLOT_020_DRIFT__CATALOG', 'SLOT_020_DRIFT__PREFLIGHT', 'SLOT_021_DRIFT__CATALOG', 'SLOT_021_DRIFT__PREFLIGHT', 'SLOT_022_DRIFT__CATALOG', 'SLOT_022_DRIFT__PREFLIGHT', 'SLOT_023_DRIFT__CATALOG', 'SLOT_023_DRIFT__PREFLIGHT', 'SLOT_024_DRIFT__CATALOG', 'SLOT_024_DRIFT__PREFLIGHT', 'SLOT_025_DRIFT__CATALOG', 'SLOT_025_DRIFT__PREFLIGHT', 'SLOT_026_DRIFT__CATALOG', 'SLOT_026_DRIFT__PREFLIGHT', 'SLOT_027_DRIFT__CATALOG', 'SLOT_027_DRIFT__PREFLIGHT', 'SLOT_028_LITERAL__CATALOG', 'SLOT_028_LITERAL__PREFLIGHT', 'SLOT_028_REMOVE__CATALOG', 'SLOT_028_REMOVE__PREFLIGHT', 'SLOT_028_OPAQUE__CATALOG', 'SLOT_028_OPAQUE__PREFLIGHT', 'SLOT_029_DRIFT__CATALOG', 'SLOT_029_DRIFT__PREFLIGHT', 'SLOT_030_DRIFT__CATALOG', 'SLOT_030_DRIFT__PREFLIGHT', 'SLOT_031_DRIFT__CATALOG', 'SLOT_031_DRIFT__PREFLIGHT', 'SLOT_032_DRIFT__CATALOG', 'SLOT_032_DRIFT__PREFLIGHT', 'SLOT_033_DRIFT__CATALOG', 'SLOT_033_DRIFT__PREFLIGHT', 'SLOT_034_DRIFT__CATALOG', 'SLOT_034_DRIFT__PREFLIGHT', 'SLOT_035_DRIFT__CATALOG', 'SLOT_035_DRIFT__PREFLIGHT', 'SLOT_036_DRIFT__CATALOG', 'SLOT_036_DRIFT__PREFLIGHT', 'SLOT_037_LITERAL__CATALOG', 'SLOT_037_LITERAL__PREFLIGHT', 'SLOT_037_REMOVE__CATALOG', 'SLOT_037_REMOVE__PREFLIGHT', 'SLOT_037_OPAQUE__CATALOG', 'SLOT_037_OPAQUE__PREFLIGHT', 'SLOT_038_DRIFT__CATALOG', 'SLOT_038_DRIFT__PREFLIGHT', 'SLOT_039_DRIFT__CATALOG', 'SLOT_039_DRIFT__PREFLIGHT', 'SLOT_040_DRIFT__CATALOG', 'SLOT_040_DRIFT__PREFLIGHT', 'SLOT_041_DRIFT__CATALOG', 'SLOT_041_DRIFT__PREFLIGHT', 'SLOT_042_DRIFT__CATALOG', 'SLOT_042_DRIFT__PREFLIGHT', 'SLOT_043_DRIFT__CATALOG', 'SLOT_043_DRIFT__PREFLIGHT', 'SLOT_044_DRIFT__CATALOG', 'SLOT_044_DRIFT__PREFLIGHT', 'SLOT_045_DRIFT__CATALOG', 'SLOT_045_DRIFT__PREFLIGHT', 'SLOT_046_LITERAL__CATALOG', 'SLOT_046_LITERAL__PREFLIGHT', 'SLOT_046_REMOVE__CATALOG', 'SLOT_046_REMOVE__PREFLIGHT', 'SLOT_046_OPAQUE__CATALOG', 'SLOT_046_OPAQUE__PREFLIGHT', 'SLOT_047_DRIFT__CATALOG', 'SLOT_047_DRIFT__PREFLIGHT', 'SLOT_048_DRIFT__CATALOG', 'SLOT_048_DRIFT__PREFLIGHT', 'SLOT_049_DRIFT__CATALOG', 'SLOT_049_DRIFT__PREFLIGHT', 'SLOT_050_DRIFT__CATALOG', 'SLOT_050_DRIFT__PREFLIGHT', 'SLOT_051_DRIFT__CATALOG', 'SLOT_051_DRIFT__PREFLIGHT', 'SLOT_052_DRIFT__CATALOG', 'SLOT_052_DRIFT__PREFLIGHT', 'SLOT_053_DRIFT__CATALOG', 'SLOT_053_DRIFT__PREFLIGHT', 'SLOT_054_DRIFT__CATALOG', 'SLOT_054_DRIFT__PREFLIGHT', 'SLOT_055_LITERAL__CATALOG', 'SLOT_055_LITERAL__PREFLIGHT', 'SLOT_055_REMOVE__CATALOG', 'SLOT_055_REMOVE__PREFLIGHT', 'SLOT_055_OPAQUE__CATALOG', 'SLOT_055_OPAQUE__PREFLIGHT', 'SLOT_056_DRIFT__CATALOG', 'SLOT_056_DRIFT__PREFLIGHT', 'SLOT_057_DRIFT__CATALOG', 'SLOT_057_DRIFT__PREFLIGHT', 'SLOT_058_DRIFT__CATALOG', 'SLOT_058_DRIFT__PREFLIGHT', 'SLOT_059_DRIFT__CATALOG', 'SLOT_059_DRIFT__PREFLIGHT', 'SLOT_060_DRIFT__CATALOG', 'SLOT_060_DRIFT__PREFLIGHT', 'SLOT_061_DRIFT__CATALOG', 'SLOT_061_DRIFT__PREFLIGHT', 'SLOT_062_DRIFT__CATALOG', 'SLOT_062_DRIFT__PREFLIGHT', 'SLOT_063_DRIFT__CATALOG', 'SLOT_063_DRIFT__PREFLIGHT', 'SLOT_064_LITERAL__CATALOG', 'SLOT_064_LITERAL__PREFLIGHT', 'SLOT_064_REMOVE__CATALOG', 'SLOT_064_REMOVE__PREFLIGHT', 'SLOT_064_OPAQUE__CATALOG', 'SLOT_064_OPAQUE__PREFLIGHT', 'SLOT_065_DRIFT__CATALOG', 'SLOT_065_DRIFT__PREFLIGHT', 'SLOT_066_DRIFT__CATALOG', 'SLOT_066_DRIFT__PREFLIGHT', 'SLOT_067_DRIFT__CATALOG', 'SLOT_067_DRIFT__PREFLIGHT', 'SLOT_068_DRIFT__CATALOG', 'SLOT_068_DRIFT__PREFLIGHT', 'SLOT_069_DRIFT__CATALOG', 'SLOT_069_DRIFT__PREFLIGHT', 'SLOT_070_DRIFT__CATALOG', 'SLOT_070_DRIFT__PREFLIGHT', 'SLOT_071_DRIFT__CATALOG', 'SLOT_071_DRIFT__PREFLIGHT', 'SLOT_072_DRIFT__CATALOG', 'SLOT_072_DRIFT__PREFLIGHT', 'SLOT_073_LITERAL__CATALOG', 'SLOT_073_LITERAL__PREFLIGHT', 'SLOT_073_REMOVE__CATALOG', 'SLOT_073_REMOVE__PREFLIGHT', 'SLOT_073_OPAQUE__CATALOG', 'SLOT_073_OPAQUE__PREFLIGHT', 'SLOT_074_LITERAL__CATALOG', 'SLOT_074_LITERAL__PREFLIGHT', 'SLOT_074_REMOVE__CATALOG', 'SLOT_074_REMOVE__PREFLIGHT', 'SLOT_074_OPAQUE__CATALOG', 'SLOT_074_OPAQUE__PREFLIGHT', 'SLOT_075_LITERAL__CATALOG', 'SLOT_075_LITERAL__PREFLIGHT', 'SLOT_075_REMOVE__CATALOG', 'SLOT_075_REMOVE__PREFLIGHT', 'SLOT_075_OPAQUE__CATALOG', 'SLOT_075_OPAQUE__PREFLIGHT', 'SLOT_076_DRIFT__CATALOG', 'SLOT_076_DRIFT__PREFLIGHT', 'SLOT_077_DRIFT__CATALOG', 'SLOT_077_DRIFT__PREFLIGHT', 'SLOT_078_DRIFT__CATALOG', 'SLOT_078_DRIFT__PREFLIGHT', 'SLOT_079_DRIFT__CATALOG', 'SLOT_079_DRIFT__PREFLIGHT', 'SLOT_080_DRIFT__CATALOG', 'SLOT_080_DRIFT__PREFLIGHT', 'SLOT_081_DRIFT__CATALOG', 'SLOT_081_DRIFT__PREFLIGHT', 'SLOT_082_DRIFT__CATALOG', 'SLOT_082_DRIFT__PREFLIGHT', 'SLOT_083_DRIFT__CATALOG', 'SLOT_083_DRIFT__PREFLIGHT', 'SLOT_084_LITERAL__CATALOG', 'SLOT_084_LITERAL__PREFLIGHT', 'SLOT_084_REMOVE__CATALOG', 'SLOT_084_REMOVE__PREFLIGHT', 'SLOT_084_OPAQUE__CATALOG', 'SLOT_084_OPAQUE__PREFLIGHT', 'SLOT_085_DRIFT__CATALOG', 'SLOT_085_DRIFT__PREFLIGHT', 'SLOT_086_DRIFT__CATALOG', 'SLOT_086_DRIFT__PREFLIGHT', 'SLOT_087_DRIFT__CATALOG', 'SLOT_087_DRIFT__PREFLIGHT', 'SLOT_088_DRIFT__CATALOG', 'SLOT_088_DRIFT__PREFLIGHT', 'SLOT_089_DRIFT__CATALOG', 'SLOT_089_DRIFT__PREFLIGHT', 'SLOT_090_DRIFT__CATALOG', 'SLOT_090_DRIFT__PREFLIGHT', 'SLOT_091_DRIFT__CATALOG', 'SLOT_091_DRIFT__PREFLIGHT', 'SLOT_092_DRIFT__CATALOG', 'SLOT_092_DRIFT__PREFLIGHT', 'SLOT_093_LITERAL__CATALOG', 'SLOT_093_LITERAL__PREFLIGHT', 'SLOT_093_REMOVE__CATALOG', 'SLOT_093_REMOVE__PREFLIGHT', 'SLOT_093_OPAQUE__CATALOG', 'SLOT_093_OPAQUE__PREFLIGHT', 'SLOT_094_DRIFT__CATALOG', 'SLOT_094_DRIFT__PREFLIGHT', 'SLOT_095_DRIFT__CATALOG', 'SLOT_095_DRIFT__PREFLIGHT', 'SLOT_096_DRIFT__CATALOG', 'SLOT_096_DRIFT__PREFLIGHT', 'SLOT_097_DRIFT__CATALOG', 'SLOT_097_DRIFT__PREFLIGHT', 'SLOT_098_DRIFT__CATALOG', 'SLOT_098_DRIFT__PREFLIGHT', 'SLOT_099_DRIFT__CATALOG', 'SLOT_099_DRIFT__PREFLIGHT', 'SLOT_100_DRIFT__CATALOG', 'SLOT_100_DRIFT__PREFLIGHT', 'SLOT_101_DRIFT__CATALOG', 'SLOT_101_DRIFT__PREFLIGHT', 'SLOT_102_DRIFT__CATALOG', 'SLOT_102_DRIFT__PREFLIGHT', 'SLOT_103_DRIFT__CATALOG', 'SLOT_103_DRIFT__PREFLIGHT', 'SLOT_104_DRIFT__CATALOG', 'SLOT_104_DRIFT__PREFLIGHT', 'SLOT_105_DRIFT__CATALOG', 'SLOT_105_DRIFT__PREFLIGHT', 'SLOT_106_DRIFT__CATALOG', 'SLOT_106_DRIFT__PREFLIGHT', 'SLOT_107_DRIFT__CATALOG', 'SLOT_107_DRIFT__PREFLIGHT', 'SLOT_108_DRIFT__CATALOG', 'SLOT_108_DRIFT__PREFLIGHT', 'SLOT_109_DRIFT__CATALOG', 'SLOT_109_DRIFT__PREFLIGHT', 'SLOT_110_DRIFT__CATALOG', 'SLOT_110_DRIFT__PREFLIGHT', 'SLOT_111_DRIFT__CATALOG', 'SLOT_111_DRIFT__PREFLIGHT', 'SLOT_112_LITERAL__CATALOG', 'SLOT_112_LITERAL__PREFLIGHT', 'SLOT_112_REMOVE__CATALOG', 'SLOT_112_REMOVE__PREFLIGHT', 'SLOT_112_OPAQUE__CATALOG', 'SLOT_112_OPAQUE__PREFLIGHT', 'SLOT_113_DRIFT__CATALOG', 'SLOT_113_DRIFT__PREFLIGHT', 'SLOT_114_DRIFT__CATALOG', 'SLOT_114_DRIFT__PREFLIGHT', 'SLOT_115_DRIFT__CATALOG', 'SLOT_115_DRIFT__PREFLIGHT', 'SLOT_116_DRIFT__CATALOG', 'SLOT_116_DRIFT__PREFLIGHT', 'SLOT_117_DRIFT__CATALOG', 'SLOT_117_DRIFT__PREFLIGHT', 'SLOT_118_DRIFT__CATALOG', 'SLOT_118_DRIFT__PREFLIGHT', 'SLOT_119_DRIFT__CATALOG', 'SLOT_119_DRIFT__PREFLIGHT', 'SLOT_120_DRIFT__CATALOG', 'SLOT_120_DRIFT__PREFLIGHT', 'SLOT_121_DRIFT__CATALOG', 'SLOT_121_DRIFT__PREFLIGHT', 'SLOT_122_DRIFT__CATALOG', 'SLOT_122_DRIFT__PREFLIGHT', 'SLOT_123_DRIFT__CATALOG', 'SLOT_123_DRIFT__PREFLIGHT', 'SLOT_124_DRIFT__CATALOG', 'SLOT_124_DRIFT__PREFLIGHT', 'SLOT_125_DRIFT__CATALOG', 'SLOT_125_DRIFT__PREFLIGHT', 'SLOT_126_DRIFT__CATALOG', 'SLOT_126_DRIFT__PREFLIGHT', 'SLOT_127_DRIFT__CATALOG', 'SLOT_127_DRIFT__PREFLIGHT', 'SLOT_128_DRIFT__CATALOG', 'SLOT_128_DRIFT__PREFLIGHT', 'SLOT_129_DRIFT__CATALOG', 'SLOT_129_DRIFT__PREFLIGHT', 'SLOT_130_DRIFT__CATALOG', 'SLOT_130_DRIFT__PREFLIGHT', 'SLOT_131_LITERAL__CATALOG', 'SLOT_131_LITERAL__PREFLIGHT', 'SLOT_131_REMOVE__CATALOG', 'SLOT_131_REMOVE__PREFLIGHT', 'SLOT_131_OPAQUE__CATALOG', 'SLOT_131_OPAQUE__PREFLIGHT', 'SLOT_132_DRIFT__CATALOG', 'SLOT_132_DRIFT__PREFLIGHT', 'SLOT_133_DRIFT__CATALOG', 'SLOT_133_DRIFT__PREFLIGHT', 'SLOT_134_DRIFT__CATALOG', 'SLOT_134_DRIFT__PREFLIGHT', 'SLOT_135_DRIFT__CATALOG', 'SLOT_135_DRIFT__PREFLIGHT', 'SLOT_136_DRIFT__CATALOG', 'SLOT_136_DRIFT__PREFLIGHT', 'SLOT_137_DRIFT__CATALOG', 'SLOT_137_DRIFT__PREFLIGHT', 'SLOT_138_DRIFT__CATALOG', 'SLOT_138_DRIFT__PREFLIGHT', 'SLOT_139_DRIFT__CATALOG', 'SLOT_139_DRIFT__PREFLIGHT', 'SLOT_140_DRIFT__CATALOG', 'SLOT_140_DRIFT__PREFLIGHT', 'SLOT_141_DRIFT__CATALOG', 'SLOT_141_DRIFT__PREFLIGHT', 'SLOT_142_DRIFT__CATALOG', 'SLOT_142_DRIFT__PREFLIGHT', 'SLOT_143_DRIFT__CATALOG', 'SLOT_143_DRIFT__PREFLIGHT', 'SLOT_144_DRIFT__CATALOG', 'SLOT_144_DRIFT__PREFLIGHT', 'SLOT_145_DRIFT__CATALOG', 'SLOT_145_DRIFT__PREFLIGHT', 'SLOT_146_DRIFT__CATALOG', 'SLOT_146_DRIFT__PREFLIGHT', 'SLOT_147_DRIFT__CATALOG', 'SLOT_147_DRIFT__PREFLIGHT', 'SLOT_148_DRIFT__CATALOG', 'SLOT_148_DRIFT__PREFLIGHT', 'SLOT_149_DRIFT__CATALOG', 'SLOT_149_DRIFT__PREFLIGHT', 'SLOT_150_DRIFT__CATALOG', 'SLOT_150_DRIFT__PREFLIGHT', 'SLOT_151_DRIFT__CATALOG', 'SLOT_151_DRIFT__PREFLIGHT', 'SLOT_152_DRIFT__CATALOG', 'SLOT_152_DRIFT__PREFLIGHT', 'SLOT_153_DRIFT__CATALOG', 'SLOT_153_DRIFT__PREFLIGHT', 'SLOT_154_DRIFT__CATALOG', 'SLOT_154_DRIFT__PREFLIGHT', 'SLOT_155_DRIFT__CATALOG', 'SLOT_155_DRIFT__PREFLIGHT', 'SLOT_156_DRIFT__CATALOG', 'SLOT_156_DRIFT__PREFLIGHT', 'SLOT_157_DRIFT__CATALOG', 'SLOT_157_DRIFT__PREFLIGHT', 'SLOT_158_DRIFT__CATALOG', 'SLOT_158_DRIFT__PREFLIGHT', 'SLOT_159_DRIFT__CATALOG', 'SLOT_159_DRIFT__PREFLIGHT', 'SLOT_160_DRIFT__CATALOG', 'SLOT_160_DRIFT__PREFLIGHT', 'SLOT_161_DRIFT__CATALOG', 'SLOT_161_DRIFT__PREFLIGHT', 'SLOT_162_DRIFT__CATALOG', 'SLOT_162_DRIFT__PREFLIGHT', 'SLOT_163_DRIFT__CATALOG', 'SLOT_163_DRIFT__PREFLIGHT', 'SLOT_164_DRIFT__CATALOG', 'SLOT_164_DRIFT__PREFLIGHT', 'SLOT_165_DRIFT__CATALOG', 'SLOT_165_DRIFT__PREFLIGHT', 'SLOT_166_DRIFT__CATALOG', 'SLOT_166_DRIFT__PREFLIGHT', 'SLOT_167_DRIFT__CATALOG', 'SLOT_167_DRIFT__PREFLIGHT', 'SLOT_168_DRIFT__CATALOG', 'SLOT_168_DRIFT__PREFLIGHT', 'SLOT_169_DRIFT__CATALOG', 'SLOT_169_DRIFT__PREFLIGHT', 'SLOT_170_DRIFT__CATALOG', 'SLOT_170_DRIFT__PREFLIGHT', 'SLOT_171_LITERAL__CATALOG', 'SLOT_171_LITERAL__PREFLIGHT', 'SLOT_171_REMOVE__CATALOG', 'SLOT_171_REMOVE__PREFLIGHT', 'SLOT_171_OPAQUE__CATALOG', 'SLOT_171_OPAQUE__PREFLIGHT', 'SLOT_172_LITERAL__CATALOG', 'SLOT_172_LITERAL__PREFLIGHT', 'SLOT_172_REMOVE__CATALOG', 'SLOT_172_REMOVE__PREFLIGHT', 'SLOT_172_OPAQUE__CATALOG', 'SLOT_172_OPAQUE__PREFLIGHT', 'SLOT_173_DRIFT__CATALOG', 'SLOT_173_DRIFT__PREFLIGHT', 'SLOT_174_DRIFT__CATALOG', 'SLOT_174_DRIFT__PREFLIGHT', 'SLOT_175_DRIFT__CATALOG', 'SLOT_175_DRIFT__PREFLIGHT', 'SLOT_176_DRIFT__CATALOG', 'SLOT_176_DRIFT__PREFLIGHT', 'SLOT_177_DRIFT__CATALOG', 'SLOT_177_DRIFT__PREFLIGHT', 'SLOT_178_DRIFT__CATALOG', 'SLOT_178_DRIFT__PREFLIGHT', 'SLOT_179_DRIFT__CATALOG', 'SLOT_179_DRIFT__PREFLIGHT', 'SLOT_180_DRIFT__CATALOG', 'SLOT_180_DRIFT__PREFLIGHT', 'SLOT_181_DRIFT__CATALOG', 'SLOT_181_DRIFT__PREFLIGHT', 'SLOT_182_DRIFT__CATALOG', 'SLOT_182_DRIFT__PREFLIGHT', 'SLOT_183_DRIFT__CATALOG', 'SLOT_183_DRIFT__PREFLIGHT', 'SLOT_184_LITERAL__CATALOG', 'SLOT_184_LITERAL__PREFLIGHT', 'SLOT_184_REMOVE__CATALOG', 'SLOT_184_REMOVE__PREFLIGHT', 'SLOT_184_OPAQUE__CATALOG', 'SLOT_184_OPAQUE__PREFLIGHT', 'SLOT_185_DRIFT__CATALOG', 'SLOT_185_DRIFT__PREFLIGHT', 'SLOT_186_DRIFT__CATALOG', 'SLOT_186_DRIFT__PREFLIGHT', 'SLOT_187_DRIFT__CATALOG', 'SLOT_187_DRIFT__PREFLIGHT', 'SLOT_188_DRIFT__CATALOG', 'SLOT_188_DRIFT__PREFLIGHT', 'SLOT_189_DRIFT__CATALOG', 'SLOT_189_DRIFT__PREFLIGHT', 'SLOT_190_DRIFT__CATALOG', 'SLOT_190_DRIFT__PREFLIGHT', 'SLOT_191_DRIFT__CATALOG', 'SLOT_191_DRIFT__PREFLIGHT', 'SLOT_192_DRIFT__CATALOG', 'SLOT_192_DRIFT__PREFLIGHT', 'SLOT_193_LITERAL__CATALOG', 'SLOT_193_LITERAL__PREFLIGHT', 'SLOT_193_REMOVE__CATALOG', 'SLOT_193_REMOVE__PREFLIGHT', 'SLOT_193_OPAQUE__CATALOG', 'SLOT_193_OPAQUE__PREFLIGHT', 'SLOT_194_LITERAL__CATALOG', 'SLOT_194_LITERAL__PREFLIGHT', 'SLOT_194_REMOVE__CATALOG', 'SLOT_194_REMOVE__PREFLIGHT', 'SLOT_194_OPAQUE__CATALOG', 'SLOT_194_OPAQUE__PREFLIGHT', 'SLOT_195_LITERAL__CATALOG', 'SLOT_195_LITERAL__PREFLIGHT', 'SLOT_195_REMOVE__CATALOG', 'SLOT_195_REMOVE__PREFLIGHT', 'SLOT_195_OPAQUE__CATALOG', 'SLOT_195_OPAQUE__PREFLIGHT', 'SLOT_196_DRIFT__CATALOG', 'SLOT_196_DRIFT__PREFLIGHT', 'SLOT_197_DRIFT__CATALOG', 'SLOT_197_DRIFT__PREFLIGHT', 'SLOT_198_DRIFT__CATALOG', 'SLOT_198_DRIFT__PREFLIGHT', 'SLOT_199_DRIFT__CATALOG', 'SLOT_199_DRIFT__PREFLIGHT', 'SLOT_200_DRIFT__CATALOG', 'SLOT_200_DRIFT__PREFLIGHT', 'SLOT_201_DRIFT__CATALOG', 'SLOT_201_DRIFT__PREFLIGHT', 'SLOT_202_DRIFT__CATALOG', 'SLOT_202_DRIFT__PREFLIGHT', 'SLOT_203_DRIFT__CATALOG', 'SLOT_203_DRIFT__PREFLIGHT', 'SLOT_204_LITERAL__CATALOG', 'SLOT_204_LITERAL__PREFLIGHT', 'SLOT_204_REMOVE__CATALOG', 'SLOT_204_REMOVE__PREFLIGHT', 'SLOT_204_OPAQUE__CATALOG', 'SLOT_204_OPAQUE__PREFLIGHT', 'SLOT_205_LITERAL__CATALOG', 'SLOT_205_LITERAL__PREFLIGHT', 'SLOT_205_REMOVE__CATALOG', 'SLOT_205_REMOVE__PREFLIGHT', 'SLOT_205_OPAQUE__CATALOG', 'SLOT_205_OPAQUE__PREFLIGHT', 'SLOT_206_LITERAL__CATALOG', 'SLOT_206_LITERAL__PREFLIGHT', 'SLOT_206_REMOVE__CATALOG', 'SLOT_206_REMOVE__PREFLIGHT', 'SLOT_206_OPAQUE__CATALOG', 'SLOT_206_OPAQUE__PREFLIGHT', 'SLOT_207_DRIFT__CATALOG', 'SLOT_207_DRIFT__PREFLIGHT', 'SLOT_208_DRIFT__CATALOG', 'SLOT_208_DRIFT__PREFLIGHT', 'SLOT_209_DRIFT__CATALOG', 'SLOT_209_DRIFT__PREFLIGHT', 'SLOT_210_DRIFT__CATALOG', 'SLOT_210_DRIFT__PREFLIGHT', 'SLOT_211_DRIFT__CATALOG', 'SLOT_211_DRIFT__PREFLIGHT', 'SLOT_212_DRIFT__CATALOG', 'SLOT_212_DRIFT__PREFLIGHT', 'SLOT_213_DRIFT__CATALOG', 'SLOT_213_DRIFT__PREFLIGHT', 'SLOT_214_DRIFT__CATALOG', 'SLOT_214_DRIFT__PREFLIGHT', 'SLOT_215_LITERAL__CATALOG', 'SLOT_215_LITERAL__PREFLIGHT', 'SLOT_215_REMOVE__CATALOG', 'SLOT_215_REMOVE__PREFLIGHT', 'SLOT_215_OPAQUE__CATALOG', 'SLOT_215_OPAQUE__PREFLIGHT', 'SLOT_216_LITERAL__CATALOG', 'SLOT_216_LITERAL__PREFLIGHT', 'SLOT_216_REMOVE__CATALOG', 'SLOT_216_REMOVE__PREFLIGHT', 'SLOT_216_OPAQUE__CATALOG', 'SLOT_216_OPAQUE__PREFLIGHT', 'SLOT_217_LITERAL__CATALOG', 'SLOT_217_LITERAL__PREFLIGHT', 'SLOT_217_REMOVE__CATALOG', 'SLOT_217_REMOVE__PREFLIGHT', 'SLOT_217_OPAQUE__CATALOG', 'SLOT_217_OPAQUE__PREFLIGHT', 'SLOT_218_DRIFT__CATALOG', 'SLOT_218_DRIFT__PREFLIGHT', 'SLOT_219_DRIFT__CATALOG', 'SLOT_219_DRIFT__PREFLIGHT', 'SLOT_220_DRIFT__CATALOG', 'SLOT_220_DRIFT__PREFLIGHT', 'SLOT_221_DRIFT__CATALOG', 'SLOT_221_DRIFT__PREFLIGHT', 'SLOT_222_DRIFT__CATALOG', 'SLOT_222_DRIFT__PREFLIGHT', 'SLOT_223_DRIFT__CATALOG', 'SLOT_223_DRIFT__PREFLIGHT', 'SLOT_224_DRIFT__CATALOG', 'SLOT_224_DRIFT__PREFLIGHT', 'SLOT_225_DRIFT__CATALOG', 'SLOT_225_DRIFT__PREFLIGHT', 'SLOT_226_LITERAL__CATALOG', 'SLOT_226_LITERAL__PREFLIGHT', 'SLOT_226_REMOVE__CATALOG', 'SLOT_226_REMOVE__PREFLIGHT', 'SLOT_226_OPAQUE__CATALOG', 'SLOT_226_OPAQUE__PREFLIGHT', 'SLOT_227_DRIFT__CATALOG', 'SLOT_227_DRIFT__PREFLIGHT', 'SLOT_228_DRIFT__CATALOG', 'SLOT_228_DRIFT__PREFLIGHT', 'SLOT_229_DRIFT__CATALOG', 'SLOT_229_DRIFT__PREFLIGHT', 'SLOT_230_DRIFT__CATALOG', 'SLOT_230_DRIFT__PREFLIGHT', 'SLOT_231_DRIFT__CATALOG', 'SLOT_231_DRIFT__PREFLIGHT', 'SLOT_232_DRIFT__CATALOG', 'SLOT_232_DRIFT__PREFLIGHT', 'SLOT_233_DRIFT__CATALOG', 'SLOT_233_DRIFT__PREFLIGHT', 'SLOT_234_DRIFT__CATALOG', 'SLOT_234_DRIFT__PREFLIGHT', 'SLOT_235_DRIFT__CATALOG', 'SLOT_235_DRIFT__PREFLIGHT', 'SLOT_236_DRIFT__CATALOG', 'SLOT_236_DRIFT__PREFLIGHT', 'SLOT_237_DRIFT__CATALOG', 'SLOT_237_DRIFT__PREFLIGHT', 'SLOT_238_DRIFT__CATALOG', 'SLOT_238_DRIFT__PREFLIGHT', 'SLOT_239_LITERAL__CATALOG', 'SLOT_239_LITERAL__PREFLIGHT', 'SLOT_239_REMOVE__CATALOG', 'SLOT_239_REMOVE__PREFLIGHT', 'SLOT_239_OPAQUE__CATALOG', 'SLOT_239_OPAQUE__PREFLIGHT', 'SLOT_240_DRIFT__CATALOG', 'SLOT_240_DRIFT__PREFLIGHT', 'SLOT_241_DRIFT__CATALOG', 'SLOT_241_DRIFT__PREFLIGHT', 'SLOT_242_DRIFT__CATALOG', 'SLOT_242_DRIFT__PREFLIGHT', 'SLOT_243_DRIFT__CATALOG', 'SLOT_243_DRIFT__PREFLIGHT', 'SLOT_244_DRIFT__CATALOG', 'SLOT_244_DRIFT__PREFLIGHT', 'SLOT_245_DRIFT__CATALOG', 'SLOT_245_DRIFT__PREFLIGHT', 'SLOT_246_DRIFT__CATALOG', 'SLOT_246_DRIFT__PREFLIGHT', 'SLOT_247_DRIFT__CATALOG', 'SLOT_247_DRIFT__PREFLIGHT', 'SLOT_248_DRIFT__CATALOG', 'SLOT_248_DRIFT__PREFLIGHT', 'SLOT_249_DRIFT__CATALOG', 'SLOT_249_DRIFT__PREFLIGHT', 'SLOT_250_DRIFT__CATALOG', 'SLOT_250_DRIFT__PREFLIGHT', 'SLOT_251_DRIFT__CATALOG', 'SLOT_251_DRIFT__PREFLIGHT', 'SLOT_252_DRIFT__CATALOG', 'SLOT_252_DRIFT__PREFLIGHT', 'SLOT_253_DRIFT__CATALOG', 'SLOT_253_DRIFT__PREFLIGHT', 'SLOT_254_DRIFT__CATALOG', 'SLOT_254_DRIFT__PREFLIGHT', 'SLOT_255_DRIFT__CATALOG', 'SLOT_255_DRIFT__PREFLIGHT', 'SLOT_256_DRIFT__CATALOG', 'SLOT_256_DRIFT__PREFLIGHT', 'SLOT_257_DRIFT__CATALOG', 'SLOT_257_DRIFT__PREFLIGHT', 'SLOT_258_DRIFT__CATALOG', 'SLOT_258_DRIFT__PREFLIGHT', 'SLOT_259_DRIFT__CATALOG', 'SLOT_259_DRIFT__PREFLIGHT', 'SLOT_260_DRIFT__CATALOG', 'SLOT_260_DRIFT__PREFLIGHT', 'SLOT_261_LITERAL__CATALOG', 'SLOT_261_LITERAL__PREFLIGHT', 'SLOT_261_REMOVE__CATALOG', 'SLOT_261_REMOVE__PREFLIGHT', 'SLOT_261_OPAQUE__CATALOG', 'SLOT_261_OPAQUE__PREFLIGHT', 'SLOT_262_DRIFT__CATALOG', 'SLOT_262_DRIFT__PREFLIGHT', 'SLOT_263_DRIFT__CATALOG', 'SLOT_263_DRIFT__PREFLIGHT', 'SLOT_264_DRIFT__CATALOG', 'SLOT_264_DRIFT__PREFLIGHT', 'SLOT_265_LITERAL__CATALOG', 'SLOT_265_LITERAL__PREFLIGHT', 'SLOT_265_REMOVE__CATALOG', 'SLOT_265_REMOVE__PREFLIGHT', 'SLOT_265_OPAQUE__CATALOG', 'SLOT_265_OPAQUE__PREFLIGHT', 'SLOT_266_LITERAL__CATALOG', 'SLOT_266_LITERAL__PREFLIGHT', 'SLOT_266_REMOVE__CATALOG', 'SLOT_266_REMOVE__PREFLIGHT', 'SLOT_266_OPAQUE__CATALOG', 'SLOT_266_OPAQUE__PREFLIGHT', 'SLOT_267_DRIFT__CATALOG', 'SLOT_267_DRIFT__PREFLIGHT', 'SLOT_268_DRIFT__CATALOG', 'SLOT_268_DRIFT__PREFLIGHT', 'SLOT_269_DRIFT__CATALOG', 'SLOT_269_DRIFT__PREFLIGHT', 'SLOT_270_DRIFT__CATALOG', 'SLOT_270_DRIFT__PREFLIGHT', 'SLOT_271_DRIFT__CATALOG', 'SLOT_271_DRIFT__PREFLIGHT', 'SLOT_272_DRIFT__CATALOG', 'SLOT_272_DRIFT__PREFLIGHT', 'SLOT_273_LITERAL__CATALOG', 'SLOT_273_LITERAL__PREFLIGHT', 'SLOT_273_REMOVE__CATALOG', 'SLOT_273_REMOVE__PREFLIGHT', 'SLOT_273_OPAQUE__CATALOG', 'SLOT_273_OPAQUE__PREFLIGHT', 'SLOT_274_DRIFT__CATALOG', 'SLOT_274_DRIFT__PREFLIGHT', 'SLOT_275_DRIFT__CATALOG', 'SLOT_275_DRIFT__PREFLIGHT', 'SLOT_276_DRIFT__CATALOG', 'SLOT_276_DRIFT__PREFLIGHT', 'SLOT_277_DRIFT__CATALOG', 'SLOT_277_DRIFT__PREFLIGHT', 'SLOT_278_DRIFT__CATALOG', 'SLOT_278_DRIFT__PREFLIGHT', 'SLOT_279_DRIFT__CATALOG', 'SLOT_279_DRIFT__PREFLIGHT', 'SLOT_280_DRIFT__CATALOG', 'SLOT_280_DRIFT__PREFLIGHT', 'SLOT_281_DRIFT__CATALOG', 'SLOT_281_DRIFT__PREFLIGHT', 'SLOT_282_DRIFT__CATALOG', 'SLOT_282_DRIFT__PREFLIGHT', 'SLOT_283_DRIFT__CATALOG', 'SLOT_283_DRIFT__PREFLIGHT', 'SLOT_284_DRIFT__CATALOG', 'SLOT_284_DRIFT__PREFLIGHT', 'SLOT_285_DRIFT__CATALOG', 'SLOT_285_DRIFT__PREFLIGHT', 'SLOT_286_DRIFT__CATALOG', 'SLOT_286_DRIFT__PREFLIGHT', 'SLOT_287_DRIFT__CATALOG', 'SLOT_287_DRIFT__PREFLIGHT', 'SLOT_288_DRIFT__CATALOG', 'SLOT_288_DRIFT__PREFLIGHT', 'SLOT_289_DRIFT__CATALOG', 'SLOT_289_DRIFT__PREFLIGHT', 'SLOT_290_DRIFT__CATALOG', 'SLOT_290_DRIFT__PREFLIGHT', 'SLOT_291_DRIFT__CATALOG', 'SLOT_291_DRIFT__PREFLIGHT', 'SLOT_292_DRIFT__CATALOG', 'SLOT_292_DRIFT__PREFLIGHT', 'SLOT_293_DRIFT__CATALOG', 'SLOT_293_DRIFT__PREFLIGHT', 'SLOT_294_DRIFT__CATALOG', 'SLOT_294_DRIFT__PREFLIGHT', 'SLOT_295_DRIFT__CATALOG', 'SLOT_295_DRIFT__PREFLIGHT', 'SLOT_296_DRIFT__CATALOG', 'SLOT_296_DRIFT__PREFLIGHT', 'SLOT_297_DRIFT__CATALOG', 'SLOT_297_DRIFT__PREFLIGHT', 'SLOT_298_DRIFT__CATALOG', 'SLOT_298_DRIFT__PREFLIGHT', 'SLOT_299_DRIFT__CATALOG', 'SLOT_299_DRIFT__PREFLIGHT', 'SLOT_300_DRIFT__CATALOG', 'SLOT_300_DRIFT__PREFLIGHT', 'SLOT_301_LITERAL__CATALOG', 'SLOT_301_LITERAL__PREFLIGHT', 'SLOT_301_REMOVE__CATALOG', 'SLOT_301_REMOVE__PREFLIGHT', 'SLOT_301_OPAQUE__CATALOG', 'SLOT_301_OPAQUE__PREFLIGHT', 'SLOT_302_LITERAL__CATALOG', 'SLOT_302_LITERAL__PREFLIGHT', 'SLOT_302_REMOVE__CATALOG', 'SLOT_302_REMOVE__PREFLIGHT', 'SLOT_302_OPAQUE__CATALOG', 'SLOT_302_OPAQUE__PREFLIGHT', 'SLOT_303_DRIFT__CATALOG', 'SLOT_303_DRIFT__PREFLIGHT', 'SLOT_304_DRIFT__CATALOG', 'SLOT_304_DRIFT__PREFLIGHT', 'SLOT_305_DRIFT__CATALOG', 'SLOT_305_DRIFT__PREFLIGHT']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','unit_files','declared_surfaces','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='DECLARED_DEFAULTS_CLOSURES_AND_TWO_AK_REPAIRS_ONLY' and data.get('expected')==756
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==756-len(rows) and len(rows)<=756 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='DEFAULTS_CLOSURE_BATCH_RECORDED' and data.get('completed')==756
      and data.get('passed')==756 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==121 and data.get('unit_files')==8 and data.get('declared_surfaces')==65 and data.get('remaining_not_run')==0
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
python3 -I -B "$HOME/xgw-w3al/batch.py" report
```

Нужны DEFAULTS_CLOSURE_REPORT_READY/rc0. Это НЕновыйworker/неPASS. Выбирает finalsummary,
илиprogress при отсутствииsummary; всеactualполя/nulls/точныеms проходятwhitelist.
Создаёт EXCL report-record.json (sanitizedprivatecheckpoint) иreport-data.md.
Snapshot сохраняет именно прочитанныйprefix даже при последующемprogress; не подменять
его новойsummary. Повторreport разрешён только как readonlydeterministicverification
этогоsnapshot, НЕповторstart. Unknownfields/privacy/typeerror→STOPreport; не обходить.
Если ниsummaryниprogress нет, AH-stylepartialfailure: NOT_COLLECTED/remainingNOT_RUN;
не выполнятьS4.4/S4.5/F3/не выдумывать756rows. Сообщитьsafe fixedfailure иactualrc.

### S4.4. Прочитать весь обезличенный Markdown

```bash
python3 -I -B - <<'PY'
from pathlib import Path
lines=(Path.home()/'xgw-w3al/report-data.md').read_text(encoding='utf-8').splitlines()
if len(lines)>800:raise SystemExit('STOP_UNEXPECTED_REPORT_LENGTH')
print('SANITIZED_REPORT_LINES',len(lines))
PY
```

Прочитать все строки, включая failed/nullable. Не ручнойперенос/округление/~N/подстановка
ожиданий. ДанныеALL_CASES_PASSED вS3.3 не заменяют actualcases. Не catcasefiles/config/
registry/fingerprints/logs/receipt/rawexceptions. Не публиковать rawstatus/screenshots.


Ниже20обязательныхстраниц по40строк. Прочитать все; truncation неreview. Пустаястраница послеpartial допустима. Один report, не новые tests.

#### S4.4a. Строки 1–40

```bash
sed -n '1,40p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4b. Строки 41–80

```bash
sed -n '41,80p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4c. Строки 81–120

```bash
sed -n '81,120p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4d. Строки 121–160

```bash
sed -n '121,160p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4e. Строки 161–200

```bash
sed -n '161,200p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4f. Строки 201–240

```bash
sed -n '201,240p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4g. Строки 241–280

```bash
sed -n '241,280p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4h. Строки 281–320

```bash
sed -n '281,320p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4i. Строки 321–360

```bash
sed -n '321,360p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4j. Строки 361–400

```bash
sed -n '361,400p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4k. Строки 401–440

```bash
sed -n '401,440p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4l. Строки 441–480

```bash
sed -n '441,480p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4m. Строки 481–520

```bash
sed -n '481,520p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4n. Строки 521–560

```bash
sed -n '521,560p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4o. Строки 561–600

```bash
sed -n '561,600p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4p. Строки 601–640

```bash
sed -n '601,640p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4q. Строки 641–680

```bash
sed -n '641,680p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4r. Строки 681–720

```bash
sed -n '681,720p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4s. Строки 721–760

```bash
sed -n '721,760p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

#### S4.4t. Строки 761–800

```bash
sed -n '761,800p' "$HOME/xgw-w3al/report-data.md"
```

Нуженrc0. Прочитать все строки; prefix/таблицу не редактировать.

### S4.5. Создать draft с неизменным automatic prefix

```bash
python3 -I -B - <<'PY'
import os
from pathlib import Path
notes=Path.home()/'xgw-w3al';repo=Path.home()/'zcod/xgw'
prefix=(notes/'report-data.md').read_bytes()
footer=(repo/'docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3al-TEMPLATE.md').read_bytes()
fd=os.open(notes/'report.md',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:out.write(prefix+footer)
print('AL_DRAFT_CREATED')
PY
```

НуженAL_DRAFT_CREATED/rc0. Заполнить ТОЛЬКОfooterJSON послеAL_EXECUTION пофактически
наблюдённымданным. start/monitor/show/shape/reportrc отдельно; workerexitNOT_COLLECTED.
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
advancingprogress не меняет snapshot. Поля target/baseline/mutation/restored/fresh/source/units nullable и whitelisted.
16details не receipts/runtimeactivation. Businessbody не исполняется.
Private paths/hashes/defaultvalues/closurecontents не сериализуются.
Автотаблицу не редактировать/не округлять. ReadallMarkdownbeforeonepublish.

PubliconlyknownIDs/enums/bools/counts/exactms/commandrc/Git/publicsourceSHA/publicrepo:line.
No rawconfig/status/log/kernel/URI/IP/MAC/UUID/secrets/PID/NIC/UID/home/boot/registryid/
tokens/privatehashes/argv/resulttexts/exceptions/screenshots. Baselineнаблюдения отдельно
отcaseданных. Installedkernel/SQLtransaction/LANUDP/IPv6/DNS/E4/performance/allTS неPASS.
Source/globalgates и bootstrap долг сохраняются. ТолькоThinkCentre, сеть не менять.

### F3. Проверить prefix/footer/identity и опубликовать ОДИН новый ALreport

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,re,subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
repo=Path.home()/'zcod/xgw';notes=Path.home()/'xgw-w3al'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
require(os.geteuid()!=0 and git('branch','--show-current')=='freepool' and not git('status','--porcelain'),'OWNER_BRANCH_CLEAN')
git('fetch','-q','origin','freepool');git('merge','--ff-only','origin/freepool')
require(git('diff','--name-only','625ac2a043a0003a6f36d1d42f997df1d5f6375c','HEAD','--','src','packaging','config.example.toml','pyproject.toml').splitlines()==[],'PRODUCT_SOURCE_CHANGED')
for rel,frozen,digest in [('tests/stand/wave3_defaults_closure.py', 'batch.py', '3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), ('tests/stand/wave3_defaults_catalog.json', 'slots.json', 'ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72')]:require(hashlib.sha256((repo/rel).read_bytes()).hexdigest()==digest,'AL_SOURCE_SHA')
for name,digest in {**json.loads((repo/'tests/stand/wave3_code_manifest.json').read_bytes()),**json.loads((repo/'tests/stand/wave3_units_manifest.json').read_bytes())}.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'PRODUCT_BYTES_CHANGED')

import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3al'
def require(v,c):
    if not v:raise SystemExit('STOP_'+c)
def valid(path,digest):
    i=path.lstat()
    return stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o600 and i.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
def directory(path):
    i=path.lstat()
    return stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and i.st_mode&0o7777==0o700
require(os.geteuid()!=0 and directory(notes),'OWNER_NOTES_METADATA')
for rel,frozen,digest in [('tests/stand/wave3_defaults_closure.py', 'batch.py', '3e4cb8ecb0264f5e8fbc6dc75b3e7bd648590ffcd7340fec9783f86cd7e58e3a'), ('tests/stand/wave3_code_handshake.py', 'ak.py', '927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55'), ('tests/stand/wave3_source_hooks.py', 'support.py', '9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917'), ('tests/stand/wave3_code_manifest.json', 'manifest.json', 'd83d70a5e52576edf84504d9d9a040efb160e5ada6897d4a9bb4b6db54df3e13'), ('tests/stand/wave3_units_manifest.json', 'units.json', '373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4'), ('tests/stand/wave3_surface_catalog.json', 'surface.json', '8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe'), ('tests/stand/wave3_schema1_reference.py', 'legacy.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), ('tests/stand/wave3_defaults_catalog.json', 'slots.json', 'ecfce37207db8aa9af503fcab6df749bf98707306a06eec2ab40fe93a0f35a72')]:require(valid(notes/frozen,digest),'FROZEN_ARTIFACT_CHANGED')
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
require(proc.returncode==0 and proc.stdout.strip()=='DEFAULTS_CLOSURE_REPORT_READY','REPORT_SNAPSHOT_CHANGED')
preview=(notes/'report-data.md').read_bytes();draft=(notes/'report.md').read_bytes()
require(draft.startswith(preview),'AUTOMATIC_PREFIX_CHANGED')
tail=draft[len(preview):].decode('utf-8')
require(tail.startswith('\n<!-- AL_EXECUTION -->\n```json\n') and tail.endswith('\n```\n'),'FOOTER_SHAPE')
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3al-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'REPORT_EXISTS')
times=('\nMSK AL start/end: '+stamp.isoformat()+' / '+datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')+'\n').encode()
(repo/relative).write_bytes(draft+times)
git('add','--',relative);require(git('diff','--cached','--name-only').splitlines()==[relative],'INDEX_EXTRA_FILES')
git('diff','--cached','--check');git('commit','-m','Отчёт: XGW wave3al — wrapper defaults and closure repair')
git('push','origin','HEAD:freepool');print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

REPORT_PUBLISHED/actualcommit нужен. Не менять AK/AJ/AI/AH/AG/AF/AE original reports. Если commit
создался, аpushошибка — не повторять F3/commit; сохранитьSHA/report и сообщитьсбой.
No force/reset/rebase/gitadd. Приdirty/conflict/identity/authproblemSTOP; prefix/footer
не обойти. ALreportнеCinstall permission. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
