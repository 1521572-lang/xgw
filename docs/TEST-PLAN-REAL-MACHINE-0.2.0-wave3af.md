# ТЗ Flash: wave3af — 145 новых source-flow/factory проверок за один заход

## 1. Основание и максимальный готовый объём

Отчёт AE 7da3b74ce70f0620e0bd634078ab8e4aabb13280 принят:112/112,4 positive composites/13 expected negatives,
3 positive file observations/21 refusals, HEALTHY/on/pool/версии/связь сохранены.
Метка HEALTHY15:31 не изменилась. REVIEW-REAL-MACHINE-0.2.0-wave3ae.md.
AE112/AD130/AC51/AB32/AA22/Z19/Y6/X26/W25 и старые batches не повторять.

Новый весь готовый safe объём:26 panel variants×3режима=78;14 core variants×3=42;
3factory variants×3=9;16extras. Всего145 новых cases, один start, автопереходы,
partial data и один итоговый Markdown. Case failure — остальные независимые cases
продолжаются; source/baseline/privacy/audit/непригодный FS — общий STOP.

ТОЛЬКО ThinkCentre. Отдельного LAN-клиента нет. Работающий LAN/HEALTHY/on baseline;
host не LAN UDP/IPv6/DNS/E4 proof. Никакого install/off/G1/новой SSH-описи/WAN/LAN/TS/
pin/pool/config/service/live rules. Always_off запрещён; incoming outage>1мин модель
следующей командой не исправит. AF не создаёт отказ сети, не guardian/rescue protocol.

## 2. Source identity, изменения и разрешённые эффекты

Baseline351fb54e074f4a7b497a8a4244fc74c6088788d7; source diff теперь **6A+8M**:
шесть ownership*.py добавлены, восемь legacy modules modified (новый восьмой engine.py).
Относительно testedAE изменились РОВНО5 source files: ownership_hooks.py,
ownership_binding.py,managed.py,cores.py,engine.py; другие111 source files байт-в-байт
сохранены. Ни нового src модуля, ни runtime activation. Старые stand helpers/manifests/
units/config/pyproject сохранены. Installed runtime не обновляется/не импортируется.

owned_function требует synchronous free function с keyword-only ownership=None;
сохраняет signature, original return/exception, использует тот же Coordinator.
23 публичных managed writers, direct save и _update_locked теперь имеют такой вход;
_update/_update_locked/save передают ownership далее. Admission до validation/read/lock/
write, если explicit coordinator задан. None остаётся legacy и unfenced.

Core Job.run/_reject/_stage/_save/_event получили instance hooks;6 free functions
save_state/forget/start/take_request/check/run_request получили hooks. Это закрывает
ранние state write/request unlink ДО update hook. run_request передаёт coordinator в
take_request/новый Job; чужой injected Job отказывается до чтения/удаления request
внутри outer ticket. Это отказ после admission с UNKNOWN, не отсутствие ticket.
Binding boundary обновлён с32 до37 методов (5 новых Job hooks). Фабрики make_api,
make_applier,make_singbox передают optional coordinator; Applier.api получает тот же.
Фабрика сама не writer admission: создание explicit-owned объекта даёт receipts0.

Глобальный runtime composition НЕ готов: текущие daemon/CLI/service callers по-прежнему
не задают coordinator; FreePool constructor/prune и другие прямые/вложенные writers,
path aliases и межпроцессный/version/boot handshake ещё открыты. Core.start только
ставит request и асинхронно просит systemd --no-block: его source hook НЕ удерживает
ticket на весь срок отдельной службы; cross-process dispatch/fence ещё не реализован.
Не выдавать 145PASS за runtime fence. Полный concrete verifier/repair/bootstrap отсутствуют.

| Артефакт → frozen file | SHA256 |
|---|---|
| tests/stand/wave3_source_flow.py → batch.py |1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8|
| tests/stand/wave3_source_hooks.py → support.py |9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
| tests/stand/wave3_flow_manifest.json → manifest.json |ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82|

116 source *.py по manifest; source inventory НЕ installed116 attestation. Freeze3+116
в ~/xgw-w3af: owner0700 dirs/files0600, exact SHA/LF/no extras/symlinks. Хеши считаются
по опубликованным Git LF bytes. Support неизменённый AD helper: только fixtures/guard/
loader, НЕ его старые CLI/batch/cases. Import private frozen_ad package.

