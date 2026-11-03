# PR-spec AL: закончить две AK проверки и квалифицировать полную цепочку метаданных

Статус04.11.2026: реализация тестового пакета готова, realAL756 NOT_RUN.
[AK435/437 разобран](REVIEW-REAL-MACHINE-0.2.0-wave3ak.md).
[ТЗ Flash](TEST-PLAN-REAL-MACHINE-0.2.0-wave3al.md).

Проблема: H_DEFAULT/H_DEFAULT_CODE ошиблись глубиной wrapper до наблюдения target.
Исправление: boundedchain≤8/exactFunctionType/nocycles, unique keyword declaration по
всейцепочке, explicitrestore originalobjects и последующие old/freshobservations.
Production source менять/устанавливать для исправления helper не требуется.

Единый756case runner:2repairtargets×2routes,35defaultslots×3mutations×2routes,
80innercode×2,190closurecells×2,1functiondefaultcode×2. Каталог306publicdescriptors
закреплёнSHA и заново выведен worker из121unchangedsource. Catalog содержит только
surface/depth/kind/publicparameter/index, не privatevalues/closurecontents.

Прямой SurfaceCatalog и CodePreflight квалифицируются раздельно. Второй читает два
privateonefileCodeSeal; во времяbadmetadata они должны оставатьсяtrue/checked1 каждый.
Любой fault/statechange вmetadata только privateworkerprocess, businessfunctions не
вызываются. Sourceбайты/frozenpublicpackagingcopies не меняются, network/liveops0.

Restore originaltarget вfinally обязателен; baseline+restored+fresh подтверждаются
до следующегоcase. Observerexception сохраняет nullablemutationdata, targetrestore,
restored/freshactualdata и rethrow исходнойошибки. Restorationerror/badbaseline→global
TargetRestoreStop/remainingNOT_RUN. OrdinaryFAIL с provenrestore→safeindependentcontinue.
Неослаблять acceptedADauditguard/source/baseline/privacySTOP. Trustedguard не sandbox.

Publicreport16nullablebool/intdetails, whitelistclass/publicrepo:line, noexceptiontext/
privatevalues/paths/hashes. Bound1MiB для новыхALrecords нужен для756rows; oldreaderunchanged.
OneEXCLstart/auto300smonitor/oneshow/strictshape/oneimmutablepartialreport/20×40pagereview/
oneFFpublish. Show subcommandrc и shape commandrc раздельны, footer15fields. Actualне0поумолчанию.

17narrowtests/RuffPASS:2oldfailure reproductions/4repairroutes/6representative slots/
catalog+cycle/observerexceptionrestore/globalbadbaseline/650KJSON+duplicatekeys.
Full756/oldbatches/broadVM/ThinkCentreNOT_RUN. Реальнаяприёмка:
REPAIR_H_DEFAULT__CATALOG/PREFLIGHT и REPAIR_H_DEFAULT_CODE__CATALOG/PREFLIGHT должны
иметь targetresolvedtrue/mutationenteredtrue/baselinetrue65/mutatedfalse0/targetrestoredtrue/
restoredtrue65/freshtrue65. Остальные752caseactual, неexpectedPASS. 435oldAK неrerun.
ПриновомFAIL исправитьконкретноеevidence; не считатьAKзакрытым покаrepairнеподтверждены.

Никаких runtime/productinstaller/faultnetwork изменений. CinstallationBLOCKED_BOOTSTRAP/
all7gatesfalse. Actualdomainverifiers/globalmandatorycomposition/boot/pathalias/repair/
independentoriginalonrescue остаются открытыми; закрыть их следующимиreadyспецификациями
после текущихregressions. Не переходить кwave4/DAE.
