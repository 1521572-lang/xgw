# ТЗ Flash: wave3v — единый пакет закрытия локальных пробелов evidence

## 1. Решение по U и границы текущей работы

Отчёт U принят в указанном scope: final summary/COVERAGE_BATCH_RECORDED, 3.442 с,
network_requests=0; рабочие HEALTHY/on, контекст/config/cache/поколения внутри U сохранны.
101 supported record независимого разбора; 66 из 67 default VLESS равны, 0 mismatch, 1 no_unique.
Reference 12/12, граф 141 мост/bad-counts0, 71 текущий узел→saved scan, свойства двух юнитов14/14.
U8 query_ok=false/TimeoutExpired: журнал НЕ прочитан успешно, автор/причина дрейфа неизвестны.
Runtime bug не установлен. Продуктовый патч/переустановка по этим данным не нужны.
Подробный разбор: REVIEW-REAL-MACHINE-0.2.0-wave3u.md.

Прямое подтверждение владельца 03.11: ТОЛЬКО ThinkCentre с XGW, управляемого устройства
за роутером нет. Рабочая схема XGW→роутер→устройства считается работающей; не выдавать
host-пробы за LAN/UDP/IPv6/DNS/E4. Не спрашивать ту же опись. Сохранять HEALTHY/on,
WAN/LAN/Tailscale/pin/pool/службы/правила. Без off/G1/install/новой SSH-описи/guardian.
Входящий обрыв дольше 1 минуты не исправляется следующей командой модели. Этот пакет не создаёт отказ.
При будущем destructive-тесте нужен независимый возврат исходного on; здесь его нет и не создаём.

## 2. Весь пакет одним запуском, без остановок после optional mismatch

| Этап | Новое evidence, без повтора принятых опытов |
|---|---|
| V1_U_identity | Проверить root U helper SHA/final summary/private baseline; current SB/Xray vs U, только bool |
| V2_contract_gap_classification | Текущий ограниченный cache/manual через U containerwalk; разделить no_unique на missing_identity и ambiguous_contracts; агрегаты конфликтующих/несовпавших 12 полей без значений; сравнение cache bytes с U |
| V3_generation_object_categories | Доступные last-good/pending vs current: изменены VLESS/GROUP/SERVICE/OTHER; категории identity/TLS/transport/mux/detour/groupmembers/other; отличить смену группы от параметров сервера |
| V4_bounded_writer_journal | ОДИН общий journalctl двух служб, окно2ч/tail1001/анализ1000,≤10с ожидания/≤1MiB raw в памяти; только фиксированные word counts; никаких raw logs |

V2 не расширяет список протоколов: всё то же ограниченное TCP/raw VLESS подмножество.
Не сравнивать все пары приблизительно и не выбирать best match при ambiguity. Источники
могли обновиться: исходный U 66/67 остаётся историческим фактом, V — новый snapshot.
Если SB/cache не равны U, нельзя утверждать, что найден именно прежний единственный gap.
Даже оба равны — не доказательство исторических endpoint R/N, свежести источника или manual lineage.
Принятые M/L/J/SB2, T7, граф/units/scanJOIN из U здесь не повторяются.

Все четыре этапа выполняет один detached worker. Локальный UNAVAILABLE/query_ok=false/отсутствующий
peer/source/mismatch → записать и автоматически продолжить остальные безопасные чтения.
Не отправлять разработчику микровопрос после этапа. Общие STOP baseline/identity/privacy
сохраняются. Один полный Markdown, в нём все этапы/неполнота/приоритеты следующих работ.
При втором неуспехе журнала НЕ увеличивать ещё раз окно/бюджет в этом или новом имени run:
зафиксировать предел, закрыть этот пакет как частичный по evidence, без цикла повторных ТЗ.

## 3. Идентичность и разрешённые эффекты

