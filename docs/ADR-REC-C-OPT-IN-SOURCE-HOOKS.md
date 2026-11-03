# ADR REC-C: opt-in hooks реальных методов, без runtime activation

## Текущий статус — AH принят; AG129 принят; единый AI78 (04.11.2026)

[AHreport](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md) exactreadback
AG129/AF145/AE112=386existingrows/0newtests/0contractmismatch. [Разбор AH](REVIEW-REAL-MACHINE-0.2.0-wave3ah.md).
AGHOLD снят в optional-source/fake-effects scope. В прежнейAGtable были54expected/
36observedenum/88approxms расхождения, actualsavedreadback соответствует source.
88различающихсяrows, не сумма178cases. Originalreports сохраняются. AF/AE безdiff.
NNP0/sudo0/collect0/show0/HEALTHY_ON/poolOFF/linkALIVE/versionssame/owneractions0.
WorkerexitNOT_COLLECTED; mutableownerfiles не authentication. Старыеbatches не повторять.

[Единое ТЗ AI](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ai.md) и
[ADR FILES completion](ADR-REC-C-FILES-COMPLETION.md):78НОВЫХcases/одинstart/
автопереходы/partialsnapshot/одинавтоматическийreport. Толькоnewownership_completion.py,
117source/7A10M; все прежние116source/units/config/pyproject/standhelpers UNCHANGED.
Concrete fresh namedFILES completion +exactrole/resultpolicy; другиеdomains→UNKNOWN.
Это неglobalruntimeverifier/rolepolicy/pathalias/atomicsnapshot/activation. Runtimeнеwired/
installedнеобновлён, все7gatesfalse. RealAI NOT_RUN;13unique narrowchecks/RuffPASS.
LiveC BLOCKED_BOOTSTRAP; independent original-on/code/unitrescue доinstall/fault.
OnlyThinkCentre/workingLAN/HEALTHY/on; nooff/install/G1/WAN/LAN/TS/pool/config/service/
live rules. Host неLANproof. Fullwave3/45s/LAN/performance/DAE gates прежние. Ниже история.


Актуально03.11: [AF145 принято](REVIEW-REAL-MACHINE-0.2.0-wave3af.md),
[AG129 подготовлено](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ag.md),
[новый ADR pool/dependencies](ADR-REC-C-POOL-FLOW-AND-DEPENDENCIES.md). Далее история:
текущий declared boundary9actors/50methods/source6A10M; globalruntimegate false.

Актуальное состояние03.11: [AE112 принято](REVIEW-REAL-MACHINE-0.2.0-wave3ae.md),
[AF145 подготовлено](TEST-PLAN-REAL-MACHINE-0.2.0-wave3af.md),
[новый ADR source flow](ADR-REC-C-SOURCE-FLOW-AND-FACTORIES.md). Далее история прежнего
snapshot. Текущий boundary37/source6A8M/111sourceunchanged; installed runtime не менялся.

Актуальное решение03.11: [AD130 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ad.md),
[AE112 подготовлен](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ae.md),
[новый ADR binding/files](ADR-REC-C-BOUND-COMPOSITE-AND-FILES.md). Ниже история AD;
старое NOT_RUN заменено отчётом, installed runtime остаётся неизменным.

Статус03.11.2026: sourcecandidate. AC51/51 принят в scopegenericadapter/readonlydiagnostics/
fakefileprocess. Новый AD проверяет реальные source entrypoints с закрытыми fixtures.
Installedruntime/pin/pool/WAN/LAN/Tailscale/services/rules неизменны, установки нет.

## 1. Конкретное изменение

ownership_hooks.py добавляет owned(role), call_owned и Coordinator. Optionalownership=None
добавлен keyword-only в конструкторы Capture,Backend,Applier,SingboxCore,Job; ApiClient
получает отдельный kw_only/nonrepr/noncomparefield, без сдвига прежних positionalfields.
31instanceметод получаетdecorator, managed._update принимает keyword-onlyownership и
передаёт неизменённый прежнийbody в _update_locked черезcall_owned.

