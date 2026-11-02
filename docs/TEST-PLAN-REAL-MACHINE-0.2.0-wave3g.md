# ТЗ Flash: wave3g — исправление host guard после reroute, один enable в автономном окне25с

## 1. Цель, пределы и идентичность

Это исполняемый протокол для GLM-5.3-Flash/ZCode с терминалом и зрением на ThinkCentre
Ubuntu24.04.5/systemd255. Прочитать целиком ДО начала команд. Выполнять только эту версию ТЗ.

Отчёт wave3d b7be627 подтвердил автономные off-окна и отдельную установку по прямой команде
владельца с rc0. Установленный продукт уже готов; повторная установка здесь не выполняется.
Отчёт wave3f221eecb подтвердил повторный plain TCP refused0.065с при успешном marked HTTPS;
mode/inbound/LISTEN/proxy lookup корректны, loadednull/child_deadline4с. Enable6.183с/rc0,
возвратoff25.146с/restore0.146с, WAN6/6True. Прежняя отдельная установка уже завершена.
В одном изолированном WSL netns A/B воспроизведён дефект guard: после route-mark reroute
следующий OUTPUT hook видит прежний WAN oif, отклоняя поток до доставки TPROXY. POSTROUTING
видит фактический oif. Подробности и ограничения — ADR-HOST-GUARD-POSTROUTING.md.
Это проверка гипотезы в фикстуре; причина ThinkCentre ещё требует фактического подтверждения.

В этой итерации меняется ТОЛЬКО установленный /opt/xgw/lib/xgw/net/nft.py: после обязательного
off-preflight, при остановленных писателях, атомарно с old/new SHA и резервной копией.
Затем старт контроллера вoff, одна HTTPS-база и ОДИН enable25с с обязательным off-rollback.
Весь installer не запускать; конфиг, профили WAN/LAN, sysctl, ядра и Tailscale не изменять.
Имена цепочек сохранены; host guard output теперь hookpostrouting10, отказdrop; forward
guard остаётся hookforward10/reject. Нет общего accept поmark_proxy или established.
Отказ при повреждении маршрута может стать таймаутом вместо TCP reset — не считать это обходом.

Волна3 этим целиком не закрывается.
От модели внутри on-окна не требуются подтверждения или сетевые действия. Указанное
локальное ожидание sleep35 разрешено; разрыв связи с моделью не отменяет таймер.

Код инструментов: **573b233bce881349e5ff4654600d3e077a9515f6**.
Относительно2862767 продуктовый diff только src/xgw/net/nft.py (render_guard).

| Frozen файл | SHA256 |
|---|---|
| wave3_safety.py | 0a9c67334ad82f5cb09eb4919220b04d6ae42410a10e0a7e0492cdee34585f3d |
| wave3_enable_probe.py | 13116c2be9f6533e5edfbae4cd9ab673f85b30545ef7cf4f36118e4777a4aa20 |
| nft.py.new (данные, mode0600) | 2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547 |

Версию определять по Git SHA и SHA256, а не по имени/старому заголовку файла. Локально прошли
15 узких nft/guard проверок (4 новых) +3 новых layout-parser проверки иruff; один изолированный reroute A/B. Реальные новые units/HTTPS/on wave3g первоначально NOT_RUN.

### 1.1. Что делает каждый участник

| Участник | Роль | Ожидаемое поведение |
|---|---|---|
| Flash | Проверяет гейты, запускает одну команду, читает сохранённый результат | Команд внутри on-окна от неё не требуется |
| xgw-w3g-safety.service | Отдельный локальный guardian, вне job-cgroup | Через25с всегда восстанавливает off, включая случай успешного enable |
| xgw-w3g-job.service | Отслеживаемый job с sampler | Один enable и сбор агрегатов; при rollback вся группа прекращается |
| xgw.service / xgw-net.service | Контроллер и другой писатель правил | При rollback останавливаются, чтобы не спорить с восстановлением |
| Xray / sing-box | Ядра | Guardian не выполняет их принудительное выключение |
| WAN | Входящее подключение к провайдеру | Профиль/адреса/DNS/MTU не перенастраиваются |
| LAN | Раздача сети | Адаптер не отключается и не переподключается вручную |

Отсутствие команд модели после launch — нормальная часть протокола. При outage>1мин модель
не сможет чинить связь: guardian должен уже работать независимо от неё. Его окно25с и команды
stop/kill/nft с таймаутами1/1/3с дают номинально около30с плюсIO/polling. Это не абсолютная
гарантия при отказе ядра, диска, питания или провайдера. Не обещать владельцу гарантированные30с.

## 2. Правила исполнения для модели

1. Один шаг — одна указанная команда/один целый heredoc-блок. Дождаться завершения команды
   и обычного приглашения терминала. Не печатать следующую команду в работающий процесс,
   запрос sudo-пароля, pager, Python REPL или редактор.
2. Кодовые ограждения Markdown и символ приглашения `$` не вводить. Heredoc копировать
   целиком, включая отдельную завершающую строку PY. Не исправлять кавычки/отступы на глаз.
3. Не считать команду успешной только по появлению shell prompt. Проверить ожидаемый
   маркер/JSON и код завершения, если инструмент его показывает. Traceback, отсутствующий
   файл, permission denied, таймаут, неожиданный JSON — отклонение, не повод чинить код.
4. При неуспешном гейте зависимые шаги NOT_RUN. Прекратить новые сетевые/системные изменения;
   записать факт и точный ID шага. Если timer уже стартовал — дать ему закончить и читать
   результат по разделу8. Не создавать новый каталог/новый trial ради PASS.
   Запись заметок и публикация отчёта поF при работающем канале остаются разрешёнными.
5. Не запускать один и тот же mutating-шаг повторно, если первый ответ потерялся/задержался.
   Особенно launch: повторный запуск не является способом узнать состояние первого.
6. Все заметки/черновик до публикации хранить в `$HOME/xgw-w3g`, не в клоне. Runtime snapshot
   и журналы остаются root0700 в `/run/xgw-w3g`. Не переносить из них сырые данные в Git.
7. Публикуемые значения брать только из этого прогона; факты прежнего wave3f помечать историческими. Ориентиры/примеры ТЗ и измерения
   прежних отчётов не подставлять вместо результата. UNKNOWN/null/отсутствие поля сохранять.
8. Прямое новое указание владельца имеет приоритет над ТЗ. Если оно меняет scope, окно или
   rollback, отметить отдельное отклонение и не объявлять изменённую процедуру штатным PASS.
   Цитата из старого отчёта не является новым указанием владельца.

### 2.1. Запреты

