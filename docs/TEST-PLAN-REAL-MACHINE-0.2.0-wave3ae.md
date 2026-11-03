# ТЗ Flash: wave3ae — 112 новых проверок связывания, составного применения и файлов

## 1. Основание и весь готовый объём одного прогона

Отчёт AD ae185ddccf056c7212c829d23d49c30303587cb7 принят: 130/130, 38 LEGACY + 38 OWNED + 38 FENCED + 16 extras.
См. REVIEW-REAL-MACHINE-0.2.0-wave3ad.md. Реальные source bodies, подставные effects;
установленный шлюз не обновлялся. AD130/AC51/AB32/AA22/Z19/Y6/X26/W25 не повторять.
Метка HEALTHY изменилась между AC и AD; причина не установлена. В AD оба bookends
HEALTHY/on, pool прежний, связь живая. Не диагностировать предполагаемый рестарт.

Один start выполняет все 112 НОВЫХ cases: 32 подмены hooks, 14 отсутствующих/чужих
привязок, 12 проверок boundary/context, 13 контрактов плана, 17 составных сценариев,
24 файловых сценария. Независимые case failures не требуют нового ТЗ и не мешают
остальным. Source/baseline/privacy/audit/unexpected filesystem failure — общий STOP.
Один итоговый Markdown с partial data; не дробить на микрозадания.

Только ThinkCentre, отдельного LAN-клиента нет. Работающий LAN — baseline; запрос
с хоста не доказывает LAN UDP/IPv6/DNS/E4. Сеть/службы/конфигурация не меняются.
Никакого install/off/G1/новой SSH-описи. Always_off запрещён. При обрыве incoming
дольше минуты следующая команда модели не обеспечит восстановление. Этот прогон
не создаёт сетевого отказа и не запускает guardian/timer/service/recovery.

## 2. Точная идентичность и разрешённые эффекты

Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7. Source diff теперь **6A + 7M**:
шесть ownership*.py добавлены, прежние семь изменённых в AD модулей сохранены БАЙТ-В-БАЙТ.
Два новых модуля: ownership_binding.py и ownership_files.py. Все остальные старые
source/units/config/pyproject/stand helpers сохранены. None-путь по-прежнему legacy;
daemon/CLI/installer не используют новый bundle. Нет глобального mandatory binding.

BoundWriters требует все семь объявленных объектов с одним exact Coordinator,
интактными 32 hooks (31 AD + новый PanelWriter.update), pinned registry/verifier.
Подмена одного hook блокирует весь объявленный boundary до admission. Перед/после
каждого шага проверяется весь boundary. Batch одноразовый в данном процессе, даже
если admission отказал; это не durable replay protection и не защита от hostile Python.
Шаги ограничены whitelist; callable accept обязателен, только exact True допускает
следующий шаг. Вся последовательность имеет один внешний LIFECYCLE ticket и одну
final verification/receipt, union вложенных ролей. Не атомарная kernel/file transaction:
при отказе второго шага первый файл может остаться изменённым, ticket UNKNOWN.
Не повторять/не лечить такой случай автоматически. Никакого runtime rollout по PASS.

PrivateFiles читает ТОЛЬКО явно указанные fixture files: exact hash/mode/uid/nlink,
либо exact absence. Anchored openat/NOFOLLOW по всем root ancestors и descendants,
root/descendant dirs owner0700; bounded reads 2MiB/file, максимум32 files. Symlink/
hardlink/FIFO/size/metadata drift отказываются. Checked — число уже подтверждённых
предыдущих файлов, не полная проверка после отказа. Это named subset observation,
не atomic snapshot/полный inventory/production policy/KERNEL/API/process verifier.
F_OWNER проверяет отказ при другом expected owner уже на root; root-DAC/chown нет.

| Артефакт → frozen file | SHA256 |
|---|---|
| tests/stand/wave3_bound_batch.py → batch.py |fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680|
| tests/stand/wave3_source_hooks.py → support.py |9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917|
| tests/stand/wave3_binding_manifest.json → manifest.json |d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0|

