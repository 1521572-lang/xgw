# WAN, LAN и условный маршрут Tailscale

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


## Актуальное уточнение владельца 02.11.2026 — сохранять рабочий on

Шлюз уже используется по схеме XGW → Wi-Fi-роутер → устройства; владелец возвращает VPN
в on и требует исходить из этой рабочей схемы. Принимаем рабочий on за текущий baseline.
Актуальное ТЗ — TEST-PLAN-REAL-MACHINE-0.2.0-wave3z.md: sandbox writers/locks,
без enable/disable/restart/install/faults и без изменения WAN/LAN/Tailscale.
Прежний always_off guardian не применять на рабочем on. Старые сценарии ниже — история;
будущий разрушительный тест требует восстановления исходного on, а не автоматического off.
SSH/sentinel не являются условием признания существующей работоспособности.
Подробно REVIEW-REAL-MACHINE-0.2.0-wave3k.md. Свойства доработок принимаются по фактам;
полнаяwave3 пока открыта, рабочая эксплуатация продолжается.

Wave3o4fbde2e принята как readonly сбор, не SB1PASS/причина. N partial1/2 остаётся.
Две строки широкой TLSкатегории не доказывают handshakefailure; oldscan устарел.
Review-wave3o фиксирует основания и ограничения. P сохраняет закрытый план до одной
попытки того же SB1 при точном O→current SBconfigdigest; N→O только filetime support.
Переходы VPN/узла/WAN/LAN/служб/правил запрещены. Реальнаяwave3p NOT_RUN.

Wave3p08cdf11: STOP_SINGLE_PROBE/rc3/request0/ValueError, контекст сохранён.
Измерения SB1 не было, точный exception site не записан; это пробел диагностики теста.
Актуальный Q — только чтения сохранённых файлов и safe stage/code/currentgateflags,
без curl/journal/GET/сканов/повтораP/переключений. Currentgate не точная старая ветвьP.
Review-wave3p фиксирует вывод из порядка исходников; реальнаяwave3q NOT_RUN.

Qe768971 принята: readonly/context сохранён; единственный false — O→currentconfigdigest.
Pblocked/request0 остаётся; точная старая ветвь UNRECORDED, filetime support не digestproof.
R вводит новую baseline, один текущий uniquevless/d по referencekeyO; historicalidentity
UNPROVEN (короткийключ не неизменность endpoint). Полный currentconfigdigest/identity
фиксируются ДО однойпопытки, любое изменение внутри R→STOP. Нет отката кO/переключений.
Review-wave3q содержит решение; реальнаяwave3r NOT_RUN. Npartial не переписывается вPASS.

Rbd51241: отрицательная попытка curl97/HTTP0/bytes0/.977с, relatedliteralREALITYverification1.
Контекст/план/owner сохранены, неbodyPASS/неустановленнаякорневаяпричина. Nне приписывать
новыйлитерал; shortkeyidentityнедоказана. Официальныйcoreимеетфоновыйfallback: curlbudget
неполныйбюджетпостоянногоcore. S толькоreadonlyconfig/Rplan/локальныйcache/manualparser,
boolсверка/форма/coverage, noGET/journal/scans/переключения. Реальнаяwave3s NOT_RUN.

Sa748237 принята: configRdigest/3cache/12equalfields/6syntaxflags/contextсохранны,
не parser/server/causePASS. Владелец потребовал укрупнять ТЗ. T объединяет независимый
разбор источников, все defaultVLESSконтракты/всеprofilebridgeграфы/healthhistory/journal/
6мин пассивных LANсчётчиков: одинworker, автоматические переходы, один итоговый отчёт.
Softphasefail не останавливает остальные чтения. Noactiveprobes/faults/networkchanges.
Review-wave3s фиксирует границы. Реальнаяwave3t NOT_RUN, полнаяwave3ещёоткрыта.

