# ADR REC-C: владение поколением и cooperative fence


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



## Актуально после Z — lifetime admission AA (03.11.2026)

[Отчёт Z](TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-2026-11-03.md) проверен:
19/19, три realprocesscases/4children, command0, HEALTHY/on/pool/versions/связь сохранны.
Принят только cooperative sandboxscope, реальный fence/driver/activeflagsfalse.
Y/REC-B snapshot/check-only принят ранее; Y6/X26/W25/Z19 не повторять.

[Разбор Z](REVIEW-REAL-MACHINE-0.2.0-wave3z.md),
[аудит entrypoints и bootstrap](REC-C-CALLSITES-AND-BOOTSTRAP.md),
[ADR lifetime admission](ADR-REC-C-ADMISSION-LIFETIME.md),
[единое ТЗ AA](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aa.md).
AA22 новых cases/3child — только user-sandbox; реальный AA NOT_RUN до отчёта.

Уточнение прежнего долгого ownershiplock: вокруг systemctlrestart он создаёт риск
parent→ExecStartPost→xgwnettun→тотжеlock. Новый кандидат использует короткий registrylock
и durabletickets на lifetime writers. При непустом registry lease сразу отказывается,
без PENDING, orphanpruning и остановки служб. COMMITTING/UNKNOWN запрещают silentretirement.
Это не productintegration и не доказательство общего lockgraph.

Далее productregistry/entrypointadapters/outcomereceipts. Fake-only независимый REC-D
можно разрабатывать до Cinstallation, потому что он не меняет сеть; это уточняет старое
строго последовательное описание C→D. Реальный E требует принятия и C, и D, и bootstrap.
Установка C-ENTRY пока BLOCKED_BOOTSTRAP: нет независимого возврата исходных code/unit/on.
Nooff/install/G1/WAN/LAN/Tailscale/pin/pool/service/ruleschanges. ThinkCentreonly, workingLAN.
Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.

Ниже история предыдущих кандидатов; прежние NOT_RUN не отменяют принятые выше отчёты.


Статус03.11.2026: контракт и test-only candidate, **не установлен в XGW**.
REC-B принят по Y1440d51 в scope snapshot/check-only; manifest PLANNED_NOT_ARMED.
Реальные writer fence/recovery driver/active faults не реализованы и не разрешены этим ADR.

## 1. Ресурс, критическая секция и граница доверия

Test resource — маленькая synthetic generation record в ~/xgw-w3z/sandbox/case-NN.
Stable lock file отделён от атомарно заменяемого state.json. Пока writer держит lock,
он проверяет phase/generation и делает commit той же synthetic record **внутри той же
критической секции**. Получить permit, отпустить lock и затем записать вне секции нельзя.

