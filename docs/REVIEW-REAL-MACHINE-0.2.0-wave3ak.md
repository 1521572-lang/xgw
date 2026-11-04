# Разбор AK:435/437; две ошибки тестового сборщика, полный пакет пока HOLD

Обновление04.11.2026: [AL756 принят](REVIEW-REAL-MACHINE-0.2.0-wave3al.md), обаAKfixturedefects
закрыты actualrepairrows. OriginalAK435/437 не изменён. Ниже история доactualAL.
Следующий [AM852](TEST-PLAN-REAL-MACHINE-0.2.0-wave3am.md), runtimegatesfalse.


[Оригинальный отчёт AK](https://github.com/1521572-lang/xgw/blob/625ac2a043a0003a6f36d1d42f997df1d5f6375c/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ak-2026-11-04.md#L1)
получен fast-forward; добавился только report. Tested69adb641768cf501de67f9d787708b90691dcec9,
tree730e351d133f8c6f4496a5af71a76784a2613f3b/source121/packaging8/surfaces65.
437IDs/nullabletypes/controls/errors проверены. ТОЛЬКО закреплённый pureformatter/schema
восстановил publicprefix byteexact; sourcecases/worker/privatenotes не запускались.

| Блок | Факт | Решение |
|---|---|---|
| A protocol |225/225|Scoped принято; syntheticbookkeep, не реальное IPC/rollout|
| B artifact seal |50/50|Readonly privatecopies; не installedunit/rootDACproof|
| C declared surfaces |144/146|H_DEFAULT/H_DEFAULT_CODE не проверили нужные targets|
| D combined preflight |16/16|Cooperative partialevidence, не runtimeactivation|

Summary/CODE_HANDSHAKE_BATCH_PARTIAL/437completed/435passed/remaining0/globalstopfalse/
auditregisteredtrue/violations0/workloadprocess0/network0/liveops0/7runtimegatesfalse.
Batch65475ms, суммаcaseelapsed47693ms. Интервал02:04:18–02:11:11MSK04.11.2026=413секунд
включает подготовку/оформление. Ни одну из этих метрик не заменять другой.

## Причина двух FAIL

[H_DEFAULT](https://github.com/1521572-lang/xgw/blob/625ac2a043a0003a6f36d1d42f997df1d5f6375c/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ak-2026-11-04.md#L418)
и [H_DEFAULT_CODE](https://github.com/1521572-lang/xgw/blob/625ac2a043a0003a6f36d1d42f997df1d5f6375c/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ak-2026-11-04.md#L431):
TypeError в helper974/977, actualdetailsnull. У lifecycle entrypoint два слоя wrappers;
одно __wrapped__ выбирает промежуточныйwrapper с __kwdefaults__None. Ошибка случилась
при подготовке dict/subscript ДО mutation/наблюдения SurfaceCatalog. Это не refusal
catalog и не отказ рабочего XGW. Подстановка expectedmatchedfalse/check0 была бы ошибкой.

[Дефект подготовки targets](https://github.com/1521572-lang/xgw/blob/69adb641768cf501de67f9d787708b90691dcec9/tests/stand/wave3_code_handshake.py#L972).
Узко воспроизведены оба TypeError; новые repaircases находят уникальное объявление
force_now/runner на depth2, проходят baseline→mutationrefusal→restore→freshobservation.
Полные старые435cases не повторяются, старый helper/report сохраняются неизменными.
Новый source product patch не нужен, все121source/8packaging/config/pyproject unchanged.

## Неоднозначность rc

Footer содержит show_rc0. Это может быть успешным внутренним show, однако S3.3 целиком
при записанной partialsummary должен был закончиться3, потому что ALL_CASES_PASSEDfalse.
Фактический overallshapecommandrc отдельно не записан: NOT_COLLECTED, не «actual3».
Не менять оригинальный footer и не объявлять его доказательством checkerPASS.
AL разделяет SHOW_SUBCOMMAND_RC/show_rc и actual S3.3shape_rc в15полях footer.
Pure shape checker проверен локально на syntheticPASS иpartialdata, не старый realrerun.

FooterHEALTHY_ONbeforeafter/poolOFF/linkALIVE/versionssame/owneractions0/NNP0/sudo0/
start0/monitor0/report0. workerexitNOT_COLLECTED. Bookends не continuousmonitoring.
Нет новых installedruntime/rootDAC/realboot/Yroot/kernel/RPDB/PID/LAN/performanceproof.
HEALTHYtimestamp прошлых отчётов не объяснён; не диагностировать restart/ТСПУ.

## Продолжение текущей квалификации

435пройденных сценариев принимаются в declaredscope, весьAK HOLD до realrepair.
[Единый AL756](TEST-PLAN-REAL-MACHINE-0.2.0-wave3al.md) объединяет исправление2targets
и exhaustive306declaredslots на2путях:directcatalog+combinedpreflight.
4repair/210defaults/160innercode/380closure/2callabledefaultcode, one start/partial/report.
Businessbody не исполняется, меняется metadata только privateworkerprocess. Не deep
mutableclosure attestation/globalcallgraph/hostilecodesandbox. После каждойподмены
originaltarget/state+old/freshobserver должны подтвердить restore до следующегоcase;
неполноеrestore/globalbaselinefailure→globalSTOP, не каскад contaminatedPASS/FAIL.

17narrowtests/RuffPASS; full756/ThinkCentreNOT_RUN. Source/units/старые59standfiles
неизменны. All7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP; independentoriginalon/code/unit
rescue до install/fault. OnlyThinkCentre, LANclientнет/не спрашивать. WorkingLAN/HEALTHY/on,
nooff/install/WAN/LAN/TS/pool/config/services/liverules. HostнеLANUDP/IPv6/DNS/E4proof.
Fullwave3/45s/D1-on/LAN/performance/allTS/DAE gates прежние.