Не выполнять install/reinstall/reboot/shutdown, nmcli modify/reapply/up/down, netplan apply,
произвольные nft/ip/sysctl, ручные xgw enable/disable/apply, смену подписок/FreePool/pin,
capture.local или Tailscale route/fallback. Не нажимать VPN в панели, трее или другом GUI.
Не выполнять isolation/scoped faults/нагрузку. Не оставлять VPN on после окна.

Не отключать TLS verification, не менять таймауты/URLs/код/права сервисов для получения PASS.
Не запускать bare job, sampler run или локальный pulse-loop. Не отправлять pulse/disarm:
фиксированное окно программно не продлевается и не снимается этим способом.

Разрешены только точные команды этого ТЗ: Git FF; локальные файлы/замороженные helpers;
G1 атомарная замена ровно nft.py и NEW_GUARD_SYNTAX nft-c без загрузки;
context/prepare/facts/window/launch/report; единственный enable внутри tracked job; подготовленный
off-rollback и старт xgw после подтверждённого восстановления.

### 2.2. Согласие и исходная ситуация

До подготовки опасных шагов проверить действующее согласие владельца именно на:
- один краткий enable, возможный обрыв прежних direct-сессий и связи модели;
- GET к уже настроенным probe.url/первому probe.urls с чтением префикса тела;
- одну атомарную замену установленного net/nft.py при off/остановленных писателях, с SHA и backup;
- обязательный возврат к текущему off через25с, остановку контроллера и его последующий старт;
- указанный номинальный бюджет восстановления и его ограничения.

Если такое согласие уже действует, повторно не спрашивать. При отсутствии/неясности —
получить его ДО шагов5–7. Прежнее разрешение владельца завершить install без страховки
не распространять автоматически на этот enable. Отказ/отсутствие ответа — сетевых опытов нет.
Ответ и время записать без личных данных. Не ждать ответа владельца внутри активного окна.

## 3. Карта переходов

| Последний успешный этап | Допустимый следующий этап |
|---|---|
| S1: терминал/согласие/папка заметок | S2: Git и исходная база |
| S2: source + installed identity, старый nft SHA, HEALTHY/off/pool off | S3: заморозка2helpers и payload nft.py.new |
| S3: все3 SHA/owner/mode и read-only job-context корректны | P1: подготовка off-preflight |
| P1: snapshot готов, WAN facts известны и совпали | P2: off-window25с |
| P2: RESTORED_OFF/nft0/timing/WAN/связь подтверждены | G1: атомарное обновление nft.py при остановленных писателях |
| G1: новый nft SHA установлен, остальные3 файла прежние, off | P3: старт контроллера |
| P3: снова HEALTHY/off | B1: новый snapshot enable и baseline HTTPS |
| B1: ready=true, diagnostic_gate=true, известны быстрые факты и есть измеренная база | E1: один launch enable |
| E1: timer/job начаты либо ответ неоднозначен | Только ожидание и R1 чтение результата |
| R1: подтверждённый off-rollback и связь | R2: старт контроллера и итог |
| Любой неуспех | STOP; разрешённое чтение/отчёт, без новых mutating-действий |

## 4. S1–S3: терминал, источник, установленный продукт, frozen helpers

### S1.1. Проверить среду

```bash
uname -s
```

Ожидается Linux на ThinkCentre. Это не Windows/PowerShell и не локальная VM разработчика.

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
root=Path.home()/'xgw-w3g'
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

Допустим новый каталог или заранее подготовленный свой каталог, содержащий только plan.md.
Plan.md сохраняется; ничего не удалять/пересоздавать. Любые run-start/notes/measurements/другие
файлы означают уже использованный каталог — STOP, не начинать новый trial. Создание run-start
эксклюзивное. После NOTES_CREATED:

```bash
sudo -n true
```

Код0 означает, что этот инструментальный канал уже может выполнять sudo без запроса пароля.
Если нужен пароль/нет кэша, новых sudo-команд модель не запускает. Владелец в своём настоящем
терминале может выполнить `sudo -v` и ввести пароль непосредственно туда. После его сообщения
повторить ТОЛЬКО read-only проверку `sudo -n true` в том же инструментальном канале.
TTY/timestamp sudo разных терминалов могут различаться: успех владельца не заменяет код0
этой проверки. Если снова отказ — STOP до сетевых шагов; отчёт S1=BLOCKED_TOOL_SUDO,
зависимые этапы NOT_RUN. Не менять sudoers, не передавать пароль через stdin/команду/заметки.
Это заранее предусмотренный путь подготовки, не основание снимать страховку.
После успеха записать согласие из§2.2 и исходные сведения в `$HOME/xgw-w3g/notes.md`. До S1.2 не создавать в этой папке артефактов прогона.

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 573b233bce881349e5ff4654600d3e077a9515f6 HEAD && git diff --exit-code 573b233bce881349e5ff4654600d3e077a9515f6 HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git diff --exit-code 28627675218f322185de11d0b569bca531d36aed HEAD -- src ':(exclude)src/xgw/net/nft.py' packaging config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
```

Ожидается SOURCE_PREFLIGHT_OK. Сохранить фактические HEAD/tree в заметках. Любая ошибка,
грязный клон, другая ветка или runtime diff — STOP. Не reset/checkout/rebase/force и не
переносить старые файлы поверх нового Git-кода. Загрузка нового ТЗ не устанавливает продукт.

### S2.2. Снять исходное состояние

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Нужны HEALTHY и явно снятый перехват (off). HEALTHY сам по себе не означает работающий VPN.

```bash
sudo xgw pool | head -1
```

Нужен pool off. Записать версии ядер и pin, не менять их. Если сейчас VPN on — STOP,
не выключать его ради подготовки. Не продолжать по одному последнему коду pipeline:
проверить сам ожидаемый текст; пустой вывод не является успехом.

Ручной выбор получить отдельно безопасным фильтром JSON; весь status JSON не печатать:

```bash
sudo python3 -I - <<'PY'
import hashlib,json,re,subprocess
result=subprocess.run(['/usr/local/bin/xgw','status','--json'],stdout=subprocess.PIPE,
                      stderr=subprocess.DEVNULL,timeout=12,check=True)
data=json.loads(result.stdout)
if 'pin' not in data:
    raise SystemExit('STOP: неизвестная схема pin')
pin=data['pin']
if pin is not None and (not isinstance(pin,dict) or not isinstance(pin.get('tag'),str)):
    raise SystemExit('STOP: неизвестная схема pin')
