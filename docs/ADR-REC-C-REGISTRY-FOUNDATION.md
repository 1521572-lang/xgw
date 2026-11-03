# ADR REC-C: dormant registry foundation с одним atomic record


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


Статус03.11.2026: sourcecandidate, **не активирован и не установлен**.
Основание: AA22/22 принят в sandboxscope. Новая библиотека src/xgw/ownership.py не импортируется
существующими entrypoints, не создаёт каталогов при импорте/конструировании, не включает
featureflags, не вызывает сеть/systemd/nft/ip/XGWruntime. Все livegatesfalse.

## 1. Почему отдельная библиотека, а не перенос AA Store

AA демонстрировал lifetime tickets, но completion обновлял generation и registry разными
файлами, оставляя COMMITTING. Новая схема хранит generation/writers/receipts/lease вместе.
Один fsyncedstate.next→replace(state.json)→fsync(directory) либо оставляет прежний record,
либо делает видимым новый целиком. Это не распределённая транзакция с kernel/API: реальные
sideeffects ещё не интегрированы. Положительный receipt — утверждение callerverifier,
а не доказательство сети. Проверка verified именно boolTrue предотвращает лишь ошибку типа.

## 2. Явные policy и identity

Registry(directory,boot_id,expected_uid=0,clock_ns=None,lock_budget=.2) не делает I/O.
Directory — абсолютный путь. Futureproductadapters должны жёстко использовать доверенный
runtimepath и UID0; AB явно использует свой sandbox и expected_uid владельца. Это fixturepolicy,
не rootattestation и не способ активировать runtimefence. ExistingPaths/CLI не меняются.

initialize создаёт новый private0700каталог, lock/state0600 EXCL. Повторное initialize
отказывается, не очищает старый каталог. Registryid uuid4 генерируется только при явной
инициализации. Bootid suppliedcaller и записывается в state; другаяbootidentity запрещает
даже обычное чтение/admission. AB использует известные syntheticbootids, не /proc/bootid.
Реальное чтение kernelbootid, bootmigration и resetстарогопоколения ещё C-ENTRY/bootstrapwork.

Recordschema1 содержит registryid/bootid/lockdev+inode/revision/generation/serial/epoch,
writers/lease/receipts. Инкременты≤2^63−1, bool не int. Revision не ниже generation/serial/epoch.
32writers максимум, receiptshistory32, JSON≤64KiB/duplicatekeysreject. Receiptgeneration
строго возрастает. UUID/tokens/inodes/boot/сырыеrecords всегда private.

## 3. Filesystem и критическая секция

Все операции открывают проверенный directoryfd и работают с именами относительно него.
Directory/lock/state проверяют тип, expectedUID, mode0700/0600; filesnlink1/nosymlink.
Directoryfd/pathidentity и lockfd/pathidentity проверяются; dev/inode lock привязаны кrecord.
Обычный commit не заменяет lock. Ручная замена lock/удаление чужого inode запрещены.
Cooperative/advisory boundary сохраняется: root или actor, игнорирующий протокол, не fenced.

LOCK_EX|LOCK_NB, budget .2s(max1s), poll5ms, monotonic. Budget относится к lockwait,
не к fsync/всему I/O и не45с rescue. Registrycriticalsection не вызывает domainlocks,
процессы или callbackоперации. Callback lifetime будет защищён ticket, а не удержанным fd.
Boot/metadata/schema/leftoverstageerrors → Refused с fixedcode, без rawpaths/exceptions.

## 4. Writer lifecycle и receipts

admit требует nolease, отсутствие UNKNOWN и свободный slot. Сохраняет LIVEticket прежде
возврата token(registryid/bootid/id/role). После этого будущий writer мог бы работать вне
registrylock, включая nestedchildhook: AAпротокол сохраняется, productcallbacks пока нет.
Leaseacquire при любомwriter сразу WRITERS_IN_FLIGHT, без PENDING и без ожидания servicejob.

