# AO66 принят: обе fixture-ошибки AN закрыты

[Оригинальный отчёт AO](https://github.com/1521572-lang/xgw/blob/f75fdc8803f3a2e24f1ee90b3f8d27c1aaa7d1af/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ao-2026-11-04.md#L1).
Tested02297d597f93f71c99c8af1295ee0c6eb9f85942/tree51d75a5184735b4fb28c1865de772a017ae757c8.
Все66orderedIDs/типы/nulls/счётчики/15footerfields проверены. Закреплённыйpureformatter/
schemaONLY восстановил exactpublicprefix байт-в-байт; cases/worker/private notes не читались
и не запускались. Оригинальные AM/AN/AO отчёты не изменены.

Summary/BOUND_COMPOSITION_BATCH_RECORDED/scopeOPERATION_FAULT_POSITION_QUALIFICATION_ONLY,
66expected/completed/passed,remaining0/globalstopfalse/auditreadytrue/violations0/
workloadprocess0/network0/liveops0/source122/unit8/surfaces65/7runtimeflagsfalse.
Batch145671ms, суммаcaseelapsed143823ms; интервал14:20:48–14:26:59MSK04.11.2026=371s.
Это разные метрики; интервал включает подготовку и оформление.

Два исходных F_CHECKER_RAISE/F_BODY_RAISE теперь фактически PASS. Их intentionalRuntimeError
записан как operation_error_observed=true, refused остаётсяnull. НеожиданныеRuntimeError
не объявлялись штатными. Остальные64case — BODY/CHECKER на всех позициях1–32.

Во всех66: body_calls=N/checker_calls=N−1(BODY)либоN(CHECKER), final_calls0,
writer_total=unknown_writers=1, receipt=generation=0, plan_used/target_restoredtrue,
files_verifiedfalse. Gateobservations3N(BODY)/3N+1(CHECKER), lastphaseBEFORE_STEP/
AFTER_STEP. Следующиеsteps/finalchecker не выполнялись. Никакой успешнойоперации/recovery
из отрицательныхcasePASS не следует.

Panel отсутствует вдвухBODYfirst случаях, присутствует в64остальных: это реальные
partialdummyfileeffects, неatomictransaction/rollback. Пара private named-files не
доказательство LAN/network/kernel/process/API состояния.

FooterNNP0/sudo0/start0/monitor0/show0/shape0/report0/HEALTHY_ONbeforeafter/poolOFF/linkALIVE/
versionssame/owneractions0. WorkerexitNOT_COLLECTED. Bookends неcontinuousmonitoring.
Нетновых installed/rootDAC/realboot/Yroot/kernel/RPDB/PID/LAN/performanceproof.

Обе ошибки ANfixtures ЗАКРЫТЫ. ANoriginal850/852 не переписан в852PASS:
850принятыхcases + двеисправленныеqualification через AO. Старые852/850/66 не повторять.
Частнаяexplicitcomposition квалифицирована только в этом scope. Mandatoryruntimegraph/
actualdomainverifiers/boot/pathaliases/repair/bootstrap/fullwave3 ещё открыты. All7gatesfalse,
LiveCBLOCKED_BOOTSTRAP, независимыйoriginalon/code/unitrescue ДОinstall/fault.

Следующий укрупнённый документ — [ТЗ разработчику AP](PR-SPEC-WAVE3-AP-RESOURCE-CONTRACTS-AND-BOOTSTRAP-DRY.md).
AP ещё не реализован, нового Flashrunner нет и новый реальный прогон не заявлен.
AP должен подготовить явные resource contracts/UNKNOWN-preserving comparison/drystartup
и один новый пакет, не очередное повторениеmetadata/faultматриц. Livecommands не разрешены.
