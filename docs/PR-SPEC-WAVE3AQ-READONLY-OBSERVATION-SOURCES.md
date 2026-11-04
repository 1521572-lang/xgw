# ТЗ AQ: readonly-источники наблюдений, provenance и единый пакет квалификации

Обновление04.11.2026: готов source candidate и единый [TEST-PLAN AQ91](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aq.md).
[API/schema](API-CONTRACT-WAVE3AQ.md), [96exact anchors/65surfaces](RESOURCE-SOURCES-WAVE3AQ.md),
[ADR](ADR-REC-C-AQ-READONLY-EVIDENCE.md).39narrow+2frozenloader/checkpoint PASS, full91/realAQ NOT_RUN.
Реализованы AQ-1 types/strict schema/session ownership, AQ-2 wire parsers и unwired bounded
query/proc/profile candidate, AQ-3 FIXTURE scoped comparison/AP boundary preservation,
AQ-4 offline lifecycle/guard/private partial, AQ-5 новые проверки, AQ-6 готовый offline пакет.
Actual host issuer/proc mount/executable/permissions/installed formats qualification НЕ закрыты;
host branch BLOCKED_SCOPE_REVIEW/HOST_NOT_RUN. Включить её флагом/обходом guard нельзя.
Нет runtime wiring/install/сети;all7gatesfalse/LiveCBLOCKED_BOOTSTRAP. Ниже исходное ТЗ;
его SPEC_ONLY относится к состоянию на момент постановки, не к готовому offline пакету.

Дата: 04.11.2026. Исполнитель первого этапа — модель-разработчик. Исполнитель будущего
реального прогона — Flash на ThinkCentre. Статус документа: **SPEC_ONLY / NOT_IMPLEMENTED / NOT_RUN**.
Это новое задание, а не предложение повторить AP211. Не начинать исполнение с запуска
старого AP/AM или с инвентаризации рабочей машины.

## 1. Результат одного захода

Реализовать максимальный законченный пакет AQ-1…AQ-6: ограниченные источники наблюдений,
строгие декодеры, привязку происхождения, сравнение объявленного подмножества ресурсов,
интеграцию без активации и полностью готовую передачу Flash. Разработчик доводит пакет
до reviewable состояния самостоятельно, включая исправления найденных narrow-проверками
дефектов. Число тестов определяется новыми ветвями и инвариантами. Превышение211/852,
раздувание комбинаций и повтор прежних партий не являются целями.

База: `origin/freepool`, проверенная от
`dec68ab48add3fda328d4de52b67feecd4049e8a` fast-forward. На ней124 source-файла;
installed runtime не обновлялся. Если свежий HEAD содержит новый отчёт или код, сначала
проверить diff и совместимость; не сбрасывать ветку и не подменять baseline молча.
Рабочее дерево с посторонними изменениями сохранить; не включать их в коммиты AQ.

Основание: [приёмка AP211](REVIEW-REAL-MACHINE-0.2.0-wave3ap.md),
[API AP](API-CONTRACT-WAVE3AP.md), [resource table AP](RESOURCE-TABLE-WAVE3AP.md),
[ADR AP](ADR-REC-C-AP-RESOURCE-CONTRACTS.md). AP211 принят только для симуляции и dry-run.
Все65 контрактов каталога имеют completeness=UNKNOWN и требуют7 domains.
Simulation MATCH не является runtime Verification. Эти ограничения сохранить.

Готовый результат AQ должен впервые различать «JSON/fixture заявляет факт» и
«конкретный разрешённый источник прочитан данным collector в данном контексте».
Даже второе ещё не доказывает полноту global graph или безопасность активации.

## 2. Граница разрешённой работы

Сейчас разрешены изменения source/tests/docs, узкие локальные проверки и публикация
через Git FF. Это ТЗ само по себе **не разрешает запуск новых host/kernel/API collectors
на ThinkCentre**: AP их не разрешал. Сначала реализовать и зафиксировать точный протокол
в новом TEST-PLAN. Его scope должен быть отдельно проверен перед реальным запуском.
Не выдавать за READY недописанный runner, placeholder или описание будущего поведения.

