# Отчёт: XGW wave3ag — FreePool PoolStore и declared dependency binding

MSK дата/интервал: 2026-11-03, 22:43:35–22:53+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 8045d3a34020e201e0d8c744236bd0e65896264b /
tree fa4165a6aeabf3ae0a14995ca496109bbf9aba41 (S2.1, предок 01c84fa… — отчёт af;
SOURCE_PREFLIGHT_OK). Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
6A10M / 3 changed vs AF / 113 unchanged / source 116: программно проверено в S2.1/F3
(SOURCE_DIFF_SIX_ADD_TEN_MODIFY): против pin A = 6 ownership*.py; M = 10 legacy модулей
(новые против AF: freepool/pool.py, freepool/store.py); относительно tested AF изменились
ровно 3 source files (freepool/store.py, freepool/pool.py, ownership_binding.py),
остальные 113 сохранены байт-в-байт (manifest 116). Store 5 + Pool 8 новых instance hooks
PEERS; PoolStore(paths,ownership=None) constructor без I/O/admission/ticket; FreePool
optional ownership передаётся Store/Backend; foreign injected Backend отказывается ДО
filesystem setup/cleanup и ДО admission; constructor cleanup теперь writer (explicit-owned
FreePool construction = 1 receipt за _prune_retired, даже empty cleanup). BoundWriters
теперь 9 объектов/50 методов (37+13) — дополнительно PoolStore/FreePool; 3 exact object
reference identity checks: xray.api→api, pool.store→pool_store, pool.runtime→peers.
HelperSHA d5ce2ef2447b809e9faddf393303460dfd854fbfdbc9e1c9118f66ac7f1a7ec6;
SupportSHA 9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917
(неизменённый AD helper; старые CLI/batch/cases не вызывались);
ManifestSHA 383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b.
116 freeze 0700/0600/Git LF/private frozen_ad: POOL_FLOW_FROZEN 116 + S2.4b POOL_FLOW_READY
rc0 (~/xgw-w3ag 0700; batch.py/support.py/manifest.json/source/** 0600, dirs 0700; import
private package; worker ДО source imports поставил принятый AD audit guard/self-test+2
manual probes; pool/backend clock 100000 synthetic, metadata outcomes искусственные).
Installed runtime unchanged / 7 flags false; daemon/CLI default None fence не активируют.
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. HEALTHY/on/pool/versions/connection bookends: HEALTHY с 03.11 19:28
(метка сместилась с «03.11 15:31» между AF и AG вне моих прогонов — записано как факт
baseline, не диагностировалось по прецеденту ТЗ; в самом прогоне AG bookends совпали);
перехват ВКЛЮЧЁН (не переключался); pool «выключен; регион EU (строго)» — без изменений;
Xray 26.10.31 / sing-box 1.14.4; связь живая в обоих концах. OldAF145/AE112/AD130/AC51/
AB32/AA22/Z19/Y6/X26/W25 и installed 110-tree NOT_RUN (не повторялись); Fake D не
исполнялся; Y root material не читался (snapshot PLANNED_NOT_ARMED).

| Этап | Actual rc/file/marker | Факты | Limits |
|---|---|---|---|
| S1/S2 | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 22:43:35; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_SIX_ADD_TEN_MODIFY + SOURCE_MANIFEST_MATCHED 116 + PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; POOL_FLOW_FROZEN 116/READY | Source ≠ installed 116 attestation |
| start | rc 0 / **POOL_FLOW_BATCH_STARTED** | Popen collector, EXCL claim/atomic progress | Не case PASS; повторный start запрещён |
| monitor | rc 0 / **BATCH_FINISHED POOL_FLOW_BATCH_RECORDED 129 129** | Прогресс 37→69→105 (5с опрос, предел 300с) | Не worker exit rc |
| show/shape | rc 0 / wrapper.file=**summary.json** / FINAL_SHAPE_VALID True / ALL_CASES_PASSED True | Финальный summary (не checkpoint); командные rc раздельно; collector_exit_rc=**NOT_COLLECTED** | Read 0 не completion |
| S4 | rc0 ×2 | HEALTHY с 03.11 19:28/включён; «выключен; регион EU (строго)»; связь живая | Не LAN/kernel proof |

## Все 129 cases

Все passed=true; errorclass/public source:line не потребовались (fail-случаев нет,
unexpected audit denials/OSError нет; intentional negative OSError ловились внутри cases
и проверялись как UNKNOWN). Сокращения: E/O = expected/observed business enum
(NONE/TRUE/FALSE/ZERO/ONE/OTHER_INT/TEXT/EMPTY_TEXT/LIST/DICT/TUPLE/POOL/OUTCOME —
business result, НЕ command rc; OUTCOME synthetic, не server-online proof);
rc/g/uw/sc = registry_receipts/registry_generation/unknown_writers/stub_calls;
leq = legacy_equivalent; fm = fixture_unchanged; rej = rejection_observed;
cv = completion_verified; «—» = null (не 0).

### Матрица Store (10 × 3) — 30 cases

| Case ID | passed / E=O / rc,g / sc / leq,cv или fm,rej / мс |
|---|---|
| S_ENSURE__LEGACY | true; NONE=NONE; 0,0; 0; —; 68 |
| S_ENSURE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 161 |
| S_ENSURE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 116 |
| S_SUCCESS__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 117 |
| S_SUCCESS__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 269 |
| S_SUCCESS__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_PARTIAL__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_PARTIAL__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_PARTIAL__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_UNAVAILABLE_EMPTY__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_UNAVAILABLE_EMPTY__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_UNAVAILABLE_EMPTY__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_UNAVAILABLE_EXISTING__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_UNAVAILABLE_EXISTING__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_UNAVAILABLE_EXISTING__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_ROTATE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_ROTATE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_ROTATE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_PRUNE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_PRUNE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_PRUNE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_RETIRE_ALL__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_RETIRE_ALL__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_RETIRE_ALL__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_RETIRE_NOOP__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_RETIRE_NOOP__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_RETIRE_NOOP__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |
| S_SAVE_CANDIDATES__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| S_SAVE_CANDIDATES__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| S_SAVE_CANDIDATES__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~100 |

### Матрица Pool (18 × 3) — 54 cases

| Case ID | passed / E=O / rc,g / sc / leq,cv или fm,rej / мс |
|---|---|
| P_PRUNE_RETIRED__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_PRUNE_RETIRED__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_PRUNE_RETIRED__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_SUCCESS__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| P_REFRESH_SUCCESS__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| P_REFRESH_SUCCESS__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_UNAVAILABLE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| P_REFRESH_UNAVAILABLE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| P_REFRESH_UNAVAILABLE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_PARTIAL__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| P_REFRESH_PARTIAL__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| P_REFRESH_PARTIAL__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_TWO__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~110 |
| P_REFRESH_TWO__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~250 |
| P_REFRESH_TWO__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_NOT_DUE__LEGACY | true; FALSE=FALSE; 0,0; 0; —; ~70 |
| P_REFRESH_NOT_DUE__OWNED | true; FALSE=FALSE; 1,1; 0; leq=true, cv=true; ~160 |
| P_REFRESH_NOT_DUE__FENCED | true; FALSE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_PRUNE_CANDIDATES__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_PRUNE_CANDIDATES__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_PRUNE_CANDIDATES__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_REFRESH_BACKEND__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_REFRESH_BACKEND__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_REFRESH_BACKEND__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_NOTE_HANDSHAKE__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_NOTE_HANDSHAKE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_NOTE_HANDSHAKE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_PROXY_XRAY__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~100 |
| P_PROXY_XRAY__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~200 |
| P_PROXY_XRAY__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_PROXY_SINGBOX__LEGACY | true; TRUE=TRUE; 0,0; 0; —; ~100 |
| P_PROXY_SINGBOX__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; ~200 |
| P_PROXY_SINGBOX__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_CHECK_PROXY__LEGACY | true; OUTCOME=OUTCOME; 0,0; 0; —; ~120 |
| P_CHECK_PROXY__OWNED | true; OUTCOME=OUTCOME; 1,1; 0; leq=true, cv=true; ~260 |
| P_CHECK_PROXY__FENCED | true; OUTCOME=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_CHECK_REACH__LEGACY | true; OUTCOME=OUTCOME; 0,0; 0; —; ~120 |
| P_CHECK_REACH__OWNED | true; OUTCOME=OUTCOME; 1,1; 0; leq=true, cv=true; ~260 |
| P_CHECK_REACH__FENCED | true; OUTCOME=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_CHECK_TUNNEL__LEGACY | true; OUTCOME=OUTCOME; 0,0; 0; —; ~120 |
| P_CHECK_TUNNEL__OWNED | true; OUTCOME=OUTCOME; 1,1; 0; leq=true, cv=true; ~260 |
| P_CHECK_TUNNEL__FENCED | true; OUTCOME=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_CHECK_CANCEL__LEGACY | true; OUTCOME=OUTCOME; 0,0; 0; —; ~120 |
| P_CHECK_CANCEL__OWNED | true; OUTCOME=OUTCOME; 1,1; 0; leq=true, cv=true; ~260 |
| P_CHECK_CANCEL__FENCED | true; OUTCOME=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_RECORD_PROXY__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_RECORD_PROXY__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_RECORD_PROXY__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_RECORD_TUNNEL__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_RECORD_TUNNEL__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_RECORD_TUNNEL__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |
| P_RECORD_LIST__LEGACY | true; NONE=NONE; 0,0; 0; —; ~80 |
| P_RECORD_LIST__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; ~180 |
| P_RECORD_LIST__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; ~90 |

Примечание к таблицам S/P: «~N» — значения из одного и того же readout с округлением
диапазона (фактические per-case elapsed_ms в summary.json 0600 notes; порядок величин
и pattern полей идентичен для каждой строки группы, отличия только в десятках мс).

### Constructors (3 × 3) — 9 cases

| Case ID | passed / details / мс |
|---|---|
| C_EMPTY__LEGACY | true; FreePool legacy construction: rc=0, cleanup —; ~90 |
| C_EMPTY__OWNED | true; explicit-owned construction: 1 receipt за _prune_retired (empty cleanup — всё равно writer), leq/cv=true; ~180 |
| C_EMPTY__FENCED | true; refusal до cleanup: synthetic retired snapshots/profiles/secrets/candidates НЕ удалены (fm=true, rej=true); ~90 |
| C_RETIRED__LEGACY | true; rc=0; ~90 |
| C_RETIRED__OWNED | true; 1 receipt за cleanup retired, leq/cv=true; ~180 |
| C_RETIRED__FENCED | true; fm=true, rej=true (FENCED не удаляет retired); ~90 |
| C_PROVIDED__LEGACY | true; provided Backend identity сохранён; rc=0; ~90 |
| C_PROVIDED__OWNED | true; nested Store/Backend ownership identity + provided Backend identity; 1 receipt, leq/cv=true; ~180 |
| C_PROVIDED__FENCED | true; fm=true, rej=true; ~90 |

PoolStore constructor: I/O не делает, ticket не создаёт (подтверждено E_STORE_NOIO отдельно).

### Extras — 36 cases

| Case ID | passed / details / мс |
|---|---|
| E_FOREIGN_NONE | true; foreign injected Backend (None-несоответствие) отказан ДО filesystem setup/cleanup и ДО admission: rej=true, rc=0; 58 |
| E_FOREIGN_OTHER | true; foreign injected Backend (другой объект): rej=true, rc=0; 60 |
| E_STORE_NOIO | true; POSITIVE identity/no-IO check: PoolStore constructor не делает I/O и не создаёт ticket (rc=0, без изменений fixture); 59 |
| E_BINDING_NINE | true; POSITIVE readonly declaration validation: BoundWriters 9 объектов/50 методов принимается (не pipeline execution); 50 |
| E_POOL_STORE_ALIAS | true; 3 foreign reference: pool.store→чужой объект отказан: rej=true, rc=0; 79 |
| E_POOL_RUNTIME_ALIAS | true; pool.runtime→чужой объект отказан: rej=true, rc=0; 52 |
| E_APPLIER_API_ALIAS | true; xray.api→чужой объект отказан: rej=true, rc=0; 58 |
| E_POOL_UNBOUND | true; unbound pool отказан: rej=true, rc=0; 50 |
| H_STORE_ENSURE | true; подмена hook Store._ensure — блокировка до body: rej=true, rc=0; 55 |
| H_STORE_COMMIT | true; rej=true, rc=0; 52 |
| H_STORE_PRUNE | true; rej=true, rc=0; 77 |
| H_STORE_RETIRE | true; rej=true, rc=0; 53 |
| H_STORE_SAVE | true; rej=true, rc=0; 57 |
| H_POOL_PRUNE | true; rej=true, rc=0; 48 |
| H_POOL_REFRESH | true; rej=true, rc=0; 51 |
| H_POOL_CANDIDATES | true; rej=true, rc=0; 61 |
| H_POOL_BACKEND | true; rej=true, rc=0; 54 |
| H_POOL_HANDSHAKE | true; rej=true, rc=0; 52 |
| H_POOL_CHECK | true; rej=true, rc=0; 60 |
| H_POOL_PROXY | true; rej=true, rc=0; 47 |
| H_POOL_RECORD | true; rej=true, rc=0 (13 hook shadows — business body не запускается); 52 |
| E_PRUNE_ERROR | true; подавленный business OSError taints outer: UNKNOWN 1 (uw=1), rc=0, cleanup других dummy files мог продолжиться; 145 |
| E_RECONCILE_ERROR | true; UNKNOWN 1, rc=0, sc=1; 141 |
| E_ROTATE_ERROR | true; UNKNOWN 1, rc=0 (current может остаться перемещённым в history — не rollback); 141 |
| E_PROBE_ERROR | true; UNKNOWN 1, rc=0, sc=1; 174 |
| E_STOP_ERROR | true; пойманный nested nft stub error не разрешает completion несмотря на последующий synthetic OK record: UNKNOWN 1, rc=0, sc=13; 444 |
| E_VERIFIER_FALSE | true; false verifier: UNKNOWN 1, rc=0; 219 |
| R_SUMMARY | true; readonly reader под synthetic lease: ret=DICT, без receipt/изменений fixture (rc=0); 245 |
| R_NEXT_CHECKS | true; LIST; rc=0; 212 |
| R_SPENT | true; OTHER_INT; rc=0; 198 |
| R_HANDSHAKES | true; LIST; rc=0; 200 |
| R_VARIANTS | true; LIST; rc=0; 206 |
| R_STORE_SNAPSHOT | true; DICT; rc=0; 205 |
| R_STORE_CANDIDATES | true; DICT; rc=0; 211 |
| I_REFRESH_CHECK | true; POSITIVE composite: 9 actors/50 hooks, prepared batch refresh→check, одна final receipt/generation, roles LIFECYCLE+PEERS, ранний lease отказан (rej=true), cv=true, sc=4; 242 |
| I_SECOND_FAIL | true; первый snapshot остаётся после второго stub probe OSError: UNKNOWN 1, rc=0, sc=4 (не rollback/auto-retry); 239 |

Expected/completed/passed/remaining NOT_RUN: **129/129/129/0** (global_scope_stop=false).
Группы actual executed/passed: S 30/30, P 54/54, C 9/9, extras 36/36.
Матрица 93 = 28 writer variants × 3 + 3 constructor variants × 3: LEGACY 31/31 receipts=0
(28 business enum match + 3 constructors ret null); OWNED 31/31 — ровно 1 receipt/generation,
legacy_equivalent=true, completion_verified=true во всех 31 (differential сравнение с LEGACY
fingerprint дерева bytes/modes/uid/nlink/entries и in-memory next_refresh/failures/backend
flags/lease count ДО completion; не mtime); FENCED 31/31 — refusal до body: fixture/memory
неизменны, trace 0, receipts 0. Constructor Owned 3 receipts 1 vs PoolStore no-IO receipts 0
— раздельно. Extras: 1 completed (I_REFRESH_CHECK), 7 UNKNOWN (6 expected errors: prune/
reconcile/rotate/probe/stop/verifier-false + I_SECOND_FAIL — все rc=0/uw=1, не успешные
restores), 21 preflight/definition/identity (8 base: E_FOREIGN×2/E_STORE_NOIO/E_BINDING_NINE
— из них 2 positive identity/no-IO checks, не refusals + 3 foreign aliases + E_POOL_UNBOUND
+ 13 hook shadows H×13, business body не запускался), 7 readonly readers (R×7 под synthetic
lease, без receipts/изменений). Не называть все 21 refusals. Actual nullable counts как в
readout, не нули из ожиданий. Audit: audit_registered=true, unexpected_forbidden_io=**0**,
workload_subprocesses=**0**, global_scope_stop=false, source_files=**116**, batch 21933 мс.
Seven runtime gates false: installed_runtime_changed/runtime_actor_binding_implemented/
runtime_writer_fence_verified/runtime_verifier_implemented/runtime_recovery_implemented/
repair_implemented/active_faults_authorized = **false** (даже 129/129).
Network_requests/live_gateway_operations: **0/0**. collector_exit_rc=NOT_COLLECTED.

## Решение

Принят полностью в optional source pool / declared 9 actors + 50 hooks / private fixtures
scope (129/129): Store mutators (_ensure/commit/prune/retire_openvpn/save_candidates) и
8 Pool hooks (_prune_retired/refresh_due/_prune_candidates/refresh_backend/_note_handshake/
check_some/_check_proxy/_record) gated до mkdir/chmod/rotate/unlink/rmtree/write при
explicit coordinator; FreePool передаёт ownership в Store/Backend; foreign Backend отказан
до filesystem setup/cleanup и до admission; constructor cleanup признан writer (explicit-
owned construction = 1 receipt даже за empty cleanup), PoolStore constructor без I/O/ticket.
Object identity graph из 3 exact references (xray.api→api, pool.store→pool_store,
pool.runtime→peers) проверяется до admission и между шагами; unbound pool и любые
foreign aliases отказаны. Частичные сценарии честно не «успешны»: rotate error может
оставить current перемещённым в history; probe-after-snapshot сохраняет первый snapshot;
nested stop error (пойманный) не разрешает completion — всё UNKNOWN 1, без rollback/
auto-retry, как и объявлено. Fake probe latency/bytes/country — synthetic outcomes, НЕ
measurement реального VPN/speed/ping/region; Backend.prepare/stop исполняли только Python
+ FakeRunner/dummy manifests, не systemd/veth/netns/process/network; private retired data —
synthetic, не live secrets; synthetic registry clock — не 45s rescue proof.
Default None unfenced; global runtime composition/async dispatch/version boot handshake/
resource verifiers/repair/bootstrap не готовы; 3 object ref identity checks ≠ filesystem
path alias policy/полный runtime callgraph; проверки остальных Resource domains не
появились. Нет install/fault/recovery authorization — по PASS никакой установки/активации.
LiveC BLOCKED_BOOTSTRAP; real E нужны C+D+independent original-on/code/unit rescue.
Источник partial/STOP: нет (не было; все 129 выполнены, guard не блокировал ничего
неожиданного). Уточнение AF-сводки (принято developer review, старый отчёт не переписан):
AF extras фактически 2 completed + 6 UNKNOWN + 8 definition/admission refusals
(H_SIGNATURE — неверная ownership signature, H_DEFERRED — generator definition, deferred
RETURN проверяет H_NESTED_RETURN; AST body proof выполнен архитектором локально, не
worker); общий AF 145 PASS не изменился.
Only ThinkCentre; working LAN; host не LAN-client proof. Full wave3/D1-on/faults/LAN UDP/
IPv6/DNS/E4/performance/all Tailscale — открыты; не wave4/DAE. Исторические evidence
AF145/AE112/AD130/AC51/AB32/AA22/Z19/Y6/X26/W25/U/V/M/J/L/Npartial/Pblocked/Q/Rnegative/
S/T сохранены без пересмотра (не повторялись).

Privacy review всего Markdown выполнен перед единственной публикацией: никаких raw
config/status/log/kernel/URI/IP/MAC/UUID/secrets/SNI/ports/fp/tags/PID/NIC/UID/home/boot/
registry ids/tokens/private hashes/fingerprints/case files/argv/business texts/exceptions —
только fixed case IDs/enums/bools/counts/ms/rc/Git/source SHA/public repo:line; 116
публичных manifest hashes в отчёт не вставлялись. Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3ag — FreePool PoolStore и declared dependency binding», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 03.11 19:28, перехват
ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не было; 3+116 frozen
файлов/started/worker-claimed/progress/summary/cases остались в заметках вне Git.
