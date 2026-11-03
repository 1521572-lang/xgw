# ADR REC-C: явное связывание writers, одно завершение composite и private file evidence

## Текущий статус — AH принят; AG129 принят; единый AI78 (04.11.2026)

[AHreport](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-2026-11-03.md) exactreadback
AG129/AF145/AE112=386existingrows/0newtests/0contractmismatch. [Разбор AH](REVIEW-REAL-MACHINE-0.2.0-wave3ah.md).
AGHOLD снят в optional-source/fake-effects scope. В прежнейAGtable были54expected/
36observedenum/88approxms расхождения, actualsavedreadback соответствует source.
88различающихсяrows, не сумма178cases. Originalreports сохраняются. AF/AE безdiff.
NNP0/sudo0/collect0/show0/HEALTHY_ON/poolOFF/linkALIVE/versionssame/owneractions0.
WorkerexitNOT_COLLECTED; mutableownerfiles не authentication. Старыеbatches не повторять.

[Единое ТЗ AI](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ai.md) и
[ADR FILES completion](ADR-REC-C-FILES-COMPLETION.md):78НОВЫХcases/одинstart/
автопереходы/partialsnapshot/одинавтоматическийreport. Толькоnewownership_completion.py,
117source/7A10M; все прежние116source/units/config/pyproject/standhelpers UNCHANGED.
Concrete fresh namedFILES completion +exactrole/resultpolicy; другиеdomains→UNKNOWN.
Это неglobalruntimeverifier/rolepolicy/pathalias/atomicsnapshot/activation. Runtimeнеwired/
installedнеобновлён, все7gatesfalse. RealAI NOT_RUN;13unique narrowchecks/RuffPASS.
LiveC BLOCKED_BOOTSTRAP; independent original-on/code/unitrescue доinstall/fault.
OnlyThinkCentre/workingLAN/HEALTHY/on; nooff/install/G1/WAN/LAN/TS/pool/config/service/
live rules. Host неLANproof. Fullwave3/45s/LAN/performance/DAE gates прежние. Ниже история.


Актуально03.11: [AF145 принято](REVIEW-REAL-MACHINE-0.2.0-wave3af.md),
[AG129 подготовлено](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ag.md),
[новый ADR pool/dependencies](ADR-REC-C-POOL-FLOW-AND-DEPENDENCIES.md). Далее история:
текущий declared boundary9actors/50methods/source6A10M; globalruntimegate false.

Актуальное состояние03.11: [AE112 принято](REVIEW-REAL-MACHINE-0.2.0-wave3ae.md),
[AF145 подготовлено](TEST-PLAN-REAL-MACHINE-0.2.0-wave3af.md),
[новый ADR source flow](ADR-REC-C-SOURCE-FLOW-AND-FACTORIES.md). Далее история прежнего
snapshot. Текущий boundary37/source6A8M/111sourceunchanged; installed runtime не менялся.

Статус03.11.2026: dormant source candidate, qualification AE NOT_RUN до отчёта.
AD130/130 принят: [разбор](REVIEW-REAL-MACHINE-0.2.0-wave3ad.md).
Установленный XGW/сеть/службы не меняются. Этот ADR не разрешает install/live fault.

## 1. Проблема и принятое решение

