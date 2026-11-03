# ADR: host guard после policy reroute


## Актуально после AD — единый AE112 bound composite пакет (03.11.2026)

[Отчёт AD](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ad-2026-11-03.md) проверен:
130/130,38LEGACY/38OWNED/38FENCED/16extras, audit violations0, network/liveops0.
[Разбор AD](REVIEW-REAL-MACHINE-0.2.0-wave3ad.md). HEALTHY/on/pool/версии/связь
сохранены в bookends. Причина изменения метки HEALTHY между прогонами не установлена.
AD130/AC51/AB32/AA22/Z19/Y6/X26/W25 не повторять. Семь runtime gates false.

[Единое ТЗ AE](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ae.md) содержит112 НОВЫХ cases:
32hook/14binding/12boundary/13plan/17composite/24file, один start/автопереходы/partial data/
один отчёт. [ADR AE](ADR-REC-C-BOUND-COMPOSITE-AND-FILES.md). Весь готовый safe объём,
без микрозаданий. Реальная AE NOT_RUN; локально11 узких regressions/Ruff проходят.

Source diff pin351 теперь6A7M, manifest116. Два новых dormant модуля binding/files;
все114 прежних AD source files, helpers/units/config сохранены байт-в-байт. Installed
XGW не менялся. Explicit bundle требует7 objects/32 hooks/один Coordinator и держит
один ticket для batch, проверяет drift между шагами. PrivateFiles читает exact named
fixture files без записи. Partial side effects возможны; UNKNOWN не retry permission.
4 positive composite vs13 expected negatives,3 positive file vs21 refusals — не112
успешных применений. Source inventory не installed116, file subset не atomic snapshot.

Глобальный actor/version/boot handshake, все runtime callsites/dependencies/path aliases,
real KERNEL/API/process verifier, repair/recovery/bootstrap ещё открыты. None legacy
остаётся unfenced вне explicit bundle. Нельзя устанавливать это как готовый global fence.
LiveCinstallation BLOCKED_BOOTSTRAP; independent original-on/code/unit rescue обязателен.
Nooff/install/G1/WAN/LAN/TS/pin/pool/config/service/live rules; always_off запрещён.
Only ThinkCentre/workingLAN/HEALTHY/on, host не LAN-client proof. Fullwave3/D1-on/faults/
LANUDP/IPv6/DNS/E4/performance/allTS открыты; неwave4/DAE. Ниже история прежних этапов;
ранний AD NOT_RUN заменён фактическим отчётом, это не runtime qualification.





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








Статус 02.11.2026: wave3g/h/i/j дали четыре plain HTTPS успеха. В wave3j
loaded=true/measured/complete/rc0 при on, actualguard postrouting10/forward/drop5/reject0.
Короткий host-кейс и измеренное соответствие приняты; полная волна3 открыта.
Точный разбор — REVIEW-REAL-MACHINE-0.2.0-wave3j.md.

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


## Факты и оставшаяся неопределённость