complete требует exactLIVEtoken/outcome(COMMITTED/NOOP/ROLLED_BACK)/verifiedisTrue.
Один новый record одновременно увеличиваетgeneration, удаляетwriter, добавляетreceipt.
ДажеNOOP консервативно invalidatesстарыйsnapshot: productadapter позднее может отличить
реальныйnoop от pendingcleanup. Duplicatecompletion отвергается, generation не удваивается.
unknown сохраняет UNKNOWN; его нельзя completeдажеverifiedTrue — нужен отдельный future
repairprotocol. DeadPID/clock/reopen не удаляют LIVEticket. UNKNOWNблокирует новыеwriters,
любойticketблокируетrecovery. Нет гарантии доступности/fairness arming при постоянныхwriters.

receipt(token) возвращает только outcome/generation из retainedhistory или None.
None может означать unfinished или уже вытесненнуюhistory: **никогда** permissionretry.
Receiptlookup не является runtimeverifier. История bounded, не полный аудит всехписателей.

## 5. Crash windows и честный UNKNOWN

До replace ошибка оставляет старыйrecord + возможноstate.next. Любойstate.next, включая
повреждённый/ссылку, блокирует subsequentoperationsINTERRUPTED_COMMIT. Библиотека его не
удаляет/не продвигает/не выбирает «самый новый». Ручной repair в AB запрещён.

После replace ошибка directoryfsync возвращает COMMIT_UNCERTAIN. В текущем работающем
filesystem новый record может уже быть видим и согласован: receipt/generation/writerremoval
проверяются вместе; повторcomplete не разрешён. Это не доказательство powerlossdurability.
После реального I/Oсбоя caller сохраняет UNKNOWN и прекращает свой job; текущийrecord
не даёт разрешения на новый fault. AB проверяет только изолированную инъекцию ошибки.

Отсутствие stage не доказывает отсутствие выполненного commit. Нельзя автоматически
повторить sideeffect по COMMIT_UNCERTAIN. Потерянный ackadmit может оставить LIVE без
начавшейсяработы; такой ticket консервативно запрещает lease. Journalrepair/доказанный
orphanretirement/bootmigration и adversarialstorage/powerloss не реализованы. Поэтому
это foundationC-REG1, **не полное закрытие C-REG/C-ENTRY**.

## 6. Recovery bookkeeping пока не driver

Acquire требует emptywriters/expectedgeneration/runid, сохраняет ARMED с epoch иfixed
deadline≤45s. Defaultclock monotonic_ns; testclock injectable. Begin требует exacttoken,
ARMED и acquired≤now<deadline; сохраняетRUNNING до будущеймутации. Повтор/позднийstart
отвергается. Expiry не снимаетfence. UNUSED толькоARMED; RESTORED_ON толькоRUNNING+
verifiedisTrue и exactboundtoken. Послеsyntheticrestored generationувеличивается,
старыйsnapshot нельзя сноваarm. Здесь нет ни команды восстановления, ни проверкиon.

Suspend/clocksemantics/harddeadline/wakeup/systemd/processsurvival ещё задачиREC-D;
defaultmonotonic не доказательство45с при suspend. Bootboundrecord не подтверждает
независимость driver. Runtimefenceinstalled/recoveryimplemented/activefaultsauthorizedfalse.

## 7. Qualification и дальнейшие атомарные изменения

AB32cases импортируют exactsource через frozenregistry.py в usernotes. Три realprocesscases
используют **новый** Registry: конкурентныйadmitдвухchild, nestedhook и ownerexit.
Остальныеboot/leaseclocksynthetic. Никакого повторAA22/Z19/старыхhelpers, netns/VMbroad.
Локально4узких tests подтверждают pre/postrenameerrors, strictverification и constructor/
bootguard. Основной32casebatch переданFlash, реальныйABNOT_RUN доотчёта.

ПослеAB: C-REG2repairdesign/operationidentity/diagnostics; C-ENTRYdormantwrappers по
REC-C-CALLSITES-AND-BOOTSTRAP, C-VERIFYrealoutcomereceipts. Затем independentDfake и
bootstraprescue. Внедрение entrypoints/установка/restart на ThinkCentre сейчас запрещены.
Sourcepreflight AB допускает только одно добавление ownership.py; прежний runtime совпадает
с pin351. Sourcecandidate≠installedruntime; не писать «полный source runtime diff пуст».