AD hooks сами по себе необязательны. Один actor с ownership=None обходит bookkeeping,
а два последовательных самостоятельных apply публикуют два поколения. Для будущей
composition нужен явный полный boundary и один outer ticket. Новая библиотека
[ownership_binding.py](../src/xgw/ownership_binding.py#L115) требует семь объектов:
Capture/Backend/Applier/SingboxCore/Job/ApiClient/PanelWriter, exact types и один exact
Coordinator. Конструктор проверяет аргументы/методы, не читает/создаёт registry.
Никакого implicit attach/default registry/env activation/daemon wiring.

SPECS/FUNCTIONS фиксируют32 hook methods:31 AD и PanelWriter.update, который вызывает
managed._update с ТЕМ ЖЕ coordinator. При prepare/run проверяется весь объявленный
набор, pinned registry/verifier identities, class/bound-function/role и PID/thread.
Подмена даже hook, не выбранного текущим планом, отказывает до admission.
Перед/после каждого шага и после result checker выполняется повторная проверка.
Отсутствующий/чужой coordinator не исправляется библиотекой.

Это контроль cooperating objects в explicit bundle. Он НЕ охватывает другие references,
прямые private helpers/runners, прямой managed._update_locked, installer/uninstaller,
все daemon/CLI/service hooks, alias защищённых путей и вложенные dependencies объектов.
Другие writers могут всё ещё работать в legacyNone. Глобальная mandatory binding
не реализована, bundle нельзя выдавать за runtime fence. Python-код владельца может
менять объекты/обходить facade; hostile-code isolation здесь не заявлена.

## 2. Контракт плана и составного завершения

Step содержит whitelist writer/method/tuple args/tuple keyword pairs; duplicate keyword
и keyword ownership отвергаются. Размер1–32. Plan требует callable accept(step,value),
только exact True. Caller обязан проверить business outcome каждого шага; например
"rejected"/"failed"/"deferred" не допускают следующий apply. Это caller assertion,
не ресурсный verifier. Аргументы внутри tuples — trusted caller objects, не deep copy
и не защищённая сериализация. Plan не принимает arbitrary top-level operation callback.

[PreparedBatch.run](../src/xgw/ownership_binding.py#L211) потребляет одну попытку ДО
проверки/admission. Даже REFUSED не разрешает retry этим plan. PreparedBatch не имеет
durable replay identity; пересоздание объекта/процесса не защищено этим флагом.
Runtime protocol ещё должен запретить unsafe recreation по uncertain результату.

Outer Coordinator.call(LIFECYCLE) допускается только без уже активного session.
Дочерние owned методы используют тот же coordinator, один LIVE ticket и union roles.
Результаты собираются в tuple, pinned verifier вызывается один раз после всех шагов.
До этого нет intermediate receipt/generation и recovery lease блокируется LIVE ticket.
Registry flock не удерживается на время business body. Final verifier обязан оценить
все требуемые ресурсы, а не только факт возвращённого результата.

Exception/terminal/failed accept/drift/file mismatch → UNKNOWN/blocking ticket,
нет итоговой receipt, дальнейшие шаги не исполняются. Частичные эффекты могут остаться:
sing-box file уже опубликован, Xray rejected. Это НЕ atomic side-effect transaction.
Автоматической компенсации/повтора/repair нет. Обратный порядок/откат нельзя изобретать
по общему bool; для него нужна отдельная проверенная outcome/postcondition policy.
Exception из business body сохраняется исходным типом через принятый Coordinator.
Ошибка final verifier становится MutationBlocked/UNKNOWN; terminal business exception
пробрасывается после best-effort bookkeeping. Completion ack uncertainty не success.

## 3. Конкретное файловое наблюдение

[ownership_files.py](../src/xgw/ownership_files.py#L56) добавляет PrivateFiles,
FileExpectation и FileEvidence. Все пути/UID/ожидания задаёт вызывающий код; defaults
на live root нет. Constructor проверяет только shape:1–32 unique safe relative paths,
точный SHA256 или absent=True, strict int mode/UID (bool не int policy).

observe открывает абсолютный root от anchor descriptor через каждый компонент
O_DIRECTORY|O_NOFOLLOW, затем descendants через dirfd. Root и descendant directories
должны быть expected owner0700. Named regular files: NOFOLLOW|NONBLOCK, exact mode/owner/
nlink1/size≤2MiB, read≤2MiB+1, before/after fstat и final nofollow path stat должны
совпасть по dev/inode/mode/uid/nlink/size/mtime/ctime; bytes hash сравнивается с заранее
заданным digest. Nonregular/FIFO/hardlink/symlink отказываются, не блокируют read на FIFO.
Ancestor replacement проверяется по directory identities, root повторно открывается
anchored traversal после всех файлов. Все descriptors закрываются finally.

Exact absence: только FileNotFound у последнего компонента. Missing parent, symlink
на missing target, wrong root metadata не означают absence. Ошибка возвращает fixed
reason/checked/matchedFalse без текста exception/path/hash. FileEvidence не является
Verification и не может само завершить registry. Нет chmod/unlink/create/repair.

Границы: это наблюдение named subset, НЕ whole inventory, не atomic snapshot нескольких
файлов, не защита от cooperating root writer после наблюдения, не hard realtime/read
deadline. Runtime C должен удерживать все writers и использовать полный protected-path
policy; kernel/API/process/live mode всё ещё отсутствуют. Directory0700 policy намеренно
ограничена private tree: нельзя автоматически перенести её на live /etc с другими modes
или chmod live paths ради прохождения. В AE root owner mismatch — user fixture, не rootDAC.

## 4. AE qualification и неизменность предыдущего source

Новые только два src модуля, helper/manifest и узкие tests. Все114 AD source files
байт-в-байт сохранены, включая четыре прежних ownership modules и семь изменённых
старых modules. Source baseline diff6A7M; новый manifest116 source files. Прежние AD
helper/manifest не меняются. Installed XGW не импортируется/не обновляется.

AE использует frozen support.py = exact AD helper, его fixtures/guard/package loader,
но НЕ старые CLI/batch/130 cases. Новые112 cases:32 hook shadows/14 bindings/12 boundary/
13 plans/17 composites/24 files. Одна summary, independent failures continue; audit,
unexpected filesystem failure или незавершённый thread — общий STOP, остальные NOT_RUN.
Контрольный runner/API/service записывает trace, не выполняет argv/network/service calls.
Положительных composites4, negative composites13; positive file observations3,
expected file refusals21. Не интерпретировать112casePASS как112 successful mutations.

Private freeze3 artifacts+116 source files, modes0700/0600, exact inventory/hashes.
Worker audit guard до source imports, accepted AD ограничения/security non-sandbox
сохраняются. Один thread проверяет foreign-context отказ, workload subprocesses0.
Таймаут монитора300с — observation limit, не гарантия возврата сети за45с.

Локально11 необходимых narrow regressions/Ruff/AST/ТЗ syntax. Полный112/thread/live
kernel/services/installed gateway нами NOT_RUN. Реальный результат только из отчёта.
Все семь runtime gates остаются false даже при112/112. Generic FILES assertion в
fixtures теперь использует concrete private reader, но полного runtime verifier нет.

## 5. Оставшиеся атомарные зависимости, до live перехода

1. Подтвердить AE на ThinkCentre; исправить только реальные source/fixture mismatches,
   сохраняя независимые branches и один следующий отчёт при необходимости.
2. Реальный composition root и межпроцессный/version/boot handshake для ВСЕХ writers,
   включая daemon/CLI/panel/servicehook/installer. Missing/legacy actor должен блокировать
   активацию глобально. Проверить вложенные actor dependencies/alias paths, не только facade.
3. Полные resource verifiers: expected configs/markers + nft/RPDB/routes/TUN/kernel +
   API/process identities + effective mode. Единый generation/outcome protocol и
   диагностируемый UNKNOWN при частичных side effects, ack error и missing evidence.
4. Interrupted state repair/boot migration по валидированному transition protocol,
   без prune orphan по PID/expiry и без автоматического promote stage. Сначала dry cases.
5. Bootstrap independent original on/code/unit rescue с проверяемыми dependencies и
   автономным deadline, только затем отдельное разрешённое C-install/D/E испытание.
   Всегда запрет always_off; incoming disconnect>1мин моделью не лечится.

Решение по deployment остаётся BLOCKED_BOOTSTRAP, даже если все dry cases зелёные.
Working LAN/HEALTHY/on сохраняются; host не LAN UDP/IPv6/DNS/E4 proof. Fullwave3/performance/
allTS не закрыты. DAE остаётся будущим dataplane ADR, не следующей live волной.
