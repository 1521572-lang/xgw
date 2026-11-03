# ТЗ Flash: wave3w —25 сценариев модели возврата on, без живого восстановления

## 1. Цель и точная граница результата

V принят: EVIDENCE_CLOSURE_RECORDED/1.747с, четыре этапа, рабочий HEALTHY/on сохранён.
67 default VLESS=66equal+1missing_identity,0mismatch/ambiguity. В текущей паре поколений
44VLESS различаются только категорией tls. Журнал2ч прочитан, writer/причина неизвестны.
Review V завершает наблюдательную ветвь: кэш/журнал/граф/units/scanJOIN/T7 заново не читать.

Новый этап REC-A проверяет контракт будущего восстановления исходного on. Это чистая
модель с виртуальными часами и синтетическими proof flags. **Реальный driver, writer
fence и восстановление сети не реализованы**. Положительный результат W не разрешает
fault, D1-on, установку, запуск guardian или следующую ступень автоматически.
ADR-RECOVERY-ORIGINAL-ON.md и PR-SPEC-WAVE3-ON-RECOVERY.md описывают оставшиеся этапы.

Доступен ТОЛЬКО ThinkCentre; отдельного клиента за роутером нет. Рабочая раздача через
XGW→роутер→устройства считается работающей. Host-пробы не LAN UDP/IPv6/DNS/E4 evidence.
HEALTHY/on — baseline. Входящий обрыв>1мин модель следующей командой не исправит.
Always_off запрещён. W не создаёт обрыв и не проверяет реальную автономность.

Один пакет: source/preflight →25 сценариев в одном процессе → конечный статус → один
Markdown. Внутренний провал сценария не прерывает остальные25. Если общий baseline,
идентичность или приватность не подтверждены — STOP до запуска/только отчёт о блокировке.
Не отправлять разработчику отдельное сообщение после каждого case.

## 2. Идентичность и эффекты

Product pin **351fb54e074f4a7b497a8a4244fc74c6088788d7**. V report commit
**be1fc1bf8b5bcc9a6e0f9b1b68eeaa8680ad1acf**. Actual tested HEAD/tree записать по S2.1.
Новый файл tests/stand/wave3_on_recovery_model.py, SHA256 **02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe**.
Копия для запуска только ~/xgw-w3w/model.py с теми же bytes. CLI только `simulate`,
Python3 -I -B, без -O. Старые helpers не импортировать/не исполнять/не менять.

Модель импортирует только dataclasses/json/math/sys; не импортирует XGW и не читает
живые config/cache/DB/proc/sys, не вызывает subprocess/socket/systemctl/nft/ip.
Пользовательский controller ТЗ создаёт заметки/result, запускает только эту модель
и выполняет явно указанные read-only status/pool и Git-команды. Это не deployment.

Разрешены: Git fetch/FF/публикация одного Markdown, sudo-проверка и read-only status/pool,
файлы ~/xgw-w3w с обычным владельцем0700/0600. Git-соединения доставки не являются
активными VPN-пробами; model network_requests/live_operations всегда0.

Запрещены: arm/restore/replay/dry-run старого guardian, systemd-run/timer, новая служба,
install/G1/enable/disable/restart/reload/kill служб, nft/ip mutations, WAN/LAN/NM/sysctl,
Tailscale/pin/pool/profile/rotation/config/keys/SNI/fingerprint, API writes/scan/rescan,
curl/GET/--version ядер/DNS/ping/SOCKS/SSH/pcap/netns/speedtests. Не набирать операции
из будущих REC-B–E. Нет root-копий в/run и нет восстановления off.

Privacy: в отчёт только bool/count/fixedenum/Git/source SHA. Не публиковать status целиком,
raw config/log/cache/URI/URL/IP/MAC/UUID/ключи/пароли/SNI/порты/fingerprint/tag/PID/NIC/
DBrows/исключения/privatehash/screenshots. Модель выдаёт только синтетические case IDs.
Никаких реальных значений в fixture вместо синтетики. Пароль владельца в чат не просить.

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
notes=Path.home()/'xgw-w3w'
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
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor be1fc1bf8b5bcc9a6e0f9b1b68eeaa8680ad1acf HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
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

### S2.4. Заморозить только модель в notes владельца

