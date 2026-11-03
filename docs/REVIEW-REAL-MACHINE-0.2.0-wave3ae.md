# Разбор wave3ae: 112/112 принято; следующий пакет расширяет source flow

[Фактический отчёт AE](https://github.com/1521572-lang/xgw/blob/7da3b74ce70f0620e0bd634078ab8e4aabb13280/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ae-2026-11-03.md#L1)
получен fast-forward, commit7da3b74ce70f0620e0bd634078ab8e4aabb13280.
03.11.2026,17:46:48–17:57MSK; batch13030мс, не длительность всей терминальной сессии.
Tested737c72037f01caa66ba0309181dbe268128edd01,
tree5bdb358a6ea811be14663276568f2058d0d30cb9. Source6A7M/pin351,3artifactSHA и116
frozen source files0700/0600 соответствуют ТЗ. Исправленные Git LF hashes подтверждены.
Это source identity, не installed116 attestation.

## Что принято

Start/monitor/show/shape rc0 отдельно; finalsummary.json/BOUND_COMPOSITE_BATCH_RECORDED,
FINAL_SHAPE_VALID/ALL_CASES_PASSEDtrue,112/112/112/0 remaining,global_scope_stopfalse.
collector_exit_rcNOT_COLLECTED. Нет повторов AE/AD/AC/AB/AA/Z/Y/X/W и live operations.
112 поимённых строк проверены: H32/MO14/B12/P13/C17/F24, без подмены group definitions
фактическими результатами. Runtime7gatesfalse/network0/liveops0/workloadsubprocess0;
audit_registeredtrue/unexpected_forbidden_io0.

Внутри объявленного boundary подмена каждого32hook, missing/foreign coordinator,
registry/verifier/call drift, PID/thread/context и invalid plan формы отклонены.
P_USED: первый private panel NOOP с receipt/generation1, второй запуск отказан.
P_FENCED: admission refused до body/lockfile. Это не durable replay protection.

C:4 positive composites получили поодной final receipt/generation и exact private
file observation;13 expected negatives оставили UNKNOWN1/receipt0. Partial effect
первого sing-box шага в C_SECOND_REJECT/TERMINAL сохранён, Xray write не выполнен;
это не rollback и не atomic side-effect transaction. C_FILE_MISMATCH отказал по bytes.
Нет промежуточной receipt/lease в проверенных source callbacks. C_NO_EARLY_LEASE
проверяет synthetic registry, не kernel/service writer exclusion.

F:3 положительных observations и21 отказ (6constructor/15read). F_TWO проверяет
две named expectations: один присутствующий файл и одно отсутствие, не два прочитанных
существующих файла. F_OWNER — root owner-policy mismatch в user fixture, не root DAC.
Nullable details сохранены как nullable, не0. Source subset не atomic snapshot.

HEALTHY/on/poolвыключен/EUстрого/Xray26.10.31/sing-box1.14.4/связь сохранены вbookends;
HEALTHY15:31 метка та же, что AD. Причина старого изменения AC→AD не диагностировалась
и остаётся неизвестной. NNPканала0/sudo0/owneractions0. Нет новых kernel/PID/RPDB/
installed110/rootDAC/realboot данных; Yroot не читался/PLANNED_NOT_ARMED.
Фразу «предокae185dd» уточняем: ADreportae185dd — предок testedAE737c720, не наоборот.
Оригинальный отчёт не переписывается. AE112 далее не повторять.

## Продолжение по незакрытым точкам записи

Новых дефектов в проверенном AE scope не выявлено. Следующий source review обнаружил
другие границы, не входившие в AE: managed public functions/directsave и Job.run,
который пишет job state и удаляет request ДО вызова уже обёрнутого update. Фабрики
engine пока не передавали explicit coordinator во вложенный API/actors.
Это незакрытые source entrypoints, а не доказанная неисправность установленного шлюза.

[ADR AF](ADR-REC-C-SOURCE-FLOW-AND-FACTORIES.md) и
[единое ТЗ AF](TEST-PLAN-REAL-MACHINE-0.2.0-wave3af.md) добавляют весь готовый safe объём:
145 НОВЫХ cases (P78/K42/F9/E16), одинstart/автопереходы/partialdata/одинreport.
Изменились5 source files,111 сохранены; source116/pin6A8M. Новые31 free-function hooks,
5Jobinstancehooks и3optional factories;37bound methods вместо32. Тела прежней логики
после удаления scaffolding AST-identical; injectedJob guard отдельно учтён.

Локально11 узких tests/RuffPASS, после уточнения factory recorder повторены только3
затронутые проверки. Полный145-case batch и ThinkCentre AF нами NOT_RUN. Старые suites
не запускались. Installed XGW/сеть/службы/настройки не менялись. Runtime activation,
полный actor/dependency/pathalias inventory, cross-process/version/boot handshake,
real KERNEL/API/process verifiers/repair/bootstrap ещё отсутствуют.

Core.start --no-block source hook не охватывает срок отдельной службы; нельзя выдать
source receipt за all-writer fence. LiveC BLOCKED_BOOTSTRAP; independent исходныйon/
code/unit rescue до установки/реального fault. Always_off запрещён; incomingoutage>1мин
следующая команда модели не исправит. OnlyThinkCentre/workingLAN/hostнеLANproof.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS открыты; неwave4/DAE.
Ожидается один TEST-REPORT-REAL-MACHINE-0.2.0-wave3af-ДАТА.md.