Рабочая раздача через LAN считается работающей; ThinkCentre HEALTHY/on. Доступен только
ThinkCentre, отдельного LAN-клиента нет. Не запрашивать его. Не трогать входящий адаптер,
исходящий адаптер, WAN/LAN/Tailscale, адреса/маршруты/правила, pin/pool/config/services.
Запрещены install/uninstall/off/on, G1, новые SSH inventories, API writes, новые
units/timers/guardian, arm/fault/replay и любые операции восстановления на рабочей машине.
Запрещён always_off. Independent original-on/code/unit rescue нужен до будущего
install/fault; следующая команда модели после входящего обрыва>1мин rescue не является.

Не подключать AQ к daemon/CLI/startup/installer и не изменять installed runtime.
Все7 runtime gates остаются false, Live C=BLOCKED_BOOTSTRAP, C/D/E не активировать.
Новые наблюдения не создают lease/receipt/ack, не снимают UNKNOWN/stage/repair blockers.
Никаких сетевых проб, HTTP/VPN/DNS/ping/speedtest. Host bookends не являются
LAN/UDP/IPv6/DNS/E4/performance proof или диагностикой ТСПУ.

## 3. Проверенные source anchors и открытая полнота

Ссылки зафиксированы на базе; при реализации добавить exact anchors нового кода.

