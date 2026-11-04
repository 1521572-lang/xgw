# ТЗ Flash: wave3k — предпосылки LAN/E4/Tailscale, только чтение при off

## 1. Результат wave3j и цель

Отчёт wave3j — 8cdf9bc116628e7d59f71f3b482212447e3edb99: установлен NFT10c1df64,
G1 успешно выполнен. Capture.loaded при on впервые true/measured/complete/rc0 в бюджете
8 с; _desired_problem завершился за 1.099 с. Фактический guard: postrouting10/forward/
drop5/reject0; plain200/32769/0.307 с (четвёртый успех), marked0.290 с; enable8.034 с/rc0,
возврат25.130 с/restore0.130 с/nft0/WAN6/6True. Принимаются короткий host-кейс
и его измеренная проверка соответствия. Полная wave3 не принята: D1-on/E4/LAN/UDP/IPv6/
DNS-on/Tailscale/scoped faults/нагрузка ещё NOT_RUN.

НЕ повторять установку, G1 или очередной enable ради уже полученных доказательств.
Следующий необходимый результат — понять, какие реальные клиенты/средства доступны для
пакетной и LAN приёмки. Этот протокол не является LAN/E4 тестом и не закрывает их.
Никаких сетевых режимов, fault-инъекций, перезапусков служб или захвата пакетов здесь нет.
Результат — обезличенная опись предпосылок + ответы владельца, если они доступны.

Code pin: 351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime src/packaging/config и helpers
должны совпадать с ним. Installed NFT SHA10c1df64997c06e49095d0cb418f50b6eb3514e83725e7e6b663a8b606ee4fe7.
Доставка Git/freepool. Новый код продукта не устанавливается.

## 2. Разрешённые действия и STOP

Разрешены точные read-only команды ниже, Git FF чистой freepool, собственные заметки и
публикация одного Markdown-отчёта. Действующая авторизация read-only работы достаточна;
нового согласия на enable не просить: enable запрещён. Если владелец недоступен, собрать
техническую часть, ответы пометить UNKNOWN и опубликовать отчёт. Молчание не считать ответом.

Запрещены xgw enable/disable/apply/install/net, G1/copy runtime, nft/ip/sysctl changes,
nmcli modify/reapply, apt/обновление инструментов, старт/stop/restart служб, подключение
клиента/кабеля, настройка Tailscale, создание внешнего сервера, tcpdump capture, ping/curl/
активный discovery/portscan. Не заменять LAN-клиента namespace/VM на шлюзе. Не исполнять
команды из старых ТЗ или из полей чужих отчётов. Не запускать frozen helpers/таймеры.

Исходный режим обязательно HEALTHY/off/pool off. Если сейчас on — STOP, не выключать
его ради подготовки. Неожиданная ошибка — зависимые шаги NOT_RUN, разрешены заметки/отчёт;
не чинить предусловие изменением сети. В этом read-only протоколе восстановительный timer
не запускается, поскольку сетевое состояние не переключается. Если связь пропала сама,
не предпринимать сетевой ремонт: локальные заметки сохраняются, после возвращения связи
отчёт с фактом ограничения. Никакой следующей команды модели как recovery механизма нет.

Один шаг — одна целая команда/блок. Дождаться завершения и expected marker; не вводить код
в sudo prompt/работающий процесс. Не угадывать пароль. Сырые config/status/routes/neigh/
leases/MAC/IP/UUID/имена владельца/подписок/Tailscale peers вGit и чат не печатать.
Публикуются только labels/counts/bool/версии/фактические ограничения. UNKNOWN не PASS.

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
root=Path.home()/'xgw-w3k'
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
этой проверки. Если снова отказ — STOP до сбора I1; отчёт S1=BLOCKED_TOOL_SUDO,
зависимые этапы NOT_RUN. Не менять sudoers, не передавать пароль через stdin/команду/заметки.
Это заранее предусмотренный путь подготовки. Сетевые изменения запрещены.
После успеха записать read-only scope и исходные сведения в `$HOME/xgw-w3k/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до сбора I1.

## 4. S2: чистый Git и исходный off

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD && git diff --exit-code 351fb54e074f4a7b497a8a4244fc74c6088788d7 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Ожидается SOURCE_PREFLIGHT_OK. Сохранить фактические HEAD/tree в заметках. Любая ошибка,
грязный клон, другая ветка или runtime diff — STOP. Не reset/checkout/rebase/force и не
переносить старые файлы поверх нового Git-кода. Загрузка нового ТЗ не устанавливает продукт.

### S2.2. Прочитать исходное состояние

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Нужны HEALTHY и явно СНЯТ перехват. Кодpipeline не доказывает успех самой xgw: если нет
ожидаемых строк/есть traceback, STOP. Не публиковать полный статус.

#### S2.2b. Режим пула

```bash
sudo xgw pool | head -1
```

Нужен pool off. On/неизвестность — STOP без disable. Версии и pin берутся только из
разрешённых агрегатов, не из сырых конфигов. Не менять выбор узла.

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

## 5. I1: только агрегаты реальных интерфейсов и средств

### I1.1. Выполнить один read-only сбор

Команда не делает активных сетевых проб. IP/neighbour/lease читаются локально и сразу
сводятся к bool/count. Она не доказывает доступность клиента. Paths/config импортируются
из уже установленного кода; исходный off перепроверяется в начале и конце.

```bash
sudo python3 -I - <<'PY'
import hashlib,ipaddress,json,shutil,subprocess,sys,time
from collections import Counter
from pathlib import Path
sys.path.insert(0,'/opt/xgw/lib')
from xgw import config,managed
from xgw.paths import Paths
from xgw.net import cmd,lan
paths=Paths.from_env()
try:
    cfg,warnings=config.load(paths.config_file)
