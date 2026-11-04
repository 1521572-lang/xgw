# API AQ1: wire fixtures, scoped evidence и закрытый host boundary

04.11.2026. Source-only candidate. Offline qualification READY после полного freeze;
real AQ NOT_RUN. Host profile BLOCKED_SCOPE_REVIEW / HOST_NOT_RUN. Installed runtime
не изменён. Ни один результат API не является разрешением C/D/E или runtime Verification.

## Типы и пределы

`ownership_observations.py`: SourceSpec, CapturePolicy, SourceResult, Decoded, Coverage,
ObservationEvidence, ObservationDecision; strict_json/canonical/project_public.
Конструкторы pure. Exact types, bool не integer, enums закрыты. SourceSpec допускает
только10 фиксированных строк SPEC_ROWS. Target не caller-defined path/argv.

Scopes: COLLECTOR_CONTEXT; UNIT_XGW/UNIT_XRAY/UNIT_SINGBOX;
PROCESS_XGW/PROCESS_XRAY/PROCESS_SINGBOX; NFT_IPV4/NFT_IPV6/NFT_GUARD.
Phase=BEFORE/AFTER/SINGLE. FixtureBackend принимает tuple до32 уникальных
`(scope_id,phase,SourceResult)`; raw bytes до1MiB. Нет callbacks, shell, dynamic imports.

CapturePolicy: child≤5s, total≤30s, stdout≤1048576, stderr≤16384, proc≤8192,
total_bytes≤4194304, max_age≤30s; каждый предел положительный exact int.
strict_json: cap≤1MiB, nesting≤32, container count≤8192; duplicate keys/nonfinite/
overflow float/invalid UTF8/truncation отказ. Это не arbitrary JSON API для private state.
UNIT/PROCESS/CONTEXT дополнительно≤8192bytes. JSON schema public1, profile AQ1.

SourceResult: collection enum, raw bytes, rc nullable exact int[-255,255], reason enum,
cleanup_confirmed bool. COMPLETE требует непустые bytes и rc0/null. Прочие rc не absence.
Decoded: COMPLETE/INVALID/UNSUPPORTED, canonical bytes, fixed reason.
Coverage всегда subset, domain_complete=false/global_complete=false.

## Wire decoders

UNIT: ровно Id/LoadState/ActiveState/SubState/MainPID по одному, UTF8 key=value;
Id совпадает с fixed target, MainPID decimal0…2^31−1. Будущие Active/Load enums
не угадываются. MainPID0/inactive/not-found не являются proof отсутствия процессов.
Известные5 свойств — не cgroup/executable/config identity.

PROCESS private wire envelope: ровно unit_scope/stat/net/mnt. stat — synthetic текст
proc stat, net/mnt — строки вида net:[1]/mnt:[2]. Эти значения исключительно private.
Parser comm допускает пробелы/скобки, suffix проверяет integer fields; starttime — field22.
Output canonical содержит pid/starttime/state/unit_scope/net/mnt, без comm.
Session требует UNIT BEFORE/AFTER с тем же положительным MainPID и PROCESS bookends.
Изменение любого выбранного поля делает context invalid; это консервативное UNKNOWN,
не вывод о падении/ТСПУ. Context collector отдельно boot/net/mnt, должен совпасть before/after.

NFT: envelope ровно nftables list≤1024 objects, JSON schema1. Поддержан ограниченный
structural profile table/chain/rule и optional metainfo. Family/table строго fixed;
таблица одна, chains уникальны, rule ссылается на объявленную chain. Rules сохраняют порядок.
Handle остаётся значимым. Counter packets/bytes проверяются как uint64, нормализуются в0.
Expressions: accept/drop/return/continue(null), counter, restricted scalar match по meta/ct/
payload. Полный список attrs/operators — в expression(); неизвестное UNSUPPORTED.
Sets/maps, jump/tproxy/mangle и прочие выражения пока UNSUPPORTED: не отбрасываются ради MATCH.
Terse не показывает элементы sets; полного KERNEL proof нет. Fixtures synthetic schema1,
не raw dumps ThinkCentre и не подтверждённая совместимость installed nft версии.

## Provenance и lifecycle

