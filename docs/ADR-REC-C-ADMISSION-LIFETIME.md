# ADR REC-C: краткий registry lock и ticket на весь writer

## Текущий статус — AG HOLD; единый AH readback (03.11.2026)

[Отчёт AG](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-2026-11-03.md) доставлен
commit62ae684af177b60e8e52683251caacab771c5760, но **129/129 пока не принято**:
54 строки expected_return противоречат pinned helper8045d3a; 88 времён приблизительные.
[Разбор AG](REVIEW-REAL-MACHINE-0.2.0-wave3ag.md). Причина неизвестна;
actual нельзя заменять source expectation. Original reports не переписываются.

[ТЗ AH](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ah.md) и
[ADR readback](ADR-REC-EVIDENCE-READBACK.md): один read-only сбор existing
AG129/AF145/AE112, до386 сохранённых строк, **ноль новых cases и повторов batches**.
Точные поля/nulls/времена переносятся автоматически; профиль с отсутствующим архивом
не мешает чтению остальных. Реальный AH NOT_RUN, ожидается один wave3ah-report.
Локально9 узких parser/privacy/render checks PASS; это не ThinkCentre evidence.

Продуктовые src116/units/config/pyproject/прежние helpers неизменны относительно8045d3a,
source diff кpin351 остаётся6A10M. Installedruntime не обновлялся. Следующий product
этап ждёт сверки AG. Все7 runtime gates false; explicit9actors/50methods не globalfence.
LiveC BLOCKED_BOOTSTRAP; independent original-on/code/unitrescue обязателен доinstall/fault.
OnlyThinkCentre/workingLAN/HEALTHY/on; nooff/install/G1/WAN/LAN/TS/pool/config/service/
live rules. Host не LAN proof. HEALTHY19:28 противAF15:31 — причина/момент смены не
установлены. Fullwave3/LAN/performance/DAE gates прежние. Ниже — история до AH.



## Актуально после AF — единый AG129 pool-flow пакет (03.11.2026)

[AFreport](TEST-REPORT-REAL-MACHINE-0.2.0-wave3af-2026-11-03.md) принят145/145,
P78/K42/F9/E16. [Разбор AF](REVIEW-REAL-MACHINE-0.2.0-wave3af.md) уточняет extras:
2completed/6UNKNOWN/8definition-admissionrefusals, не2/4/10. Два Hnested callbacks
выполнялись; H_SIGNATURE — неверная ownershipsignature, H_DEFERRED — generatordefinition.
AST proof архитектора локальный, не действие worker. Общий145PASS неизменён.
HEALTHY15:31/on/pool/версии/связь сохранены. Runtime7gatesfalse/network+liveops0.
AF145/AE112/AD130/AC51/... не повторять. Yroot/installed110 NOT_RUN.

[Единое ТЗ AG](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ag.md):129НОВЫХcases/S30/P54/C9/E36,
одинstart/автопереходы/partialdata/одинreport, весь готовый safe объём.
[ADR AG](ADR-REC-C-POOL-FLOW-AND-DEPENDENCIES.md). Локально11 narrowtests/RuffPASS,
full129/реальныйThinkCentreAG NOT_RUN.

Source116/pin6A10M: changed3 vsAF (pool/store/binding),113source/oldhelpers/units/config
unchanged. 13newPEERShooks, constructor ownership propagation/foreignRuntimeguard;
declared9actors/50methods, exactrefsApplier.api/pool.store/pool.runtime. PoolStorectornoIO/
noadmission; ownedFreePoolconstructorcleanup1receipt, неenginefactory0receipt.
AST старых pool/store bodies после scaffolding идентичны, injectedRuntimeguard отдельно.
Fakepoll/probes/runner/tunnel неmeasurement speed/ping/region/realVPN. Dummyfiles only.

Installedruntime НЕ менялся. Nonelegacyunfenced; глобальныйdaemon/CLI/servicecomposition/
fullinventory/pathaliases/interprocess/version/boot/asyncdispatch/realverifiers/repair/
bootstrap не готовы. 3referencechecks неfilesystemaliaspolicy. LiveCBLOCKED_BOOTSTRAP;
independent original-on/code/unitrescue доinstall/fault, always_off запрещён.
Nooff/install/G1/WAN/LAN/TS/pin/pool/config/service/live rules. OnlyThinkCentre/workingLAN/
HEALTHY/on, hostнеLANproof. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTS
открыты,неwave4/DAE. Ниже история: старые37methods/AFNOT_RUN/constructorprunegap относятся
к предыдущему snapshot; sourceprune в AG gated, actual runtime всё ещё legacy.









## Актуально после AB — единый максимальный пакет AC (03.11.2026)

[ABотчёт](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ab-2026-11-03.md) проверен:32/32,
3processcases/4children, command0/shapevalid; HEALTHY/on/pool/versions/связьсохранны.
[Разбор AB](REVIEW-REAL-MACHINE-0.2.0-wave3ab.md). Scopefoundationonly; AB32/AA22/Z19/Y6/
X26/W25 не повторять. Driver/fence/repair/activegatesреальнойсети по-прежнемуfalse.

