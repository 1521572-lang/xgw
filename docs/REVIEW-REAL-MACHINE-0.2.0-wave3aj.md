# Разбор AJ: 328/328 принято в пределах optional source flow

[Оригинальный отчёт](https://github.com/1521572-lang/xgw/blob/63c9c413930eb348d46b2ff986bef46dd2e423d4/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3aj-2026-11-04.md#L1)
получен fast-forward. Tested446e0efe0fa37f495d9b4e3059bf3dff5830af08,
treec91195c0b904bb8019dd682887f1a6a15c00c764/source118/pin8A11M.
Original report не переписан. Проверены328unique orderedIDs, nullable actualdetails,
controls, footer. Выполнены ТОЛЬКО pinned pure formatter/schema statements без source
cases/worker/notes I/O: восстановленный публичный prefix совпал байт-в-байт.

Summary/LIFECYCLE_FLOW_BATCH_RECORDED/328expected/completed/passed/remaining0/globalstopfalse,
auditregisteredtrue/violations0/workloadprocess0/network0/liveops0/7runtimeflagsfalse.
Batch71180мс, суммаcaseelapsed59282мс — разные метрики. MSK04.11.2026
01:00:33–01:07:35 (422секунды) включает подготовку/оформление, не время worker.

| Группа | Факт | Правильная интерпретация |
|---|---|---|
| A246 |82LEGACY/82OWNED/82FENCED|OWNED65COMPLETED/17UNKNOWN; negative PASS не completion|
| B36 |24dependency+12definition|Проверки отказа до admission/body|
| C22 |19UNKNOWN/3preadmission|Actor/context/factory/terminal qualifications|
| D24 |4positive/19UNKNOWN/1fenced|Строгие privateFILE/composite verifiers; не сеть|

17OWNEDUNKNOWN:ENABLE_CAP_ERROR/DISABLE_CAP_ERROR/NETWORK_CAP_ERROR/NETWORK_BOTH_ERROR/
PIN_API_ERROR/UNPIN_API_ERROR/POOL_MODE_ERROR/HOUSE_ERROR/POOL_PIN_ERROR/CORE_ERROR/
INVENTORY_WRITE_ERROR/FINGERPRINTS_WRITE_ERROR/COLLECT_CANCEL/COLLECT_WRITE_ERROR/
PERSIST_SQL_ERROR/APPLY_XR_ERROR/APPLY_SB_ERROR. Остальные65получили fixture receipts,
но matrix verifier проверяет private-effect equivalence; caught businesserror может
не taint. Receipt не доказательство успешного сетевого применения. Строгие Dverifiers
проверяют knownfinalmodes/FILES отдельно. Низкоуровневые network/service/APIcalls stubbed.

Footer NNP0/sudo0/start0/monitor0/show0/report0/HEALTHY_ONbeforeafter/poolOFF/linkALIVE/
versionssame/owneractions0. Start/monitor/show/report0 не worker exit0: NOT_COLLECTED.
Installedruntime неизменён. Нет новых installed121/rootDAC/realboot/Yroot/kernel/RPDB/PID/
LANend-to-end/performance доказательств. Timestamp HEALTHY прошлых отчётов не объяснён;
не выводить restart/TSPU из одной метки. Bookends не непрерывное наблюдение.

AJ принят как optional source/private fixtures qualification. Runtimegraph/defaultNone/
globalmandatorybinding/version/boot/pathaliases/actualdomainverifiers/repair/bootstrap
не закрыты. LiveC BLOCKED_BOOTSTRAP. Independent original-on/code/unit rescue доinstall/
fault. ThinkCentre единственный доступный host; LANclientнет. Все7runtimegatesfalse.

По указанию владельца готов следующий укрупнённый [AK437](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ak.md):
225protocol+50artifact+146surfaces+16integration, одинstart/partial/одинreport.
[ADR](ADR-REC-C-CODE-IDENTITY-AND-PREFLIGHT.md). 19узкихtests/RuffPASS, полный437/
ThinkCentreNOT_RUN. Старые batches не повторять. Новых сетевых действий нет.
