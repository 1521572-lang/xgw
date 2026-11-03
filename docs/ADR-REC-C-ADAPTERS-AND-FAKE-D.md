# ADR REC-C / D-fake: один пакет адаптеров, диагностики и process independence


## Актуально после AC — единый AD130 source-hook пакет (03.11.2026)

[ACreport](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ac-2026-11-03.md) проверен:
51/51,A28/B16/D7; fakepositiverestorations2/expectedfailure1/refusals2/unused2;
measuredtimings5, WORKLOAD8directchildren+7driverlaunchobservations. HEALTHY/on/pool/
версии/связьсохранны. [Разбор AC](REVIEW-REAL-MACHINE-0.2.0-wave3ac.md) уточняет
Acounts:10COMPLETED/2REFUSED/14UNKNOWN/2terminalcases, ане11/15. Общий51PASSверен.
AC51/AB32/AA22/Z19/Y6/X26/W25неповторять. Runtimeгейтыfalse.

[Единое ТЗ AD](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ad.md) объединяет130НОВЫХcases:
38вариантовреальныхметодов×LEGACY/OWNED/FENCED +16context/error/readerchecks.
[ADR AD](ADR-REC-C-OPT-IN-SOURCE-HOOKS.md). Одинstart/автопереходы/partialreadout/одинreport,
максимальныйготовыйsafeобъём. РеальнаяAD NOT_RUN; локально8узкихtests/RuffPASS.

Source diffпротивpin351 теперь4A+7M: ownership*.pyдобавлены; 7модулейCapture/Backend/
Applier/SingboxCore/Job/ApiClient/managedполучилиopt-inhooks. 31instancewrapper+managed
_update. СохраняемостьстарыхbodyпроверяетсяAST. Вsourceстарые7модулейтеперьимпортируют
hooks; раннее«нетimports»нижеисторическое. Ноexistingruntimeactors coordinatorНЕпередают,
NoneсохраняетlegacyиНЕобеспечиваетfence. Installedruntimeне меняется/неустанавливается.
Mandatorybinding/realverifier/repair/recovery/bootstrapNOT_IMPLEMENTED.

ADfreezehelper+publicSHAmanifest+114sourcefilesвusernotes, импортprivatefrozen_ad, не
installedXGW. Runner/API/service/TUNподставные, dummycorefilesтольковfixture. Auditguard
отказываетprocess/socket/out-of-noteswriteдоэффекта; этонеhostilecode securitysandbox.
Никакихworkloadprocesses/ACfakeDповторов/служб/сети. FENCEDchecksпроверяютfixturecontent/
modes/entriesиtrace0; OWNEDreturnclass+одинreceipt. CallerassertionsнеactualKERNEL/APIproof.

Coordinatorсохраняетbusinessresult/exception, nestedrolesделятticket, nestedfailuretaints
outer. Deferredresultsотвергаютсявключаявложенные, thread/PIDcontextпроверяется. Новая
регрессиязакрываетescapeвложенногогенератора; генераторbodyнеисполняется. DefaultNone
неразрешаетзаявлятьglobalfence/ставитьlivefault. LiveCinstallationBLOCKED_BOOTSTRAP.
Nooff/install/G1/WAN/LAN/TS/pin/pool/config/service/ruleschanges. OnlyThinkCentre,
workingLAN/HEALTHY/on. Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты,
неwave4/DAE. Далееистория; прежнийACNOT_RUNзаменёнфактическимотчётом,неliveготовностью.


Статус03.11.2026: sourcecandidate, без установки и активации. AB32/32 принят в scope
registryfoundation. Источникownership.py остаётся неизменным; новые productmodules
ownership_adapters.py и ownership_diagnostics.py не импортируются существующим runtime.
Ни один API/CLI/action/Capture/Applier/backend entrypoint ещё не инструментирован.

## 1. Объём одного захода и границы независимости