T8d208e9 принята scopedreadonly7phases/364.31с/contextсохранён. 6/67contractsравны,
61NOT_RUN;141bridgeграф согласован. Исправляется testcollectorJSONarraycontainergap,
неruntime. U:8этапов sourcecoverage/configgenerations/keyedscans/unitprops/writerjournal,
одинworker/отчёт. Аудит cumulativeT7 безповторанаблюдения. Владелец03.11: толькоThinkCentre,
отдельногоLANклиентанет; hostпробы не LANдоказательство. Реальнаяwave3u NOT_RUN.








Статус: требование о сохранении входящего подключения принято как ограничение.
В wave3d реализовано сохранение текущего WAN при повторной/частичной установке:
без NM modify/reapply, переключения IPv6 и повторного применения старых WAN sysctl.
Boot-ключи и журнал сохраняются без автоматической обратной миграции. Чистая установка,
явная миграция старого WAN и отдельный канал Flash — следующие задачи; их не считать готовыми.
Основание: уточнение владельца02.11.2026 — два физических адаптера, WAN к провайдеру,
LAN раздаёт сеть, Tailscale в некоторых случаях должен работать через VPN.

Wave3l149ffec принята:608.141с/on bookends,6active/PID same/NRestartsdelta0,
sing-box nonprivileged/caps0×5/NoNewPrivs/DAC подтверждены; настройки прежние.
Отдельное клиентское использование/Tailscale в интервале не наблюдалось; LAN-счётчики
не являются атрибуцией потоку. Review-wave3l содержит точные пределы. Новый продуктовый
patch не требуется. Wave3m проверяет файловые/API/netlink границы отдельными capless
процессами с фактическими UID/GID/Groups; сеть/службы/VPN не изменяются. Исключение только
собственный пустой state-probe, если ошибочно разрешено создание: удалить свой inode,
зафиксировать FAIL, без правок каталога/конфигов. Live ip rule add/del запрещены.
Реальнаяwave3m NOT_RUN; полнаяwave3 открыта.


Wave3m09abf5c принята:6/6 actual permission cases с проверенной identity, root nft-read
control успешен, state-файл не создан, on/PID/настройки сохранены. Review-wave3m фиксирует
scope: отдельные capless UID/GID/Groups, не весь service sandbox; live ipruleadd NOT_RUN.
Новый дефект продукта не найден. Следующий wave3n выполняет небольшие HTTPS GET через
существующие постоянные SOCKS-входы SB, без смены основного pin/ядра/правил/режима VPN.
Это positive compatibility worker, не fault/E4 или все LAN/UDP/IPv6/Tailscale пути.
Реальнаяwave3n NOT_RUN; рабочий on сохраняется, полный wave3 acceptance ещё открыт.


Wave3ne4f6f2d: частичный результат1/2, не общийPASS. SB-2vless/d206/32769/.372с,
ownedlistener/TLS/контекст подтверждены; SB-1двеcurl97/HTTP0/bytes0. УспехSB2 исключает
глобальную неспособность процесса, но не endpoint-specific права/конфиг/маршрут SB1.
Случайнаяпоhealth выборка2из71 не доказывает проблему продукта. On/6PID/settings/pin
сохранены. Новый runtimepatch пока не обоснован. Wave3o читает только существующие
свидетельства/журналы/lastscan, не повторяет запросы и не меняет рабочий шлюз.
Исторический mapping по filetimes не скрывает отсутствие старого configdigest.
Review-wave3n фиксирует пределы; O_NOT_RUN, полнаяwave3 открыта.


### Принято после Y,03.11.2026

Y1440d51:6/6guard, live10/10/dropcount5/reject0, полный REC-B snapshot/check0/afterstable,
manifestPLANNED_NOT_ARMED; working on сохранён. Xtestcontractbug закрыт, product не менялся.
Zпередаёт19cooperative sandbox fence cases, три process cases, без XGW/runtime integration.
Реальные fence/driver/activegatesfalse. Root Ymaterial не используется. Реальная Z NOT_RUN.
Подробно ReviewY/ADR-REC-C-OWNERSHIP/ТЗ Z; полнаяwave3/D1-on/faults остаются открыты.