| Модуль/класс | Entry points |
|---|---|
| net.capture/Capture | _save,_load,up,enable,disable,open,close,down,restore_tun,tidy,tailscale_direct,tailscale_fallback |
| freepool.backend/Backend | _save_peers,_nft_element,prepare,stop,reconcile |
| apply.applier/Applier | apply,rollback |
| apply.singbox/SingboxCore | apply,rollback,restart |
| cores/Job | update,rollback |
| xraycore.api/ApiClient | add_outbounds,remove_outbound,add_inbounds,remove_inbound,replace_routing,pin,unpin |
| managed | _update→_update_locked |

В частности gate стоит до earlyunlink tailscale_direct, markerchangesopen/close,
preparemanifest/peers и cleanupstop, pendingunlink в unchanged и APIbo pin/unpin.
Кандидат не ограничивается nft.apply. Privatehelpers и прямыеrunners вне указанного
покрытия, installer/uninstaller/boot/daemoncomposition/versionhandshake ещё требуют
полногоохвата. Это не полный callgraph и не принятое исключение всех writers.

## 2. OptionalNone — совместимость, НЕ runtimefence

Если coordinator=None, owned вызывает прежнийbody с темиже аргументами. Никакой registry
не создаётся/не читается. Envactivation, defaultrootregistry, чтения bootid и autoinstall
нет. Existingactors не передают coordinator, поэтому live actorbinding отсутствует.
Такойdefault НЕЛЬЗЯ считатьбезопаснымbypass в активированном механизме. Передреальной
активацией все writers обязаны получать проверенный mandatorybinding; missingbinding
должен быть отказом, а неNone. Этот activationprotocol ещё не реализован.

Нельзя разворачивать необязательныеhooks какготовыйfence, даже при130/130. Конкретные
resourceverifiers, composition одногоSB→Xraygeneration, protectedpathalias rules,
servicehookbinding и полномочияbootstrap остаются gatingзадачами.

## 3. Lifetime и reentrancy

Coordinator.call допускает outerticket до callback черезпринятыйadapter; callback
выполняется без registryflock. Вложенные synchronouscalls того жеcoordinator/thread/PID
используют тотже ticket. Собирается unionroles для callerverifier; частичное вложенное
завершение не публикует отдельную generation и не открывает окно для lease.

Любая nestedexception taintsouter даже если businesscode её поймал: genericverifier
не вызывается, outerUNKNOWN. Для легального компенсированного результата понадобится
отдельный concreteverificationprotocol, не снятиеtaint по bool. Uncaughtbusinessexception
пробрасывается исходнымтипом после best-effortUNKNOWN; terminalexceptions тоже не
превращаются в успех. Исходныйbusinessresult возвращается только после COMPLETEDreceipt.

Session thread-local, PID/thread/activechecked; inheritedclosed/foreigncontext refused.
Другойthread получает собственный ticket, не заимствует scope родителя. last_execution
такжеthread-local, не глобальнаяатрибуция последнего вызова. Это не межпроцессное
делегирование; systemdExecStartPost должен получить отдельный будущийbinding.

Generator/coroutinefunctions owned отвергает приdefinition, deferredreturnvalue не
подтверждаетсяverifier. Ни awaiting, ни запускdeferredbody библиотека не делает.
Конкретные текущие methods синхронные. Без callableverifier coordinator отказывает до
admission/callback. Verification остаётсяcallerassertions, **не** actualKERNEL/APIchecks.

## 4. Почему AD проверяет sourcepackage и что заменено

Publicmanifest tests/stand/wave3_hook_manifest.json фиксирует SHA256 всех114.pyисходников.
Flashкопирует их в ~/xgw-w3ad/source с режимами0700/0600, проверяетполныйinventory иhash,
импортирует privatepackagefrozen_ad. InstalledXGW неимпортируется и неустанавливается.
Новый helper иmanifest заморожены отдельно; source data/UI/assets не нужны этимfixtures.

