# ТЗ Flash: wave3r — один запрос с новой зафиксированной базой

## 1. Решение после Q и границы измерения

Исходная схема XGW → Wi-Fi-роутер → устройства работает; HEALTHY/on сохраняется.
Не менять входящий WAN-адаптер/профиль, LAN, Tailscale route=vpn, pool/pin/службы/правила.
Не выключать VPN ради теста, не переустанавливать продукт/не G1/не новая SSH-инвентаризация.

Отчёт Qe768971594d20ca6ac0b424bc114cadf2c33f179: GATE_DIAGNOSTIC_RECORDED/rc0,
все contextflags true, один staticgatefalse: current_config_digest_matches_O.
Остальные10проверок true; Prequest0/точный P_exception_siteUNRECORDED. RootPsummary
не содержит версииcurl/подтвержденияOmapping/plan; Qplanfileabsentnow. FiletimesbeforeP+
clockcompatible дают FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN, не сохранённый Pdigest.
Фраза отчёта «значит содержимое точно совпало с baselineP» слишком сильная: сохраняем
только временную поддержку. Не устанавливать причину/время изменения/действия владельца.

Решение разработчика: закрыть Q как readonly сбор, P оставить BLOCKED/NOT_RUN(request0).
Не добиваться точного старого exception site повторными чтениями и не откатывать старыйOconfig.
R — ОТДЕЛЬНОЕ новое измерение текущего постоянного входа с новой baseline, а не повторP
под старым названием или доказательство старогоSB1. На старте R digestcurrent фиксируется
и не должен меняться до/после единственного запроса. Внутри R проверки НЕ ослаблены.

Выбор: только текущий uniquevless/d вход по ключу SB1 из сохранённогоOmapping. Не firstnew,
не другой здоровый узел, неSB2, безhealthfilter. Ключ8hex — короткая идентичность; старые
значения endpoint/ключи/TLS не были сохранены. Поэтому historical_endpoint_identity=UNPROVEN,
selection_basis=CURRENT_UNIQUE_VLESS_AT_O_CASE_KEY. Совпадениеключа не доказывает неизменность
всех параметров/отсутствие коллизии. Имя случая R-CURRENT-1, не «доказаннототжеSB1».
Полный текущийconfigdigest/targetdigest/processidentity сохраняются приватно ДО запроса.
Цель — первая допустимая HTTPS ТЕКУЩЕГО config.probe, не гарантированно oldNtarget.

Один вопрос: получит ли этот текущий вход тело≥32769байт при caplessworker и сохранном
контексте? Отрицательный результат +safeerrorenum сохраняются без сменыузла/ретрая.
УспехR не переписывает Npartial1/2/Prequest0/историческуюпричинуSB1. M/L/J/SB2 не повторять.

Productpin351fb54e074f4a7b497a8a4244fc74c6088788d7, runtime не устанавливается/не меняется.
Git/freepool, записать фактические testedHEAD/tree. Заморозка пяти файлов:
- wave3_current_bridge.py: SHA256 `38b40524dad5aa76742100cea46b07853b9c9d06940ffc17da3094384bdd59f4`;
- wave3_single_bridge.py: SHA256 `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: SHA256 `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: SHA256 `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: SHA256 `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Единственный CLI — новый wave3_current_bridge.py. Старые P/O/N/L только библиотеки,
их CLI не вызывать. R использует неизменённые функцииrequest/journal/contextP, не Pmain.
RootQsourceSHA ожидается e793106474f7a7910886cecd0d11a65f084d123f440473dba8d596f2a36f648b,
его источник/summary читаются, CLI не вызывается. Старые /runфайлы не переписывать.

## 2. Разрешённые эффекты, STOP и сохранение работы

Разрешены чистый Gitfetch/FF/публикацияодногоMarkdown, чтения config/proc/sys/nft/systemctl,
pinфиксированнымSELECTSQLite mode=ro, rootQsource/summary и O/Nисторическиеinputs.
Только новые root700/600 файлы в /run/xgw-w3r и заметки владельца ~/xgw-w3r.
Разрешён одинcurl--version(3с) и ОДИН запрос через существующий ownedSOCKS127.0.0.1 вход.
ТолькоHTTPS/SOCKS5hostname+basic/url+authstdin/curl-q/globoff/no_proxyempty/proxyenvremoved/
безdirectfallback/insecure/redirect/retry. Connect2/curl6/child8с, Range0-32768,
minbody32769/maxbody131072; curl>=8.4. Не обновлятьtool. Это bodylimit, неwirequota:
заголовки/TLS/буферы дополнительно; time_total неRTT/скорость. Новая цель не задаётся вручную.
В рамках запроса worker может выполнять DNS/TLS; отдельные DNS/ping/curlкоманды запрещены.
После запроса один journal exactНОВОГОокна±2с/2001rows/3с, анализ2000; raw только в памяти.