```bash
python3 -I -B - <<'PY'
import hashlib,os,sys
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP_OWNER_REQUIRED')
notes=Path.home()/'xgw-w3w'
if notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_NOTES_METADATA')
raw=(Path.home()/'zcod/xgw/tests/stand/wave3_on_recovery_model.py').read_bytes()
expected='02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe'
if len(raw)>131072 or hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit('STOP_MODEL_SOURCE_SHA')
if (notes/'model.py').exists() or (notes/'model.py').is_symlink():
    raise SystemExit('STOP_ALREADY_FROZEN_USE_S2_4b')
fd=os.open(notes/'model.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:
    out.write(raw)
print('MODEL_FROZEN',expected)
PY
```

Нужен MODEL_FROZEN/rc0 и точный SHA. Уже существующий model.py не перезаписывать:
если он был успешно подготовлен до остановки, выполнить S2.4b и продолжить
S3.1, если model-started.json ещё нет. Непонятный частичный файл → STOP_IDENTITY,
не новый каталог. Копирование не создаёт драйвер/timer, не меняет /opt или/root material.

#### S2.4b. Только при возобновлении после успешной заморозки

```bash
python3 -I -B - <<'PY'
import hashlib,os
from pathlib import Path
notes=Path.home()/'xgw-w3w'
model=notes/'model.py'
ok=(os.geteuid()!=0 and not notes.is_symlink() and notes.exists()
    and notes.stat().st_uid==os.getuid() and notes.stat().st_mode&0o777==0o700
    and model.exists() and not model.is_symlink() and model.stat().st_uid==os.getuid()
    and model.stat().st_mode&0o777==0o600
    and hashlib.sha256(model.read_bytes()).hexdigest()=='02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe')
unused=not any((notes/name).exists() or (notes/name).is_symlink()
               for name in ('model-started.json','model-result.json'))
print('FROZEN_MODEL_RESUME_OK' if ok and unused else 'STOP_RESUME_IDENTITY_OR_ALREADY_STARTED')
raise SystemExit(0 if ok and unused else 3)
PY
```

Только FROZEN_MODEL_RESUME_OK/rc0 разрешает S3.1. Если уже есть started/result — S3.2,
не повтор. Если нет подтверждённой заморозки — STOP_IDENTITY, файл не исправлять.

## 5. S3 — все25 сценариев одним запуском

### S3.1. Однократный запуск и сохранение результата

```bash
python3 -I -B - <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
notes=Path.home()/'xgw-w3w'
model=notes/'model.py'
if os.geteuid()==0 or notes.is_symlink() or notes.stat().st_uid!=os.getuid() or notes.stat().st_mode&0o777!=0o700:
    raise SystemExit('STOP_OWNER_NOTES')
if not model.exists() or model.is_symlink() or model.stat().st_uid!=os.getuid() or model.stat().st_mode&0o777!=0o600 or hashlib.sha256(model.read_bytes()).hexdigest()!='02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe':
    raise SystemExit('STOP_FROZEN_MODEL_SHA')
if any((notes/name).exists() or (notes/name).is_symlink() for name in ('model-started.json','model-result.json')):
    raise SystemExit('STOP_ALREADY_STARTED_READ_S3_2')
fd=os.open(notes/'model-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump({'started':True},out)
try:
    proc=subprocess.run([sys.executable,'-I','-B',str(model),'simulate'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False)
    data=json.loads(proc.stdout)
    valid=(isinstance(data,dict) and data.get('scope')=='SYNTHETIC_STATE_MACHINE_ONLY'
           and data.get('runtime_recovery_implemented') is False
           and data.get('active_faults_authorized') is False
           and data.get('network_requests')==0 and data.get('live_operations')==0
           and data.get('total')==25 and len(data.get('cases',[]))==25)
    if not valid:
        raise ValueError('shape')
    good=(proc.returncode==0 and data.get('marker')=='ON_RECOVERY_MODEL_RECORDED'
          and data.get('passed')==25 and all(r.get('passed') is True for r in data['cases']))
    result={'command_rc':proc.returncode,'data':data,'shape_valid':True,'all_cases_passed':good}
except subprocess.TimeoutExpired:
    result={'command_rc':124,'runner_marker':'MODEL_RUN_TIMEOUT','all_cases_passed':False}
except Exception:
    result={'command_rc':None,'runner_marker':'MODEL_RUN_OR_READOUT_FAILED','all_cases_passed':False}
fd=os.open(notes/'model-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
    json.dump(result,out)
    out.write('\n')
print(json.dumps(result))
raise SystemExit(0 if result['all_cases_passed'] else 3)
PY
```

