# ТЗ Flash: wave3ag — 129 новых FreePool/PoolStore/dependency проверок одним запуском

## 1. Принятый отчёт и весь готовый объём

AFreport 01c84fa9c66fcd67b7bf785a9ff776cb3fcef4fb принят:145/145,40 OWNED writer comparisons,
43 LEGACY/43 FENCED (3 factory constructors отдельно от mutations). HEALTHY/on/pool/
версии/связь сохранены. REVIEW-REAL-MACHINE-0.2.0-wave3af.md уточняет extras:
2completed +6UNKNOWN +8definition/admissionrefusals, НЕ2+4+10. H_SIGNATURE — неверная
ownership signature, H_DEFERRED — generator function definition, deferred RETURN
проверяет H_NESTED_RETURN. AST body proof выполнен архитектором локально, НЕ worker.
Оригинальный report не переписывать. AF145/AE112/AD130/AC51/... не повторять.

Новый весь готовый safe объём:Store10×3=30,Pool18×3=54,constructor3×3=9,extras36=129.
Одинstart/автопереходы/partialdata/одинreport. Не микроТЗ после каждого branch.
При assertionfailure другие независимые cases идут; baseline/source/privacy/audit/
unexpectedFS failure — общий STOP. Не добавлять неготовый live этап ради объёма.

ТОЛЬКО ThinkCentre. WorkingLAN/HEALTHY/on baseline; отдельного LAN client нет и host
не LAN UDP/IPv6/DNS/E4 proof. Preserve WAN/LAN/TS/pin/pool/config/service/live rules.
Nooff/install/G1/новаяSSHопись. Always_off запрещён; independent original-on/code/unit
rescue ДО реального install/fault; incomingoutage>1мин модель следующей командой не лечит.
AG не включает сетевой отказ, actual VPN пробу, timer/guardian/service install/restart.

## 2. Source identity, новые hooks и границы доказательства

Baseline351fb54e074f4a7b497a8a4244fc74c6088788d7. Diff теперь **6A+10M**, source116.
Изменились РОВНО3source files относительно testedAF:freepool/store.py,freepool/pool.py,
ownership_binding.py; остальные113source/oldhelpers/manifests/units/config/pyproject
байт-в-байт сохранены. Store5 иPool8 новых instance hooks PEERS, constructor injection
и3 dependency identity checks. Existing daemon/CLI defaultNone не активируют fence.

PoolStore(paths,ownership=None) не делает I/O, mutators _ensure/commit/prune/retire_openvpn/
save_candidates gated до mkdir/chmod/rotate/unlink/rmtree/write. FreePool optionalownership
передаётся его Store/Backend; foreign injected Backend отказывается ДО filesystem setup/
cleanup и ДО admission. _prune_retired/refresh_due/_prune_candidates/refresh_backend/
_note_handshake/check_some/_check_proxy/_record имеют hooks. Constructor cleanup теперь
writer: explicit-owned FreePool construction получает1 receipt за _prune_retired,
даже empty cleanup. PoolStore constructor остаётся безadmission/receipt. Не путать
это с AF engine constructors, которые сами не writer. None legacy остаётся unfenced.

BoundWriters теперь9objects/50methods (прежние37 +13): дополнительно PoolStore/FreePool,
те же Coordinator/Registry/verifier и intact hooks. Проверяются3 exact references:
xray.api→api, pool.store→pool_store, pool.runtime→peers. До admission и между шагами.
Это object identity graph, НЕ filesystem path alias policy/полный runtime callgraph.
Проверки остальных Resource domains не появились. Full global composition/daemon/CLI/
servicehook/installer/uninstaller/async dispatch/version/boot handshake ещё открыты.

| Артефакт → frozen file | SHA256 |
|---|---|
| tests/stand/wave3_pool_flow.py → batch.py |d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6|
| tests/stand/wave3_source_hooks.py → support.py |9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
| tests/stand/wave3_pool_manifest.json → manifest.json |383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b|

