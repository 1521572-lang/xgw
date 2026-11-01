# ТЗ Flash: wave3e — один enable в автономном окне25с

## 1. Цель, пределы и идентичность

Это исполняемый протокол для GLM-5.3-Flash/ZCode с терминалом и зрением на ThinkCentre
Ubuntu24.04.5/systemd255. Прочитать целиком ДО начала команд. Выполнять только эту версию ТЗ.

Отчёт wave3d b7be627 подтвердил автономные off-окна и отдельную установку по прямой команде
владельца с rc0. Установленный продукт уже готов; повторная установка здесь не выполняется.
Нужно получить ограниченное наблюдение: один enable, локальные frames и HTTPS-пробы во время
on, затем ОБЯЗАТЕЛЬНЫЙ возврат в исходный off через25с. Волна3 этим целиком не закрывается.
От модели внутри on-окна не требуются подтверждения или сетевые действия. Указанное
локальное ожидание sleep35 разрешено; разрыв связи с моделью не отменяет таймер.

Код инструментов: **1d62fadfc0464912dec3142352cd285718be5e6a**.
Продуктовый src/packaging/config не менялся относительно2862767.

| Frozen файл | SHA256 |
|---|---|
| wave3_safety.py | c72f8078a869c04d19e39f17938f8f77b2164f7859f271b19baae276b31ce93b |
| wave3_enable_probe.py | 903f7f3f3ee99ad9ffe560d412e42ad3bbe2569ada238ef4abf55b42821c3feb |

Версию определять по Git SHA и SHA256, а не по имени/старому заголовку файла. Локально прошли
6 новых узких регрессий иruff. Реальные новые units/HTTPS/on wave3e первоначально NOT_RUN.

### 1.1. Что делает каждый участник

| Участник | Роль | Ожидаемое поведение |
|---|---|---|
| Flash | Проверяет гейты, запускает одну команду, читает сохранённый результат | Команд внутри on-окна от неё не требуется |
| xgw-w3e-safety.service | Отдельный локальный guardian, вне job-cgroup | Через25с всегда восстанавливает off, включая случай успешного enable |
| xgw-w3e-job.service | Отслеживаемый job с sampler | Один enable и сбор агрегатов; при rollback вся группа прекращается |
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
6. Все заметки/черновик до публикации хранить в `$HOME/xgw-w3e`, не в клоне. Runtime snapshot
   и журналы остаются root0700 в `/run/xgw-w3e`. Не переносить из них сырые данные в Git.
7. Публикуемые значения брать только из этого прогона. Ориентиры/примеры ТЗ и измерения
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
context/prepare/facts/window/launch/report; единственный enable внутри tracked job; подготовленный
off-rollback и старт xgw после подтверждённого восстановления.

### 2.2. Согласие и исходная ситуация

До подготовки опасных шагов проверить действующее согласие владельца именно на:
- один краткий enable, возможный обрыв прежних direct-сессий и связи модели;
- GET к уже настроенным probe.url/первому probe.urls с чтением префикса тела;
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
| S2: source + installed identity, HEALTHY/off/pool off | S3: заморозка2файлов |
| S3: обе SHA/owner/mode и read-only job-context корректны | P1: подготовка off-preflight |
| P1: snapshot готов, WAN facts известны и совпали | P2: off-window25с |
| P2: RESTORED_OFF/nft0/timing/WAN/связь подтверждены | P3: старт контроллера |
| P3: снова HEALTHY/off | B1: новый snapshot enable и baseline HTTPS |
| B1: готовы цель и измеренная база, нет критических ошибок worker | E1: один launch enable |
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
root=Path.home()/'xgw-w3e'
root.mkdir(mode=0o700,exist_ok=False)
stamp=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
(root/'run-start.txt').write_text(stamp+'\n')
print('NOTES_CREATED',stamp)
PY
```

Каталог уже существует — STOP, не удалять/перезаписывать. После NOTES_CREATED:

```bash
sudo -v
```

При запросе пароля дать владельцу ввести его в настоящий sudo-prompt. Не угадывать пароль,
не помещать его в команду/заметки/Git. Дождаться успешного завершения. После этого записать
согласие из§2.2 и исходные сведения в `$HOME/xgw-w3e/notes.md`.

### S2.1. Обновить только чистую freepool

```bash
cd "$HOME/zcod/xgw" && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 1d62fadfc0464912dec3142352cd285718be5e6a HEAD && git diff --exit-code 1d62fadfc0464912dec3142352cd285718be5e6a HEAD -- src packaging tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py config.example.toml pyproject.toml && git diff --exit-code 28627675218f322185de11d0b569bca531d36aed HEAD -- src packaging config.example.toml pyproject.toml && git rev-parse HEAD && git rev-parse 'HEAD^{tree}' && printf 'SOURCE_PREFLIGHT_OK\n'
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
for wave in ('b','c','d'):
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
Скрипт завершается0 только после проверки всех шести; это отличается от единичного
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

Нужны три True и INSTALLED_SOURCE_OK. Несовпадение — STOP, не запускать install: новый
enable-прогон не предназначен для восстановления/обновления продукта.

