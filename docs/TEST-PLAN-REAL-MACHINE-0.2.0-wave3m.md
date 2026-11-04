# ТЗ Flash: wave3m — границы доступа sing-box при рабочем on

## 1. Принятый результат и задача

Фактический отчёт wave3l149ffecefb966b9f33d69b58868d270a3fc93ec9 принят в своём scope:
608.141с между двумя on-снимками,6службactive, PID прежние, NRestarts delta0;
sing-box nonprivileged/caps0×5/NoNewPrivs, DAC ожидаемый, guard postrouting10/forward/
drop5/reject0. Настройки прежние, рабочий VPN сохранён. Журналы вернули0строк;
личное использование устройств за роутером/Tailscale в интервале не наблюдалось.
Это не повод заново доказывать существование рабочей LAN: схема XGW → роутер → устройства
принята как baseline владельца. Не повторять десятиминутное наблюдение или установку.

Следующий узкий вопрос — фактические границы доступа по UID/GID/группам. Нужны один
положительный контроль чтения собственного конфига и пять ожидаемых отказов. Постоянные
процессы не меняются; проверки выполняют отдельные краткоживущие дочерние процессы.
Рабочие VPN/WAN/LAN/Tailscale и службы сохраняются. SSH на роутер не требуется.

Product/старые helpers pin351fb54e074f4a7b497a8a4244fc74c6088788d7. Продукт не обновляется.
Новый helper tests/stand/wave3_permission_probe.py SHA256 3699bd2ab77831ba46bc09e719e521c0bf2d9ed37535d101e65cc320059391d6.
Прежний reader tests/stand/wave3_on_observer.py SHA256 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 (не изменён).
Доставка Git/freepool; записать фактические HEAD/tree. Два helper-файла копируются только
в закрытый /run/xgw-w3m, ничего в /opt/xgw/lib или systemd не заменяется.

## 2. Разрешённые эффекты, STOP и рабочее состояние

Разрешены подготовка собственных заметок, FF Git и точные команды ниже. Операции:
чтение состояния/метаданных; открытие файлов O_RDONLY без чтения содержимого; connect
к локальному UNIX API без отправки RPC/команд; read-only nft list tables; одна попытка
создать собственный пустой .xgw-w3m-empty-UUID.probe в /var/lib/xgw от UID sing-box.
Ожидается отказ на создание. Если оно неожиданно разрешено, worker удаляет только
собственный inode и сообщает ALLOWED — это дефект границы, не PASS. Существующие файлы
не перезаписываются и не удаляются. При неудалённом тестовом файле путь остаётся только
в root600 cleanup-private.json; не чинить права каталога и не чистить /var/lib/xgw.

Запрещены enable/disable/install/apply/net updown/restart/reload/kill служб, nft/ip/sysctl/
NM изменения, ip rule add/del (включая старый тест pref49), flush/fault injection,
смена pin/FreePool/Tailscale/подписки, создание слушателя/активные внешние HTTP/DNS/UDP
пробы/SSH на роутер, установка инструментов и запуск старого guardian/rollback-to-off.
Unix-connect не отправляет API запросов; никаких изменений Xray через API.

Исходный режим HEALTHY/on. Если off/неизвестен — WAIT_OWNER_ON/STOP, модель не включает
и не выключает VPN. Нет нужного файла/сокета/инструмента — NOT_RUN/BLOCKED_TOOL, не отказ
доступа и не повод менять рабочую машину. Не добавлять SSH-ключи или пользователей.
Первый неожиданный результат останавливает следующие попытки; оставшиеся NOT_RUN.
Повторять run/создавать новый каталог ради PASS запрещено. Show/отчёт разрешены.

Отказ или timeout сборщика останавливает только проверку. Рабочая сеть сохраняется,
без автоматического «ремонта», остановки VPN или таймера off. Recovery не запускается,
поскольку сетевое состояние не изменяется. При потере связи после её возвращения только
show/отчёт; входящий обрыв>1мин не предполагает восстановление следующей командой модели.
Будущие разрушающие опыты требуют отдельного восстановления исходного on.

Одна команда/целый блок на шаг, дождаться результата. Не вставлять код в sudo prompt.
Не печатать сырые config/rules/journal/private JSON/IP/PID/UID числом/имена NIC/учётные
данные/URI. В Git только обезличенная сводка. Передача кода worker через stdin позволяет
сохранить каталог helpers root700: не ослаблять его права ради запуска от service UID.

## 3. S1: терминал, собственные заметки, sudo

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
root=Path.home()/'xgw-w3m'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3m/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: чистый Git, installed и существующий on

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

## 5. P1: заморозить только два тестовых helper