Product pin **351fb54e074f4a7b497a8a4244fc74c6088788d7**. Записать actual HEAD/tree.
Runtime/packaging/config и исходники всех старых helper не менять/не устанавливать.
Отчёт U в commit f5a5928078a418d2db5494185acc84cb5657717b; exact SHA отчёта проверен разработчиком в review.
Восемь замораживаемых файлов:
- wave3_evidence_closure.py: SHA256 `be906a5278ce677f7f053ee0f272b2580b8b2f8f2e2287aa2bebd7307f3852f8`;
- wave3_coverage_batch.py: SHA256 `f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48`;
- wave3_extended_batch.py: SHA256 `9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb`;
- wave3_reality_contract.py: SHA256 `3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c`;
- wave3_single_bridge.py: SHA256 `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Единственный CLI — **wave3_evidence_closure.py start/status/show**; `_worker` вручную
запрещён. Семь старых — только библиотеки: старые worker/CLI/request/journal не запускать.
U source из /run/xgw-w3u сверяется с указанным SHA; старый run не переисполнять/не пересоздавать.
Новый worker создаёт только /run/xgw-w3v root700/600 (started/worker-claimed/progress/partial/
summary), заметки — ~/xgw-w3v. Private baseline U не cat/не Git. Не создаётся подмена истории.
Все Python с флагами -I -B, без pyc. Start EXCL и worker-claimed EXCL блокируют повтор; обход новым
именем/чисткой запрещён. Не применять pending/last-good и не менять кэш.

Разрешены Git fetch/FF/публикация одного Markdown; status/pool только чтение; чтение
локальных config/proc/sys/nft/systemctl и cache/manual/peer; ОДИН ограниченный journalctl.
Новых сетевых запросов 0. Запрещены curl/GET/--version ядер/SOCKS/DNS/ping/SSH/scans/speedtest/
pcap/netns/API writes; смена узла/профиля/pin/pool/capture/VPN/Tailscale/WAN/LAN/NM/sysctl/
rules; install/apply/enable/disable/restart/reload служб, изменение loglevel, fault/permission-опыты.
Никаких recovery timer/always_off. Собственный detached Python — не служба/guardian.
При достижении бюджета журнала helper завершает ТОЛЬКО созданный им дочерний journalctl
(terminate, при необходимости kill этого дочернего процесса), не worker/службу/ядро/VPN.
Это освобождение ограниченного чтения, не восстановление сети. Нельзя вручную применять
kill/pkill или управляющие команды systemctl к worker, службам и ядрам.

Нет исходного on/root-контекста/identity/config → общий STOP, никакой автоустановки/on/off.
Off→WAIT_OWNER_ON. При потере связи дождаться возврата, затем status/show/отчёт; не новый start.
Monitor error/timeout не разрешает restart/kill worker или изменение сети. Сбор только читает.

Privacy: только bool/count/fixed enum/source SHA/Git. Запрещены raw JSON/config/log/cache,
URI/URL/IP/MAC/UUID/ключи/пароли/SNI/порты/имена/fp/теги/PID/NIC/DB rows/сырой exception/
private plan/хеши значений/config digest/screenshots в чате/Git. Ошибки — fixed code/class.
Никаких cat/ручного grep raw logs для уточнения. В V нет несанацированных файлов readout.
Одна команда/целый блок на шаг; фиксировать фактические rc и маркеры, unknown не заменять 0.

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
root=Path.home()/'xgw-w3v'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3v/notes.md`.

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
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются HEALTHY и включённый перехват. Если off — WAIT_OWNER_ON по разделу2;
нет ожидаемых строк/traceback — STOP_READ. Код pipeline не заменяет чтение результата.
Сохранить буквальные строки версий. Не выводить весь статус.

### S2.2b. Сохранить текущий режим пула

```bash
sudo -n xgw pool | head -1
```

Это фиксация текущего выбора, не требование переключить пул в off. Режим до/после
должен остаться тем же. При неизвестности — STOP_READ без изменения настроек.

### S2.3. Проверить реально установленный код

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
repo=Path(sys.argv[1])
ok=True
for rel in ('install.py','net/sysctl.py','diag.py','net/nft.py'):
    try:
        wanted=(repo/'src/xgw'/rel).read_bytes()
        actual=(Path('/opt/xgw/lib/xgw')/rel).read_bytes()
        equal=hashlib.sha256(wanted).digest()==hashlib.sha256(actual).digest()
    except OSError:
        equal=False
    print(rel,'installed_equals_pinned_source=',equal)
    ok=ok and equal