FixtureBackend создаёт только FIXTURE. LinuxReadonlyBackend.capture для любого scope
возвращает BLOCKED_SCOPE_REVIEW без I/O; параметра/JSON-флага для включения нет.
ProposedTransport/query и proposed_argv — unwired candidate, не путь host runner.
Поддерживаются только fixed absolute paths `/usr/bin/systemctl`, `/usr/sbin/nft`,
literal show/property и terse list table. Transport имеет streaming cap+1, deadline,
общий byte budget,≤9 children; cleanup только своего Popen child. Не root/service PID.
Executable final lstat policy не является полным ancestor/mount/exec race proof.
ProposedTransport._proc_stream/proc_context/proc_process и proposed_profile реализуют
unwired candidate: bounded zero-size proc stream, fixed self/PID namespace links, PID только
из успешно decoded UNIT, нет /proc/0; порядок9children/24proc-context reads. Ordinary
permission/missing/budget дают partial; cleanup failure прекращает дальнейшие reads.
Их positive paths локально проверены только fake I/O,4 новых stand cases без host calls.
Final executable/ancestor/proc mount policy, permissions, active issuer и actual wire
qualification требуют отдельного scope review. Это не включённый host collector.

ReadonlyObservationSession(policy, exact backend, clock_values=None, expected_states=()).
Все expected_states создаются независимо ДО collect и pin по identity/flat immutable values.
ExpectedState: scope, canonical JSON bytes, AQ1, origin FIXTURE/DECLARED. Пришедшее DECLARED
не доказывает installed baseline и не квалифицировано для actual MATCH.
Фиксированный fixture clock — tuple2…256 конечных неотрицательных floats; real clock
time.monotonic pinned by identity. Reversed clock/terminal error прекращает collect.
Никаких clock callbacks из JSON. Owner PID/thread проверяется, nested collect запрещён.

collect_once(scope,phase) выдаёт session-owned immutable handle, ≤32; duplicate scope/phase
не retry, а отказ. Context/UNIT/PROCESS BEFORE/AFTER нужны до finalize(). Raw evidence
до finalize предварительный. Latest scope replaces earlier authority: старый handle
не даёт cached success после свежего failure. После finalize новые collect запрещены.
Clock/budget failures не сбрасываются restart/retry внутри API.

compare_scoped(handle,expected=None): чужой/clone handle UNKNOWN; changed nested fields,
wrong expected identity/values, stale, unfinalized/drift/partial → UNKNOWN. Unknown wire
profile UNSUPPORTED. Scoped MATCH/MISMATCH только owned FIXTURE+independently pinned
FIXTURE expected после всех bookends. Expected отсутствует → EXPECTED_MISSING.
SESSION_CAPTURED зарезервирован, но активный issuer в AQ отсутствует. Caller origin/digest
или JSON не создают такой provenance. Imported public projection всегда IMPORTED_UNTRUSTED,
UNKNOWN/NOT_COLLECTED; runtime_authorized=true во входе запрещён.

Method/code/default reference checks и session-owned flat fields — cooperative regression
boundary. Не arbitrary globals/deep state seal, hostile Python/root sandbox, durable fence,
cryptographic remote attestation или доказательство загруженного installed кода.
Sequential reads не atomic snapshot, не устранение ABA/TOCTOU.

## Public JSON и интеграция

project_public принимает exact ObservationDecision, не dict/private evidence. Ровно12 keys:

```json
{"schema_version":1,"source_id":"NFT_TABLE","scope_id":"NFT_IPV4","provenance":"FIXTURE","collection":"COMPLETE","decode":"COMPLETE","decision":"MATCH","coverage":"STRUCTURAL_SUBSET","reason":"SCOPED_MATCH","source_rc":0,"elapsed_ms":0,"runtime_authorized":false}
```

Это пример синтетики, не отчёт машины. rc/ms nullable; null не0. Строки только known enums,
нет raw/argv/PID/unit-properties/boot/namespace/config/private hashes/exception texts.
Private envelope не сохраняется этим API. Stand сохраняет только sanitized details,
raw живёт в bounded in-memory fixture. Не выдавать чужой bool/class как authority.

aggregate_scoped возвращает UNKNOWN/COVERAGE_INCOMPLETE и сохраняет scoped decisions.
runtime_verification всегда UNKNOWN Verification. AP helpers/types/facade не меняются;
65AP contracts всё ещё7required/completenessUNKNOWN. FILES/API/MODE/ROUTES/MARKERS
не реализованы AQ; PROCESSES/KERNEL только subset. Writers/registry/receipt/repair
не вызываются. Daemon/CLI/installer/unit hooks не подключены, все7runtime gates false.

Stand markers: READONLY_OBSERVATIONS_BATCH_STARTED, ..._BATCH_RECORDED/PARTIAL,
..._REPORT_READY; scope OFFLINE_OBSERVATION_QUALIFICATION_HOST_BLOCKED.
Worker_exit NOT_COLLECTED.91cases — не87host operations. Источник будущего host протокола:
[ТЗ AQ](PR-SPEC-WAVE3AQ-READONLY-OBSERVATION-SOURCES.md); текущий host branch закрыт.
