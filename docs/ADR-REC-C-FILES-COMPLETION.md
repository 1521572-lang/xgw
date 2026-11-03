# ADR: explicit FILES completion и строгий контракт неполных проверок

Статус04.11.2026: sourcecandidate готов; реальнаяAIqualification NOT_RUN.
[AHreview](REVIEW-REAL-MACHINE-0.2.0-wave3ah.md) снялAGHOLD exactreadback; старые
AG129/AF145/AE112/AD130/... не повторяются. [ТЗ AI](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ai.md).

## Решение и граница

src/xgw/ownership_completion.py связывает существующий readonlyPrivateFiles с
типизированным Verification. Единственное sourceдобавление к117files/7A10M относительно
pin351;116старыхmodules/units/config/pyproject не менялись, изruntimeновогоимпорта нет.
Constructor не читает файлы/clock/boot/registry и не создаёт directories. Observer
arguments валидируются заново безI/O: ранее созданный PrivateFiles мог измениться.
Emptyexpectations/boolUID не превращаются в vacuousFILESsuccess. Root/UID/expectations,
exactclass и4метода observer, checker/contractidentity, PID/thread закрепляются.
Это cooperativechecks, не hostile-code sandbox; private underscore fields не являются
защитой от произвольного кода владельца. Runtimepathpolicy/aliasinventory ещё отсутствуют.

CompletionContract задаётся полностью caller: exact frozenset roles, tuple unique known
domains сFILES, outcome COMMITTED/NOOP/ROLLED_BACK. Runtime role→domain requirements
не выдумываются. FILES-only contract не разрешает подтвердить полные эффекты CAPTURE,
LIFECYCLE/CORE/PEERS. Future runtime policy обязана требовать все нужные domains;
FileCompletion тогда честно возвращаетUNKNOWN доcallback/observe, поскольку KERNEL/API/
PROCESSES/MODE/ROUTES/MARKERS НЕреализованы. Подмена их literalTrue запрещена.

Вызов требует exact nonempty roleunion (не subset); unsupporteddomains→UNKNOWN.
Explicit resultchecker должен вернуть именноTrue, не1/text/truthy. После него повторно
проверяетсяidentity, затем выполняется fresh readonly observe всех namedfiles. Только
exactFileEvidence/matchedTrue/checkedlen/fixedsuccessreason даёт
Verification(contract.outcome,((FILES,True),)). Namedfileabsence/bytes/mode/owner/nlink/
NOFOLLOW/limits проверяются существующимPrivateFiles; no cachedsuccess. checkedprefix
неfullverification. Filesystem меняетсяконкурентно; это не атомарный snapshot/transaction.
Noop/rollback label требует отдельного businesschecker и ожидаемых файлов; не означает
проверку kernel/API/process/runtime/networkrestore. Callback trusted/read-only по договору.

Drift до/послеchecker/observe, false/exception/partialfileevidence→VerificationUNKNOWN.
Пойманный reentrantcall taintsouter, не позволяет скрыть nestederror. Terminalsignal
записывает CHECK_INTERRUPTED, очищаетactiveguard, повторно выбрасывается Coordinator/
execute, который ведёт UNKNOWNticketbest-effort. LastCompletionEvidence диагностический,
не receipt. Никаких retry/repair/compensation/lease/registrycreation/activation.

## Квалификация AI — максимум готового safe объёма

78новыхcases:17constructorinvalidpolicy;8exactrolepositive+6rolecoverage+6unsupported
domains;12actualnamedfiles;12identitydrift;9resultchecker;8realPanelcomposites. Всеfixture
UIDowner/private700/bootclocksynthetic. Threadодинforeignfixture, boundedjoin/STOPесли
неfinished; неrootDAC/realboot/process/kernel proof. 9actors/50hooksbinding unchanged,
3refsintact. Другиеactorsblank, businessbodiesневызываются. PrivatePanelactualmanaged
load/save/atomicwrite/flock используются. Expectedserializedorder рассчитывается по
existingpanelbaseline, ане missingfiledefaultdict: этаошибкаfixture поймана узкимtest.

IntegrationCOMMITTED/NOOP/ROLLED_BACK:2panelsteps, одинfreshfinalverifier/receipt/gen1.
Mismatch/role/domain/resultreject:обаdummyeffects могут остаться, UNKNOWN1/receipt0.
FENCED:body0/receipt0/verifierNOT_OBSERVED. R/Fdirectcases неRegistrycompletions.
All7runtimegatesfalse/network+liveops+workloadprocess0 всегда. TrustedADauditguard
доsourceimports/selfregistration/manualdenialprobes, coarse dirfdlimitations прежние.
Caseassertionfail не мешаетindependentcases; severeFS/audit/unfinishedthreadglobalSTOP.

Collectorstart/status/show неравныworkerexit/casePASS. Exactcase rows/nullablefields/
sanitizedpublicerrorfile:line сохраняются вprogress/final. Новый report command одинраз
фиксирует sanitized selectedsummary/checkpoint вEXCLreport-record.json иMarkdown.
При advancingprogress старыйreport остаётсяточнымpartial. Re-renderread-onlyпроверяет
тотжеsnapshot, ане подменяетfinalexpected. Автотаблица/strictfooter/exactprefix и frozen
SHAvalidation передпубликацией уменьшают manualcopyerrors AG. Ownermutableartifacts
не cryptographicauthentication; collector0/report0 не подменяют casePASS.

## Следующий порядок и оставшиеся gates

После actualAIreport: fixes по evidence либо mandatoryruntimecomposition/entrypoint
handshakes и concrete readonlyKERNEL/API/process/mode/routesverifiers с plannedresource
policy. Отдельно conservative interruptedwrite repair и originalon/code/unitbootstrap
rescue; source/filechecks не снимают installationBLOCKED_BOOTSTRAP. До readyindependent
rescue нельзя ставить C или livefault. Не менятьincomingWANadapter и существующую
раздачуLAN. ТолькоThinkCentre, hostнеLANclientproof. Fullwave3/45s/D1-on/fault/LANUDP/
IPv6/DNS/E4/performance/allTS открыты; wave4/DAE не начинается.
