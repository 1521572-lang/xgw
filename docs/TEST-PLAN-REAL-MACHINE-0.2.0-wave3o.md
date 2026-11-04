# ТЗ Flash: wave3o — разбор SB-1 из wave3n, только сохранённые данные

## 1. Факт и цель

Отчёт wave3n e4f6f2d2f8ae8cf6148a624f5231c4107bd7f225: BRIDGE_PROBES_RECORDED/rc3,
не общий PASS. SB-1(vless/d) на двух целях далcurl97/HTTP0/bytes0 за1.599/0.709с;
SB-2(vless/d) передал206/32769байт за0.372с, TLS/body/ownedlistener подтверждены.
On/caps/PID6/settings/SBconfig/pinrecord сохранены. Принята положительная совместимость
только SB-2; SB-1 остаётся отрицательным случаем с неизвестной причиной.

Успех SB-2 исключает глобальную неспособность процесса передать HTTPS, но НЕ исключает
специфическую проблему SB-1 в настройках, маршруте, правах или upstream. Curl97 означает
ошибку proxy handshake, без точной причины. [Официальные коды libcurl](https://curl.se/libcurl/c/libcurl-errors.html).
TLS_verify_result0 при HTTP0/bytes0 не доказывает, что TLS целевого HTTPS вообще начался.
71 кандидат выбирался по fingerprint, не по health; SB-1 мог быть уже неработоспособен.
Не объявлять его причиной ТСПУ/падение сервера/дефект изоляции без дальнейших фактов.

Задача: использовать существующий root600 summary N, ограниченный journal за его реальное
окно, текущие безопасные признаки конфигурации и последний сохранённый scan. Не повторять
N/GET, не искать другой успешный узел ради PASS. Никаких новых соединений на этом этапе.
Существующая рабочая схема XGW → роутер → устройства, HEALTHY/on сохраняется.

Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7, runtime/службы не устанавливаются.
Доставка Git/freepool, HEAD/tree записать. Заморозка только3тестовых файлов:
- wave3_bridge_diagnostic.py SHA256 e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068;
- wave3_bridge_probe.py SHA256 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef (не изменён, используется как библиотека);
- wave3_on_observer.py SHA256 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 (не изменён).

## 2. Разрешённые эффекты и STOP

Разрешено чтение config/proc/sys/nft/systemctl, старого /run/xgw-w3n summary/helper,
SQLite mode=ro фиксированными SELECT (nodes/scans/pin), одного ограниченного journal
за окно N±2с. Никакого Store/DDL/DML/rescan. Root700/600 файлы только теста в/run/xgw-w3o.
При сопоставимой исторической конфигурации создаётся закрытый mapping-private.json
с отпечатками/контрольными хешами для будущего точного исследования; паролей/URL в нём нет.
Он не публикуется. Сырой journal/config/curlstderr не сохраняется новым сборщиком.

Запрещены любые GET/curl/SOCKS-connect/DNS/ping/SSH/новые listeners/перескан серверов,
повторN/смена выбранных71кандидатов, coreAPIwrites, pin/unpin/ротация/исключение узла,
enable/disable/install/apply/net updown/restart/reload/kill служб, nft/ip/NM/sysctl/
WAN/LAN/Tailscale/pool/configchanges, старые permission/safety/fault helpers/rollback-off.
Не увеличивать loglevel и не перезапускать SB для получения более подробного журнала.
Не чинить гипотезу о причине до фактического отчёта.

Нет исходного on — WAIT_OWNER_ON/STOP, модель не включает его. Нет старого Nsummary/
замороженного helper — BLOCKED_HISTORICAL_EVIDENCE; не создавать их заново и не копировать
текущий summary вместо старого. Нет совпадения источников/дат — UNKNOWN, а не новая попытка.
Ошибки останавливают только проверку. VPN/службы остаются в текущем состоянии, не off.
Recovery-таймер не запускается: тест сеть не меняет, связь модели не является механизмом
восстановления. При обрыве после возвращения связи show/отчёт, не повторrun.

Одна команда/целый блок на шаг. Не вводить следующий код в sudo prompt. В Git/чат только
summary нового helper и обезличенный текст; не выводить rawNsummary, sourceconfig, journal,
DBrow/error, IP/MAC/UUID/fingerprints/outboundtag/порты/имена/SNI/пароли/URL/PID/NIC.
Ни вручную, ни «посмотреть один пример строки». Даже старый stderr curl не публиковать.
N-helper stderr детально не сохранял: его отсутствие нельзя исправить повторным запросом.

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
root=Path.home()/'xgw-w3o'
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
После успеха записать разрешённые эффекты из раздела 2 и исходные сведения в `$HOME/xgw-w3o/notes.md`.

### S1.3. Записать версию nft

```bash
nft --version
```

Нужны exit0 и строка версии; записать буквально в отчёт, не предполагать версию по Ubuntu.
Не обновлять nft/libnftables ради прогона. Отсутствующая команда — STOP до проверок.

## 4. S2: исходный on и точная идентичность

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

## 5. P1: заморозить только библиотеки/сборщик

### P1.1. Однократная подготовка трёх файлов

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,os,sys
from pathlib import Path
repo=Path(sys.argv[1])
expected={'wave3_bridge_diagnostic.py':'e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068',
          'wave3_bridge_probe.py':'2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef',
          'wave3_on_observer.py':'0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46'}
payload={name:(repo/'tests/stand'/name).read_bytes() for name in expected}
if any(hashlib.sha256(payload[name]).hexdigest()!=sha for name,sha in expected.items()):
    raise SystemExit('STOP_HELPER_SOURCE_SHA')
root=Path('/run/xgw-w3o')
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
print('READ_DIAGNOSTIC_FROZEN',expected)
PY
```

Нужен READ_DIAGNOSTIC_FROZEN/exit0/3SHA. Уже существующий каталог/неполная подготовка —
STOP, не удалять/переименовывать/создавать другой каталог ради результата. В/opt/systemd
ничего не копируется. Старый /run/xgw-w3n не трогать; его source/summary только читаются.
CLI bridge_probe/observer не запускать — только новый diagnostic.

## 6. D1: один read-only разбор

### D1.1. Выполнить один раз

```bash
sudo -n python3 -I /run/xgw-w3o/wave3_bridge_diagnostic.py run
```

Нужен READ_DIAGNOSTIC_RECORDED/exit0: сохранён диагностический отчёт при подтверждённом
историческом Nsummary и рабочем on. Это НЕ PASS SB-1, не исправление и не доказанная причина.
STOP_READ_DIAGNOSTIC/exit3 — частичные данные/нет исторического материала; не повторrun.
Проверить каждое поле отдельно, не считать marker достаточным для классификации причины.

Сборщик проверяет owner/mode старых N-файлов, SHA фактического frozen Nhelper и специфическую
форму результата (71/2кандидата,2цели, SB-1две97, SB-2один206/32769). Берёт реальное окно
из before/after JSON, а не грубые15:40–15:46 из текстового отчёта. Ретроспективный journal
ограничен этим окном±2с,2001строкой/3с; анализируются максимум2000строк. Фразы/адреса
никогда не выводятся, только counts/enums. Может быть0строк, timeout, truncation/parseerror.

Исходный N не сохранил выбранные fingerprints/configSHA/PID как отдельный privateplan.
Поэтому O допускает сопоставление SB-1/SB-2 только когда время/часы согласованы, mtime И
ctime текущего SBconfig предшествуют N, число кандидатов71 и первые2vless/d совпадают
со структурой старого алгоритма. Метка FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN — поддержка
временами файла, не криптографически сохранённый исторический hash. Указать это ограничение.
Если условия не выполнены — historical_mappingUNCONFIRMED, caseattrs/scans/relatedlogs
NOT_RUN. Общие counts journal можно получить, но не приписывать SB-1.

Endpoint summary — безопасные признаки ТЕКУЩЕЙ конфигурации: protocol/transport/flow,
TLS/reality/uTLS/mux, наличие detour/bind, класс server/port, число и globalbool статических
hosts. Это не пакетная трасса/подтверждение DNS или фактической загрузки всех полей процессом.
Ничего не менять по одному флагу: private endpoint/bind/reality не являются сами по себе ошибкой.

Latest_persisted_scan — только текущая последняя строка, без rawerror. Поле relation_to_N
обязательно: before/during/after. Scan после N НЕ доказывает, что узел был мёртв до N.
Scanbefore с большим age может быть устаревшим. Даже ранний CONNECT_FAIL не устанавливает
внешнюю причину: мог отказать адрес пробы/конфиг/другой путь. Новые сканы не запускаются.

### D1.2. Прочитать только новую сводку

```bash
sudo -n python3 -I /run/xgw-w3o/wave3_bridge_diagnostic.py show
```

Show можно повторить для отчёта; run нельзя. Не cat mapping-private.json/старый Nsummary,
не открывать journal вручную для вставки в чат. Если summary отсутствует, ранний STOP/ошибка
в отчёт, не пересоздавать опыт. Неполные данные остаются UNKNOWN, а не PASS/«ошибок нет».

### D1.3. Конечный пользовательский статус

```bash
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
```

Ожидаются HEALTHY/on/прежние версии. Иное — зафиксировать без переключений/перезапуска.

### D1.4. Конечный режим пула

```bash
sudo xgw pool | head -1
```

Текущий выбор сохраняется, не навязывать off. Pin/Tailscale не менять.

### D1.5. Матрица выводов

| Данные | Допустимый вывод |
|---|---|
| READ_DIAGNOSTIC_RECORDED | Записаны данные; SB-1 не объявляется починенным |
| historical_mappingUNCONFIRMED | Нет надёжного соответствия случаев; не пересчитывать first2 как прежние |
| FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN | Условное сопоставление с явно указанным основанием и пределом |
| related.matched_rows/categorycounts | Теги и окно связаны с кандидатом, не обязательно с конкретным curl-сеансом |
| permission/timeout/DNS/refused/TLS-auth-handshake/reset categories | Совпадения слов; категории пересекаются и возможны в неошибочных сообщениях |
| global_categories без related | Не приписывать SB-1 или SB-2 |
| journal queryfalse/truncated/parseerrors | Неполное покрытие, zero counts не отсутствие причины |
| rows0/matched0 при queryok | Нет соответствующих сохранённых строк; причина остаётся неизвестной |
| scanrelationafter | Позднее состояние, не прошлый факт |
| attrs отличаются SB1/SB2 | Кандидат для следующей узкой гипотезы, не доказанная причинность |
| Context/settings/SBconfig/PID/boot/pin поменялись | Смешанный контекст, сохранить факт и остановиться без восстановления настроек |

Сборщик сравнивает текущие before/after on/caps/6PID/settings3/SBconfig/boot/pin;
отсутствующее/false не подменять предыдущим отчётом. Нет active requests, значит O не
повторяет тест N и не проверяет исправление. Из одного вывода нельзя получить E4/полный
VPN-egress/LAN UDP/IPv6/DNS/Tailscale/fault/D1-on PASS. Полнаяwave3 остаётся открытой.

## 7. Обезличенный отчёт

Скопировать docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-TEMPLATE.md редактором в
`$HOME/xgw-w3o/report.md`. Включить HEAD/tree/codepin/installed4/3SHA/mode, marker/rc,
historicalвалидность/окно/маппинг/ограничения, все journalcounts/coverage, безопасные attrs
и scans relation/age, currentcontext/pinreadable/unchanged, STOP/UNKNOWN/отклонения.
Отдельно: наблюдение → гипотеза → чего не хватает для её проверки. Не назначать причину
автоматически и не чинить/удалять/ротировать сервер. Не переносить rawrows/URI/адреса/
имена/ключи/SNI/пароли/порты/fingerprints/privateplan/hash/скриншоты в Git.
Прочитать черновик. Рабочий on в конце сохраняется, никакого off-rollback.

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
notes=Path.home()/'xgw-w3o'
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
relative='docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-'+stamp.date().isoformat()+'.md'
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
git('commit','-m','Отчёт: XGW 0.2.0, wave3o — разбор частичного результата wave3n')
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
