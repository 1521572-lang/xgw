# ТЗ Flash: wave3n — HTTPS через существующий постоянный sing-box, без смены pin

## 1. Уже принято и новый вопрос

Фактический wave3m09abf5c46101cf69783dce447d759a416bf8403f принят:6/6cases,
положительный контроль своего SB-конфига и5отказов, identity подтверждена внутри child.
State-файл не создан, cleanup не нужен; рабочий HEALTHY/on/настройки/6PID сохранены.
Wave3l608с наблюдения и wave3j короткий host-кейс тоже приняты. Не повторять их,
установку/G1, повторные inventory/permission-probes или отключение VPN.

Нужно проверить полезную совместимость новой изоляции: может ли постоянный capless
sing-box передать HTTPS-тело через уже настроенные узлы. Используются существующие
SOCKS-входы sing-box (базовый профиль d), максимум2узла; новый узел не создаётся,
основной выбранный сервер не переключается. XGW → роутер → устройства остаётся рабочим
baseline. Продукт/службы/правила не устанавливаются и не меняются.

Product/старыеhelpers pin351fb54e074f4a7b497a8a4244fc74c6088788d7. Новый сборщик
tests/stand/wave3_bridge_probe.py SHA256 db9edb6f7dd95549f52e21a9b733e33404bcef1f34189819d35d8f42d78b6390;
прежний reader wave3_on_observer.py SHA256 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 (не изменён).
Доставка Git/freepool, фактические HEAD/tree записать в отчёт. Freeze только helpers в/run.

## 2. Разрешённые эффекты и STOP

Разрешены FF Git, собственные заметки/закрытые файлы теста, чтение config/proc/sys/nft/
systemctl и pin из SQLite mode=ro фиксированным SELECT, без Store/DDL/DML/API управления.
Активный эффект — небольшие HTTPS GET через существующие loopback SOCKS входы постоянного
sing-box к уже настроенным cfg.probe.url/urls. Ни одного запроса напрямую при отказе proxy.
Пароль моста и URL передаются curl через stdin, не argv/переменные shell/публикуемый файл.
Содержимое тела уничтожается, публикуются только обезличенные метаданные.

Предел: максимум2базовых входа, по1запросу к первой подходящей цели; только при её неуспехе
допустима одна другая существующая цель. Максимум4разных пары bridge/target за run;
одна пара никогда не повторяется. Range0-32768, читаемое curl тело не больше131072байт,
Общий срок curl6с, connect2с, внешний child8с. Цель — минимум32769байт (больше32KiB).
Это лимит чтения приложения, не абсолютная гарантия WAN-байт: TLS/заголовки/буферы и
уже отправленные сервером данные расходуют дополнительный трафик. Множители тарифа
подписки не измеряются. Длительность одного GET не равна ping/RTT или тесту скорости.

