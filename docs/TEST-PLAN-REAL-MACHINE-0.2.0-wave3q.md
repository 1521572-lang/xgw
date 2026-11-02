# ТЗ Flash: wave3q — read-only разбор STOP в wave3p

## 1. Факт, цель и точная идентичность

Рабочая схема XGW → Wi-Fi-роутер → устройства остаётся baseline. Сохранять HEALTHY/on,
входящий WAN-адаптер/профиль, LAN, Tailscale route=vpn, pool/pin и службы. Существующая
LAN считается работающей. Не выключать ради подготовки, не делать install/G1/новую SSH-опись.

Отчёт P08cdf113dd0a020321199dda86166a9bde6dae5a, testedHEADf9ed31f966d2e2dc337096e450c537702d4cb489:
STOP_SINGLE_PROBE/commandrc3, showrc0, request_count0, collection_error_classValueError,
all_context_checks_oktrue. Запрос/новый journal не выполнялись. Это блокировка теста,
не отрицательный запрос SB-1. N остаётся partial1/2, SB-2 positive принят; O — readonly сбор.
On/settings3/SBconfig/6PID/SBprocess/boot/pin сохранены. Никаких действий владельца в P нет.
Новый HEALTHY timestamp сам по себе не доказывает, что владелец перезапускал VPN между опытами.

Дефект тестового сборщика P: выдавался только класс исключения, без безопасного stage/code.
Не читать/публиковать raw исключение. По коду bridge_config_unchangedtrue означает, что
исходный configdigest был вычислен. Если в rootPsummary нет curl_version, диапазон сбоя —
после чтения configdigest до выдачи версииcurl. В нём проверки mapping/route/marks/targets/
tool/version; это не точная ветвь. Plan создаётся позже версии, не назначать plan причиной.

Цель Q: прочитать существующие тестовые артефакты P/O/N, вывести безопасные коды проверок
и СОВРЕМЕННЫЕ сравнения. Не повторять P, GET, healthscan, journal или curl--version.
Старую точку ValueError задним числом точно не восстановить, если она не была записана.
Current first unmet gate — факт Q, не автоматически точное место исключения P.

Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime не изменён/не устанавливается.
Доставка freepool, фактические testedHEAD/tree записать. Заморозка четырёх файлов:
- wave3_gate_diagnostic.py: SHA256 `e793106474f7a7910886cecd0d11a65f084d123f440473dba8d596f2a36f648b`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Единственный CLI — новый wave3_gate_diagnostic.py. O/N/L — библиотеки, их CLI не запускать.
Старый rootPsource только читается/проверяется по SHA
66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93, не изменяется и не импортируется.

## 2. Разрешённые эффекты, STOP и восстановление

Разрешены только:
- чистый Git fetch/FF и безопасная публикация одного Markdown после просмотра;
- чтения config/proc/sys/nft/systemctl/pin (фиксированный SELECT SQLite mode=ro);
- root700/600 каталоги P/O/N: Psource/summary, Nsource/summary, Osummary/mapping-private;
  наличие и owner/mode/kind Pplan проверяются без чтения его содержимого;
- новые тестовые файлы только /run/xgw-w3q(root700/600) и заметки ~/xgw-w3q;
- поиск пути curl через shutil.which, БЕЗ запуска curl. Версия в Q не перепроверяется.

Запрещены GET/curl/--version/SOCKS/DNS/ping/SSH/сканы/rescan/APIwrites/повторN/O/P/Qrun,
выбор другого узла/цели/pin/unpin/rotation, enable/disable/install/apply/netupdown/kill/
restart/reload, новые listeners/netns, изменение loglevel/служб/правил/конфигов/пула/
WAN/LAN/Tailscale/NM/sysctl. Не запускать старые guardians/permission/fault helpers.
Ни одного нового сетевого запроса или journal-чтения этим ТЗ не предусмотрено.
Шлюз сам продолжает обычную работу; запрет относится к действиям теста.

STOP останавливает проверку, не продукт. Off→WAIT_OWNER_ON, модель его не включает.
Нет oldrootфайлов/не совпал sourceSHA/формат/права→BLOCKED, не создавать историю заново.
Изменённый O→current configdigest не откатывать и mapping не пересоздавать радиPASS.
Повторные каталоги/старый started не удалять и не обходить новым именем.
Recoveryтаймер не нужен: сеть не меняется. Старый always_off запрещён на рабочем on.
При потере связи после возвращения только show/status/отчёт, не run/переключения.
Если после сбоя started есть, summary нет — INTERRUPTED_UNKNOWN; нет повторногоrun.
Reboot может уничтожить /run: не перезагружать ради теста; потерянные файлы не подменять.

