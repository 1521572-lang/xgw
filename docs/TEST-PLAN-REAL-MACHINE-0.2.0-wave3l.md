# ТЗ Flash: wave3l — наблюдение рабочего шлюза при on, без переключений

## 1. Действующее указание владельца и цель

Владелец уточнил 02.11.2026: шлюз использовался для раздачи интернета через подключённый
к XGW Wi-Fi-роутер ещё до доработок; он вернёт VPN в рабочий режим. Исходить из рабочей
схемы XGW → роутер → устройства. Исходный режим этого протокола — **существующий on**.
Не переводить его в off ради теста. Прежние off-preflight/enable/off-rollback из wave3b…k
не входят в этот пакет. Прежнее согласие на выключение не переносится на этот опыт.

Wave3k3d4a3dc подтвердил read-only опись: WAN/LAN up/carrier1, разные интерфейсы,
LAN адрес соответствует конфигурации, tcpdump установлен; files_unchanged3true.
В начале был on; владелец сам выключил его и разрешил продолжить, модель не переключала
сеть. Это зафиксированное отклонение прежнего сценария. SSH заявлен владельцем, не испытан.
Tailscale route=vpn, службу и её роль канала управления сохраняем.

Результат wave3j остаётся принятым: короткий host-кейс и measured loaded=true.
Повторять установку/G1/enable ради этих фактов не требуется. Новый этап — не новая
инвентаризация базовой работоспособности: он наблюдает обычную эксплуатацию минимум600с
и фактические свойства новой защиты/процесса sing-box. SSH на роутер не является гейтом.

Новый файл tests/stand/wave3_on_observer.py — только тестовый сборщик. Продуктовый код,
unit/config/пакеты не устанавливаются и не меняются. Code pin продукта и прежних helpers:
351fb54e074f4a7b497a8a4244fc74c6088788d7. SHA нового сборщика: 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46.
Фактические HEAD/tree этого прогона записать в отчёт; доставка Git/freepool.

## 2. Границы и переходы

Разрешено: чистый FF Git, создание собственных заметок/закрытых файлов наблюдения,
чтение config/capture, nft list, systemctl show, /proc, /sys и ограниченных журналов.
Владелец продолжает обычное использование интернета. Сборщик не генерирует нагрузку,
не открывает SSH к роутеру и не посылает проверочные HTTP/DNS/UDP пакеты.

Запрещено: enable/disable/install/apply/net up/down; запуск прежних safety/job/restore,
создание rollback-to-off таймера; рестарт/остановка/reload/kill служб; nft/ip/sysctl/NM
изменения; смена pin/подписки/режима FreePool/Tailscale; установка инструментов;
fault injection/flush/перезагрузка/новые сетевые настройки роутера. No WAN changes.
Не запускать предыдущие ТЗ параллельно. Никакого автоматического «исправления» предусловий.

Если on ещё не включён владельцем — WAIT_OWNER_ON. Модель не включает его сама и не
повторяет вопрос о согласии: владелец уже сообщил намерение. Если ожидание сейчас
неосуществимо, отчёт BLOCKED_START_STATE с текущим фактом. Не менять off в on ради PASS.
При неизвестном/неожиданном результате остановить только проверку, сохранить рабочий
режим как есть и отчёт. Не выключать VPN «для безопасности» по этому протоколу.

Автономный recovery здесь не запускается: тест не меняет сетевое состояние. Если пропадёт
связь, потеря следующей команды модели не оставляет тестовую неисправность или таймер
выключения VPN. Сохранённые снимки останутся локально; после возвращения связи допустим
только show/отчёт. Внешние поломки ядра/провайдера этот наблюдатель не восстанавливает.
Будущие разрушительные опыты требуют отдельного дизайна восстановления исходного on;
старый always_off guardian для рабочего on неприменим.

Одна команда/целый блок на шаг; дождаться конца. Не вводить следующий код в sudo prompt
или работающий процесс. Указанные интервалы ожидания не превышают45с за вызов.
Никаких сырых rules/config/logs/status/IP/MAC/UUID/имён клиентов/URI в Git или чат.
Публикуются только сводки show, статусы/версии и обезличенные наблюдения владельца.

