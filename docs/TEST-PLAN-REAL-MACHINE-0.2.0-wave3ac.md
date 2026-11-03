# ТЗ Flash: wave3ac — максимальный готовый пакет A/B/D-fake, 51 сценарий

## 1. Объём, основание и независимость ветвей

ABreportcce1d22c952482b556a315fece63274ed78c239e принят:32/32,3realprocesscases/4children;
workingHEALTHY/on/pool/versions/связь прежние. REVIEW-REAL-MACHINE-0.2.0-wave3ab.md.
AB32/AA22/Z19/Y6/X26/W25/прошлыеbatches НЕ повторять, Yrootmaterial не читать.

Прямое указание владельца: максимальный объём готовой работы за один заход без потери
качества. Один start исполняет28A+16B+7D=51 независимый case и сохраняет одинsummary.
Casefail→остальныеcases/ветви автоматически, без промежуточных вопросов/микроТЗ. Один
финальныйMarkdown. Globalidentity/baseline/privacy/filesystemSTOP сохраняются; зависимый
liveэтап не добавлять ради объёма. Этот принцип применять и к последующим заданиям.

A — genericcallbackadapter/verifierassertions/cleanup/ackerrors. B — read-onlydiagnostics
state/stage/boot/metadata, **неrepair**. D — конечный detachedfakeprocess, который возвращает
ТОЛЬКОфайлвusercase кBASELINE послеexit/crashсвоегоcontroller. Ни systemd, ни сеть,
ни реальныйXGWdriver. Никаких новыхunits/timers/networkguardians. ADR-REC-C-ADAPTERS-AND-FAKE-D.md.

ТОЛЬКОThinkCentre; workingLAN/HEALTHY/on — baseline. HostнеLANUDP/IPv6/DNS/E4proof.
Preserve WAN/LAN/Tailscale/pin/pool/config/services/rules. Always_off запрещён;
incomingoutage>1мин не исправляется следующейкомандоймодели. ACне вызываетсетевойотказ.

## 2. Идентичность и допустимые эффекты

Productbaseline351fb54e074f4a7b497a8a4244fc74c6088788d7. Source diffтеперь **ровно3добавления**:
ownership.py/ownership_adapters.py/ownership_diagnostics.py вsrc/xgw. ABownership.pyбезизменений.
Прежниеsrc/packaging/config/CLI/entrypoints/standhelpers неизменны. Новыемодули не
импортируютсясуществующимruntime, не устанавливаются, не активируются. Полный sourcediff
непустой; installedruntimeпрежний. Неpipinstall/xgwinstall/restart/reload.

Freeze5files в ~/xgw-w3ac0700, файлы0600/owner/nlink1/regular; при starthelper проверяет4
зависимости поSHA и импортируетprivatepackagefrozen_ac, **не installedXGW**. Python-I-B,
ordinaryUIDonly. SOURCE SHA:

| Frozenfile | Source | SHA256 |
|---|---|---|
|batch.py|tests/stand/wave3_writer_superbatch.py|3d6b821fd2197043456c2c2d004056f401a1ca7ed5ff08f58f3e147494062b2f|
|ownership.py|src/xgw/ownership.py|2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5|
|ownership_adapters.py|src/xgw/ownership_adapters.py|70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3|
|ownership_diagnostics.py|src/xgw/ownership_diagnostics.py|f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d|
|fake_driver.py|tests/stand/wave3_fake_recovery.py|a287ed4d611a5a1f10d9d7c2043c83367282f89265b50d4a844f034c944fc81b|

Разрешены GitFF,NNP/sudo/status/poolreadonly, usernotes/casefiles/flock/fsync/rename и
ограниченные собственные Pythonprocesses. Registryboot/clocksynthetic. Dclockнастоящий
monotonic, но толькоfakefile. Driverdispatchwindow1с/restoredue1.5с/measuredhardbudget4с,
within_budgetfalse→FAIL; это НЕ45среальнойсети. Controllerlate2с должен отказатьfakefault.
Контрольныеstart/status/show/collector не входят в счётчики workloadchildren.

