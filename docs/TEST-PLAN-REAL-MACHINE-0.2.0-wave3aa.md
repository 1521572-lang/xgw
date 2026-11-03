# ТЗ Flash: wave3aa — lifetime admission и незавершённые writers

## 1. Основание и scope

Zreport2a5b1fbfa722c7995a783e2b3c0744cd3757aba5 принят:19/19,3realprocesscases/4children,
runtimegatesfalse; workingHEALTHY/on/pool/versions/связь сохранны. Z19/Y6/X26/W25 НЕ повторять.
Подробно REVIEW-REAL-MACHINE-0.2.0-wave3z.md. SnapshotYrootmaterial не читать.

AA проверяет новый test-only ticketgate, а не установленный XGW. Короткий registryflock
учитывает durable writer tickets; callback идёт без этого flock, но lease запрещён до
завершения всех tickets. Новое acquire при занятых writers не ставит PENDING и не мешает
вложенному lifecyclehook. Ошибки/UNKNOWN/COMMITTING не снимаются автоматически.
Реальные productcallsiteintegration/bootidentity/repair/verifier пока NOT_IMPLEMENTED.
Контракт ADR-REC-C-ADMISSION-LIFETIME.md; sourceaudit REC-C-CALLSITES-AND-BOOTSTRAP.md.

ТОЛЬКО ThinkCentre; рабочая LAN XGW→роутер→устройства — baseline, hostнеLANUDP/IPv6/DNS/E4proof.
PreserveHEALTHY/on/WAN/LAN/Tailscale/pin/pool/config/службы/живыеправила. Always_off запрещён;
incomingoutage>1мин не исправляется следующей командой модели. AAне создаёт сетевой отказ.

Один batch22 новых cases, три realprocesscases/три собственных child. Один отчёт.
Callbacks — заглушки, а не nft/API/services. Нет systemdunits/timer/guardian/arm/fault.
Общие STOP baseline/identity/privacy; optionalcasefailure → остальныеcases автоматически.

## 2. Идентичность и разрешённые эффекты

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7; actualHEAD/tree записать.
Новый tests/stand/wave3_writer_tickets.py SHA256 **7b3a99ac9ecc6e53f317c4e73389c28deaf8aec48e14c2fd8b3808574cacedfe**.
Зависимость tests/stand/wave3_writer_fence_dry.py SHA256 **be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b** НЕ изменена;
она копируется как ledger.py и импортируется только как библиотека Store/read/create.
Zbatch/peer/main НЕ запускаются; Znotes/run не читаются. Новый helper CLIbatch обычным
пользователем Python-I-B, internal_peer вручную запрещён. Roothelper отвергается.

Ownernotes ~/xgw-w3aa0700, tickets.py и ledger.py0600. Только syntheticcasefiles в sandbox,
controller/result/progress/report в notes и один проверенный Markdown в Git. Все
state/tickets/tokens/identities/inodes private. Никаких /run/xgw и rootYmaterials.
Поколения gN/roles тестовые, не реальные поколения XGW. Новый ledgerid в AAне Zlease.

Разрешены readonlyNNP/sudo/status/pool, GitFF; собственные localfiles/flock/fsync/rename,
три собственных Pythonchild и их boundedcleanup. Времяlease виртуальное. Helpertimeout30с
не45сnetworkrecovery. Childcommunicate4с, cleanup1+1с. При controllerloss child сам имеет
только boundedлокальныеоперации; absencechildren послеобрыва не объявлять доказанным.

Запрещены off/install/G1/enable/disable/restart/reload/killчужих/новыеunits/timers/guardian/
arm/replay/fault/nft/ipmutations/nft-c/APImutations/configwrites/pin/pool/WAN/LAN/TSchanges,
curl/GET/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtests/новаяопись/новыеcoreversions.
Gitdelivery не VPNprobe. Не повторять installed110tree/oldhelpers/прошлые tests.

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
notes=Path.home()/'xgw-w3aa'
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