Freeze3+116GitLFsourcefiles в ~/xgw-w3ag0700, files0600/dirs0700, exact inventory/SHA,
никаких extras/symlinks/overwrite. Source inventory не installed116 attestation. Import
private frozen_ad, неизменённый AD support только fixtures/guard/loader; старые CLI/
batch/cases не исполнять. Никаких Yroot/installedsource/liveconfig reads в worker.

Registry boot/clock synthetic, pool/backendclock100000, metadata outcomes искусственные:
latency/bytes/country НЕ измерение скорости/пинга/региона реального VPN. Source setters
иcleanup работают ТОЛЬКО с dummy files в private fixture. Старые profiles/secrets.json
содержат synthetic data, не реальные пароли. ENSURE fixture намеренно имеет nested
dir0755 перед вызовом; это разрешённая private precondition, не chmod реального XGW.
Source outputs с640/644/755 допустимы внутри0700, не менять продукт радиPASS.

Poll/serverhosts/Xray+sing-box probe/reach/tunnel/unavailable/find_binary/guarded/PID
низкоуровневые boundaries подставлены. FakeTunnel вызывает настоящие Backend.prepare/
stop сFakeRunner и dummy manifests, НЕ создаёт veth/netns/процессы/systemd. Литерал
fakePID — константа source, не наблюдение процесса, не публиковать raw argv/manifest.
SSTP/HTTP/DNS/SQL/VPN/livekernel ничего не исполняют. Реальные source bodies для
refresh schedule/ledger/region logic/store rotation/deletion/nested bookkeeping вызываются.
Matrix pool objects созданы legacyNone для setup, затем graph.owner явно injected;
actual constructor propagation отдельно проверяется C9, не подменять одно другим.

Worker ДО source imports: accepted AD CPython audit guard/self-test+2manual probes;
process/socket/fork/exec/kill/ctypes/out-of-noteswrite refused. Trusted regression guard,
не hostile-code sandbox/coarse dirfd limitations прежние. Unexpected denial/OSError/
ScopeStop → globalSTOP/остальныеNOT_RUN. Intentional negative OSError ловится внутри
case и отдельно проверяется UNKNOWN, не permission ослаблять guard.

Разрешены GitFF/NNP/sudo/status/pool readonly, source freeze и обычные userfixture files/
flock/fsync/rename/rmtree/chmod, один detached collector. Workload processes/network/live
gateway ops0. Нет newthread/fakeD. Запреты off/install/G1/enable/disable/WAN/LAN/TS/pin/
pool/config/service/live rules/APIwrites/nft/ip/GET/curl/SOCKS/DNS/ping/SSH/scans/pcap/
netns/speedtest/coreversion/newunits/timers/guardian/arm/replay/fault сохраняются.
Gitдоставка не VPNprobe. Все7 runtimegatesfalse ВСЕГДА, даже129/129.

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
notes=Path.home()/'xgw-w3ag'
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
git('merge-base','--is-ancestor','01c84fa9c66fcd67b7bf785a9ff776cb3fcef4fb','HEAD')
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

### S2.4. Freeze batch/support/manifest и 116 исходников одним блоком

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
os.umask(0o077)
notes=Path.home()/'xgw-w3ag'
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
raw=(repo/'tests/stand/wave3_pool_manifest.json').read_bytes()
freeze(notes/'manifest.json',raw,'383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b')
freeze(notes/'batch.py',(repo/'tests/stand/wave3_pool_flow.py').read_bytes(),'d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6')
freeze(notes/'support.py',(repo/'tests/stand/wave3_source_hooks.py').read_bytes(),'9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917')
data=json.loads(raw)
if type(data) is not dict or len(data)!=116:
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
print('POOL_FLOW_FROZEN',len(data))
PY
```

НуженPOOL_FLOW_FROZEN116/rc0. Existingmatchingfiles допускаютсятолькодляresumeподготовки
доstart; mismatch→STOP_IDENTITY, безoverwrite/newnotes. ЗатемS2.4bобязателен.

#### S2.4b. Полнаяпроверкаfreeze/unused передstart

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ag'
def valid(path,digest):
    info=path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
ok=ok and valid(notes/'batch.py','d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6') and valid(notes/'manifest.json','383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b') and valid(notes/'support.py','9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917')
data=json.loads((notes/'manifest.json').read_bytes())
ok=ok and len(data)==116
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
print('POOL_FLOW_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

ТолькоREADY/rc0→S3.1. Afterstarted→S3.2/S3.3, никакихповторовfreeze/start/worker.

## 5. S3 —129проверок одногоsourceпакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ag/batch.py" start
```