Нельзя off/install/G1/enable/disable/WAN/LAN/Tailscale/config/pin/pool/service/rules/
APIwrites/nft-c/nft/ipmutations/GET/curl/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtest/
coreversionprobes/новаяопись/newunits/timers/guardian/arm/replay/real faults. GitнеVPNprobe.
РеальныйrootDAC/boot/реальныеverifiers/fence/repair/recovery/bootstrap NOT_RUN/NOT_IMPLEMENTED.
YsnapshotPLANNED_NOT_ARMED/неиспользован. Onlyprivatefakecasefiles — неrootY/runtimepaths.

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
notes=Path.home()/'xgw-w3ac'
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

### S2.1. Чистаяfreepool/FF/ровно3sourceдобавления с exactSHA

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
git('merge-base','--is-ancestor','cce1d22c952482b556a315fece63274ed78c239e','HEAD')
runtime=['src','packaging','config.example.toml','pyproject.toml','tests/stand/wave3_safety.py','tests/stand/wave3_enable_probe.py']
expected={'src/xgw/ownership.py': '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5', 'src/xgw/ownership_adapters.py': '70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3', 'src/xgw/ownership_diagnostics.py': 'f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d'}
changes=git('diff','--name-status','351fb54e074f4a7b497a8a4244fc74c6088788d7','HEAD','--',*runtime).splitlines()
require(changes==['A\t'+name for name in sorted(expected)],'SOURCE_DIFF_NOT_THREE_ADDITIONS')
for name,digest in expected.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'MODULE_SOURCE_SHA')
print('SOURCE_DIFF_THREE_DORMANT_ADDITIONS')
print('TESTED_HEAD',git('rev-parse','HEAD'))
print('TESTED_TREE',git('rev-parse','HEAD^{tree}'))
print('SOURCE_PREFLIGHT_OK')
PY
```

Нужны rc0/SOURCE_DIFF_THREE_DORMANT_ADDITIONS/SOURCE_PREFLIGHT_OK. ActualHEAD/tree записать.
Dirty/mismatch/nonFF→STOP, безreset/rebase/force/перекопирования/установки. Installed110tree
не повторять. Пустойsource diff тоже mismatch: необходимы3 reviewednewmodules.

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

### S2.4. Заморозить все5files одним блоком

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ac'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o7777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
used=('started.json','worker-claimed.json','progress.json','summary.json','sandbox')
if any((notes/name).exists() or (notes/name).is_symlink() for name in used):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
expected={'batch.py': ('tests/stand/wave3_writer_superbatch.py', '3d6b821fd2197043456c2c2d004056f401a1ca7ed5ff08f58f3e147494062b2f'), 'ownership.py': ('src/xgw/ownership.py', '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5'), 'ownership_adapters.py': ('src/xgw/ownership_adapters.py', '70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3'), 'ownership_diagnostics.py': ('src/xgw/ownership_diagnostics.py', 'f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d'), 'fake_driver.py': ('tests/stand/wave3_fake_recovery.py', 'a287ed4d611a5a1f10d9d7c2043c83367282f89265b50d4a844f034c944fc81b')}
for target,(source,digest) in expected.items():
    raw=(Path.home()/'zcod/xgw'/source).read_bytes()
    if len(raw)>131072 or hashlib.sha256(raw).hexdigest()!=digest:
        raise SystemExit('STOP_SOURCE_SHA')
    path=notes/target
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o7777!=0o600 or info.st_nlink!=1 or path.read_bytes()!=raw:
            raise SystemExit('STOP_EXISTING_FREEZE_MISMATCH')
        continue
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw)
print('WRITER_SUPERBATCH_FROZEN',len(expected))
PY
```

Нужен WRITER_SUPERBATCH_FROZEN5/rc0. Совпадающиефайлы допускаются только для resumeподготовки
доstart; частичный/mismatchfile→STOP_IDENTITY, неoverwrite/newnotes. Послеstartedникакойfreeze.