По прямому указанию владельца объединены51 готовый сценарий трёх ветвей:28A/16B/7D.
Casefailure не останавливает другие cases/ветви; один detacheduserworker сохраняетprogress
после каждогоcase и одинfinalsummary. Не повторять AB32 и прежние batches. Наличие
51definitions не PASS; реальные результаты должны прийти из одного отчёта Flash.

Глобальные sourceidentity/baseline/privacy/непригодныйfilesystem STOP сохраняются.
Нельзя включать ещё неготовый liveэтап только ради объёма. Зависимый этап не выполняется
при недоказанном prerequisite. Максимальный пакет = весь готовый независимый safeобъём,
не подмена реальных gates fixtureTrue. Этот порядок действует и для последующих ТЗ.

## 2. Dormant callback adapter

execute(registry,role,operation,verifier) допускает ticket **до** callback, затем отпускает
registryflock. Domainoperation может получить собственные locks и nestedchildticket.
Пока ticket существует, recoverylease не допускается. Никакого долгого flock вокруг
systemctlrestart. Adapter пока genericcoordinator; реальные productcallbacks не передаются.

Verification(outcome,checks) defaultUNKNOWN/empty. Exactdataclasstype, outcome из
COMMITTED/NOOP/ROLLED_BACK, непустойtuple уникальных фиксированных checks, значения
только boolTrue. Boolean/строка/duplicate/unknownkey/list/empty отвергаются. Названия
FILES/KERNEL/API/PROCESSES/MODE/ROUTES/MARKERS — **assertions caller**, не реализованные
проверки этих ресурсов. Одно правильное название не делает runtimeverifier готовым.

Mutation/verifier failure → best-effortUNKNOWNticket, результатUNKNOWN. Ошибкаcleanup
не маскируется: unknown_recorded и cleanupclassification отдельные. KeyboardInterrupt/
SystemExit сохраняютblockingstate best-effort и пробрасываются. Failedadmission не
вызывает callback. VerifiedNOOP/ROLLED_BACK ведут к registryreceipt по прежнему контракту.

Completionackerror, даже при retainedreceipt=true, **не** становится COMPLETED. Возвращается
UNKNOWN/COMPLETION_UNCERTAIN; повторять mutation нельзя. До-rename stageblocked может
не позволить дажепрочитатьreceipt: None неFalse. ВозвратExecution означает bookkeeping,
не сетевой успех; runtime_verifier_implemented всегдаfalse. Нет результата с реальным
NETWORK_RESTORED_ON и нет автоматического включения capture.

## 3. Read-only диагностика прерванной записи

inspect_registry берёт boundedregistryflock и читает validatedstate/stage черезdirectoryfd.
Не создаёт/неперезаписывает/неудаляет/непродвигает ни одногофайла. Базовыеmeta/boot/lock/
schema checks те же. Приотказеbaseline counts=None, не0. Отсутствующийstore не создаётся.

Классификации:CLEAN_IDLE/LIVE_WRITERS/UNKNOWN_WRITERS/RECOVERY_ARMED/RECOVERY_RUNNING,
STAGE_VALID_UNPROVEN/STAGE_UNRELATED/STAGE_REFUSED/BASELINE_REFUSED. Validstage означает
только schema, тежеregistry/boot/lockidentities и revision+1. Происхождение transition,
выполненные sideeffects и право promote **не** доказаны. repair_authorized и
runtime_fence_verified всегдаfalse. Никаких PIDpruning/leaseunlock/старыхlocksудалений.

Read-only diagnostics — подготовка C-REG2repairprotocol, не его реализация. Нужны
обоснованные правила reconciliation с реальными ресурсами/владельцами/bootmigration,
не «убратьstage и попробовать снова». Файловыйpostrenameackerror не powerlossattestation.

## 4. Новый D-fake опыт без служб и сетевых команд

tests/stand/wave3_fake_recovery.py — отдельный конечный процесс, только usercasefiles.
Collector запускает свой controllerchild, тот создаёт detacheddrivergrandchild с
start_new_session/stdin-out-errDEVNULL, а затем выходит или os._exit(9). Collector только
наблюдает artifacts и не посылает restoreкоманду. Driver не импортирует XGW/Registry.