### P1.1. Одна подготовка по двум SHA

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_permission_probe.py':'3699bd2ab77831ba46bc09e719e521c0bf2d9ed37535d101e65cc320059391d6',
          'wave3_on_observer.py':'0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3m')
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
print('PERMISSION_HELPERS_FROZEN',expected)
PY
```

Нужен PERMISSION_HELPERS_FROZEN и два точных SHA, exit0. Уже существующий каталог или
неполная подготовка — STOP; не удалять/переименовывать и не ослаблять mode. Это не
установка продукта. Старый observer используется только как библиотека snapshot/public;
его CLI start/wait/end и старые safety helpers не запускать.

## 6. T1: один прогон и чтение результата

### T1.1. Запустить один раз

```bash
sudo -n python3 -I /run/xgw-w3m/wave3_permission_probe.py run
```

Ожидается exit0 и marker=PERMISSION_PROBES_PASS. Перед попытками читается on-контекст,
проверяются реальные UID/GID/Groups процесса и отсутствие DAC-bypass caps, непривилегированный
аккаунт SB, CapInh/Prm/Eff/Bnd/Amb0, NoNewPrivs. Missing/гоночная identity не считается
отказом доступа. Root-контроль nft list tables должен завершиться успешно.
Утилита setpriv не устанавливается; если её нет/опции несовместимы — BLOCKED_TOOL.

В каждом child UID/GID/дополнительные группы совпадают с целевым процессом. Capsets0×5
и NoNewPrivs повторно проверяются внутри child ДО попытки. Bounding set очищен; пароли,
runuser с другим набором групп или root вместо пользователя недопустимы. Для Xray отдельно
проверяется отсутствие эффективных DAC_OVERRIDE/DAC_READ_SEARCH, поэтому capless child
не скрывает возможности обхода файловых прав настоящим процессом.

| Порядок/ID | Операция child | Ожидается |
|---|---|---|
| 1 SB_OWN_CONFIG | open собственного конфига SB, затем close; содержимое не читается | ALLOWED, positive control |
| 2 SB_XRAY_CONFIG | open конфига Xray | DENIED_PERMISSION |
| 3 SB_XRAY_API | connect к существующему UNIX socket Xray, без RPC | DENIED_PERMISSION |
| 4 SB_STATE_CREATE | создать один уникальный пустой файл в состоянии XGW | DENIED_PERMISSION |
| 5 SB_NFT_READ | nft list tables, stdout уничтожается | DENIED_PERMISSION |
| 6 XRAY_SB_CONFIG | open конфига SB от UID/GID/групп Xray | DENIED_PERMISSION |

Child ограничен3с, его nft2с/socket0.5с; запросы snapshot/root-read3с. Это таймауты отдельных
операций, не обещание строгого времени всего процесса/ядра. В пределах run не вводить
следующую команду в тот же terminal. На stdout только JSON-сводка, private identifiers
остаются в памяти/закрытых файлах. Отказ CAP/UID drop, ENOENT, ECONNREFUSED, ELOOP,
timeout/ошибка команды или JSON — UNKNOWN/NOT_RUN, а не ожидаемый Permission denied.
Root-контроль отличает неисправную команду nft от отказа прав.

Первое несовпадение → следующие cases NOT_RUN, затем read-only конечный снимок и отчёт.
PERMISSION_PROBES_RECORDED/STOP_PERMISSION_PROBE/exit3 — не PASS; не перезапускать run,
не править ACL/groups/caps/systemd/конфиги для получения нужного результата.

### T1.2. Прочитать только сводку

```bash
sudo -n python3 -I /run/xgw-w3m/wave3_permission_probe.py show
```

Show можно повторить для заполнения отчёта. summary отсутствует — run не завершился,
доступные факты и ошибка в отчёт; не cat helpers/private JSON. Недоступный sudo —
BLOCKED_TOOL_SUDO, не передавать пароль в команду и не менять sudoers.

### T1.3. Конечный рабочий статус

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Нужны прежний HEALTHY/on и версии. Иное — записать без enable/disable/restart.

### T1.4. Конечный выбор пула

```bash
sudo xgw pool | head -1
```

Должен сохраниться текущий режим, не навязанный off. Pin/Tailscale тоже не меняются.

### T1.5. Оценить ровно измеренный scope

PASS требует всех6cases/pass_expectedtrue с identity_verifiedtrue, on_context_preservedtrue,
settings_unchanged3true, same_boottrue, service_pid_same6true и отсутствия cleanup pending.
При смене PID/настроек — контекст не тот же: разобрать факт, не приписывать автоматически
проверке и не объявлять устойчивость одного процесса. Рост логов от отказа может быть
следствием этих попыток; не считать его внезапной сетевой поломкой без контекста.

Проверяется доступ отдельных capless процессов с реальными UID/GID/Groups. Это не код,
запущенный внутри постоянного service sandbox, и не доказательство всех seccomp/AppArmor/
mount namespace ограничений. Неподтверждённые ограничения не дописывать. Запрос изменения
ip rule в живое ядро специально NOT_RUN; отсутствие сетевых capabilities измерено отдельно.
Не запускать старый isolation, который содержит ip rule add/del.

Этим не закрываются D1-on reinstall/scopedfaults/E4 actual packets/LAN UDP/IPv6/DNS leak/
все Tailscale-пути или всяwave3. Рабочий шлюз и его эксплуатация сохраняются независимо
от того, какие специальные проверки ещё не выполнены.

## 7. Отчёт

Скопировать docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-TEMPLATE.md обычным редактором в
`$HOME/xgw-w3m/report.md`, заполнить факты/STOP/UNKNOWN. Сохранить codepin/HEAD/tree,
два SHA/owner/mode, installed4, исходный/конечный режим, all6cases и NOT_RUN после первого
несовпадения, root positive control, identity flags, before/after и ограничения.
Если остался собственный пустой файл — только факт cleanup pending без приватного пути,
не делать ручную чистку; сообщить для отдельного точного исправления. Не удалять другие файлы.
Без сырых конфигов/API сообщений/правил/адресов/скриншотов/private JSON. Прочитать черновик
перед публикацией. VPN в конце остаётся on; отключение/откат в off не предусмотрены.

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
notes=Path.home()/'xgw-w3m'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3m — проверки границ доступа при on')
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