116 source *.py по новому manifest копируются в ~/xgw-w3ae/source. Это source inventory,
НЕ аттестация installed116. Support — неизменённые AD fixtures/guard/loader/helpers;
его старый CLI/batch НЕ вызывается и старые AD cases НЕ повторяются. Импорт только
private frozen_ad package. Новые registry/file tests используют синтетические boot/
clock и UID владельца. Реальный boot/rootDAC/network/process lifecycle не проверяются.
Freeze3+116: notes/dirs0700, files0600. Source product outputs0640/0644 допустимы
в private0700 fixture; не chmod продукта ради PASS. Private file hash не публиковать.

Worker ДО source imports ставит принятый AD CPython audit guard (self-test registration
и два manual events без реальных process/socket). Неожиданный запрет — общий STOP,
не ослаблять guard. Guard для trusted regression, НЕ security sandbox. Принятые
ограничения dirfd-relative events остаются. Новый observer открывает readonly directory
ancestors ради NOFOLLOW, не читает их содержимое/секреты. No Y/root snapshot reads.

Разрешены: Git FF, NNP/sudo проверки, xgw status/pool readonly bookends, заморозка,
обычные user fixture files/flock/fsync/rename/symlink/hardlink/FIFO/один thread fixture,
один detached user collector. Синтетические service/API/runner лишь регистрируют вызовы.
Workload subprocesses/network requests/live gateway operations = 0. Запрещены install/
off/enable/disable/G1/WAN/LAN/TS/pin/pool/config/service/live rules/API writes/nft/ip/
GET/curl/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtest/core version probes/new units/
timers/guardian/arm/replay/live faults. Git доставка не VPN probe. Все 7 runtime gates
ложны всегда, даже при112/112; FILE evidence из private fixtures не делает их истинными.

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
notes=Path.home()/'xgw-w3ae'
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