НужныPOOL_FLOW_BATCH_STARTED/rc0. Это Popencollector, не129PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AF145/AE112/AD130 не выполняются.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ag/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ag/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['S_ENSURE__LEGACY', 'S_ENSURE__OWNED', 'S_ENSURE__FENCED', 'S_SUCCESS__LEGACY', 'S_SUCCESS__OWNED', 'S_SUCCESS__FENCED', 'S_PARTIAL__LEGACY', 'S_PARTIAL__OWNED', 'S_PARTIAL__FENCED', 'S_UNAVAILABLE_EMPTY__LEGACY', 'S_UNAVAILABLE_EMPTY__OWNED', 'S_UNAVAILABLE_EMPTY__FENCED', 'S_UNAVAILABLE_EXISTING__LEGACY', 'S_UNAVAILABLE_EXISTING__OWNED', 'S_UNAVAILABLE_EXISTING__FENCED', 'S_ROTATE__LEGACY', 'S_ROTATE__OWNED', 'S_ROTATE__FENCED', 'S_PRUNE__LEGACY', 'S_PRUNE__OWNED', 'S_PRUNE__FENCED', 'S_RETIRE_ALL__LEGACY', 'S_RETIRE_ALL__OWNED', 'S_RETIRE_ALL__FENCED', 'S_RETIRE_NOOP__LEGACY', 'S_RETIRE_NOOP__OWNED', 'S_RETIRE_NOOP__FENCED', 'S_SAVE_CANDIDATES__LEGACY', 'S_SAVE_CANDIDATES__OWNED', 'S_SAVE_CANDIDATES__FENCED', 'P_PRUNE_RETIRED__LEGACY', 'P_PRUNE_RETIRED__OWNED', 'P_PRUNE_RETIRED__FENCED', 'P_REFRESH_SUCCESS__LEGACY', 'P_REFRESH_SUCCESS__OWNED', 'P_REFRESH_SUCCESS__FENCED', 'P_REFRESH_UNAVAILABLE__LEGACY', 'P_REFRESH_UNAVAILABLE__OWNED', 'P_REFRESH_UNAVAILABLE__FENCED', 'P_REFRESH_PARTIAL__LEGACY', 'P_REFRESH_PARTIAL__OWNED', 'P_REFRESH_PARTIAL__FENCED', 'P_REFRESH_TWO__LEGACY', 'P_REFRESH_TWO__OWNED', 'P_REFRESH_TWO__FENCED', 'P_REFRESH_NOT_DUE__LEGACY', 'P_REFRESH_NOT_DUE__OWNED', 'P_REFRESH_NOT_DUE__FENCED', 'P_PRUNE_CANDIDATES__LEGACY', 'P_PRUNE_CANDIDATES__OWNED', 'P_PRUNE_CANDIDATES__FENCED', 'P_REFRESH_BACKEND__LEGACY', 'P_REFRESH_BACKEND__OWNED', 'P_REFRESH_BACKEND__FENCED', 'P_NOTE_HANDSHAKE__LEGACY', 'P_NOTE_HANDSHAKE__OWNED', 'P_NOTE_HANDSHAKE__FENCED', 'P_PROXY_XRAY__LEGACY', 'P_PROXY_XRAY__OWNED', 'P_PROXY_XRAY__FENCED', 'P_PROXY_SINGBOX__LEGACY', 'P_PROXY_SINGBOX__OWNED', 'P_PROXY_SINGBOX__FENCED', 'P_CHECK_PROXY__LEGACY', 'P_CHECK_PROXY__OWNED', 'P_CHECK_PROXY__FENCED', 'P_CHECK_REACH__LEGACY', 'P_CHECK_REACH__OWNED', 'P_CHECK_REACH__FENCED', 'P_CHECK_TUNNEL__LEGACY', 'P_CHECK_TUNNEL__OWNED', 'P_CHECK_TUNNEL__FENCED', 'P_CHECK_CANCEL__LEGACY', 'P_CHECK_CANCEL__OWNED', 'P_CHECK_CANCEL__FENCED', 'P_RECORD_PROXY__LEGACY', 'P_RECORD_PROXY__OWNED', 'P_RECORD_PROXY__FENCED', 'P_RECORD_TUNNEL__LEGACY', 'P_RECORD_TUNNEL__OWNED', 'P_RECORD_TUNNEL__FENCED', 'P_RECORD_LIST__LEGACY', 'P_RECORD_LIST__OWNED', 'P_RECORD_LIST__FENCED', 'C_EMPTY__LEGACY', 'C_EMPTY__OWNED', 'C_EMPTY__FENCED', 'C_RETIRED__LEGACY', 'C_RETIRED__OWNED', 'C_RETIRED__FENCED', 'C_PROVIDED__LEGACY', 'C_PROVIDED__OWNED', 'C_PROVIDED__FENCED', 'E_FOREIGN_NONE', 'E_FOREIGN_OTHER', 'E_STORE_NOIO', 'E_BINDING_NINE', 'E_POOL_STORE_ALIAS', 'E_POOL_RUNTIME_ALIAS', 'E_APPLIER_API_ALIAS', 'E_POOL_UNBOUND', 'H_STORE_ENSURE', 'H_STORE_COMMIT', 'H_STORE_PRUNE', 'H_STORE_RETIRE', 'H_STORE_SAVE', 'H_POOL_PRUNE', 'H_POOL_REFRESH', 'H_POOL_CANDIDATES', 'H_POOL_BACKEND', 'H_POOL_HANDSHAKE', 'H_POOL_CHECK', 'H_POOL_PROXY', 'H_POOL_RECORD', 'E_PRUNE_ERROR', 'E_RECONCILE_ERROR', 'E_ROTATE_ERROR', 'E_PROBE_ERROR', 'E_STOP_ERROR', 'E_VERIFIER_FALSE', 'R_SUMMARY', 'R_NEXT_CHECKS', 'R_SPENT', 'R_HANDSHAKES', 'R_VARIANTS', 'R_STORE_SNAPSHOT', 'R_STORE_CANDIDATES', 'I_REFRESH_CHECK', 'I_SECOND_FAIL']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='OPTIONAL_POOL_STORE_AND_DECLARED_DEPENDENCIES_ONLY' and data.get('expected')==129
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==129-len(rows) and len(rows)<=129 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='POOL_FLOW_BATCH_RECORDED' and data.get('completed')==129
      and data.get('passed')==129 and all(r.get('passed') is True for r in rows)
      and data.get('audit_registered') is True and data.get('unexpected_forbidden_io')==0
      and data.get('source_files')==116 and data.get('remaining_not_run')==0
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

