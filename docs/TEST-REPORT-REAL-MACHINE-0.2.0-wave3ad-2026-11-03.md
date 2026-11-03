# Отчёт: XGW wave3ad — source hooks fake-effects batch

MSK дата/интервал: 2026-11-03, 16:22:27–16:36+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 9f0bbbbab15d49d4bbace45f11a6ec3aae54a6e2 /
tree cb1bbd23683f3b02ad01f5016ec4009d92b0791e (S2.1, предок 04a21bd… — отчёт ac;
SOURCE_PREFLIGHT_OK). Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
Source diff ровно 4A7M (проверено программно в S2.1/F3: SOURCE_DIFF_FOUR_ADD_SEVEN_MODIFY):
A = ownership.py/ownership_adapters.py/ownership_diagnostics.py/ownership_hooks.py;
M = net/capture.py, freepool/backend.py, apply/applier.py, apply/singbox.py, cores.py,
xraycore/api.py, managed.py — получили opt-in hooks. Existing callers всё ещё НЕ передают
coordinator: None-путь сохраняет legacy и **не** является fence; 7 runtime gates false.
HelperSHA 9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917;
ManifestSHA 69283e6ff3f6e84e7e5415cd6d4dae2dd5f907959c505c14b97003fde9694091;
114 source files / freeze 0700/0600: SOURCE_HOOK_FROZEN 114 + S2.4b SOURCE_HOOK_READY
rc0 (manifest закрепил полный src/xgw *.py inventory 114 файлов, каждый SHA сверен в
S2.1/freeze/start; ~/xgw-w3ad 0700, batch.py/manifest.json/source/** 0600, dirs 0700;
helper импортировал private package frozen_ad, не installed XGW; worker до imports
поставил CPython audit guard (process/socket/fork/exec/kill/ctypes/write вне notes —
refused), self-registration подтверждена: audit_registered=true).
Installed runtime не обновлялся (не pip install/xgw install/restart/reload);
None-legacy не fenced; mandatory actor binding/real verifier/bootstrap не реализованы.
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. Before/after: HEALTHY с 03.11 15:31 (метка сместилась с «02.11 19:56»
между прогонами — внешний рестарт вне моих операций: мои прогоны не выполняют live
gateway operations; записано, не диагностировалось — сетевые операции запрещены ТЗ);
перехват ВКЛЮЧЁН (не переключался); pool «выключен; регион EU (строго)» — без изменений;
Xray 26.10.31 / sing-box 1.14.4; связь живая в обоих концах. Старые batches (AC51/AB32/
AA22/Z19/Y6/X26/W25) и installed 110-tree NOT_RUN; Fake D в этом прогоне НЕ исполнялся;
Y root material не читался (snapshot PLANNED_NOT_ARMED).

| Этап | rc/file/marker | Факты | Limits |
|---|---|---|---|
| S1/S2 | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 16:22:27; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_FOUR_ADD_SEVEN_MODIFY + SOURCE_MANIFEST_MATCHED 114 + PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; SOURCE_HOOK_FROZEN 114/READY | Не установка; sourceManifest public, не аттестация живых модулей |
| S3 start | rc 0 / **SOURCE_HOOK_BATCH_STARTED** | Popen collector, EXCL worker claim/atomic progress | Только запуск, не 130 PASS; повторный start запрещён |
| S3 monitor | rc 0 / **BATCH_FINISHED SOURCE_HOOK_BATCH_RECORDED 130 130** | Прогресс 44→77→112 (5с опрос, предел 300с) | summary найден ≠ case PASS; не network deadline |
| S3 show | rc 0 / wrapper.file=**summary.json** | Финальный итог (не checkpoint); collector_exit_rc=**NOT_COLLECTED** | Read 0 не PASS; командные rc записаны раздельно |
| S3 shape | rc 0 / FINAL_SHAPE_VALID True / ALL_CASES_PASSED True | 130 ID в точном порядке ТЗ; 7 флагов false; 0/0/0; audit_registered=true; forbidden_io=0; source_files=114 | |
| Matrix | 114 executed / **114 passed** | LEGACY: business return подтверждён, receipts=0 во всех 38; OWNED: тот же body, receipts=1 во всех 38; FENCED: refusal до effects — fixture_unchanged=true/stubs=0/receipts=0 во всех 38 | Real source / fake effects; None не fence proof |
| Extras | 16 executed / **16 passed** | 9 H-context, 3 E-error, 4 R-reader | Context/errors/readers |
| S4 | rc0 ×2 | HEALTHY с 03.11 15:31/включён; «выключен; регион EU (строго)»; связь живая | Bookends, не Y-kernel/PID/RPDB after |

## Все 130 cases

Все passed=true; errorclass/public source:line не потребовались (fail-случаев нет —
ни одного несовпадения business return, ни одного unexpected audit denial).
Сокращения: «ф» = fixture_unchanged; s=N = stub_calls (FakeRunner/API/service/TUN
заглушки — команды НЕ исполнялись); r=N = registry_receipts; мс = elapsed_ms.

| Case ID | passed/ф/s/r/мс |
|---|---|
| C_SAVE__LEGACY | true; нет; s=0; r=0; 95 |
| C_SAVE__OWNED | true; нет; s=0; r=1; 187 |
| C_SAVE__FENCED | true; да; s=0; r=0; 98 |
| C_LOAD_OFF__LEGACY | true; нет; s=3; r=0; 108 |
| C_LOAD_OFF__OWNED | true; нет; s=3; r=1; 214 |
| C_LOAD_OFF__FENCED | true; да; s=0; r=0; 98 |
| C_UP__LEGACY | true; нет; s=1; r=0; 56 |
| C_UP__OWNED | true; нет; s=1; r=1; 148 |
| C_UP__FENCED | true; да; s=0; r=0; 98 |
| C_ENABLE__LEGACY | true; нет; s=1; r=0; 96 |
| C_ENABLE__OWNED | true; нет; s=1; r=1; 193 |
| C_ENABLE__FENCED | true; да; s=0; r=0; 112 |
| C_DISABLE__LEGACY | true; нет; s=1; r=0; 101 |
| C_DISABLE__OWNED | true; нет; s=1; r=1; 188 |
| C_DISABLE__FENCED | true; да; s=0; r=0; 108 |
| C_OPEN__LEGACY | true; нет; s=1; r=0; 57 |
| C_OPEN__OWNED | true; нет; s=1; r=1; 161 |
| C_OPEN__FENCED | true; да; s=0; r=0; 133 |
| C_CLOSE__LEGACY | true; нет; s=1; r=0; 65 |
| C_CLOSE__OWNED | true; нет; s=1; r=1; 150 |
| C_CLOSE__FENCED | true; да; s=0; r=0; 121 |
| C_DOWN__LEGACY | true; нет; s=5; r=0; 108 |
| C_DOWN__OWNED | true; нет; s=5; r=1; 221 |
| C_DOWN__FENCED | true; да; s=0; r=0; 106 |
| C_TUN__LEGACY | true; нет; s=2; r=0; 55 |
| C_TUN__OWNED | true; нет; s=2; r=1; 174 |
| C_TUN__FENCED | true; да; s=0; r=0; 109 |
| C_TIDY__LEGACY | true; да; s=1; r=0; 63 |
| C_TIDY__OWNED | true; да; s=1; r=1; 146 |
| C_TIDY__FENCED | true; да; s=0; r=0; 122 |
| C_TS_DIRECT__LEGACY | true; нет; s=1; r=0; 57 |
| C_TS_DIRECT__OWNED | true; нет; s=1; r=1; 145 |
| C_TS_DIRECT__FENCED | true; да; s=0; r=0; 106 |
| C_TS_EARLY__LEGACY | true; нет; s=0; r=0; 64 |
| C_TS_EARLY__OWNED | true; нет; s=0; r=1; 173 |
| C_TS_EARLY__FENCED | true; да; s=0; r=0; 111 |
| C_TS_FALLBACK__LEGACY | true; нет; s=1; r=0; 59 |
| C_TS_FALLBACK__OWNED | true; нет; s=1; r=1; 162 |
| C_TS_FALLBACK__FENCED | true; да; s=0; r=0; 113 |
| B_SAVE__LEGACY | true; нет; s=0; r=0; 113 |
| B_SAVE__OWNED | true; нет; s=0; r=1; 234 |
| B_SAVE__FENCED | true; да; s=0; r=0; 193 |
| B_ELEMENT__LEGACY | true; да; s=1; r=0; 97 |
| B_ELEMENT__OWNED | true; да; s=1; r=1; 143 |
| B_ELEMENT__FENCED | true; да; s=0; r=0; 134 |
| B_PREPARE__LEGACY | true; нет; s=6; r=0; 148 |
| B_PREPARE__OWNED | true; нет; s=6; r=1; 230 |
| B_PREPARE__FENCED | true; да; s=0; r=0; 99 |
| B_STOP__LEGACY | true; нет; s=4; r=0; 124 |
| B_STOP__OWNED | true; нет; s=4; r=1; 187 |
| B_STOP__FENCED | true; да; s=0; r=0; 109 |
| B_RECONCILE__LEGACY | true; да; s=2; r=0; 56 |
| B_RECONCILE__OWNED | true; да; s=2; r=1; 138 |
| B_RECONCILE__FENCED | true; да; s=0; r=0; 95 |
| X_APPLY__LEGACY | true; нет; s=2; r=0; 102 |
| X_APPLY__OWNED | true; нет; s=2; r=1; 182 |
| X_APPLY__FENCED | true; да; s=0; r=0; 108 |
| X_ROLLBACK__LEGACY | true; нет; s=2; r=0; 99 |
| X_ROLLBACK__OWNED | true; нет; s=2; r=1; 194 |
| X_ROLLBACK__FENCED | true; да; s=0; r=0; 100 |
| S_APPLY__LEGACY | true; нет; s=1; r=0; 111 |
| S_APPLY__OWNED | true; нет; s=1; r=1; 237 |
| S_APPLY__FENCED | true; да; s=0; r=0; 102 |
| S_EQUAL__LEGACY | true; нет; s=0; r=0; 58 |
| S_EQUAL__OWNED | true; нет; s=0; r=1; 148 |
| S_EQUAL__FENCED | true; да; s=0; r=0; 113 |
| S_REMOVE__LEGACY | true; нет; s=1; r=0; 64 |
| S_REMOVE__OWNED | true; нет; s=1; r=1; 202 |
| S_REMOVE__FENCED | true; да; s=0; r=0; 110 |
| S_DEFER__LEGACY | true; нет; s=0; r=0; 111 |
| S_DEFER__OWNED | true; нет; s=0; r=1; 195 |
| S_DEFER__FENCED | true; да; s=0; r=0; 100 |
| S_ROLLBACK__LEGACY | true; нет; s=1; r=0; 99 |
| S_ROLLBACK__OWNED | true; нет; s=1; r=1; 200 |
| S_ROLLBACK__FENCED | true; да; s=0; r=0; 117 |
| S_RESTART__LEGACY | true; да; s=1; r=0; 101 |
| S_RESTART__OWNED | true; да; s=1; r=1; 157 |
| S_RESTART__FENCED | true; да; s=0; r=0; 121 |
| API_ADD_OUT__LEGACY | true; да; s=1; r=0; 82 |
| API_ADD_OUT__OWNED | true; да; s=1; r=1; 167 |
| API_ADD_OUT__FENCED | true; да; s=0; r=0; 142 |
| API_RM_OUT__LEGACY | true; да; s=1; r=0; 99 |
| API_RM_OUT__OWNED | true; да; s=1; r=1; 156 |
| API_RM_OUT__FENCED | true; да; s=0; r=0; 121 |
| API_ADD_IN__LEGACY | true; да; s=1; r=0; 55 |
| API_ADD_IN__OWNED | true; да; s=1; r=1; 140 |
| API_ADD_IN__FENCED | true; да; s=0; r=0; 98 |
| API_RM_IN__LEGACY | true; да; s=1; r=0; 52 |
| API_RM_IN__OWNED | true; да; s=1; r=1; 166 |
| API_RM_IN__FENCED | true; да; s=0; r=0; 106 |
| API_ROUTING__LEGACY | true; да; s=1; r=0; 53 |
| API_ROUTING__OWNED | true; да; s=1; r=1; 157 |
| API_ROUTING__FENCED | true; да; s=0; r=0; 98 |
| API_PIN__LEGACY | true; да; s=1; r=0; 75 |
| API_PIN__OWNED | true; да; s=1; r=1; 154 |
| API_PIN__FENCED | true; да; s=0; r=0; 116 |
| API_UNPIN__LEGACY | true; да; s=1; r=0; 57 |
| API_UNPIN__OWNED | true; да; s=1; r=1; 142 |
| API_UNPIN__FENCED | true; да; s=0; r=0; 101 |
| P_UPDATE__LEGACY | true; нет; s=1; r=0; 92 |
| P_UPDATE__OWNED | true; нет; s=1; r=1; 195 |
| P_UPDATE__FENCED | true; да; s=0; r=0; 107 |
| P_NOOP__LEGACY | true; нет; s=1; r=0; 60 |
| P_NOOP__OWNED | true; нет; s=1; r=1; 184 |
| P_NOOP__FENCED | true; да; s=0; r=0; 124 |
| K_UPDATE__LEGACY | true; да; s=0; r=0; 56 |
| K_UPDATE__OWNED | true; да; s=0; r=1; 139 |
| K_UPDATE__FENCED | true; да; s=0; r=0; 108 |
| K_REPLACE__LEGACY | true; нет; s=0; r=0; 95 |
| K_REPLACE__OWNED | true; нет; s=0; r=1; 208 |
| K_REPLACE__FENCED | true; да; s=0; r=0; 113 |
| K_ROLLBACK__LEGACY | true; нет; s=0; r=0; 105 |
| K_ROLLBACK__OWNED | true; нет; s=0; r=1; 199 |
| K_ROLLBACK__FENCED | true; да; s=0; r=0; 123 |
| H_NO_VERIFIER | true; s=0; r=0; 52 |
| H_NESTED_ROLES | true; s=1; r=1; 137 |
| H_TAINT | true; s=0; r=0; 149 |
| H_EXCEPTION | true; s=0; r=0; 138 |
| H_TERMINAL | true; s=0; r=0; 143 |
| H_GENERATOR | true; s=0; r=0; 135 |
| H_NESTED_GENERATOR | true; s=0; r=0; 151 |
| H_THREAD | true; s=1; r=2; 282 |
| H_FOREIGN_CONTEXT | true; s=0; r=0; 61 |
| E_BACKEND_COMPENSATION | true; s=6; r=0; 323 |
| E_FAILED_OUTCOME | true; s=0; r=0; 198 |
| E_SINGBOX_ROLLBACK | true; s=1; r=1; 294 |
| R_ADDRESS | true; s=0; r=0; 95 |
| R_OUTBOUNDS | true; s=1; r=0; 95 |
| R_INBOUNDS | true; s=1; r=0; 92 |
| R_BALANCER | true; s=1; r=0; 86 |

Total/passed/completed: **130/130/130**; remaining NOT_RUN нет; итог final — summary.json
(не checkpoint). Final marker/shape: **SOURCE_HOOK_BATCH_RECORDED** /
OPT_IN_SOURCE_HOOKS_FAKE_EFFECTS_ONLY / FINAL_SHAPE_VALID=True / ALL_CASES_PASSED=True
(командные rc: start 0 / monitor 0 / show 0 / shape 0 — раздельно;
collector_exit_rc=NOT_COLLECTED). Матрица: LEGACY 38/38 receipts=0 (business return
подтверждён в каждом); OWNED 38/38 receipts=1, промежуточных публикаций nested helpers
нет; FENCED 38/38 refusal до body effects (fixture bytes unchanged, FakeRunner trace 0,
receipts 0). Extras: H_THREAD — отдельный ticket во втором потоке (2 receipts), H_TAINT/
H_FOREIGN_CONTEXT/H_GENERATOR/H_NESTED_GENERATOR/H_TERMINAL/H_EXCEPTION — без
публикаций; E_BACKEND_COMPENSATION — 6 stub-вызовов компенсации, receipts 0;
E_SINGBOX_ROLLBACK — rollback с 1 receipt; R_ADDRESS/R_OUTBOUNDS/R_INBOUNDS/R_BALANCER —
reader-проверки synthetic, не LAN packet proof. Audit guard: audit_registered=true,
unexpected_forbidden_io=**0**, workload_subprocesses=**0** (thread fixture — не процесс).
114 source files сверены; batch суммарно 20200 мс. Семь runtime gates false:
installed_runtime_changed/runtime_actor_binding_implemented/runtime_writer_fence_verified/
runtime_verifier_implemented/runtime_recovery_implemented/repair_implemented/
active_faults_authorized = **false** (даже 130/130).
Network_requests/live_gateway_operations: **0/0**.

## Решение

Принят полностью в scope fake-effects (130/130): opt-in hooks в реальных source-методах
проверены в трёх режимах на private-копии с заглушками. LEGACY-совместимость сохранена
(None-координатор → прежнее поведение без receipts); OWNED публикует ровно один receipt
на операцию с ожидаемым return class; FENCED отказывает до эффектов (байты fixture не
меняются, trace заглушек пуст). Контекст: verifier по умолчанию отсутствует (H_NO_VERIFIER —
завершение не публикуется без assertion), taint/чужой контекст/генераторы/терминальные
вызовы не публикуют; exceptions безопасны; вложенные роли не публикуют промежуточное
поколение. Ошибки: компенсация backend после неудачи (6 вызовов), failed outcome без
публикации, rollback sing-box с receipt. Уточнение сводки AC (принято developer review,
старый отчёт не переписывался): A-ветвь AC фактически 10 COMPLETED/2 REFUSED/14 UNKNOWN/
2 terminal — мой AC-отчёт отнёс terminal к COMPLETED; общий 51 PASS не изменился.
Это НЕ install/activation: existing callers по-прежнему не передают coordinator;
None-путь не fence; K_REPLACE/K_ROLLBACK работали с dummy core files в user fixture (не
скачивали/не исполняли бинарники); API stub ≠ API запрос; FakeRunner argv ≠ исполненная
команда; Capture.mode/rules synthetic ≠ LAN packet proof/actual kernel apply;
fixture verifier caller assertions ≠ C-VERIFY. Runtime actor binding/verifier/fence/
repair/recovery/bootstrap — NOT_IMPLEMENTED (7 gates false). Источник partial/STOP: нет
(не было; все 130 выполнены, audit guard не блокировал ничего неожиданного).
Y snapshot PLANNED_NOT_ARMED; installed runtime не менялся; сеть/продукт не трогались.
Только ThinkCentre; working LAN; host не LAN-client proof. Full wave3 / D1-on / faults /
LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE не
начинались. Исторические evidence AC51/AB32/AA22/Z19/Y6/X26/W25/U/V/M/J/L/Npartial/
Pblocked/Q/Rnegative/S/T сохранены без пересмотра (не повторялись).
Дальше (без автоматического live-перехода): fixes по evidence либо mandatory binding/
composite generation/verifiers/repair/bootstrap в следующем максимальном готовом dry
пакете.

Privacy review всего Markdown выполнен перед единственной публикацией: никаких raw
case files/config/status/logs/kernel/URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/
PID/NIC/UID/home paths/registry ids/boot/tokens/private hashes/raw exceptions/argv/
result texts — только fixed case IDs/enums/bools/counts/timings ms/rc/Git/source SHA;
114 хешей манифеста в отчёт не вставлялись (SourceManifest публичный в Git). Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ad-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3ad — source hooks fake-effects batch», push в freepool (REPORT_PUBLISHED в финальном
сообщении). Конечный режим: HEALTHY с 03.11 15:31, перехват ВКЛЮЧЁН, pool прежний;
связь живая; действий владельца в прогоне не было; 2+114 frozen файлов/started/
worker-claimed/progress/summary/cases остались в заметках вне Git.