| Участок | Exact permalink | Что следует учитывать |
|---|---|---|
| AP Binding | [ownership_resources.py:32](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/ownership_resources.py#L32) | Оpaque идентификаторы не являются provenance |
| AP Observation | [ownership_resources.py:100](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/ownership_resources.py#L100) | simulation_only/origin не превращать в доверие к actual capture |
| Сравнение AP | [ownership_resources.py:141](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/ownership_resources.py#L141) | Не ослаблять existing actual/unbound refusal |
| Runtime facade | [ownership_resources.py:377](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/ownership_resources.py#L377) | Runtime Verification остаётся UNKNOWN |
| Контракт каталога | [ownership_resource_catalog.py:975](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/ownership_resource_catalog.py#L975) | declared65 не является полным графом |
| XGW nft tables | [net/nft.py:88](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/net/nft.py#L88) | `ip xgw`, `ip6 xgw6`, `inet xgw_guard` — разные scope |
| Старое listing | [net/nft.py:1182](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/net/nft.py#L1182) | Не наследовать отсутствие таблицы из текста stderr |
| Старое structure | [net/nft.py:1220](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/net/nft.py#L1220) | Очищенный text не является полным semantic kernel proof |
| Generation query | [net/nft.py:1404](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/net/nft.py#L1404) | Netlink socket не включён в AQ allowlist автоматически |
| Маршруты | [net/iprule.py:1](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/src/xgw/net/iprule.py#L1) | ROUTES не доказываются наличием nft table или MainPID |
| Xray unit | [packaging/xgw-xray.service:18](https://github.com/1521572-lang/xgw/blob/dec68ab48add3fda328d4de52b67feecd4049e8a/packaging/xgw-xray.service#L18) | Unit start имеет ExecStartPre/Post: никогда не запускать его ради проверки |

## AQ-1. Контракты источников и неизменяемая схема

Добавить изолированные модули с явными зависимостями. Пример разделения:
`ownership_observations.py` — типы/provenance/coverage;
`ownership_observation_sources.py` — фиксированные readonly adapters;
`ownership_observation_compare.py` — нормализация/сравнение/агрегация.
Имена можно уточнить в ADR до реализации; обязанности и границы не смешивать.
Constructor/validate/compile/serialize не выполняют I/O, subprocess, socket или actor calls.
Не использовать неявный `Paths.from_env()`, PATH lookup или installed XGW imports.

Ввести versioned SourceSpec, CapturePolicy, SourceResult, ObservationEvidence,
Coverage, ObservationDecision и ReadonlyObservationSession. Строгие exact types,
bounded enums/строки/коллекции, unique IDs, запрет bool вместо int, неизвестных ключей,
дубликатов JSON keys, nonfinite numbers и неверных schema versions. Никакого pickle,
eval/exec, dynamic import по данным, arbitrary dataclass reconstruction.

SourceSpec содержит фиксированный source_id, версию adapter/parser, domain, точный scope,
capability и profile. CapturePolicy задаёт лимиты до I/O; никакого default unlimited.
SourceResult раздельно содержит transport status, actual rc/null, decoder status,
context consistency, coverage и safe reason. Source failure не превращать в пустой успех.
Успешное чтение ещё не успешный parse, MATCH или полнота.

Private envelope хранит policy/source/code/session binding, context before/after,
monotonic begin/end, bounded raw capture reference, parse result и выданный session handle.
Поля с boot/PID/namespace/unit paths/частными hashes не включать в public projection.
Разделить provenance classes `FIXTURE`, `SESSION_CAPTURED`, `IMPORTED_UNTRUSTED`.
Origin из входного JSON, caller bool, AP Binding и предъявленный digest не повышают класс.
Fixtures никогда не становятся SESSION_CAPTURED после serialize/deserialize.

Session выдаёт evidence только после собственного разрешённого read path и хранит
принадлежность handle в закрытом ledger текущей сессии. Запретить выдачу за своё handle
другой сессии, equivalent clone, stale handle, подменённый result/parser/policy/context.
JSON persistence не переносит session authority. При импорте только UNTRUSTED, без MATCH
для actual provenance. Схема не является hostile-root/Python sandbox или криптографической
удалённой аттестацией. Не добавлять HMAC/тайный ключ вместо описания этой границы.

Одна сессия обслуживается синхронно одним owner thread/process. Конкурентное/вложенное
collect запрещено явным отказом до I/O. Повтор collect не retry старого evidence: новые
время/sequence/context, новый результат. Потребитель не должен использовать старое MATCH
при свежем failure. Перезапуск процесса не обещает durable replay fence.

Пример API flow, а не разрешение запуска:

```python
# compile/construct: pure, ни host reads, ни автоматического collect
plan = compile_profile(explicit_source_specs, capture_policy)
session = ReadonlyObservationSession(plan, owned_backend, owned_clock)
# Только в отдельно проверенной host ветке; fixture backend имеет другой provenance.
evidence = session.collect_once(source_id)
decision = session.compare_scoped(evidence, independently_fixed_expected)
public = project_public(decision)  # allowlist; не str(evidence)/asdict(private)
# Даже при scoped MATCH: runtime_authorized=False, runtime Verification UNKNOWN.
```

Минимальный пример public row (FIXTURE, не результат машины):

```json
{"schema_version":1,"source_id":"NFT_TABLE","scope_id":"XGW_IPV4","provenance":"FIXTURE","collection":"NOT_COLLECTED","decode":"NOT_RUN","decision":"UNKNOWN","coverage":"STRUCTURAL_SUBSET","reason":"SOURCE_NOT_COLLECTED","source_rc":null,"elapsed_ms":null,"runtime_authorized":false}
```

Логический scope_id различает tables/units: фиксированный enum, не строка с machine data.
Коллекции/decision enums фиксируются единым schema contract, без смешения transport,
decode и compare. Public serializer не должен принимать произвольный dict.

## AQ-2. Конкретный readonly source profile

Реализовать весь следующий ограниченный profile и offline fixtures для него. Real-host
исполнение этого profile допускается только в будущем проверенном TEST-PLAN; сейчас его
не выполнять. Расширение allowlist требует отдельного описания scope до добавления.

| source_id | Кандидат разрешённого чтения | Обязательная граница результата |
|---|---|---|
| CONTEXT | Bounded read `/proc/sys/kernel/random/boot_id`; namespace identities только `/proc/self/ns/net` и `/proc/self/ns/mnt` | Контекст collector, не доказательство реального reboot и не полная mount/DAC policy |
| UNIT | `systemctl show` только `xgw.service`, `xgw-xray.service`, `xgw-singbox.service`; свойства `Id,LoadState,ActiveState,SubState,MainPID` | Properties данного unit; не code identity/cgroup completeness/глобальное отсутствие процессов |
| PROCESS | Bounded read `/proc/<MainPID>/stat` только PID, полученного из UNIT; targeted namespace identity этого PID | Starttime/context binding MainPID; не argv/executable/config identity и не все потомки |
| NFT_TABLE | `nft -j -t list table` только пары `ip xgw`, `ip6 xgw6`, `inet xgw_guard` | Только документированный structural subset; terse не раскрывает элементы sets/maps |

Здесь приведён протокол argv, а не команды для выполнения сейчас. Runner использует
заранее проверенные absolute executable paths и literal argv arrays, shell=false.
Зафиксировать фактически поддерживаемые версии/форматы и соответствующие fixtures.
Не искать альтернативные binaries в домашнем каталоге; metadata/owner/mode/path policy
executable должна быть описана в ADR. Если путь/версия/права не удовлетворяют profile,
вернуть UNSUPPORTED/NOT_COLLECTED, не исправлять окружение и не устанавливать пакеты.

Для systemctl передать свойства явно; не использовать `status`, `cat`, `list-units`,
`--all`, journal, ExecStart/Environment или свободный unit name. Запретить pager, prompts
и сетевой/remote transport; выбрать минимальное детерминированное окружение для local
system bus. Parser `key=value` принимает только эти5 ключей, проверяет каждый ровно раз,
не принимает неизвестные строки/дубликаты/многострочные значения. MainPID0 означает лишь
«MainPID не предъявлен». Inactive/NotFound/permission/timeout сохраняются раздельно.

Для PROCESS: валидировать decimal PID до построения пути; не сканировать `/proc`,
не читать cmdline/environ/maps/mem/fd/exe/config. `/proc/PID/stat` содержит comm со
скобками/пробелами: parser должен выделять поля по документированной грамматике, а не
`split()[21]` от всей строки. PID, starttime и context читать до/после зависимых наблюдений;
несовпадение/исчезновение даёт INCONSISTENT/UNKNOWN, не «сервис исправен».
У PID0 не открывать `/proc/0`. Отличать syntactic parse от подтверждённого process binding.

Procfs pseudo-files могут иметь st_size=0; применять bounded stream read с cap+1, а не
доверять st_size. Namespace magic links обслуживает отдельная узкая metadata/readlink
policy только указанных proc paths, без перехода на произвольный target. Не переносить
NOFOLLOW/regular-file требования частного CodeSeal на procfs без проверки семантики.
Same starttime/netns before/after снижает риск обычного PID reuse, не устраняет ABA,
TOCTOU или вмешательство privileged процесса. Возможный ProtectProc/permission — UNKNOWN.

Для NFT_TABLE: запретить `list ruleset`, чужие tables, `-f`, interactive/input commands,
add/delete/flush/replace/check/monitor и socket-based generation query. Даже `--check`
не требуется. Не использовать прежний mutating Runner или parser text structure как
trust shortcut. rc1/строка «No such file» не доказательство absence: безопасный результат
QUERY_FAILED/ABSENCE_UNPROVEN. Не выполнять дополнительный полный dump для уточнения.
Отсутствующая/нечитаемая IPv6 table не даёт запрета собирать независимые UNIT данные.

JSON parser проверяет envelope, объектные типы, family/table scope и ссылки на объекты;
не должен игнорировать неизвестное expression так, чтобы получить MATCH. Неизвестный
version/object/expression/неполный output → UNSUPPORTED/INCOMPLETE в соответствующем scope.
Нормализовать только явно описанные volatile fields; сохранить порядок rules и значимую
семантику выражений. Нельзя сортировать rules или отбрасывать handle/flags без обоснования.
Покрытие отдельных table/chain/rule features описать точно. Элементы sets/maps, packet
counters, routes, actual traffic enforcement остаются вне доказательства этого profile.

Бюджет по умолчанию: ≤5s на каждый child, ≤30s суммарно на host profile, ≤1MiB stdout
на child, ≤16KiB private stderr, ≤8KiB на proc read, ≤4MiB raw data на весь profile.
Общий byte budget и command timeout проверяются во время чтения, не после полного
capture. Не использовать unbounded communicate/read или неограниченный JSON parse.
Больше лимита — OUTPUT_LIMIT/UNKNOWN без автоматического retry/роста лимита.
Для repeated bookends/context reads учесть полный command/read ledger в manifest.
Если реализация требует изменить бюджет, обосновать worst-case в policy до READY.

Порядок одного полного profile: CONTEXT before → UNIT before для3 units → targeted
PROCESS before для предъявленных положительных MainPID →3 NFT_TABLE → targeted PROCESS
after → UNIT after для тех же3 units → CONTEXT after. Никаких других reads «для полноты».
Верхняя граница:9 children (6UNIT+3NFT),6 reads контекста collector,6 process stat reads
и12 targeted namespace identity reads. Identity/permission metadata executable/private
files учитывать отдельной bounded категорией, не скрывать в этих24 reads.
При совпавших MainPID не добавлять новые процессы/сканирование; допустима явная дедупликация
с сохранением unit associations. UNIT after с новым MainPID инвалидирует прежнее binding;
не собирать новый PID второй попыткой. Сравнение cross-source разрешать только после
bookend-проверок. Результат раннего source до final context check предварительный.
9×5s может превысить общий30s: deadline имеет приоритет, остальные reads NOT_RUN_BUDGET;
это честный partial, не основание увеличить timeout в ходе исполнения.

Никакого sudo fallback, password prompt, capabilities setup, daemon-reload или правок
permissions. Допускается только уже имеющийся разрешённый контекст исполнения будущего
плана. Недостаточные права дают честный partial. Обрывать только собственный collector
child по сохранённому ownership handle; никогда MainPID unit, XGW, Tailscale или чужую
process group. Не pkill/killall. Необеспеченный cleanup → STOP дальнейших host reads.

Остальные источники в AQ явно НЕ реализуются: ROUTES (`ip`/RPDB), API/core sockets,
MODE, MARKERS и содержимое FILES/config/SQLite/status/logs. Отметить UNSUPPORTED с
точной причиной. PROCESS/UNIT не закрывают весь PROCESSES; NFT_TABLE — весь KERNEL.
Не выдавать наличие namespace/unit/table за полноту семи domains.

## AQ-3. Provenance, сравнение и полнота

Сравнивать только явно объявленный compatible scope и supported parser profile.
Expected side поступает из независимого заранее фиксированного контракта; запрещено
делать observed snapshot его же expected baseline и объявлять это проверкой состояния.
Изменённые expected/policy/code/scope после выдачи evidence инвалидируют binding.
В AQ допустим qualification fixture expected; это не описание installed конфигурации.
Если actual expected для host не предоставлен безопасно, host ветка только OBSERVED,
без MATCH. Извлечение expected из приватного config не добавлять молча.

Новая decision matrix должна различать provenance, freshness/context, collection,
decode, expected match и coverage. Статусы минимум MATCH/MISMATCH/UNKNOWN/UNSUPPORTED;
reasons фиксированные. MATCH возможен только для заявленного узкого scope при всех
его проверках, а не для AP ResourceContract целиком. При PARTIAL/unknown required scope
aggregate не MATCH. Утверждение полной операции запрещено даже при нескольких
успешных structural/process comparisons. В evidence/report хранить coverage отдельно.

Свежесть: задаваемый policy monotonic max_age, тот же session/boot/context; clock drift,
clock exception, future/reversed timestamps, stale и repeated read discrepancy → UNKNOWN.
Clock provider session-owned и pinned; не подставлять timestamp из JSON как actual now.
Два последовательных чтения — не atomic snapshot и не durable attestation.
Проверка PID/unit/nft не доказывает совпадение загруженного кода с source124/packaging8.

Интеграция AP через отдельный facade/adapter с явной scoped decision. Не изменять AP
так, чтобы actual capture прошёл по simulation path. Не выставлять simulation_only=true
для actual данных и не использовать origin=SIMULATION как обход. Runtime facade по-прежнему
возвращает UNKNOWN Verification; all7 gates false. Новые observations не вызывают writer
body/registry commit/repair. Указать exact path всех отказов и ограничения cooperative API.

## AQ-4. Lifecycle, private I/O и failure matrix

Отделить offline worker с прежним accepted guard от минимального host collector.
Не отключать audit guard целиком ради subprocess/procfs. Старые helpers оставить
byte-exact. Новый host capability profile — literal allowlist операций AQ-2 и собственных
private artifacts; запрет arbitrary argv/path/network/imported callable на этой границе.
Audit guard здесь regression guard доверенного кода, не hostile-code sandbox.
Если чисто разделить capability boundary не получается, host ветка остаётся BLOCKED;
offline часть сохраняет проверяемую пользу и partial report без выдуманных наблюдений.

Private files: отдельный каталог700, files600, exclusive/no-follow создание, bounded
inventory/size, атомарные checkpoint snapshots, отсутствие fallback в общий `/tmp`.
Сохранять raw только когда необходимо для диагностики parser и в пределах бюджета.
Retention/cleanup зафиксировать; не удалять чужие/непроверенные пути. Никогда не публиковать
raw captures, stderr, unit properties, PID/UID/NIC/IP/MAC/UUID/home/boot/namespace IDs,
private hashes, argv, config, tokens, исключения или screenshots.
Public projection строится заново по whitelist, не sanitization произвольного текста.

| Событие | Обязательное поведение |
|---|---|
| Source/pin/privacy/policy/baseline violation | Global STOP; оставшееся NOT_RUN; никаких host retries |
| Ordinary declared source unavailable/permission/unsupported format | Nullable actual поля + fixed reason; независимые разрешённые ветви продолжаются |
| Timeout/output cap/child cleanup proven | Данный source UNKNOWN; продолжить только независимое в оставшемся бюджете |
| Child cleanup не подтверждён | STOP host branch; не kill по имени и не повторять collect |
| Context drift/PID reuse/clock failure | Evidence не принимать; не маскировать cached success; сохранить partial |
| Expected отсутствует | OBSERVED/UNKNOWN comparison, не автоматически MATCH |
| Worker failure до первого case | Уже созданный empty checkpoint; если создать его не удалось — fixed failure и actual rc, без вымышленного отчёта |
| Пользовательская связь прервалась | Не считать это подтверждением host здоровья; при возврате только предусмотренный read/report path, без повторного start |

## AQ-5. Проверки разработчика и новое покрытие

Минимум VM: только проверки, необходимые для новых ветвей. Не запускать AP211/AO66/AN850/
AM852/AL756/AK437 и прежние партии. Не запускать real host adapters на VM ради PASS;
не выдавать fixtures за captured evidence. Narrow tests обязаны проверять следующий смысл:

1. Строгая схема/лимиты/duplicate keys/nonfinite/type errors, отсутствие constructor I/O.
2. Session handle ownership, clone/replay/import/stale/context/policy/parser/code drift,
   nested/concurrent collect refusal; нет доверия caller flags/digests.
3. Process stat с comm со скобками/пробелами, PID0/missing/reuse, namespace failure,
   zero-size procfs stream и cap; starttime observation не всему process graph proof.
4. Unit parser: missing/duplicate/extra properties, inactive/MainPID0, malformed PID,
   NotFound/permission/timeout как разные факты, незапланированный argv не исполняется.
5. NFT parser: несколько реально поддержанных wire fixtures; unknown expression,
   truncated/oversized JSON, foreign scope, rule reorder, counters/sets limitations,
   rc1≠absence. Fixture version pinned; без копий приватных dump машины.
6. Byte/time budget до исчерпания ресурсов, capped stderr, child ownership cleanup,
   global budget, deterministic partial и сохранение независимых результатов.
7. Scoped positive/mismatch/unsupported/unknown, incomplete coverage aggregate,
   actual-vs-fixture provenance separation; AP runtime Verification всё ещё UNKNOWN.
8. Guard boundary и checkpoint до imports/collect: startup failure, empty report path,
   formatter/read-only report без повторного source collection; строгая public projection.

Не строить декартово произведение ради количества. Матрица manifest должна сопоставлять
каждый case новой ветви/инварианту и exact test/source anchor. Сначала исправить source,
затем уникальные ID/count/schema/hash; не править expected ради зелёного результата.
На стенде запускать новые независимые cases автоматически одним start и не прекращать
весь batch из-за обычного case FAIL с доказанным cleanup/baseline. Scope/privacy/source
STOP никогда не ослаблять. Старые guards/runner cases не rerun ради сравнения чисел.

## AQ-6. Полностью готовая передача Flash

После реализации подготовить один комплект:
`docs/TEST-PLAN-REAL-MACHINE-0.2.0-wave3aq.md`, TEMPLATE, runner, manifest,
schema/API contract, resource-source table, ADR и publication verifier.
Пока code отсутствует — не создавать тест-план со статусом READY. Не использовать
заранее выбранные фиктивные counts, source inventory124 или stale hashes в новом плане:
пересчитать по фактическому финальному source tree.

План имеет две явные ветви: обязательная offline qualification новых adapters и
отдельный proposed readonly host profile AQ-2. До review конкретного allowlist/budgets/
capabilities host ветка BLOCKED_SCOPE_REVIEW, а не «пропустить guard и попробовать».
После review перечислить в плане точные executable paths, args, property/proc allowlist,
число children/reads/bytes/time, права и отдельный host_enabled scope decision.
Если profile всё ещё не готов, передать рабочую offline ветку и честно указать HOST_NOT_RUN;
не смешивать это с доказательством actual machine state. Разработчик обязан довести
готовую часть до конца в одном заходе, а не остановиться после написания документа.

Последовательность будущего плана: Git FF/source preflight → private freeze → один READY →
один start → автоматические независимые branches → bounded monitor → один show + shape →
fresh разрешённые bookends → immutable sanitized snapshot → review всех страниц → один F3.
Не допускать manual rerun worker/internal subcommand или start после timeout/disconnect.
Контроль before/after HEALTHY_ON/poolOFF/linkALIVE/версий использовать только прежним
разрешённым способом; новые status/API reads молча не добавлять. Bookends не мониторинг.
Общий monitor deadline не network rescue и не подтверждение того, что worker завершён.

Для каждого шага уникальный ID, одна полная команда, точный cwd/inputs, actual rc/marker,
допустимые branches, STOP и разрешённый resume. Все bash-блоки проверить `bash -n`,
embedded Python — AST. Не предлагать Flash «собрать команду по смыслу», угадывать путь,
редактировать JSON руками, снимать запрет или писать ad-hoc diagnostics при ошибке.

Раздельно собирать preflight/start/monitor/show/shape/report/publish rc. start0 не casePASS,
monitor0 не completion, show0 не shape0. worker_exit=NOT_COLLECTED, пока он фактически
не получен соответствующим механизмом. Nullable поля сохранять null, не0/false по догадке.
Счётчики network0/liveops0 не использовать нечестно: subprocess/procfs/system-bus/netlink
reads, если разрешены и выполнены, учитывать отдельно по точной семантике. `nft` читает
kernel через netlink; systemctl обращается к local bus. Отсутствие внешних сетевых проб
не означает socket/process count0. Указать actual command counts, failed/attempted reads,
нет workload network traffic и нет state-changing operations как отдельные показатели.

F3 публикует единственный разрешённый отчёт только после report rc0/точного READY marker,
byte-exact canonical prefix, strict footer, schema/privacy/source checks и fresh FF.
Каждый footer field формируется из actual шага, не из expected PASS. Report фиксирует
immutable выбранный snapshot; progress не должен незаметно менять prefix. При report rc3,
нет snapshot или failure до checkpoint — fixed failure с actual rc; ручной commit отчёта,
обход prefix/footer и выдуманные case rows запрещены. Иметь проверенный bounded reader
и worst-case record/page size до передачи. Не смешивать batch_ms/case_sum/elapsed interval.
Повторный report/render не запускает sources. Partial сохраняется, но не повышает статус.

## 4. Deliverables, атомарные commits и критерии завершения

Доставить через normal FF `origin/freepool`, без force/ZIP/patch и без изменения старых
отчётов. Рекомендуемые атомарные commits, каждый с рабочими ссылками и narrow checks:

1. **AQ-1**: типы/provenance/source policy/ADR; схема private/public и явная coverage matrix.
2. **AQ-2**: конкретные adapters/parsers AQ-2, bounded capture/cleanup, synthetic wire fixtures.
3. **AQ-3**: scoped compare/AP facade/partial flow; отсутствие runtime activation доказано.
4. **AQ-4**: готовый Flash комплект AQ-6, фиксированные inventories/hashes/commands/схемы.

Обязательные документы: `docs/API-CONTRACT-WAVE3AQ.md`,
`docs/RESOURCE-SOURCES-WAVE3AQ.md`, `docs/ADR-REC-C-AQ-READONLY-EVIDENCE.md`.
Таблица источников содержит exact commit permalink file:line для source function,
сборщика, decoder, scope/coverage check, каждого отказа, budget enforcement, public
projection, cleanup и потребителя. Не заменять её ссылкой на весь файл/директорию.
Для прежних65 surfaces показать, что реально добавилось и почему aggregate остаётся
UNKNOWN; не заявлять полноту ресурсов на основании имён методов.

API contract содержит versioned JSON examples private/public, actual nullable fields,
status/reason enums, trust/provenance и exact size limits. Примеры только синтетические,
явно FIXTURE; не содержат данные ThinkCentre. ADR содержит решение и альтернативы:
readonly profile vs broad inventory; session-owned provenance vs caller trust; scoped
comparison vs global completion; отдельная host boundary vs отключение audit guard.

Критерии приёмки разработчика: новые narrow checks проходят; diff подтверждает отсутствие
runtime wiring/install/services/config/network changes; старые source/helpers, затронутые
без необходимости, возвращены; manifest соответствует финальному tree; весь передаваемый
план проверен синтаксически/schema/prefix/footer и по command ledger. В отчёте разработчика
перечислить actual checks, NOT_RUN, открытые blockers и точный стартовый документ Flash.
Не называть локальные проверки или наличие ТЗ успешным реальным AQ прогоном.

Критерии будущей реальной приёмки: один настоящий Flash report, проверенный canonical
prefix/actual rc/coverage/cleanup, отсутствие source/privacy/scope нарушений, all7 gates
false. HOST_NOT_RUN/UNSUPPORTED — допустимый честный partial, но не закрытие actualcollector
задачи. Реальную часть принимать только по фактически выполненным источникам/ветвям.

После AQ остаются открыты: global mandatory graph/path aliases/installed loaded identity,
полнота domains, actual boot/bootstrap/repair, independent rescue, C+D до E, runtime45s/
durable replay/absent-table qualification/D1-on/scopedfault/LAN/performance/Tailscale.
Не переходить к wave4/DAE и не объявлять проект завершённым на основании AQ.

## 5. Первичные форматы для реализации

Проверить поддерживаемые версии на fixtures и зафиксировать в API contract. Эти ссылки
описывают формат источника; сами по себе не квалифицируют XGW collector или installed host.

- [nftables manual](https://netfilter.org/projects/nftables/manpage.html): JSON/terse/list и границы вывода.
- [systemctl manual](https://www.freedesktop.org/software/systemd/man/259/systemctl.html): show/property и поведение manager query.
- [Linux procfs documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html): stat, process lifecycle и procfs caveats.
- [Linux proc_pid_stat(5)](https://www.man7.org/linux/man-pages/man5/proc_pid_stat.5.html): comm и starttime field22.

Не опираться на память о формате или на пример одной машины. Unsupported version не
чинить расширением parser без нового fixture/coverage contract. Документация latest/main
не pin installed version; в готовом пакете указать поддержанные версии отдельно.
