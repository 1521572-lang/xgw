# Отчёт: XGW wave3af — source flow, panel/core writers и factories

MSK дата/интервал: 2026-11-03, 19:17:28–19:30+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD d8598b4cd7ce99cd2f999af6d5bd2c4eead8ae75 /
tree ab909c82095ab90975bb06572e866b1163b9b40f (S2.1, предок 7da3b74… — отчёт ae;
SOURCE_PREFLIGHT_OK). Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
Source 6A8M / 5 changed vs AE / 111 unchanged: программно проверено в S2.1/F3
(SOURCE_DIFF_SIX_ADD_EIGHT_MODIFY): против pin A = 6 ownership*.py; M = восемь legacy
модулей, включая новый восьмой engine.py; относительно tested AE изменились ровно 5
source files (ownership_hooks.py, ownership_binding.py, managed.py, cores.py, engine.py),
остальные 111 сохранены байт-в-байт (сверены manifest'ом 116). Граница binding расширена
с 32 до 37 методов (5 новых Job hooks); 23 публичных panel writers + save/_update_locked/
_update получили keyword-only ownership=None (None остаётся legacy/unfenced); 6 core free
functions и 5 Job methods получили hooks (ранний state write/request unlink закрыт до
update hook); run_request передаёт coordinator в take_request/новый Job; фабрики
make_api/make_applier/make_singbox передают optional coordinator (Applier.api — тот же;
создание explicit-owned объекта даёт receipts 0).
HelperSHA 1973c1f7aa316a09a86e6057146929d27792f81208c00256f545c6ccf996e2c8;
SupportSHA 9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917
(неизменённый AD helper; его старые CLI/batch/cases не вызывались);
ManifestSHA ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82.
116 freeze 0700/0600/LF/private frozen_ad: SOURCE_FLOW_FROZEN 116 + S2.4b SOURCE_FLOW_READY
rc0 (~/xgw-w3af 0700; batch.py/support.py/manifest.json/source/** 0600, dirs 0700; хеши по
опубликованным Git LF bytes; импорт только private package; worker ДО source imports
поставил неизменённый AD audit guard/self-test + 2 manual probes). Installed runtime
unchanged / 7 gates false: все флаги runtime/repair false; daemon/CLI/service callers
по-прежнему не задают coordinator; глобальный runtime composition не готов.
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. HEALTHY/on/pool/versions/connection before/after: HEALTHY с 03.11 15:31
(та же метка, что и AE — не менялась); перехват ВКЛЮЧЁН (не переключался); pool
«выключен; регион EU (строго)» — без изменений; Xray 26.10.31 / sing-box 1.14.4; связь
живая в обоих концах. OldAE112/AD130/AC51/AB32/AA22/Z19/Y6/X26/W25 и installed 110-tree
NOT_RUN (не повторялись); Fake D не исполнялся; Y root material не читался
(snapshot PLANNED_NOT_ARMED).

| Этап | Actual rc/file/marker | Факты | Limits |
|---|---|---|---|
| S1/S2 | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 19:17:28; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_SIX_ADD_EIGHT_MODIFY + SOURCE_MANIFEST_MATCHED 116 + PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; SOURCE_FLOW_FROZEN 116/READY | Source ≠ installed 116 attestation |
| start | rc 0 / **SOURCE_FLOW_BATCH_STARTED** | Popen collector, EXCL claim/atomic progress | Не case PASS; повторный start запрещён |
| monitor | rc 0 / **BATCH_FINISHED SOURCE_FLOW_BATCH_RECORDED 145 145** | Прогресс 89→115 (5с опрос, предел 300с) | Не worker rc |
| show/shape | rc 0 / wrapper.file=**summary.json** / FINAL_SHAPE_VALID True / ALL_CASES_PASSED True | Финальный summary (не checkpoint); командные rc раздельно; collector_exit_rc=**NOT_COLLECTED** | Read 0 не completion |
| S4 | rc0 ×2 | HEALTHY с 03.11 15:31/включён; «выключен; регион EU (строго)»; связь живая | Не kernel/LAN proof |

## Все 145 cases

Все passed=true; errorclass/public source:line не потребовались (fail-случаев нет;
business assertion mismatches нет; unexpected audit denials/OSError нет).
Сокращения: E/O = expected/observed business return enum (NONE/TRUE/FALSE/TEXT/
EMPTY_TEXT/ZERO/ONE — это business result, НЕ command exit rc); rc/g/uw/sc =
registry_receipts/registry_generation/unknown_writers/stub_calls; leq = legacy_equivalent;
fm = fixture_unchanged; rej = rejection_observed; cv = completion_verified;
«—» = null (неизвестно/не применимо, не 0).

### Матрица P (26 panel writers × 3) — 78 cases

| Case ID | passed / E=O / rc,g / sc / leq,cv или fm,rej / мс |
|---|---|
| P_SET_FREE_POOL_MODE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 109 |
| P_SET_FREE_POOL_MODE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 192 |
| P_SET_FREE_POOL_MODE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 120 |
| P_SET_FREE_POOL_PIN__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 98 |
| P_SET_FREE_POOL_PIN__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 205 |
| P_SET_FREE_POOL_PIN__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 101 |
| P_SET_TAILSCALE_DIRECT__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 102 |
| P_SET_TAILSCALE_DIRECT__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 191 |
| P_SET_TAILSCALE_DIRECT__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 97 |
| P_REPLACE_TAILSCALE_DIRECT__LEGACY | true; NONE=NONE; 0,0; 0; —; 101 |
| P_REPLACE_TAILSCALE_DIRECT__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 202 |
| P_REPLACE_TAILSCALE_DIRECT__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 95 |
| P_SET_DEVICE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 106 |
| P_SET_DEVICE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 196 |
| P_SET_DEVICE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 129 |
| P_REPLACE_DEVICES__LEGACY | true; NONE=NONE; 0,0; 0; —; 103 |
| P_REPLACE_DEVICES__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 204 |
| P_REPLACE_DEVICES__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 109 |
| P_SET_KERNEL_DEVICE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 104 |
| P_SET_KERNEL_DEVICE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 209 |
| P_SET_KERNEL_DEVICE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 103 |
| P_SPLIT_KERNEL_DIRECT__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 115 |
| P_SPLIT_KERNEL_DIRECT__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 188 |
| P_SPLIT_KERNEL_DIRECT__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 102 |
| P_SET_ROUTE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 112 |
| P_SET_ROUTE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 221 |
| P_SET_ROUTE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 131 |
| P_SET_SERVERS__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 113 |
| P_SET_SERVERS__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 206 |
| P_SET_SERVERS__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 118 |
| P_SET_PRIORITY__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 121 |
| P_SET_PRIORITY__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 223 |
| P_SET_PRIORITY__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 126 |
| P_SET_CORE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 138 |
| P_SET_CORE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 241 |
| P_SET_CORE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 109 |
| P_SET_STICKY__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 101 |
| P_SET_STICKY__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 205 |
| P_SET_STICKY__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 107 |
| P_SET_KERNEL_DIRECT__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 112 |
| P_SET_KERNEL_DIRECT__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 204 |
| P_SET_KERNEL_DIRECT__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 104 |
| P_SET_TAILSCALE_SERVE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 129 |
| P_SET_TAILSCALE_SERVE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 215 |
| P_SET_TAILSCALE_SERVE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 112 |
| P_SET_TAILSCALE_FUNNEL__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 101 |
| P_SET_TAILSCALE_FUNNEL__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 210 |
| P_SET_TAILSCALE_FUNNEL__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 108 |
| P_SET_TAILSCALE_ROUTE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 120 |
| P_SET_TAILSCALE_ROUTE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 201 |
| P_SET_TAILSCALE_ROUTE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 131 |
| P_DROP_TELEGRAM__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 117 |
| P_DROP_TELEGRAM__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 201 |
| P_DROP_TELEGRAM__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 111 |
| P_ADD_SUBSCRIPTION__LEGACY | true; TEXT=TEXT; 0,0; 0; —; 110 |
| P_ADD_SUBSCRIPTION__OWNED | true; TEXT=TEXT; 1,1; 0; leq=true, cv=true; 197 |
| P_ADD_SUBSCRIPTION__FENCED | true; TEXT=null; 0,0; 0; fm=true, rej=true; 107 |
| P_UPDATE_SUBSCRIPTION__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 116 |
| P_UPDATE_SUBSCRIPTION__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 197 |
| P_UPDATE_SUBSCRIPTION__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 109 |
| P_REMOVE_SUBSCRIPTION__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 108 |
| P_REMOVE_SUBSCRIPTION__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 216 |
| P_REMOVE_SUBSCRIPTION__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 107 |
| P_ADD_LINKS__LEGACY | true; ONE=ONE; 0,0; 0; —; 114 |
| P_ADD_LINKS__OWNED | true; ONE=ONE; 1,1; 0; leq=true, cv=true; 198 |
| P_ADD_LINKS__FENCED | true; ONE=null; 0,0; 0; fm=true, rej=true; 100 |
| P_REMOVE_LINK__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 113 |
| P_REMOVE_LINK__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 232 |
| P_REMOVE_LINK__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 137 |
| P_SAVE__LEGACY | true; NONE=NONE; 0,0; 0; —; 143 |
| P_SAVE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 231 |
| P_SAVE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 121 |
| P__UPDATE_LOCKED__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 126 |
| P__UPDATE_LOCKED__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 228 |
| P__UPDATE_LOCKED__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 127 |
| P__UPDATE__LEGACY | true; TRUE=TRUE; 0,0; 0; —; 145 |
| P__UPDATE__OWNED | true; TRUE=TRUE; 1,1; 0; leq=true, cv=true; 204 |
| P__UPDATE__FENCED | true; TRUE=null; 0,0; 0; fm=true, rej=true; 123 |

### Матрица K (14 core variants × 3) — 42 cases

| Case ID | passed / E=O / rc,g / sc / leq,cv или fm,rej / мс |
|---|---|
| K_SAVE_STATE__LEGACY | true; NONE=NONE; 0,0; 0; —; 130 |
| K_SAVE_STATE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 202 |
| K_SAVE_STATE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 111 |
| K_FORGET__LEGACY | true; NONE=NONE; 0,0; 0; —; 140 |
| K_FORGET__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 205 |
| K_FORGET__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 99 |
| K_START__LEGACY | true; EMPTY_TEXT=EMPTY_TEXT; 0,0; 1; —; 136 (command trace, не actual service run) |
| K_START__OWNED | true; EMPTY_TEXT=EMPTY_TEXT; 1,1; 1; leq=true, cv=true; 299 |
| K_START__FENCED | true; EMPTY_TEXT=null; 0,0; 0; fm=true, rej=true; 142 |
| K_TAKE_BAD__LEGACY | true; DICT=DICT; 0,0; 0; —; 57 |
| K_TAKE_BAD__OWNED | true; DICT=DICT; 1,1; 0; leq=true, cv=true; 185 |
| K_TAKE_BAD__FENCED | true; DICT=null; 0,0; 0; fm=true, rej=true; 122 |
| K_TAKE_VALID__LEGACY | true; DICT=DICT; 0,0; 0; —; 67 |
| K_TAKE_VALID__OWNED | true; DICT=DICT; 1,1; 0; leq=true, cv=true; 146 |
| K_TAKE_VALID__FENCED | true; DICT=null; 0,0; 0; fm=true, rej=true; 106 |
| K_CHECK__LEGACY | true; TUPLE=TUPLE; 0,0; 1; —; 103 |
| K_CHECK__OWNED | true; TUPLE=TUPLE; 1,1; 1; leq=true, cv=true; 213 |
| K_CHECK__FENCED | true; TUPLE=null; 0,0; 0; fm=true, rej=true; 105 |
| K_RUN_REQUEST__LEGACY | true; ZERO=ZERO; 0,0; 3; —; 157 |
| K_RUN_REQUEST__OWNED | true; ZERO=ZERO; 1,1; 3; leq=true, cv=true; 252 |
| K_RUN_REQUEST__FENCED | true; ZERO=null; 0,0; 0; fm=true, rej=true; 120 |
| K_RUN_REQUEST_EMPTY__LEGACY | true; ZERO=ZERO; 0,0; 0; —; 61 |
| K_RUN_REQUEST_EMPTY__OWNED | true; ZERO=ZERO; 1,1; 0; leq=true, cv=true; 150 |
| K_RUN_REQUEST_EMPTY__FENCED | true; ZERO=null; 0,0; 0; fm=true, rej=true; 111 |
| K_JOB_RUN__LEGACY | true; ZERO=ZERO; 0,0; 3; —; 160 |
| K_JOB_RUN__OWNED | true; ZERO=ZERO; 1,1; 3; leq=true, cv=true; 255 |
| K_JOB_RUN__FENCED | true; ZERO=null; 0,0; 0; fm=true, rej=true; 125 |
| K_JOB_RUN_ROLLBACK__LEGACY | true; ZERO=ZERO; 0,0; 3; —; 361 |
| K_JOB_RUN_ROLLBACK__OWNED | true; ZERO=ZERO; 1,1; 3; leq=true, cv=true; 432 |
| K_JOB_RUN_ROLLBACK__FENCED | true; ZERO=null; 0,0; 0; fm=true, rej=true; 136 |
| K_JOB_REJECT__LEGACY | true; NONE=NONE; 0,0; 0; —; 112 |
| K_JOB_REJECT__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 300 |
| K_JOB_REJECT__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 106 |
| K_JOB_STAGE__LEGACY | true; NONE=NONE; 0,0; 0; —; 106 |
| K_JOB_STAGE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 206 |
| K_JOB_STAGE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 113 |
| K_JOB_SAVE__LEGACY | true; NONE=NONE; 0,0; 0; —; 125 |
| K_JOB_SAVE__OWNED | true; NONE=NONE; 1,1; 0; leq=true, cv=true; 248 |
| K_JOB_SAVE__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 109 |
| K_JOB_EVENT__LEGACY | true; NONE=NONE; 0,0; 3; —; 62 |
| K_JOB_EVENT__OWNED | true; NONE=NONE; 1,1; 3; leq=true, cv=true; 179 |
| K_JOB_EVENT__FENCED | true; NONE=null; 0,0; 0; fm=true, rej=true; 109 |

### Матрица F (3 factory × 3) — 9 cases

| Case ID | passed / details / мс |
|---|---|
| F_API__LEGACY | true; constructor/identity: rc=0, fm=true, ret —; 61 |
| F_API__OWNED | true; constructor с coordinator: rc=0 (owned constructor ≠ owned mutation), fm=true, ret —; 59 |
| F_API__FENCED | true; arm synthetic lease + mutator вызов: refusal до validator/runner/service (rej=true), fm=true; 107 |
| F_APPLIER__LEGACY | true; rc=0, fm=true, ret —; 59 |
| F_APPLIER__OWNED | true; Applier.api тот же coordinator; rc=0, fm=true, ret —; 58 |
| F_APPLIER__FENCED | true; rej=true, fm=true; 110 |
| F_SINGBOX__LEGACY | true; rc=0, fm=true, ret —; 87 |
| F_SINGBOX__OWNED | true; rc=0, fm=true, ret —; 87 |
| F_SINGBOX__FENCED | true; rej=true, fm=true; 110 |

### Extras — 16 cases

| Case ID | passed / details / мс |
|---|---|
| H_SIGNATURE | true; async/generator signature отвергнута owned_function: rej=true, rc=0; 51 |
| H_DEFERRED | true; deferred return не публикует: rej=true, rc=0; 48 |
| H_NO_VERIFIER | true; без verifier нет публикации: rej=true, rc=0; 63 |
| H_NESTED_ERROR | true; nested taint при error: rej=true, rc=0, uw=1; 144 |
| H_NESTED_RETURN | true; nested taint при return: rej=true, rc=0, uw=1; 137 |
| K_RUN_FAILED | true; failed job: UNKNOWN 1 (uw=1), rc=0, sc=3 — failed state записан, это не rollback/успех; 396 |
| K_RUN_INVALID | true; invalid: UNKNOWN 1, rc=0; 151 |
| K_REQUEST_FOREIGN | true; чужой injected Job отказан до чтения/удаления request внутри outer ticket: UNKNOWN 1 (отказ после admission, не отсутствие ticket), rc=0; 168 |
| K_REQUEST_NO_JOB | true; ПОЛОЖИТЕЛЬНЫЙ: автоматический Job construction (recorder-обёрнутый constructor, exact type/ownership/state/removal проверены): rc=1, g=1, cv=true, sc=3; 240 |
| K_SWALLOWED_SAVE | true; swallowed OSError: UNKNOWN 1, rc=0; 158 |
| I_PANEL_CORE | true; ПОЛОЖИТЕЛЬНЫЙ composite PANEL→CORE: роль union PANEL/CORE/LIFECYCLE, без раннего lease/receipt (ранний lease-запрос rej=true), один финальный rc=1, g=1, cv=true, sc=3; 303 |
| B_RUN_SHADOW | true; shadow нового Job.run hook — объявление boundary 37 отклоняет: rej=true, rc=0 (business body не вызывался); 59 |
| B_REJECT_SHADOW | true; rej=true, rc=0; 57 |
| B_STAGE_SHADOW | true; rej=true, rc=0; 58 |
| B_SAVE_SHADOW | true; rej=true, rc=0; 53 |
| B_EVENT_SHADOW | true; rej=true, rc=0; 78 |

Expected/completed/passed/remaining NOT_RUN: **145/145/145/0** (global_scope_stop=false).
Группы actual executed/passed: P 78/78, K 42/42, F 9/9, extras 16/16.
LEGACY vs OWNED differential: 40 writer-вариантов — OWNED дал ровно 1 final
receipt/generation, legacy_equivalent=true, completion_verified=true (сравнение fixture
verifier'ом с LEGACY fingerprint ДО completion, не checksum сам с собой; возвращаемые
enum совпали в 40/40); 3 F constructor-варианта — OWNED с receipts 0 (owned factory ≠
owned mutation). LEGACY receipts=0 во всех 43. FENCED во всех 43: refusal до body
(включая validation/early unlink), fixture_unchanged=true, stub trace 0, receipts 0.
Matrix OWNED 40 final receipts vs 3 owned constructors receipts 0 — раздельно.
Extras: положительных 2 (K_REQUEST_NO_JOB, I_PANEL_CORE), UNKNOWN 4 (K_RUN_FAILED/
K_RUN_INVALID/K_REQUEST_FOREIGN/K_SWALLOWED_SAVE — rc=0, uw=1; failed job записал failed
state — не rollback), отказные/definition 10 (H×5, B×5 shadows — business body не
вызывался). Не «145 успешных применений». Business return enums ≠ command exit rc;
observed null при отказе ≠ 0; nullable counts как в readout.
Audit: audit_registered=true, unexpected_forbidden_io=**0**, workload_subprocesses=**0**,
global_scope_stop=false, source_files=**116**, batch 25269 мс.
Seven runtime gates false: installed_runtime_changed/runtime_actor_binding_implemented/
runtime_writer_fence_verified/runtime_verifier_implemented/runtime_recovery_implemented/
repair_implemented/active_faults_authorized = **false** (даже 145/145).
Network_requests/live_gateway_operations: **0/0**. collector_exit_rc=NOT_COLLECTED.

## Решение

Принят полностью в optional source-flow/real bodies/fake external effects scope (145/145):
real source bodies (private frozen_ad копия) на fixture JSON/dummy binaries/text с
подставными Store/release/service/runner — реальная бизнес-семантика сохранена
(differential OWNED↔LEGACY 40/40, включая return enum и bytes/modes/entries/stub counts),
AST-проверка старых тел дополнительно выполнена helper'ом. 23 публичных panel writers и
direct save/_update_locked/_update — owned admission до validation/read/lock/write при
explicit coordinator; core state/request hooks закрыли ранний state write/request unlink
до update hook; run_request прокидывает coordinator в take_request/новый Job; чужой
injected Job отказан после admission с UNKNOWN (не отсутствие ticket); фабрики
распространяют optional coordinator (Applier.api идентичность подтверждена), при этом
создание объекта не является writer admission (receipts 0). Composite PANEL→CORE —
роль union без раннего lease, один финальный receipt. Boundary 37 (32+5 новых Job hooks)
отклоняет любые shadows. Это **не** global runtime composition: daemon/CLI/service
callers по-прежнему не задают coordinator; None legacy unfenced; FreePool constructor/
prune и другие прямые/вложенные writers, path aliases, межпроцессный/version/boot
handshake открыты; Core.start только ставит request и асинхронно просит systemd
--no-block — его hook не удерживает ticket на весь срок отдельной службы, cross-process
dispatch/fence не реализован. Store stub ≠ SQLite proof; release stub ≠ GitHub query;
factories stub find_binary/services ≠ version probes; core rollback/forget — dummy dirs
в private notes; registry boot/lease clock synthetic; Job.now в матрице 10, default Job
factory real wall timestamp только в private dummy JSON (не deadline proof). Differential
fixture verifier ≠ runtime KERNEL/API/process/resource verifier. Нет install/repair/
recovery/bootstrap/fault authorization — по PASS никакой установки. LiveC
BLOCKED_BOOTSTRAP; independent original-on/code/unit rescue до установки/fault.
Источник partial/STOP: нет (не было; все 145 выполнены, guard не блокировал ничего
неожиданного). Only ThinkCentre; working LAN; host не LAN-client proof.
Full wave3/D1-on/faults/LAN UDP/IPv6/DNS/E4/performance/all Tailscale — открыты; не
wave4/DAE. Исторические evidence AE112/AD130/AC51/AB32/AA22/Z19/Y6/X26/W25/U/V/M/J/L/
Npartial/Pblocked/Q/Rnegative/S/T сохранены без пересмотра (не повторялись).

Privacy review всего Markdown выполнен перед единственной публикацией: никаких raw
configs/status/logs/kernel/URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/UID/
home paths/registry ids/boot/tokens/private hashes/fingerprints/case files/raw exceptions/
argv/business result texts — только fixed case IDs/enums/bools/counts/ms/rc/Git/source
SHA/public repo file:line; 116 публичных manifest hashes в отчёт не вставлялись.
Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3af-2026-11-03.md, коммит «Отчёт:
XGW 0.2.0, wave3af — source flow, panel/core writers и factories», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 03.11 15:31, перехват
ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не было; 3+116 frozen
файлов/started/worker-claimed/progress/summary/cases остались в заметках вне Git.