## 3. S1: подготовка терминала и собственных заметок

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
root=Path.home()/'xgw-w3l'
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
этой проверки. Если снова отказ — STOP до наблюдения; отчёт S1=BLOCKED_TOOL_SUDO,
зависимые этапы NOT_RUN. Не менять sudoers, не передавать пароль через stdin/команду/заметки.
Это заранее предусмотренный путь подготовки. Сетевые изменения запрещены.
После успеха записать read-only scope и исходные сведения в `$HOME/xgw-w3l/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до наблюдения.

## 4. S2: идентичность и существующий рабочий on

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

## 5. P1: закрытая копия только нового наблюдателя

### P1.1. Создать root700 каталог и root600 файл по SHA

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
expected='0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'
source=Path(sys.argv[1])/'tests/stand/wave3_on_observer.py'
payload=source.read_bytes()
if hashlib.sha256(payload).hexdigest()!=expected:
    raise SystemExit('STOP_OBSERVER_SOURCE_SHA')
root=Path('/run/xgw-w3l')
if root.exists() or root.is_symlink():
    raise SystemExit('STOP_ALREADY_PREPARED')
root.mkdir(mode=0o700,exist_ok=False)
fd=os.open(root/'observer.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as stream:
    stream.write(payload)
actual=root/'observer.py'
assert actual.stat().st_uid==0 and actual.stat().st_mode&0o777==0o600
assert root.stat().st_uid==0 and root.stat().st_mode&0o777==0o700
assert hashlib.sha256(actual.read_bytes()).hexdigest()==expected
print('ON_OBSERVER_FROZEN',expected)
PY
```

Нужен ON_OBSERVER_FROZEN и точный SHA. Если каталог уже есть — STOP, не удалять,
не переименовывать, не создавать новый ради чистого результата. Если копирование
прервалось — неполный P1, никаких запусков. Это закрытые файлы теста в /run,
не установка продукта и не замена /opt/xgw/lib. Guardian не копируется и не запускается.

## 6. O1: снимок начала и обычная работа

### O1.1. Один стартовый снимок

```bash
sudo -n python3 -I /run/xgw-w3l/observer.py start
```

Нужны exit0 и marker=ON_OBSERVATION_STARTED. Файлы start-private/start-summary создаются
эксклюзивно root600. В stdout только сводка. Начальные условия: capture before/aftertrue,
пять основных служб active, guard postrouting10/forward/drop>=1/reject0, три файла
не изменились во время чтения. Tailscaled, caps и DAC записываются отдельно.

STOP_BASELINE_READ/STOP_OBSERVER_READ/инойrc — STOP проверки, не продукта; не начинать
ожидание и не повторять start. Разрешены O2.2 show и отчёт. Не делать диагноз об отказе
домашнего интернета из timeout единственного nft/systemctl чтения.

### O1.2. Наблюдение без вмешательства

Владелец продолжает обычную работу через свой роутер. Не требовать SSH, отдельного
sentinel или специально выключать другие VPN на устройствах. Не просить менять кабели.
В заметках только фактически доступное: продолжал ли работать интернет на привычном
устройстве и сохранился ли прежний способ управления/Tailscale. Если никто не наблюдал
путь лично, записать «не наблюдался в этом интервале», сохраняя рабочую схему как baseline.
Это не основание ещё раз инвентаризировать LAN или отказать в существовании рабочего шлюза.

Выполнить одну команду:

```bash
sudo -n python3 -I /run/xgw-w3l/observer.py wait
```

WAIT_MORE/exit0 означает, что минимум600с ещё не прошёл. Повторять ТОЛЬКО этот шаг,
не более20 вызовов. Каждый вызов ждёт максимум45с, затем возвращается. Между вызовами
можно сообщать владельцу существенные наблюдения, не выполнять сетевые команды.
READY_FOR_END/exit0 → сразу O2.1. Если600с уже прошли из-за задержки оператора, дополнительное
ожидание не добавляется. Это ожидание существующей работы, не повтор сетевого опыта.
Если лимит20 вызовов исчерпан без READY/ошибка/перезагрузка — O2.2 и отчёт INCONCLUSIVE.
Не увеличивать сроки ради PASS. Сборщик не работает постоянно, на wait он только спит.

## 7. O2: конечный снимок и допустимая интерпретация

### O2.1. Один конечный снимок

```bash
sudo -n python3 -I /run/xgw-w3l/observer.py end
```