#### S2.4b. Все5SHA и unused перед единственнымstart

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3ac'
expected={'batch.py': '3d6b821fd2197043456c2c2d004056f401a1ca7ed5ff08f58f3e147494062b2f', 'ownership.py': '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5', 'ownership_adapters.py': '70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3', 'ownership_diagnostics.py': 'f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d', 'fake_driver.py': 'a287ed4d611a5a1f10d9d7c2043c83367282f89265b50d4a844f034c944fc81b'}
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
for name,digest in expected.items():
    path=notes/name
    if not path.exists() or path.is_symlink():
        ok=False
        continue
    info=path.stat()
    ok=ok and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
unused=not any((notes/name).exists() or (notes/name).is_symlink() for name in ('started.json','worker-claimed.json','progress.json','summary.json','sandbox'))
print('WRITER_SUPERBATCH_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

Только READY/rc0→S3.1. Alreadystarted→S3.2/S3.3, без повторногоstart/worker/driver/notes.

## 5. S3 — единый независимый usercollector на весь готовый объём

### S3.1. Единственный start

```bash
python3 -I -B "$HOME/xgw-w3ac/batch.py" start
```

Нужны WRITER_INTEGRATION_BATCH_STARTED/rc0. Это только успешныйPopencollector, ещё не51PASS.
Collectorпишет EXCLworker-claimed иpercaseprogress. Онконечныйuserprocess, неsystemdservice/
networkguardian. Внутренние _batch/_hold/_controller/_driver вручную НЕвызывать.
Не root. Повторныйstartзапрещён даже послеrc3/обрыва/timeout/отсутствияsummary.

### S3.2. Один автоматическийmonitor всехветвей, не микрокоманды

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys,time
from pathlib import Path
model=Path.home()/'xgw-w3ac/batch.py'
limit=time.monotonic()+180
previous=None
while time.monotonic()<limit:
    try:
        proc=subprocess.run([sys.executable,'-I','-B',str(model),'status'],capture_output=True,text=True,timeout=8,check=False)
        if proc.returncode!=0:
            print('MONITOR_READ_FAILED',proc.returncode)
            raise SystemExit(3)
        value=json.loads(proc.stdout)
        if value.get('file')=='summary.json':
            print('BATCH_FINISHED',value['data'].get('marker'),value['data'].get('passed'),value['data'].get('total'))
            raise SystemExit(0)
        completed=value.get('data',{}).get('completed')
        if completed!=previous:
            print('BATCH_PROGRESS',completed)
            previous=completed
    except (OSError,ValueError,subprocess.TimeoutExpired):
        print('MONITOR_READ_UNAVAILABLE')
        raise SystemExit(3) from None
    time.sleep(5)
print('BATCH_OBSERVATION_TIMEOUT')
raise SystemExit(3)
PY
```

BATCH_FINISHED значит summaryнайден, неcasePASS.180с — пределнаблюдателя, неdeadlineсети.
Monitorrc3/обрыв→S3.3/statusbookends/report, неstart/retry/killcollector/службы. Collector
можетдописатьsummaryпозже; разрешено толькоstatus/show. Сохранённыйcheckpoint неfinal.

### S3.3. Один fullreadout и проверка формы результата

```bash
python3 -I -B - <<'PY'
import json,subprocess,sys
from pathlib import Path
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(Path.home()/'xgw-w3ac/batch.py'),'show'],capture_output=True,text=True,timeout=8,check=False)
    if proc.returncode!=0:
        print('SHOW_FAILED',proc.returncode)
        raise SystemExit(3)
    wrapper=json.loads(proc.stdout)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('SHOW_UNAVAILABLE') from None
print(json.dumps(wrapper))
if wrapper.get('file')!='summary.json':
    print('FINAL_NOT_RECORDED_USE_CHECKPOINT')
    raise SystemExit(3)