### S4.3. Интерпретация cases, partial data и исходной совместимости

S30/P54 — 28 writer variants×LEGACY/OWNED/FENCED. LEGACY: business enum +receipts0,
private fingerprint дерева и in-memory next_refresh/failures/backend flags/leasecount,
stubcount держатся только в памяти. OWNED сравнивает их ДО completion с LEGACY,
один receipt/generation, даже при NOOP/empty list; это caller fixture assertion.
FENCED — отказ до body; дерево/память неизменны, trace0/receipt0. Missing reference
означает UNKNOWN/failed OWNED comparison, не выдуманный PASS; другие варианты идут.
Сравниваются bytes/modes/uid/nlink/entries, не mtime и не registry/case artifacts.

C9 — actual FreePool constructor EMPTY/RETIRED/PROVIDED в трёх режимах: nested Store/
Backend ownership identity и providedBackend identity. OWNED1receipt за cleanup;
FENCED не удаляет synthetic retired snapshots/profiles/secrets/candidates. Простое
создание PoolStore I/Oне делает и ticketне создаёт. Все constructor memory allocations
до _prune_retired не filesystem effects. E_FOREIGN* отказывает доadmission, receipt0.

Extras36:8base/13hookshadows/6expected errors/7readers/2integrations. E_BINDING_NINE
только readonly declarationvalidation9/50, не pipeline execution. 3foreignreference
aliases и unbound pool отказываются. Readers работают подsynthetic lease безreceipt/
измененияfixtures. H13 — подмены всех новых hooks, business body не запускается.
E_PRUNE_ERROR — подавленный businessOSError всё равно taints outer; cleanup других
dummyfiles может продолжиться. E_ROTATE_ERROR может оставить current перемещённым в
history. E_STOP_ERROR — пойманный nested nft stub error не разрешает completion,
несмотря на последующий synthetic OK record. E_RECONCILE/PROBE/VERIFIERFALSE остальные
expected negatives. Все6errors UNKNOWN1/receipt0, не успешные restores/проверкиVPN.