print('INSTALLED_SOURCE_OK' if ok else 'STOP_INSTALLED_SOURCE_MISMATCH')
raise SystemExit(0 if ok else 3)
PY
```

Нужны четыре True и INSTALLED_SOURCE_OK. Иначе STOP; не копировать файлы/не запускать installer.

### S2.4. Проверить установленное Python-дерево для библиотек чтения

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
wanted=Path(sys.argv[1])/'src/xgw'
actual=Path('/opt/xgw/lib/xgw')
left={p.relative_to(wanted).as_posix():hashlib.sha256(p.read_bytes()).digest() for p in wanted.rglob('*.py')}
right={p.relative_to(actual).as_posix():hashlib.sha256(p.read_bytes()).digest() for p in actual.rglob('*.py')}
same=bool(left) and left==right
print('installed_python_tree_equal=',same,'source_module_count=',len(left),'installed_module_count=',len(right))
print('INSTALLED_PARSER_TREE_OK' if same else 'STOP_INSTALLED_PARSER_TREE_MISMATCH')
raise SystemExit(0 if same else 3)
PY
```

Нужны True/INSTALLED_PARSER_TREE_OK/rc0. Mismatch→STOP, не копировать/не чинить установку.
Это только байтовое чтение .py; не импорт/запуск широких тестов/установка. Сохранитьcounts.

## 6. P1: однократная заморозка

### P1.1. Подготовить восемь файлов

```bash
sudo -n python3 -I -B - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_evidence_closure.py': 'be906a5278ce677f7f053ee0f272b2580b8b2f8f2e2287aa2bebd7307f3852f8', 'wave3_coverage_batch.py': 'f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48', 'wave3_extended_batch.py': '9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb', 'wave3_reality_contract.py': '3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c', 'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3v')
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
print('EVIDENCE_CLOSURE_FROZEN',expected)
PY
```

Нужны EVIDENCE_CLOSURE_FROZEN/rc0/8SHA. Ошибка/каталогсуществует→общийSTOP, не чистка/
пересоздание/новоеимя. Старые/run и /opt не меняются.

## 7. O1: один start, автоматический dispatcher, общий show

### O1.1. Запустить один раз

```bash
sudo -n python3 -I -B /run/xgw-w3v/wave3_evidence_closure.py start
```

Нужен EVIDENCE_CLOSURE_STARTED/rc0: запущен worker, НЕ завершён пакет. Он detached от
терминала; stdin/stdout/stderr worker идут в /dev/null, только безопасные JSON в/run.
Launcherror/rc3→стартнеподтверждён, status/show разрешены, startнеповторять.
Сразу перейти к O1.2. Не ждать указания разработчика после вывода стартмаркера.

### O1.2. Автоматический dispatcher наблюдения — один блок

