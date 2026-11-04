# ADR REC-C: FreePool/PoolStore source flow и три явные dependency-связи

## Текущий статус — AO66 принят, ошибки AN закрыты; AP — ТЗ разработчику (04.11.2026)

[Разбор AO](REVIEW-REAL-MACHINE-0.2.0-wave3ao.md):66/66,exactprefix byteequal,
два ANfixtures repaired+BODY/CHECKER positions1–32. All66writerUNKNOWN1/receipt0/
gen0/no furthersteps/final0/restoretrue. Частныйpanelfile присутствуетв64случаях:
этоpartialeffects,неatomicrollback. Batch145671ms/casesum143823ms/371sreportinterval.
HEALTHY_ON/poolOFF/linkALIVE/versionssame/NNP0/sudo0/start-monitor-show-shape-report0/
owneractions0. WorkerexitNOT_COLLECTED. OriginalAN850/852 не изменён в852PASS.
Source122/units/config/pyproject/старыеhelpersUNCHANGED;повторятьAO/AN/oldbatchesне нужно.

Следующее [ТЗ разработчику AP](PR-SPEC-WAVE3-AP-RESOURCE-CONTRACTS-AND-BOOTSTRAP-DRY.md):
явные resource contracts, comparison preservingUNKNOWN, drystartup prerequisites,
одна новая квалификация после реализации. APНЕреализован/НЕFlashready/realAPNOT_RUN.
Нет новых livecommands/collector/installer. All7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP.
Globalmandatorycomposition/actualdomainverifiers/boot/pathaliases/repair/rescue/fullwave3/
LAN/performance/DAEещёоткрыты. OnlyThinkCentre/workingLAN/HEALTHYon/LANclientнет.
Nooff/install/WAN/LAN/TS/pool/config/services/live rules. Ниже история.


Статус03.11.2026: dormant source candidate AG; [AF145 принято](REVIEW-REAL-MACHINE-0.2.0-wave3af.md).
Реальный AG NOT_RUN, нет установки/сети/fault/recovery authorization.

## 1. Конкретный source gap

FreePool constructor сразу вызывает _prune_retired: удаляет старые snapshots/profiles/
secrets/candidate records. PoolStore пишет/вращает/удаляет файлы, а FreePool refresh/check
пишет snapshots/ledgers и вызывает Backend. Эти source paths раньше не получали coordinator.
Даже при правильных отдельных actors mixed pool.store/runtime или Applier.api могли
ссылаться на другие объекты вне declared binding. Новый патч закрывает эти paths.