I_REFRESH_CHECK:9actors/50hooks, preparedbatch refresh→check, однаfinalreceipt/generation,
rolesLIFECYCLE+PEERS, раннийlease отказан. I_SECOND_FAIL: первыйsnapshot остаётся после
второгоstubprobeOSError, UNKNOWN1/receipt0, неrollback/auto-retry. Итог extras:1 positive
completion,7 UNKNOWN(6errors+I_SECOND_FAIL),21pre-admission/definition/identity cases
(8base+13shadows),7readonlycases. E_BINDING_NINE/E_STORE_NOIO из21 не отказы, не называть
все21refusals. No data invention при partial: nullable details остаютсяnull, не0.

Business enums NONE/TRUE/FALSE/ZERO/ONE/OTHER_INT/TEXT/EMPTY_TEXT/LIST/DICT/TUPLE/POOL/
OUTCOME — не command rc; OUTCOME synthetic, не server-online proof. Ошибка сохраняет
actual nullable counts/expected-observed/legacy_equivalent/fixture_unchanged/rejection/
completion и errorclass/public repo source:line. Private fingerprints/содержимое/trace/
argv/result text/exception не публиковать. partialsummary/progress/remainingNOT_RUN
не подменять completedPASS. Никакого retry/newnotes/killworker при отсутствии результата.