### Поправка после X,03.11.2026

X283bb12:26/26 cases, snapshot GUARD_LAYOUT/partial; check/after NOT_RUN, on сохранён.
В тестовом X ошибочно требовался forward priority5. Product render_guard задаёт10;
старые «forward/drop5» означали hook forward и число host-drop правил5, не priority5.
Прежний observer forward priority не измерял. Исторические записи не являются указанием
менять живую таблицу. Новый Y v2 строго10/10 и safe details, шесть новых регрессий,
полная qualification REC-B одним пакетом. Реальная wave3y NOT_RUN; REC-B не закрыт.
Review-wave3x содержит исходниковое доказательство и пределы реального X.


### Принято после реального W,03.11.2026

W e670ceb:25/25 synthetic model cases, working on/status bookends сохранены.
REC-A принят в своём scope; реальная автономность/recoverytime не проверены.
X реализует кандидат REC-B snapshot и check-only nft-c без применения правил,
26 validation cases/четыре автоэтапа/один отчёт. Material root0700/0600, gatesfalse.
Writer inventory описан в REC-C-WRITER-INVENTORY; fence/driver НЕ реализованы.
Реальная wave3x NOT_RUN. D1-on/faults по-прежнему требуют независимого возвратаon.
Рабочая LAN считается работающей, единственный ThinkCentre не LAN-клиентский proof.


### Принято после реального V,03.11.2026

V be1fc1b завершён/1.747с/context/on сохранны. SameSB/cache с U; один missing_identity,
0 mismatch/ambiguity. В текущей паре поколений44VLESS отличаются только категорией tls,
identity/groups0. Журнал2ч/708строк/EOF/rc0 успешно получен, writer/причина не установлены.
Review-wave3v завершает эту readonly ветвь. Следующий открытый этап — возврат исходного on.
ADR-RECOVERY-ORIGINAL-ON и PR-SPEC-WAVE3-ON-RECOVERY определяют REC-A–E.
Реализована чистая модель REC-A, без сетевых/служебных/файловых операций модели;
W передаёт25 синтетических сценариев на ThinkCentre одним пакетом/отчётом.
Реальный driver/fence/recovery НЕ реализованы, simulate не разрешает fault/D1-on.
ТЗ W не создаётtimer/guardian и не меняет сеть/службы; реальная wave3w NOT_RUN.


### Принято после реального U, 03.11.2026

Отчёт f5a5928: U завершён за3.442с, контекст/рабочий on сохранены, запросов0.
Исправленный тестовый JSON-разбор: 101 supported, 66/67 default VLESS equal,
0 mismatch, 1 no_unique; reference12/12; граф141/badcounts0; units14/14.
U8 query_ok=false/TimeoutExpired — журнал не доказал автора/причину дрейфа.
U44 изменённых endpoint-объекта не равны44 изменившимся серверам: возможны группы.
Последние cumulative T: RX5 517 331/TX139 736 077 байт, сумму cumulative не считать трафиком.
Исторический Rnegative/клиентские NOT_RUN не переписываются текущей сверкой.
Review-wave3u фиксирует пределы. V объединяет классификацию gap, категории объектов,
связь U→current и один bounded journal; без повтора принятых опытов/активных запросов.
Второй неуспех журнала не повод для следующего микроповтора. Реальная wave3v NOT_RUN.
Доступен только ThinkCentre; LAN считается работающей, host-пробы не LAN acceptance.
Полная wave3 открыта; D1-on/faults требуют независимого возврата исходного on.


## Что показал реальный прогон

