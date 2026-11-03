# ТЗ Flash: wave3ab — dormant product registry, без установки

## 1. Основание и scope

AAreporte64a39b7743da2a1f999d51e829dfd0f4b3dd9f9 принят:22/22/3realprocesscases/3children,
HEALTHY/on/pool/versions/связь сохранны. См. REVIEW-REAL-MACHINE-0.2.0-wave3aa.md.
AA22/Z19/Y6/X26/W25/старые batches не повторять. Yrootmaterial не читать/не переносить.

Добавлен новый sourcefile src/xgw/ownership.py, но существующие XGWentrypoints его НЕ
импортируют. Нетimport-timeI/O/автоактивации/установки. ABкопирует exactsource как
registry.py в notes обычного владельца, helper импортирует только эту privateкопию.
InstalledXGW/его файлы/службы не меняются. НЕpipinstall/неxgwinstall/неrestart/reload.
Это foundationC-REG1, не готовые runtimefence/driver/repair/C-ENTRY.

Новая unifiedschema хранитgeneration/writers/receipts/lease в одном atomicrecord.
Проверки32новых cases объединены в один batch: metadata/boot/schema/token/receipts/
lease/admission, инъекции filecommitошибок, три realprocesscases/четыре ownchildren.
Все callbackverifications synthetic, bootids/leaseclock виртуальные. Kernel/systemd/
сетьневызываются. Подробно ADR-REC-C-REGISTRY-FOUNDATION.md.

ТОЛЬКО ThinkCentre. Рабочая LAN/HEALTHY/on — baseline. HostнеLANUDP/IPv6/DNS/E4proof.
Preserve WAN/LAN/Tailscale/pin/pool/config/services/rules. Always_off запрещён,
incomingoutage>1мин следующаякомандамоделинеисправит. ABне создаёт сетевойотказ.
Общие STOPidentity/baseline/privacy; optionalcasefail→остальныеcases→одинreport.

## 2. Точная идентичность и разрешённые эффекты

Baselineproductpin351fb54e074f4a7b497a8a4244fc74c6088788d7. **Source diff допускает ровно
одно добавление** src/xgw/ownership.py с SHA256 **2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5**. Прежние src/packaging/config/
CLI/standhelpers неизменны. Нельзя писать «весь runtime source diff пуст»: новый module
есть в исходниках. Он пока не установлен и не импортируется работающим XGW.

tests/stand/wave3_registry_batch.py SHA256 **5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64**.
Freeze ~/xgw-w3ab0700/registry.py+batch.py0600. Roothelper запрещён. CLIbatch ordinary
Python-I-B; internal_peerвручную запрещён. Registryexpected_uid=os.getuid() в тесте —
fixturepolicy; defaultUID0/runtimeDACнастоящего /run/xgw здесь NOT_RUN. Измененийuid/chown
нет. Bootfixtures не читатькакреальныйbootid. Rawrecord/registryid/boot/tokens/inodes private.

Записи только usernotes и newcase-*sandbox. Внутри можно менять/создавать/переименовывать
собственные syntheticstate/lock/stage для negativecases; чужих/XGWlocks это не касается.
Файлы libraryexpectedprivate0600/owner/nlink1/regular/size≤128KiB/hash перед импортом.
Никаких rootYmaterials/старыхrun/процессаdaemon. gitdeliveryнеVPNprobe.

Разрешены GitFF/NNP/sudo/status/pool readonly, собственные fsync/flock/rename и4 ownchildren.
Запрещены off/install/G1/enable/disable/servicechanges/новыеunits/timers/guardian/arm/
replay/fault/nft/ipmutations/nft-c/APIwrites/config/pin/pool/TS/WAN/LANchanges/SSH/scans/
pcap/netns/speedtest/GET/curl/SOCKS/DNS/ping/coreversionprobes/новаяопись.
Controllerbudget60с — только testbatch, не измеренные45сrescue. Childcommunicate4с,
owncleanup1+1с. Послеcontrollerloss отсутствиеchild не объявлять доказанным.

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
notes=Path.home()/'xgw-w3ab'
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

### S2.1. Чистая freepool/FF/единственное разрешённое sourceдобавление

