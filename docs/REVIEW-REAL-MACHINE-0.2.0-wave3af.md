# Разбор wave3af: 145/145 принято; уточнение extras и следующий pool-flow пакет

[Отчёт AF](https://github.com/1521572-lang/xgw/blob/01c84fa9c66fcd67b7bf785a9ff776cb3fcef4fb/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3af-2026-11-03.md#L1)
получен fast-forward, commit01c84fa9c66fcd67b7bf785a9ff776cb3fcef4fb.
03.11.2026,19:17:28–19:30MSK,batch25269мс. Tested
d8598b4cd7ce99cd2f999af6d5bd2c4eead8ae75/treeab909c82095ab90975bb06572e866b1163b9b40f.
Source6A8M,116files,5changed/111unchanged vs AE, exact3SHA/freeze0700/0600/GitLF.
Не installed116 attestation. Original report не переписывается и AF не повторяется.

## Принятое evidence

Start/monitor/show/shape rc0 раздельно; finalsummary.json/SOURCE_FLOW_BATCH_RECORDED,
FINAL_SHAPE_VALID/ALL_CASES_PASSEDtrue,145/145/145/0remaining,global_scope_stopfalse.
P78/K42/F9/E16 поимённых case IDs проверены. Workloadprocess/network/liveops0,
audit_registeredtrue/violations0,7runtimegatesfalse. collector_exit_rcNOT_COLLECTED.
NNPканала0/sudo0/owneractions0; HEALTHY15:31/on/poolвыключенEUстрого/XR26.10.31/SB1.14.4/
связь сохранены вbookends. Kernel/PID/RPDB/installed110/rootDAC/realboot не проверялись;
Yroot не читался/PLANNED_NOT_ARMED. Host не LANclientproof.

40 OWNED writer variants совпали с LEGACY по private product fingerprint/businessenum/
stubcount и получили ровно1finalreceipt/generation, без промежуточных публикаций.
3 OWNED factory cases только создали объекты, receipts0, nestedApplier.api coordinator
тотже. 43LEGACY receipts0. 43FENCED mutator calls отказаны до body; в factory cases
constructor уже исполнялся ДО synthetic lease, поэтому это не отказ до constructor.
CoreJob.run early state/request writes и source-function nesting проверены только вfixtures.

## Исправление описаний, без повторного прогона

Extras реально: **2 positive completions,6 UNKNOWN,8 definition/admission/identity refusals**.
UNKNOWN: H_NESTED_ERROR,H_NESTED_RETURN,K_RUN_FAILED,K_RUN_INVALID,K_REQUEST_FOREIGN,
K_SWALLOWED_SAVE. Два H nested callbacks выполнялись и tainted outer. Поэтому сводка
«UNKNOWN4 +10definition/no business body» неверна: два H нельзя относить к отказу до body.
Итог16casePASS и общий145casePASS остаются верными.

H_SIGNATURE проверяет rejection неправильной ownership signature (positional ownership),
не async signature. H_DEFERRED проверяет rejection generatorFUNCTION при definition,
не отложенный return. GeneratorRETURN проверяет H_NESTED_RETURN. H_NO_VERIFIER — отказ
до admission/callback, а не только отсутствие completion. Другие refusal cases —5 новых
Job hookshadows. K_REQUEST_FOREIGN действительно отказан внутри outer ticket/UNKNOWN,
до request read/unlink. K_RUN_FAILED мог записать failed state, не rollback/успех.

Фраза «AST старых тел проверен helper'ом» не подтверждается worker: helper не выполняет
AST-нормализацию. AST proof выполнен архитектором локально и сохранён в handoff validation;
ThinkCentre подтвердил sourceSHA/differential execution. Эти доказательства различаются.
Ancestry уточняется: AEreport7da3b74 — предок testedAFd8598b4, не наоборот.

## Границы принятия и продолжение

Дефекта в заявленном AF scope не выявлено. Нет globalruntimecomposition, lifecycle
отдельной core service после start--no-block не покрыт; Nonelegacy остаётся unfenced,
full actor/pathalias inventory/handshake/realverifiers/repair/bootstrap не готовы.
Внешние эффекты подставные, dummy files не livebinaryupdate, Store stub не SQLiteproof.
Полный wave3 и установка по145PASS не разрешаются.

[ADR AG](ADR-REC-C-POOL-FLOW-AND-DEPENDENCIES.md) и
[единое ТЗ AG](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ag.md) объединяют129 НОВЫХ cases:
S30/P54/C9/E36, весь готовый safe объём однимstart/автопереходами/partialdata/однимreport.
Закрываются source PoolStore mutations, FreePool constructor cleanup и8 flows;
declared boundary9objects/50methods,3nested-reference identities. Изменились3source
files,113 сохранены,116inventory/source6A10M. Old helpers/units/config неизменны.

Локально11 необходимых narrowtests/RuffPASS; full129/ThinkCentreAG нами NOT_RUN.
Fake poll/probe/tunnel/backend runner не измеряют реальные VPN/ping/speed/region.
Installed XGW/сеть/службы не менялись. LiveC BLOCKED_BOOTSTRAP; independent originalon/
code/unitrescue до install/fault, always_off запрещён, incomingoutage>1мин следующей
командой модели не исправляется. OnlyThinkCentre/workingLAN/HEALTHY/on.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS ещё открыты, неwave4/DAE.
Ожидается один TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-ДАТА.md.
