# ADR: точное чтение existing artifacts перед принятием AG

Актуализация после AI04.11.2026: [AI78 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ai.md),
AGHOLD ранее снят exactAH. Готов [следующий укрупнённый AJ328](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aj.md).
Ниже история соответствующего отчёта; прежние NOT_RUN не отменяют actualAIreview.


Обновление04.11.2026: [AH exactreadback](REVIEW-REAL-MACHINE-0.2.0-wave3ah.md) принят;
AG129 принят в sourcefixture scope, HOLD снят. Ниже исходный разбор до получения AH;
он сохраняет историю противоречий publictable. Originaltestreports не переписаны.
Следующий пакет [AI78](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ai.md), realAI NOT_RUN.


Статус03.11.2026: AGHOLD. Продуктовые доработки приостановлены до evidence reconciliation,
это не пользовательский pause/goalstatus и не причина изменять сеть. [Разбор AG](REVIEW-REAL-MACHINE-0.2.0-wave3ag.md).

AGreport заявляет129/129, но54строки expected_return противоречат источнику,88времён
приближены. Исправление текста догадками не допустимо. Принято: одно чтение сохранённых
AG/AF/AE results, без исполнения старых helpers/product. Включение AF/AE — независимая
проверка целостности прежнего ручного переноса за один заход, НЕ повтор accepted batches.

tests/stand/wave3_evidence_contract.json содержит fixedprofiles/386IDs/source reference
SHA, knownexpectedcasechecks и только разрешённые поля уже публичных таблиц. Ожидания
не подставляются в actual columns. Source_context и actual_source_fields в report отдельны.
Helper readout использует только stdlib files/hash/json, не subprocess/socket/xgw imports.

Каждый архив: owner700, frozen batch/support/manifest600, strict SHA, exact116pyinventory,
sourcefile≤2MiB/total≤16MiB, no symlink/extra/insecuremetadata. Read NOFOLLOW/NONBLOCK,
sizebound/stable inode+mtime+ctime, duplicatesJSONreject. Started/claimed strictboolTrue,
не process-exit proof. Summary читается первым; progress допускается только при отсутствии
summary, не при его corruption. Unsupportedschema отказывает этому профилю; другие идут.

Normalization принимает exact caseIDprefix, boolpassed, integerexactms, nullable typed
known details, sanitized publicerrors. Unknownprivatefield запрещён; raw reason/traceback/
argv не публикуется. Genericexceptionclass внеwhitelist →OTHER_EXCEPTION_CLASS, path вне
publicsourceinventory→UNKNOWN. Controlflags/IOcounts сохраняются фактическими илиnull,
не принудительноfalse/0. Wrongmarker/counts/scope/IO/runtimeflags блокируют consistency.
Checkpoint/failed/missing/contractmismatch не превращаются в all_case_checks_passed.

Различаются: collectioncommandrc, sourceartifactavailability/identity/schema, final vs
checkpoint, actualcasepassed, sourcecontractconsistency, publicreportdifferences и
окончательное принятие архитектором. EVIDENCE_READBACK_RECORDED означает завершённую
попытку сбора, даже если всеprofilesUNAVAILABLE. WorkerexitrcNOT_COLLECTED остаётся.
129PASSstatement без exact saved rows не закрываетAG. Отсутствие файла не доказывает,
что worker не запускался; owner может менять файлы, криптографической authenticationнет.

Collector пишет EXCL только в новый ~/xgw-w3ah: marker/readout/report-data/receipt.
SHAreceipt и deterministic renderer защищают от случайного изменения новой нормализованной
передачи; они не защищают от root/user, способного пересчитать оба. Canonical reportdata
prefix нельзя редактировать; вручную заполняется только строгоtyped executionfooterJSON.
Publication проверяет prefix и whitelistfooter. Raw oldfiles/hashes/private fingerprints
не отправляются. Exactms передаются без округления, missingcounts не заменяются нулями.

Новый ТЗ содержит2artifactfreeze, одно foregroundcollect/одноshow/одинreport, baseline/
NNP/sudo/privacy/source STOP. Нет sourcecopy/newfixture/process/threads/services/таймеров/
kernelrules/обрывов. Source116/6A10M и все прежниеhelpers неизменны. NoAHrepeatedcollect
приобрыве: show/partialreport, не rerun старыхbatches. NoYroot/casefiles/liveconfigs/logs.

Локально9 necessary synthetic tests: enumcontradiction/nullablecheckpoint/typeboolcounter/
unexpectedfields/privacy/markerconsistency/symlink+mode/duplicatesJSON/renderroundtrip.
Реальные386архивныхстрок нами не читались. AHNOT_RUN до отчёта Flash. После него —
принятие AG, конкретные evidencefixes или подтверждённыйsourcefix; не следующая wave
при недостоверных исходных результатах. Fullwave3/bootstrap/LAN/performance/DAE gates прежние.