| Группа | Точные case IDs |
|---|---|
|Case|S_ENSURE__LEGACY|
|Case|S_ENSURE__OWNED|
|Case|S_ENSURE__FENCED|
|Case|S_SUCCESS__LEGACY|
|Case|S_SUCCESS__OWNED|
|Case|S_SUCCESS__FENCED|
|Case|S_PARTIAL__LEGACY|
|Case|S_PARTIAL__OWNED|
|Case|S_PARTIAL__FENCED|
|Case|S_UNAVAILABLE_EMPTY__LEGACY|
|Case|S_UNAVAILABLE_EMPTY__OWNED|
|Case|S_UNAVAILABLE_EMPTY__FENCED|
|Case|S_UNAVAILABLE_EXISTING__LEGACY|
|Case|S_UNAVAILABLE_EXISTING__OWNED|
|Case|S_UNAVAILABLE_EXISTING__FENCED|
|Case|S_ROTATE__LEGACY|
|Case|S_ROTATE__OWNED|
|Case|S_ROTATE__FENCED|
|Case|S_PRUNE__LEGACY|
|Case|S_PRUNE__OWNED|
|Case|S_PRUNE__FENCED|
|Case|S_RETIRE_ALL__LEGACY|
|Case|S_RETIRE_ALL__OWNED|
|Case|S_RETIRE_ALL__FENCED|
|Case|S_RETIRE_NOOP__LEGACY|
|Case|S_RETIRE_NOOP__OWNED|
|Case|S_RETIRE_NOOP__FENCED|
|Case|S_SAVE_CANDIDATES__LEGACY|
|Case|S_SAVE_CANDIDATES__OWNED|
|Case|S_SAVE_CANDIDATES__FENCED|
|Case|P_PRUNE_RETIRED__LEGACY|
|Case|P_PRUNE_RETIRED__OWNED|
|Case|P_PRUNE_RETIRED__FENCED|
|Case|P_REFRESH_SUCCESS__LEGACY|
|Case|P_REFRESH_SUCCESS__OWNED|
|Case|P_REFRESH_SUCCESS__FENCED|
|Case|P_REFRESH_UNAVAILABLE__LEGACY|
|Case|P_REFRESH_UNAVAILABLE__OWNED|
|Case|P_REFRESH_UNAVAILABLE__FENCED|
|Case|P_REFRESH_PARTIAL__LEGACY|
|Case|P_REFRESH_PARTIAL__OWNED|
|Case|P_REFRESH_PARTIAL__FENCED|
|Case|P_REFRESH_TWO__LEGACY|
|Case|P_REFRESH_TWO__OWNED|
|Case|P_REFRESH_TWO__FENCED|
|Case|P_REFRESH_NOT_DUE__LEGACY|
|Case|P_REFRESH_NOT_DUE__OWNED|
|Case|P_REFRESH_NOT_DUE__FENCED|
|Case|P_PRUNE_CANDIDATES__LEGACY|
|Case|P_PRUNE_CANDIDATES__OWNED|
|Case|P_PRUNE_CANDIDATES__FENCED|
|Case|P_REFRESH_BACKEND__LEGACY|
|Case|P_REFRESH_BACKEND__OWNED|
|Case|P_REFRESH_BACKEND__FENCED|
|Case|P_NOTE_HANDSHAKE__LEGACY|
|Case|P_NOTE_HANDSHAKE__OWNED|
|Case|P_NOTE_HANDSHAKE__FENCED|
|Case|P_PROXY_XRAY__LEGACY|
|Case|P_PROXY_XRAY__OWNED|
|Case|P_PROXY_XRAY__FENCED|
|Case|P_PROXY_SINGBOX__LEGACY|
|Case|P_PROXY_SINGBOX__OWNED|
|Case|P_PROXY_SINGBOX__FENCED|
|Case|P_CHECK_PROXY__LEGACY|
|Case|P_CHECK_PROXY__OWNED|
|Case|P_CHECK_PROXY__FENCED|
|Case|P_CHECK_REACH__LEGACY|
|Case|P_CHECK_REACH__OWNED|
|Case|P_CHECK_REACH__FENCED|
|Case|P_CHECK_TUNNEL__LEGACY|
|Case|P_CHECK_TUNNEL__OWNED|
|Case|P_CHECK_TUNNEL__FENCED|
|Case|P_CHECK_CANCEL__LEGACY|
|Case|P_CHECK_CANCEL__OWNED|
|Case|P_CHECK_CANCEL__FENCED|
|Case|P_RECORD_PROXY__LEGACY|
|Case|P_RECORD_PROXY__OWNED|
|Case|P_RECORD_PROXY__FENCED|
|Case|P_RECORD_TUNNEL__LEGACY|
|Case|P_RECORD_TUNNEL__OWNED|
|Case|P_RECORD_TUNNEL__FENCED|
|Case|P_RECORD_LIST__LEGACY|
|Case|P_RECORD_LIST__OWNED|
|Case|P_RECORD_LIST__FENCED|
|Case|C_EMPTY__LEGACY|
|Case|C_EMPTY__OWNED|
|Case|C_EMPTY__FENCED|
|Case|C_RETIRED__LEGACY|
|Case|C_RETIRED__OWNED|
|Case|C_RETIRED__FENCED|
|Case|C_PROVIDED__LEGACY|
|Case|C_PROVIDED__OWNED|
|Case|C_PROVIDED__FENCED|
|Case|E_FOREIGN_NONE|
|Case|E_FOREIGN_OTHER|
|Case|E_STORE_NOIO|
|Case|E_BINDING_NINE|
|Case|E_POOL_STORE_ALIAS|
|Case|E_POOL_RUNTIME_ALIAS|
|Case|E_APPLIER_API_ALIAS|
|Case|E_POOL_UNBOUND|
|Case|H_STORE_ENSURE|
|Case|H_STORE_COMMIT|
|Case|H_STORE_PRUNE|
|Case|H_STORE_RETIRE|
|Case|H_STORE_SAVE|
|Case|H_POOL_PRUNE|
|Case|H_POOL_REFRESH|
|Case|H_POOL_CANDIDATES|
|Case|H_POOL_BACKEND|
|Case|H_POOL_HANDSHAKE|
|Case|H_POOL_CHECK|
|Case|H_POOL_PROXY|
|Case|H_POOL_RECORD|
|Case|E_PRUNE_ERROR|
|Case|E_RECONCILE_ERROR|
|Case|E_ROTATE_ERROR|
|Case|E_PROBE_ERROR|
|Case|E_STOP_ERROR|
|Case|E_VERIFIER_FALSE|
|Case|R_SUMMARY|
|Case|R_NEXT_CHECKS|
|Case|R_SPENT|
|Case|R_HANDSHAKES|
|Case|R_VARIANTS|
|Case|R_STORE_SNAPSHOT|
|Case|R_STORE_CANDIDATES|
|Case|I_REFRESH_CHECK|
|Case|I_SECOND_FAIL|

