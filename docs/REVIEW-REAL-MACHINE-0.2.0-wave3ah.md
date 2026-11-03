# Разбор AH: readback принят; AG129 принят в пределах source fixture

Актуализация после AI04.11.2026: [AI78 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ai.md),
AGHOLD ранее снят exactAH. Готов [следующий укрупнённый AJ328](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aj.md).
Ниже история соответствующего отчёта; прежние NOT_RUN не отменяют actualAIreview.


[AH report](https://github.com/1521572-lang/xgw/blob/2479d76b86b3543b17a5c9c2b61e2a3807490f88/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md#L1)
доставлен fast-forward, commit2479d76b86b3543b17a5c9c2b61e2a3807490f88.
Readback delivery2669a2aa82d6f56b4cd43781f4ad07bfe1470b7a,
tree663ba88f4f37261008f8d2bad47271eee7a0193b. 23:44:10–23:47:08MSK03.11.2026.
Проверены все386строк, exactIDorder/strictbool/int/null/sourcechecks/reportdifferences.
Из публичных таблиц восстановлены normalizedrecords и вновь сформирован Markdown:
автоматический prefix БАЙТ-В-БАЙТ совпал с report. Это offline проверка передачи,
не чтение private notes архитектором, не новый прогон cases и не cryptographicauthentication.

## Принятие AG и расхождения прежнего отчёта

[AG129](https://github.com/1521572-lang/xgw/blob/2479d76b86b3543b17a5c9c2b61e2a3807490f88/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md#L9):
FINAL_RECORDED/129of129/frozenidentitytrue/contracttrue/0contractmismatch/0controlissues.
Сохранённые actual expected/observed отвечают pinnedhelper8045d3a. В прежней publictable
расходились54expected/36observed enums;88rows содержали приблизительные времена.
Всего88различающихсяrows, НЕ54+36+88разныхcases. Actual batch21933мс, суммаcaseelapsed18141мс,
не смешивать эти времена. receipt1rows32/UNKNOWN1rows7 — агрегат строк, НЕ32сетевыхприменения.
28OWNEDwriter variants +3OWNEDconstructors +1positiveintegration;7UNKNOWNnegativecases.

HOLD снят только для AGoptional-source/fake-effects qualification. AH разрешил
противоречие сохранёнными точными полями. Публичный AGreport остаётся ошибочным в
указанных местах и сохраняется как история; использовать exactAHtable. Причину ручного
расхождения и происхождение mutableownerfiles AH не устанавливает. Нельзя утверждать
неисполнение старогоworker, умысел или новый повтор129tests.

## Архивы AF и AE

[AF145](https://github.com/1521572-lang/xgw/blob/2479d76b86b3543b17a5c9c2b61e2a3807490f88/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md#L158):
145of145/contracttrue/0differences/0mismatches, batch25269мс/casesum20903мс.
42receipt1rows/6UNKNOWN1rows. Прежний accepted scope сохранён, не новый AFпрогон.

[AE112](https://github.com/1521572-lang/xgw/blob/2479d76b86b3543b17a5c9c2b61e2a3807490f88/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md#L323):
112of112/contracttrue/0differences/0mismatches, batch13030мс/casesum9853мс.
5receipt1rows включают reusedplan negative P_USED с прежней квитанцией и4positiveC;
это НЕ5новыхcompositecompletions. UNKNOWN1rows13. Нельзя назвать112применениями.

Во всех3архивах auditregisteredtrue/violations0/workloadsubprocess0/network0/liveops0/
globalstopfalse/remaining0/source116/7runtimeflagsfalse. Controls прочитаны изactual,
не подставлены вместоnull. Архитектор проверил формат/контракт по публичной передаче,
не непрерывное состояние машины, installedruntime или authenticity notes.

## Исполнение и рабочий режим

[Footer](https://github.com/1521572-lang/xgw/blob/2479d76b86b3543b17a5c9c2b61e2a3807490f88/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md#L461):
NNP0/sudo0/collect0/show0/HEALTHY_ONbeforeafter/poolOFFbeforeafter/linkALIVEbeforeafter/
versionsunchangedtrue/owneractions0. Collect0 означаетreadback, show0 проверкуегоформы;
worker_exit_rcNOT_COLLECTED. 386oldrows/0newtests. NoYroot/новойSSHописи/kernel/PID/RPDB/
installed116/rootDAC/realboot/сети/служб. HEALTHYtimestamp19:28 противAF15:31 по-прежнему
без доказанной причины/момента: не выводить внешнийрестарт/ТСПУ/«междуrun».

## Следующий готовый пакет

[ADR AI](ADR-REC-C-FILES-COMPLETION.md) и [единое ТЗ AI](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ai.md):
новый dormantFileCompletion +78НОВЫХprivatefixturecases/одинstart/автопереходы/
immutablepartialreport/одинreport. ConcreteFILES observation вместо literalTrue,
exactrolecoverage и unsupportedotherdomains→UNKNOWN. Source117/7A10M, только1новый
source относительноAG/AH; прежние116source/oldhelpers/units/config unchanged.
Installedruntime не менялся. RealAI NOT_RUN;14unique narrowchecks/RuffPASS локально.
LiveC BLOCKED_BOOTSTRAP. Mandatoryruntimegraph/version/boot/pathalias/interprocess/
kernel/API/process/routes/mode verifiers/repair/bootstrap ещё открыты. Fullwave3/LAN/
45s/performance/allTS/DAE gates прежние. SourcefixturePASS не разрешает liveinstall/fault.