[Отчёт wave3f](https://github.com/1521572-lang/xgw/blob/221eecb115cfb8629d8c0a6d49fd2212e5fe745b/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3f-2026-11-02.md)
повторил отказ plain TCP за0.065с при успешном marked HTTPS32769/200. Inbound согласован,
IPv4 LISTEN на loopback есть, proxy lookup local/lo/tproxy; effective_mode=on. Enable rc0 за
6.183с, возвратoff25.146с, restore0.146с, WAN6/6True. Loaded on неизвестен: child_deadline4с.
Приёмочные гейты выполнения прошли; работоспособность ordinary host path не подтверждена.
Carrier1 в точках и успех marked не означают непрерывную связь модели; duringon UNKNOWN.

Исторический wave3e JSON содержит loaded неожиданного типа. Это согласуется со строковым
fallback старого sampler; точное значение безопасный фильтр не печатал. Формулировка старого
Markdown «поля нет» неточна. Это не доказательство loadedFalse и не новая неисправность ядра.

## Причина в изолированной фикстуре

Исходный guard проверяет oifname в filter OUTPUT10. Предшествующая route OUTPUT-chain меняет
skb mark и выполняет reroute вlo. Вывод из
[nft_chain_route.c Linux6.18](https://github.com/torvalds/linux/blob/v6.18/net/netfilter/nft_chain_route.c)
и [nft_meta.c](https://github.com/torvalds/linux/blob/v6.18/net/netfilter/nft_meta.c): новое skb dst
не заменяет исходный nf_hook_state.out этого hook; oifname следующего OUTPUT-chain может
показывать WAN. Это объясняет локальный reject при корректном отдельном route-get.

Один ограниченный unshare-netns A/B на WSL6.18.54.1 воспроизвёл именно этот вопрос, без Xray,
внешних сайтов или изменений сети хоста. Listener с IP_TRANSPARENT возвращал разные данные
относительно прямого сервера, поэтому accept проверял действительную доставку в TPROXY.

| Условие | Plain | Bypass-mark |
|---|---|---|
| off | DIRECT | — |
| исходный OUTPUT guard | ConnectionRefusedError | DIRECT |
| тот же guard в POSTROUTING | TPROXY | DIRECT |
| удалён proxy RPDB, новый guard сохранён | TimeoutError | DIRECT |
| удалена capture-table, новый guard сохранён | TimeoutError | DIRECT |

Все результаты получены в одном изолированном опыте. Тело product render_guard AST-совпало с
исполненным кандидатом, кроме поясняющей docstring. Это причинный результат фикстуры;
тождества ядра ThinkCentre/его причины и исправления на реальном шлюзе ещё не доказано.
Это не запуск полной VM suite, проверка VPN-транспорта, LAN, UDP, IPv6 или Tailscale.

## Решение и границы

[Изменён только render_guard](https://github.com/1521572-lang/xgw/blob/573b233bce881349e5ff4654600d3e077a9515f6/src/xgw/net/nft.py#L1052):

- host цепочка с прежним именем output переходит в filter POSTROUTING10, до SNAT;
- первая проверка iif!=0 возвращает пересылаемые пакеты: их защищает прежний scoped forward;
- исключения core/service/утверждённых direct соединений сохраняются;
- host отказ использует drop: reject недопустим в postrouting;
  это ограничение описано в [официальном nft manual](https://www.netfilter.org/projects/nftables/manpage.html);
- forward/transit остаётся на прежнем hook и с reject; guard не выставляет mark/ct approval;
- не добавлены accept поmark_proxy или общий established accept. При потере маршрута поток
  уходит к WAN и отбрасывается по фактическому oif, вместо прямого выпуска.

При отказе host клиент может получить timeout вместо немедленного reset. Это ожидаемая
смена отказа, не успех сети. Нельзя ради быстрого восстановления разрешить mark_proxy на WAN.
Остальные capture rules, RPDB, WAN/LAN profiles, sysctl, Tailscale route/fallback прежние.
Чистая установка всё ещё имеет legacy WAN IPv6-путь; этот PR не завершает его миграцию.

## Реальный следующий шаг

В [отчёте wave3g](https://github.com/1521572-lang/xgw/blob/6c93e22f153617168e8aa77afa2ad3ef7289462f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3g-2026-11-02.md)
G1 успешно установил новый nft.py с backup/SHA/dry nft-c. Повторная замена не нужна.
Plain приon впервые получил200/32769/0.354с, marked200/32769/0.380с; enable8.801с0,
возврат25.172с/restore0.171с/nft0/WAN6/6True. Guard layout неизвестен: diagnostic4с остановился
на phaseconfig до быстрых фактов. Работоспособность одного host-запроса измерена; полного
доказательства механизма/соответствия/стабильности это не даёт.

Найдено ограничение test helper: inbound_problem вызывает полную rules(on), включая GeoIP,
и стоял ДО чтения actual guard. Старый phaseconfig охватывал несколько операций; нельзя
выдать неизвестную задержку за доказанную медленную config.load/DNS/GeoIP.

Wave3hbc24353 дал повторный plain200/32769/0.466с, enable8.533с0, rollback25.161с/0.161с,
nft0/WAN6/6True. Loadednull/8сdeadline наphase loaded. Guard querydeadline_or_error не
доказывает timeout: catch объединял ошибки процесса/разбора. Внутри loaded вновь вызывается
сборка rules; ранний завершённый inbound не исключает внутренние стадии. Уточнения и точные
permalink: REVIEW-REAL-MACHINE-0.2.0-wave3h.md.

Wave3ib32669a подтвердил actuallayout JSON0.064с икороткий host-кейс: plain200/32769/0.428с,
marked200/32769/0.436с, enable8.524с0, rollback25.126с/0.126с/nft0/WAN6/6True. Fullchild8с
не завершился на method__desired_problem. Новый быстрыйguard не определяет заднимчислом
причину старогоdeadline_or_error. Точные пределы: REVIEW-REAL-MACHINE-0.2.0-wave3i.md.

PurePython профиль мотивировал узкое parser-изменение351fb54. В wave3j новая версия
NFT10c1 установлена с backup и SHA, dry nft-c успешен; render/guard прежние. Loaded приon
впервые measured true/complete/rc0 в8с child-бюджете, _desired_problem returned1.099с.
Actualguard JSON0.025с подтвердил postrouting10/forward/drop5/reject0 при capture=true
до/после. Plain200/32769/0.307с, marked0.290с, enable8.034с0, rollback25.130с/0.130с,
nft0/WAN6/6True. Trace truncated48 не отменяет complete verdict. Это не A/B benchmark
и не определение исторической причины дедлайнов. Переменные и пределы — review wave3j.

Исторический протокол wave3k (до нового указания владельца): только read-only опись
предпосылок при off. Без установки/G1/enable/таймеров/захвата и без изменения адаптеров,
правил, конфигурации, ядер или Tailscale. Новый продуктовый PR по отчёту j не требуется.

Layout/checkpoint/loaded — разные наблюдения; layout считает правила, не пакеты.
Короткий host-кейс и его measured соответствие приняты, но LAN/UDP/IPv6/DNS/Tailscale/E4,
D1-on/D2/scoped faults и полная волна3 открыты. Возврат в подготовленный off — механизм
согласованного опыта; непрерывная связь вon UNKNOWN. Следующий активный опыт требует
независимой локальной страховки, не следующей команды Flash.
