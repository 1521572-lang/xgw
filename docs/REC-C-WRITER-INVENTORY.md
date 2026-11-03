# REC-C: писатели поколения, первая инвентаризация и план внедрения fence


## Актуально после Z — lifetime admission AA (03.11.2026)

[Отчёт Z](TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-2026-11-03.md) проверен:
19/19, три realprocesscases/4children, command0, HEALTHY/on/pool/versions/связь сохранны.
Принят только cooperative sandboxscope, реальный fence/driver/activeflagsfalse.
Y/REC-B snapshot/check-only принят ранее; Y6/X26/W25/Z19 не повторять.

[Разбор Z](REVIEW-REAL-MACHINE-0.2.0-wave3z.md),
[аудит entrypoints и bootstrap](REC-C-CALLSITES-AND-BOOTSTRAP.md),
[ADR lifetime admission](ADR-REC-C-ADMISSION-LIFETIME.md),
[единое ТЗ AA](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aa.md).
AA22 новых cases/3child — только user-sandbox; реальный AA NOT_RUN до отчёта.

Уточнение прежнего долгого ownershiplock: вокруг systemctlrestart он создаёт риск
parent→ExecStartPost→xgwnettun→тотжеlock. Новый кандидат использует короткий registrylock
и durabletickets на lifetime writers. При непустом registry lease сразу отказывается,
без PENDING, orphanpruning и остановки служб. COMMITTING/UNKNOWN запрещают silentretirement.
Это не productintegration и не доказательство общего lockgraph.

Далее productregistry/entrypointadapters/outcomereceipts. Fake-only независимый REC-D
можно разрабатывать до Cinstallation, потому что он не меняет сеть; это уточняет старое
строго последовательное описание C→D. Реальный E требует принятия и C, и D, и bootstrap.
Установка C-ENTRY пока BLOCKED_BOOTSTRAP: нет независимого возврата исходных code/unit/on.
Nooff/install/G1/WAN/LAN/Tailscale/pin/pool/service/ruleschanges. ThinkCentreonly, workingLAN.
Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.

Ниже история предыдущих кандидатов; прежние NOT_RUN не отменяют принятые выше отчёты.


Актуально после Y1440d51: REC-B принята в snapshot/check-only scope, guard10/10 исправлен
только в тесте. Zпроверяет cooperative sandbox candidate/19cases/3processcases; реальные
writers ещё не интегрированы, fence NOT_INSTALLED. См. ADR-REC-C-OWNERSHIP и ReviewY.


Обновление после X283bb12: REC-B partial/guard contract bug. Исторический collector
ошибочно ожидал forward priority5 вместо source10. Новый Y v2 исправляет тест и
публикует safe guard observations; старый X/run неизменён, живые правила не менять.
Y объединяет6 новых guard cases и snapshot/check/after; реальная Y NOT_RUN. REC-B пока
не закрыт, переход к REC-C/D/E не выполнен. Подробно REVIEW-REAL-MACHINE-0.2.0-wave3x.md.


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

Уточнение имени: функция nft.py1154 называется delete, раннее remove было опиской.

## 5. Дополнительные прямые nft writers: scope и admission

Продолжение статического аудита, не исчерпывающий call graph и не реальное наблюдение.

| Путь | Scope | Следствие для будущего fence |
|---|---|---|
| [Backend._save_peers/_nft_element](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/freepool/backend.py#L152-L163) | peers.json и **host ip xgw/fp_peers**, TABLE=xgw | Прямые add/delete element обходят capture._load; включить в admission/generation publication |
| [Backend.prepare](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/freepool/backend.py#L172-L195) | запись peers и add element | Нужна граница между файлом поколения и kernel update; проверить cleanup при частичной ошибке |
| [Backend.stop/reconcile](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/freepool/backend.py#L281-L335) | delete/flush fp_peers плюс lifecycle | Режим pool off сам по себе не доказывает отсутствие этих writers; actual invocation в Y не устанавливалась |
| [nft.delete](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/nft.py#L1154-L1159) | capture+guard removal | Top-level down/uninstall paths должны получить явный admission; не обходить через cleanup |
| [usage.remove/_nft](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/usage.py#L250-L274) | отдельная **ip xgw_acct** (TABLE line44) | Не объявлять writer ip xgw только по наличию nft -f; сохранить чужой относительно snapshot scope |
| [agent._guard](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/freepool/agent.py#L752-L759) и [штатный unit](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/packaging/xgw-fp%40.service#L10-L16) | table xgwfp; штатный unit PrivateNetwork=yes | Различать host vs namespace; прямой CLI entry и зависимости peer generation ещё требуют аудита |

Snapshot Y содержит наблюдавшиеся fp_peers в kernel table, но не устанавливает исключение
будущих backend writes. Перед real replay fence обязан учитывать и file generation,
и host set operations. Не копировать Ysnapshot в Z: sandbox использует только synthetic g0/g1.
Zcooperative Store демонстрирует admission/commit под одним lock для synthetic record;
перенос permit наружу перед настоящим nft/API write запрещён контрактом.
Lock order/top-level call graph/bootstrap installation ещё не доказаны. Никакой автоматической
установки по sandbox PASS. Следующие product adapters требуют отдельного конкретного кода
и безопасной real-machine qualification с независимым возвратом исходного on.