### S3.1. Создать frozen-копии

```bash
cd "$HOME/zcod/xgw" && test ! -e /run/xgw-w3e && sudo install -d -m 700 /run/xgw-w3e && sudo install -m 700 tests/stand/wave3_safety.py tests/stand/wave3_enable_probe.py /run/xgw-w3e/ && printf 'FROZEN_COPY_CREATED\n'
```

Нужен FROZEN_COPY_CREATED. Существующий каталог/ошибка — STOP, ничего не удалять/переписывать.
Имена обоих файлов сохранять. Переименование guardian в safety.py сломает импорт sampler.

### S3.2. Проверить обе SHA и права ДО запуска кода

```bash
sudo python3 -I - <<'PY'
import hashlib,stat
from pathlib import Path
root=Path('/run/xgw-w3e')
expected={
 'wave3_safety.py':'c72f8078a869c04d19e39f17938f8f77b2164f7859f271b19baae276b31ce93b',
 'wave3_enable_probe.py':'903f7f3f3ee99ad9ffe560d412e42ad3bbe2569ada238ef4abf55b42821c3feb',
}
items=[root]+[root/name for name in expected]
ok=True
for path in items:
    info=path.stat()
    safe=info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700
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
sudo systemd-run --unit=xgw-w3e-job --wait --pipe --collect --property=RuntimeMaxSec=10 --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3e/wave3_enable_probe.py context /run/xgw-w3e
```

Это только чтение: mode=context не вызывает enable, не читает HTTP и не меняет правила.
Нужен JSON tracked_job_context=true/euid_root=true и успешное завершение процесса. Одна
строка systemd «запущено» не заменяет этот результат. Команда ограничена RuntimeMaxSec10с;
неожиданный timeout/exitне0/false — STOP, не отключать cgroup-проверку.

```bash
systemctl is-active xgw-w3e-job.service
```

