# Отчёт: XGW wave3ah — точное чтение сохранённых AG/AF/AE результатов

Автоматические таблицы. Старые workers не запускались; src/сеть/службы не менялись.
Readback не является повторным PASS или подтверждением происхождения owner files.
AG остаётся на сверке архитектора. worker_exit_rc=NOT_COLLECTED.

Delivery HEAD/tree: 2669a2aa82d6f56b4cd43781f4ad07bfe1470b7a / 663ba88f4f37261008f8d2bad47271eee7a0193b

## AG

State: FINAL_RECORDED
Rows: 129/129
All source-contract checks passed: true
Frozen identity verified: true

Reference tested HEAD: 8045d3a34020e201e0d8c744236bd0e65896264b
Reference helper/manifest/source: `{"helper_sha256":"d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6","manifest_sha256":"383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b","source_files":116,"support_sha256":"9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"}`

Controls: `{"active_faults_authorized":false,"audit_registered":true,"completed":129,"elapsed_ms":21933,"expected":129,"global_scope_stop":false,"installed_runtime_changed":false,"live_gateway_operations":0,"network_requests":0,"passed":129,"remaining_not_run":0,"repair_implemented":false,"runtime_actor_binding_implemented":false,"runtime_recovery_implemented":false,"runtime_verifier_implemented":false,"runtime_writer_fence_verified":false,"source_files":116,"unexpected_forbidden_io":0,"workload_subprocesses":0}`
Control issues: `[]`
Report difference rows: 88
Contract mismatch rows: 0