Прямоеуказаниевладельца: последующиеТЗ — весьмаксимальныйготовыйsafeобъём заодинзаход,
безпотерикачества: независимыеветви/автопереходы/partialresults/одинreport. Не дробить на
микрозадания. Globalidentity/baseline/privacySTOP и prerequisitegatesнеослаблять.

[ТЗ AC](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ac.md) объединяет51 новыйcase:28adapter +
16readonlydiagnostic +7fake-onlyprocess. [ADR](ADR-REC-C-ADAPTERS-AND-FAKE-D.md).
Один detachedusercollector/EXCLstart/checkpoints/summary/Markdown. Casefailнеблокирует
другиеветви. Реальная AC NOT_RUN. Локально8узкихtests/RuffPASS, fullbatchнеисполнялся.

Source diffпротивpin351 теперьровно3новыхмодуля:ownership.py(ABbytesunchanged),
ownership_adapters.py,ownership_diagnostics.py. Прежнийruntime/entrypoints/unit/config
не менялись и не импортируютновыемодули; installedruntimeнеобновлялся. Неinstall/restart.
Adapterverification — callerassertions, diagnosticsneverrepair/promote/prune. FakeD
возвращаеттолькоusercasefileпослеexit/crashсвоегоcontroller; это неслужба/таймер/
networkguardian/реальныйrescue. Положительныхfakerestorations2, expectedfailure1,
refusals2,unused2, не7restored. D01–D05 timingmeasured; D06/D07 timeNOT_MEASURED.

C-ENTRY/verifier/fence/repair/recovery/bootstrapNOT_IMPLEMENTED. Liveустановкапо-прежнему
BLOCKED_BOOTSTRAP; realEтребуетC+D+независимоговозвратаисходногоon. Nooff/install/G1/
WAN/LAN/Tailscale/pin/pool/service/ruleschanges. OnlyThinkCentre/workingLAN/HEALTHY/on.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты,неwave4/DAE.

Ниже история; прежнийAB NOT_RUN отменён фактическим отчётомвыше, livegatesнеподменять.



## Актуально после AA — dormant registry AB (03.11.2026)

[AAотчёт](TEST-REPORT-REAL-MACHINE-0.2.0-wave3aa-2026-11-03.md) принят:
22/22, триprocesscases/3children, command0/shapevalid, HEALTHY/on/pool/versions/связь
сохранны. [Разбор AA](REVIEW-REAL-MACHINE-0.2.0-wave3aa.md). Это sandboxscope;
реальные fence/recovery/activeflagsfalse. AA22/Z19/Y6/X26/W25 не повторять.

Следующий [ADRfoundation](ADR-REC-C-REGISTRY-FOUNDATION.md) и
[единое ТЗ AB](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ab.md):32 новых проверок sourceRegistry,
включая bootidentity/metadata/receipts/pre-postrename и3processcases/4children.
Реальный AB NOT_RUN. Новый src/xgw/ownership.py — **единственное source-добавление**,
без import-timeI/O и без импорта из существующего runtime/entrypoints. Все старые src,
packaging/config/CLI неизменны, на ThinkCentre не устанавливается. Поэтому source diff
не пуст, а установленный рабочий runtime остаётся прежним.

Unifiedrecord сохраняет generation+writerremoval+receipt одной заменой. Это заменяет
двухфайловый COMMITTINGgap AA, но не даёт kernel/APIatomicity. state.next → failclosed,
без autorepair/prune; COMMIT_UNCERTAIN не разрешает повтор. Receipts — assertions caller,
не networkproof. FoundationC-REG1 не закрывает C-REG2repair/C-ENTRY/C-VERIFY/bootstrap.

Далее fixes поAB либо dormantadapters/repair/receipts; fake-only независимыйD может
разрабатываться до Cinstallation. Установка C-ENTRY остаётся BLOCKED_BOOTSTRAP:
независимый возврат исходных code/unit/on ещё не реализован. Nooff/install/G1/WAN/LAN/
Tailscale/pin/pool/service/ruleschanges. ТолькоThinkCentre, workingLAN; hostнеLANclientproof.
Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.

Ниже история. Прежние AA/Z NOT_RUN — статус до полученных выше фактических отчётов.


Статус03.11.2026: design + test-only candidate AA. Не product implementation.
Z19/19 принят, но его Store.writer меняет только одну syntheticrecord под flock.
Расширение такой секции на systemctlrestart создаёт cross-process dependency, описанную
в [аудите](REC-C-CALLSITES-AND-BOOTSTRAP.md). AA проверяет другую границу admission.

## 1. Решение и отказ от механической обёртки

Registry flock удерживается только при чтении/изменении ownership state и списка tickets.
Операция writer выполняется после отпускания flock, но пока её durable ticket существует.
Lease acquire под тем же flock требует пустой список tickets и IDLE ownership; затем
атомарно сохраняет ARMED. Все дальнейшие cooperating admissions видят FENCED.
Значит permit не потерян: lifetime защищает ticket, а не свободный OSlock.

