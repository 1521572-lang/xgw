# ТЗ Flash: wave3x — приватный snapshot исходного on и check-only плана

## 1. Принятый W и рабочая схема

Отчёт W e670cebfb49dfe2e42e34ed0196ce289caef4dd2 принят:25/25 сценариев модели,
ON_RECOVERY_MODEL_RECORDED/rc0, gates=false, working HEALTHY/on и связь сохранены.
Модель REC-A не является driver.25 сценариев не повторять. Review W описывает пределы.

Следующий REC-B: собрать приватный кандидат snapshot текущего on и проверить typed
JSON-проект только через nft --check. **Применения транзакции, arm/fault/recovery нет.**
Не запускать действия REC-C–E по наличию snapshot. Writer fence и runtime driver ещё
не реализованы. Продукт не устанавливать, старые helpers не исполнять.

Flash доступен ТОЛЬКО ThinkCentre; отдельного управляемого клиента за роутером нет.
Рабочая LAN XGW→роутер→устройства считается работающей. Host-пробы не LAN/UDP/IPv6/DNS/E4.
Сохранять HEALTHY/on/WAN/LAN/Tailscale/pin/pool/службы/правила. Always_off запрещён.
При входящем обрыве>1мин модель следующей командой не восстановит связь; X не создаёт отказ.

## 2. Весь разрешённый объём одним worker, один итоговый отчёт

| Этап | Что выполняется автоматически |
|---|---|
| X1_negative_fixtures |26 независимых синтетических validation cases: JSON/ownership/scope/counters/metadata/limits/manifest/oneshot/запрещённые команды; только временные synthetic files внутри root-run |
| X2_private_snapshot | Текущие raw config/panel/capture/SB/Xray, cached status; nft JSON только ip xgw и inet xgw_guard; IPv4 rules и собственная route table; шесть unit properties, boot/process/markers; приватные копии и draft |
| X3_nft_check_only | РОВНО один nft -c -j -f - со scoped JSON по stdin; никаких apply/fault; timeout/byte budget; role/rc отдельно при ошибке |
| X4_after_stability | Повтор того же bounded чтения, сравнение фактически прочитанных входов, kernel structure/RPDB/units/boot/markers; manifest только при полной qualification |

Локальная fixture failure или UNAVAILABLE не останавливает другие независимые проверки.
Если before snapshot не получен, зависимые X3/X4 явно UNAVAILABLE/NO_BEFORE, а не PASS.
Не вызывать команду вручную ради выяснения ошибки. Один полный Markdown с26case bools,
каждой фазой/rc/reason, qualification и backlog. Не сообщение разработчику после строки.
Общие STOP identity/baseline/privacy сохраняются до запуска. После старта всегда получить
summary/partial, не менять сеть и не перезапускать worker ради нужного маркера.

## 3. Идентичность, границы и новые разрешённые чтения

Product pin **351fb54e074f4a7b497a8a4244fc74c6088788d7**. ActualHEAD/tree записать.
Freeze только **wave3_on_snapshot.py**, SHA256 **efa8524fe962f6b9207e1ea1659f5c269c0dc6455bea92a0b02aba3bc824c664**.
CLI только start/status/show, _worker вручную запрещён. Root-run /run/xgw-w3x0700/0600,
notes ~/xgw-w3x. Код не импортирует XGW или старые helpers, installed110-module tree
вновь не проверять и не объявлять новым измерением. Продуктовый Git runtime diff пуст.

Обычный detached Python-процесс — сборщик, не guardian/служба. Он создаёт только закрытые
файлы своего run и synthetic fixtures. EXCL started/workerclaimed защищает от повторного
start; partial/progress заменяются атомарно. Private material не читает команда show.

Бюджет каждого child:5с, stdout<8MiB; при превышении cleanup только собственного child,
terminate/wait1с/kill/wait1с, не служб/ядер/сборщика. Стандартный stderr не публикуется.
До10 bounded reads в двух bookends плюс один check. Monitor180с, не продление/restart.
Config input≤2MiB каждый/16MiB суммарно, закрытый snapshot payload≤32MiB.
Nft JSON большой: limit означает неполноту, а не неисправность шлюза.

РАЗРЕШЕНО: Gitfetch/FF/один Markdown; status/pool readonly; чтение фиксированных config/
cached status/proc/markers; systemctl show шести именованных юнитов; nft list двух таблиц;
ip -j rule show и ip -j route show table <проверенныйномер>; один check-only ниже.
Службы не запускаются/останавливаются/перечитываются. MainPID0 допустим только для
активного xgw-net в SubState=exited (oneshot); остальные пять требуют живого PID.