До имитации fault driver сохраняет ARMED; controller под тем же fakefilelock проверяет
nonce/phase/dispatchdeadline и одним record отмечает RUNNING/valueFAULT. Driver по своему
monotonicclock возвращает **тестовый файл** к BASELINE. Это не исходныйcaptureon.
Необходимость нового интернетзапроса/следующейкомандымодели отсутствует только в этом
файловомопыте. Реальное восстановление сети/процессов/units не реализовано.

Сроки от собственногоARMED: dispatchby1с, restoredue1.5с, measuredhardbudget4с.
Позднийcontroller2с не может начать fakefault послеEXPIRED_UNUSED. Срок не продлевается
heartbeat. Scheduler/I/O могут задержать любойPythonprocess; within_budgetfalse → caseFAIL,
не обещание hardrealtime. Boot/cgroup/systemdkill/suspend/reboot/power/WAN не входят в scope.

| Case | Controller rc | Ожидаемый финал файла | Принимаемое доказательство |
|---|---|---|---|
| D01normal |0|FAKE_RESTORED/BASELINE|файловыйdriver завершилпослеexitcontroller |
| D02crash |9|FAKE_RESTORED/BASELINE|послеos._exitcontroller, без следующей restoreкоманды |
| D03unused |0|EXPIRED_UNUSED/BASELINE|fault не dispatch, не ложныйrestore |
| D04late |0|EXPIRED_UNUSED/BASELINE|поздняя mutationнепрошла |
| D05fail_restore |0|FAILED/FAULT|ожидаемыйотрицательный результат, НЕ успешныйвозврат |
| D06bad_nonce |3|REFUSED/BASELINE|armотказал |
| D07bad_baseline |3|REFUSED/OTHER|armотказалдоfault |

Успешныйbatch требует51casePASS, но positivefakerestorations только2, failures1,
refusals2, unused2. Даже51/51 не значит7restorations/реальныйdriverготов.
CollectorPopenсчётчик8=busyholder1+controllers7; отдельныеdriverlaunchobservations7 из
реальныхprivateзаписейпослеPopen. Не выводитьPID/nonce/timestamps/manifest вreport.
8realprocesscase definitions и measuredpassed различаются. Реальные15workloadprocesses
на успешном пути — наблюдаемые8+7, без start/status/show/collector; не переноситьexpectedcounts
вpartialPASS. D01–D05 имеют5 настоящих timingobservations. D06/D07 отказали доARMED:
timing_measuredfalse/elapsed_msnull/within_budgetnull, не «восстановление за0мс».

Collector завершает только собственных directchildren при timeout/cleanup. Grandchild
имеет конечныйпротокол; при отсутствии result он UNCONFIRMED, не «убит/успешен» по догадке.
Не kill по сохранённомуголомуPID, не systemctl, не manualstart_internal, не networkguardian.
Рабочаясеть не зависит от этих files/processes. D-fake не является полным REC-D acceptance.

## 5. Delivery и последующие зависимости

Один [ACпакет](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ac.md) freeze5 exactsourcefiles вusernotes;
старыйownership32batch не исполняется, импортbase только какlibrary. Registryclock/boot
synthetic; fakeDtimings настоящиеmonotonic. КаналNNPдоsudo, status/poolbookends, одинreport.
Installedruntime/defaultrootDAC/настоящийboot/LANpacketpaths по-прежнему NOT_RUN.

Sourceallowlist противpin351: ровно3новых модуля ownership.py/ownership_adapters.py/
ownership_diagnostics.py, каждый с exactSHA. Прежниеsrc/unit/config/entrypoints безизменений.
C-ENTRY/реальныйverifier/fence/repair/recovery/bootstrapNOT_IMPLEMENTED. Fullwave3/D1-on/
fault/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты, неwave4/DAE. ПослеAC — конкретные
evidencefixes либо следующий укрупнённый готовый dormantintegration/repair/bootstrapdry
пакет. ДляliveE всё ещё нужны принятыеC+D+независимыйисходныйonrescue.