Успех: rc0, command_rc0, shape_valid=true, all_cases_passed=true,
marker=ON_RECOVERY_MODEL_RECORDED, passed=total=25, все case.passed=true.
Также ОБЯЗАТЕЛЬНО runtime_recovery_implemented=false и active_faults_authorized=false.
Если они true — неверный scope/shape, не готовность реального recovery.

Rc3/failed case/timeout/ошибка формата не разрешают retry или починку кода на шлюзе.
Сценарии уже выполняются независимо внутри одного процесса; сохранить все полученные
результаты и перейти к S3.2/S4/отчёту. MODEL_RUN_TIMEOUT завершает только собственный
дочерний Python-модели, не службы/ядра. Критический material сети модель не трогала.
После обрыва — S3.2, не S3.1. Exclusive model-started препятствует повтору.

### S3.2. Чтение уже сохранённого результата при необходимости

```bash
python3 -I -B - <<'PY'
import json,os
from pathlib import Path
path=Path.home()/'xgw-w3w/model-result.json'
if not path.exists():
    raise SystemExit('STOP_RESULT_UNAVAILABLE_INTERRUPTED_UNKNOWN')
if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o777!=0o600 or path.stat().st_size>65536:
    raise SystemExit('STOP_RESULT_METADATA')
try:
    value=json.loads(path.read_text())
except (OSError,ValueError):
    raise SystemExit('STOP_RESULT_UNREADABLE') from None
print(json.dumps(value))
PY
```

Это только чтение, допускается повторять. Read0 не означает test PASS. Нет файла после
обрыва → INTERRUPTED_UNKNOWN, не создавать результат вручную/не запускать S3.1 снова.
Ошибка запуска шага до result также остаётся ошибкой шага, не all_cases_passed.

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

### S4.3. Единое решение без перехода к сетевым действиям

Прочитать cases: восемь отказов при false предусловиях; отказ defaults; scope D1_INSTALL;
overbudget/NaN/string bool; просроченный timer; старое поколение/unarmeddriver; virtual
controller loss; early job finish; corrupt snapshot; transaction/verify failure;
restore/verify timeout; hard deadline; backwards clock. Итого25.

Это конечные свойства **синтетической модели**, а не измеренное выполнение локального
таймера или сетевого восстановления. Tick(clock) вызывался программой; он не доказывает
автономность без контроллера. Бюджет45с задан в модели, реальное время восстановления
UNKNOWN/NOT_RUN. RESTORED_ON в сценарии не статус живого шлюза.
Никакого автоматического REC-B/C/D/E по результату25/25. Для них нужно готовое изменение
кода и соответствующее ТЗ из единого PR spec. Другие открытые проверки не закрывать.

## 7. Один отчёт и privacy review

Редактором заполнить TEMPLATE в `$HOME/xgw-w3w/report.md`. Указать actualHEAD/tree/SHA,
source runtime diff, NNP/sudo/owner actions, все шаги и rc, command/model/readout отдельно,
25 case bools/counts, model flags false, before/after status и pool/связь.
Неполные данные сохранять как UNKNOWN/NOT_RUN; общий fail не скрывать числом25.
Повтор установки/110modules/VM/netns/journal/cache/network proof в W NOT_RUN.

Отдельно назвать следующий приоритет: REC-B snapshot planning и REC-C writer fence,
затем реальный автономный driver qualification; live recovery ещё не реализован.
Полная wave3/D1-on/faults/performance/all Tailscale/LAN UDP/IPv6/DNS/E4 открыты.
Владельцу доступен только ThinkCentre; работающая LAN считается работающей.
Wave4/DAE не начинать, старые принятые факты не переписывать.

До публикации прочитать весь Markdown: нет live identifiers/raw config/log/cache/секретов/
скриншотов/privatehash; только источник кода и fixed case IDs. Публикуется один Markdown.
Файлы notes/model.py/model-result.json/model-started.json не git add.

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
notes=Path.home()/'xgw-w3w'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3w-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3w — модель возврата исходного on')
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
