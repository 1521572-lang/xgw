# ТЗ Flash: wave3p — один новый запрос через тот же SB-1

## 1. Исходные факты, вопрос и границы

Рабочая схема владельца XGW → Wi-Fi-роутер → устройства считается исходно работающей.
HEALTHY/on сохраняется. WAN-профиль/адаптер, LAN, Tailscale route=vpn, pool и pin не менять.
Задача не требует отключения VPN, переустановки, новой SSH-инвентаризации или внешнего клиента.

Прочитаны N e4f6f2d2f8ae8cf6148a624f5231c4107bd7f225 и O
4fbde2e4469ec2bda92956d3715ab0e5a3f80728.
N: SB-1 две curl97/HTTP0/bytes0; SB-2 rc0/206/32769/.372с, positive принят.
O: READ_DIAGNOSTIC_RECORDED/rc0, рабочий on/settings3/SBconfig/6PID/boot/pin сохранены.
Для SB-1 условно связаны 2 journal-строки категории TLS-auth-handshake; это совпадения
слов, не доказанный сбой handshake. error_priority_rows=0 не означает отсутствия ERROR
в тексте приложения. Scan SB-1 OK/305байт/.77с за1464.083с до N, мог устареть; scan
SB-2 после N не является свидетельством его прошлого состояния. 305байт не равны
проверке передачи32769байт. Безопасные классы attrs одинаковы, значения приватных
параметров/их корректность этим не сравнивались. Точная причина SB-1 неизвестна.

Один проверяемый вопрос: что даст ОДИН НОВЫЙ запрос через тот же сопоставленный SB-1
при неизменном с O SB-config, с сохранённой ДО запроса идентичностью и диагностикой?
Это отдельное измерение текущего состояния, не восстановление старого stderr и не
повтор N ради PASS. N остаётся partial независимо от нового результата. SB-2 не повторять.
Других кандидатов/целей не брать. Никаких health-scan/rescan или исправлений по догадке.

Сопоставление N→O по-прежнему FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN. P проверяет
точный digest текущего SB-config с mapping-private O и сохраняет собственный план,
но НЕ превращает старое временное основание N→O в криптографическое доказательство.
Цель — первая допустимая HTTPS из ТЕКУЩЕГО config.probe; исторический digest URL N
не сохранён, совпадение со старой целью НЕ утверждать. Новый targetdigest только private.

Продуктовый pin351fb54e074f4a7b497a8a4244fc74c6088788d7. Изменён только тестовый пакет,
не runtime. Обновление Git не является установкой. Записать фактические testedHEAD/tree.
Четыре замораживаемых файла и точные SHA256:
- wave3_single_bridge.py: `66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93`;
- wave3_bridge_diagnostic.py: `e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068`;
- wave3_bridge_probe.py: `2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef`;
- wave3_on_observer.py: `0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46`;

Только новый wave3_single_bridge.py запускается как CLI. Три старых — библиотеки;
их run/start/end/permission/safety CLI запрещены. В /opt/systemd ничего не копировать.

## 2. Эффекты, ограничения, STOP и восстановление

Разрешены:
- обычный Git fetch/FF для чистой freepool и публикация только проверенного Markdown;
- чтения config/proc/sys/nft/systemctl и pin фиксированным SQLite SELECT mode=ro;
- чтение старых root600 N summary/helper и O summary/mapping-private;
- новые root700/600 файлы теста ТОЛЬКО /run/xgw-w3p; заметки владельца ~/xgw-w3p;
- ОДИН curl через существующий, подтверждённый как принадлежащий sing-box SOCKS127.0.0.1
  вход SB-1/d. Только HTTPS, SOCKS5 hostname+basic, URL/password через stdin, curl-q,
  proxyenv удалено, noproxy пусто, globoff, без redirect/retry/directfallback/insecure;
- одно чтение journal xgw-singbox за НОВОЕ окно запроса±2с:2001rows/3с, анализ2000.

Curl connect-timeout2/max-time6/childtimeout8с, Range0-32768, bodymin32769/max131072.
MAX относится к bodycurl, не строгой wirequota: заголовки/TLS/буферы дополнительно.
Секунды time_total — длительность запроса, не ping/скорость. Curl>=8.4, не обновлять tool.
Серверная обработка внутри существующего VPN может включать DNS/handshake — это часть
единственного запроса, а не разрешение модели выполнять отдельные DNS/ping/curl команды.

Запрещены enable/disable/restart/reload/install/apply/netupdown/kill, nft/ip/NM/sysctl
мутации, новые listener/namespace/служба, логlevelchanges, pin/unpin/rotation/удалениеузла,
pool/Tailscale/configchanges, ручнойcurl/DNS/ping/SSH/healthscan, fallback наSB2/другойузел,
повторN/O/P run и старый always_off guardian/offrollback. Не трогать входящий адаптер.

STOP значит остановить только тест, сохранить работающий продукт. Не делать off.
Если statusoff — WAIT_OWNER_ON, модель не включает его. Нет sudo/tool/исторических
файлов/правильныхSHA/совпаденияOconfigdigest — BLOCKED, request_count0, не обходить.
Изменённый конфиг нельзя откатывать ради прогона. Отсутствующий mapping не пересоздавать.