## 7. Один обезличенный итоговый отчёт

Заполнить TEMPLATE в ~/xgw-w3ag/report.md. Actual HEAD/tree/source6A10M/3SHA/116freeze/
modes/NNP/sudo/owneractions/HEALTHY/on/pool/versions/connection bookends. Start/monitor/
show/shape commandrc РАЗДЕЛЬНО; collector_exit_rcNOT_COLLECTED. Весь129case readout,
S30/P54/C9/E36counts; OWNEDwriter28+constructors3 отдельно отreadonly и8preflightbase.
Expected/completed/passed/remaining/nullable counts actual. Нет actualVPN/performance/
kernel/install доказательств. Только один Markdown, без microbranch reports.

Весь Markdown прочитать перед однимF3. Не Git/чат/скрин rawconfig/status/log/kernel/
URI/IP/MAC/UUID/secrets/SNI/ports/fp/tags/PID/NIC/UID/home/boot/registryids/tokens/private
hashes/fingerprints/casefiles/argv/business texts/exceptions. Только fixedcaseIDs/enums/
bools/counts/ms/rc/Git/sourceSHA/publicrepo:line. 116manifesthashes вreport не вставлять.

OnlyThinkCentre/workingLAN, hostнеLANclient. Никакой установки/активации поPASS. Далее
evidencefixes либо максимальныйготовый runtimecomposition/fullinventory/handshake/
resourceverifiers/repair/bootstrapdryпакет. LiveC BLOCKED_BOOTSTRAP; realEнужныC+D+
independentoriginalon/code/unitrescue. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/
allTS открыты,неwave4/DAE. Реальный AG NOT_RUN до фактического отчёта.

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
notes=Path.home()/'xgw-w3ag'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M', 'src/xgw/freepool/pool.py': 'M', 'src/xgw/freepool/store.py': 'M'}
require(git('diff','--name-status',code,'HEAD','--',*runtime).splitlines()==[expected[name]+'\t'+name for name in sorted(expected)],'source diff не6A10M')
require(hashlib.sha256((repo/'tests/stand/wave3_pool_manifest.json').read_bytes()).hexdigest()=='383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b','manifest SHA изменился')
for name,digest in json.loads((repo/'tests/stand/wave3_pool_manifest.json').read_bytes()).items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'source SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_pool_flow.py').read_bytes()).hexdigest()=='d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6','helper SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','support SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3ag — FreePool PoolStore и declared dependency binding')
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