Запрещены enable/disable/install/apply/netupdown/kill/restart/reload, nft/ip/NM/sysctl
мутации, новые listeners/netns/loglevel/службы, APIwrites/pin/unpin/rotation/сканы,
сменаузла/цели/пула/Tailscale/WAN/LAN/config/откатOmapping, ручнойcurl/DNS/ping/SSH.
Не повторять N/O/P/Q/Rrun и не пересоздавать старые inputs/новые каталоги радиPASS.
Старый always_off guardian/offrollback и permission/faulthelpers запрещены.

STOP останавливает тест, не продукт. Off→WAIT_OWNER_ON, модель сама не включает.
Нет Qevidence/старыхфайлов/каноническоговхода/sourceSHA/tool→BLOCKED, request_count0.
R не требует старогодигестаO: его отличие — отдельный bool, не повод восстанавливатьO.
Но любое изменение currentbaseline ВНУТРИ R→STOP, не запускать запрос/не повторятьего.

Сетевого разрушительного действия нет, recoverytimer не нужен. Запрос ограничен8с;
он не отключает управление. Incoming outage>1мин нельзя исправлять следующей командой
модели: здесь ни источник сети, ни правила не меняются. При потере связи после её
возвращения только show/status/report. Started/planесть, summaryнет→INTERRUPTED_UNKNOWN,
не runagain/не новыйкаталог. Не reboot: /runvolatile; потерянное не восстанавливатьдогадкой.

Один целый блок на шаг, дождатьсяrc/marker. Не вводить код в sudo prompt. Неизвестныйrc
так и записатьUNKNOWN. При STOP dependentstepsNOT_RUN, перейти к разделу7.
В Git/чат только bools/counts/enums/numericcurlmetadata и исходникиSHA/GitHEAD.
Никаких rawconfig/logs/curlJSON/stderr/DBrows/исключений/URL/IP/MAC/UUID/ключей/паролей/
SNI/портов/имён/fp/тегов/PID/NIC/privateplan/config+targethashes/скриншотов.
Planroot600 безrawURL/пароля; не cat/не копировать вnotes/не публиковать.

## 3. S1: терминал и заметки

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
root=Path.home()/'xgw-w3r'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3r/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: рабочий on и точные исходники

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

## 5. P1: только заморозка тестового пакета

### P1.1. Однократная подготовка пяти файлов

```bash
sudo -n python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_current_bridge.py': '38b40524dad5aa76742100cea46b07853b9c9d06940ffc17da3094384bdd59f4', 'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3r')
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
print('CURRENT_BRIDGE_FROZEN',expected)
PY
```

Нужны CURRENT_BRIDGE_FROZEN/rc0 и5точныхSHA. Существует/неполнаяподготовка/ошибка→STOP,
не удалить/пересоздать/переименовать. В/opt/systemd не копировать; старые/rootinputsнетрогать.

## 6. D1: один новый опыт

### D1.1. Единственный запуск

```bash
sudo -n python3 -I /run/xgw-w3r/wave3_current_bridge.py run
```

Порядок: exclusive started → beforeon/process/pin → QsourceSHA/Qsummaryshape,
подтверждающая именноreportedO→currentdrift → O/Nsource/summary/mappingreference →
новыйcurrentconfigdigest/uniquevlessпоreferencekey/route/marks → configuredfirstHTTPS/
curlversion → fsyncprivateplan ДО запроса → precontext6PID/settings3/SBconfig/boot/pin/
workeridentity/listenerowner → ровно1request → ownerafter/journal новогоокна → aftercontext.
План содержит currentconfig+targetdigests/key/process/boot/6serviceidentity/Qsummaryhash/
Omappinghash/время, не rawendpoint/URL/auth. Plan не является историческим identityproofN.

Каждый STOP хранит stage и safe stop_code. Примеры: Q_EVIDENCE_MISMATCH,
REFERENCE_MAPPING_INVALID/REFERENCE_KEY_INVALID/CURRENT_BRIDGE_NOT_UNIQUE_VLESS/
CURRENT_ROUTING_MARKS_PRESENT/CURRENT_TARGETS_UNAVAILABLE/CURL_MISSING/
CURL_VERSION_UNREADABLE/CURL_VERSION_BELOW_8_4/PRE_REQUEST_CONTEXT_CHANGED.
UNEXPECTED_STAGE_ERROR+класс сохраняют границу, без rawтекста. AFTER_CONTEXT_ERROR
означает неполныйafter, beforeнеподставлять. Не исправлять по догадке и не повторятьrun.
AFTER_CONTEXT_OR_LISTENER_UNCONFIRMED — итоговыйконтекст/owner не подтверждён;
при раннем STOP до чтенияconfigdigest поле bridge_config_unchangednull значит «не измерено»,
а не «конфиг изменился». Все остальныеcontextflags также читать независимо.