После context ожидается inactive/not-found (exitне0). Active/activating/deactivating —
STOP. Применение wait/pipe/collect соответствует
[systemd-run255](https://www.freedesktop.org/software/systemd/man/255/systemd-run.html):
ожидаем завершения диагностического процесса и получаем его stdout; scope/user не использовать.
Новый реальный job позже всё равно повторно проверит свой контекст и active safety-window.

## 5. P1–P3: обязательный автономный off-preflight

### P1.1. Подготовить snapshot, не запуская окно

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py prepare /run/xgw-w3e/offcheck
```

Ожидается PREPARED. Команда проверяет existing unit, явный off/pool off, исходную политику
и nft -c, сохраняет boot ID, snapshot и fingerprints. PREPARED означает только подготовку:
таймер ещё НЕ работает. Ошибка/Traceback — STOP, никаких последующих сетевых команд.

### P1.2. Проверить полноту WAN evidence

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py facts /run/xgw-w3e/offcheck
```

Нужны all_verified=true и все шесть WAN_unchanged=true: profile, addresses,
live_gateway_dns, route4, route6, mtu. False означает изменение; null — замер недоступен.
Ни false, ни null не считать совпадением. STOP, без «переснимем до получения True».
DHCP/RA могли обновиться самостоятельно; несовпадение не доказывает вину XGW.

### P2.1. Запустить независимое окно при уже off

```bash
sudo systemd-run --unit=xgw-w3e-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3e/wave3_safety.py window /run/xgw-w3e/offcheck 25
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
sudo python3 -I /run/xgw-w3e/wave3_safety.py status /run/xgw-w3e/offcheck
```

Нужны state=RESTORED_OFF, nft_rc=0, seconds_since_last_pulse в ориентире25–30с и
recovery_seconds≤5с. Здесь seconds_since_last_pulse — всё время от начала фиксированного
окна: pulse не было. recovery_seconds исключает ожидание. Время чтения экрана/sleep35
не подменяет эти измерения. stop/kill rc могут быть ненулевыми из-за отсутствующего job.

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py observe /run/xgw-w3e/offcheck
```

Нужны capture_enabled=false, WAN/LAN operstateup/carrier1.

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py facts /run/xgw-w3e/offcheck
```

Нужны all_verified=true и все поля true. Владелец/модель остаются на связи.
FAILED_*, restoring спустя окно, nft_rcне0, total>30с, проблема связи/неизвестный WAN fact —
STOP; B1/E1 NOT_RUN. Не запускать следующий опыт, даже если сам xgw выглядит HEALTHY.

### P3.1. Вернуть контроллер после доказанного off

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
sudo python3 -I /run/xgw-w3e/wave3_safety.py prepare /run/xgw-w3e/enable
```

Ожидается PREPARED. Это новый case с текущим off после P3, не повторение on-опыта.

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py facts /run/xgw-w3e/enable
```

Все true/all_verified=true. Иначе STOP.

### B1.2. Измерить HTTPS без включения VPN

```bash
sudo python3 -I /run/xgw-w3e/wave3_enable_probe.py baseline /run/xgw-w3e/enable
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
публичная цель и измеренная база; второй — что обе off-пробы дочитали префикс. При ready=false
STOP. Если все результаты worker_deadline_or_error/неизвестны, тоже STOP: сравнивать нечего.
При ready=true, известной фазе хотя бы части измерений и healthy=false опыт разрешён под
тем же таймером: off-body уже мог быть заблокирован. Ограничение отметить в отчёте.
Не подбирать новые URL, не отключать TLS verification, не увеличивать таймауты/пороги.

База действительна5мин и связана с SHA sampler/boot ID. Между B1.2 и E1 не обсуждать новые
настройки и не редактировать файлы. Просрочка/изменение файла приводит к отказу до enable;
не обходить это новым timestamp/каталогом. Согласие владельца должно уже действовать.

## 7. E1: единственный enable

### E1.1. Финальная проверка перехода

До следующей команды модель должна иметь в заметках:
- согласие§2.2, source/frozen identity, installed-source×3 true;
- успешный off-preflight с локальными timings и живой связью;
- текущий HEALTHY/off/pool off после P3;
- PREPARED нового case, WAN all_verified=true, измеренную свежую baseline;
- понимание, что после launch вмешательство модели внутри окна не требуется.

Нет хотя бы одного факта — E1 NOT_RUN. Исторический PASS другого запуска не заменяет гейт.

### E1.2. Одна команда локального старта

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py launch /run/xgw-w3e/enable enable "$HOME/zcod/xgw"
```

Ожидаемый смысл ответа: started=enable, fixed_window_seconds25, rollback=always_off,
pulse_required=false. Это подтверждение запуска, не PASS VPN и не доказательство, что
он до сих пор on к моменту чтения экрана. Внутри local launch сначала создаётся guardian,
проверяются armed/active, затем запускается tracked job. Sampler дополнительно проверяет
свою job-cgroup, актуальное fixed-window и свежую неизменённую baseline.

Сам sampler делает один xgw enable, записывает его rc отдельно, снимает on-frames,
Capture.loaded с пределом6с и plain/marked HTTPS. Достаточность25с для полного сбора не
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
sudo python3 -I /run/xgw-w3e/wave3_safety.py status /run/xgw-w3e/enable
```

Отдельно записать state/nft_rc/stop_rc/kill_rc/seconds_since_last_pulse/recovery_seconds,
а также job-result.state/rc, если он есть. Нужны RESTORED_OFF, nft_rc0 и total≤30с.

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py observe /run/xgw-w3e/enable
```

Нужны capture_enabled=false, linksup/carrier1.

```bash
sudo python3 -I /run/xgw-w3e/wave3_safety.py facts /run/xgw-w3e/enable
```

Нужны все WAN facts true. False/null записать как изменение/неизвестность, не округлять.
Подтвердить, что владелец и модель на связи; прежнюю недоступность тоже отметить, если была.
Успешное чтение ПОСЛЕ rollback не доказывает непрерывную связь модели ВНУТРИ окна. Если её
не наблюдали отдельно, записать: during_on=UNKNOWN, after_off=подтверждено.

### R1.3. Прочитать автономный сбор

```bash
sudo python3 -I /run/xgw-w3e/wave3_enable_probe.py report /run/xgw-w3e/enable
```

Ожидаемые категории: baseline.json, enable-result.json, on-observations.json.
Отсутствие категории/поля — NOT_RUN/UNKNOWN, не восстановить его предположением. Порядок
событий: before_enable → after_enable → loaded → HTTPS plain/marked → after_https.
Если job остановлен таймером, более поздние события могут отсутствовать — это ожидаемое
ограничение сбора, не повод повторить enable. Raw job.log/enable-cli.log не открывать/не печатать.

Для сохранения только безопасных агрегатов разрешено (после окна):

```bash
(umask 077; sudo python3 -I /run/xgw-w3e/wave3_enable_probe.py report /run/xgw-w3e/enable > "$HOME/xgw-w3e/measurements.jsonl")
```

Проверить, что файл не пуст, и использовать его вместе с заметками. Это не автоматический
готовый отчёт и не подтверждение полноты всех событий.

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
| after_enable capture=true, guard=true, loaded=true, plain prefix_ok | Один успешный короткий host-кейс по действующей политике |
| loaded=false | Фактическая проверка соответствия политики не прошла; расследовать, без вывода об утечке |
| loaded UNKNOWN/null/нет поля | Проверка не завершена/не получена; INCONCLUSIVE, не False/True |
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

Шаблон: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3e-TEMPLATE.md.
Заполнить `$HOME/xgw-w3e/report.md`. Для каждого выполненного гейта — фактическое значение,
источник/ID шага и категория; невыполненное NOT_RUN, неопределённое UNKNOWN/INCONCLUSIVE.
Не удалять строки шаблона для сокрытия незакрытых ворот. Не подставлять пример вместо числа.

Обязательно указать:
- дату/таймзону/модель/ОС/systemd, tested HEAD/tree, code SHA и2frozenSHA;
- scope согласия, исходные HEALTHY/off/pool/pin/ядра и installed identity;
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
notes=Path.home()/'xgw-w3e'
code='1d62fadfc0464912dec3142352cd285718be5e6a'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3e-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3e — короткий enable')
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