```bash
python3 -I -B - <<'PY'
import hashlib,os,subprocess
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
git('merge-base','--is-ancestor','e64a39b7743da2a1f999d51e829dfd0f4b3dd9f9','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml',
         'tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
changes=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime)
require(changes=='A\tsrc/xgw/ownership.py','SOURCE_DIFF_NOT_SINGLE_ADDITION')
require(hashlib.sha256((repo/'src/xgw/ownership.py').read_bytes()).hexdigest()=='2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5','REGISTRY_SOURCE_SHA')
require(hashlib.sha256((repo/'tests/stand/wave3_registry_batch.py').read_bytes()).hexdigest()=='5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64','BATCH_SOURCE_SHA')
print('SOURCE_DIFF_SINGLE_DORMANT_ADDITION')
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужны rc0/SOURCE_DIFF_SINGLE_DORMANT_ADDITION/SOURCE_PREFLIGHT_OK; actualHEAD/tree записать.
Иное→общийSTOP, неreset/checkout/rebase/force/install. Веткадолжнабытьfreepool.
Existingruntime равенpin, добавлен толькоdormantmodule. Installed110treeповтор NOT_RUN.
Наличие нового sourcefile не означает его установку/активацию на шлюзе.

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

### S2.4. Заморозить sourceбиблиотеку и batch в notes

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ab'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o7777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','registry-started.json','registry-result.json','sandbox')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
expected={'batch.py':('tests/stand/wave3_registry_batch.py','5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64'),
          'registry.py':('src/xgw/ownership.py','2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5')}
for target,(source,digest) in expected.items():
    path=notes/target
    raw=(Path.home()/'zcod/xgw'/source).read_bytes()
    if len(raw)>131072 or hashlib.sha256(raw).hexdigest()!=digest:
        raise SystemExit('STOP_SOURCE_SHA')
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o7777!=0o600 or info.st_nlink!=1 or path.read_bytes()!=raw:
            raise SystemExit('STOP_EXISTING_FREEZE_MISMATCH')
        continue
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw)
print('REGISTRY_FROZEN',len(expected))
PY
```

Нужен REGISTRY_FROZEN2/rc0. Два совпадающих файла допускаются для возобновления
подготовки; чужой/частичный файл STOP_IDENTITY, без overwrite/newnotes. Затем S2.4b ОБЯЗАТЕЛЕН.
Freeze не импортирует installedXGW, не активирует module и не устанавливает runtime.

#### S2.4b. Проверить freeze и отсутствие предыдущего запуска

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ab'
expected={'batch.py':'5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64','registry.py':'2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'}
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
for name,digest in expected.items():
    path=notes/name
    if not path.exists() or path.is_symlink():
        ok=False
        continue
    info=path.stat()
    ok=ok and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