Нет разрушающего сетевого действия, поэтому recoveryтаймер не нужен и не запускается.
Запрос сам ограничен8с; он не отключает управление. Связь модели не механизм возврата:
при потере связи не посылать спасательные переключения. После её возвращения только show,
статус и отчёт, НЕ run. При начатом опыте/started.json без summary — INTERRUPTED_UNKNOWN,
не удалять каталог/не создавать новый. /run теряется при reboot: не reboot, не имитировать
исторические данные; если они потеряны, сохранить BLOCKED и обратиться с отчётом.

Никогда не публиковать rawconfig/journal/curlJSON/stderr, URL/IP/MAC/UUID/ключи/пароли/SNI,
порты/имена/fingerprint/теги/PID/NIC/DBrows/privateplan/hash их значений/скриншоты.
Публичны только fixedenum/bool/counts и SHA исходников/testedGit. Закрытый plan содержит
casekey/configdigest/targetdigest/processidentity/boot/serviceidentity/Ohashes, безURL/паролей;
остаётся root600 на шлюзе. Не cat/show privateplan даже для сверки, не переносить в notes.

Один целый блок на шаг, не запускать весь документ как скрипт. После каждой команды
проверить ожидаемый marker/rc. Если код не показан инструментом, записать UNKNOWN,
не выдумывать0. При STOP dependentstepsNOT_RUN, перейти к разделу7 и безопасной публикации.

## 3. S1: подготовка терминала и заметок

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
root=Path.home()/'xgw-w3p'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3p/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: существующий on и исходники

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

## 5. P1: только заморозка тестовых файлов

### P1.1. Однократно подготовить четыре файла

```bash
sudo -n python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_single_bridge.py': '66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93', 'wave3_bridge_diagnostic.py': 'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068', 'wave3_bridge_probe.py': '2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef', 'wave3_on_observer.py': '0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3p')
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
print('SINGLE_PROBE_FROZEN',expected)
PY
```

Нужен SINGLE_PROBE_FROZEN/rc0 и четыре точных SHA. Уже существует/частично подготовлено —
STOP, не удалить/переименовать/дописать и не использовать другой каталог. В /opt ничего
не копировать. Старые /run/xgw-w3n и /run/xgw-w3o остаются как есть, только чтения.

## 6. D1: один новый запрос, без повторов

### D1.1. Единственный запуск

```bash
sudo -n python3 -I /run/xgw-w3p/wave3_single_bridge.py run
```

Сохранить отдельно exitкод команды и поля collector. Сборщик первым записывает started,
проверяет on/процесс/caps/pin, права/форму старыхsummary/mapping, SHA старогоNhelper,
Oconfigdigest→текущийconfigdigest и соответствие ровноSB1vless/d. Новый firstN не вычисляет.
Затем до запроса сохраняет/fsync закрытый plan. Проверяет listenerowner/netns и ещё один
снимок процесса/settings/boot/currentconfig/on. Только после этого один request. После —
owner, journal ограниченного нового окна, полный aftercontext. Сырые строки остаются
в памяти до завершения, не сохраняются. Никакого2гоtarget/SB2/скана при отказе.

request_window сохраняет realtime начала/конца и monotonic длительность. При несовместимой
основе часов journal не запрашивается: query_okfalse/blocked_clock_basistrue; не приписывать
нулевые counts отсутствию ошибок. Результат запроса и неполнота журнала — разные поля.

Маркеры:
- SINGLE_PROBE_RECORDED/rc0: одна попытка закончилась и все контекстные проверки истинны.
  Это НЕ BODY_OK/PASS само по себе; отрицательный curl97 тоже даёт RECORDED при сохранном
  контексте. Читать attempt.body_ok/http/bytes/curlrc отдельно.
- STOP_SINGLE_PROBE/rc3: условие/контекст/сбор не подтверждены. request_count может быть0
  или1. Отсутствие attempt после request_count1 — запрос мог начаться, исход UNKNOWN,
  не повторять. Отрицательный запрос не путать со сбоем сборщика.
- нетsummary/обрыв/внешняяошибка: INTERRUPTED_UNKNOWN; started/plan запрещают повтор.

WORKER_TIMEOUT в attempt означает превышение бюджета дочернего процесса, не доказанный
сетевой timeout сервера. WORKER_OR_METADATA_ERROR/METADATA_UNKNOWN — неполная диагностика,
не подтверждение причины. Эти outcome не являются BODY_OK даже при collectorrc0.

### D1.2. Прочитать только публичную сводку

```bash
sudo -n python3 -I /run/xgw-w3p/wave3_single_bridge.py show
```

Ожидается JSON/rc0. Show повторяем, run не повторяем. Если show сообщил STOP/нетsummary,
не читать private/raw файлы; зафиксировать код/marker и UNKNOWN. Код show0 означает
прочитан файл, не успешный тест. До/после поля и contextflags переносить раздельно.

### D1.3. Конечный статус