### S2.1. Чистая freepool, FF и runtime identity

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 2a5b1fbfa722c7995a783e2b3c0744cd3757aba5 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Нужен SOURCE_PREFLIGHT_OK/rc0. HEAD/tree записать. Dirty/dругая ветка/runtime diff/неFF
→ общий STOP, не reset/checkout/rebase/force и не копирование поверх. Новое ТЗ не установка.
Модель не импортирует installed XGW: повтор полного110-module parser-tree check здесь
не выполняется и не считается новым evidence. Ранее принятые проверки V не переписывать.

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

### S2.4. Заморозить два проверенных helper в notes

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3aa'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o7777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','tickets-started.json','tickets-result.json','sandbox')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
expected={'tickets.py':('wave3_writer_tickets.py','7b3a99ac9ecc6e53f317c4e73389c28deaf8aec48e14c2fd8b3808574cacedfe'),
          'ledger.py':('wave3_writer_fence_dry.py','be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b')}
for target,(source,digest) in expected.items():
    path=notes/target
    raw=(Path.home()/'zcod/xgw/tests/stand'/source).read_bytes()
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
print('WRITER_TICKETS_FROZEN',len(expected))
PY
```

Нужен WRITER_TICKETS_FROZEN2/rc0. Два совпадающих файла допускаются для возобновления
подготовки; чужой/частичный файл STOP_IDENTITY, без overwrite/newnotes. Затем S2.4b ОБЯЗАТЕЛЕН.
Freezeне запускает ledgerbatch/worker и не устанавливает runtime.

#### S2.4b. Проверить freeze и отсутствие предыдущего запуска

```bash
python3 -I -B - <<'PY'
import hashlib,os,stat
from pathlib import Path
notes=Path.home()/'xgw-w3aa'
expected={'tickets.py':'7b3a99ac9ecc6e53f317c4e73389c28deaf8aec48e14c2fd8b3808574cacedfe','ledger.py':'be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b'}
ok=os.geteuid()!=0 and not notes.is_symlink() and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o7777==0o700
for name,digest in expected.items():
    path=notes/name
    if not path.exists() or path.is_symlink():
        ok=False
        continue
    info=path.stat()
    ok=ok and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o7777==0o600 and info.st_nlink==1 and hashlib.sha256(path.read_bytes()).hexdigest()==digest