Все factory/service/runner/release/Store boundaries подставные. Actual source bodies
меняют ТОЛЬКО fixture JSON/dummy binaries/text; не скачивают/не исполняют ядра, не
запускают systemctl/API/socket/HTTP/DB. Store stub не SQLite proof; release stub не
GitHub query. Factories используют stub find_binary/services, не version probes.
Core rollback/forget удаляет/перемещает только dummy dirs в private notes. Реальные
source product modes0640/0644/0755 допустимы в0700, не chmod продукта ради PASS.
Registry boot/lease clock synthetic; Job.now в матрице10, default Job factory может
писать real wall timestamp только в private dummy JSON — это не deadline proof.
Default Job factory обёрнут recorder: вызывается реальный constructor, проверяются
exact type/ownership и actual job state/request removal, не только число receipts.

Worker ДО source imports ставит неизменённый AD audit guard/self-test+2manual probes:
process/socket/fork/exec/kill/ctypes/out-of-notes write refused. Trusted regression guard,
НЕ hostile-code security sandbox, coarse dirfd ограничения прежние. Unexpected denial
или unexpected OSError/ScopeStop — failed case + globalSTOP, остальные NOT_RUN.
При обычном business assertion mismatch остальные независимые cases продолжаются.

Разрешены Git FF/NNP/sudo/status/pool readonly, private source freeze/user fixture writes/
flock/fsync/rename/rmtree, один detached user collector. Workload subprocesses/network/
live gateway ops0. Ни thread fixture, ни fakeD повторно нет. Никаких live /runXGW/Yroot/
installed source/control socket/config/log/kernel reads в worker. Запреты install/off/
G1/enable/disable/WAN/LAN/TS/pin/pool/config/service/rules/APIwrites/nft/ip/GET/curl/SOCKS/
DNS/ping/SSH/scans/pcap/netns/speedtest/newunits/timers/guardian/arm/replay/live fault.
Git доставка не VPN probe. Все7 runtime gates всегдаfalse, даже при145/145.

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
notes=Path.home()/'xgw-w3af'
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