[Отчёт wave3b](https://github.com/1521572-lang/xgw/blob/cc0b021a9204a1238903628fb8766af5e47519f6/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3b-2026-11-02.md#L23-L42):
три восстановления off успешны, связь модели/владельца сохранилась, оба carrier1 в точках
измерения.0.137–1.018с — только выполнение restore после истечения15с lease. Это не полный
срок от последнего pulse и не доказательство поведения при enable. Установка дважды прервана
из-за ритма оператора; rc0 нет, enable/on-reinstall/D1/D2 не проверены. Доказательств физического
отключения WAN-порта нет; непрерывного carrier-мониторинга также не было.

## Граница ответственности

WAN несёт двунаправленный транспорт к провайдеру и VPN-серверу. LAN получает обычный трафик
клиентов и возвращает ответы. У XGW по TPROXY пользовательский поток приходит с LAN в локальный
Xray, а внешнее соединение к VPN-серверу создаёт процесс ядра и отправляет через WAN. Поэтому
«управлять профилем WAN» и «участвовать в маршрутизации через WAN» — разные действия.
Разделение локальных output и транзитных forward-путей описано в
[Netfilter hooks](https://wiki.nftables.org/wiki-nftables/index.php/Netfilter_hooks);
TPROXY требует локальной доставки по policy routing
([документация ядра](https://docs.kernel.org/networking/tproxy.html)).

Для VPN только клиентов LAN достаточно перехватывать входящие с LAN потоки и обеспечивать
маршруты/обратный путь. Но требования этого шлюза шире: есть трафик самой Ubuntu и Tailscale.
Автоматическое `capture.local=false` уберёт существующий путь tailscaled через Xray. Поэтому
его не принимать как исправление потери связи. Сохранять route/fallback Tailscale и различать
соединения самого tailscaled и трафик устройств tailnet через exit-node.

В коде уже разграничены:
- [LAN/lo ingress и host output](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nft.py#L645-L705): входящий WAN в TPROXY не направляется;
- [политика Tailscale](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/config.py#L123-L133): route и автоматический DERP fallback;
- [независимый guard](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nft.py#L1052-L1115): host output и выбранные forward ingress, не выключение NIC.

Чистая установка пока имеет отдельное legacy-изменение WAN:
[wan_ipv6_off](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nm.py#L273-L316)
может изменить ipv6.method профиля и вызвать device reapply; для netplan используется
sysctl disable_ipv6. Это существующий код, не новый вызов отключения карты в guard. Наличие
такого пути не доказывает, что он вызвал D2. Обычное включение перехвата и повторная установка
должны рассматриваться отдельно.

## Доработки для отдельного PR

1. **Явное владение профилем WAN.** В обычном цикле VPN сохранять адреса, DHCP/PPPoE,
   default route, DNS, MTU, IPv6 и активность профиля WAN. Не выполнять device disconnect,
   connection up/down, reapply/перезапуск NetworkManager ради enable/disable/failover.
   Установку физической LAN-сети отделить от обновления runtime-кода и политики VPN.
2. **Миграция старого IPv6 без автоматического переподключения.** Проверить journal nm_wan
   и sysctl: переключение новой политики не должно незаметно ни повторно выключить IPv6,
   ни вернуть старый профиль. Сохранить фактическую текущую настройку до отдельной операции
   миграции. IPv6 не должен получить прямой обход защиты LAN/host: существующие nft v6_guard,
   перехват и исключения внешних VPN/Tailscale-соединений проверить до удаления legacy writes.
   Просто удалить wan_ipv6_off без этой проверки недостаточно.
3. **Разделить политику клиента и управления.** LAN/host VPN и условный Tailscale сохранить.
   Для Flash выделить проверяемый служебный путь по отдельному процессу/cgroup/netns, с явным
   DNS и маршрутами. Не разрешать весь трафик пользователя/root, не делать общий established
   accept: это может открыть обход VPN. Связь Flash, Tailscale и пользовательский VPN проверять
   раздельно; исправность Tailscale сама по себе не доказывает доступность модели.
4. **Реальная приёмка.** До/после enable, disable, смены узла и сбоя ядра сравнить хеши
   разрешённого набора свойств WAN-профиля, IP/default route/DNS/MTU и наблюдать carrier.
   Проверить новые LAN TCP+UDP, IPv6-политику, прямой/черезVPN/DERP-fallback Tailscale и канал
   Flash. До этого независимая локальная страховка обязательна. Не считать socket.connect
   через TPROXY доказательством внешнего TLS/получения тела.

## Следующий безопасный опыт

Отчёт b7be627 подтвердил автономные окна25/45с и сохранение WAN через прерванную установку.
Затем по отдельной команде владельца установка завершилась с rc0 вне окна; это не PASS
45-секундного бюджета. Дальнейшая переустановка ради завершения не нужна.

Отчёт wave3e9677cb9 подтвердил enable rc0 за9.279с и возвратoff за25.167с (restore0.167с),
WAN6/6True, carrier1 в точках. Во времяon plain TCP получил ConnectionRefusedError за0.089с,
а marked-проба того же этапа прочитала32769байт/HTTP200. Вoff обе пробы успешны. Причина
различия путей не установлена; ни физическое отключение WAN, ни ТСПУ этим не доказаны.
Связь во времяon UNKNOWN; loaded в Markdown UNKNOWN без значения, нужен исходный артефакт.

Отчёт wave3f221eecb повторил plainTCPrefused0.065с при исправных inbound/listener/proxy lookup;
loadednull/child_deadline4с. Один изолированный netns A/B воспроизвёл отказ host guard вOUTPUT
после reroute: hook видит прежний WAN oif. Новый host guard проверяет фактический oif в
POSTROUTING, при неразрешённом выходе drop. Forward guard прежний. Никакого нового accept
поproxy mark нет. Причина ThinkCentre ещё требует подтверждения; факты и границы в
`ADR-HOST-GUARD-POSTROUTING.md`.

Wave3g6c93e22 успешно установил nft.py; plainon впервые200/32769/0.354с, marked тоже успешен,
rollback25.172с/restore0.171с/nft0/WAN6/6True. Повторять обновление не нужно. Фактический
on-hook и loaded не получены: test child4с остановился до layout. Его ранняя стадия включала
тяжёлый inbound_problem/rules(on), поэтому сборщик переставлен, без нового продуктового PR.

Wave3hbc24353 повторил plainHTTPS успех0.466с, restore25.161с/0.161с/nft0/WAN6/6True.
Loaded8сdeadline иguard deadline_or_error остаются неизвестностями. Последнее не является
доказанным timeout, подробнее в REVIEW-REAL-MACHINE-0.2.0-wave3h.md.

Wave3ib32669a впервые подтвердил actualpostrouting10/forward/drop5/reject0, plainтретий
успех0.428с, rollback25.126с/WAN6/6True. Короткийhost-кейс принят; loadedchild8состановился
на_desired_problem. Историческаяпричинаh остаётсянеизвестной. Подробно REVIEW-REAL-MACHINE-0.2.0-wave3i.md.

Wave3j8cdf9bc подтвердил loaded=true/measured/complete/rc0 приon в8с child-бюджете,
actualguard JSON0.025с postrouting10/forward/drop5/reject0, plain0.307с/marked0.290с
с HTTP200/32769 байт. Enable8.034с0, rollback25.130с/restore0.130с/nft0/WAN6/6True.
Новая parser-версия NFT10c1 установлена один раз, четыре файла совпали, dry nft-c успешен.
Принят короткий host-кейс и его измеренное соответствие. Состояние после HEALTHY/off/
pooloff; непрерывная связь вon, LAN/UDP/IPv6/DNS/Tailscale/E4/D1-on ещё не доказаны.

Исторический протокол wave3k (до нового указания владельца): только чтение приoff для
получения предпосылок независимой LAN/E4/Tailscale приёмки. Не повторять G1/установку/enable,
не запускать захват, не менять WAN/LAN/sysctl/config/Tailscale/ядра. Наличие инструмента,
lease или neighbour не закрывает гейт. Отсутствующие ответы владельца — UNKNOWN.
При следующем активном опыте независимый локальный возврат обязателен; incoming outage
>1 минуты нельзя восстанавливать следующей командой модели. Полная волна3 остаётся открыта.
