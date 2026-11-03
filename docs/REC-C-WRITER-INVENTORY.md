# REC-C: писатели поколения, первая инвентаризация и план внедрения fence

Статус03.11.2026: анализ исходников, **writer fence NOT_IMPLEMENTED**. Это не полный
доказанный call graph и не разрешение остановить службы. Исходники по product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7. Тестовый X не меняет ни один из этих путей.

## 1. Что необходимо защищать

Возврат capture table зависит от фактических capture/settings, bridge/config generation,
маркеров Tailscale, выбранных core/freepool peers, RPDB и процессов. Совпавшие файловые
digest в двух точках не исключают промежуточный writer и live API changes.
Fence должен охватывать **всех писателей разрешённого scope**, а не только одного job.
Старый снимок не должен перезаписать законное новое поколение. Отключать нормальную
работу шлюза и применять этот механизм в X нельзя.

## 2. Подтверждённые исходниками пути

| Путь | Что пишет/делает | Существующая сериализация и пробел |
|---|---|---|
| [Capture._save](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L185-L192) | capture.json | Атомарный файл, но сам по себе не общий fence |
| [Capture._load](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L447-L520) | routes, nft, forwarding/sysctl, baseline | Вызывается через net.lock-пути; внутри может иметь несколько nft apply |
| [up/enable/disable/open/close/down](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L748-L805) | режим, правила, markers, маршруты | net.lock с ожиданием30с; это не ownership generation |
| [Tailscale runtime markers/sets](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L682-L742) | tailscale-direct/via-vpn, nft elements | Часть проверки marker выполняется до net.lock; учитывать TOCTOU |
| [restore_tun](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L656-L680) | TUN и маршруты после запуска ядра | Отдельный lifecycle-путь, вне первого IPv4 capture fault scope; не игнорировать при расширении |
| [nft.apply](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/nft.py#L1131-L1164) | capture+guard транзакция | Базовая точка применения, но caller serialization не равна fence всех config writers |
| [daemon capture maintenance](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/daemon.py#L2036-L2158) | автоматический open/close/up/reapply | Работает без следующей команды модели; нельзя считать UI idle quiescence |
| [daemon apply path](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/daemon.py#L2381-L2415) | config/API generation | Проследить до конкретного applier и reapply capture; не ограничиваться файловыми hashes |
| [Xray Applier](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/applier.py#L97-L159) | files/API/pending/restart | apply.lock; это другой lock, не net.lock |
| [Xray install/rollback/API-dirty](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/applier.py#L209-L251) | last-good/current/API-dirty | Нужен учёт error/rollback ветвей, не только успешного install |
| [Singbox apply/install/rollback](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/singbox.py#L112-L216) | SB current/pending/last-good/reload | apply.lock; equal config не переписывает current, но может убрать pending |
| [managed._update](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/managed.py#L63-L92) | panel.json, node/core/pool/TS policy | Собственный .panel.json.lock/10с; не общий fence с kernel generation |
| [CLI network actions](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/cli.py#L640-L697) | enable/disable/net/TUN | Независимые entry points, должны получать тот же admission decision |
| [installer pause/resume](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/install.py#L683-L707) | daemon lifecycle | Сам installer и его config/unit writes не входят в узкий capture-only scope |
| [xgw-net unit](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/packaging/xgw-net.service#L15-L24) | boot/reload net up | oneshot+RemainAfterExit; active/exited с MainPID0 нормален, не «пропавший процесс» |

Это кандидаты для аудита, а не утверждение, что текущие callbacks исчерпаны. Панель/бот/
core update/freepool namespace/backend и прямые cmd runners требуют отдельного обхода
call sites перед product patch. Live Xray API membership нельзя аттестовать файлами.

## 3. Атомарные задания без установки на работающий шлюз

**C1. Контракт владения.** Описать ресурс generation, run identity, acquisition deadline,
publication и retirement. Указать общий порядок net.lock/apply.lock/panel lock и
доказать отсутствие нового deadlock. Не помещать driver в30-секундное ожидание net.lock.
Unknown writer path оставляет BLOCKED_WRITER_FENCE, не «остальные, наверное, не пишут».

**C2. Аудит call sites.** Для каждого писателя: read-before-lock, admission point,
atomic commit boundary, rollback/finally, process crash, stale lease и повторный вход.
Результат — кодовые ссылки и тесты конкретных гонок. Lock файла не равен lock inode
атомарно заменяемого файла; брать отдельный стабильный lock resource.

**C3. Изолированный кандидат.** Добавить participation adapter сначала с подставными
writers/drivers. Все реальные gates false до интеграции. Не прятать bypass в environment,
uid/root или выборе профиля. Deadline нельзя продлить heartbeat либо новым каталогом.
Синтетический PASS не доказывает quiescence работающего демона.

**C4. Bootstrap.** Установка нового fence на единственный работающий шлюз сама может
затронуть lifecycle. Подготовить конкретный путь и независимый возврат исходного on до
такой установки. Не решать циклическую зависимость запуском старого always_off, остановкой
XGW вручную или ожиданием следующей команды Flash при отсутствии интернета.

**C5. Реальная квалификация.** После конкретного кода и bootstrap-плана — один подробный
пакет на ThinkCentre, сначала безопасные dry adapters. Не расширять scope на D1-on,
WAN/TS/core faults автоматически. Только затем независимый driver и ограниченный fault
по REC-D/E. Текущий X выполняет только REC-B и не запускает C1–C5 в живой системе.

## 4. Что хранится после X

Приватный материал X — кандидат snapshot, не эксклюзивное владение поколением.
Manifest status PLANNED_NOT_ARMED, fence/driver/active gates=false. Kernel check0 лишь
проверяет проект в текущем контексте, не реальный replay и не случай отсутствующей таблицы.
По результату X исправлять конкретный дефект снимка/парсера, если он появится;
при успешном scope продолжать C1/C2, не возвращаться к TLS/cache/journal микропрогонам.