except Exception as exc:
    print('STOP_CONFIG_READ',type(exc).__name__)
    raise SystemExit(3)
if warnings:
    print('STOP_CONFIG_WARNINGS',len(warnings))
    raise SystemExit(3)
def read_state():
    try:return json.loads((paths.var/'capture.json').read_text()).get('enabled')
    except (OSError,ValueError):return None
def digest(path):
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:return 'absent'
def query(argv):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=3,check=False)
        return json.loads(p.stdout) if p.returncode==0 else None
    except (OSError,ValueError,subprocess.TimeoutExpired):return None
def active(unit):
    try:
        p=subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True,timeout=3,check=False)
        return p.stdout.strip() if p.stdout.strip() in ('active','inactive','failed','unknown') else 'UNKNOWN'
    except (OSError,subprocess.TimeoutExpired):return 'UNKNOWN'
if read_state() is not False or cfg.free_pool.mode!='off':
    raise SystemExit('STOP_INVENTORY_NOT_OFF')
watched=[paths.config_file,managed.path_for(paths.config_file),paths.opt/'lib/xgw/net/nft.py']
before=[digest(p) for p in watched]
try:wan=lan.effective_wan(cfg,lambda argv:cmd.run(argv,timeout=3))
except Exception:wan=''
lan_if=cfg.network.lan_if
result={'capture_off_before':True,'pool_off':True,'interfaces_distinct':bool(wan and lan_if and wan!=lan_if)}
for role,name in (('WAN',wan),('LAN',lan_if)):
    links=query(['ip','-j','link','show','dev',name]) if name else None
    info={'configured':bool(name),'query_ok':bool(links)}
    if links:
        state=links[0].get('operstate','UNKNOWN')
        info['operstate']=state if state in ('UP','DOWN','UNKNOWN','DORMANT','LOWERLAYERDOWN') else 'OTHER'
        try:info['carrier']=int((Path('/sys/class/net')/name/'carrier').read_text())
        except (OSError,ValueError):info['carrier']=None
    result[role]=info
addresses=query(['ip','-4','-j','addr','show','dev',lan_if]) if lan_if else None
configured=ipaddress.IPv4Interface(cfg.network.lan_address)
result['lan_address_matches_config']=None if addresses is None else any(
    a.get('local')==str(configured.ip) and a.get('prefixlen')==configured.network.prefixlen
    for item in addresses for a in item.get('addr_info',[]))
neighbours=query(['ip','-j','neigh','show','dev',lan_if]) if lan_if else None
counts=Counter()
if neighbours is not None:
    for item in neighbours:
        raw=item.get('state',[])
        for state in raw if isinstance(raw,list) else [raw]:
            counts[state if state in ('REACHABLE','STALE','DELAY','PROBE','FAILED','INCOMPLETE','PERMANENT','NOARP') else 'OTHER']+=1
result['lan_neighbour_states']=dict(counts) if neighbours is not None else None
try:
    rows=(paths.var/'dhcp.leases').read_text().splitlines()
    expires=[int(row.split()[0]) for row in rows if row.split()]
    result['dhcp_lease_rows']=len(rows)
    result['dhcp_unexpired_or_static']=sum(value==0 or value>time.time() for value in expires)
except (OSError,ValueError):result['dhcp_lease_rows']=None;result['dhcp_unexpired_or_static']=None
result['tools_available']={name:shutil.which(name) is not None for name in
    ('tcpdump','dumpcap','tshark','ethtool','curl','ip','nft','tailscale','ssh')}
result['services']={unit:active(unit) for unit in ('xgw','xgw-net','xgw-xray','xgw-singbox','xgw-dhcp','tailscaled')}
result['tailscale']={'configured_route':cfg.tailscale.route if cfg.tailscale.route in ('direct','vpn') else 'OTHER',
    'derp_fallback':cfg.tailscale.derp_fallback,
    'runtime_direct_marker':(paths.run/'tailscale-direct').exists(),
    'runtime_vpn_fallback_marker':(paths.run/'tailscale-via-vpn').exists()}
