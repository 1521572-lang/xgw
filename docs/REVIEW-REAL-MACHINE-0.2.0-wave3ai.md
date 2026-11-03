# Разбор AI: 78/78 принято в пределах проверки FILES

[Отчёт AI](https://github.com/1521572-lang/xgw/blob/813dbbcf75092a63f4a1273cbe58c8c9fde20ba3/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ai-2026-11-04.md#L1)
получен fast-forward. Tested6f247ea6eb777369319f7a42d92de681ec737895,
tree8fff194878ae121830e7fb7ee3bc21e089366c6a. Source117, diff7A10M. Исходный report не менялся.

Проверены точные78IDs, типы/nulls, значения controls и групп. Публичные строки восстановлены
в записи; исполнены ТОЛЬКО pure formatter/schema statements закреплённого helper, без
чтения notes, запуска source cases или нового worker. Автоматический prefix совпал с
отчётом байт-в-байт. Неподтверждённых исправлений таблицы/приблизительных времён нет.

Controls: summary.json/FILE_COMPLETION_BATCH_RECORDED/78expected/78completed/78passed/
remaining0/globalstopfalse/source117/auditregisteredtrue/violations0/workloadprocess0/
network0/liveops0/7runtimeflagsfalse. Batch7743мс, суммаcaseelapsed5652мс; это разные
метрики. Интервал отчёта00:16:00–00:19:44MSK04.11 (224секунды) включает подготовку/
оформление, не является временем исполнения78cases.

17constructorpolicyrefusals/20role-domain/12namedfile/12drift/9checker/8integration.
R8 и F5positive подтверждают только namedFILES и не выдают registryreceipt. K_FRESH_SECOND
первыйpositive/второйnegative, в таблице последнее состояние. K_EXCEPTION два отказных
подслучая, это один case. D_THREAD — ограниченный threadfixture, неprocess/bootproof.
TerminalnegativeK_TERMINAL сохраняет rethrow/NULLoutcome, неCOMPLETED.

[I8](https://github.com/1521572-lang/xgw/blob/813dbbcf75092a63f4a1273cbe58c8c9fde20ba3/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ai-2026-11-04.md#L82):
I_COMMITTED/I_NOOP/I_ROLLBACK→1receipt/generation/FILES1, по2dummyPanelbodycalls;
I_FILES_MISMATCH/I_ROLE_MISMATCH/I_DOMAIN_UNKNOWN/I_RESULT_REJECT→UNKNOWN1/receipt0;
I_FENCED→body0/receipt0/verifierNOT_OBSERVED. В integration outcome/verification_accepted
остались NULL: helper их не записывал при record(v) без decision, не подставлять их
из имениcase/квитанции. NOOP и ROLLED_BACK — о dummyfiles, не о работающей сети.

Footer: NNP0/sudo0/start0/monitor0/show0/report0/HEALTHY_ONbeforeafter/poolOFF/linkALIVE/
versionsunchanged/owneractions0. Start0 не workerPASS; monitor0 неcasePASS; show/report0
неworkerexit0. worker_exit_rcNOT_COLLECTED. Нет новых rootDAC/realboot/installed117/
kernel/RPDB/PID/Yroot/LANend-to-end/performance данных. HEALTHYtimestamp прошлых отчётов
по-прежнему не объяснён; причина рестарта/ТСПУ не выводится. Installedruntime не менялся.

AI78 принимается как qualification dormantFileCompletion. Полнота resource domains,
mandatoryruntimegraph, version/boot/pathaliases/repair/bootstrap остаются открытыми.
LiveC BLOCKED_BOOTSTRAP; реальный fault требует независимого original-on/code/unitrescue.

По прямому указанию владельца следующий пакет существенно укрупнён:
[ТЗ AJ328](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aj.md), [ADR](ADR-REC-C-LIFECYCLE-ENTRYPOINTS.md).
15sourceentrypoints/4блока/328новыхcases,4,205×AI, один start и один automaticreport.
Все независимые ветви автоматически продолжаются при обычном caseFAIL, partialdata
сохраняются. Общие source/baseline/privacy/scopeSTOP не ослаблены. Нет искусственных
ожиданий, повторов старыхbatches или неготовых liveэтапов ради числа задач.
RealAJ NOT_RUN;15узких локальныхchecks/RuffPASS, legacyAST двухмодулей после удаления
ownershipscaffolding равенAI. Полный328 выполняет Flash на ThinkCentre.