Используется [fcntl.flock Python3.12](https://docs.python.org/3.12/library/fcntl.html).
[Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html) — advisory locking:
неучаствующий писатель может его игнорировать; он не даёт автоматического deadlock detection.
Это контракт cooperating actors, не защита от скомпрометированного root/того же UID.
Поведение в test filesystem не является аттестацией будущих runtime mount/namespace.

Lock UID/mode/nlink/inode проверяются, lock не заменяется обычным commit. Все
данные private0700/0600. В негативном случае заменяется только собственный synthetic lock;
чужие/product locks не открываются. Никаких /run/xgw, /etc/xgw, /var/lib/xgw или root snapshot
входов в этом кандидате нет.

## 2. Состояние и токен

Version1: epoch≥0, generation, phase(IDLE/ARMED/RUNNING), owner,
acquired_ns/deadline_ns. IDLE имеет owner/times=null. Epoch монотонно увеличивается
при каждом acquisition; retirement не возвращает старый номер. Token содержит точные
epoch+owner+generation. Старый, чужой, неполный или уже retired token не начинает job.

Acquisition только IDLE и с expected_generation=current. Длительность>0/≤45с,
clock int/nonnegative. Срок фиксируется; метода renew/heartbeat нет.
Begin_job требует ARMED, точный token и acquired_ns≤now<deadline. Сначала persist RUNNING,
потом будущий adapter мог бы начинать mutation. Поздний либо повторный job запрещён.
В Z эти события — только synthetic record updates, не мутации шлюза.

Writer разрешён только IDLE и с exact expected generation. Expiry не снимает fence:
при ARMED/RUNNING writer получает FENCED даже после deadline. Потеря OS lock при выходе
процесса и логический retirement lease — разные события. Сохранённая ARMED запись
после выхода владельца продолжает запрещать cooperating writers.

## 3. Retirement и результаты ошибки

- UNUSED допускается только ARMED: job ещё не был dispatched. Token атомарно retiring,
  поздний begin_job отвергается. Если другой actor успел persist RUNNING, UNUSED запрещён.
- RESTORED_ON допускается только RUNNING, с verified именно bool True и совпавшим
  observed_generation. В Z это явно synthetic verification, не проверка работающей сети.
- Ошибка/неизвестное/строка "true" не снимают fence. Настоящий verifier ещё не реализован.

Bounded lock acquisition использует LOCK_NB, budget150мс; истечение не разрешает ломать
чужой lock. Это bound попытки с обычным scheduler, а не45с сетевого восстановления.
Write/fsync/replace/fsync-directory выполняются под lock. При ошибке до replace старый
state сохраняется, незавершённый state.part блокирует повторный commit. После ошибки
после replace исход операции может быть UNKNOWN: нельзя автоматически повторить запись
или объявить отсутствие commit. Этот кандидат не реализует journal repair/power-loss recovery.

## 4. Что реально проверяет Z

Один batch/19 независимых сценариев, case failure не прекращает остальные.
Generation/owner/epoch/expiry/clock cases используют заданные synthetic times. Они
не измеряют15/45с recovery. Filesystem records и три process cases используют реальные
системные вызовы на ThinkCentre. Временный writer не имеет доступа к gateway API в коде.

Real-process cases:

1. Два процесса с expected g0: один COMMITTED, другой STALE_GENERATION; итог g1.
2. Собственный child удерживает только synthetic lock; parent получает LOCK_BUSY,
   завершает именно этот child и после закрытия fd выполняет synthetic writer.
3. Child сохраняет ARMED lease и выходит; следующий cooperating writer всё ещё FENCED.

Child argv только Python-I-B/этот же frozen source/_peer/sandboxcase/fixed mode.
_peer вручную запрещён. Child holder ждёт максимум3с release; parent budgetы2/4с,
cleanup terminate/kill только своих children. Это не service/guardian/autonomy proof.
Если общий controller timeout, нельзя объявлять все сценарии/отсутствие children успешными.

Все epoch/owner/generation/inode и sandbox data остаются private, source constants
synthetic. В report только fixed case IDs/bools/counts/child rc/fixed error enums.
runtime_writer_fence_installed/runtime_recovery_implemented/active_faults_authorized=false.

## 5. Будущая product integration: незакрытые задачи

Начальная инвентаризация дополняется host FreePool backend fp_peers writers, lifecycle
и путями удаления таблиц. Нужен полный call-site audit всех entry points, rollback,
API/config generation и background activity. Не заменять его поиском одной nft.apply.

Предлагаемый порядок для будущих adapters: top-level ownership admission → domain
apply/net/panel lock → validate current generation → bounded operation → durable generation
publication → release. Это **не доказанный порядок существующего графа**: реальные пути
уже могут держать apply.lock при входе в capture/net.lock. Вставка fence внутрь такого
пути без аудита создаёт риск ABBA. Нужен реальный dependency graph и отсутствие reverse
acquisition. Driver не должен ждать живой net.lock30с после fault.

До product patch остаются: полный call graph; failure/rollback publication; drainage
in-flight writers; stale owner/repair protocol; реальный verifier; bootstrap установки
без незастрахованного обрыва. Нельзя устанавливать adapter и проверять его на работающем
шлюзе без конкретного пакета с независимым исходным on возвратом.
Z не создаёт такой bootstrap и не переносит sandbox leases в product. Далее REC-D только
после решения этих вопросов; D1-on/real scoped faults/WAN/core faults не разрешены Z.