Если tickets непусты, acquire сразу возвращает WRITERS_IN_FLIGHT. Он **не** выставляет
PENDING и не ждёт освобождения net/apply/panel locks. Уже работающий parent может
допустить childhook, закончить свой servicejob и закрыть ticket. Нет гарантии fairness:
при постоянном потоке writers arming может быть недоступен; fault тогда NOT_RUN.
До ARMED нет обещания45с. Обычные задачи нельзя останавливать ради окна для эксперимента.

Этот протокол не разрешает реальные callbacks/внешние writers игнорировать admission.
Advisory trust boundary прежняя. Прямой root/editor/внешний systemctl вне инструментированных
entrypoints не становится автоматически fenced. Все реальные gates остаются false.

## 2. Сохраняемый учёт и публикация

В AA отдельно stableZlock/state.json и tickets.json(version1,serial,tickets).
Ticket={id,role,phase}; id уникален в одном registry, role из fixedsyntheticallowlist,
phase LIVE/COMMITTING/UNKNOWN. Токен{id,role} должен точно совпасть. Это идентичность
testoperation, не аутентификация непривилегированного клиента. Нет PID-based pruning.

Порядок успешного completion под registrylock:

1. Точный LIVEticket + verified именно boolTrue + stateIDLE.
2. Сохранить COMMITTING. Дублированный completion уже не допускается.
3. Durable publication следующего syntheticgeneration.
4. Durable removal ticket. Только теперь acquisition может увидеть пустой registry.

Любой crash между шагами оставляет ticket либо уже совершённое полноценное завершение.
При ошибке generationpublication ticketCOMMITTING остаётся. При публикации g1 и ошибке
cleanup g1 уже возможен/записан, но lease запрещён. Повтор completion не увеличивает
поколение второй раз. Двухфайловой атомарной транзакции нет; safety достигается
консервативным запретом при промежуточном состоянии, не автоматическим repair.

Mutation/verifier error → best-effort UNKNOWN, но и оставшийся LIVE/COMMITTING блокирует
lease. UNKNOWN/COMMITTING блокируют новые обычные admissions. Если процесс умер с LIVE,
AA не определяет это по PID/clock и не снимает запись: lease остаётся запрещённым;
другие LIVE admissions ещё могут проходить. Это admission candidate, не liveness/crash
recovery. Сетевая работа в AA вообще не выполняется.

Publication-before-remove сохраняется и при callbacks, которые ничего не изменили:
AA консервативно увеличивает поколение. Productadapter должен различать истинный noop,
pendingcleanup и неизвестный частичный apply. Outcome(mode="unchanged") нельзя использовать
как универсальное доказательство no-write: SB удаляет pending даже в этой ветви.

## 3. Почему это снимает найденную зависимость только в модели

Parent ticket CORE остаётся LIVE; его registryflock уже освобождён. Child TUN_HOOK получает
свой ticket, выполняет syntheticcompletion и выходит. Попытка recovery между ними
получает WRITERS_IN_FLIGHT. Parent публикует своё поколение и удаляет ticket; только
теперь новый snapshot/arming может продолжиться. Child не обходит fence по root/envtoken.

В настоящем XGW hook может ждать net.lock, другие callbacks — apply.lock, и отдельные
job могут длиться дольше45с. AA не доказывает отсутствие существующих domain-level
циклов и не требует driver ждать их после fault. Полный registry→domain→registry lockgraph
нельзя трактовать как вложенный: domain→registry completion допустим лишь если никакой
registrycriticalsection не ждёт domain/process. Это инвариант будущей реализации.

## 4. Что AA проверяет и что ещё нужно

22 новых cases проверяют drainbeforearm, отказ lease внутри callback, reentrant lifecycle
child без PENDING, неизвестный результат, строгую verification, publication/cleanup failures,
дублированные/чужие tickets и отсутствие orphanpruning. Три childprocesscases выполняются
обычным UID в ~/xgw-w3aa. Fullbatch локально NOT_RUN, mainvalidation — FlashThinkCentre.
Реальные operations заменены callbackзаглушками; leaseclock synthetic. Нет измеренных
45с, systemdexperience, восстановления nft, install/arm/fault.

Следующие атомарные implementationtasks после AA:

- C-REG: отдельный product registry с bootidentity, fixedpaths/DAC, bounds, journalrepair
  и auditfailclosed. Никогда не переносить AArecords в /run/xgw.
- C-ENTRY: инструментировать конкретные top-level writers по матрице аудита; lowerlayers
  получают контекст/ticket, а не повторно захватывают долгий flock. Перед touch/unlink,
  backendpreparecleanup и api.pin тоже admission. Не подавлять отказ как успех.
- C-VERIFY: receipt для noop/success/rollback/failed/UNKNOWN. Verifier реальной generation
  включает kernel+files+API/process dependencies; одного digest недостаточно.
- C-BOOT: отдельно решить versionhandshake всех entrypoints и безопасную активацию;
  старый daemon с новым CLI не считается fenced. Ни один из этих патчей не устанавливать
  до независимого исходного onвозврата и отдельного ТЗ.

REC-D/E пока закрыты. Writerfenceinstalled/recoveryimplemented/activefaultsauthorized=false.
