# ADR AP: описание ресурсов, симуляция и dry-run подготовки запуска

Следующий этап: [ТЗ AQ](PR-SPEC-WAVE3AQ-READONLY-OBSERVATION-SOURCES.md), пока SPEC_ONLY.
Отдельные readonly sources/provenance не ослабляют simulation trust boundary AP.
Нового готового Flash runner или разрешения host collection это ADR не даёт.

Обновление04.11.2026: [AP211 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ap.md).
211/211/summary/byteexactprefix;C91/P20/A14/B17/T65/I4. Данныесимуляции не создают
runtimeквитанции: I3verificationfalse/receipt0/UNKNOWNwriter1. Каталог65требуетвсе7domains/
completenessUNKNOWN. HEALTHY_ON/poolOFF/linkALIVE/versionssame/bookendsсохранны.
Actualcollectors/provenanceНЕреализованы;all7gatesfalse/LiveCBLOCKED_BOOTSTRAP.
СтарыеAPcasesнеповторять. Ниже описаниедоactualAP;егоNOT_RUNустарелпослеэтойприёмки.


Статус: реализован source candidate AP-1…4; realAP NOT_RUN. Source124 против122,
добавлены только ownership_resources.py и ownership_resource_catalog.py. Существующий
runtime/units/defaultownership/daemonCLI/installer не изменены.

Проблема: успешная квалификация private FILES композиции не доказывает полноту
network/core effects или готовность запуска общего recovery. Нужны явные required
domains, сохранение UNKNOWN и отдельный план prerequisites.

Принято:
1. Immutable validated typed contracts, bounded explicit state identifiers/binding.
2. Per-domain comparisons и independent partial aggregation. Actual provenance и
   wire decoders отсутствуют; любой nonsimulation/unbound input UNSUPPORTED.
3. Pure bootstrapinventory/plan без system reads/writes или executable actions.
4. Explicit facade с runtime_verification(), который всегда возвращает UNKNOWN.

Trust boundary: origin=SIMULATION и Binding — caller-supplied namespace. MATCH
означает только согласованность simulation input с ожиданиями; не реальный ресурс.
READY_FOR_REVIEW означает, что описание simulated dry prerequisites полно. Оба
результата не permission. Decisions имеют иной тип, accepted() отсутствует;
ownership_adapters.execute требует exactVerification. Facade не конвертируетMATCH
в acceptedVerification. В runner три privateRegistry integration подтверждают
UNKNOWN writer/no receipt при MATCH/ACTUAL/UNKNOWN source. Это не runtime activation.

Source catalogue65 документирует реальные тела/calls/exactsourceanchors; domain
кандидаты консервативны, полнотаUNKNOWN и все7domains required. Не выдавать таблицу
за полный граф и не подключать FILES-only fallback к сетевым операциям.
ArbitraryJSON/Linuxsnapshots/host /proc/units/API не собираются. Explicit typed inputs
ограничены; constructor/inspect/planner не выполняютI/O. Callables как источник нет.

All7runtimegatesfalse/LiveCBLOCKED_BOOTSTRAP. Wholemandatorygraph/protectedpathaliases/
actualcollectors+provenance/boot/repair/independentoriginalon-code-unitrescue должны
быть реализованы и отдельно квалифицированы до live C/D/E/install/fault. Не включать
always_off. ThinkCentre имеет рабочуюраздачу HEALTHYon и толькоhost access; LANклиента
нет. Не обещать LANUDP/IPv6/DNS/performance/45srecoverability по этому пакету.

Следующая стадия после realAP: реальные ограниченные readonly source adapters с
доказаннымscope/identity/fullness, отдельно разрешённый сбор данных; затем whole
startupcomposition и независимый originalon/code/unit rescue. AP не исполняет
пункты будущегоroadmap и не ослабляет existinggates.

Приёмка AP: code+APIcontract+65exactanchors+данныйADR+atomiccommits+ONEFlashplan/
runner/manifest/template. Pure source cases/guard/freeze/real loader проверяются
до передачи без полного VM прогона. OriginalAO/ANreports и старыеbatches не повторять.