unused=not any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','tickets-started.json','tickets-result.json','sandbox'))
print('WRITER_TICKETS_READY' if ok and unused else 'STOP_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

Только WRITER_TICKETS_READY/rc0 разрешает S3.1. Если есть started/result/sandbox — S3.2,
не новый batch. При возобновлении после обрыва сразу S3.2; не freeze/restart/cleanup.

## 5. S3 — все22 сценариев одним запуском

### S3.1. Однократный запуск и сохранение результата

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
notes=Path.home()/'xgw-w3aa'
model=notes/'tickets.py'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if not model.exists() or model.is_symlink() or model.stat().st_uid!=os.getuid() or model.stat().st_mode&0o777!=0o600 or hashlib.sha256(model.read_bytes()).hexdigest()!='7b3a99ac9ecc6e53f317c4e73389c28deaf8aec48e14c2fd8b3808574cacedfe':
    raise SystemExit('STOP_FROZEN_WRITER_TICKETS_SHA')
ledger=notes/'ledger.py'
if not ledger.exists() or ledger.is_symlink() or ledger.stat().st_uid!=os.getuid() or ledger.stat().st_mode&0o7777!=0o600 or ledger.stat().st_nlink!=1 or hashlib.sha256(ledger.read_bytes()).hexdigest()!='be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b':
    raise SystemExit('STOP_FROZEN_LEDGER_SHA')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','tickets-started.json','tickets-result.json','sandbox')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
fd=os.open(notes/'controller-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump({'started':True},out)
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(model),'batch'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=False)
    data=json.loads(proc.stdout)
    valid=(isinstance(data,dict) and data.get('scope')=='COOPERATIVE_ADMISSION_LIFETIME_USER_SANDBOX'
           and data.get('runtime_recovery_implemented') is False
           and data.get('runtime_writer_fence_installed') is False
           and data.get('active_faults_authorized') is False
           and data.get('network_requests')==0 and data.get('live_gateway_operations')==0
           and data.get('total')==22 and len(data.get('cases',[]))==22
           and data.get('real_process_cases')==3 and data.get('virtual_lease_boundaries') is True)
    if not valid:
        raise ValueError('shape')
    good=(proc.returncode==0 and data.get('marker')=='WRITER_TICKETS_DRY_RECORDED'
          and data.get('passed')==22 and all(r.get('passed') is True for r in data['cases'])
          and data.get('real_process_cases_passed')==3 and data.get('children_started')==3)
    result={'command_rc':proc.returncode,'data':data,'shape_valid':True,'all_cases_passed':good}
except subprocess.TimeoutExpired:
    result={'command_rc':124,'runner_marker':'WRITER_TICKETS_RUN_TIMEOUT','all_cases_passed':False}
except Exception:
    result={'command_rc':None,'runner_marker':'WRITER_TICKETS_RUN_OR_READOUT_FAILED','all_cases_passed':False}
fd=os.open(notes/'controller-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump(result,out)
    out.write('\n')
print(json.dumps(result))
raise SystemExit(0 if result['all_cases_passed'] else 3)
PY
```

Успех: rc0, command_rc0, shape_valid=true, all_cases_passed=true,
marker=WRITER_TICKETS_DRY_RECORDED, passed=total=22, все case.passed=true.
Также ОБЯЗАТЕЛЬНО все три runtime/fence/active flags=false, real_process_cases_passed=3,
children_started=3 и virtual_lease_boundaries=true. real_process_cases=3 — число определённых
процессных cases, успешность каждого подтверждается отдельно.
Если любой из runtime/fence/active flags стал true — scope неверен; это не готовность recovery.

Rc3/failed case/timeout/ошибка формата не разрешают retry или починку кода на шлюзе.
Сценарии уже выполняются независимо внутри одного batch; сохранить все полученные
результаты и перейти к S3.2/S4/отчёту. WRITER_TICKETS_RUN_TIMEOUT завершает только собственный
дочерний Python-модели, не службы/ядра. Критический material сети модель не трогала.
После обрыва — S3.2, не S3.1. Exclusive controller-started/tickets-started препятствуют повтору.

### S3.2. Прочитать сохранённый итог либо безопасный checkpoint

```bash
python3 -I -B - <<'PY'
import json,os
from pathlib import Path
notes=Path.home()/'xgw-w3aa'
for name in ('controller-result.json','tickets-result.json','tickets-progress.json'):
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

Один dispatcher: controller-result содержит rc команды и helperdata; tickets-result —
окончательный helper итог, если controller его не сохранил; tickets-progress — checkpoint
с final=false, не законченный batch. При неуспешном controller читается следующий
доступный итог/checkpoint в том же блоке. Не переносить checkpoint в финальный PASS.
Нет файлов → INTERRUPTED_UNKNOWN. Read rc0 не означает22/22. S3.1 не повторять.
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

### S4.3. Интерпретация всех22 новых cases

Нужны commandrc0/shapevalidtrue/allcasestrue/WRITER_TICKETS_DRY_RECORDED/22of22,
real_process_cases_passed3/children_started3, runtimefence/recovery/activeflagsfalse,
networkrequests/liveoperations0. Rc3/PARTIAL → всеcasebools/fixedreason/errorclass в отчёт,
без исправлений/повтора. НижеследующиеcaseIDs сверить с фактическим safe readout.

| № | Case ID |
|---|---|
|1|SUCCESS_PUBLISHES_BEFORE_DRAIN|
|2|LEASE_REFUSED_INSIDE_CALLBACK|
|3|REAL_CHILD_HOOK_ADMITTED_WITH_PARENT_TICKET|
|4|REAL_CHILD_LEASE_REFUSED_DURING_CALLBACK|
|5|REAL_OWNER_EXIT_DOES_NOT_DRAIN_TICKET|
|6|ARMED_PREVENTS_CALLBACK_ENTRY|
|7|DRAIN_REQUIRED_BEFORE_ARM|
|8|FAILED_ACQUIRE_NEVER_SETS_PENDING_BARRIER|
|9|PARTIAL_CALLBACK_ERROR_RETAINS_UNKNOWN|
|10|FALSE_VERIFIER_NEVER_DRAINS|
|11|STRING_VERIFIER_NEVER_DRAINS|
|12|VERIFIER_ERROR_RETAINS_TICKET|
|13|DUPLICATE_COMPLETION_REJECTED|
|14|CROSS_ROLE_TOKEN_REJECTED|
|15|UNKNOWN_HAS_NO_AUTOMATIC_RETIREMENT|
|16|OUT_OF_ORDER_COMPLETIONS_ADVANCE_GENERATION|
|17|ROLE_AND_INFLIGHT_LIMITS_REJECTED|
|18|MALFORMED_REGISTRY_BLOCKS_ADMISSION_AND_LEASE|
|19|EXPIRED_LOGICAL_LEASE_STILL_BLOCKS_WRITERS|
|20|FAILED_GENERATION_PUBLICATION_NEVER_DRAINS|
|21|PUBLISHED_GENERATION_WITH_FAILED_CLEANUP_STAYS_BLOCKED|
|22|REOPEN_NEVER_PRUNES_ORPHAN_TICKET|

Три REAL_*cases — каждый по одному child: hookadmission при parentticket, leaserefusal
внутри callback и ownerexit безdrain. Ожидаются details.child_rc0/fixed_output_matchedtrue.
Порядок registryoperations реальный, но calls не настоящий systemctl/TUN. Первые два
показывают новый lifecycleпротокол, а не повтор Zconcurrentgenerationcase.

Ошибки generationpublication/cleanup специально инжектируются только в syntheticfiles/
метод testGate. COMMITTING сохраняется до cleanup, повтор completion отвергается.
UNKNOWN не retirement и не recovery. Непустой LIVEticket после childexit не удаляется.
Не интерпретировать durableticket как доказанное отсутствие всех kernelwriters или
гарантию восстановления: продукт ещё не использует tickets.

Status/pool — только bookends. Ykernel/RPDB/config/unitsafter и Z19 не новое evidenceAA.
Leaseclock synthetic, verifiedTrue вcallback — заглушка. Yrootmaterial не читался,
snapshotPLANNED_NOT_ARMED. Реальные fence/driver/activeflagsfalse даже22/22.

## 7. Один отчёт и privacy review

Заполнить TEMPLATE в ~/xgw-w3aa/report.md: testedHEAD/tree/pin/runtimeempty, обаSHA/
ownerfreeze, NNP/sudo/owneractions, before/afterHEALTHY/on/pool/versions/связь.
Отдельно controllercommandrc/helpermarker/filetype,22casebools и3processdetails/childrc,
childrenstarted, virtualclock, runtimefalseflags. При checkpointonly completed +
фактическиеcases; остальные NOT_RUN, finalmarkerUNKNOWN. Не повторять S3.1.

Privateledger/tickets/identity/tokens/inodes/casefiles/rawstdout неизвестногоchild не
печатать/не Git/не скрин. ТолькоfixedcaseIDs/bools/counts/enums/sourceSHA/Git/rc.
Никаких URL/URI/IP/MAC/UUID/ключей/паролей/SNI/портов/реальныхtags/PID/NIC/homepaths/
rawstatus/config/logs/privatehashes/screenshots/исключений. Один проверенный Markdown.

После отчёта не переходить автоматически к Cinstallation/D/E/fault. Следующая разработка
по ADR/admission и аудитуматрице: productregistry/entrypoints/receipts, затем fake-only
независимый driver и отдельный bootstraprescue. Код AA не устанавливать в XGW.
OnlyThinkCentre/workingLAN, fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS
открыты, неwave4/DAE. Реальный AA NOT_RUN до фактического отчёта.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 7. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3aa'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3aa-'+stamp.date().isoformat()+'.md'
require(not (repo/relative).exists(),'такой отчёт уже существует; не перезаписывать')
git('fetch','-q','origin','freepool')
git('merge','--ff-only','origin/freepool')
git('merge-base','--is-ancestor',code,'HEAD')
require(not git('diff','--name-only',code,'HEAD','--',*runtime),'runtime изменён после ТЗ')
require(not git('status','--porcelain'),'клон изменился во время подготовки')
(repo/relative).write_bytes(draft)
git('add','--',relative)
require(git('diff','--cached','--name-only').splitlines()==[relative],
        'в индексе есть что-то кроме отчёта; не делать commit')
git('diff','--cached','--check')
git('commit','-m','Отчёт: XGW 0.2.0, wave3aa — lifetime admission в sandbox')
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
