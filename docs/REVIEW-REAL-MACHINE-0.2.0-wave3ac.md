# Разбор wave3ac: 51/51 принята, следующая проверка реальных source entrypoints

[Отчёт AC](https://github.com/1521572-lang/xgw/blob/04a21bdc003493dc0c6bfacb360ee43856ccfcc6/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ac-2026-11-03.md)
принят fast-forward, commit04a21bdc003493dc0c6bfacb360ee43856ccfcc6.
03.11.2026,14:42:04–14:50MSK; batch16987мс. Tested8aae0fb06396df406ebe9221173e5bb426230c90,
tree2275eb2061db7631910d8e0fe362cbfc9232aacb. Sourcebaseline351: тридобавленияownership.py/
ownership_adapters.py/ownership_diagnostics.py; installedruntime неизменён.
Все5SHA/freeze0700/0600 подтверждены по ТЗ, sourcepackageprivate, неinstalledXGW.

## Принятое evidence

Start/monitor/show/shape rc0 раздельно; finalsummary.json/WRITER_INTEGRATION_BATCH_RECORDED,
FINAL_SHAPE_VALID/ALL_CASES_PASSEDtrue, collector_exit_rcNOT_COLLECTED. Все51/51:
A28/28/B16/16/D7/7. B16busyholderrc−15/cleanupconfirmed. Workloadcollectorchildren8 и
driverlaunchobservations7 отдельно; realprocesscases8/8. Принимается только описанныйscope.

D01/D02вернулиfakefileкBASELINE послеcontrollerexit0/crash9 за1553/1548мс отfakeARMED.
D03/D04EXPIRED_UNUSED за1543/1548мс, D05expectedFAILED за1550мс, D06/D07REFUSED доarming:
timingfalse/elapsednull/budgetnull. Положительныхrestorations2, expectedfailure1,
refusals2/unused2. Это не7возвратов, неsystemd/cgroup/suspend/reboot/power/45ссетиproof.
GrandchilddriverexitrcNOT_COLLECTED. Collector наблюдалфайлы, не посылал restoreкоманду.

**Исправление сводки A в отчёте:** по поимённым строкам/sourcecases COMPLETED10
(A01–A07,A20,A21,A27), REFUSED2, UNKNOWN14, terminalexceptioncases2(A22/A23).
Последние прошли проверку проброса исключений, но не вернули ExecutionCOMPLETED.
Фраза «COMPLETED11/UNKNOWN15» арифметически неверна. Итог28casePASS и общий51PASS верны;
не переписывать исходный отчёт и не повторятьAC ради исправления сводки.

Фразу «предокcce» читать по Git: ABcceпредокtestedAC8aa, не наоборот. NNPканала0/sudo0/
owneractions0; HEALTHY/on/pool/версии/связь сохранны вbookends. НетновыхYkernel/RPDB/PID/
configafter/installed110tree/rootDAC/realboot. YsnapshotPLANNED_NOT_ARMED/нечитался.
Network/liveops0; все6runtime/repairflagsfalse. Продуктовыйдефект не выявлен, установка
по отчёту не требуется. AB32/AA22/Z19/Y6/X26/W25/AC51 далее не повторять.

## Что теперь подготовлено

[ADR AD](ADR-REC-C-OPT-IN-SOURCE-HOOKS.md) и [единое ТЗ AD](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ad.md):
130новыхcases =38вариантов реальных sourceметодов×3режима +16контекстных/error/readerпроверок.
Это первый opt-in hookкандидат в Capture/Backend/Applier/SingboxCore/Job/ApiClient/managed.
Новый Coordinator сохраняет исходныйresult/exception, nestedroles делятодинticket,
пойманнаяnestederror taintsouter. Async/generator/inheritedcontexts отвергаются.

Старые bodyсохраняются: меняются decorators/optionalconstructorfields, managedbody вынесен
в _update_locked. Существующие callsites coordinator не передают: Noneсохраняетlegacy,
**не обеспечиваетfence**. Actorbinding/handshake/realverifiers/repair/bootstrap ещё неготовы.
Нельзя устанавливать этоткандидат и выдавать OptionalNone за защищённый runtime.

Flash копирует exact114sourcefiles по publicSHAmanifest в usernotes; импорт только
privatefrozen_adpackage. Runner/API/service/TUNeffects подставные. Worker блокирует
process/socket и запись вне notes; это regressionguard проверенного кода, неsecuritysandbox.
Сеть/правила/службы/установленныйXGW не изменяются. Восстановления дажеfakeD повторнонет.

Локально8узких tests/RuffPASS; ASTпроверка сохраняемостистарыхbody и командыТЗ отдельно.
Полные130/sourcefixturecalls наThinkCentre NOT_RUN до отчёта. Одинstart/автопереходы/
partialreadout/одинMarkdown, безмикрозаданий. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/
performance/allTS открыты, неwave4/DAE. Ожидается reportwave3ad-ДАТА.md.