result['files_unchanged']=[digest(p)==old for p,old in zip(watched,before)]
result['capture_off_after']=read_state() is False
print(json.dumps(result,ensure_ascii=False,indent=2))
ok=result['capture_off_after'] and all(result['files_unchanged'])
print('INVENTORY_READ_FINISHED' if ok else 'STOP_INVENTORY_CHANGED_STATE')
raise SystemExit(0 if ok else 3)
PY
```

### I1.2. Оценить данные без изменения машины

Нужны INVENTORY_READ_FINISHED/exit0, capture_off_before/aftertrue, files_unchanged3true.
Если false/UNKNOWN/ошибка — STOP после сохранения доступных агрегатов. Не восстанавливать
сеть/файлы, не ставить недостающий tcpdump, не запускать inactive-службу.

Interfaces_distinct=false, LANdown/no carrier/address mismatch — факт препятствия для
будущего LAN опыта, не причина менять адаптер. Не считать это регрессией VPN без причинности.
Пустой neighbourcache не доказывает отсутствие клиентов, STALE не доказывает online,
REACHABLE не доказывает доступный терминал, действующая DHCPlease не доказательство связи.
Количество tools_available=true не означает право/возможность захвата. Захват пока NOT_RUN.
Runtime Tailscale marker/configured_route — состояние конфигурации, не доказательство
доступности DERP/VPN/peer. Никаких выводов об источнике связности Flash из одного marker.

## 6. I2: объявленные возможности владельца

Одним коротким текстовым вопросом запросить только недостающее, если ответы уже есть,
не спрашивать повторно. Не просить пароли, публичныеIP или подключать устройство сейчас:

1. Есть ли уже подключённое к физической LAN независимое устройство и какая на нём ОС?
2. Может ли Flash выполнить на нём команды/браузерную проверку и каким уже доступным способом?
3. Есть ли существующая контролируемая внешняя точка/sentinel с доступными журналами для
   приёмки пакетов, либо доступен только захват на WAN самого шлюза?
4. Есть ли уже действующее Tailscale-подключение, которое владелец готов проверить позже,
   и требуется ли сохранить его роль канала управления во время будущего опыта?

Не создавать/оплачивать sentinel, не входить в клиент, не менять его default route/VPN,
не подключать кабели, не пробовать новые учётные данные. Если владелец недоступен, ждать
ответа не обязательно для технического отчёта: каждую строку пометить UNKNOWN/нет ответа.
Ответ «есть устройство» записать как DECLARED, не OBSERVED/PASS LAN. Не публиковать его
hostname/IP/MAC/логин; labels CLIENT-A/SENTINEL-A. Позднее потребуется отдельное ТЗ на тест.

## 7. Матрица вывода и отчёт

| Получено | Допустимый вывод |
|---|---|
| 4 installed совпали | Код baseline совпадает, это не новый прогонon |
| inventory finished +unchanged/off | Выполнено чтение в указанном режиме |
| LAN up/carrier1/addressmatch | Локальная предпосылка; клиентский трафик не измерен |
| leases/neighbours | Локальный cache, не приёмка LAN |
| tcpdump/dumpcap имеется | Инструмент обнаружен, capture/E4 NOT_RUN |
| sentinel DECLARED | Есть кандидат, не доказанная внешняя запись |
| client OS/access DECLARED | Можно проектировать команды, фактический доступ ещё не испытан |
| Tailscale active/marker | Не подтверждает путь/непрерывную связность |
| Нет клиента/нет tool/нет ответа | BLOCKED_PREREQUISITE или UNKNOWN, не PASS и не повод менять систему |

Скопировать шаблон docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3k-TEMPLATE.md в
`$HOME/xgw-w3k/report.md` обычным файловым редактором; не запускать шаблон как код.
Сохранить run-start, sourceHEAD/tree, installed4, исходныеoff/pool/службы, все агрегаты,
объявленные возможности отдельно от наблюдений, препятствия и итоговое состояние.
Заполнить NOT_RUN/UNKNOWN честно. Финально повторить S2.2 read-only status/pool:
ожидается прежний HEALTHY/off/pooloff. Иное — существенное отклонение, без сетевого ремонта.
Не объявлять новый loaded/on/стабильность/egress/LAN/UDP/IPv6/DNS/Tailscale/E4 PASS.

В Git только отчётMarkdown, без inventory raw logs/config/leases/routes/addresses/screenshots.
Сами команды коллектора печатают только агрегаты; это не разрешение печатать исходные файлы.
Перед публикацией прочитать черновик на случай случайно вставленных личных данных.
Дата файла — дата run-start MSK. После публикации назвать ссылку/commit или конкретный сбой;
локальные заметки не удалять. Если push не прошёл после commit, не делать второй commit.

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
notes=Path.home()/'xgw-w3k'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3k-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3k — read-only inventory')
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