НОВАЯ КОМАНДА ТОЛЬКО ВНУТРИ ПРОВЕРЕННОГО HELPER: `nft -c -j -f -`.
[Официальный nft manual](https://netfilter.org/projects/nftables/manpage.html) описывает
--check как проверку без применения изменений. Не удалять -c, не подменять argv,
не добавлять apply/reset/flush. Snapshot JSON-проект содержит add/delete/add только
своей ip xgw, guard/чужие таблицы запрещены валидатором. Это данные для check, не готовый
live restore. Случай отсутствующей таблицы в живом kernel НЕ тестируется.

ЗАПРЕЩЕНО: nft/ip mutations без -c, flush ruleset, replay/arm/restore/window/watch/guardian,
systemd-run/timer/newservice, G1/install/enable/disable/restart/reload/kill служб, WAN/LAN/
NM/sysctl/Tailscale/pin/pool/profile/rotation/config changes/API writes, activehealth,
curl/GET/--version ядер/SOCKS/DNS/ping/SSH/scans/pcap/netns/speedtests. Нет новой сети клиентов.
Инвентаризация REC-C — документ, не команда менять writers или устанавливать fence.

Приватность: raw config/kernel/status/boot/process/material/draft/manifest/digests входов
остаются root600 в/run. Нельзя cat/less/grep private files, подбирать manual nft-команды,
публиковать их в Git/чат/скриншоты. Только sanitized summary/progress/partial: bool/count/
fixed enum/Git/sourceSHA. Не показывать URI/URL/IP/MAC/UUID/ключи/пароли/SNI/порты/имена/
fp/теги/PID/NIC/DBrows/сыройexception/логи/configdigest/privatehash/содержимое правил.
Public command_role — фиксированная роль, не имя интерфейса/номер таблицы/адрес.

Нет исходного HEALTHY/on → WAIT_OWNER_ON/STOP_READ до старта, модель не включает.
Нет sourceidentity/NNP/sudo → общийSTOP. После старта source/collection failure сохранить
как PARTIAL, продолжить только разрешённый readout/after/report. При обрыве дождаться
возврата и status/show/report, не start/_worker/сеть. Старые run-каталоги не пересоздавать.

## 4. S1: терминал, заметки и канал sudo

### S1.1. Проверить среду

```bash
uname -s
```

Ожидается Linux на ThinkCentre. Это не Windows/PowerShell и не локальная VM разработчика.

#### S1.1b. Shell владельца

```bash
test "$(id -u)" -ne 0 && test -d "$HOME/zcod/xgw/.git" && printf 'OWNER_SHELL_OK\n'
```

Нужен OWNER_SHELL_OK: обычный shell владельца, не root-shell. Все последующие `$HOME`
относятся к владельцу. Если маркера нет — STOP, не угадывать путь/пользователя.

### S1.2. Создать новые заметки и заранее проверить sudo

```bash
python3 -I -B - <<'PY'
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
root=Path.home()/'xgw-w3x'
if root.is_symlink():
    raise SystemExit('STOP_NOTES_SYMLINK')
if root.exists():
    if not root.is_dir() or root.stat().st_uid!=__import__('os').getuid():
        raise SystemExit('STOP_NOTES_OWNER')
    if {p.name for p in root.iterdir()}-{'plan.md'}:
        raise SystemExit('STOP_NOTES_ALREADY_USED')
    root.chmod(0o700)
else:
    root.mkdir(mode=0o700,exist_ok=False)
stamp=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
with (root/'run-start.txt').open('x') as stream:
    stream.write(stamp+'\n')
print('NOTES_CREATED',stamp)
PY
```

Допустим новый каталог или заранее созданный свой каталог только сplan.md. Сохранить plan,
не удалять/пересоздавать. Другие файлы/run-start означают уже начатый опыт — STOP, не новый
каталог радиPASS. Run-start создаётся эксклюзивно. После NOTES_CREATED:

#### S1.2a. Проверить NoNewPrivs именно канала исполнителя

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

Нужны EXECUTOR_NNP_OK/rc0. При1/UNKNOWN — общий STOP ДОsudo/worker. Это свойство
дерева процессов исполнителя, не дефект шлюза и не NNP ядра sing-box(там1 ожидается).
Пароль/sudo-v не исправляют наследуемыйNNP1. Не менять sudoers/prctl/политику приложения,
не пробовать альтернативные способы повышения. Требуется действие владельца: предоставить
обычный терминальный канал с рабочимsudo; при перезапуске ZCode самим владельцем
возобновить с S1.1b→S1.2a→S1.2b, НЕ повторять создание notes/run-start/каталога.
[Свойства флага в документации ядра](https://docs.kernel.org/userspace-api/no_new_privs.html).

#### S1.2b. Проверка sudo

```bash
sudo -n true
```

Код0 означает, что этот инструментальный канал уже может выполнять sudo без запроса пароля.
Если нужен пароль/нет кэша, новых sudo-команд модель не запускает. Владелец в своём настоящем
терминале может выполнить `sudo -v` и ввести пароль непосредственно туда. После его сообщения
повторить ТОЛЬКО read-only проверку `sudo -n true` в том же инструментальном канале.
TTY/timestamp sudo разных терминалов могут различаться: успех владельца не заменяет код0
этой проверки. Если снова отказ — STOP до проверок; отчёт S1=BLOCKED_TOOL_SUDO,
зависимые этапы NOT_RUN. Не менять sudoers, не передавать пароль через stdin/команду/заметки.
Это заранее предусмотренный путь подготовки. Сетевые изменения запрещены.
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3x/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 5. S2: рабочий on и sourceidentity

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Ожидается SOURCE_PREFLIGHT_OK. Сохранить фактические HEAD/tree в заметках. Любая ошибка,
грязный клон, другая ветка или runtime diff — STOP. Не reset/checkout/rebase/force и не
переносить старые файлы поверх нового Git-кода. Загрузка нового ТЗ не устанавливает продукт.

### S2.2. Прочитать режим, не переключать его

```bash
bash -o pipefail -c 'sudo -n xgw status | grep -E "^Состояние|Перехват:|^Xray|^sing-box"'
```

Ожидаются HEALTHY и включённый перехват. Если off — WAIT_OWNER_ON по разделу2;
нет ожидаемых строк/traceback — STOP_READ. Код pipeline не заменяет чтение результата.
Сохранить буквальные строки версий. Не выводить весь статус.

### S2.2b. Сохранить текущий режим пула

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

Это фиксация текущего выбора, не требование переключить пул в off. Режим до/после
должен остаться тем же. При неизвестности — STOP_READ без изменения настроек.

Повтор installed4/110-module tree здесь NOT_RUN: новый collector не импортирует XGW.
Это не утверждение о новой проверке installedruntime. Сохранять предыдущие scoped Vфакты.

## 6. P1: однократная заморозка

### P1.1. Подготовить один файл

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_on_snapshot.py': 'efa8524fe962f6b9207e1ea1659f5c269c0dc6455bea92a0b02aba3bc824c664'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3x')
if root.exists() or root.is_symlink():
    raise SystemExit('STOP_ALREADY_PREPARED')
root.mkdir(mode=0o700,exist_ok=False)
for name,data in payload.items():
    fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data)
    path=root/name
    assert path.stat().st_uid==0 and path.stat().st_mode&0o777==0o600
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected[name]
assert root.stat().st_uid==0 and root.stat().st_mode&0o777==0o700
print('ON_SNAPSHOT_FROZEN',expected)
PY
```

Нужны ON_SNAPSHOT_FROZEN/rc0/один SHA. Ошибка/каталогсуществует→общийSTOP, не чистка/
пересоздание/новоеимя. Старые/run и /opt не меняются.

## 7. O1: один start, автоматический dispatcher, общий show

### O1.1. Запустить один раз

```bash
sudo -n python3 -I -B /run/xgw-w3x/wave3_on_snapshot.py start
```

Нужен ON_SNAPSHOT_STARTED/rc0: запущен worker, НЕ завершён пакет. Он detached от
терминала; stdin/stdout/stderr worker идут в /dev/null, только безопасные JSON в/run.
Launcherror/rc3→стартнеподтверждён, status/show разрешены, startнеповторять.
Сразу перейти к O1.2. Не ждать указания разработчика после вывода стартмаркера.

### O1.2. Автоматический dispatcher наблюдения — один блок

```bash
python3 -I -B - <<'PY'
import json,subprocess,time
began=time.monotonic()
while time.monotonic()-began < 180:
    try:
        p=subprocess.run(['sudo','-n','python3','-I','-B','/run/xgw-w3x/wave3_on_snapshot.py','status'],capture_output=True,text=True,timeout=10,check=False)
    except subprocess.TimeoutExpired:
        print('MONITOR_READ_TIMEOUT_NO_RESTART')
        break
    if p.returncode != 0:
        print('MONITOR_READ_UNAVAILABLE',p.returncode)
        break
    try:
        wrapper=json.loads(p.stdout)
        name,data=wrapper['file'],wrapper['data']
    except (ValueError,KeyError,TypeError):
        print('MONITOR_FORMAT_UNKNOWN_NO_RESTART')
        break
    if name=='summary.json':
        print('BATCH_FINISHED',data.get('marker','UNKNOWN'))
        break
    print('BATCH_PROGRESS',data.get('stage','UNKNOWN'),'samples',data.get('completed_samples','N/A'),flush=True)
    time.sleep(5)