Одна команда/целый блок на шаг; дождаться результата, сверить marker/rc. Не вводить код
в sudo prompt. При STOP зависимые шаги NOT_RUN, перейти к разделу7. Если rc не доступен
инструменту, писать UNKNOWN, не выдумывать0. Showrc0 означает чтение, не успешную проверку.

В Git/чат только публичная summary/обезличенный Markdown. Никаких rawconfig/logs/DBrows/
curlJSON/stderr/исключений/URL/IP/MAC/UUID/ключей/паролей/SNI/имён/портов/fingerprints/
тегов/PID/NIC/privateplan/configdigest/targetdigest/скриншотов. SHA исходников и GitHEAD
публичны. Не cat старые summary/mapping/plan: новый helper сам выдаёт только allowlisted поля.

## 3. S1: терминал, заметки, sudo

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
python3 -I - <<'PY'
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
root=Path.home()/'xgw-w3q'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3q/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: исходный on и код

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
sudo -n python3 -I - "$HOME/zcod/xgw" <<'PY'
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

## 5. P1: заморозка только тестового пакета

### P1.1. Подготовить четыре файла один раз

```bash
sudo -n python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_gate_diagnostic.py': 'e793106474f7a7910886cecd0d11a65f084d123f440473dba8d596f2a36f648b', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3q')
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
print('GATE_DIAGNOSTIC_FROZEN',expected)
PY
```

Нужны GATE_DIAGNOSTIC_FROZEN/rc0 и4точныхSHA. Ошибка/существует/частично подготовлено —
STOP, не удалять/переименовать/дописывать. В /opt/systemd ничего не копируется.
Никаких chmod/chown старых P/O/N файлов, никакой замены исторических источников.

## 6. D1: один read-only разбор

### D1.1. Единственный запуск нового helper

```bash
sudo -n python3 -I /run/xgw-w3q/wave3_gate_diagnostic.py run
```

Сначала пишется эксклюзивный started, затем проверки текущего on/процесса/pin. Далее
проверяются rootkind/modes старых каталогов, точный PsourceSHA и rootPsummary: markerSTOP,
request0/ValueError/contexttrue, finiteсогласованное before/afterокно0..120с. Читаются
только фактические JSON, неизвестные поля не дополняются из предположений текстового отчёта.

P_source_derived_stage_range — диапазон исходного кода при известных эмитированных полях;
P_exception_site всегда UNRECORDED. Наличие/неимение файла Pplan теперь — современная
метаинформация, не самостоятельное доказательство его прошлого состояния. Содержимое
Pplan не читается. Нет планфайла — это не новый STOP, отсутствие сохраняется как bool.

Далее NsourceSHA/summaryshape, Osummary+mapping; текущий SBconfig сравнивается с O по
digest БЕЗ вывода digest/key. Отдельные current_static_checks:
O_recorded_marker/O_historical_summary_valid/O_mapping_basis_supported/
mapping_basis_supported/N_summary_digest_matches_O/current_config_digest_matches_O/
SB1_key_shape_valid/current_route_canonical/mapped_SB1_unique/mapped_SB1_vless/
current_routing_marks_absent. Порядок соответствует таблице проверок, не трассе старогоP.
current_first_unmet_gate — первое false/None текущих статических проверок; остальные
bool также читать. Null firstgate означает только этот набор принят, не готовность GET.

Currentprobe HTTPS targetcount/configwarnings/curlpathavailable собираются отдельно;
curl_version_recheckedfalse намеренно. Не запускать tool/GET «чтобы закончить проверки».

Для связи текущего конфига с P выводятся clock_basis_compatible_with_P и mtime/ctime
predateP. Только обаtrue→FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN; иначе UNCONFIRMED.
Это поддержка временами файлов, НЕ сохранённый Pconfigdigest/не доказанный общийboot.
Даже если текущая digestпроверка не прошла, не объявлять её ТОЧНЫМ старым ValueError.
Смена HEALTHYtimestamp не доказывает действия владельца или перезапуск.

