# ADR REC-C: free-function writers, ранний Job gate и передача ownership фабриками

Статус03.11.2026: source candidate AF; [AE112 принято](REVIEW-REAL-MACHINE-0.2.0-wave3ae.md).
Реальное выполнение AF NOT_RUN. Нет установки/активации или сетевого отказа.

## 1. Точки записи, пропущенные предыдущим boundary

AE проверил определённые32 instance hooks и7объектов. Это не exhaustive writer graph.
Job.run сохраняет running state и удаляет request до update/rollback. managed public
mutators вызывали _update без возможности передать coordinator; directsave имел прямую
запись без gate. Engine factories теряли explicit injection на вложенном ApiClient.
Новый патч расширяет именно эти source paths, сохраняя defaultNone и старые bodies.

[owned_function](../src/xgw/ownership_hooks.py#L130) требует kw-only ownership=None и
synchronous function, отвергает coroutine/generator/неоднозначную signature при definition.
Wrapper передаёт исходные args/kwargs/ownership в настоящий body через call_owned.
Нет context-global/env/defaultregistry activation. Original signature сохраняет wraps;
по success возвращается исходный business result, по businessexception исходный тип.
Отсутствующий callable verifier в explicit Coordinator — refusal до body/admission.
Nested free/instance calls одного coordinator делят ticket/roles; caught error taints
outer, deferred returns не допускаются. Это accepted Coordinator behavior, не новый ledger.

## 2. Полный список изменений текущего пакета

Managed:23 public functions, найденных по прямому _update callsite, получают optional
kw-only ownership и function hook. Дополнительно directsave и
[_update_locked](../src/xgw/managed.py#L76) имеют hook. _update→_update_locked→save
пропускает один coordinator через весь chain, включая validation/read/lock/write.
При explicit coordinator admission происходит ДО public input validation, поэтому
fenced вызов не читает/не удаляет migration fields и не создаёт lockfile.
Это25 НОВЫХ function hooks,26 вариантов AF с уже существующим _update.

Core free functions:save_state/forget/start/take_request/check/run_request,6hooks.
Job instance methods:run/_reject/_stage/_save/_event,5новыхhooks к update/rollback.
[Job.run](../src/xgw/cores.py#L671) gated до первой _save/requestunlink. _save передаёт
ownership в save_state. Ошибка вложенной записи taints outer даже если старый _save
подавил OSError. Старое business поведение без ownership сохранено. Wrapper не исправляет
старые swallowed Store errors; для COMMITTED по реальным ресурсам всё ещё нужен verifier.

[run_request](../src/xgw/cores.py#L893) передаёт ownership в take_request/новый Job.
Injected Job с другим ownership вызывает fixed JOB_BINDING_REFUSED внутри outer ticket
до request read/unlink, остаётся UNKNOWN. Это не REFUSED before admission. При None
старое внедрение job сохраняется. Неверный business return2/failed return1 не должен
становиться успешным receipt из-за truthiness; fixture policy различает их отдельно.

Engine factories:make_api/make_applier/make_singbox получают optional kw-onlyownership;
[make_applier](../src/xgw/engine.py#L961) передаёт его и Applier, и вложенному ApiClient.
API/SB объекты получают тот же identity. Constructor не writer admission, receipts0.
make_singbox всё ещё делает find_binary в прежнем body; в AF эта dependency подставлена,
никаких livebinary reads/version probes. Service factories в AF также подставлены.

BoundWriters.SPECS для Job расширяется2→7methods, весь boundary32→37. Проверка каждого
hook теперь замечает и подмену новых run/save/event helpers. Другие SPECS/binding logic
не меняются. Старые body AST пяти изменённых модулей после удаления scaffolding
совпадают с AE; exception: явный новый injectedJob guard, отдельно проверенный.

## 3. Что этот патч не завершает

Текущие daemon/CLI/panel/service callers используют defaultNone. Глобальный mandatory
composition ещё отсутствует. Нет полного покрытия PoolStore/FreePool constructor prune,
installer/uninstaller, прямых file/runners/lifecycle callbacks, nesteddependency references
и protectedpath aliases. Нельзя назвать этот patch глобальным fence или ставить его
на работающий gateway на основании dryPASS. Эти ветви остаются в actor inventory debt.

[Core.start](../src/xgw/cores.py#L200) пишет request и вызывает systemctl start --no-block.
Hook охватывает ТОЛЬКО этот callback, не весь lifetime отдельного xgw-core process.
Future all-writer activation требует отдельной admission службы, version/boot handshake
и запрета промежутка между завершённым enqueue ticket и неучтённым child writer.
AF FakeRunner не запускает child и не подтверждает межпроцессный protocol.

Free-function None всё ещё legacy/unfenced. Callable verifier остаётся caller policy;
FILE-only fixture assertion не доказывает KERNEL/API/process/mode/routes. Новые hooks
не делают несколько side effects атомарными и не выполняют compensation/retry/repair.
При businesscaught error возвращённый failed code может быть скрыт outer MutationBlocked,
поскольку tainted ticket нельзя подтвердить. Обходить это truthy-verifier запрещено.

## 4. Консолидированная AF qualification

[ТЗ AF](TEST-PLAN-REAL-MACHINE-0.2.0-wave3af.md):145 НОВЫХ cases в одном запуске:
26panel variants×3=78,14core×3=42,3factories×3=9,16extras.
Matrix LEGACY/OWNED/FENCED проверяет реальные source bodies с подставными внешними
dependencies. LEGACY reference (private tree fingerprint+return enum+stubcount)
держится только в памяти, не JSON. OWNED сравнивает его ДО completion и получает1receipt;
FENCED отказывает до body и оставляет fixture bytes/modes/entries и trace неизменными.
Если reference отсутствует, это UNKNOWN/failure, не permission to invent a match.

Сравнение между отдельными fixtures работает с deterministic data/Job.now10, безPID/
privatepaths в выходе. Registry/case dirs исключены из сравниваемого product subtree.
Это differential compatibility плюс AST body proof, не independent production verifier.
В owned callbacks могут остаться partial dummy effects при verificationfailure;
нет автоматического повторного start или cleanup радиPASS.

Factory OWNED означает только construction identity, receipt0. FENCED factory scenario
после construction ставит synthetic lease и проверяет actual mutator отказ до validator/
runner/service. Automatic Job factory recorder вызывает реальный constructor, затем
проверяет exacttype/ownership/stateok/requestremoved; simple receiptcount недостаточен.
Defaultfactory Job timestamps realwallprivate; это не clock/deadline evidence.

Runner/service/Store/release stubs не исполняют systemd/binary/SQL/network. Core update/
rollback/forget работает с dummy text files/dirs. Check использует fake release list,
explicitplatform и stub routes. Никаких LAN/TS/WAN действий: managed setters меняют JSON
только user fixture. Workload subprocess/network/live gateway ops0; нет thread/fakeD.

Freeze3artifacts+116sources с exact GitLF hashes. Никакого archive/install/installedXGW
import. Worker до source imports использует неизменённый AD audit guard/self-test.
Trusted regression guard, не securitysandbox, прежние dirfd limitations сохраняются.
Unexpected OSError/ScopeStop/audit → общийSTOP, обычный assertionfailure → другие
independentcases. Atomic progress и nullable actual counts/errorclass/publicsource:line.
Один start/auto300сmonitor/одинshow/одинreport; rc чтения не collector_exit_rc.

Локально11узких tests/RuffPASS, после recorder refinement повторены3 затронутых tests.
116AST/manifest/sourcebody/ТЗsyntax проверяются отдельно. Полный145-case batch/реальный
ThinkCentre AF нами NOT_RUN, реальные kernel/API/processverifiers тоже NOT_RUN.
Все7runtimegatesfalse даже при145/145. OldAE112/AD130/... не повторяются.

## 5. Последующие зависимости

1. Принять AF evidence, исправить реальные mismatches, сохраняя независимые branches.
2. Достроить полный writer/dependency/path inventory и explicit source composition roots
   daemon/CLI/panel/servicehook/PoolStore/installer; missing actor запрещает activation.
3. Cross-process/version/boot handshake и единая generation semantics для async dispatch,
   complete resource verifiers, UNKNOWN/ack-error handling без unsafe retry.
4. Interruptedstate/bootmigration repair через доказанный transition protocol, сначала dry.
5. Independent original-on/code/unit rescue с autonomous bounded restore ДО live Cinstall/
   D/Efault; сохранить incoming связь. Always_off запрещён, model-next-command не rescue.

LiveC остаётся BLOCKED_BOOTSTRAP. ТолькоThinkCentre/workingLAN/HEALTHY/on, host не LANclient
proof. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.