### S2.1. Чистаяfreepool/FF/6A+7M и publicsourceManifest

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
git('merge-base','--is-ancestor','ae185ddccf056c7212c829d23d49c30303587cb7','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M'}
actual=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(actual==[expected[name]+'\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_6A_7M')
manifest=repo/'tests/stand/wave3_binding_manifest.json'
require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0','MANIFEST_SHA')
data=json.loads(manifest.read_bytes())
require(len(data)==116,'SOURCE_COUNT')
require(set(data)=={str(p.relative_to(repo)).replace('\\','/') for p in (repo/'src/xgw').rglob('*.py')},'SOURCE_INVENTORY')
for name,digest in data.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_bound_batch.py').read_bytes()).hexdigest()=='fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680','BATCH_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','SUPPORT_SHA')
print('SOURCE_DIFF_SIX_ADD_SEVEN_MODIFY')
print('SOURCE_MANIFEST_MATCHED',len(data))
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужныrc0/SOURCE_DIFF_SIX_ADD_SEVEN_MODIFY/SOURCE_MANIFEST_MATCHED116/SOURCE_PREFLIGHT_OK.
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
notes=Path.home()/'xgw-w3ae'
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
raw=(repo/'tests/stand/wave3_binding_manifest.json').read_bytes()
freeze(notes/'manifest.json',raw,'d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0')
freeze(notes/'batch.py',(repo/'tests/stand/wave3_bound_batch.py').read_bytes(),'fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680')
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
print('BOUND_COMPOSITE_FROZEN',len(data))
PY
```

НуженBOUND_COMPOSITE_FROZEN116/rc0. Existingmatchingfiles допускаютсятолькодляresumeподготовки
доstart; mismatch→STOP_IDENTITY, безoverwrite/newnotes. ЗатемS2.4bобязателен.

#### S2.4b. Полнаяпроверкаfreeze/unused передstart

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ae'
def valid(path,digest):
    info=path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
ok=ok and valid(notes/'batch.py','fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680') and valid(notes/'manifest.json','d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0') and valid(notes/'support.py','9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917')
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
print('BOUND_COMPOSITE_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

ТолькоREADY/rc0→S3.1. Afterstarted→S3.2/S3.3, никакихповторовfreeze/start/worker.

## 5. S3 —112проверок одногоsourceпакета

### S3.1. Единственныйstart

```bash
python3 -I -B "$HOME/xgw-w3ae/batch.py" start
```

НужныBOUND_COMPOSITE_BATCH_STARTED/rc0. Это Popencollector, не112PASS. CollectorordinaryUID,
EXCLworkerclaim/atomicprogress, syntheticRegistry и productfixtures толькоnotes.
_batchвручнуюневызывать. Нет workload subprocess/netprobe/fakeD/service/timer/guardian. Старые AD130 не выполняются.

### S3.2. Одинmonitor до300с, автоматическийпрогонвсехвариантов

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ae/batch.py'
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
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ae/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        raise SystemExit('SHOW_FAILED')
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    raise SystemExit('FINAL_NOT_RECORDED_USE_CHECKPOINT')
data=wrapper['data']
expected=['H_CAPTURE___SAVE', 'H_CAPTURE___LOAD', 'H_CAPTURE__UP', 'H_CAPTURE__ENABLE', 'H_CAPTURE__DISABLE', 'H_CAPTURE__OPEN', 'H_CAPTURE__CLOSE', 'H_CAPTURE__DOWN', 'H_CAPTURE__RESTORE_TUN', 'H_CAPTURE__TIDY', 'H_CAPTURE__TAILSCALE_DIRECT', 'H_CAPTURE__TAILSCALE_FALLBACK', 'H_PEERS___SAVE_PEERS', 'H_PEERS___NFT_ELEMENT', 'H_PEERS__PREPARE', 'H_PEERS__STOP', 'H_PEERS__RECONCILE', 'H_XRAY__APPLY', 'H_XRAY__ROLLBACK', 'H_SINGBOX__APPLY', 'H_SINGBOX__ROLLBACK', 'H_SINGBOX__RESTART', 'H_CORES__UPDATE', 'H_CORES__ROLLBACK', 'H_API__ADD_OUTBOUNDS', 'H_API__REMOVE_OUTBOUND', 'H_API__ADD_INBOUNDS', 'H_API__REMOVE_INBOUND', 'H_API__REPLACE_ROUTING', 'H_API__PIN', 'H_API__UNPIN', 'H_PANEL__UPDATE', 'M_CAPTURE', 'M_PEERS', 'M_XRAY', 'M_SINGBOX', 'M_CORES', 'M_API', 'M_PANEL', 'O_CAPTURE', 'O_PEERS', 'O_XRAY', 'O_SINGBOX', 'O_CORES', 'O_API', 'O_PANEL', 'B_INCOMPLETE', 'B_EXTRA', 'B_WRONG_TYPE', 'B_NO_VERIFIER', 'B_WRONG_COORDINATOR', 'B_WRONG_REGISTRY', 'B_REGISTRY_DRIFT', 'B_VERIFIER_DRIFT', 'B_CALL_DRIFT', 'B_FOREIGN_PID', 'B_FOREIGN_THREAD', 'B_NESTED', 'P_EMPTY', 'P_LIST', 'P_TOO_MANY', 'P_WRONG_STEP', 'P_UNKNOWN_WRITER', 'P_UNKNOWN_METHOD', 'P_ARGS_LIST', 'P_KWARGS_DICT', 'P_DUP_KEY', 'P_OWNER_KEY', 'P_USED', 'P_FENCED', 'P_NO_CHECKER', 'C_SB_XRAY', 'C_SB_XRAY_API', 'C_PANEL_PEERS', 'C_FAILED_RESULT', 'C_VERIFIER_EXCEPTION', 'C_FALSE_VERIFIER', 'C_STEP_EXCEPTION', 'C_AFTER_UNBIND', 'C_AFTER_HOOK_DRIFT', 'C_AFTER_VERIFIER_DRIFT', 'C_AFTER_REGISTRY_DRIFT', 'C_NO_EARLY_LEASE', 'C_CHECKER_FALSE', 'C_CHECKER_EXCEPTION', 'C_FILE_MISMATCH', 'C_SECOND_REJECT', 'C_SECOND_TERMINAL', 'F_PRESENT', 'F_ABSENT', 'F_TWO', 'F_DIGEST_MISMATCH', 'F_MODE', 'F_OWNER', 'F_HARDLINK', 'F_SYMLINK', 'F_PARENT_SYMLINK', 'F_ROOT_SYMLINK', 'F_FIFO', 'F_OVERSIZE', 'F_MISSING', 'F_ABSENT_PRESENT', 'F_ABSENT_SYMLINK', 'F_ABSENT_MISSING_PARENT', 'F_DIRECTORY_MODE', 'F_ROOT_MODE', 'F_DUPLICATE', 'F_TRAVERSAL', 'F_BAD_DIGEST', 'F_BOOL_OWNER', 'F_BOOL_MODE', 'F_EMPTY']
rows=data.get('cases',[])
counts=('expected','completed','passed','remaining_not_run','source_files','network_requests','live_gateway_operations','workload_subprocesses','unexpected_forbidden_io')
count_types=all(type(data.get(k)) is int and data[k]>=0 for k in counts)
rows_valid=(type(rows) is list and all(type(r) is dict and type(r.get('passed')) is bool and type(r.get('elapsed_ms')) is int and r['elapsed_ms']>=0 for r in rows))
shape=(count_types and rows_valid and data.get('scope')=='EXPLICIT_BOUND_SOURCE_AND_PRIVATE_FILES_ONLY' and data.get('expected')==112
       and data.get('completed')==len(rows) and data.get('passed')==sum(r['passed'] for r in rows)
       and data.get('remaining_not_run')==112-len(rows) and len(rows)<=112 and [r.get('case') for r in rows]==expected[:len(rows)]
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_actor_binding_implemented','runtime_writer_fence_verified','runtime_verifier_implemented','runtime_recovery_implemented','repair_implemented','active_faults_authorized'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0 and data.get('workload_subprocesses')==0)
good=(shape and data.get('marker')=='BOUND_COMPOSITE_BATCH_RECORDED' and data.get('completed')==112
      and data.get('passed')==112 and all(r.get('passed') is True for r in rows)
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

### S4.3. Интерпретация одного итогового результата

Все cases перечислены ниже. H — shadow каждого из 32 hooks, M — missing coordinator,
O — foreign coordinator. Blank source actors в H/M/O только проверяют binding,
их business bodies НЕ вызываются. B проверяет полный boundary/context. P — shape/
whitelist/checker/one-use/fenced admission. P_USED: первый запуск действительно NOOP
в panel fixture, второй отказан. P_FENCED: lease fixture, ни одного body/lockfile.

C_SB_XRAY / C_SB_XRAY_API / C_PANEL_PEERS / C_NO_EARLY_LEASE — четыре положительных
composites: receipt/generation1, roles union, actual exact fixture file observation.
Нет промежуточной receipt. Остальные13 C — expected negative: receipt/generation0,
UNKNOWN1, несмотря на passed=true. C_SECOND_REJECT/TERMINAL подтверждают partial effect
первого sing-box шага и остановку до Xray write, не rollback. C_FILE_MISMATCH блокирует
receipt по реальному сравнению bytes. C_AFTER_* останавливает продолжение при drift.
Никаких network/service действий в C, только принятые fake effects AD fixtures.

F_PRESENT/F_ABSENT/F_TWO — три положительных file observations; остальные21 — expected
refusal (6 constructor refusals,15 read refusals). F_OWNER — root owner-policy mismatch,
не root privilege test. Symlinks/hardlinks/FIFO только в fixture, не трогать их после
проверки для "исправления" результата. Observer не пишет. No concurrent filesystem /
atomic snapshot proof. File replacement narrow local regression отдельно, не real test.

На failure сохранять actual nullable registry_receipts/generation/unknown/stub_calls/
file_checked/file_matched/rejection_observed/completion_verified. None значит неизвестно
или поле неприменимо, не false/0. Case passed=true у expected rejection НЕ означает
business completion. completion_verified здесь только 4 positive fixture composites,
не runtime verifier proof. Error class + публичный репозиторный source:line, без текста
exception/traceback/argv/private path. Нельзя публиковать private fixture contents/hashes.
global_scope_stop=true или audit denial: оставшиеся remaining_not_run, не перезапуск.
Unexpected OSError/непригодный FS также останавливает остальные safe branches.

| Группа | Точные case IDs |
|---|---|
|Case|H_CAPTURE___SAVE|
|Case|H_CAPTURE___LOAD|
|Case|H_CAPTURE__UP|
|Case|H_CAPTURE__ENABLE|
|Case|H_CAPTURE__DISABLE|
|Case|H_CAPTURE__OPEN|
|Case|H_CAPTURE__CLOSE|
|Case|H_CAPTURE__DOWN|
|Case|H_CAPTURE__RESTORE_TUN|
|Case|H_CAPTURE__TIDY|
|Case|H_CAPTURE__TAILSCALE_DIRECT|
|Case|H_CAPTURE__TAILSCALE_FALLBACK|
|Case|H_PEERS___SAVE_PEERS|
|Case|H_PEERS___NFT_ELEMENT|
|Case|H_PEERS__PREPARE|
|Case|H_PEERS__STOP|
|Case|H_PEERS__RECONCILE|
|Case|H_XRAY__APPLY|
|Case|H_XRAY__ROLLBACK|
|Case|H_SINGBOX__APPLY|
|Case|H_SINGBOX__ROLLBACK|
|Case|H_SINGBOX__RESTART|
|Case|H_CORES__UPDATE|
|Case|H_CORES__ROLLBACK|
|Case|H_API__ADD_OUTBOUNDS|
|Case|H_API__REMOVE_OUTBOUND|
|Case|H_API__ADD_INBOUNDS|
|Case|H_API__REMOVE_INBOUND|
|Case|H_API__REPLACE_ROUTING|
|Case|H_API__PIN|
|Case|H_API__UNPIN|
|Case|H_PANEL__UPDATE|
|Case|M_CAPTURE|
|Case|M_PEERS|
|Case|M_XRAY|
|Case|M_SINGBOX|
|Case|M_CORES|
|Case|M_API|
|Case|M_PANEL|
|Case|O_CAPTURE|
|Case|O_PEERS|
|Case|O_XRAY|
|Case|O_SINGBOX|
|Case|O_CORES|
|Case|O_API|
|Case|O_PANEL|
|Case|B_INCOMPLETE|
|Case|B_EXTRA|
|Case|B_WRONG_TYPE|
|Case|B_NO_VERIFIER|
|Case|B_WRONG_COORDINATOR|
|Case|B_WRONG_REGISTRY|
|Case|B_REGISTRY_DRIFT|
|Case|B_VERIFIER_DRIFT|
|Case|B_CALL_DRIFT|
|Case|B_FOREIGN_PID|
|Case|B_FOREIGN_THREAD|
|Case|B_NESTED|
|Case|P_EMPTY|
|Case|P_LIST|
|Case|P_TOO_MANY|
|Case|P_WRONG_STEP|
|Case|P_UNKNOWN_WRITER|
|Case|P_UNKNOWN_METHOD|
|Case|P_ARGS_LIST|
|Case|P_KWARGS_DICT|
|Case|P_DUP_KEY|
|Case|P_OWNER_KEY|
|Case|P_USED|
|Case|P_FENCED|
|Case|P_NO_CHECKER|
|Case|C_SB_XRAY|
|Case|C_SB_XRAY_API|
|Case|C_PANEL_PEERS|
|Case|C_FAILED_RESULT|
|Case|C_VERIFIER_EXCEPTION|
|Case|C_FALSE_VERIFIER|
|Case|C_STEP_EXCEPTION|
|Case|C_AFTER_UNBIND|
|Case|C_AFTER_HOOK_DRIFT|
|Case|C_AFTER_VERIFIER_DRIFT|
|Case|C_AFTER_REGISTRY_DRIFT|
|Case|C_NO_EARLY_LEASE|
|Case|C_CHECKER_FALSE|
|Case|C_CHECKER_EXCEPTION|
|Case|C_FILE_MISMATCH|
|Case|C_SECOND_REJECT|
|Case|C_SECOND_TERMINAL|
|Case|F_PRESENT|
|Case|F_ABSENT|
|Case|F_TWO|
|Case|F_DIGEST_MISMATCH|
|Case|F_MODE|
|Case|F_OWNER|
|Case|F_HARDLINK|
|Case|F_SYMLINK|
|Case|F_PARENT_SYMLINK|
|Case|F_ROOT_SYMLINK|
|Case|F_FIFO|
|Case|F_OVERSIZE|
|Case|F_MISSING|
|Case|F_ABSENT_PRESENT|
|Case|F_ABSENT_SYMLINK|
|Case|F_ABSENT_MISSING_PARENT|
|Case|F_DIRECTORY_MODE|
|Case|F_ROOT_MODE|
|Case|F_DUPLICATE|
|Case|F_TRAVERSAL|
|Case|F_BAD_DIGEST|
|Case|F_BOOL_OWNER|
|Case|F_BOOL_MODE|
|Case|F_EMPTY|

## 7. Один обезличенный отчёт и публикация

Заполнить TEMPLATE в ~/xgw-w3ae/report.md. Actual HEAD/tree/6A7M/3artifactSHA/116sources/
freeze modes; NNP/sudo/owner actions; HEALTHY/on/pool/versions/connection before/after.
Start/monitor/show/shape command rc РАЗДЕЛЬНО. collector_exit_rc=NOT_COLLECTED.
summary.json финальный; progress finalfalse — checkpoint, remaining NOT_RUN. Прочитанный
JSON/monitor0 не равен PASS. Строки112 cases, групповые counts, actual partial details,
error class/public source:line/elapsed_ms. Total/completed/passed/remaining отдельно.
Показать 4 positive composites vs13 expected negatives,3 positive file observations
vs21 refusals, а не112 успешных применений. Все7 runtime gatesfalse, network/liveops0.

Полностью прочитать Markdown до единственного F3. Не Git/чат/скрин: raw configs/status/
logs/kernel/URIs/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/UID/home paths/
registry ids/boot/tokens/private hashes/case files/raw exceptions/argv/result texts.
Разрешены только фиксированные case IDs/enums/bools/counts/timings_ms/rc/Git/sourceSHA/
публичный repo file:line. Manifest публичный,116 hashes в report не вставлять.

Только ThinkCentre. Host не LAN client. По успешному отчёту НЕТ установки/активации.
Runtime composition/mandatory all-writer handshake, protected path policy, real KERNEL/
API/process verification/repair/bootstrap/independent original-on rescue ещё открыты.
Full wave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS не закрывать. Не wave4/DAE.
Реальная AE NOT_RUN до фактического отчёта.

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
notes=Path.home()/'xgw-w3ae'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ae-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
expected={'src/xgw/ownership.py': 'A', 'src/xgw/ownership_adapters.py': 'A', 'src/xgw/ownership_diagnostics.py': 'A', 'src/xgw/ownership_hooks.py': 'A', 'src/xgw/ownership_binding.py': 'A', 'src/xgw/ownership_files.py': 'A', 'src/xgw/net/capture.py': 'M', 'src/xgw/freepool/backend.py': 'M', 'src/xgw/apply/applier.py': 'M', 'src/xgw/apply/singbox.py': 'M', 'src/xgw/cores.py': 'M', 'src/xgw/xraycore/api.py': 'M', 'src/xgw/managed.py': 'M'}
require(git('diff','--name-status',code,'HEAD','--',*runtime).splitlines()==[expected[name]+'\t'+name for name in sorted(expected)],'source diff не6A7M')
require(hashlib.sha256((repo/'tests/stand/wave3_binding_manifest.json').read_bytes()).hexdigest()=='d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0','manifest SHA изменился')
for name,digest in json.loads((repo/'tests/stand/wave3_binding_manifest.json').read_bytes()).items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'source SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_bound_batch.py').read_bytes()).hexdigest()=='fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680','helper SHA изменился')
require(hashlib.sha256((repo/'tests/stand/wave3_source_hooks.py').read_bytes()).hexdigest()=='9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917','support SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3ae — bound composite и private file observer')
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