Нужен JSON с marker=ON_OBSERVATION_RECORDED, exit0. Это означает только сохранённые
on bookends, прежние три файла и pool mode. Сам маркер не объявляет все остальные поля
PASS. Минимум600с определяется monotonic, сохраняется фактическое время. Снимки не
атомарны между всеми подсистемами. Capture проверяется до/после каждого снимка;
из них нельзя сделать непрерывное измерение capture за весь интервал.

Если STOP_STATE_CHANGED/инойrc — сохранить частичный результат, не повторять end/start,
не возвращать настройки/службы/сетевой режим. Причина изменения ещё не установлена.
Недоступный sudo — отчёт BLOCKED_TOOL_SUDO; продукт продолжает текущую работу.

### O2.2. Прочитать только готовые обезличенные сводки

```bash
sudo -n python3 -I /run/xgw-w3l/observer.py show
```

Этот read можно повторить для переписывания отчёта. Если есть только start-summary —
end NOT_RUN. Если summaries нет — указать ранний STOP. Не cat start-private.json,
не печатать /proc/raw journal/config. Сохранять файлы до разбора, не чистить /run.

### O2.3. Зафиксировать конечный пользовательский статус

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидается рабочий HEALTHY/on. Иное — факт для отчёта без enable/disable/restart.

### O2.4. Зафиксировать конечный режим пула

```bash
sudo xgw pool | head -1
```

Ожидается прежний режим, не навязанный off. Версии/pin/действия владельца не подменять
предположениями. Не восстанавливать значения по предыдущему отчёту.

| Данные | Допустимая трактовка |
|---|---|
| elapsed>=600 + bookends_on | Наблюдались включённые начало/конец, не непрерывный capture |
| Account_nonprivilegedtrue + CapInh/Prm/Eff/Bnd/Amb zero + UID/GID match + forbidden groups absent + NoNewPrivs | Фактические свойства процесса в этих точках; не все negative isolation tests |
| same_process_during_read=false | Гонка с заменой процесса, свойства UNKNOWN |
| same_singbox_process_bookends=false/null | Другой/неизвестный процесс; не объявлять один стабильный процесс |
| restart_count_delta>0 / <0 / null | Перезапуск / reset несопоставимых счётчиков / неизвестность; причину не выдумывать |
| DAC expectedtrue | Метаданные по stat, не попытка чтения/записи от UID sing-box |
| LAN RX/TX delta>0 | Передача байт на интерфейсе, не привязка к конкретному клиенту/VPN-egress |
| interface_roles_samefalse/counter reset | Delta null/несопоставима, не нулевой трафик |
| journals query_okfalse/truncated/parse_errors/clock_step_suspected | Покрытие журналов неполное; ноль ошибок не доказан |
| error_priority/traceback/permission/fatal rows>0 | Есть строки для разбора; категории пересекаются, не обязательно новый дефект |
| journals complete и counts0 | В выбранных журналах/интервале соответствующих строк не найдено |
| tailscale_routevpn, serviceactive | Сохранённая настройка/служба, не проверенный DERP или все сетевые пути |
| Владелец пользовался интернетом | Зафиксированное наблюдение обычной эксплуатации; не синтетический E4 |

Нельзя объявить закрытыми D1-on reinstall/scoped faults/E4 actual-packets/LAN UDP/IPv6/
DNS leak/все Tailscale-пути или всюwave3. Они остаются отдельными задачами; разрушительные
проверки не обязательны для продолжения эксплуатации рабочего шлюза и здесь не выполняются.
DERP fallback settingtrue при route=vpn не означает выполнение ветки проверки DERP direct.

## 8. Отчёт и безопасная публикация

Скопировать docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-TEMPLATE.md обычным редактором в
`$HOME/xgw-w3l/report.md`. Заполнить факты/STOP/UNKNOWN, HEAD/tree, frozen SHA, start/end,
все агрегаты, elapsed, журналы с покрытием, пользовательские наблюдения отдельно от
счётчиков. Действия владельца в период наблюдения записать, не скрывать как «изменений нет».
Не включать private JSON, IP/имена NIC/PID/сырые логи/скриншоты/адреса клиентов/учётные данные.
Вручную прочитать черновик перед публикацией. Существующий рабочий шлюз не выключать
после отчёта. Указать фактический режим; если on ещё не включён — не создавать фиктивный PASS.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместо чтения черновика из раздела 8. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3l'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3l — наблюдение рабочего on')
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