else:
    print('MONITOR_BUDGET_REACHED_NO_RESTART')
PY
```

Ожидаются progress и BATCH_FINISHED после завершения четырёх этапов. ON_SNAPSHOT_PARTIAL тоже завершённый
сбор: продолжить O1.3 и отчёт, не новоеТЗ/не повторstart. Мониторне запускаетworker,
не восстанавливает сеть и не читает rawstderr. MONITOR.../истёкbudget→workerможетпродолжаться;
перейти O1.3, сохранитьpartial/UNKNOWN, не kill/restart/сменарежимов. Sudoотказ не обходить
паролемвкоманде/sudoers. При потересвязи после еёвозврата разрешён только O1.3/O1.4/O1.5.

### O1.3. Прочитать итог или последнее partial

```bash
sudo -n python3 -I -B /run/xgw-w3x/wave3_on_snapshot.py show
```

Show0 означаетпрочитанJSON, неPASS. В wrapper.file обязательно указано, что прочитано:
summary.json — завершённыйитог; partial.json — последнийcheckpoint(не финальныйafter);
progress.json — толькоход. Если summaryнет, не объявлять after/context/выполненныеэтапы
по старым данным. Не переносить beforeвafter. При progress-only/нетдоступа→INTERRUPTED_UNKNOWN/
BLOCKED_READOUT, всё ещё не новоеstart. Сохранитькакойфайлпрочитан и фактическиеrc.
Допустимо повторять status/show для чтения, запрещеноstart/_worker.

### O1.4. Конечный статус

```bash
bash -o pipefail -c 'sudo -n xgw status | grep -E "^Состояние|Перехват:|^Xray|^sing-box"'
```

ОжидаютсяHEALTHY/on/прежниеверсии. Иное записать без переключений. При потересвязи ждатьвозврата.

### O1.5. Конечный режим пула

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

Прежнийрежим, pin/Tailscale/captureне менять. Не требовать off.

## 8. Данные и смысл: snapshot не разрешение реального replay

**ON_SNAPSHOT_PLAN_RECORDED**:26 fixtures прошли, приватный snapshot/draft собран,
check-only rc0, фактически наблюдаемые входы совпали в двух чтениях, manifest записан
и перечитан с digest-проверкой. Plan status **PLANNED_NOT_ARMED**.
**ON_SNAPSHOT_PARTIAL**: сохранить всё полученное; manifest может отсутствовать.
Старые raw files в том же run не становятся готовым планом. Не запускать ещё один run.

ВСЕГДА writer_fence_verified=false, runtime_recovery_implemented=false,
active_faults_authorized=false. Даже manifest/rc0/check0 не меняют эти флаги.
CollectionRECORDED означает ответ фазы, не семантическую полноту. Старт rc0 не завершение;
show rc0 лишь успешное чтение. wrapper.file=summary.json — завершённый итог,
partial.json — checkpoint, progress.json — только ход. Не переносить before в after.

### X8.1.26 validation cases

Отметить каждый fixed case ID. Данные только synthetic, не реальные конфиги/правила.
JSON duplicate/nonfinite, неверная форма/чужой family/table/command, dynamic expires,
counter vs verdict, packets вне counter, reserved route table/TUN, stale/false status,
typed scope/global flush, symlink/permissions/size, manifest digest/missing/unsafe gate/
install scope, запрещённые mutating argv, active-exited oneshot/zeroPID daemon.
26/26 относится только к этим validation cases; это не26 реальных отказов шлюза.

### X8.2. Snapshot

Источники read-only. Config/panel/capture/SB/Xray обычные root-owned файлы, без group/
world write; raw cached status root-owned, updated от -5 до120с, daemon HEALTHY,
capture.mode=on/loaded=true/blocked=false/no inbound_missing/tun=false. Capture enabled=true,
capture-open отсутствует. Cached status не новая активная health-проверка.

TOML нужен только для числовых route_table/mark_proxy и tproxy method. Defaults100/1
соответствуют текущему product pin. Невалидные значения не нормализуются молча;
неподдержанный method/лимит/неизвестный cached status → UNAVAILABLE, не runtimebug.
Managed panel сохраняется opaque и проверяется JSON, но настройки не пересчитываются
productparser. Capture-параметры panel не переопределяет в текущем sourcepin.

Kernel snapshot: только ip xgw и inet xgw_guard. Требуется один owned table и допустимые
object kinds, хотя бы одна tproxy-expression в capture; basic guard postrouting10/
forward5/drop/nohostreject. Это не полная проверка каждого правила/пакета. Unknown kind,
table flags или expires закрывают qualification, не удаляются ради PASS.

Сравнение игнорирует только handles объектов и packets/bytes внутри counter. Иное содержимое
сохраняется, порядок rules/arrays не сортируется: перестановка может дать консервативный
STALE_SNAPSHOT. Counter с пустым содержимым в draft — anonymous counter null.
Нет считывания/reset счётчиков как отдельной мутации. RPDB должен иметь точное нужное
правило priority100/mark/fullmask/table с допустимыми ключами, route table — local default
через lo. Наличие этого правила не доказывает отсутствие всех ранних foreign rules.
Сырые rules/routes остаются private, numeric table не публиковать.

Пять обычных active units требуют PID>0/starttime. xgw-net active/exited/0 — корректный
oneshot, без чтения /proc/0. Сравниваются шесть identities, NRestarts, boot и markers.
Это bookends, не непрерывное наблюдение. Cached status может обновляться: его bytes
не сравниваются как immutableconfig, но обе baseline gates должны пройти.

### X8.3. Один check-only

Успех: collection RECORDED, nft_check_rc=0, changes_applied=false. Это check в присутствии
текущей таблицы. JSON add/delete/add не проверен реальным replay; отсутствие таблицы,
packet/LAN paths и соблюдение45с восстановления NOT_RUN.
Ошибка: collection UNAVAILABLE, reason/error_class, command_role и command_rc если доступны.
При лимите rc может быть null/UNKNOWN (до cleanup child ещё не завершился), не подменять0.
Не выводить raw stderr/план для объяснения, не увеличивать timeout и не повторять check.
Source/phase/role/rc достаточно для единого отчёта; точную причину не придумывать.

### X8.4. After и manifest

Сравнить inputs_unchanged, optional_absence_unchanged и отдельные capture/guard/rules/
routes/units/boot/markers_unchanged, затем all_observed_inputs_stable. Inputs сравнивают
действительно прочитанные bytes config/panel/capture/SB/Xray; optional panel отсутствие
тоже проверяется. Нет before/after → UNAVAILABLE/UNKNOWN, не «не изменилось».
Меняющийся status не считается config drift; новая baseline должна быть HEALTHY/on.

Manifest только при полной qualification, root600, version1/scopeCAPTURE_TABLE_ONLY_IPV4/
statusPLANNED_NOT_ARMED, exact member set/size/SHA проверены повторным чтением material.
Private manifest не выводится. Стабильность в точках не является writer fence и не
исключает промежуточную замену/возврат поколения. Время/автор этих событий не установлены.
Не использовать этот материал с новым live driver автоматически: сначала REC-C/D и review.

## 9. Единый отчёт и последующие атомарные работы

Редактором заполнить TEMPLATE в `$HOME/xgw-w3x/report.md`. Включить actualHEAD/tree/
productdiff/sourceSHA, NNP/sudo/owner actions, старт/monitor/show rc/filetype, четыре
collection,26case bools и counts, команды role/rc и лимиты, manifest flag/plan status,
after flags отдельно, реальные mode/pool/version bookends и связь. Summary и partial
не смешивать. Raw private material/имена интерфейсов/значения/hash не копировать.

При optional UNAVAILABLE выполнить все оставшиеся разрешённые этапы автоматически,
закончить один отчёт. При общем STOP остановить подготовку до старта, не чинить сеть.
Если snapshot drift/лимит/check failure — конкретный дефект или недостающее evidence,
не назначать причину «ТСПУ/сервер умер». Не перекрашивать working LAN из NOT_RUN.

В этом же отчёте перечислить следующий приоритет из REC-C-WRITER-INVENTORY.md:
контракт владения → полный call-site audit → test adapters → решение bootstrap →
реальный независимый driver dry qualification. X не исполняет эти будущие действия.
Ни один gate не считать реализованным из модели25/25, snapshot или nft-c0.
W25/U/V/M/J/L/Npartial/Pblocked/Q/Rnegative/S/T не повторять и не переписывать.

Реальная wave3x **NOT_RUN** до внешнего отчёта. Fullwave3/D1-on/scopedfaults/LANUDP/
IPv6/DNS/E4/performance/allTS открыты; wave4/DAE не начинать. No WAN/LAN/Tailscale/
pin/pool/service/rule changes. Продуктовый fence и runtime recovery NOT_IMPLEMENTED.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 9. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I -B - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3x'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3x-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3x — приватный snapshot исходного on и check-only плана')
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