```bash
sudo -n xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

HEALTHY/on/прежниеверсии ожидаются; иное зафиксировать, без переключений. При общей
потере связи не запускать команды до её возвращения. Статус — чтение, не recovery.

### D1.4. Конечный текущий выбор пула

```bash
sudo -n xgw pool | head -1
```

Режим прежний. Не настаивать на off, не восстанавливать pin вручную: изменение может
быть независимым событием. Никаких автоматических исправлений по результату этого опыта.

### D1.5. Точная интерпретация

| Поле/факт | Допустимый вывод |
|---|---|
| body_oktrue+ownedbefore/after+all_context_checks_oktrue | Текущий положительный HTTPS через данный worker/bridge; N не переписывается вPASS |
| curl97/http0/bytes0 | Новый отказ SOCKS-handshake; tlsverify0 не доказывает целевой TLS |
| socks5_reply_code1 | SOCKS сообщил общий отказ, не точная upstreamпричина/ТСПУ |
| replycodeNone | Формат не распознан/нет такого текста, не отсутствие SOCKSошибки |
| socks_auth_failure_texttrue | Распознан текст отказа авторизации SOCKS, не доказана ошибочность хранимого пароля |
| related_literal_details.*>0 | Буквальная фраза в журнале с тегом/окном, не гарантированно curlсессия и не корневая причина |
| related_message_levels.error>0 при priorityerrors0 | Приложение пишет ERROR в MESSAGE, transportpriority другой; противоречия нет |
| tls_auth_or_handshake>0 при literal_details0 | Только широкое словоTLS/reality/handshake, НЕ подтверждённый отказhandshake |
| levelsunknown | Формат leadingloglevel не распознан, не INFO/PASS |
| queryfalse/truncated/parseerrors/rows0 | Неполное/пустое наблюдение; нули не отсутствие ошибок |
| settings3/SBconfig/process/boot/6PID/pinflagfalse | Смешанный контекст, STOP, не обвинять запрос автоматически и не откатывать настройки |
| body305илииной<32769 | Не проходит критерий полногоbody, даже HTTP200/scanOK |

Группы литералов: reality_verification_failed, certificate_failure, tls_alert,
handshake_failure, permission_failure, dns_failure, timeout, refused, unreachable,
reset_or_eof. Они могут пересекаться и описывают текст, не источник сбоя. Логуровень
распознаётся только в начале стандартной строки, не по словуERROR в домене/URL.
MappingN→O условный, digestO→P точный; эти основания не смешивать. Длительность неRTT.

[curl: error97](https://curl.se/libcurl/c/libcurl-errors.html),
[curl8.5.0 socks.c: сообщение replycode](https://github.com/curl/curl/blob/curl-8_5_0/lib/socks.c#L924-L944),
[ограничениеbodycurl](https://curl.se/docs/manpage.html#--max-filesize).
Распознавание текста зависит от версии и языкаC; неизвестное остаётсяUNKNOWN.

## 7. Отчёт и дальнейшее решение

Скопировать TEMPLATE редактором в `$HOME/xgw-w3p/report.md`, заполнить реальными данными.
Не выполнять cp из /run/root, не публиковать privateплан. Отдельно записать:
1. GitHEAD/tree/codepin/installed4/4SHA, версии, начальный/конечныйon и связь.
2. Каждый STOP/неполный этап и точные commandrc, collector marker, showrc.
3. Основания oldmapping/digestO→P, planpersisted, request_count, listenerbefore/after.
4. attempt: outcome/curlrc/http/bytes/seconds/TLSverify/encoding/body_ok; errorenum/reply.
5. request_window/clockbasis; Journalcoverage, global/relatedcategories, literalcounts и
   messagelevels раздельно, blocked_clock_basis при наличии.
6. before/afteron/guard/caps/NNP/DAC/services; settings3/SBconfig/process/boot/6PID/
   pinreadablebeforeafter/pinunchanged и all_context_checks_ok каждое отдельно.
7. Отклонения, действия владельца, что NOT_RUN; наблюдение→гипотеза→недостающийфакт.

Не писать «сервер починен/упал», «виноватТСПУ», «изоляцияисключена» без свидетельств.
УспехP показывает только текущую доступность, не причину прошлого отказа. НеуспехP
сохраняет отрицательныйфакт и диагностическиеenum, не разрешает вращатьузлы/менятьruntime.
M6/6/L608с/Jshort-host+loaded/SB2positive приняты и не повторяются. Полнаяwave3/Npartial/
D1-on/E4/scopedfaults/LANUDP/IPv6/DNS/allTailscale ещё открыты, wave4/DAE не запускать.
Это не означает неисправность рабочей LAN. РеальныйP пока NOT_RUN.

Прочитать черновик перед публикацией: только разрешённыеbool/counts/enums, исходникиSHA,
без rawlogs/адресов/портов/fingerprints/личныхданных. При нарушении убрать приватное
редактором ДОgitadd. Не автоматическийregex вместо просмотра. Не вставлять секреты в чат.

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
notes=Path.home()/'xgw-w3p'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3p-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3p — один запрос SB-1 с сохранённой идентичностью')
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