```bash
python3 -I -B - <<'PY'
import json,subprocess,time
began=time.monotonic()
while time.monotonic()-began < 120:
    try:
        p=subprocess.run(['sudo','-n','python3','-I','-B','/run/xgw-w3v/wave3_evidence_closure.py','status'],capture_output=True,text=True,timeout=10,check=False)
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

Ожидаются progress и BATCH_FINISHED после завершения четырёх этапов. EVIDENCE_CLOSURE_PARTIAL тоже завершённый
сбор: продолжить O1.3 и отчёт, не новоеТЗ/не повторstart. Мониторне запускаетworker,
не восстанавливает сеть и не читает rawstderr. MONITOR.../истёкbudget→workerможетпродолжаться;
перейти O1.3, сохранитьpartial/UNKNOWN, не kill/restart/сменарежимов. Sudoотказ не обходить
паролемвкоманде/sudoers. При потересвязи после еёвозврата разрешён только O1.3/O1.4/O1.5.

### O1.3. Прочитать итог или последнее partial

```bash
sudo -n python3 -I -B /run/xgw-w3v/wave3_evidence_closure.py show
```

Show0 означаетпрочитанJSON, неPASS. В wrapper.file обязательно указано, что прочитано:
summary.json — завершённыйитог; partial.json — последнийcheckpoint(не финальныйafter);
progress.json — толькоход. Если summaryнет, не объявлять after/context/выполненныеэтапы
по старым данным. Не переносить beforeвafter. При progress-only/нетдоступа→INTERRUPTED_UNKNOWN/
BLOCKED_READOUT, всё ещё не новоеstart. Сохранитькакойфайлпрочитан и фактическиеrc.
Допустимо повторять status/show для чтения, запрещеноstart/_worker.

### O1.4. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

ОжидаютсяHEALTHY/on/прежниеверсии. Иное записать без переключений. При потересвязи ждатьвозврата.

### O1.5. Конечный режим пула

```bash
sudo -n xgw pool | head -1
```

Прежнийрежим, pin/Tailscale/captureне менять. Не требовать off.

## 8. Трактовка: результат сборщика, данные и смысл

**EVIDENCE_CLOSURE_RECORDED** означает: все четыре collection=RECORDED и наблюдаемый
контекст, конфигурации, кэш и прочитанные поколения сохранились. Это не semantic PASS.
Внутри возможны query_ok=false, отсутствие peer, mismatch или неподдержанные записи.
**EVIDENCE_CLOSURE_PARTIAL** сохраняет полученный материал вместе с UNAVAILABLE,
global_stop и after_stop. Ради другого маркера пакет не перезапускать.

Summary содержит финальный after; partial — последний checkpoint; progress — только ход.
Не переносить before в after. Непрочитанный baseline не означает «изменился». Пустой watched
не доказывает сохранность: читать cache_inputs_read/generation_inputs_read и available
каждого входа. Сохранять отдельно результат команды, сборщика и смысл проверки.

### V8.1. Связь с U

Отсутствующий или невалидный старый U даёт локальный UNAVAILABLE. Независимые фазы далее
используют свою текущую baseline. Current SB/Xray matches_U=false означает различие bytes;
время, автор и причина из этого не следуют. Не назначать «ночную регенерацию» или действие
владельца. Одинаковая дата HEALTHY не доказывает непрерывность работы ночью. Изменение
между U и V само по себе не является нарушением сохранности внутри V.

### V8.2. Классификация оставшегося пробела

Проверить равенство счётчиков:
`default_vless = equal + mismatched + missing_identity + ambiguous_contracts`.

- **missing_identity:** среди supported records нет точной тройки server/port/uuid.
  Возможны неподдержанный формат, неполный кэш или другая baseline. Это не установленный
  дефект парсера, удалённый сервер или воздействие ТСПУ.
- **ambiguous_contracts:** одна тройка server/port/uuid имеет несколько разных контрактов.
  ambiguous_field_counts показывает только число случаев расхождения по каждому полю,
  без значений. Не выбирать «правильный» или наиболее похожий контракт.
- **mismatched:** при единственном distinct-контракте хотя бы одно из 12 полей отличается.
  mismatch_field_counts показывает категории. Не применять автоматическое исправление.
- Несколько одинаковых контрактов не создают ambiguity. Ambiguity не считать mismatch.

Равенство 12 полей не покрывает всю семантику DNS/bind/extras/socket options и health.
Читать source coverage целиком: до6 уровней, 20 000 visited и 5 000 leaves на body;
до32 источников, 2MiB на body, 8MiB всего, manual до2MiB; все limits/reasons/missing.
Native SB использует общий extractor полей, поэтому эта часть не полностью независима.
Absent fingerprint=chrome — конвенция, а не явно присутствующее поле источника.

Same_cache_digests_as_U относится только к реально прочитанным body. Это не связь manual
или ответ удалённого сервера. При изменившихся SB/cache нельзя утверждать, что классифицирован
именно прежний единственный gap U. Даже совпадение обоих не доказывает endpoint identity
со времён R/N. Старый результат U66/67 не заменять новыми числами.

### V8.3. Категории изменения конфигурации

Для каждого изменённого общего объекта выбирается одна роль по текущему type:
VLESS, GROUP (selector/urltest), SERVICE (direct/block/dns), OTHER.
Сумма current_type_counts должна равняться shared_objects_changed.

Категории changed_field_group_counts_OVERLAP могут пересекаться. Их сумму нельзя выдавать
за число серверов. GROUP и порядок group_members могут измениться без смены VPN endpoint.
Identity объединяет server/port/uuid/password; значения не публиковать. TLS, transport,
multiplex, detour и other_fields считаются отдельно. Отсутствующий ключ и null различаются.
Added/removed направлены от peer к current. Повтор endpoint tag даёт UNAVAILABLE,
а не молчаливый выбор последнего значения.

Current и peer могут быть другими поколениями, чем U44objects. Имя last-good/pending,
метаданные и diff не устанавливают автора и время. Ни один файл не применять и не откатывать.

### V8.4. Ограниченный журнал

Query_ok=true только при EOF и child_rc=0. TIME_BUDGET, BYTE_BUDGET, CHILD_UNAVAILABLE
или ненулевой rc означают неполную/неуспешную выборку. Counts, полученные до обрыва,
относятся только к прочитанному фрагменту. Не называть их итогом полного окна.

Записать window_seconds=7200, byte_limit=1048576, raw_bytes_read, child_rc, stop_reason,
rows_analyzed, row_limit_hit, incomplete_last_line, parse_errors и все literal_counts.
Tail1001 позволяет обнаружить ограничение; анализируются последние1000 полных строк.
Row_limit_hit=false не доказывает полноту существования журналов за пределами выборки.
MESSAGE в виде массива байтов не декодируется как текст: это parse_error. Его нельзя
приравнивать к отсутствующему событию. Ноль при неполных данных не доказательство отсутствия.

Фразы могут пересекаться или быть цитатой. Даже успешный запрос не устанавливает точного
автора записи конфигурации, причину дрейфа или историю T/R вне окна2ч. Не повышать loglevel.
Повторного запроса в V нет. Если журнал снова недоступен, зафиксировать предел и закончить
отчёт; не создавать очередное микрозадание с увеличением бюджета ради тех же counts.

## 9. Один отчёт и приоритетный backlog

Редактором заполнить TEMPLATE в `$HOME/xgw-w3v/report.md`. Заполнить все четыре строки:
collection, фактические данные, semantic decision, ограничения. Отдельно записать:

1. Actual HEAD/tree, product pin, runtime diff, installed4, число модулей и восемь SHA.
2. NNP канала, sudo, действия владельца; start/monitor/show rc и маркеры, wrapper.file.
3. Global/after ошибки, каждый context flag, settings3, SB/Xray, cache/generation readcounts,
   pin/boot/process/шесть PID, исходный и конечный режим, доступность связи.
4. Какие данные не получены и почему. NOT_RUN/UNKNOWN не заменять PASS. After не брать
   из before, private input не публиковать как readout.

При optional missing/mismatch автоматически закончить остальные разрешённые фазы и один
отчёт. При общем STOP не продолжать подготовку/worker; сохранить доступные результаты.
Не ждать задания разработчика после отдельной строки матрицы.

В том же отчёте составить единый backlog:

- Классифицировать текущий gap и указать, доказана ли связь с прежним U. Если inputs
  изменились, исторический gap может остаться неразрешённым — это честный результат.
- Разделить изменение групп и полей endpoint. Writer по словам и diff не назначать.
- Зафиксировать предел журнала; второй bounded-неуспех не порождает новый микропрогон.
- Для конкретного mismatch подготовить atomic fixspec: trigger, evidence, участок кода,
  минимальная проверка, риски. Если продуктового evidence нет, написать «runtime fix
  не обоснован». Продукт в этом прогоне не менять.
- Сохранить принятые M/J/L/Npartial/Pblocked/Q/Rnegative/S/T/U. Отрицательный R остаётся
  фактом своего времени; текущие66/67 или короткий saved OK его не отменяют. Доказанной
  причины «ТСПУ/мёртвый сервер» здесь нет.
- D1-on/scoped faults требуют независимого возврата исходного on и отдельного плана.
  LAN UDP/IPv6/DNS/E4 требуют подходящего наблюдения клиентского пути; Flash доступен
  только ThinkCentre. Работающая LAN не становится неисправной из-за NOT_RUN. Performance
  и все Tailscale paths также открыты. Full wave3 не закрывать, wave4/DAE не начинать.
  Принятые M/L/J/граф/units/scanJOIN/T7 повторять не нужно.

Реальная **wave3v NOT_RUN** до внешнего отчёта. Продуктовый код и сеть не меняются.

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
notes=Path.home()/'xgw-w3v'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3v-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3v — закрытие локальных пробелов evidence')
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