### S2.1. Чистаяfreepool/FF/6A+8M и publicsourceManifest

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
git('merge-base','--is-ancestor','7da3b74ce70f0620e0bd634078ab8e4aabb13280','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_6A_8M')
manifest=repo/'tests/stand/wave3_flow_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==116,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_flow.py').read_bytes()).hexdigest()=='1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')
print('SOURCE_DIFF_SIX_ADD_EIGHT_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужныrc0/SOURCE_DIFF_SIX_ADD_EIGHT_MODIFY/SOURCE_MANIFEST_MATCHED116/SOURCE_PREFLIGHT_OK.
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
notes=Path.home()/'xgw-w3af'
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
raw=(repo/'tests/stand/wave3_flow_manifest.json').read_bytes()
freeze(notes/'manifest.json',raw,'ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82')
freeze(notes/'batch.py',(repo/'tests/stand/wave3_source_flow.py').read_bytes(),'1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8')
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
print('SOURCE_FLOW_FROZEN',len(data))
PY
```

НуженSOURCE_FLOW_FROZEN116/rc0. Existingmatchingfiles допускаютсятолькодляresumeподготовки
доstart; mismatch→STOP_IDENTITY, безoverwrite/newnotes. ЗатемS2.4bобязателен.

#### S2.4b. Полнаяпроверкаfreeze/unused передstart

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3af'
def valid(path,digest):
    info=path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
ok=ok and valid(notes/'batch.py','1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8') and valid(notes/'manifest.json','ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82') and valid(notes/'support.py','9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917')
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
print('SOURCE_FLOW_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

ТолькоREADY/rc0→S3.1. Afterstarted→S3.2/S3.3, никакихповторовfreeze/start/worker.

## 5. S3 —145проверок одногоsourceпакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3af/batch.py" start
```

НужныSOURCE_FLOW_BATCH_STARTED/rc0. Это Popencollector, не145PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AE112/AD130 не выполняются.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3af/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3af/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['P_SET_FREE_POOL_MODE__LEGACY', 'P_SET_FREE_POOL_MODE__OWNED', 'P_SET_FREE_POOL_MODE__FENCED', 'P_SET_FREE_POOL_PIN__LEGACY', 'P_SET_FREE_POOL_PIN__OWNED', 'P_SET_FREE_POOL_PIN__FENCED', 'P_SET_TAILSCALE_DIRECT__LEGACY', 'P_SET_TAILSCALE_DIRECT__OWNED', 'P_SET_TAILSCALE_DIRECT__FENCED', 'P_REPLACE_TAILSCALE_DIRECT__LEGACY', 'P_REPLACE_TAILSCALE_DIRECT__OWNED', 'P_REPLACE_TAILSCALE_DIRECT__FENCED', 'P_SET_DEVICE__LEGACY', 'P_SET_DEVICE__OWNED', 'P_SET_DEVICE__FENCED', 'P_REPLACE_DEVICES__LEGACY', 'P_REPLACE_DEVICES__OWNED', 'P_REPLACE_DEVICES__FENCED', 'P_SET_KERNEL_DEVICE__LEGACY', 'P_SET_KERNEL_DEVICE__OWNED', 'P_SET_KERNEL_DEVICE__FENCED', 'P_SPLIT_KERNEL_DIRECT__LEGACY', 'P_SPLIT_KERNEL_DIRECT__OWNED', 'P_SPLIT_KERNEL_DIRECT__FENCED', 'P_SET_ROUTE__LEGACY', 'P_SET_ROUTE__OWNED', 'P_SET_ROUTE__FENCED', 'P_SET_SERVERS__LEGACY', 'P_SET_SERVERS__OWNED', 'P_SET_SERVERS__FENCED', 'P_SET_PRIORITY__LEGACY', 'P_SET_PRIORITY__OWNED', 'P_SET_PRIORITY__FENCED', 'P_SET_CORE__LEGACY', 'P_SET_CORE__OWNED', 'P_SET_CORE__FENCED', 'P_SET_STICKY__LEGACY', 'P_SET_STICKY__OWNED', 'P_SET_STICKY__FENCED', 'P_SET_KERNEL_DIRECT__LEGACY', 'P_SET_KERNEL_DIRECT__OWNED', 'P_SET_KERNEL_DIRECT__FENCED', 'P_SET_TAILSCALE_SERVE__LEGACY', 'P_SET_TAILSCALE_SERVE__OWNED', 'P_SET_TAILSCALE_SERVE__FENCED', 'P_SET_TAILSCALE_FUNNEL__LEGACY', 'P_SET_TAILSCALE_FUNNEL__OWNED', 'P_SET_TAILSCALE_FUNNEL__FENCED', 'P_SET_TAILSCALE_ROUTE__LEGACY', 'P_SET_TAILSCALE_ROUTE__OWNED', 'P_SET_TAILSCALE_ROUTE__FENCED', 'P_DROP_TELEGRAM__LEGACY', 'P_DROP_TELEGRAM__OWNED', 'P_DROP_TELEGRAM__FENCED', 'P_ADD_SUBSCRIPTION__LEGACY', 'P_ADD_SUBSCRIPTION__OWNED', 'P_ADD_SUBSCRIPTION__FENCED', 'P_UPDATE_SUBSCRIPTION__LEGACY', 'P_UPDATE_SUBSCRIPTION__OWNED', 'P_UPDATE_SUBSCRIPTION__FENCED', 'P_REMOVE_SUBSCRIPTION__LEGACY', 'P_REMOVE_SUBSCRIPTION__OWNED', 'P_REMOVE_SUBSCRIPTION__FENCED', 'P_ADD_LINKS__LEGACY', 'P_ADD_LINKS__OWNED', 'P_ADD_LINKS__FENCED', 'P_REMOVE_LINK__LEGACY', 'P_REMOVE_LINK__OWNED', 'P_REMOVE_LINK__FENCED', 'P_SAVE__LEGACY', 'P_SAVE__OWNED', 'P_SAVE__FENCED', 'P__UPDATE_LOCKED__LEGACY', 'P__UPDATE_LOCKED__OWNED', 'P__UPDATE_LOCKED__FENCED', 'P__UPDATE__LEGACY', 'P__UPDATE__OWNED', 'P__UPDATE__FENCED', 'K_SAVE_STATE__LEGACY', 'K_SAVE_STATE__OWNED', 'K_SAVE_STATE__FENCED', 'K_FORGET__LEGACY', 'K_FORGET__OWNED', 'K_FORGET__FENCED', 'K_START__LEGACY', 'K_START__OWNED', 'K_START__FENCED', 'K_TAKE_BAD__LEGACY', 'K_TAKE_BAD__OWNED', 'K_TAKE_BAD__FENCED', 'K_TAKE_VALID__LEGACY', 'K_TAKE_VALID__OWNED', 'K_TAKE_VALID__FENCED', 'K_CHECK__LEGACY', 'K_CHECK__OWNED', 'K_CHECK__FENCED', 'K_RUN_REQUEST__LEGACY', 'K_RUN_REQUEST__OWNED', 'K_RUN_REQUEST__FENCED', 'K_RUN_REQUEST_EMPTY__LEGACY', 'K_RUN_REQUEST_EMPTY__OWNED', 'K_RUN_REQUEST_EMPTY__FENCED', 'K_JOB_RUN__LEGACY', 'K_JOB_RUN__OWNED', 'K_JOB_RUN__FENCED', 'K_JOB_RUN_ROLLBACK__LEGACY', 'K_JOB_RUN_ROLLBACK__OWNED', 'K_JOB_RUN_ROLLBACK__FENCED', 'K_JOB_REJECT__LEGACY', 'K_JOB_REJECT__OWNED', 'K_JOB_REJECT__FENCED', 'K_JOB_STAGE__LEGACY', 'K_JOB_STAGE__OWNED', 'K_JOB_STAGE__FENCED', 'K_JOB_SAVE__LEGACY', 'K_JOB_SAVE__OWNED', 'K_JOB_SAVE__FENCED', 'K_JOB_EVENT__LEGACY', 'K_JOB_EVENT__OWNED', 'K_JOB_EVENT__FENCED', 'F_API__LEGACY', 'F_API__OWNED', 'F_API__FENCED', 'F_APPLIER__LEGACY', 'F_APPLIER__OWNED', 'F_APPLIER__FENCED', 'F_SINGBOX__LEGACY', 'F_SINGBOX__OWNED', 'F_SINGBOX__FENCED', 'H_SIGNATURE', 'H_DEFERRED', 'H_NO_VERIFIER', 'H_NESTED_ERROR', 'H_NESTED_RETURN', 'K_RUN_FAILED', 'K_RUN_INVALID', 'K_REQUEST_FOREIGN', 'K_REQUEST_NO_JOB', 'K_SWALLOWED_SAVE', 'I_PANEL_CORE', 'B_RUN_SHADOW', 'B_REJECT_SHADOW', 'B_STAGE_SHADOW', 'B_SAVE_SHADOW', 'B_EVENT_SHADOW']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='OPTIONAL_SOURCE_FLOW_AND_FACTORY_PROPAGATION_ONLY' and data.get('expected')==145
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==145-len(rows) and len(rows)<=145 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='SOURCE_FLOW_BATCH_RECORDED' and data.get('completed')==145
      and data.get('passed')==145 and all(r.get('passed') is True for r in rows)
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

### S4.3. Результаты матрицы и исходная совместимость

P26×3=78:23 публичных panel writers +save/_update_locked/_update. K14×3=42:
6 core free functions в8 вариантах +6 Job сценариев (run update/rollback и4 helpers).
LEGACY: ownershipNone, business return class проверен, receipts0. После него приватный
fingerprint fixture content/modes/uid/nlink/entries и stub count держатся ТОЛЬКО в памяти.
OWNED: тот же business return и те же bytes/modes/entries/stub count, ровно1 final receipt/
generation, нет intermediate nested publications. Сравнение с LEGACY ДО completion
в fixture verifier, не checksum сам с собой. Все direct/new helpers проходят real source.
FENCED: refusal до body (включая validation и early unlink), fixture_unchanged=true,
stub trace0, receipts0. Проверка выполняется независимо от успешности LEGACY.

Если LEGACY reference не получен, OWNED может записать private effects, но fixture
verifier откажет, останется UNKNOWN; rowfailed/legacy_equivalentnull, НЕ false PASS.
Другие варианты/ветви продолжаются. Missing comparison не permissionretry.
Это differential совместимость с source bodies, дополнительно старые тела проверены AST.
Это НЕ concrete runtime resource verifier: generic fixture FILES assertion, не KERNEL/API.

F3×3=9: фабрики создают реальные ApiClient/Applier/SingboxCore с optional coordinator,
у Applier.api тот же coordinator. LEGACY/OWNED — только constructor/identity, receipts0.
FENCED — ещё arm synthetic lease и вызов mutator: refusal до validator/runner/service.
OWNED factory не значит owned mutation, не приписывать ему receipt1.

16extras: signature/generator/no-verifier/nestedtaint/deferredreturn; failed/invalid Job,
foreign injected Job, automatic Job construction, swallowed OSError, PANEL→CORE composite,
пять shadows новых Job hooks. K_REQUEST_NO_JOB/I_PANEL_CORE — по1 receipt; I_PANEL_CORE
рольunionPANEL/CORE/LIFECYCLE, без раннего lease/receipt. K_RUN_FAILED/K_RUN_INVALID/
K_REQUEST_FOREIGN/K_SWALLOWED_SAVE — UNKNOWN1/receipt0; failed job может записать failed
state, это не rollback/успех. Definition/refusal cases не business completion.
5new hook shadows проверяют declaration boundary37, business body не вызывается.

Expected/observed return enums: NONE/TRUE/FALSE/TEXT/EMPTY_TEXT/ZERO/ONE/OTHER_INT/DICT/
TUPLE/UNSUPPORTED. Это business result, НЕ command exit rc. При отказе observed_return
может оставатьсяnull, не считать0. K_START emptytext/command trace не actual service run.
Записывать actual nullable legacy_equivalent/fixture_unchanged/rejection_observed/
completion_verified, receipts/generation/unknown/stub counts и public error class/source:line.
Не публиковать сами fingerprints/JSON/strings/argv/trace/exception/private paths.

| Группа | Точные case IDs |
|---|---|
|Case|P_SET_FREE_POOL_MODE__LEGACY|
|Case|P_SET_FREE_POOL_MODE__OWNED|
|Case|P_SET_FREE_POOL_MODE__FENCED|
|Case|P_SET_FREE_POOL_PIN__LEGACY|
|Case|P_SET_FREE_POOL_PIN__OWNED|
|Case|P_SET_FREE_POOL_PIN__FENCED|
|Case|P_SET_TAILSCALE_DIRECT__LEGACY|
|Case|P_SET_TAILSCALE_DIRECT__OWNED|
|Case|P_SET_TAILSCALE_DIRECT__FENCED|
|Case|P_REPLACE_TAILSCALE_DIRECT__LEGACY|
|Case|P_REPLACE_TAILSCALE_DIRECT__OWNED|
|Case|P_REPLACE_TAILSCALE_DIRECT__FENCED|
|Case|P_SET_DEVICE__LEGACY|
|Case|P_SET_DEVICE__OWNED|
|Case|P_SET_DEVICE__FENCED|
|Case|P_REPLACE_DEVICES__LEGACY|
|Case|P_REPLACE_DEVICES__OWNED|
|Case|P_REPLACE_DEVICES__FENCED|
|Case|P_SET_KERNEL_DEVICE__LEGACY|
|Case|P_SET_KERNEL_DEVICE__OWNED|
|Case|P_SET_KERNEL_DEVICE__FENCED|
|Case|P_SPLIT_KERNEL_DIRECT__LEGACY|
|Case|P_SPLIT_KERNEL_DIRECT__OWNED|
|Case|P_SPLIT_KERNEL_DIRECT__FENCED|
|Case|P_SET_ROUTE__LEGACY|
|Case|P_SET_ROUTE__OWNED|
|Case|P_SET_ROUTE__FENCED|
|Case|P_SET_SERVERS__LEGACY|
|Case|P_SET_SERVERS__OWNED|
|Case|P_SET_SERVERS__FENCED|
|Case|P_SET_PRIORITY__LEGACY|
|Case|P_SET_PRIORITY__OWNED|
|Case|P_SET_PRIORITY__FENCED|
|Case|P_SET_CORE__LEGACY|
|Case|P_SET_CORE__OWNED|
|Case|P_SET_CORE__FENCED|
|Case|P_SET_STICKY__LEGACY|
|Case|P_SET_STICKY__OWNED|
|Case|P_SET_STICKY__FENCED|
|Case|P_SET_KERNEL_DIRECT__LEGACY|
|Case|P_SET_KERNEL_DIRECT__OWNED|
|Case|P_SET_KERNEL_DIRECT__FENCED|
|Case|P_SET_TAILSCALE_SERVE__LEGACY|
|Case|P_SET_TAILSCALE_SERVE__OWNED|
|Case|P_SET_TAILSCALE_SERVE__FENCED|
|Case|P_SET_TAILSCALE_FUNNEL__LEGACY|
|Case|P_SET_TAILSCALE_FUNNEL__OWNED|
|Case|P_SET_TAILSCALE_FUNNEL__FENCED|
|Case|P_SET_TAILSCALE_ROUTE__LEGACY|
|Case|P_SET_TAILSCALE_ROUTE__OWNED|
|Case|P_SET_TAILSCALE_ROUTE__FENCED|
|Case|P_DROP_TELEGRAM__LEGACY|
|Case|P_DROP_TELEGRAM__OWNED|
|Case|P_DROP_TELEGRAM__FENCED|
|Case|P_ADD_SUBSCRIPTION__LEGACY|
|Case|P_ADD_SUBSCRIPTION__OWNED|
|Case|P_ADD_SUBSCRIPTION__FENCED|
|Case|P_UPDATE_SUBSCRIPTION__LEGACY|
|Case|P_UPDATE_SUBSCRIPTION__OWNED|
|Case|P_UPDATE_SUBSCRIPTION__FENCED|
|Case|P_REMOVE_SUBSCRIPTION__LEGACY|
|Case|P_REMOVE_SUBSCRIPTION__OWNED|
|Case|P_REMOVE_SUBSCRIPTION__FENCED|
|Case|P_ADD_LINKS__LEGACY|
|Case|P_ADD_LINKS__OWNED|
|Case|P_ADD_LINKS__FENCED|
|Case|P_REMOVE_LINK__LEGACY|
|Case|P_REMOVE_LINK__OWNED|
|Case|P_REMOVE_LINK__FENCED|
|Case|P_SAVE__LEGACY|
|Case|P_SAVE__OWNED|
|Case|P_SAVE__FENCED|
|Case|P__UPDATE_LOCKED__LEGACY|
|Case|P__UPDATE_LOCKED__OWNED|
|Case|P__UPDATE_LOCKED__FENCED|
|Case|P__UPDATE__LEGACY|
|Case|P__UPDATE__OWNED|
|Case|P__UPDATE__FENCED|
|Case|K_SAVE_STATE__LEGACY|
|Case|K_SAVE_STATE__OWNED|
|Case|K_SAVE_STATE__FENCED|
|Case|K_FORGET__LEGACY|
|Case|K_FORGET__OWNED|
|Case|K_FORGET__FENCED|
|Case|K_START__LEGACY|
|Case|K_START__OWNED|
|Case|K_START__FENCED|
|Case|K_TAKE_BAD__LEGACY|
|Case|K_TAKE_BAD__OWNED|
|Case|K_TAKE_BAD__FENCED|
|Case|K_TAKE_VALID__LEGACY|
|Case|K_TAKE_VALID__OWNED|
|Case|K_TAKE_VALID__FENCED|
|Case|K_CHECK__LEGACY|
|Case|K_CHECK__OWNED|
|Case|K_CHECK__FENCED|
|Case|K_RUN_REQUEST__LEGACY|
|Case|K_RUN_REQUEST__OWNED|
|Case|K_RUN_REQUEST__FENCED|
|Case|K_RUN_REQUEST_EMPTY__LEGACY|
|Case|K_RUN_REQUEST_EMPTY__OWNED|
|Case|K_RUN_REQUEST_EMPTY__FENCED|
|Case|K_JOB_RUN__LEGACY|
|Case|K_JOB_RUN__OWNED|
|Case|K_JOB_RUN__FENCED|
|Case|K_JOB_RUN_ROLLBACK__LEGACY|
|Case|K_JOB_RUN_ROLLBACK__OWNED|
|Case|K_JOB_RUN_ROLLBACK__FENCED|
|Case|K_JOB_REJECT__LEGACY|
|Case|K_JOB_REJECT__OWNED|
|Case|K_JOB_REJECT__FENCED|
|Case|K_JOB_STAGE__LEGACY|
|Case|K_JOB_STAGE__OWNED|
|Case|K_JOB_STAGE__FENCED|
|Case|K_JOB_SAVE__LEGACY|
|Case|K_JOB_SAVE__OWNED|
|Case|K_JOB_SAVE__FENCED|
|Case|K_JOB_EVENT__LEGACY|
|Case|K_JOB_EVENT__OWNED|
|Case|K_JOB_EVENT__FENCED|
|Case|F_API__LEGACY|
|Case|F_API__OWNED|
|Case|F_API__FENCED|
|Case|F_APPLIER__LEGACY|
|Case|F_APPLIER__OWNED|
|Case|F_APPLIER__FENCED|
|Case|F_SINGBOX__LEGACY|
|Case|F_SINGBOX__OWNED|
|Case|F_SINGBOX__FENCED|
|Case|H_SIGNATURE|
|Case|H_DEFERRED|
|Case|H_NO_VERIFIER|
|Case|H_NESTED_ERROR|
|Case|H_NESTED_RETURN|
|Case|K_RUN_FAILED|
|Case|K_RUN_INVALID|
|Case|K_REQUEST_FOREIGN|
|Case|K_REQUEST_NO_JOB|
|Case|K_SWALLOWED_SAVE|
|Case|I_PANEL_CORE|
|Case|B_RUN_SHADOW|
|Case|B_REJECT_SHADOW|
|Case|B_STAGE_SHADOW|
|Case|B_SAVE_SHADOW|
|Case|B_EVENT_SHADOW|

## 7. Один итоговый обезличенный отчёт

Заполнить TEMPLATE в ~/xgw-w3af/report.md. Actual HEAD/tree/6A8M/3artifactSHA/116sources/
freeze modes. NNP/sudo/owner actions/HEALTHY/on/pool/versions/connection before/after.
Start/monitor/show/shape command rc РАЗДЕЛЬНО; collector_exit_rcNOT_COLLECTED.
summary финальный, progress finalfalse checkpoint; remainingNOT_RUN/unknowncounts не0.
Все145 case rows, групповые actual executed/passed, nullable details, enum business
returns, error class/public repo source:line/elapsed_ms. Collector rc не business return.
Matrix OWNED40 vs F-owned constructors3 отдельно; extra positive2 vs expected failure4
и остальная отказная/definition семантика отдельно. Не "145 successful applies".

Весь Markdown прочитать перед одним F3. Не Git/чат/скрин: raw configs/status/logs/kernel/
URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/UID/homepaths/registryids/boot/
tokens/privatehashes/fingerprints/casefiles/rawexceptions/argv/business result texts.
Только fixed case IDs/enums/bools/counts/ms/rc/Git/sourceSHA/publicrepo file:line.
116 public manifest hashes в report не вставлять. Никакой установки после PASS.

Только ThinkCentre/working LAN, host не LAN client proof. Далее конкретные fixes либо
готовый source composition/полный actor inventory/handshake/real verifiers/repair/
bootstrap dry пакет. LiveC BLOCKED_BOOTSTRAP; independent original-on/code/unit rescue
до установки/fault. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS ещё открыты,
неwave4/DAE. Реальный AF NOT_RUN до фактического отчёта.

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
notes=Path.home()/'xgw-w3af'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3af-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M', 'src/xgw/engine.py': 'M'}
require(git('diff','--name-status',code,'HEAD','--',*runtime).splitlines()==[expected[name]+'\t'+name for name in sorted(expected)],'source diff не6A8M')
require(hashlib.sha256((repo/'tests/stand/wave3_flow_manifest.json').read_bytes()).hexdigest()=='ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82','manifest SHA изменился')
for name,digest in json.loads((repo/'tests/stand/wave3_flow_manifest.json').read_bytes()).items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'source SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_source_flow.py').read_bytes()).hexdigest()=='1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8','helper SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','support SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3af — source flow, panel/core writers и factories')
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
