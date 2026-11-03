# ADR: общий допуск для lifecycle-операций engine и actions

Обновление04.11.2026: [AJ328 принят](REVIEW-REAL-MACHINE-0.2.0-wave3aj.md).
Следующий [AK437](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ak.md) добавляет opt-in code namespace/preflight.
Ниже историческое описание AJ candidate до actualreport; runtimegates остаютсяfalse.


Статус04.11.2026: source candidate готов, реальная AJ квалификация NOT_RUN.
[AI принят](REVIEW-REAL-MACHINE-0.2.0-wave3ai.md). [Единое ТЗ AJ328](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aj.md).
Прямое указание владельца: увеличить объём готовой работы за один заход. Объединены
15entrypoints и4блока328cases, без повторов AI/AG/AF/AE/AD или ослабления gates.

## Проблема и решение

Ранее explicit-owned Applier/Singbox имели свои tickets, но engine.apply_all не имел
общего lifetime admission. Между отдельными actor completions оставался промежуток
для recoverylease. Действия панели/CLI и публикация inventory/SQL могли также оказаться
вне общего допуска. Это gap исходного кандидата, не установленного рабочего шлюза.

Новый ownership_entrypoints.py: owned_entrypoint/EntryBoundary/pin_actor/require_bound_actor.
Optionalkwonlyownership=None сохраняет существующий путь, не делает его fenced.
Explicit-owned проверяет exactCoordinator/Registry/callablepinnedverifier/callmethod,
exact declared actor classes/ownership/method identities доadmission. До/послеbody
перепроверяются тот же coordinator/registry/verifier, PID/thread, отсутствие taint и
declaredactorhooks. Nested synchronous calls используют прежний Coordinator/session,
unionroles и один finalcompletion/receipt/generation. Registryflock не держится на
время domainlocks/servicewait/SQL/networkstub. Есть sourceboundary, но нет автодопуска.

| Source entrypoint | Допуск/зависимости | Вложенные эффекты в квалификации |
|---|---|---|
| engine.save_inventory | LIFECYCLE | private inventory.json |
| engine._save_fingerprints | LIFECYCLE | private fingerprints.json, caught writeerror |
| engine.collect | LIFECYCLE | stubsubscription/manualparse, private cache/history, cancellation |
| engine.persist | LIFECYCLE | actualprivateSQLite nodes/quota/core/events; caught SQLerror |
| engine.apply_all | LIFECYCLE; exactApplier/SB optional | SB→XR, factoryownerpropagation, проверки между шагами |
| actions.enable/enable_checked | LIFECYCLE; exactCapture.enable | actualsourceCapture publicbody/_save, _loadstub, privateevents |
| actions.disable | LIFECYCLE; exactCapture.disable | private marker/state, _loadstub, privateevents |
| actions.apply_network | LIFECYCLE; exactCapture.up | privatecapture, DHCP/service stubs |
| actions.pin/unpin | LIFECYCLE | exactownedAPI factory проверяется перед APIstub; privateSQLite |
| actions.set_pool_mode/house_after_boot/set_pool_pin/set_core | LIFECYCLE | ownership→managed, private panel/SQLite only |

Engineapply_all строит EntryBoundary для обоих actors. Послеfactory проверяется исходный
контекст и новое exact-owned ядро; созданный actor получает boundary до первого шага.
ПослеSB, передXR и послеXR boundary повторно валидируется. Drift/taint послеSB не
запускаетXR. Factoryclass/functionrefs закреплены при импорте, не repin послеdrift.
APIfactory аналогично получает pre/postcontextcheck и actorcheck до API businesscall.
Bootstrap не активируется, никаких registry/path defaults/envactivation/import-timeI/O.

При ошибке допуска body не вызывается. После частичного эффекта failure/taint даёт
UNKNOWN/no receipt; автоматического rollback/retry/repair нет. Терминальные исключения
сохраняются, bookkeepingbest-effort прежний. Caughtnestederror может изменить owned
результат на MutationBlocked, сохранив безопасно неполную операцию. Это намеренный
fail-closed контракт, а не promise одинакового businessOutcome для ownedfailures.

## Увеличенный единый прогон

A246=82variants×LEGACY/OWNED/FENCED:54actionbranches+28enginebranches. Legacy даёт
privatebytes+mode/uid/nlink/inventoryhashes+stubtrace и fixedreturnenum. Owned сравнивает
их, но knownfailednestedoperations могут закончитьсяUNKNOWN. Fenced не исполняетbody.
Реальная privateSQLite используется; времяbusinesslogic100000synthetic. Источник JSON
ошибок/URI/адресов не публикуется. Фактические NULL сохраняются.

B36=24dependencyrefusals доadmit+12definitionrefusals. C22=10context/actor/class/taint/
terminal cases+12foreignfactorycases. D24=16SB×XRresults+8concreteFILEScompositions.
В C16 только2acceptedfinals; в I8 только2positive/5UNKNOWN/1fenced. Квитанции fixture
не сетевые применения. Matrixcaller-verifier подтверждает эквивалентность частных
эффектов даже для некоторых businesserrorreturns. Это намеренно НЕ runtime success
policy; строгая семантическая policy нужна до глобального запуска.

Чтение source/private fixtures и actualSQL не заменяет реальный kernel/API/process/
route/mode verifier. Низкоуровневые Capture._load/SB._install/XR._apply_locked/API._run/
runner/HTTP/subscription/DHCP явноstubbed. Никаких настоящих nft/ip/systemctl/HTTP/DNS/
VPNprobe/WAN/LAN/TS/pin/pool изменений; названия действий относятся к private Paths.
Один usercollector/EXCLstart/progress/final/immutablepartialreport/strictfooter/FFpublish.
OrdinaryFAIL→independentbranchescontinue; scope/source/baseline/privacy/OSError/audit STOP.
TrustedCPythonauditguard не hostile-code sandbox; SQLite/dirfd limitations сохраняются.

15narrowлокальныхchecksPASS, полный328/ThinkCentreNOT_RUN. AST engine/actions после
удаления только explicitownershipscaffolding совпадает с pinnedAI. Не запускать broadVM.
Source diff кpin351 теперь8A11M/118files; только1A+2M относительноAI,115source unchanged.
Units/config/pyproject/старыеhelpers/manifests неизменны. Installedruntime не обновлён.

## Что остаётся открытым

BoundWriters прежний explicit9actors/50methods; новые15functionentrypoints не означают
его расширения до65methods. Глобальная daemon/CLI/servicehook/installer/uninstaller
композиция, mandatory ownership, scopes, protectedpathaliases, version/boot/interprocess
handshake и concrete domainverifiers ещё не завершены. Вызовownership=None остаётся
legacy/unfenced; arbitraryrootcode/callbacks не sandboxed. Старая generationне свидетельство
семантическойвсехресурсов. LiveC installationBLOCKED_BOOTSTRAP и все7runtimegatesfalse.

Следующий шаг после actualAJ: конкретные evidencefixes либо новый максимальный готовый
пакет runtimecomposition/handshake/domainverifiers/repair/bootstrapdry. Реальныйfault/
install требует независимого восстановления originalon/code/units. Incomingoutage>1мин
модель следующей командой не исправит. ТолькоThinkCentre/workingLAN/HEALTHY/on; отдельного
LANclientнет. Fullwave3/45s/D1-on/LANUDP/IPv6/DNS/E4/performance/allTS/DAE gates прежние.