38вариантов×LEGACY/OWNED/FENCED =114cases. ВLEGACY проверяется прежнийbusinessreturn
и отсутствиеreceipt. ВOWNED — returnclass + одинreceipt, включаяnestedhelpers. ВFENCED —
refusal до bodyeffects: bytesfixturetree неизменны, traceFakeRunner пустой. Ещё16cases
покрывают noverifier/nestedroles/taint/exceptions/deferred/thread/foreigncontext,
preparecompensation/failedOutcome/SBrollback и четыреreadonlyAPIpaths.

Это настоящие Pythonbodies, но не реальные kernel/service/networkactions. Capture._load
использует syntheticrules и stubs низкоуровневых dependencies. Coreupdate/rollback меняют
только dummyfiles внутриfixture; никакие бинарники не исполняются/не скачиваются.
Runner/API/service/TUNhelpers подставлены. Fixtureverifier учитывает fakeoutcomemode,
но не является реализацией C-VERIFY. Actorcfg/boot/clocksynthetic. HostнеLANclient.

## 5. Ограничение побочных эффектов теста

Вworker до sourceimports добавляется CPythonauditguard. Он отказывает subprocess/socket/
fork/exec/kill/ctypescalls, installedxgwimport и write/delete/renameвнеnotes. Hookregistration
проверяется собственным auditevent и двумя manualeventprobes, которые не запускают
процесс/сокет. Unexpecteddenial сохраняетfailedcase и останавливаетостальные какNOT_RUN.
Start/status/show находятся вне этого worker; единственный разрешённый Popen стартует
самprivatecollector. Никаких workloadprocesses, ACfakeD не повторяется.

Это защита от регрессий проверенного fixtureкода, **не securitysandbox для hostilecode**.
Pythonдокументация прямо ограничивает назначение [addaudithook](https://docs.python.org/3.12/library/sys.html#sys.addaudithook);
использованы именованные [CPythonauditevents](https://docs.python.org/3.12/library/audit_events.html).
Dirfdrelativeevents проверяются coarse относительноcwdnotes, поэтому trustedsource/
Paths(fixture) и проверкаfreeze необходимы; они не заменяются аудитором.

Новые registry/sourcefreeze/reportfiles0600. Dummyproductoutputs могут иметь source-expected
0640/0644 и0755дляdummycore внутри privatefixture0700: не chmodпродукт ради фиктивногоPASS. Эти файлы не
секреты работающегошлюза; ихсыройконтент всёравнонепубликуется. No root/Ymaterialreads.
Сборщик печатает только fixedcaseids/counts/status/returnclasses и publicsourcefile:line
приошибке, неrawexception/путьhome/config/argv/секреты или privatefilehashes.

## 6. Проверка и следующие зависимости

Локально8узких regressions/RuffPASS. ASTразница семи старыхмодулей ограничена imports/
hooks/optionalfields и rename managedbody; остальнойbody сохраняется. Полные130cases,
threadfixture и реальные filesystempaths ThinkCentre до отчёта **NOT_RUN**.
ТЗ объединяетвесьготовыйsafeобъём, однаsummary/одинreport; optionalfixturefailнеостанавливает
остальные. Scope/audit/source/baseline/privacy/непригодныйFS — globalSTOP.

ПослеAD: конкретныефиксыилиmandatoryactorbinding/compositegeneration/realresourceverifier/
repair/bootstrapdesign в следующеммаксимальномготовомdryпакете. Liveinstallation по-прежнему
BLOCKED_BOOTSTRAP. Реальныеfence/recovery/repair/actorbinding/activefaultsfalse.
Fullwave3/D1-on/scopedfault/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты, неwave4/DAE.
