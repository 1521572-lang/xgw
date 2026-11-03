# ТЗ Flash: wave3z — cooperative writer fence в пользовательском sandbox

## 1. Основание и scope

Y1440d51558636a6059c4b7f211abc4561908aee7 принят:6/6, guard10/10/dropcount5/reject0,
полный REC-B snapshot/check-only0/afterstable/manifestPLANNED_NOT_ARMED, working on сохранён.
Z не использует root material Y и не запускает snapshot-код. Y6/X26/W25/старые network checks
не повторять. Подробно REVIEW-REAL-MACHINE-0.2.0-wave3y.md.

Новый REC-C candidate проверяет только synthetic state generation/epoch/owner в отдельных
файлах обычного владельца. Это НЕ встроенный fence XGW и НЕ автономный recovery driver.
Никакие product writers не блокируются и не меняются. Только cooperating test peers.
Свойство flock advisory, все реальные writers ещё должны быть интегрированы.
Контракт — ADR-REC-C-OWNERSHIP.md, исходниковый аудит — REC-C-WRITER-INVENTORY.md.

Доступен ТОЛЬКО ThinkCentre. Рабочая LAN XGW→роутер→устройства считается работающей,
host не LAN UDP/IPv6/DNS/E4 proof. HEALTHY/on — baseline; preserve WAN/LAN/Tailscale/
pin/pool/config/службы/живые rules. Always_off запрещён. Входящий обрыв>1мин следующая
команда модели не исправит; Z не создаёт сетевой отказ и не проверяет независимый rescue.

Один запуск включает19 cases, в том числе ТРИ real-process cases/ЧЕТЫРЕ собственных
child процесса суммарно. Ошибка case не прекращает остальные. Один итоговый Markdown,
без вопросов разработчику после отдельных строк. Общие STOP baseline/identity/privacy
сохраняются. По окончании не переходить к live stages REC-C/D/E автоматически.

## 2. Точная идентичность, файлы и разрешённые эффекты

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7; tested actualHEAD/tree записать.
tests/stand/wave3_writer_fence_dry.py SHA256 **4a85e87eb82756bc0fbb260288b9b5ff557dfe36f47e11e7801b39a44912ed25**. Ownerfreeze в ~/xgw-w3z/fence.py,
0600, каталог0700. CLI только `batch` обычным пользователем Python3-I-B.
Внутренний `_peer` вручную запрещён; helper сам запускает фиксированные modes writer/hold/lease.
Root-запуск helper отвергается. Все настоящие UID/поколения/lease XGW вне этого кода.

Допустимы Gitfetch/FF/одинMarkdown; NNPканала/sudo/status/pool readonly; запись обычного
владельца ТОЛЬКОв ~/xgw-w3z. Private source/controller outputs и sandboxcasefiles0600,
directories0700. Stable lock/state/identity files — только synthetic. Для одного negative
case допускается замена/изменение прав только его собственного synthetic файла. Не чужой
lock/product lock. Не удалять run-каталоги/снимки Y/X и не переносить их в sandbox.

Batch делает реальные fsync/rename/flock в тестовом каталоге. Kernel/table/network/API/
service действий нет. Peer argv — этот же frozen source Python-I-B, casepath и fixedmode.
Cleanup terminate/kill разрешён только для собственных созданных children, не служб,
ядер, terminal/ZCode или любых процессов по имени. Нет pkill/ручного kill/systemctl.
Child holder сам ограничен3с; ожидание ready≤2с/communicate≤4с; controller budget30с.
Это bounds теста при работающем scheduler, не гарантия45с сетевого восстановления.

Network_requests/live_gateway_operations=0/0. runtime_writer_fence_installed=false,
runtime_recovery_implemented=false, active_faults_authorized=false — даже при19/19.
Виртуальные границы lease обозначены virtual_lease_boundaries=true. Времена1/2/10/11
в synthetic cases не реальные timestamps и не измеренные15/45с.