unused=not any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','registry-started.json','registry-result.json','sandbox'))
print('REGISTRY_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

Только REGISTRY_READY/rc0 разрешает S3.1. Если есть started/result/sandbox — S3.2,
не новый batch. При возобновлении после обрыва сразу S3.2; не freeze/restart/cleanup.

## 5. S3 — все32 сценариев одним запуском

### S3.1. Однократный запуск и сохранение результата

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
notes=Path.home()/'xgw-w3ab'
model=notes/'batch.py'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if not model.exists() or model.is_symlink() or model.stat().st_uid!=os.getuid() or model.stat().st_mode&0o777!=0o600 or hashlib.sha256(model.read_bytes()).hexdigest()!='5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64':
    raise SystemExit('STOP_FROZEN_REGISTRY_SHA')
ledger=notes/'registry.py'
if not ledger.exists() or ledger.is_symlink() or ledger.stat().st_uid!=os.getuid() or ledger.stat().st_mode&0o7777!=0o600 or ledger.stat().st_nlink!=1 or hashlib.sha256(ledger.read_bytes()).hexdigest()!='2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5':
    raise SystemExit('STOP_FROZEN_LEDGER_SHA')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','registry-started.json','registry-result.json','sandbox')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
fd=os.open(notes/'controller-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump({'started':True},out)
proc=None
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(model),'batch'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60,check=False)
    data=json.loads(proc.stdout)
    valid=(isinstance(data,dict) and data.get('scope')=='DORMANT_PRODUCT_REGISTRY_USER_SANDBOX'
           and data.get('runtime_recovery_implemented') is False
           and data.get('runtime_writer_fence_installed') is False
           and data.get('active_faults_authorized') is False
           and data.get('installed_runtime_changed') is False
           and data.get('network_requests')==0 and data.get('live_gateway_operations')==0
           and data.get('total')==32 and len(data.get('cases',[]))==32
           and data.get('real_process_cases')==3 and data.get('virtual_boot_and_clock') is True)
    if not valid:
        raise ValueError('shape')
    good=(proc.returncode==0 and data.get('marker')=='REGISTRY_FOUNDATION_RECORDED'
          and data.get('passed')==32 and all(r.get('passed') is True for r in data['cases'])
          and data.get('real_process_cases_passed')==3 and data.get('children_started')==4)
    result={'command_rc':proc.returncode,'data':data,'shape_valid':True,'all_cases_passed':good}
except subprocess.TimeoutExpired:
    result={'command_rc':None,'runner_rc':124,'shape_valid':False,'runner_marker':'REGISTRY_RUN_TIMEOUT','all_cases_passed':False}
except Exception as exc:
    result={'command_rc':None if proc is None else proc.returncode,'shape_valid':False,'runner_marker':'REGISTRY_RUN_OR_READOUT_FAILED','error_class':type(exc).__name__,'all_cases_passed':False}
fd=os.open(notes/'controller-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump(result,out)
    out.write('\n')
print(json.dumps(result))
raise SystemExit(0 if result['all_cases_passed'] else 3)
PY
```

Успех: rc0, command_rc0, shape_valid=true, all_cases_passed=true,
marker=REGISTRY_FOUNDATION_RECORDED, passed=total=32, все case.passed=true.
Также ОБЯЗАТЕЛЬНО все три runtime/fence/active flags=false, real_process_cases_passed=3,
children_started=4 и virtual_boot_and_clock=true. real_process_cases=3 — число определённых
процессных cases, успешность каждого подтверждается отдельно.
Если любой из runtime/fence/active flags стал true — scope неверен; это не готовность recovery.

Rc3/failed case/timeout/ошибка формата не разрешают retry или починку кода на шлюзе.
Сценарии уже выполняются независимо внутри одного batch; сохранить все полученные
результаты и перейти к S3.2/S4/отчёту. REGISTRY_RUN_TIMEOUT завершает только собственный
дочерний Python-модели, не службы/ядра. Критический material сети модель не трогала.
При timeout command_rcUNKNOWN, runner_rc124 — разные поля, не считать124 фактическим exit helper. При ошибке JSON известный proc.returncode сохраняется отдельно. После обрыва — S3.2, не S3.1. Exclusive controller-started/registry-started препятствуют повтору.

### S3.2. Прочитать сохранённый итог либо безопасный checkpoint

```bash
python3 -I -B - <<'PY'
import json,os
from pathlib import Path
notes=Path.home()/'xgw-w3ab'
for name in ('controller-result.json','registry-result.json','registry-progress.json'):
    path=notes/name
    if not path.exists():
        continue
    if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o777!=0o600 or path.stat().st_size>65536:
        raise SystemExit('STOP_RESULT_METADATA')
    try:
        value=json.loads(path.read_text())
    except (OSError,ValueError):
        raise SystemExit('STOP_RESULT_UNREADABLE') from None
    print(json.dumps({'file':name,'data':value}))
    if name=='controller-result.json' and not value.get('all_cases_passed'):
        continue
    break
else:
    print('READOUT_END_NO_FURTHER_FINAL_RESULT')
PY
```

Один dispatcher: controller-result содержит rc команды и helperdata; registry-result —
окончательный helper итог, если controller его не сохранил; registry-progress — checkpoint
с final=false, не законченный batch. При неуспешном controller читается следующий
доступный итог/checkpoint в том же блоке. Не переносить checkpoint в финальный PASS.
Нет файлов → INTERRUPTED_UNKNOWN. Read rc0 не означает32/32. S3.1 не повторять.
Не читать state/identity/lock/case files вручную: dispatcher выбирает только safe outputs.

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

### S4.3. Интерпретация всех32 новых cases

Нужны commandrc0/shapevalidtrue/allcasestrue/REGISTRY_FOUNDATION_RECORDED/32of32,
realprocesspassed3/childrenstarted4. installed_runtime_changed/runtimefence/recovery/
activeflagsfalse, networkrequests/liveops0, virtual_boot_and_clocktrue.
Casefail→fixedreason/errorclass, остальныеcasesавтоматически, одинreport, безповтора.

| № | Case ID |
|---|---|
|1|UNIFIED_RECORD_COMPLETION|
|2|SAME_BOOT_REOPEN_RETAINS_WRITER|
|3|OLD_BOOT_REFUSES_READ_AND_ADMISSION|
|4|FOREIGN_REGISTRY_TOKEN_REFUSED|
|5|DUPLICATE_COMPLETION_CANNOT_PUBLISH_TWICE|
|6|UNKNOWN_REQUIRES_FUTURE_REPAIR|
|7|FALSE_COMPLETION_REFUSED|
|8|STRING_COMPLETION_REFUSED|
|9|OUTCOME_RECEIPTS_ALL_INVALIDATE_OLD_GENERATION|
|10|NO_PENDING_BARRIER_BEFORE_DRAIN|
|11|ARMED_BLOCKS_WRITER|
|12|EXPIRED_LEASE_NEVER_UNFENCES|
|13|DISPATCHED_JOB_CANNOT_BE_UNUSED_OR_DISPATCHED_TWICE|
|14|UNUSED_RETIRE_INVALIDATES_OLD_EPOCH|
|15|SYNTHETIC_RESTORED_RECEIPT_ADVANCES_GENERATION|
|16|BOOLEAN_EXPECTED_GENERATION_REFUSED|
|17|BOOLEAN_CLOCK_REFUSED|
|18|BACKWARD_CLOCK_REFUSED|
|19|STATE_PERMISSIONS_REFUSED|
|20|STATE_SYMLINK_REFUSED|
|21|REPLACED_STABLE_LOCK_REFUSED|
|22|DUPLICATE_JSON_KEYS_REFUSED|
|23|OVERSIZED_RECORD_REFUSED|
|24|INTERRUPTED_STAGE_BLOCKS_WITHOUT_AUTOREPAIR|
|25|PRE_REPLACE_FAILURE_PRESERVES_OLD_RECORD_AND_STAGE|
|26|POST_REPLACE_ACK_ERROR_HAS_COHERENT_RECEIPT|
|27|RECEIPT_HISTORY_IS_BOUNDED|
|28|WRITER_CAP_NEVER_EVICTS_LIVE_TICKET|
|29|REAL_PROCESSES_HAVE_DISTINCT_DURABLE_TICKETS|
|30|REAL_CHILD_HOOK_FINISHES_WITH_PARENT_TICKET|
|31|REAL_OWNER_EXIT_DOES_NOT_PRUNE_DURABLE_TICKET|
|32|OWNER_POLICY_MISMATCH_REFUSED|

Три REAL_*cases: конкурентныйadmit2child даёт дваразличныхdurabletickets и childrc[0,0];
nestedhook1child и ownerexit1child — childrc0. Везде fixed_output_matchedtrue.
Это **новая** sourceimplementation, старые AA22/Z19 batches не выполняются. Childhook
не настоящий systemctl/TUN, ownerexitне отказ шлюза. RootruntimeDAC/bootidNOT_RUN.

Pre-replaceerror намеренно оставляет старыйrecord+stage, дальнейший доступrefused.
Post-replacefsyncerror даёт COMMIT_UNCERTAIN, а текущийrecord может уже иметь целиком
новыйreceipt/generation/removal. Не считатьerror доказательствомno-commit/permissionretry.
Receipt/summaryнеnetworkverifier. Powerloss/repair/реальный возвратonNOT_RUN.

Status/pool — толькоbookends, не новыеYkernel/RPDB/PID/configobservations. Ysnapshot
PLANNED_NOT_ARMED/неиспользован. Lease/bootfixtures synthetic. Не принимать32/32 за
C-ENTRYintegration/полныйC-REGrepair/driver/autonomy/45s/faultauthorization.

## 7. Один отчёт и privacyreview

Заполнить TEMPLATE в ~/xgw-w3ab/report.md. ActualHEAD/tree/pin, source diff=единственное
добавлениеownership.py, обаSHA/freeze, installedruntimeunchanged, NNP/sudo/owneractions,
before/afterHEALTHY/on/pool/versions/связь. Отдельно commandrc/helpermarker/filetype,
32casebools/processdetails/childrenstarted/virtualbootclock/falsegates.
Если checkpointonly, completed+фактическиесases, остальные NOT_RUN/finalmarkerUNKNOWN.
Не повторять batch/_peer/newnotes/freezeпослезапуска, не чинитьsourceнаThinkCentre.

Не читать/печатать/Git/скрин rawstate/registryids/boot/tokens/inodes/UID/homepaths/private
hashes/исключения/unknownchildstdout/rawstatus/config/logs/URI/IP/MAC/UUID/keys/passwords/
SNI/ports/fp/tags/PID/NIC. ТолькоfixedcaseIDs/bools/counts/enums/Git/sourceSHA/rc.
ОдноуведомлениепослепубликацииилисущественногоSTOP/необходимогодействиявладельца.

Следующаяработа: C-REG2repairprotocol/C-ENTRYdormantadapters/C-VERIFYreceipts,
независимыйDfake и отдельныйbootstraprescue. Нетавтоматическогопереходакinstall/liveC/D/E.
OnlyThinkCentre/workingLAN, hostнеLANclient. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/
performance/allTSоткрыты, неwave4/DAE. РеальныйABNOT_RUN доотчёта.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 7. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import hashlib,os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3ab'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ab-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
require(git('diff','--name-status',code,'HEAD','--',*runtime)=='A\tsrc/xgw/ownership.py','source diff не одно добавление')
require(hashlib.sha256((repo/'src/xgw/ownership.py').read_bytes()).hexdigest()=='2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5','module SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3ab — dormant registry foundation в sandbox')
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