data=wrapper['data']
expected=['A01_CAPTURE', 'A02_PANEL', 'A03_PEERS', 'A04_CORE', 'A05_API', 'A06_TUN_HOOK', 'A07_LIFECYCLE', 'A08_FENCED_NO_CALLBACK', 'A09_UNKNOWN_NO_CALLBACK', 'A10_OPERATION_ERROR', 'A11_VERIFIER_ERROR', 'A12_DEFAULT_EVIDENCE', 'A13_BARE_BOOL_EVIDENCE', 'A14_FALSE_CHECK', 'A15_STRING_CHECK', 'A16_DUPLICATE_CHECK', 'A17_UNKNOWN_CHECK', 'A18_LIST_CHECKS', 'A19_UNKNOWN_OUTCOME', 'A20_NOOP_RECEIPT', 'A21_ROLLBACK_RECEIPT', 'A22_KEYBOARD_INTERRUPT', 'A23_SYSTEM_EXIT', 'A24_PRE_REPLACE_ACK', 'A25_POST_REPLACE_ACK', 'A26_UNKNOWN_RECORD_FAILURE', 'A27_NESTED_ADMISSION', 'A28_EMPTY_CHECKS', 'B01_CLEAN_READONLY', 'B02_LIVE_READONLY', 'B03_UNKNOWN_READONLY', 'B04_ARMED_READONLY', 'B05_RUNNING_READONLY', 'B06_VALID_STAGE_NOT_PROMOTED', 'B07_TRUNCATED_STAGE', 'B08_FOREIGN_STAGE', 'B09_STALE_STAGE', 'B10_DUPLICATE_STAGE_KEYS', 'B11_BOOT_MISMATCH', 'B12_BAD_MODE', 'B13_STAGE_SYMLINK', 'B14_CORRUPT_BASELINE_NO_ZERO_COUNTS', 'B15_ABSENT_STORE_NOT_CREATED', 'B16_REAL_BUSY_DIAGNOSTIC', 'D01_CONTROLLER_EXIT_FAKE_RESTORE', 'D02_CONTROLLER_CRASH_FAKE_RESTORE', 'D03_UNUSED_EXPIRES', 'D04_LATE_DISPATCH_REFUSED', 'D05_EXPECTED_FAKE_RESTORE_FAILURE', 'D06_FOREIGN_NONCE_REFUSED', 'D07_BAD_BASELINE_REFUSED']
rows=data.get('cases',[])
shape=(data.get('scope')=='DORMANT_ADAPTER_DIAGNOSTIC_AND_FAKE_FILE_DRIVER' and data.get('total')==51
       and [r.get('case') for r in rows]==expected
       and all(data.get(k) is False for k in ('installed_runtime_changed','runtime_entrypoints_integrated','runtime_writer_fence_installed','runtime_recovery_implemented','active_faults_authorized','repair_implemented'))
       and data.get('network_requests')==0 and data.get('live_gateway_operations')==0
       and data.get('virtual_registry_boot_and_clock') is True and type(data.get('fake_driver_clock_measured')) is bool)
good=(shape and data.get('marker')=='WRITER_INTEGRATION_BATCH_RECORDED' and data.get('passed')==51
      and all(r.get('passed') is True for r in rows)
      and data.get('real_process_cases')==8 and data.get('real_process_cases_passed')==8
      and data.get('collector_children_started')==8 and data.get('driver_launch_observations')==7
      and data.get('fake_positive_restorations')==2 and data.get('fake_expected_failures')==1
      and data.get('fake_expected_refusals')==2 and data.get('fake_unused')==2
      and data.get('fake_driver_clock_measured') is True and data.get('fake_driver_timings_observed')==5)
