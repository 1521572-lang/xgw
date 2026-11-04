# ADR: explicit build-bound composition и проверка FILES

Статус04.11.2026: source candidate готов, realAM852 NOT_RUN.
[AL756 принят](REVIEW-REAL-MACHINE-0.2.0-wave3al.md). [ТЗ AM](TEST-PLAN-REAL-MACHINE-0.2.0-wave3am.md).

## Проблема и изменение

CodePreflight, BoundWriters и FileCompletion прежде использовались по отдельности.
Наличие любого из них не обязывало explicit composite проверить buildidentity до
допуска, повторить проверку между шагами или проверить всю actorboundary после
вызова FILES checker. Это gap sourcecandidate, не заявление о поломке installedgateway.

Новый ownership_composition.py объединяет их. BuildCompletion принимает exact Registry
schema2 с тем же CodeIdentity object, exactCodePreflight иexactFileCompletion с FILESonly.
Composition seals один ужеexplicitownedBoundWriters; ownership не прикрепляется и не
исправляется, actors/registry/directories не создаются. Constructors/seal без filesystem
I/O/clockcalls. Unsealedverifier отказывает. Отдельно закреплёнsealedbinding identity,
равноценная новаяboundary послеseal тоже отказывается. Registry path/boot/UID/clock/budget
и provider/binding/method/functioncode/default/closure identity закреплены process-local.

PreparedComposition принимает1–32whitelistedSteps иstrictsyncFunctionTypechecker.
Обязательные ролиLIFECYCLE+declaredstepRoles входятвexplicitFILEScontract; итоговый
FileCompletion проверяет exactunionroles. Попытка одноразоваяprocess-local, consumed
приrefusal; не durable replayfence/serializationauthorization и неdeepfreeze аргументов.

| Checkpoint | Поведение |
|---|---|
| PRE_ADMISSION |Wholebinding+freshcode до registry.admit|
| INSIDE_ADMISSION |Повтор под LIVEticket до первого businessstep|
| BEFORE_STEP/AFTER_STEP |Полная declaredboundary иfreshcode для каждого step|
| AFTER_CHECKER |Проверка после calleraccept, требуется exactTrue|
| VERIFY_BEFORE_FILES |Build+binding до финального namedFILESnapshot|
| VERIFY_AFTER_FILES |Повтор после FileCompletion/checker; только затем допускается receipt|

Один outerLIFECYCLE coordinator объединяетnestedroles иfinaltuple. Registryflock не
держитсяво время body/FILESwaits. Отказ после частичногоэффекта→UNKNOWN/no receipt,
без rollback/retry/repair. Если повреждены методы записиRegistry, best-effort UNKNOWN
может не подтвердиться: LIVEwriter тоже blocking. unknown0 не CLEAN_IDLE приwriter1.
Публичноеevidence сохраняет actualwriter_total/unknown отдельно; не инвентитьcompletion.

Methodchecks выполняются также снаружи перед вызовом validate: shadowvalidate не
может отключить собственную проверку состава. Pin23Registry/preflight/FILES/binding/
gatemethodtargets квалифицируется115cases по пяти моментам. Newcompositionmethodstates
перепроверяются после fixture restoration перед независимымcase. Этоcooperativechecks,
не защита от произвольногоrootcode, способного переписать приватныеполитики/модули.

## Явные ограничения

Global daemon/CLI/servicehook/installercomposition не wired. Nonecallers legacy/unfenced.
Sourcecandidate НЕ mandatoryruntimefence/loadedcodeattestation/полныйwritergraph или
protectedpathaliaspolicy. Digest suppliedcooperatively, не доказательство actualloadedcode.
FILESonly не KERNEL/API/process/routes/MODE verification. Нельзя этим ТЗ активировать
реальные сетевые/COREactors. Scopeреальногопрогона толькоprivatePanelWriter/managedfiles.
CodeSeal observations последовательны, неatomicfilesystemsnapshot/transaction. Окно
после последнейнаблюдаемойпроверки не устранено, никакогоTOCTOU/hardrealtime обещания.
Квитанция относитсякFILEcontract/outcomealias, не к сетевойуспешности/actualrollback.

All7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP. RealE требует C+D+independentoriginalon/
code/unitrescue. Incomingoutage>1мин следующаякоманда модели неrescue. OnlyThinkCentre/
workingLAN/HEALTHY/on/LANclientнет. Никакихoff/install/WAN/LAN/TS/pool/config/services/rules.
Fullwave3/45s/D1-on/LANUDP/IPv6/DNS/E4/performance/allTS/DAE остаются открыты.
NFT10c1/backup2739/freshinstalllegacyWANIPv6 debts не исчезли.

## Единый пакет квалификации

852новыхcases:500hooks/90actorowners/30nestedrefs/40codefilemismatches/115methoddrifts/
20context/16constructorpolicy/16stepdefinitions/12positive-fence/13failures.
H/A/R/T стадииPREPARE/RUN/BODY/CHECKER/FINAL различаютpre- иpostadmission effects.
Tlatecleanup может оставитьLIVE1/UNKNOWN0, receipts0, generation0; неretrypermission.
I11positive+1fenced, F13UNKNOWN/noreceipt; NOOP/ROLLED_BACKprivateoutcomealiases.
ТриIfullbuild читают122frozen source+8publicunitcopies; это неinstalledattestation.
Blankточныеactorclassesчерез__new__неисполняютbody, кромеPanelWriter сprivatePaths.

22narrowtests/RuffPASS/122AST/hash/shape/shellsyntax checks. Full852/ThinkCentreNOT_RUN.
121старыхsource/packaging8/config/pyproject/61старыхstandfiles неизменны.
OneREADY/oneSTART/auto600smonitor/oneSHOW+shape/partial/22pages/oneFFreport.
ПоactualAM:fixevidence либо следующиймаксимальныйготовыйcandidateactualresourceobservations/
startupcomposition/bootstrapdry. НаличиеТЗ не realqualification, livegates не ослаблять.