ЗАПРЕЩЕНО: любой install/G1/enable/disable/restart/reload/stop служб, guardian/timer/
systemd-run, nft/ip mutations И nft-c (в Z они вообще не нужны), изменение WAN/LAN/
NM/sysctl/TS/pin/pool/profile/config, APIwrites/scans/GET/curl/DNS/ping/SOCKS/SSH/pcap/
netns/speedtests/--versionядер. Нельзя вооружать root Ymanifest/fence или делать live fault.
Нет нового110module/installedruntime check: helper не импортирует XGW.

Приватность: source SHA/Git/fixedcaseIDs/bools/counts/childrc/fixedreason/errorclass.
Не публиковать sandbox state/identity/owner/epoch/generation/inode/путьhome/privateoutputs
как raw screenshots. Не выводить реальные URI/URL/IP/MAC/UUID/keys/passwords/SNI/порты/
имена/fp/tag/PID/NIC/DBrows/config/logs/kernel/inputhash/сыройexception. Child stdout
классифицируется, неизвестный текст не печатается. Никаких реальных данных в fixture.

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
notes=Path.home()/'xgw-w3z'
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
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 1440d51558636a6059c4b7f211abc4561908aee7 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
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

### S2.4. Заморозить только test adapter в notes владельца

```bash
python3 -I -B - <<'PY'
import hashlib,os,sys
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP_OWNER_REQUIRED')
notes=Path.home()/'xgw-w3z'
if notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_NOTES_METADATA')
raw=(Path.home()/'zcod/xgw/tests/stand/wave3_writer_fence_dry.py').read_bytes()
expected='4a85e87eb82756bc0fbb260288b9b5ff557dfe36f47e11e7801b39a44912ed25'
if len(raw)>131072 or hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP_FENCE_DRY_SOURCE_SHA')
if (notes/'fence.py').exists() or (notes/'fence.py').is_symlink():
    raise SystemExit('STOP_ALREADY_FROZEN_USE_S2_4b')
fd=os.open(notes/'fence.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:
    out.write(raw)
print('FENCE_DRY_FROZEN',expected)
PY
```

Нужен FENCE_DRY_FROZEN/rc0 и точный SHA. Уже существующий fence.py не перезаписывать:
если он был успешно подготовлен до остановки, выполнить S2.4b и продолжить
S3.1, если controller-started.json ещё нет. Непонятный частичный файл → STOP_IDENTITY,
не новый каталог. Копирование не создаёт драйвер/timer, не меняет /opt или/root material.

#### S2.4b. Только при возобновлении после успешной заморозки

```bash
python3 -I -B - <<'PY'
import hashlib,os
from pathlib import Path
notes=Path.home()/'xgw-w3z'
model=notes/'fence.py'
ok=(os.geteuid()!=0 and not notes.is_symlink() and notes.exists()
    and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o777==0o700
    and model.exists() and not model.is_symlink() and model.stat().st_uid==os.getuid()
    and model.stat().st_mode&0o777==0o600
    and hashlib.sha256(model.read_bytes()).hexdigest()=='4a85e87eb82756bc0fbb260288b9b5ff557dfe36f47e11e7801b39a44912ed25')
unused=not any((notes/name).exists() or (notes/name).is_symlink()
               for name in ('controller-started.json','controller-result.json','fence-started.json','fence-result.json','sandbox'))
print('FROZEN_FENCE_DRY_RESUME_OK' if ok and unused else 'STOP_RESUME_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

Только FROZEN_FENCE_DRY_RESUME_OK/rc0 разрешает S3.1. Если уже есть started/result — S3.2,
не повтор. Если нет подтверждённой заморозки — STOP_IDENTITY, файл не исправлять.

## 5. S3 — все19 сценариев одним запуском

### S3.1. Однократный запуск и сохранение результата

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
notes=Path.home()/'xgw-w3z'
model=notes/'fence.py'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if not model.exists() or model.is_symlink() or model.stat().st_uid!=os.getuid() or model.stat().st_mode&0o777!=0o600 or hashlib.sha256(model.read_bytes()).hexdigest()!='4a85e87eb82756bc0fbb260288b9b5ff557dfe36f47e11e7801b39a44912ed25':
    raise SystemExit('STOP_FROZEN_FENCE_DRY_SHA')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('controller-started.json','controller-result.json','fence-started.json','fence-result.json','sandbox')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
fd=os.open(notes/'controller-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump({'started':True},out)
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(model),'batch'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=False)
    data=json.loads(proc.stdout)
    valid=(isinstance(data,dict) and data.get('scope')=='COOPERATIVE_SYNTHETIC_WRITERS_USER_SANDBOX'
           and data.get('runtime_recovery_implemented') is False
           and data.get('runtime_writer_fence_installed') is False
           and data.get('active_faults_authorized') is False
           and data.get('network_requests')==0 and data.get('live_gateway_operations')==0
           and data.get('total')==19 and len(data.get('cases',[]))==19
           and data.get('real_process_cases')==3 and data.get('virtual_lease_boundaries') is True)
    if not valid:
        raise ValueError('shape')
    good=(proc.returncode==0 and data.get('marker')=='WRITER_FENCE_DRY_RECORDED'
          and data.get('passed')==19 and all(r.get('passed') is True for r in data['cases'])
          and data.get('real_process_cases_passed')==3 and data.get('children_started')==4)
    result={'command_rc':proc.returncode,'data':data,'shape_valid':True,'all_cases_passed':good}
except subprocess.TimeoutExpired:
    result={'command_rc':124,'runner_marker':'FENCE_DRY_RUN_TIMEOUT','all_cases_passed':False}
except Exception:
    result={'command_rc':None,'runner_marker':'FENCE_DRY_RUN_OR_READOUT_FAILED','all_cases_passed':False}
fd=os.open(notes/'controller-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump(result,out)
    out.write('\n')
print(json.dumps(result))
raise SystemExit(0 if result['all_cases_passed'] else 3)
PY
```