Для известного и неизвестного Content-Length требуется curl>=8.4.0: с этой версии
max-filesize останавливает и продолжающуюся загрузку. Версия читается на машине;
старую не обновлять ради теста — BLOCKED_TOOL. [Первичная документация curl](https://curl.se/docs/manpage.html#--max-filesize).
Без --compressed, Accept-Encoding:identity; сертификат проверяется, --insecure запрещён.
Не применять curlrc, системные proxy-переменные, redirects, retry, HTTP вместо HTTPS
или IP/URL «на замену» из интернета. Если целей/мостов нет — NOT_RUN, не менять конфиг.

Запрещены enable/disable/install/apply/net updown/restart/reload/kill служб, nft/ip/sysctl/
NM changes/faults/flush/ipruleadd, смена pin/пула/подписки/Tailscale, core API мутации,
новые listeners/временные VPN workers/SSH на роутер и старые guardian/rollback-to-off.
Режим on и входящий WAN сохраняются. Запускаются только краткие curl-клиенты; постоянный
sing-box/Xray не перезапускается. Прерывание по timeout касается собственного child.

Если исходный on отсутствует/неизвестен — WAIT_OWNER_ON/STOP, модель его не переключает.
Ошибка предусловий/чтения контекста, смена конфигурации/процесса/владельца порта — остановить проверку, отчёт без
«ремонта» рабочей сети. Пустой/ошибочный SELECT pin — неизвестность, не разрешение снять pin.
Смена записи pin может быть автоматическим обновлением down/срока; не объявлять виновником
тест без причинности и не возвращать pin по старому отчёту. Тест его не записывает.

Recovery/таймер off здесь не нужен: сетевых мутаций нет. При пропаже связи после её
возвращения только show/отчёт, не повторrun. Incomingoutage>1мин не предполагает следующей
команды модели для восстановления. Старый off-guardian к рабочему baseline неприменим.

Одна команда/блок за шаг, дождаться завершения. Не вставлять код в sudo prompt.
Сырые config/curlJSON/stderr/пароли/URL/PID/UID/NIC/адреса/UUID в Git и чат не выводить.
Только summaries сборщика. Даже при ошибке не печатать input/stdout/stderr curl для диагностики.

## 3. S1: терминал, заметки и sudo

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
root=Path.home()/'xgw-w3n'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3n/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: исходный рабочий on и идентичность

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Ожидается SOURCE_PREFLIGHT_OK. Сохранить фактические HEAD/tree в заметках. Любая ошибка,
грязный клон, другая ветка или runtime diff — STOP. Не reset/checkout/rebase/force и не
переносить старые файлы поверх нового Git-кода. Загрузка нового ТЗ не устанавливает продукт.

### S2.2. Прочитать режим, не переключать его

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются HEALTHY и включённый перехват. Если off — WAIT_OWNER_ON по разделу2;
нет ожидаемых строк/traceback — STOP_READ. Код pipeline не заменяет чтение результата.
Сохранить буквальные строки версий. Не выводить весь статус.

### S2.2b. Сохранить текущий режим пула

```bash
sudo xgw pool | head -1
```

Это фиксация текущего выбора, не требование переключить пул в off. Режим до/после
должен остаться тем же. При неизвестности — STOP_READ без изменения настроек.

### S2.3. Проверить реально установленный код

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
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

## 5. P1: заморозить два тестовых файла

### P1.1. Создать закрытую копию по SHA

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_bridge_probe.py':'db9edb6f7dd95549f52e21a9b733e33404bcef1f34189819d35d8f42d78b6390',
          'wave3_on_observer.py':'0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3n')
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
print('BRIDGE_HELPERS_FROZEN',expected)
PY
```

Нужен BRIDGE_HELPERS_FROZEN/exit0 и два точных SHA. При существующем каталоге/неполной
подготовке STOP: не удалять, не переименовывать, не новый каталог ради PASS.
Ничего не копируется в/opt/systemd. Старый observer импортируется только для чтения;
его CLI start/wait/end и permission/safety helpers в этом тесте не запускать.

## 6. T1: один прогон

### T1.1. Выполнить один раз

```bash
sudo -n python3 -I /run/xgw-w3n/wave3_bridge_probe.py run
```

Ожидается BRIDGE_PROBES_PASS/exit0 для фактически выбранных узлов. Сборщик сначала
проверяет существующий on/процесс/caps/NoNewPrivs, читает curl version и applied SB config.
Routing_mark в постоянном конфиге должен отсутствовать. Входы только socks127.0.0.1,
порт>=1024, профиль d, штатная auth; правило однозначно ведёт в соответствующий proxy/
endpoint, завершается reject. Direct/block/неоднозначный route не принимается.
Выбор детерминированный из существующих входов, без смены выбранного пользователем сервера.

Перед и после запроса LISTEN socket inode сопоставляется именно с fd текущего PID SB,
а не просто с любым сокетом в его netns; netns с observer должен совпасть. Если listener
не подтверждён/конфиг поменялся — запрос не выполняется, оставшееся NOT_RUN.
Нельзя заменить эти проверки одним успешным connect к loopback или ослабить их ради PASS.

Запрос выполняется через явно заданный SOCKS proxy, remote DNS через него; direct fallback
отсутствует, curlrc/proxyenv/globbing/redirect/retry выключены. TLS проверяется системным
CAstore. 200/206, rc0, ssl_verify_result0, identity encoding и32769..131072байт обязательны.
Если сервер игнорирует Range, допускается только ограниченное тело в указанных пределах.
Большой Content-Length/max-filesize error — ограничение цели, не доказательство падения узла.

При неудаче первой cfg-цели разрешена только одна другая cfg-цель в рамках этого же run.
Сохраняются оба результата; первый не затирается поздним успехом. Все попытки имеют
номерtarget, rawURL и имена серверов не выводятся. Не запускать новые круги по серверам,
не тянуть подписку, не исключать/ротировать сервер и не переключать main pin.

### T1.2. Прочитать только обезличенную сводку

```bash
sudo -n python3 -I /run/xgw-w3n/wave3_bridge_probe.py show
```

Show можно повторить для отчёта. Отсутствие summary/STOP_BRIDGE_PROBE/exit3 не PASS.
BRIDGE_PROBES_RECORDED — частичный/отрицательный результат; исходные данные сохранить,
не повторrun. Сбой sudo/нет инструмента/кандидата/цели — BLOCKED/NOT_RUN без установки
и сетевого ремонта. Все настройки/службы сохраняются в текущем состоянии.

### T1.3. Конечный статус

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются прежние HEALTHY/on/версии. Иное — факт в отчёт без enable/disable/restart.

### T1.4. Конечный режим пула

```bash
sudo xgw pool | head -1
```

Должен остаться текущим, не навязанным off. Пользователь продолжает обычную работу.

### T1.5. Матрица вывода

| Поле/результат | Вывод |
|---|---|
| BRIDGE_PROBES_PASS | Все выбранные1или2входа прошли BODY_OK и контекст сохранён; не все возможные протоколы |
| BODY_OK + listener_owned_before/after | HTTPS через существующий порт именно постоянного SB, scoped compatibility |
| Target1failed/target2OK | Записываются обе попытки; первая цель/путь не прошли, окончательная причина неизвестна |
| HTTP/TLS/limit/timeout error | Отрицательный/неполный запрос, не автоматический диагноз ТСПУ или падения сервера |
| No candidates/старыйcurl/нетtarget | BLOCKED/NOT_RUN, не продуктовый FAIL |
| pin_record_readablebefore/afterfalse | Запись pin неизвестна, не «выбор не менялся» |
| pin_record_unchangedfalse при readabletrue | Запись изменилась; возможна служебная правка down/срока, не восстанавливать вручную |
| Settings3/bridge_config/sameboot/sameSBprocess/PID6/oncontext unchanged | Измеренные условия сохранены; не непрерывная трасса всех компонентов |
| Seconds/bytes | Время одного GET/прочитанное тело, не RTT и не пропускная способность |

Прямой SOCKS вход SB проверяет постоянный worker и его ответ клиенту. Это не проверка
всей цепочки TPROXY → Xray → SB на каждом профиле, не UDP/IPv6/LAN/DNS leak и не WAN-packet
E4. Socket ownership/config mapping не заменяют внешнюю packet-трассу. Результат не закрывает
D1-on reinstall/scopedfaults/все Tailscale-пути или всюwave3. Не включать wave4/DAE.

## 7. Отчёт и публикация

Скопировать docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-TEMPLATE.md редактором в
`$HOME/xgw-w3n/report.md`. Включить HEAD/tree/codepin/installed4/2SHA/mode, начальный/конечный
on/версии/pool, curlversion, число доступных/выбранных мостов и целей, каждую попытку,
before/after, все контекстные bool, ограничения/STOP/UNKNOWN. Не публиковать полный
curlJSON, пароль, URL, порты, fingerprints/имена серверов, privateDB record/hash, PID/NIC,
сырые config/status/logs/скриншоты. Readonly pin digest остаётся только в памяти.
Прочитать черновик перед отправкой. Рабочий VPN в конце остаётся включённым.

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
notes=Path.home()/'xgw-w3n'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3n — HTTPS через постоянный sing-box')
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