|Case|actual passed|source expectation|actual expected|actual observed|receipt/gen/unknown/stubs|other actual fields|exact ms|issues/report differences|error source|
|---|---|---|---|---|---|---|---|---|---|
|S_ENSURE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|68|[]|[null,null,null]|
|S_ENSURE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|161|[]|[null,null,null]|
|S_ENSURE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|116|[]|[null,null,null]|
|S_SUCCESS__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|117|[]|[null,null,null]|
|S_SUCCESS__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|269|[]|[null,null,null]|
|S_SUCCESS__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|111|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PARTIAL__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|104|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PARTIAL__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|196|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PARTIAL__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|104|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EMPTY__LEGACY|true|"FALSE"|"FALSE"|"FALSE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|113|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EMPTY__OWNED|true|"FALSE"|"FALSE"|"FALSE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|211|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EMPTY__FENCED|true|"FALSE"|"FALSE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|166|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EXISTING__LEGACY|true|"FALSE"|"FALSE"|"FALSE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|110|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EXISTING__OWNED|true|"FALSE"|"FALSE"|"FALSE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|199|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_UNAVAILABLE_EXISTING__FENCED|true|"FALSE"|"FALSE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|108|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_ROTATE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|113|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_ROTATE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|206|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_ROTATE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|105|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PRUNE__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|76|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PRUNE__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|159|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_PRUNE__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|135|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_ALL__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|158|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_ALL__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|248|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_ALL__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|138|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_NOOP__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|115|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_NOOP__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|191|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_RETIRE_NOOP__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|113|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_SAVE_CANDIDATES__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|132|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_SAVE_CANDIDATES__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|254|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|S_SAVE_CANDIDATES__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|157|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_RETIRED__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|137|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_RETIRED__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|237|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_RETIRED__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|149|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_SUCCESS__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|114|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_SUCCESS__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|273|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_SUCCESS__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|183|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_UNAVAILABLE__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|188|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_UNAVAILABLE__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|204|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_UNAVAILABLE__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|106|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_PARTIAL__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|111|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_PARTIAL__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|191|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_PARTIAL__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_TWO__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,2]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|150|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_TWO__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,2]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|256|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_TWO__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|103|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_NOT_DUE__LEGACY|true|"LIST"|"LIST"|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|64|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_NOT_DUE__OWNED|true|"LIST"|"LIST"|"LIST"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|161|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_NOT_DUE__FENCED|true|"LIST"|"LIST"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|114|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_CANDIDATES__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|105|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_CANDIDATES__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|195|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PRUNE_CANDIDATES__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|108|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_BACKEND__LEGACY|true|"EMPTY_TEXT"|"EMPTY_TEXT"|"EMPTY_TEXT"|[0,0,0,2]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|78|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_BACKEND__OWNED|true|"EMPTY_TEXT"|"EMPTY_TEXT"|"EMPTY_TEXT"|[1,1,0,2]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|162|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_REFRESH_BACKEND__FENCED|true|"EMPTY_TEXT"|"EMPTY_TEXT"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|112|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_NOTE_HANDSHAKE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|106|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_NOTE_HANDSHAKE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|211|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_NOTE_HANDSHAKE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|107|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_XRAY__LEGACY|true|"OUTCOME"|"OUTCOME"|"OUTCOME"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|93|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_XRAY__OWNED|true|"OUTCOME"|"OUTCOME"|"OUTCOME"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|147|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_XRAY__FENCED|true|"OUTCOME"|"OUTCOME"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|120|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_SINGBOX__LEGACY|true|"OUTCOME"|"OUTCOME"|"OUTCOME"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|65|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_SINGBOX__OWNED|true|"OUTCOME"|"OUTCOME"|"OUTCOME"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|172|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_PROXY_SINGBOX__FENCED|true|"OUTCOME"|"OUTCOME"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|110|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_PROXY__LEGACY|true|"ONE"|"ONE"|"ONE"|[0,0,0,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|104|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_PROXY__OWNED|true|"ONE"|"ONE"|"ONE"|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|201|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_PROXY__FENCED|true|"ONE"|"ONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|103|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_REACH__LEGACY|true|"ONE"|"ONE"|"ONE"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|99|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_REACH__OWNED|true|"ONE"|"ONE"|"ONE"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|212|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_REACH__FENCED|true|"ONE"|"ONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|102|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_TUNNEL__LEGACY|true|"ONE"|"ONE"|"ONE"|[0,0,0,13]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|315|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_TUNNEL__OWNED|true|"ONE"|"ONE"|"ONE"|[1,1,0,13]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|448|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_TUNNEL__FENCED|true|"ONE"|"ONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|126|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_CANCEL__LEGACY|true|"ZERO"|"ZERO"|"ZERO"|[0,0,0,2]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|66|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_CANCEL__OWNED|true|"ZERO"|"ZERO"|"ZERO"|[1,1,0,2]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|192|["REPORTED_EXPECTED_DIFFERS","REPORTED_OBSERVED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_CHECK_CANCEL__FENCED|true|"ZERO"|"ZERO"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|126|["REPORTED_EXPECTED_DIFFERS","REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_PROXY__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|125|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_PROXY__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|226|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_PROXY__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|106|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_TUNNEL__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|108|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_TUNNEL__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|194|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_TUNNEL__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|112|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_LIST__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|120|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_LIST__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|216|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|P_RECORD_LIST__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|104|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_EMPTY__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|64|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_EMPTY__OWNED|true|null|null|null|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|159|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_EMPTY__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|101|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_RETIRED__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|108|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_RETIRED__OWNED|true|null|null|null|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|199|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_RETIRED__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|140|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_PROVIDED__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|87|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_PROVIDED__OWNED|true|null|null|null|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|171|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|C_PROVIDED__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|106|["REPORTED_TIME_APPROXIMATE"]|[null,null,null]|
|E_FOREIGN_NONE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|58|[]|[null,null,null]|
|E_FOREIGN_OTHER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|60|[]|[null,null,null]|
|E_STORE_NOIO|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|59|[]|[null,null,null]|
|E_BINDING_NINE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|50|[]|[null,null,null]|
|E_POOL_STORE_ALIAS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|79|[]|[null,null,null]|
|E_POOL_RUNTIME_ALIAS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|52|[]|[null,null,null]|
|E_APPLIER_API_ALIAS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|58|[]|[null,null,null]|
|E_POOL_UNBOUND|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|50|[]|[null,null,null]|
|H_STORE_ENSURE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|55|[]|[null,null,null]|
|H_STORE_COMMIT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_STORE_PRUNE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|77|[]|[null,null,null]|
|H_STORE_RETIRE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|53|[]|[null,null,null]|
|H_STORE_SAVE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|57|[]|[null,null,null]|
|H_POOL_PRUNE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|48|[]|[null,null,null]|
|H_POOL_REFRESH|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|51|[]|[null,null,null]|
|H_POOL_CANDIDATES|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|61|[]|[null,null,null]|
|H_POOL_BACKEND|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|54|[]|[null,null,null]|
|H_POOL_HANDSHAKE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_POOL_CHECK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|60|[]|[null,null,null]|
|H_POOL_PROXY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|47|[]|[null,null,null]|
|H_POOL_RECORD|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|52|[]|[null,null,null]|
|E_PRUNE_ERROR|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|145|[]|[null,null,null]|
|E_RECONCILE_ERROR|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|141|[]|[null,null,null]|
|E_ROTATE_ERROR|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|141|[]|[null,null,null]|
|E_PROBE_ERROR|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|174|[]|[null,null,null]|
|E_STOP_ERROR|true|null|null|null|[0,0,1,13]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|444|[]|[null,null,null]|
|E_VERIFIER_FALSE|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|219|[]|[null,null,null]|
|R_SUMMARY|true|null|null|"DICT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|245|[]|[null,null,null]|
|R_NEXT_CHECKS|true|null|null|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|212|[]|[null,null,null]|
|R_SPENT|true|null|null|"OTHER_INT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|198|[]|[null,null,null]|
|R_HANDSHAKES|true|null|null|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|200|[]|[null,null,null]|
|R_VARIANTS|true|null|null|"LIST"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|206|[]|[null,null,null]|
|R_STORE_SNAPSHOT|true|null|null|"DICT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|205|[]|[null,null,null]|
|R_STORE_CANDIDATES|true|null|null|"DICT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|211|[]|[null,null,null]|
|I_REFRESH_CHECK|true|null|null|null|[1,1,0,4]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|242|[]|[null,null,null]|
|I_SECOND_FAIL|true|null|null|null|[0,0,1,4]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|239|[]|[null,null,null]|

Null не заменён ожиданием. Приблизительные времена из старых таблиц не копировались.

## AF

State: FINAL_RECORDED
Rows: 145/145
All source-contract checks passed: true
Frozen identity verified: true

Reference tested HEAD: d8598b4cd7ce99cd2f999af6d5bd2c4eead8ae75
Reference helper/manifest/source: `{"helper_sha256":"1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8","manifest_sha256":"ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82","source_files":116,"support_sha256":"9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"}`

Controls: `{"active_faults_authorized":false,"audit_registered":true,"completed":145,"elapsed_ms":25269,"expected":145,"global_scope_stop":false,"installed_runtime_changed":false,"live_gateway_operations":0,"network_requests":0,"passed":145,"remaining_not_run":0,"repair_implemented":false,"runtime_actor_binding_implemented":false,"runtime_recovery_implemented":false,"runtime_verifier_implemented":false,"runtime_writer_fence_verified":false,"source_files":116,"unexpected_forbidden_io":0,"workload_subprocesses":0}`
Control issues: `[]`
Report difference rows: 0
Contract mismatch rows: 0

|Case|actual passed|source expectation|actual expected|actual observed|receipt/gen/unknown/stubs|other actual fields|exact ms|issues/report differences|error source|
|---|---|---|---|---|---|---|---|---|---|
|P_SET_FREE_POOL_MODE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|109|[]|[null,null,null]|
|P_SET_FREE_POOL_MODE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|192|[]|[null,null,null]|
|P_SET_FREE_POOL_MODE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|120|[]|[null,null,null]|
|P_SET_FREE_POOL_PIN__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|98|[]|[null,null,null]|
|P_SET_FREE_POOL_PIN__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|205|[]|[null,null,null]|
|P_SET_FREE_POOL_PIN__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|101|[]|[null,null,null]|
|P_SET_TAILSCALE_DIRECT__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|102|[]|[null,null,null]|
|P_SET_TAILSCALE_DIRECT__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|191|[]|[null,null,null]|
|P_SET_TAILSCALE_DIRECT__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|97|[]|[null,null,null]|
|P_REPLACE_TAILSCALE_DIRECT__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|101|[]|[null,null,null]|
|P_REPLACE_TAILSCALE_DIRECT__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|202|[]|[null,null,null]|
|P_REPLACE_TAILSCALE_DIRECT__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|95|[]|[null,null,null]|
|P_SET_DEVICE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|106|[]|[null,null,null]|
|P_SET_DEVICE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|196|[]|[null,null,null]|
|P_SET_DEVICE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|129|[]|[null,null,null]|
|P_REPLACE_DEVICES__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|103|[]|[null,null,null]|
|P_REPLACE_DEVICES__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|204|[]|[null,null,null]|
|P_REPLACE_DEVICES__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|[]|[null,null,null]|
|P_SET_KERNEL_DEVICE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|104|[]|[null,null,null]|
|P_SET_KERNEL_DEVICE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|209|[]|[null,null,null]|
|P_SET_KERNEL_DEVICE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|103|[]|[null,null,null]|
|P_SPLIT_KERNEL_DIRECT__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|115|[]|[null,null,null]|
|P_SPLIT_KERNEL_DIRECT__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|188|[]|[null,null,null]|
|P_SPLIT_KERNEL_DIRECT__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|102|[]|[null,null,null]|
|P_SET_ROUTE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|112|[]|[null,null,null]|
|P_SET_ROUTE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|221|[]|[null,null,null]|
|P_SET_ROUTE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|131|[]|[null,null,null]|
|P_SET_SERVERS__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|113|[]|[null,null,null]|
|P_SET_SERVERS__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|206|[]|[null,null,null]|
|P_SET_SERVERS__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|118|[]|[null,null,null]|
|P_SET_PRIORITY__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|121|[]|[null,null,null]|
|P_SET_PRIORITY__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|223|[]|[null,null,null]|
|P_SET_PRIORITY__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|126|[]|[null,null,null]|
|P_SET_CORE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|138|[]|[null,null,null]|
|P_SET_CORE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|241|[]|[null,null,null]|
|P_SET_CORE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|[]|[null,null,null]|
|P_SET_STICKY__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|101|[]|[null,null,null]|
|P_SET_STICKY__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|205|[]|[null,null,null]|
|P_SET_STICKY__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|107|[]|[null,null,null]|
|P_SET_KERNEL_DIRECT__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|112|[]|[null,null,null]|
|P_SET_KERNEL_DIRECT__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|204|[]|[null,null,null]|
|P_SET_KERNEL_DIRECT__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|104|[]|[null,null,null]|
|P_SET_TAILSCALE_SERVE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|129|[]|[null,null,null]|
|P_SET_TAILSCALE_SERVE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|215|[]|[null,null,null]|
|P_SET_TAILSCALE_SERVE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|112|[]|[null,null,null]|
|P_SET_TAILSCALE_FUNNEL__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|101|[]|[null,null,null]|
|P_SET_TAILSCALE_FUNNEL__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|210|[]|[null,null,null]|
|P_SET_TAILSCALE_FUNNEL__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|108|[]|[null,null,null]|
|P_SET_TAILSCALE_ROUTE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|120|[]|[null,null,null]|
|P_SET_TAILSCALE_ROUTE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|201|[]|[null,null,null]|
|P_SET_TAILSCALE_ROUTE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|131|[]|[null,null,null]|
|P_DROP_TELEGRAM__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|117|[]|[null,null,null]|
|P_DROP_TELEGRAM__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|201|[]|[null,null,null]|
|P_DROP_TELEGRAM__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|111|[]|[null,null,null]|
|P_ADD_SUBSCRIPTION__LEGACY|true|"TEXT"|"TEXT"|"TEXT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|110|[]|[null,null,null]|
|P_ADD_SUBSCRIPTION__OWNED|true|"TEXT"|"TEXT"|"TEXT"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|197|[]|[null,null,null]|
|P_ADD_SUBSCRIPTION__FENCED|true|"TEXT"|"TEXT"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|107|[]|[null,null,null]|
|P_UPDATE_SUBSCRIPTION__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|116|[]|[null,null,null]|
|P_UPDATE_SUBSCRIPTION__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|197|[]|[null,null,null]|
|P_UPDATE_SUBSCRIPTION__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|[]|[null,null,null]|
|P_REMOVE_SUBSCRIPTION__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|108|[]|[null,null,null]|
|P_REMOVE_SUBSCRIPTION__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|216|[]|[null,null,null]|
|P_REMOVE_SUBSCRIPTION__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|107|[]|[null,null,null]|
|P_ADD_LINKS__LEGACY|true|"ONE"|"ONE"|"ONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|114|[]|[null,null,null]|
|P_ADD_LINKS__OWNED|true|"ONE"|"ONE"|"ONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|198|[]|[null,null,null]|
|P_ADD_LINKS__FENCED|true|"ONE"|"ONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|100|[]|[null,null,null]|
|P_REMOVE_LINK__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|113|[]|[null,null,null]|
|P_REMOVE_LINK__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|232|[]|[null,null,null]|
|P_REMOVE_LINK__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|137|[]|[null,null,null]|
|P_SAVE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|143|[]|[null,null,null]|
|P_SAVE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|231|[]|[null,null,null]|
|P_SAVE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|121|[]|[null,null,null]|
|P__UPDATE_LOCKED__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|126|[]|[null,null,null]|
|P__UPDATE_LOCKED__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|228|[]|[null,null,null]|
|P__UPDATE_LOCKED__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|127|[]|[null,null,null]|
|P__UPDATE__LEGACY|true|"TRUE"|"TRUE"|"TRUE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|145|[]|[null,null,null]|
|P__UPDATE__OWNED|true|"TRUE"|"TRUE"|"TRUE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|204|[]|[null,null,null]|
|P__UPDATE__FENCED|true|"TRUE"|"TRUE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|123|[]|[null,null,null]|
|K_SAVE_STATE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|130|[]|[null,null,null]|
|K_SAVE_STATE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|202|[]|[null,null,null]|
|K_SAVE_STATE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|111|[]|[null,null,null]|
|K_FORGET__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|140|[]|[null,null,null]|
|K_FORGET__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|205|[]|[null,null,null]|
|K_FORGET__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|99|[]|[null,null,null]|
|K_START__LEGACY|true|"EMPTY_TEXT"|"EMPTY_TEXT"|"EMPTY_TEXT"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|136|[]|[null,null,null]|
|K_START__OWNED|true|"EMPTY_TEXT"|"EMPTY_TEXT"|"EMPTY_TEXT"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|299|[]|[null,null,null]|
|K_START__FENCED|true|"EMPTY_TEXT"|"EMPTY_TEXT"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|142|[]|[null,null,null]|
|K_TAKE_BAD__LEGACY|true|"DICT"|"DICT"|"DICT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|57|[]|[null,null,null]|
|K_TAKE_BAD__OWNED|true|"DICT"|"DICT"|"DICT"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|185|[]|[null,null,null]|
|K_TAKE_BAD__FENCED|true|"DICT"|"DICT"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|122|[]|[null,null,null]|
|K_TAKE_VALID__LEGACY|true|"DICT"|"DICT"|"DICT"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|67|[]|[null,null,null]|
|K_TAKE_VALID__OWNED|true|"DICT"|"DICT"|"DICT"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|146|[]|[null,null,null]|
|K_TAKE_VALID__FENCED|true|"DICT"|"DICT"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|106|[]|[null,null,null]|
|K_CHECK__LEGACY|true|"TUPLE"|"TUPLE"|"TUPLE"|[0,0,0,1]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|103|[]|[null,null,null]|
|K_CHECK__OWNED|true|"TUPLE"|"TUPLE"|"TUPLE"|[1,1,0,1]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|213|[]|[null,null,null]|
|K_CHECK__FENCED|true|"TUPLE"|"TUPLE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|105|[]|[null,null,null]|
|K_RUN_REQUEST__LEGACY|true|"ZERO"|"ZERO"|"ZERO"|[0,0,0,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|157|[]|[null,null,null]|
|K_RUN_REQUEST__OWNED|true|"ZERO"|"ZERO"|"ZERO"|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|252|[]|[null,null,null]|
|K_RUN_REQUEST__FENCED|true|"ZERO"|"ZERO"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|120|[]|[null,null,null]|
|K_RUN_REQUEST_EMPTY__LEGACY|true|"ZERO"|"ZERO"|"ZERO"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|61|[]|[null,null,null]|
|K_RUN_REQUEST_EMPTY__OWNED|true|"ZERO"|"ZERO"|"ZERO"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|150|[]|[null,null,null]|
|K_RUN_REQUEST_EMPTY__FENCED|true|"ZERO"|"ZERO"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|111|[]|[null,null,null]|
|K_JOB_RUN__LEGACY|true|"ZERO"|"ZERO"|"ZERO"|[0,0,0,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|160|[]|[null,null,null]|
|K_JOB_RUN__OWNED|true|"ZERO"|"ZERO"|"ZERO"|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|255|[]|[null,null,null]|
|K_JOB_RUN__FENCED|true|"ZERO"|"ZERO"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|125|[]|[null,null,null]|
|K_JOB_RUN_ROLLBACK__LEGACY|true|"ZERO"|"ZERO"|"ZERO"|[0,0,0,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|361|[]|[null,null,null]|
|K_JOB_RUN_ROLLBACK__OWNED|true|"ZERO"|"ZERO"|"ZERO"|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|432|[]|[null,null,null]|
|K_JOB_RUN_ROLLBACK__FENCED|true|"ZERO"|"ZERO"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|136|[]|[null,null,null]|
|K_JOB_REJECT__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|112|[]|[null,null,null]|
|K_JOB_REJECT__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|300|[]|[null,null,null]|
|K_JOB_REJECT__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|106|[]|[null,null,null]|
|K_JOB_STAGE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|106|[]|[null,null,null]|
|K_JOB_STAGE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|206|[]|[null,null,null]|
|K_JOB_STAGE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|113|[]|[null,null,null]|
|K_JOB_SAVE__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|125|[]|[null,null,null]|
|K_JOB_SAVE__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,0]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|248|[]|[null,null,null]|
|K_JOB_SAVE__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|[]|[null,null,null]|
|K_JOB_EVENT__LEGACY|true|"NONE"|"NONE"|"NONE"|[0,0,0,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|62|[]|[null,null,null]|
|K_JOB_EVENT__OWNED|true|"NONE"|"NONE"|"NONE"|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":true,"rejection_observed":null}|179|[]|[null,null,null]|
|K_JOB_EVENT__FENCED|true|"NONE"|"NONE"|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|109|[]|[null,null,null]|
|F_API__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|61|[]|[null,null,null]|
|F_API__OWNED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|59|[]|[null,null,null]|
|F_API__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|107|[]|[null,null,null]|
|F_APPLIER__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|59|[]|[null,null,null]|
|F_APPLIER__OWNED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|58|[]|[null,null,null]|
|F_APPLIER__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|110|[]|[null,null,null]|
|F_SINGBOX__LEGACY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|87|[]|[null,null,null]|
|F_SINGBOX__OWNED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":null}|87|[]|[null,null,null]|
|F_SINGBOX__FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":true,"legacy_equivalent":null,"rejection_observed":true}|110|[]|[null,null,null]|
|H_SIGNATURE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|51|[]|[null,null,null]|
|H_DEFERRED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|48|[]|[null,null,null]|
|H_NO_VERIFIER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|63|[]|[null,null,null]|
|H_NESTED_ERROR|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|144|[]|[null,null,null]|
|H_NESTED_RETURN|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|137|[]|[null,null,null]|
|K_RUN_FAILED|true|null|null|null|[0,0,1,3]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|396|[]|[null,null,null]|
|K_RUN_INVALID|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|151|[]|[null,null,null]|
|K_REQUEST_FOREIGN|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|168|[]|[null,null,null]|
|K_REQUEST_NO_JOB|true|null|null|null|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":null}|240|[]|[null,null,null]|
|K_SWALLOWED_SAVE|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|158|[]|[null,null,null]|
|I_PANEL_CORE|true|null|null|null|[1,1,0,3]|{"completion_verified":true,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|303|[]|[null,null,null]|
|B_RUN_SHADOW|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|59|[]|[null,null,null]|
|B_REJECT_SHADOW|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|57|[]|[null,null,null]|
|B_STAGE_SHADOW|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|58|[]|[null,null,null]|
|B_SAVE_SHADOW|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|53|[]|[null,null,null]|
|B_EVENT_SHADOW|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"fixture_unchanged":null,"legacy_equivalent":null,"rejection_observed":true}|78|[]|[null,null,null]|

Null не заменён ожиданием. Приблизительные времена из старых таблиц не копировались.

## AE

State: FINAL_RECORDED
Rows: 112/112
All source-contract checks passed: true
Frozen identity verified: true

Reference tested HEAD: 737c72037f01caa66ba0309181dbe268128edd01
Reference helper/manifest/source: `{"helper_sha256":"fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680","manifest_sha256":"d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0","source_files":116,"support_sha256":"9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"}`

Controls: `{"active_faults_authorized":false,"audit_registered":true,"completed":112,"elapsed_ms":13030,"expected":112,"global_scope_stop":false,"installed_runtime_changed":false,"live_gateway_operations":0,"network_requests":0,"passed":112,"remaining_not_run":0,"repair_implemented":false,"runtime_actor_binding_implemented":false,"runtime_recovery_implemented":false,"runtime_verifier_implemented":false,"runtime_writer_fence_verified":false,"source_files":116,"unexpected_forbidden_io":0,"workload_subprocesses":0}`
Control issues: `[]`
Report difference rows: 0
Contract mismatch rows: 0

|Case|actual passed|source expectation|actual expected|actual observed|receipt/gen/unknown/stubs|other actual fields|exact ms|issues/report differences|error source|
|---|---|---|---|---|---|---|---|---|---|
|H_CAPTURE___SAVE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|H_CAPTURE___LOAD|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_CAPTURE__UP|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|58|[]|[null,null,null]|
|H_CAPTURE__ENABLE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|H_CAPTURE__DISABLE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|54|[]|[null,null,null]|
|H_CAPTURE__OPEN|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|51|[]|[null,null,null]|
|H_CAPTURE__CLOSE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_CAPTURE__DOWN|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|58|[]|[null,null,null]|
|H_CAPTURE__RESTORE_TUN|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|58|[]|[null,null,null]|
|H_CAPTURE__TIDY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|64|[]|[null,null,null]|
|H_CAPTURE__TAILSCALE_DIRECT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|H_CAPTURE__TAILSCALE_FALLBACK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|H_PEERS___SAVE_PEERS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_PEERS___NFT_ELEMENT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|61|[]|[null,null,null]|
|H_PEERS__PREPARE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|53|[]|[null,null,null]|
|H_PEERS__STOP|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|58|[]|[null,null,null]|
|H_PEERS__RECONCILE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|H_XRAY__APPLY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|H_XRAY__ROLLBACK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|65|[]|[null,null,null]|
|H_SINGBOX__APPLY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|H_SINGBOX__ROLLBACK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|58|[]|[null,null,null]|
|H_SINGBOX__RESTART|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|H_CORES__UPDATE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|H_CORES__ROLLBACK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|65|[]|[null,null,null]|
|H_API__ADD_OUTBOUNDS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|54|[]|[null,null,null]|
|H_API__REMOVE_OUTBOUND|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|50|[]|[null,null,null]|
|H_API__ADD_INBOUNDS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|50|[]|[null,null,null]|
|H_API__REMOVE_INBOUND|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|H_API__REPLACE_ROUTING|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|H_API__PIN|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|H_API__UNPIN|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|51|[]|[null,null,null]|
|H_PANEL__UPDATE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|M_CAPTURE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|63|[]|[null,null,null]|
|M_PEERS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|53|[]|[null,null,null]|
|M_XRAY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|M_SINGBOX|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|M_CORES|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|M_API|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|M_PANEL|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|76|[]|[null,null,null]|
|O_CAPTURE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|O_PEERS|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|O_XRAY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|70|[]|[null,null,null]|
|O_SINGBOX|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|O_CORES|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|O_API|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|O_PANEL|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|60|[]|[null,null,null]|
|B_INCOMPLETE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|B_EXTRA|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|B_WRONG_TYPE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|B_NO_VERIFIER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|76|[]|[null,null,null]|
|B_WRONG_COORDINATOR|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|78|[]|[null,null,null]|
|B_WRONG_REGISTRY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|B_REGISTRY_DRIFT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|51|[]|[null,null,null]|
|B_VERIFIER_DRIFT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|B_CALL_DRIFT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|57|[]|[null,null,null]|
|B_FOREIGN_PID|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|54|[]|[null,null,null]|
|B_FOREIGN_THREAD|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|B_NESTED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|P_EMPTY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|55|[]|[null,null,null]|
|P_LIST|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|52|[]|[null,null,null]|
|P_TOO_MANY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|71|[]|[null,null,null]|
|P_WRONG_STEP|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|64|[]|[null,null,null]|
|P_UNKNOWN_WRITER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|65|[]|[null,null,null]|
|P_UNKNOWN_METHOD|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|69|[]|[null,null,null]|
|P_ARGS_LIST|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|66|[]|[null,null,null]|
|P_KWARGS_DICT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|64|[]|[null,null,null]|
|P_DUP_KEY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|65|[]|[null,null,null]|
|P_OWNER_KEY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|
|P_USED|true|null|null|null|[1,1,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|161|[]|[null,null,null]|
|P_FENCED|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|149|[]|[null,null,null]|
|P_NO_CHECKER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|61|[]|[null,null,null]|
|C_SB_XRAY|true|null|null|null|[1,1,0,3]|{"completion_verified":true,"file_checked":2,"file_matched":true,"rejection_observed":null}|289|[]|[null,null,null]|
|C_SB_XRAY_API|true|null|null|null|[1,1,0,4]|{"completion_verified":true,"file_checked":2,"file_matched":true,"rejection_observed":null}|258|[]|[null,null,null]|
|C_PANEL_PEERS|true|null|null|null|[1,1,0,0]|{"completion_verified":true,"file_checked":1,"file_matched":true,"rejection_observed":null}|202|[]|[null,null,null]|
|C_FAILED_RESULT|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|131|[]|[null,null,null]|
|C_VERIFIER_EXCEPTION|true|null|null|null|[0,0,1,3]|{"completion_verified":null,"file_checked":2,"file_matched":true,"rejection_observed":true}|229|[]|[null,null,null]|
|C_FALSE_VERIFIER|true|null|null|null|[0,0,1,3]|{"completion_verified":null,"file_checked":2,"file_matched":true,"rejection_observed":true}|228|[]|[null,null,null]|
|C_STEP_EXCEPTION|true|null|null|null|[0,0,1,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|152|[]|[null,null,null]|
|C_AFTER_UNBIND|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|204|[]|[null,null,null]|
|C_AFTER_HOOK_DRIFT|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|234|[]|[null,null,null]|
|C_AFTER_VERIFIER_DRIFT|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|277|[]|[null,null,null]|
|C_AFTER_REGISTRY_DRIFT|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|222|[]|[null,null,null]|
|C_NO_EARLY_LEASE|true|null|null|null|[1,1,0,3]|{"completion_verified":true,"file_checked":2,"file_matched":true,"rejection_observed":true}|310|[]|[null,null,null]|
|C_CHECKER_FALSE|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|252|[]|[null,null,null]|
|C_CHECKER_EXCEPTION|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|254|[]|[null,null,null]|
|C_FILE_MISMATCH|true|null|null|null|[0,0,1,3]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":true}|223|[]|[null,null,null]|
|C_SECOND_REJECT|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|197|[]|[null,null,null]|
|C_SECOND_TERMINAL|true|null|null|null|[0,0,1,1]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|185|[]|[null,null,null]|
|F_PRESENT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":1,"file_matched":true,"rejection_observed":null}|62|[]|[null,null,null]|
|F_ABSENT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":1,"file_matched":true,"rejection_observed":null}|86|[]|[null,null,null]|
|F_TWO|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":2,"file_matched":true,"rejection_observed":null}|54|[]|[null,null,null]|
|F_DIGEST_MISMATCH|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|53|[]|[null,null,null]|
|F_MODE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|60|[]|[null,null,null]|
|F_OWNER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|67|[]|[null,null,null]|
|F_HARDLINK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|93|[]|[null,null,null]|
|F_SYMLINK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|56|[]|[null,null,null]|
|F_PARENT_SYMLINK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|94|[]|[null,null,null]|
|F_ROOT_SYMLINK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|65|[]|[null,null,null]|
|F_FIFO|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|68|[]|[null,null,null]|
|F_OVERSIZE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|91|[]|[null,null,null]|
|F_MISSING|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|70|[]|[null,null,null]|
|F_ABSENT_PRESENT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|70|[]|[null,null,null]|
|F_ABSENT_SYMLINK|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|64|[]|[null,null,null]|
|F_ABSENT_MISSING_PARENT|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|65|[]|[null,null,null]|
|F_DIRECTORY_MODE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|69|[]|[null,null,null]|
|F_ROOT_MODE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":0,"file_matched":false,"rejection_observed":null}|67|[]|[null,null,null]|
|F_DUPLICATE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|67|[]|[null,null,null]|
|F_TRAVERSAL|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|59|[]|[null,null,null]|
|F_BAD_DIGEST|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|87|[]|[null,null,null]|
|F_BOOL_OWNER|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|62|[]|[null,null,null]|
|F_BOOL_MODE|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|66|[]|[null,null,null]|
|F_EMPTY|true|null|null|null|[0,0,0,0]|{"completion_verified":null,"file_checked":null,"file_matched":null,"rejection_observed":true}|56|[]|[null,null,null]|

Null не заменён ожиданием. Приблизительные времена из старых таблиц не копировались.

## Исполнение AH и конечный режим — заполняет исполнитель

Добавить фактические MSK/NNP/sudo/command rc/status/pool/connection/owner actions.
Таблицы не редактировать. При unavailable/mismatch старые batches не запускать.

<!-- AH_EXECUTION -->
```json
{
  "nnp": 0,
  "sudo_rc": 0,
  "collect_rc": 0,
  "show_rc": 0,
  "before_health": "HEALTHY_ON",
  "after_health": "HEALTHY_ON",
  "before_pool": "OFF",
  "after_pool": "OFF",
  "before_link": "ALIVE",
  "after_link": "ALIVE",
  "versions_unchanged": true,
  "owner_actions": 0
}
```

MSK AH start/end: 2026-11-03T23:44:10+03:00 / 2026-11-03T23:47:08+03:00