print('FINAL_SHAPE_VALID',shape)
print('ALL_CASES_PASSED',good)
raise SystemExit(0 if good else 3)
PY
```

Отдельно записать start/monitor/show/shapecommandrc и collector_exit_rc=NOT_COLLECTED.
Асинхронныйcollector не имеет commandrc0 из show0. Summaryfile — финальные собранные
данные; progressfilefinalfalse — только completed/cases, остальные NOT_RUN. Нетфайлов→
INTERRUPTED_UNKNOWN. Не beforeкакafter/не0вместоUNKNOWN. Partialнеповодповторять.

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

### S4.3. Все51cases, отдельные семантические решения

| № | Case ID |
|---|---|
|1|A01_CAPTURE|
|2|A02_PANEL|
|3|A03_PEERS|
|4|A04_CORE|
|5|A05_API|
|6|A06_TUN_HOOK|
|7|A07_LIFECYCLE|
|8|A08_FENCED_NO_CALLBACK|
|9|A09_UNKNOWN_NO_CALLBACK|
|10|A10_OPERATION_ERROR|
|11|A11_VERIFIER_ERROR|
|12|A12_DEFAULT_EVIDENCE|
|13|A13_BARE_BOOL_EVIDENCE|
|14|A14_FALSE_CHECK|
|15|A15_STRING_CHECK|
|16|A16_DUPLICATE_CHECK|
|17|A17_UNKNOWN_CHECK|
|18|A18_LIST_CHECKS|
|19|A19_UNKNOWN_OUTCOME|
|20|A20_NOOP_RECEIPT|
|21|A21_ROLLBACK_RECEIPT|
|22|A22_KEYBOARD_INTERRUPT|
|23|A23_SYSTEM_EXIT|
|24|A24_PRE_REPLACE_ACK|
|25|A25_POST_REPLACE_ACK|
|26|A26_UNKNOWN_RECORD_FAILURE|
|27|A27_NESTED_ADMISSION|
|28|A28_EMPTY_CHECKS|
|29|B01_CLEAN_READONLY|
|30|B02_LIVE_READONLY|
|31|B03_UNKNOWN_READONLY|
|32|B04_ARMED_READONLY|
|33|B05_RUNNING_READONLY|
|34|B06_VALID_STAGE_NOT_PROMOTED|
|35|B07_TRUNCATED_STAGE|
|36|B08_FOREIGN_STAGE|
|37|B09_STALE_STAGE|
|38|B10_DUPLICATE_STAGE_KEYS|
|39|B11_BOOT_MISMATCH|
|40|B12_BAD_MODE|
|41|B13_STAGE_SYMLINK|
|42|B14_CORRUPT_BASELINE_NO_ZERO_COUNTS|
|43|B15_ABSENT_STORE_NOT_CREATED|
|44|B16_REAL_BUSY_DIAGNOSTIC|
|45|D01_CONTROLLER_EXIT_FAKE_RESTORE|
|46|D02_CONTROLLER_CRASH_FAKE_RESTORE|
|47|D03_UNUSED_EXPIRES|
|48|D04_LATE_DISPATCH_REFUSED|
|49|D05_EXPECTED_FAKE_RESTORE_FAILURE|
|50|D06_FOREIGN_NONCE_REFUSED|
|51|D07_BAD_BASELINE_REFUSED|

A28/B16/D7 — количестваcases по ветвям, не packetproof. Bdiagnosticdetails fixedcounts/
classificationsonly, missingbaselinecountsNone не0. STAGE_VALID_UNPROVEN неразрешениеrepair.
AdapterCOMPLETEDтолькоcallerassertion+registryreceipt, неготовыйKERNEL/APIverifier.

Процессныеcases8=B16holder+7D. Workloadcollectorchildren8=holder1+controllers7; отдельные
driverlaunchobservations7 из artifacts. Start/status/show/collectorне входят в этисчётчики.
B16detailsbounded_refusal/holder_rc/own_child_cleanup_confirmed раздельно. Не считать
terminateownfixturechild действием надслужбой XGW. Остальныеcasesнеpollуютсеть.

| D | Controller rc | Final | Fakebaseline | Dispatch | Интерпретация |
|---|---|---|---|---|---|
| D01 |0|FAKE_RESTORED|true|true|положительныйфайловыйвозврат |
| D02 |9|FAKE_RESTORED|true|true|положительныйвозвратпослеcontrollercrash |
| D03 |0|EXPIRED_UNUSED|true|false|небылоfault, неrestore |
| D04 |0|EXPIRED_UNUSED|true|false|latefaultнепрошёл |
| D05 |0|FAILED|false|true|ожидаемыйfailure; casePASS≠restored |
| D06 |3|REFUSED|true|false|чужойnonceотвергнут |
| D07 |3|REFUSED|false|false|чужойbaselineотвергнут |

Ddetails: observed/expectedphase,controller_rc,driver_launch_observed,fault_dispatched,
fake_baseline,elapsed_ms,within_budget,timing_measured. D01–D05 дают5 настоящих timingobservations;
D06/D07 отказали доARMED: timing_measuredfalse/elapsed_msnull/within_budgetnull, не нулевая длительность.
Время от fakeARMED до финальногоfilewrite, не
end-to-endизустановки/45ссети. within_budgetfalse — FAIL даже еслифайлпозжевосстановлен.
controller_wait_timeout/controller_cleanup_confirmed/driver_exit_rcNOT_COLLECTED/
readout_error_class сохраняютсяраздельно. При unexpectedcontrollerrc всёравно собираются
независимыеsafeartifacts безповтораjob; частичныеDdetails остаютсявfailedcase.
Artifactнеподменяетненаблюдаемыйexitcodegrandchild. AExecutiondetailsтакжесохраняются
приошибкеожидания, включаяcleanup/retainedreceiptUNKNOWN, безrawexceptions.
Положительныхrestorations2, expectedfailure1/refusals2/unused2; не7restored.
Послеисчезновенияcontroller collectorничегоневосстанавливает, тольконаблюдаетartifact.
Systemd/cgroups/reboot/suspend/power/modelappshutdown/networksurvival NOT_RUN.

Timeoutcleanup касаетсятолькособственных directchildren; статусgrandchildUNKNOWN без
результата не превращатьв«успешно завершён». Запрещены killпоголомуPID/ручнойdriver/
повторjob/restoreнастоящихrules. Всеpayloadsтолькоtestfiles, рабочаясетьнеучаствует.

Status/poolafter — толькоbookends, неYkernel/PID/RPDB/configafter. Installed110tree/
rootDAC/bootidповторNOT_RUN. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS
открыты, неwave4/DAE. Все6runtime/repairflagsfalse даже51/51.

## 7. Один отчёт, приватность, продолжение

Заполнить TEMPLATE в ~/xgw-w3ac/report.md: actualHEAD/tree/source3additions/5SHA/freeze/
NNP/sudo/owneractions/before-afterHEALTHY/on/pool/versions/связь. Все51casebools иfailed
reason/errorclass, 3cohortcounts, timings/fakephases/отрицательныерезультатыраздельно.
Start/monitor/show/shapecommandrc отдельно; collector_exit_rcNOT_COLLECTED. Partialfinal
илиcheckpointonly явноразличать. Общийread0/monitor0 неPASS. Не переносить expectedcounts
в incomplete. ОдинMarkdown, не поотчётунaкаждуюветвь.

Не Git/чат/скрин rawconfig/status/logs/kernel/realURIs/IP/MAC/UUID/keys/passwords/SNI/
ports/fp/tags/PID/NIC/UID/homepaths/privatehashes/boot/registryids/tokens/nonce/timestamps/
rawcasefiles/unknownchildstdout/исключения. Толькоfixedenums/caseIDs/bools/counts/
timingsms/rc/Git/sourceSHA. ЧитатьвесьMarkdownпередединственнойпубликацией.

ПослеAC — fixesпоevidenceилиследующийукрупнённыйготовыйdormantintegration/repair/
bootstrapdryпакет. Неliveinstall/service/networkmutations/C-Earming. Реальный C-ENTRY,
verifier/fence/repair/driver/bootstrapещёNOT_IMPLEMENTED. OnlyThinkCentre/workingLAN;
hostнеLANclient. РеальнаяAC NOT_RUN дофактическогоотчёта.

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
notes=Path.home()/'xgw-w3ac'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ac-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
expected={'src/xgw/ownership.py': '2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5', 'src/xgw/ownership_adapters.py': '70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3', 'src/xgw/ownership_diagnostics.py': 'f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d'}
require(git('diff','--name-status',code,'HEAD','--',*runtime).splitlines()==['A\t'+name for name in sorted(expected)],'source diff не три добавления')
for name,digest in expected.items():
    require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'module SHA изменился')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3ac — adapters diagnostics и fake-process batch')
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