tag=pin['tag'] if pin else None
safe=bool(tag and re.fullmatch(r'(?:proxy|spare)-[a-z]{2}-[0-9a-f]{4,64}',tag))
print(json.dumps({'manual_pin_active':bool(pin),'safe_tag':tag if safe else None,
                  'tag_sha256':hashlib.sha256(tag.encode()).hexdigest() if tag else None,
                  'down':bool(pin and pin.get('down'))}))
print('PIN_STATE_OK')
PY
```

Нужен PIN_STATE_OK. Отсутствие активного pin допустимо: записать manual_pin_active=false,
не создавать выбор. При скрытом tag сравнивать fingerprint. Изменение/истечение pin позже
записать как факт; не возвращать старый выбор вручную для совпадения с ожиданием.

```bash
python3 -I - <<'PY'
import subprocess
required=('xgw.service','xgw-xray.service','xgw-singbox.service','xgw-dhcp.service')
ok=True
for unit in (*required,'xgw-net.service'):
    result=subprocess.run(['systemctl','is-active',unit],text=True,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
    state=result.stdout.strip()
    print(unit,state)
    if unit in required:
        ok=ok and state=='active'
print('CORE_UNITS_OK' if ok else 'STOP_CORE_UNITS')
raise SystemExit(0 if ok else 3)
PY
```

Для четырёх required-служб ожидаются active и CORE_UNITS_OK. Общий exit0 от обычного
systemctl is-active с несколькими именами сам по себе не доказывает, что active все службы.
Не стартовать отсутствующую/неактивную службу для «починки» предусловия. Неожиданное состояние
записать и STOP. xgw-net выводится отдельно как факт, не включён в этот active-гейт.

```bash
python3 -I - <<'PY'
import subprocess
ok=True
for wave in ('b','c','d','e','f'):
    for role in ('safety','job'):
        unit=f'xgw-w3{wave}-{role}.service'
        result=subprocess.run(['systemctl','is-active',unit],text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
        state=result.stdout.strip()
        print(unit,state)
        ok=ok and state in ('inactive','not-found','unknown')
print('OLD_TRIALS_INACTIVE' if ok else 'STOP_OLD_TRIAL')
raise SystemExit(0 if ok else 3)
PY
```

Здесь ожидается OLD_TRIALS_INACTIVE: каждый старый unit inactive/not-found/unknown.
Скрипт завершается0 только после проверки всех десяти; это отличается от единичного
systemctl is-active отсутствующего unit, где код обычно ненулевой. Active/activating/
deactivating — STOP: старый опыт вручную не прерывать. Состояние xgw-net может быть inactive
после прежнего rollback; записать его отдельно, не выдавать за результат нового enable.

### S2.3. Проверить реально установленный код

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
repo=Path(sys.argv[1])
ok=True
for rel in ('install.py','net/sysctl.py','diag.py'):
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

Нужны три True и INSTALLED_SOURCE_OK. Несовпадение — STOP, не запускать install.
Эти3 файла вG1 не обновляются; разрешённая замена касается только net/nft.py после off-preflight.

### S2.4. Подтвердить исходный установленный nft.py ДО обновления

```bash
sudo python3 -I - <<'PY'
import hashlib,stat
from pathlib import Path
path=Path('/opt/xgw/lib/xgw/net/nft.py')
info=path.lstat()
safe=stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0 and not info.st_mode&0o022
match=hashlib.sha256(path.read_bytes()).hexdigest()=='75057aaf1846a386fb694e9d1116d7a1c0569dfc60c3425f9a950ae4894a2b96' if safe else False
print('old_nft_sha_matches=',match,'safe_owner_mode=',safe)
print('OLD_NFT_SOURCE_OK' if safe and match else 'STOP_OLD_NFT_IDENTITY')
raise SystemExit(0 if safe and match else 3)
PY
```

Нужны обаTrue/OLD_NFT_SOURCE_OK. Уже новый/иной SHA означает иной или частично выполненный
deployment — STOP с отчётом; не пропускать G1, не переустанавливать и не откатывать на глаз.
Остальные3 installed файла изS2.3 должны совпасть с pinned source, они не изменяются.

### S3.1. Создать frozen-копии

```bash
cd "$HOME/zcod/xgw" && test ! -e /run/xgw-w3g && sudo install -d -m 700 /run/xgw-w3g && sudo install -m 700 tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py /run/xgw-w3g/ && sudo install -m 600 src/xgw/net/nft.py /run/xgw-w3g/nft.py.new && printf 'FROZEN_COPY_CREATED\n'
```

Нужен FROZEN_COPY_CREATED. Существующий каталог/ошибка — STOP, ничего не удалять/переписывать.
Имена обоих helpers сохранять. Nft.py.new — данные обновления, mode0600, не исполнять/не импортировать. Переименование guardian в safety.py сломает импорт sampler.

### S3.2. Проверить все3 SHA и права ДО запуска кода

```bash
sudo python3 -I - <<'PY'
import hashlib,stat
from pathlib import Path
root=Path('/run/xgw-w3g')
expected={
 'wave3_safety.py':'0a9c67334ad82f5cb09eb4919220b04d6ae42410a10e0a7e0492cdee34585f3d',
 'wave3_enable_probe.py':'13116c2be9f6533e5edfbae4cd9ab673f85b30545ef7cf4f36118e4777a4aa20',
 'nft.py.new':'2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547',
}
items=[root]+[root/name for name in expected]
ok=True
for path in items:
    info=path.stat()
    wanted_mode=0o600 if path.name=='nft.py.new' else 0o700
    safe=info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==wanted_mode
    if path.name in expected:
        safe=safe and hashlib.sha256(path.read_bytes()).hexdigest()==expected[path.name]
    print(path.name,'verified=',safe)
    ok=ok and safe
print('FROZEN_IDENTITY_OK' if ok else 'STOP_FROZEN_IDENTITY')
raise SystemExit(0 if ok else 3)
PY
```

Нужны все verified=True и FROZEN_IDENTITY_OK. Не исправлять несовпадение на месте.

### S3.3. Проверить настоящий job-контекст без enable

```bash
sudo systemd-run --unit=xgw-w3g-job --wait --pipe --collect --property=RuntimeMaxSec=10 --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3g/wave3_enable_probe.py context /run/xgw-w3g
```

Это только чтение: mode=context не вызывает enable, не читает HTTP и не меняет правила.
Нужен JSON tracked_job_context=true/euid_root=true и успешное завершение процесса. Одна
строка systemd «запущено» не заменяет этот результат. Команда ограничена RuntimeMaxSec10с;
неожиданный timeout/exitне0/false — STOP, не отключать cgroup-проверку.

```bash
systemctl is-active xgw-w3g-job.service
```

После context ожидается inactive/not-found (exitне0). Active/activating/deactivating —
STOP. Применение wait/pipe/collect соответствует
[systemd-run255](https://www.freedesktop.org/software/systemd/man/255/systemd-run.html):
ожидаем завершения диагностического процесса и получаем его stdout; scope/user не использовать.
Новый реальный job позже всё равно повторно проверит свой контекст и active safety-window.

## 5. P1–P3: обязательный автономный off-preflight

### P1.1. Подготовить snapshot, не запуская окно

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py prepare /run/xgw-w3g/offcheck
```

Ожидается PREPARED. Команда проверяет existing unit, явный off/pool off, исходную политику
и nft -c, сохраняет boot ID, snapshot и fingerprints. PREPARED означает только подготовку:
таймер ещё НЕ работает. Ошибка/Traceback — STOP, никаких последующих сетевых команд.

### P1.2. Проверить полноту WAN evidence

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py facts /run/xgw-w3g/offcheck
```

Нужны all_verified=true и все шесть WAN_unchanged=true: profile, addresses,
live_gateway_dns, route4, route6, mtu. False означает изменение; null — замер недоступен.
Ни false, ни null не считать совпадением. STOP, без «переснимем до получения True».
DHCP/RA могли обновиться самостоятельно; несовпадение не доказывает вину XGW.

### P2.1. Запустить независимое окно при уже off

```bash
sudo systemd-run --unit=xgw-w3g-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3g/wave3_safety.py window /run/xgw-w3g/offcheck 25
```

Успешный systemd-run означает принятие запуска unit, а не завершённый rollback.
Если ответ задержался/команда вернула ошибку, НЕ запускать повторно: unit уже мог стартовать.
Продолжать только чтением после ожидания. Не нужны pulse, disarm или быстрый цикл Flash.

### P2.2. Дождаться окна без действий модели

```bash
sleep 35
```

Это обычное локальное ожидание, не условие срабатывания guardian. Если сама модель ответит
позже, таймер всё равно завершится. После возврата приглашения читать отдельно:

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py status /run/xgw-w3g/offcheck
```

Нужны state=RESTORED_OFF, nft_rc=0, seconds_since_last_pulse в ориентире25–30с и
recovery_seconds≤5с. Здесь seconds_since_last_pulse — всё время от начала фиксированного
окна: pulse не было. recovery_seconds исключает ожидание. Время чтения экрана/sleep35
не подменяет эти измерения. stop/kill rc могут быть ненулевыми из-за отсутствующего job.

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py observe /run/xgw-w3g/offcheck
```

Нужны capture_enabled=false, WAN/LAN operstateup/carrier1.

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py facts /run/xgw-w3g/offcheck
```

Нужны all_verified=true и все поля true. Владелец/модель остаются на связи.
FAILED_*, restoring спустя окно, nft_rcне0, total>30с, проблема связи/неизвестный WAN fact —
STOP; B1/E1 NOT_RUN. Не запускать следующий опыт, даже если сам xgw выглядит HEALTHY.

### G1. Атомарно обновить ТОЛЬКО nft.py при остановленном контроллере

G1 выполняется один раз ПОСЛЕ успешных P2 RESTORED_OFF/nft0/timing/WAN/связи и ДО P3.
Guardian уже оставил xgw/xgw-net остановленными. Команда сама повторно проверяет состояние,
boot/off snapshot, старый SHA и frozen новый SHA. Она не вызывает xgw/nft/ip/sysctl/NM,
не стартует службы и не меняет config/capture state. Backup остаётся root0600 в/run, не вGit.
Если связь пропадёт между файловым обновлением и P3, текущие правила и явный off остаются;
следующая команда модели не является механизмом сетевого восстановления.

```bash
sudo python3 -I - <<'PY'
import hashlib,json,os,stat,subprocess,tempfile
from pathlib import Path
root=Path('/run/xgw-w3g')
target=Path('/opt/xgw/lib/xgw/net/nft.py')
payload=root/'nft.py.new'
backup=root/'nft.py.before-wave3g'
old_sha='75057aaf1846a386fb694e9d1116d7a1c0569dfc60c3425f9a950ae4894a2b96'
new_sha='2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547'
temporary=None
phase='preconditions'
def digest(data):
    return hashlib.sha256(data).hexdigest()
try:
    for unit in ('xgw.service','xgw-net.service'):
        result=subprocess.run(['systemctl','show',unit,'--property=ActiveState','--value'],
                              text=True,capture_output=True,timeout=2,check=False)
        if result.returncode!=0 or result.stdout.strip() not in ('inactive','failed'):
            raise RuntimeError('writers')
    status=json.loads((root/'offcheck/status.json').read_text())
    snap=json.loads((root/'offcheck/snapshot.json').read_text())
    if status.get('state')!='RESTORED_OFF' or status.get('nft_rc')!=0:
        raise RuntimeError('off_restore')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=snap['boot']:
        raise RuntimeError('boot')
    if json.loads(Path(snap['capture_state']).read_text()).get('enabled') is not False:
        raise RuntimeError('not_off')
    if Path(snap['open_marker']).exists():
        raise RuntimeError('open_marker')
    if str(target.parent.resolve())!='/opt/xgw/lib/xgw/net' or target.is_symlink():
        raise RuntimeError('target')
    info=target.lstat()
    source_info=payload.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_gid!=0 or info.st_mode&0o022:
        raise RuntimeError('target_permissions')
    if not stat.S_ISREG(source_info.st_mode) or source_info.st_uid!=0 or source_info.st_gid!=0 or stat.S_IMODE(source_info.st_mode)!=0o600:
        raise RuntimeError('payload_permissions')
    old=target.read_bytes();new=payload.read_bytes()
    if digest(old)!=old_sha or digest(new)!=new_sha:
        raise RuntimeError('identity')
    phase='backup'
    with backup.open('xb') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(old);stream.flush();os.fsync(stream.fileno())
    if digest(backup.read_bytes())!=old_sha:
        raise RuntimeError('backup')
    phase='stage'
    fd,name=tempfile.mkstemp(prefix='.nft.py.wave3g.',dir=target.parent)
    temporary=Path(name)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),stat.S_IMODE(info.st_mode));os.fchown(stream.fileno(),0,0)
        stream.write(new);stream.flush();os.fsync(stream.fileno())
    if digest(temporary.read_bytes())!=new_sha or digest(target.read_bytes())!=old_sha:
        raise RuntimeError('stage_identity')
    phase='replace'
    os.replace(temporary,target);temporary=None
    dirfd=os.open(target.parent,os.O_DIRECTORY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    phase='verify'
    if digest(target.read_bytes())!=new_sha:
        raise RuntimeError('verify')
    print('NFT_CODE_UPDATED old_sha_verified=True new_sha_verified=True backup_verified=True')
except Exception as error:
    print('STOP_NFT_UPDATE','phase='+phase,'error_class='+type(error).__name__)
    raise SystemExit(3)
finally:
    if temporary is not None:
        temporary.unlink(missing_ok=True)
PY
```

Нужен единственный NFT_CODE_UPDATED с тремяTrue и exit0. Любая ошибка→STOP, P3/B1/E1 NOT_RUN.
Команду не повторять: backup эксклюзивный. После ошибки читать только текущий SHA/backup
наличие и состояниеoff; при публикации указать phase/error_class и был ли target уже заменён,
если это удалось установить. Не восстанавливать файлы через cp/install и не запускать installer.
При неясности оставить писателей остановленными, перехват не включать вручную.

Если G1 завершился ошибкой, разрешена только следующая read-only классификация файла и
публикация отчёта. Она не чинит/не восстанавливает файл и не запускает службу:

```bash
sudo python3 -I - <<'PY'
import hashlib
from pathlib import Path
def classify(path):
    try:
        value=hashlib.sha256(path.read_bytes()).hexdigest()
        return 'old' if value=='75057aaf1846a386fb694e9d1116d7a1c0569dfc60c3425f9a950ae4894a2b96' else 'new' if value=='2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547' else 'other'
    except OSError:
        return 'unreadable_or_absent'
print('installed_nft_version=',classify(Path('/opt/xgw/lib/xgw/net/nft.py')))
print('backup_version=',classify(Path('/run/xgw-w3g/nft.py.before-wave3g')))
PY
```

После этой ветки — F отчёт, не P3/B1/E1. При успешном G1 этот диагностический блок не нужен.

После успеха обязательно повторить installed3-файла S2.3 и следующую проверку четвёртого:

```bash
sudo python3 -I - <<'PY'
import hashlib
from pathlib import Path
equal=hashlib.sha256(Path('/opt/xgw/lib/xgw/net/nft.py').read_bytes()).hexdigest()=='2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547'
print('NEW_NFT_SOURCE_OK' if equal else 'STOP_NEW_NFT_IDENTITY')
raise SystemExit(0 if equal else 3)
PY
```

Нужны INSTALLED_SOURCE_OK×3 и NEW_NFT_SOURCE_OK; затем syntax-check ниже. В отчёте G1 выделить old/newSHA,
backup_verified, итоговые4 файла. Это выборочное файловое обновление, не новая установка.
Приватную резервную копию не удалять. После опыта новый файл остаётся установленным,
а сеть возвращается вoff; guardian откатывает сетевой режим, не версию файла.

До P3 проверить применимость НОВОГО on-guard синтаксисом nft -c на этой машине, без загрузки.
Команда импортирует уже проверенный installed код, создаёт текст guard в памяти и использует
только -c: не заменять на обычный nft -f. Stdout/stderr с правилами не печатаются.

```bash
sudo python3 -I - <<'PY'
import subprocess,sys
sys.path.insert(0,'/opt/xgw/lib')
from xgw import config
from xgw.paths import Paths
from xgw.net import nft
from xgw.net.capture import capture_for
paths=Paths.from_env();cfg,_=config.load(paths.config_file)
text=nft.render_guard(capture_for(cfg,paths).rules('on'))
try:
    result=subprocess.run(['nft','-c','-f','-'],input=text,text=True,capture_output=True,timeout=5,check=False)
    ok=bool(text) and result.returncode==0
except (OSError,subprocess.TimeoutExpired):
    ok=False
print('NEW_GUARD_SYNTAX_OK' if ok else 'STOP_NEW_GUARD_SYNTAX')
raise SystemExit(0 if ok else 3)
PY
```

Нужен NEW_GUARD_SYNTAX_OK/exit0; иначе P3/B1/E1 NOT_RUN, код остаётся установленным,
писатели остановленными, сеть в доказанномoff. Следующий шаг — отчёт о несовместимости,
а не удаление guard/упрощение правила. Это проверка синтаксиса, не доказательство пакетов.

### P3.1. Вернуть контроллер после доказанного off

Только после успешного G1, всех4 установленных файлов и NEW_GUARD_SYNTAX_OK. При STOP вG1 этот шаг запрещён.

Только когда RESTORED_OFF, nft0, timing/связь/WAN подтверждены:

```bash
sudo systemctl start xgw
```

Guardian намеренно оставляет xgw/xgw-net остановленными; это не дефект VPN.

```bash
sleep 5
```

Повторить read-only команды status/pool, PIN_STATE и CORE_UNITS из S2.2: HEALTHY/off/pool off, прежние
ядра/pin и связь. Иначе STOP. Не переходить к B1 по старому статусу из прежнего окна.

## 6. B1: новая off-база перед enable

### B1.1. Создать отдельный snapshot

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py prepare /run/xgw-w3g/enable
```

Ожидается PREPARED. Это новый case с текущим off после P3, не повторение on-опыта.

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py facts /run/xgw-w3g/enable
```

Все true/all_verified=true. Иначе STOP.

### B1.2. Измерить HTTPS без включения VPN

```bash
sudo python3 -I /run/xgw-w3g/wave3_enable_probe.py baseline /run/xgw-w3g/enable
```

Эта команда сама не включает VPN. В off разрешается DNS максимум двух уже настроенных
HTTPS-целей, сохраняются публичные IPv4 приватно. Выбранный адрес не печатается.
Каждая проба проверяет сертификат/SNI, HTTP200 и identity encoding, читает32769байт тела.
Внутренний предел3с и внешний subprocess4с. При падении на теле уже прочитанные байты
сохраняются; worker_deadline_or_error означает неизвестные фазу/байты, а не ноль байт.

Два пути:
- plain — обычная host-политика, без SO_MARK bypass;
- marked — штатная bypass-mark XGW, контрольный путь.

**ready_for_enable и baseline_healthy — разные признаки.** Первый означает, что сохранена
публичная цель, измеренная база И пройден read-only diagnostic_gate; второй — что обе off-пробы дочитали префикс. При ready=false
STOP; в том числе при diagnostic_gate=false. Не включать VPN для подтверждения известного дефекта. Если все результаты worker_deadline_or_error/неизвестны, тоже STOP: сравнивать нечего.
При ready=true, известной фазе хотя бы части измерений и healthy=false опыт разрешён под
тем же таймером: off-body уже мог быть заблокирован. Ограничение отметить в отчёте.
Не подбирать новые URL, не отключать TLS verification, не увеличивать таймауты/пороги.

База действительна5мин и связана с SHA sampler/boot ID. Между B1.2 и E1 не обсуждать новые
настройки и не редактировать файлы. Просрочка/изменение файла приводит к отказу до enable;
не обходить это новым timestamp/каталогом. Согласие владельца должно уже действовать.

### B1.3. Разобрать off_diagnostic до разрешения enable

baseline теперь печатает объект off_diagnostic и сохраняет его в отдельный off-diagnostic.json.
Оба — безопасные агрегаты этого прогона. Сборщик делает только чтение installed config/state,
/proc/net/tcp{,6}, `ip -4 -j route get` и Capture.loaded; не меняет сеть, конфиг, ядра, службы.
На весь child —4с; на каждый route-get —0.7с. Результаты быстрых стадий атомарно сохраняются
до loaded, поэтому даже его таймаут не должен стирать уже прочитанные mode/listener/routes.

Проверить и явно переписать в заметки, не пропускать это за ready=true:

| Поле | Условие перехода/значение |
|---|---|
| schema | 1 |
| requested_mode, effective_mode | оба off |
| configured_local | true; false→STOP, не включать local для прохождения теста |
| configured_lan | записать факт, не менять |
| inbound_problem_present | false; true→STOP, строка причины/конфиг не публикуются |
| capture_method | tproxy или tun; иное/отсутствует→STOP |
| loaded | false→STOP; true — проверка этой off-политики; null — неизвестность с причиной |
| loaded_reason, child_rc, phase | записать буквально; отсутствие→ошибка формата/STOP |
| guard_layout | вoff not_confirmed допустим; не загружать guard вручную |
| mismatch_present | записать факт; true→STOP до включения, требуется разбор политики |
| listener при tproxy | tcp_read=true И хотя бы ipv4_loopback=true либо ipv4_any=true |
| listener при tun | записать, отсутствие IPv4 LISTEN не объявлять отказом host TUN |
| routes.unmarked/proxy/bypass | перенести только route_type/device_role/table_role либо query/rc |
| ready_for_enable | true |
| baseline.json diagnostic_gate | true; можно прочитать разрешённым report, как ниже |

```bash
sudo python3 -I /run/xgw-w3g/wave3_enable_probe.py report /run/xgw-w3g/enable
```

На этом этапе ожидаются ТОЛЬКО baseline.json и off-diagnostic.json. Старые enable-result или
on-observations в новом snapshot недопустимы — STOP, исходный каталог не очищать и не повторять.
Loaded=null допустим только с полученными быстрыми фактами выше и известной причиной
child_deadline/child_error/capture_unknown; его не считать PASS loaded. В этой точке guardian
prepare уже проверил off loaded=True; новый null не отменяет честную неизвестность нового чтения.
invalid_result/spawn_error или неполные быстрые факты→STOP. При mismatch_present=true также
STOP, автоматический ready должен бытьfalse; противоречащий ему true — ошибка формата/логики,
а не разрешение продолжить. Route query error переносить как UNKNOWN; если все три lookup
неизвестны, ready должен бытьfalse: ключевой вопрос этой итерации не будет измерен.
Один/два известных lookup допустимы с
явно ограниченным результатом; менять приоритеты/таблицы ради диагностики запрещено.

Что означают эти поля:
- requested_mode — выбранный режим библиотеки; effective_mode — её расчёт по config/state и
  наличию inbound. Это не независимое наблюдение пакетов/всей nft-политики.
- inbound_problem_present=false означает согласованность применённого файла с ожидаемым
  inbound. Само по себе не доказывает, что Xray использует именно этот файл или принимает поток.
- LISTEN относится к порту capture.tproxy_port в текущем netns, не доказывает PID владельца,
  IP_TRANSPARENT или работоспособность outbound. IPv6 any/loopback не принимаются за IPv4:
  значение IPV6_V6ONLY этим не измерено. Порт/имена/адреса в отчёт не выводить.
- route-get — отдельный lookup для предразрешённой HTTPS-цели, uid0/ipproto TCP/dport, с mark0,
  mark_proxy и mark_bypass. Вывод содержит роли WAN/LAN/loopback/tun/other_or_absent и
  main/tproxy/tun/other. Это моделирование маршрута, НЕ nft trace и НЕ фактический egress.
  В частности unmarked→WAN до OUTPUT-mark — обычный результат даже исправного TPROXY.
- В off proxy lookup может указывать WAN/main: перехват и его маршруты ещё не включены.
  Не требовать local_lo вoff и не «исправлять» таблицы. Сравнивать именно on lookup послеE1.

## 7. E1: единственный enable

### E1.1. Финальная проверка перехода

До следующей команды модель должна иметь в заметках:
- согласие§2.2, source/frozen identity, G1 update/backup, installed-source×4 true, NEW_GUARD_SYNTAX_OK;
- успешный off-preflight с локальными timings и живой связью;
- текущий HEALTHY/off/pool off после P3;
- PREPARED нового case, WAN all_verified=true, измеренную свежую baseline;
- понимание, что после launch вмешательство модели внутри окна не требуется.

Нет хотя бы одного факта — E1 NOT_RUN. Исторический PASS другого запуска не заменяет гейт.

### E1.2. Одна команда локального старта

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py launch /run/xgw-w3g/enable enable "$HOME/zcod/xgw"
```

Ожидаемый смысл ответа: started=enable, fixed_window_seconds25, rollback=always_off,
pulse_required=false. Это подтверждение запуска, не PASS VPN и не доказательство, что
он до сих пор on к моменту чтения экрана. Внутри local launch сначала создаётся guardian,
проверяются armed/active, затем запускается tracked job. Sampler дополнительно проверяет
свою job-cgroup, актуальное fixed-window и свежую неизменённую baseline.

Сам sampler делает один xgw enable, записывает его rc отдельно, снимает on-frames,
Read-only diagnostic с общим пределом4с и plain/marked HTTPS (параллельно). Достаточность25с для полного сбора не
предполагается заранее: частичный результат сохраняется. Guardian через25с прекратит job
и писателей правил, применит сохранённый off, оставит контроллер остановленным.

Ошибка/таймаут/потерянный ответ launch — не повторять launch, не выполнять ручной enable.
Таймер уже мог стартовать. Следующий допустимый этап — R1 ожидание/чтение, не новый trial.

## 8. R1–R2: окончание окна и восстановление контроллера

### R1.1. Ожидание

```bash
sleep 35
```

Не отправлять pulse/disarm, не переключать панель/трей, не менять pin/Tailscale и не
выполнять другие network-команды. При потере связи модель может ничего не делать:
rollback должен исполниться локально. После восстановления сначала только чтение.

### R1.2. Прочитать guardian и фактическое состояние

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py status /run/xgw-w3g/enable
```

Отдельно записать state/nft_rc/stop_rc/kill_rc/seconds_since_last_pulse/recovery_seconds,
а также job-result.state/rc, если он есть. Нужны RESTORED_OFF, nft_rc0 и total≤30с.

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py observe /run/xgw-w3g/enable
```

Нужны capture_enabled=false, linksup/carrier1.

```bash
sudo python3 -I /run/xgw-w3g/wave3_safety.py facts /run/xgw-w3g/enable
```

Нужны все WAN facts true. False/null записать как изменение/неизвестность, не округлять.
Подтвердить, что владелец и модель на связи; прежнюю недоступность тоже отметить, если была.
Успешное чтение ПОСЛЕ rollback не доказывает непрерывную связь модели ВНУТРИ окна. Если её
не наблюдали отдельно, записать: during_on=UNKNOWN, after_off=подтверждено.

### R1.3. Прочитать автономный сбор

```bash
sudo python3 -I /run/xgw-w3g/wave3_enable_probe.py report /run/xgw-w3g/enable
```

Ожидаемые категории: baseline.json, off-diagnostic.json, enable-result.json, on-observations.json.
Отсутствие категории/поля — NOT_RUN/UNKNOWN, не восстановить его предположением. Порядок
событий: before_enable → after_enable → три независимо завершающихся задачи loaded/plain/marked
→ after_https. Порядок этих трёх строк отражает готовность задач, а не последовательное
прохождение одного потока. Поиск строки — по stage и path, не по номеру в массиве.
Каждый готовый результат атомарно записывается немедленно. Loaded-child≤4с и два HTTPS-child≤4с
идут параллельно; внешний25с guardian остаётся неизменным. Конкурентные пробы могут влиять
на задержки: это функциональная диагностика, не бенчмарк скорости/пинга.
Если job остановлен таймером, более поздние события могут отсутствовать — это ожидаемое
ограничение сбора, не повод повторить enable. Raw job.log/enable-cli.log не открывать/не печатать.

Для сохранения только безопасных агрегатов разрешено (после окна):

```bash
(umask 077; sudo python3 -I /run/xgw-w3g/wave3_enable_probe.py report /run/xgw-w3g/enable > "$HOME/xgw-w3g/measurements.jsonl")
```

Проверить, что файл не пуст, и использовать его вместе с заметками. Это не автоматический
готовый отчёт и не подтверждение полноты всех событий.

### R1.4. Разобрать on diagnostic и целостность схемы

Новое поле guard_layout — read-only `nft -j list table inet xgw_guard` с пределом0.8с,
сохранённое ДО loaded. Для подтверждения установленного исправления при on нужны query=ok,
host_hook=postrouting, host_priority=10, forward_hook=forward, host_drop_rules>=1,
host_reject_rules=0. Имена chain output/forward — внутренние идентификаторы XGW; output
больше не означает hookOUTPUT. Не делать вывод по одному имени цепочки.
Любой unknown/старый host_hook=output→исправленная фактическая политика не подтверждена.
После возвратаoff не подгружать правила/не повторять enable ради подтверждения.
Счётчики числа правил не являются счётчиками пакетов/утечки; layout не заменяет loaded.


В on-observations найти stage=loaded. Обязательны schema=1, loaded (bool или null),
loaded_reason и child_rc. Поле отсутствует либо неожиданный тип→INVALID_DIAGNOSTIC_SCHEMA;
не сокращать до «loaded не успел» без доказательства. При остановленном job сама строка
может отсутствовать: это PARTIAL_DIAGNOSTIC, а не неверный JSON и не False.

| loaded_reason | Как записывать результат |
|---|---|
| measured и loadedbool | фактическое True/False, child_rc отдельно |
| capture_unknown и loadednull | библиотека вернула неизвестность, child нормально завершился |
| child_deadline | общий child не завершился за4с, сохранить все полученные быстрые факты |
| child_error | child завершился ненулевым кодом, причина глубже этим не установлена |
| spawn_error | процесс child не удалось запустить; это ошибка измерения |
| invalid_result | schema/value не получены в корректном виде, ошибка измерения |

Если fast facts отсутствуют, UNKNOWN без догадок. Не открывать сырой stderr/конфиг в публичный
канал. Сравнить off/on requested/effective_mode, inbound_problem, mismatch, LISTEN и три lookup.
Все поля нового diagnostic перенести в шаблон §4.1, даже если они UNKNOWN. Не требовать,
чтобы порядок JSON ключей или стадий повторял примеры ТЗ. Затем R2 выполняется по тем же
условиям фактически доказанного off, независимо от успеха сбора.

### R2.1. Когда можно стартовать xgw

Только после RESTORED_OFF/nft0, off-флага, проверенных timing/WAN/links и живой связи:

```bash
sudo systemctl start xgw
```

```bash
sleep 5
```

Read-only status/pool, PIN_STATE и CORE_UNITS из S2.2: ожидаются HEALTHY/off/pool off,
CORE_UNITS_OK, прежние ядра/pin.
Если сам сбор был прерван, но возврат доказан, старт контроллера всё равно разрешён:
это восстановление проверенного off, не новая попытка enable.

### R2.2. Если восстановление не доказано

При FAILED_*, nft_rcне0, неизвестном состоянии, total>30с, still-on, отсутствии связи или
неподтверждённом WAN не стартовать контроллер «на удачу». Не xgw net up, не disable, не
перезапуск NetworkManager/адаптера/машины. Новых mutating-действий нет; сохранить доступные
агрегаты и уведомить владельца о конкретном незакрытом гейте. Если модель отключилась,
не считать наличие запланированной следующей команды механизмом восстановления.

## 9. Матрица интерпретации

| Наблюдение | Допустимый вывод |
|---|---|
| Guardian RESTORED_OFF/nft0 и фактический off/связь | Успешный локальный возврат этого опыта |
| job-result.rc0 | Sampler завершил сбор; это НЕ код xgw enable и НЕ PASS VPN |
| enable-result.rc0 | Команда enable завершилась; политику/данные проверять отдельно |
| Нет enable-result | Запуск/завершение enable не установлен; не писать, что его точно не было |
| Sampler aborted_by_safety, enable rc0 уже записан | Enable успел завершиться, сбор ограничен окном |
| Новый guard_layout приon, enable0, plain/markedprefix_ok и успешный off rollback | Короткий hostTCP кейс прошёл; loadedunknown отдельно, полная волна3 открыта |
| loaded=false | Фактическая проверка соответствия политики не прошла; расследовать, без вывода об утечке |
| loadednull и явная причина | Неизвестность проверки; перенести reason/phase/child_rc, не False/True |
| Строка stage=loaded без loaded/schema/reason | Ошибка формата/переноса, не называть доказанным таймаутом |
| requestedon, effectiveblocked, inbound_problemtrue | Библиотека ожидает hold-block; причина TCP-отказа может быть локальной; сопоставить loaded/реальную политику |
| TPROXY IPv4 listener отсутствует при on | Порт не наблюдается как IPv4 LISTEN; кандидат локального отказа, не доказанный PID/TPROXY диагноз |
| proxy lookup вon local/loopback/tproxy | Модель policy lookup ведёт наlo, фактический проход пакета ещё не доказан |
| proxy lookup вon WAN/main при методеtproxy | Кандидат проблемы RPDB/маршрута, не разрешение менять route и не доказательство, что flow был помечен |
| proxy lookup вon unicast/tun/tun при методеtun | Ожидаемая модель host TUN; TPROXY listener оценивается отдельно дляLAN |
| Все mode/listener/lookup/loaded корректны, plainrefused | Причина не локализована этими данными; следующим отдельным опытом потребуется наблюдение конкретного flow |
| unmarked lookup WAN/main | Нормально до OUTPUT; не доказательство обходаVPN |
| guard_present=false | Запрос не подтвердил таблицу; не доказывает её отсутствие/утечку |
| guard_present=null | Запрос не получен; неизвестность, не отсутствие таблицы |
| plain не работает, marked работает, carrier1 | Пути различаются; причина в capture/маршруте/узле/цели требует атрибуции |
| Оба HTTPS не работают, carrier1 | Не доказательство выключенного Ethernet; учесть baseline/цель/фазы |
| prefix_ok32769 | Проверен префикс HTTP body, не всё тело, не все сайты и не WAN-egress |
| bytes=null, phaseunknown | Неизвестно, а не ноль/ошибка handshake |
| HEALTHY при off | Контроллер здоров; VPN этим не подтверждён |
| После rollback guard отсутствует | Для off это ожидаемо; не загружать guard вручную |
| xgw/xgw-net inactive сразу после rollback | Предусмотренная остановка писателей; R2 нужен отдельно |

plain может уйти direct по разрешённому исключению маршрутизации. Даже успешный prefix
не доказывает выход через VPN. DNS-on также не проверен: IP подготовлены заранее. Carrier
снимается в точках, непрерывного мониторинга здесь нет. HTTPS не доказывает работоспособность
канала модели, Tailscale, LAN или UDP. Их подтверждать отдельными фактами, иначе NOT_RUN.
Одного CDN/отказа пробы недостаточно для вывода «ТСПУ», «VPN упал» или «WAN отключён».

## 10. Отчёт и публикация

### F1. Подготовить черновик вне клона

Шаблон: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3g-TEMPLATE.md.
Заполнить `$HOME/xgw-w3g/report.md`. Для каждого выполненного гейта — фактическое значение,
источник/ID шага и категория; невыполненное NOT_RUN, неопределённое UNKNOWN/INCONCLUSIVE.
Не удалять строки шаблона для сокрытия незакрытых ворот. Не подставлять пример вместо числа.

Обязательно указать:
- дату/таймзону/модель/ОС/systemd, tested HEAD/tree, code SHA и2frozenSHA;
- scope согласия, исходные HEALTHY/off/pool/pin/ядра и installed identity;
- G1 old/new nft SHA, backup,4 installed совпадения, dry nft-c и фактический on guard_layout;
- отдельные timings25с preflight и25с enable-окна, total иrestore отдельно;
- enable CLI rc и sampler job rc раздельно, частичные on-frames/loaded/body-результаты;
- baseline ready иhealthy раздельно; target только номер, route plain/marked, phase/status/
  bytes/outcome/seconds; неизвестные значения сохранять;
- WAN facts bool/null, carrier в точках, фактическую связь владельца/модели и финальный off;
- все отклонения/указания владельца, выполненные отдельно от штатного ТЗ.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/нагрузка
остаются NOT_RUN. Волну3 целиком не закрывать. Отдельное наблюдение владельца о Tailscale
не заменяет испытание его трафика во время этого on-окна.

### F2. Проверить черновик перед Git

В Git только итоговый Markdown-отчёт. Не включать сырой snapshot/capture.json/off.nft,
probe-plan, URLs/IP/UUID/MAC/имена устройств и владельца/подписок, payload, job.log,
enable-cli.log, полный журнал и screenshots с такими данными. Допустимы labels WAN/LAN,
службы/UID xray/xgw-singbox, агрегаты, timings, версии и публичные Git-ссылки.
Наличие0 URI-patterns само по себе не является полной проверкой секретов.

Перечитать черновик: ожидаемые значения не выданы за факты, rc не смешаны, полная установка
из3d не названа тестом enable, нет утверждения «WAN никогда не падал» по двум frames.

### F3. Публикация только проверенного черновика

Только когда публикация отчёта разрешена действующим порядком владельца, выполнить один
приведённый блок обычным пользователем, без sudo. Он проверяет чистоту, FF и runtime identity,
вычисляет дату файла из начала этого прогона вMSK, копирует ТОЛЬКО Markdown-черновик,
проверяет состав индекса и делает обычный push безforce. Он не выполняет privacy-review
вместоF2. Если error/конфликт/auth-пауза — STOP, сохранить черновик, не обходить защиту Git.

```bash
python3 -I - <<'PY'
import os,subprocess
from datetime import datetime
from pathlib import Path
if os.geteuid()==0:
    raise SystemExit('STOP: publish выполнять обычным пользователем')
repo=Path.home()/'zcod/xgw'
notes=Path.home()/'xgw-w3g'
code='573b233bce881349e5ff4654600d3e077a9515f6'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3g-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3g — короткий enable')
git('push','origin','HEAD:freepool')
print('REPORT_PUBLISHED',relative,git('rev-parse','HEAD'))
PY
```

Нужен REPORT_PUBLISHED с фактическим путём и commit. Если commit создался, а push не прошёл,
не запускать весь блок заново и не делать новый commit: сообщить фактический локальный SHA
и сбой отправки, сохранить состояние. Не git add., не force, не reset и не чистка чужих файлов.
Для установления локального состояния после сбоя публикации разрешены только чтения:

```bash
git -C "$HOME/zcod/xgw" log -1 --format='%H %s'
```

```bash
git -C "$HOME/zcod/xgw" status --short
```

Финальное сообщение владельцу: что проверено/что осталось NOT_RUN, конечный режим и связь,
ссылка на реальный отчёт либо точная причина, почему публикация не состоялась.