Успех: rc0, command_rc0, shape_valid=true, all_cases_passed=true,
marker=WRITER_FENCE_DRY_RECORDED, passed=total=19, все case.passed=true.
Также ОБЯЗАТЕЛЬНО все три runtime/fence/active flags=false, real_process_cases_passed=3,
children_started=4 и virtual_lease_boundaries=true. real_process_cases=3 — число определённых
процессных cases, успешность каждого подтверждается отдельно.
Если любой из runtime/fence/active flags стал true — scope неверен; это не готовность recovery.

Rc3/failed case/timeout/ошибка формата не разрешают retry или починку кода на шлюзе.
Сценарии уже выполняются независимо внутри одного batch; сохранить все полученные
результаты и перейти к S3.2/S4/отчёту. FENCE_DRY_RUN_TIMEOUT завершает только собственный
дочерний Python-модели, не службы/ядра. Критический material сети модель не трогала.
После обрыва — S3.2, не S3.1. Exclusive controller-started/fence-started препятствуют повтору.

### S3.2. Прочитать сохранённый итог либо безопасный checkpoint

```bash
python3 -I -B - <<'PY'
import json,os
from pathlib import Path
notes=Path.home()/'xgw-w3z'
for name in ('controller-result.json','fence-result.json','fence-progress.json'):
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

Один dispatcher: controller-result содержит rc команды и helperdata; fence-result —
окончательный helper итог, если controller его не сохранил; fence-progress — checkpoint
с final=false, не законченный batch. При неуспешном controller читается следующий
доступный итог/checkpoint в том же блоке. Не переносить checkpoint в финальный PASS.
Нет файлов → INTERRUPTED_UNKNOWN. Read rc0 не означает19/19. S3.1 не повторять.
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
В W эти подробные context flags не собирались: не переносить их из V как новый after.

### S4.3. Интерпретировать все19 сценариев

Ожидаются WRITER_FENCE_DRY_RECORDED/passed=total=19 и19 строк case.passed=true.
Case failure → WRITER_FENCE_DRY_PARTIAL/rc3 с fixed reason/error_class; остальные cases
уже исполнены. Не менять код на шлюзе и не повторять batch радиPASS.

| Группа | Cases |
|---|---|
| Commit/generation | WRITER_COMMIT, STALE_WRITER |
| Exclusive owner/expiry | WRITER_BLOCKED_DURING_LEASE, SECOND_OWNER_BLOCKED, EXPIRY_NEVER_UNFENCES_WRITER_OR_STARTS_JOB |
| Token/epoch/job | FOREIGN_TOKEN, LATE_JOB_AFTER_RETIRE, REACQUIRE_INVALIDATES_OLD_EPOCH, NO_DUPLICATE_JOB_OR_UNUSED_AFTER_DISPATCH |
| Retirement | UNVERIFIED_RECOVERY_KEEPS_FENCE, SYNTHETIC_VERIFIED_RETIRE_THEN_WRITER |
| Invalid inputs/record | INVALID_DURATION, BOOLEAN_CLOCK_REJECTED, WRITABLE_STATE_REJECTED, LOCK_INODE_REPLACEMENT_REJECTED, CLOCK_BEFORE_LEASE_REJECTED |
| Три real-process cases | TWO_REAL_PROCESSES_ONE_COMMIT, OWN_CHILD_EXIT_RELEASES_OS_LOCK, LEASE_PERSISTS_AFTER_OWNER_PROCESS_EXIT |

Последние три — реальные обычные children/локальные lock calls в sandbox. Первый из них
даёт details:committed1/stale1/busy0/fenced0/other0/child_rc[0,0]. Неверный исход сохраняет
эти фиксированные counts/codes, не raw stdout. Одна ветвь завершает только собственного
holder, не имитирует потерю VPN/службы. Завершение fd-holder и сохранность логического
lease после выхода owner — разные свойства, не реальная автономность recovery.

Token/generation/expiry cases имеют synthetic clock inputs, virtual_lease_boundaries=true.
RESTORED_ON внутри test record — simulated verification, не verdict шлюза. Успешные19/19
не означают установленный fence, отсутствие всех product writers/ABBA или гарантированный
возврат рабочего on. SnapshotY остаётся PLANNED_NOT_ARMED, его данные не читаются.

Status/pool bookends — единственные новые наблюдения gateway. Не переносить Yunits/
kernel/RPDB/config after как измерения Z. Подробная topology/LAN/UDP/IPv6/DNS/E4 проверка
в Z NOT_RUN. Идентичность child/process test не аттестует xgw daemon или model channel.

## 7. Один отчёт, privacy review и следующий scope

Заполнить TEMPLATE редактором в `$HOME/xgw-w3z/report.md`. Указать actualHEAD/tree/runtime
diff/sourceSHA/freeze, NNP/sudo/owneractions, исходный/конечныйmode/pool/version/связь,
controller commandrc и helpermarker отдельно,19casebools/details/ошибки/partial readout.
Filetype controller-result/fence-result/checkpoint явно различать; unknown rc не0.
Если helper закончился, а controller нет — взять фактический helper result, commandrcUNKNOWN.
При checkpoint-only сохранить completed/cases, остальные NOT_RUN; финальныйmarkerUNKNOWN.
Не начинать новый batch/новый каталог после timeout/обрыва. Сеть не восстанавливать.

Сохранить false runtime gates и явно написать: product fence/driver не установлен,
Y root snapshot не использован, lease time boundaries synthetic, realprocesscases3.
Следующий этап — полный product call-site/lockorder/rollback/drainage/bootstrap дизайн,
не установка test Store в реальный XGW. Новое обнаружение аудита: host FreePool backend
напрямую меняет fp_peers в ip xgw, его нельзя пропустить из admission. Usage/agent имеют
другие таблицы/namespace scopes; не считать любое nft слово writer собственной capturetable.

Принятые исторические Y6/X26/W25 и прежние scoped факты не переписывать. ТолькоThinkCentre,
LANработающая, host неclientproof. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/
allTS открыты; wave4/DAEне начинать. Реальная wave3z NOT_RUN до отчёта.

Перед Git прочитать весь Markdown: никаких rawledger/identities/путейhome/реальныхсекретов/
screenshots/исключений. Только один Markdown, не sandbox/source/result files. Одно итоговое
уведомление после публикации или общего STOP/необходимого действия владельца.

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
notes=Path.home()/'xgw-w3z'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3z — cooperative writer fence в sandbox')
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