Маркеры/коды:
- GATE_DIAGNOSTIC_RECORDED/rc0: закончены статические чтения и сохранён весь контекст.
  Допускает currentgatefalse — он является результатом диагностики, не её поломкой.
  НЕ SB1PASS/исправление/разрешениеPповторить.
- STOP_GATE_DIAGNOSTIC/rc3: stage+stop_code сообщают конкретный непроверенный вход/
  форму/права. Коды MISSING/READ_ERROR/OWNER_MODE_OR_KIND_INVALID/JSON_INVALID/
  JSON_OBJECT_REQUIRED/SHA_MISMATCH/REPORTED_P_SHAPE_MISMATCH/TIME_BASIS_INVALID/
  HISTORICAL_SHAPE_INVALID/WORKING_CONTEXT_UNCONFIRMED — фиксированные без rawданных.
- UNEXPECTED_READ_OR_SCHEMA_ERROR: только stage+класс, дополнительного точного места нет.
  Не превращать его в конкретную причину. AFTER_CONTEXT_READ_ERROR — послеопытные поля
  неполны, before не копировать вместо after. Ошибка может дать частичнуюsummary.
- Нетsummary/процессоборвался→INTERRUPTED_UNKNOWN. Каталог/started не удалять/неповторять.

### D1.2. Прочитать публичную сводку

```bash
sudo -n python3 -I /run/xgw-w3q/wave3_gate_diagnostic.py show
```

Ожидается JSON/rc0. Show повторять можно, run нельзя. Не раскрывать rawprivateфайлы
вместо недостающей сводки. Если summary нет, записать фактический STOP и UNKNOWN.

### D1.3. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидается HEALTHY/on/прежние версии; иное зафиксировать без изменений. Не полныйstatus.

### D1.4. Конечный режим пула

```bash
sudo -n xgw pool | head -1
```

Режим прежний. Не навязывать off/другойpin. Нет связи — ждать её возвращения без команд.

### D1.5. Контекст и итог

Поля before/afteron/guard/caps/NNP/DAC/services, settings3/SBconfig/process/boot/6PID/
pinreadable/unchanged независимы. all_context_checks_ok не заменяет каждое из них.
bridge_config_unchangednull означает, что при раннем STOP baselineconfig не был прочитан,
НЕ то, что конфиг изменился. True — совпал before/afterQ, не автоматически с O/P.
Currentconfigdigest_matchesOfalse может быть нормальным изменением вне P/Q; не откатывать,
не удалятьmapping/узел/не обвинятьтест. Если все currentgatestrue — точка P всё ещё
UNRECORDED: могут отличаться старые входы/tool/version. Нет новогоGET — нет нового health.

## 7. Обезличенный отчёт и решение

Скопировать TEMPLATE редактором в `$HOME/xgw-w3q/report.md`. Заполнить:
- фактические HEAD/tree/codepin/installed4/4SHA/modes, версии, исходный/конечныйon/связь;
- commandrc/collector marker/showrc, первыйSTOP/stage/code, всеUNKNOWN/NOT_RUN;
- historical_P_valid/Prequest0/Pstage_range/exceptionUNRECORDED, поляэмиссии/planpresent;
- ВСЕcurrentstaticbools/firstgate, targetcount/configwarnings/curlpath/versionnotrechecked;
- связьQconfig→P поfiletimes+clockbasis и явное ограничение против digestproof;
- каждый contextflag, отклонения/действиявладельца, отсутствиесетевыхизменений/запросов;
- наблюдение→гипотеза→недостающийфакт. Не делать из современногоgate старуюточнуюпричину.

Не повторять P автоматически при любом результате. Не назначать ТСПУ/падениесервера/
дефектизоляции. На основании Q разработчик выберет следующий атомарный шаг. M/L/J/SB2
приняты и не повторяются. Npartial/fullwave3/D1-on/E4/scopedfaults/LANUDP/IPv6/DNS/allTS
ещё открыты; wave4/DAE не начинать. Рабочая LAN не объявляется неисправной.
Реальная Q пока NOT_RUN. ПередGitadd лично просмотреть Markdown: никаких raw/секретов/
privatehashes/файлов, только разрешённые enums/bools/counts и SHA исходников/Git.
Recovery: не требовалось сетевого возврата, offrollback/таймер не запускались.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 7. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3q'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3q-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3q — read-only разбор STOP до запроса P')
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