[PoolStore](../src/xgw/freepool/store.py#L72) получает optional kw-onlyownership=None;
constructor только присваивает поля и I/Oне делает. Новые PEERS hooks:
_ensure,commit,prune,retire_openvpn,save_candidates. Admission перед mkdir/chmod/rename/
unlink/rmtree/write. Nested ensure/save внутри commit/retire используют один ticket.
Даже false/empty/noop business result может получить final receipt по caller verifier;
это не свидетельство успешной загрузки каталога или поднятия VPN.

[FreePool constructor](../src/xgw/freepool/pool.py#L77) передаёт optional coordinator
в Store/defaultBackend. При explicit ownership foreign/non-exact injected Backend
отказывается ДО filesystem setup/cleanup/admission, code POOL_RUNTIME_BINDING_REFUSED.
LegacyNone путь сохраняет прежнее поведение. Перед последним _prune_retired constructor
делает лишь memory assignments/создание libraryobjects. Сам _prune_retired gated и
получает1receipt, поэтому explicit-owned FreePool constructor имеет writer effect;
это отличается от AF engine constructors/PoolStore constructor без admission.

8 FreePool PEERS hooks: _prune_retired,refresh_due,_prune_candidates,refresh_backend,
_note_handshake,check_some,_check_proxy,_record. Gate до новых probe/backend/catalog
callbacks, source ledger/schedule logic остаётся прежней. Caught error внутри старой
cleanup/Backend.stop логики не снимает nested taint: outer UNKNOWN и no receipt даже
если business code продолжил cleanup или записал synthetic OK result.

При actual network callbacks LIVE ticket может жить долго; библиотека не обещает
boundedquiescence/45s. Если writer не закончил, lease блокируется, orphan не удаляется
по PID/timeout. Kernel/agent/async dispatch actors ещё требуют отдельного протокола.

## 2. Declared source graph:9objects/50methods

BoundWriters.SPECS расширяется FreePool/PoolStore: прежние37 +8+5=50 методов,9objects.
Валидация всех type/role/bound-function/ownership/registry/verifier identities остаётся;
добавлены exact references xray.api→api, pool.store→pool_store, pool.runtime→peers.
Они проверяются до admission и между каждым prepared batch step. Ошибка code
DEPENDENCY_BINDING_REFUSED. Aliascases используют новый объект с тем же ownership,
поэтому проверяется именно reference identity, а не равенство coordinator полей.

Это не filesystem path alias policy и не полный graph. Не проверяются все cfg/Paths/
service/private callback/dependency references, direct helper/runners и subprocess
entrypoints. Не выполняются daemon/CLI/service composition/handshake/realboot migration.
None legacy всё ещё unfenced; constructor defaultNone liveactors не становятся protected.
Хостильный Python/root может обойти facade, это cooperating code boundary.

## 3. Совместимость и ограничение патча

Изменились3 source files:freepool/pool.py,freepool/store.py,ownership_binding.py.
Остальные113 source files, включая registry/hooks/adapters/diagnostics/privatefiles,
managed/cores/engine, все старые stand helpers/manifests/units/config/pyproject сохранены.
Source116/pin6A10M. Старые тела pool/store после удаления decorators/optionalfields/
forwardkwargs/new injectedBackend guard AST-identical. В binding separately accounted
новые2imports/2SPECS entries/3dependencychecks/docstring, остальная AST неизменна.
Нет ambient activation/defaultregistry/install-time action.

## 4. AG129 и доказательства

[ТЗ AG](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ag.md):Store10×3=30,Pool18×3=54,
constructor3×3=9,extras36. LEGACY/OWNED/FENCED реальных source methods. Differential
reference включает private filetree/modes/uid/nlink/entries и memory scheduling/backend
state плюс returnenum/stubcount, только память. OWNED сравнение ДО completion,1receipt;
FENCED до body, no file/memory changes/no stub. Missing reference не выдумывает PASS.

Matrix objects строятся legacyNone для setup и затем injected с одним coordinator;
actual constructor forwarding проверяется отдельно C9, не смешивать evidence.
Constructor EMPTY/RETIRED/PROVIDED после cleanup имеет1OWNEDreceipt, FENCED сохраняет
все dummy retiredfiles; Store constructor отдельно noIO/noadmission. ForeignRuntime
отказывается доadmission. ENSURE начинает private dir0755 и подтверждает gate доchmod.

Extras:8base(6refusals+2positiveidentity/noIO),13hookshadows,6expectederrors,7readonly,
2integrations. Все6errors плюс I_SECOND_FAIL→UNKNOWN1/no receipt; I_REFRESH_CHECK→
1completion/rolesPEERS+LIFECYCLE/noearlylease. E_ROTATE_ERROR оставляет partialhistory,
E_PRUNE_ERROR может продолжить другие cleanup, E_STOP_ERROR не публикует completion
после пойманной ошибки nested nftstub. Существование candidateOK не business healthproof.
Читатели summary/nextchecks/spent/handshakes/variants/store работают подsynthetic lease
безadmission. E_BINDING_NINE не pipeline test, только source declaration validation.

Внешние poll/serverhosts/probe/unavailable/findbinary/guarded/PID boundaries подставлены.
FakeTunnel вызывает настоящие Backend.prepare/stop Python bodies с FakeRunner и dummy
manifest; systemd/veth/netns/socket/agent processes не исполняются. Randomdummy lease
directories удаляются source stop, не публикуются. Registry clocksynthetic/poolclock100000.
Outcome bytes128/seconds0.25/countryDE — константы, НЕ measured speed/ping/egress.
SSTP source branch не означает real SSTP compatibility. Installed gateway не импортирован.

Worker до source imports использует exactAD audit guard/selfregistration/manualprobes,
trustedregressionguard, не securitysandbox. Coarse dirfd limitations прежние. Sourcefreeze
3artifacts+116files exactLF/0700/0600, noextras/symlink. Private product modes640/644/755
не следует править радиPASS. Registry/case dirs не входят в differential product subtree.
Atomic progress/finalsummary, nullable actual counts/publicerrorclass/source:line;
нет raw privatehashes/content/argv/exception/path в публикации. Одинstart/автопереходы/
одинreport, optionalcasefail продолжает другие, FS/audit/source/baseline/privacySTOP общий.

Локально11 narrowtests/RuffPASS. Full129/realThinkCentre/kernel/services/network нами
NOT_RUN. Семь runtime gates всегдаfalse, даже129/129. OldAF145/AE112/... не повторяются.

## 5. До реальной активации

Нужны полный remaining actor/path/dependency inventory и composition roots daemon/CLI/
panel/service/installer/uninstaller, version/boot/crossprocess handshake, complete resource
verifiers/async dispatch closure, interruptedstate repair и independent originalon/code/unit
rescue. LiveC BLOCKED_BOOTSTRAP; всегда запрет always_off. Incoming outage>1мин модель
следующей командой не исправит. OnlyThinkCentre/workingLAN/HEALTHY/on, hostнеLANproof.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS открыты; неwave4/DAE.