CURRENT_BRIDGE_RECORDED/rc0 означает, что однапопытка зарегистрирована и contextchecks
сохранны. НЕ bodyPASS: отрицательныйcurl97 также может датьRECORDED. body_ok/http/bytes/
TLSverify/owner читатьотдельно. STOP_CURRENT_BRIDGE/rc3→частичные данные/request0или1.
request1безattempt→вызовмогначаться, исходUNKNOWN, не retry. Request0→новогоhealthнет.
WORKER_TIMEOUT — childbudget, не доказанныйtimeoutсервера; METADATA_UNKNOWN/
WORKER_OR_METADATA_ERROR — неполнаядиагностика, не причинаSB1 и неBODY_OK.

### D1.2. Прочитать публичную сводку

```bash
sudo -n python3 -I /run/xgw-w3r/wave3_current_bridge.py show
```

JSON/rc0 ожидаются; showповторяем, runнет. Show0 — прочитанфайл, не успешныйbody.
Нетsummary→зафиксироватьSTOP/UNKNOWN, не читатьraw/privateвзамен.

### D1.3. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

HEALTHY/on/версиипрежние ожидаются. Иное записать безпереключений/перезапусков.

### D1.4. Конечный режим пула

```bash
sudo -n xgw pool | head -1
```

Режимпрежний, pinне менять. Потерясвязи→только послевозврата, не recoveryкоманды.

### D1.5. Матрица интерпретации

| Факт | Разрешённый вывод |
|---|---|
| current_config_equals_Ofalse | Различие старойбазы и новой; R разрешён решениемdeveloper, не откатывать |
| selection_basisCURRENT_UNIQUE_VLESS_AT_O_CASE_KEY/historical_identityUNPROVEN | Текущий вход связан короткимключом, старый endpoint неизменным НЕ доказан |
| body_oktrue+ownerboth+all_context_checks_oktrue | Scopedpositive текущего входаR, не ретроспективныйPASSN/SB1 |
| curl97/http0/bytes0 | Новый proxyhandshakeотказ; verify0 не доказываетtargetTLS |
| socks5_reply_code1 | Общий ответотказаSOCKS, не установленнаяupstreamпричина |
| replyNone/messageunknown | Не распознан формат; не отсутствиеошибки |
| relatedliteralcounts/messagelevels | Безопасные признаки новыхлогов, tag+time не exactcurlsession |
| broadTLScounts>0 | СловаTLS/reality/handshake, не доказанныйTLSfailure |
| journalqueryfalse/truncated/parseerrors/rows0 | Неполнота/пустота, не отсутствиеошибок |
| request_windowclockincompatible | Journalне запрошен/queryfalse/blocked_clock_basis; запрос отдельно |
| settings3/config/boot/process/6PID/pinfalse | Contextсмешан, STOP, не восстанавливатьстароенастройками |

Journalкатегории/литеральныеfailureфразы/leadingmessagelevel/transportpriority раздельны.
Приоритетжурнала0errors не запрещает ERRORвMESSAGE, широкие категории пересекаются.
Не назначать ТСПУ/падениесервера/defectизоляции по одному enum. Время запроса неping.
ИзR нельзя получить полнуюTPROXY→Xray→SB/LANUDP/IPv6/DNS/allTS/E4/fault/D1-onPASS.

## 7. Отчёт и следующий шаг

Скопировать TEMPLATE редактором в `$HOME/xgw-w3r/report.md`. Указать:
- testedHEAD/tree/productpin/installed4/5SHA/modes/версии/исходныйконечныйon/связь;
- commandrc/collectormarker/showrc, stage+stopcode/ошибки/UNKNOWN/NOT_RUN;
- selectionbasis/historicalidentityUNPROVEN/currentconfigequalsO/planpersisted/ownerboth;
- request_count, единственныйattempt(outcome/rc/http/bytes/time/TLS/encoding/body_ok/errorenum);
- requestwindow/clockbasis/journalcoverage/global+relatedcategories/literals/messagelevels;
- before/aftercontext, settings3/SBconfig/process/boot/6PID/pinreadable+unchanged каждый;
- отклонения/действиявладельца, сохранённыйon, отсутствиеслужебных/сетевыхмутаций;
- наблюдение→гипотеза→недостающийфакт. Не смешиватьN/O/P/Q/R и не объявлятьстарыйSB1починенным.

Успех/отказ одинаково заканчивают R; нетfallback/ретраев/сканов. Npartial и историческая
причинаSB1 сохраняются как открытыефакты; Pblocked0/Qacceptedreadonly. M/L/J/SB2 не повторять.
Fullwave3/D1-on/E4/scopedfaults/LANUDP/IPv6/DNS/allTS открыты; wave4/DAE не запускать.
Рабочая LAN считаетсяработающей. РеальнаяR покаNOT_RUN. Просмотретьprivacyчерновик ДОgitadd:
толькообезличенныйMarkdown, не privatehashes/raw/секреты. Recoveryнепотребовалось,
offrollback/таймер/режимыпереключения не запускались. Еслисетьизмениласьнезависимо, фактсохранить.

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
notes=Path.home()/'xgw-w3r'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3r-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3r — один запрос с новой базой')
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
