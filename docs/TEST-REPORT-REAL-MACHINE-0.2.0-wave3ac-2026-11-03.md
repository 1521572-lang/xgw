# Отчёт: XGW wave3ac — adapters diagnostics и fake-process batch

MSK дата/интервал: 2026-11-03, 14:42:04–14:50+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 8aae0fb06396df406ebe9221173e5bb426230c90 /
tree 2275eb2061db7631910d8e0fe362cbfc9232aacb (S2.1, предок cce1d22… — отчёт ab;
SOURCE_PREFLIGHT_OK). Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
Source diff ровно 3 добавления (проверено программно в S2.1/F3 против pin:
SOURCE_DIFF_THREE_DORMANT_ADDITIONS): src/xgw/ownership.py (без изменений с AB) +
src/xgw/ownership_adapters.py + src/xgw/ownership_diagnostics.py; прежние
src/packaging/config/CLI/entrypoints/stand helpers неизменны; новые модули
существующим runtime не импортируются, не устанавливаются, не активируются.
Все 5 source SHA / freeze 0700/0600: WRITER_SUPERBATCH_FROZEN 5 + S2.4b
WRITER_SUPERBATCH_READY rc0 (~/xgw-w3ac 0700; batch.py ← wave3_writer_superbatch.py
3d6b821fd2197043456c2c2d004056f401a1ca7ed5ff08f58f3e147494062b2f; ownership.py
2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5; ownership_adapters.py
70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3;
ownership_diagnostics.py f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d;
fake_driver.py ← wave3_fake_recovery.py
a287ed4d611a5a1f10d9d7c2043c83367282f89265b50d4a844f034c944fc81b; все 0600 nlink=1;
helper при start сам проверил 4 зависимости по SHA и импортировал private
frozen_ac-package, не installed XGW; python3 -I -B, ordinary UID; внутренние
_batch/_hold/_controller/_driver вручную не вызывались). Existing runtime/installed
runtime unchanged: все 6 флагов runtime/repair=false, продукт не менялся (не
pip install/xgw install/restart/reload). NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3
EXECUTOR_NNP_OK); sudo rc 0; действий владельца не требовалось. Before/after: HEALTHY
с 02.11 19:56; перехват ВКЛЮЧЁН (не переключался); pool «выключен; регион EU (строго)» —
без изменений; Xray 26.10.31 / sing-box 1.14.4; связь живая в обоих концах.
Installed 110-tree/root DAC/real boot/Y material/старые batches (AB32/AA22/Z19/Y6/X26/
W25) NOT_RUN — не повторялись; Y snapshot PLANNED_NOT_ARMED не читался.

| Этап | Реальный rc/file/marker | Факты | Limits |
|---|---|---|---|
| S1/S2 | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 14:42:04; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_THREE_DORMANT_ADDITIONS + PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; WRITER_SUPERBATCH_FROZEN 5/READY | Не установка; статус grep-строками |
| S3 start | rc 0 / **WRITER_INTEGRATION_BATCH_STARTED** | Успешный Popen collector; EXCL started/worker-claimed/progress | Только запуск, ещё не PASS; повторный start запрещён |
| S3 monitor | rc 0 / **BATCH_FINISHED WRITER_INTEGRATION_BATCH_RECORDED 51 51** | Прогресс 44→46→50 (5с опрос, предел 180с) | summary найден ≠ case PASS; monitor rc ≠ deadline сети |
| S3 show | rc 0 / wrapper.file=**summary.json** | Финальные собранные данные (не checkpoint) | collector_exit_rc=**NOT_COLLECTED** (асинхронный collector; из show 0 не берётся) |
| S3 shape | rc 0 / FINAL_SHAPE_VALID True / ALL_CASES_PASSED True | 51 ID в точном порядке; 6 флагов false; 0/0; virtual=true; clock bool | Командные rc start/monitor/show/shape записаны раздельно |
| A | 28 executed / **28 passed** | COMPLETED 11 (A01–A07,A20,A21,A27 + A22/A23 passed), REFUSED 2, UNKNOWN 15 | Caller assertions only; runtime_verifier_implemented=false в каждом |
| B | 16 executed / **16 passed** | READONLY диагностика; все repair_authorized=false, runtime_fence_verified=false; недостающие counts=null не 0 | Read-only / не repair |
| D | 7 executed / **7 passed** | Положительных restore **2** (D01,D02); expected failure **1** (D05); refusals **2** (D06,D07); unused **2** (D03,D04); timings observed **5** | Fake file only; case PASS ≠ restored |
| S4 | rc0 ×2 | HEALTHY с 02.11 19:56/включён; «выключен; регион EU (строго)»; связь живая | Bookends, не Y-kernel/PID/RPDB after |

## Все 51 cases

По фактическому summary.json readout (все passed=true; reason/error_class поfail-случаям
не потребовались):

| Case ID | Actual passed/reason/errorclass/details/elapsed_ms |
|---|---|
| A01_CAPTURE | true; COMPLETED/CALLER_ASSERTION_RECORDED; entered/verified/attempted=true; retained_receipt=true; cleanup=NOT_NEEDED; 121 |
| A02_PANEL | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 85 |
| A03_PEERS | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 81 |
| A04_CORE | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 83 |
| A05_API | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 89 |
| A06_TUN_HOOK | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 85 |
| A07_LIFECYCLE | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 82 |
| A08_FENCED_NO_CALLBACK | true; REFUSED/ADMISSION_REFUSED; entered=false (callback не начинался); 40 |
| A09_UNKNOWN_NO_CALLBACK | true; REFUSED/ADMISSION_REFUSED; entered=false; 89 |
| A10_OPERATION_ERROR | true; UNKNOWN/OPERATION_RAISED; unknown_recorded=true; cleanup=UNKNOWN_RECORDED; 87 |
| A11_VERIFIER_ERROR | true; UNKNOWN/VERIFIER_RAISED; unknown_recorded=true; cleanup=UNKNOWN_RECORDED; 83 |
| A12_DEFAULT_EVIDENCE | true; UNKNOWN/VERIFICATION_REFUSED; 86 |
| A13_BARE_BOOL_EVIDENCE | true; UNKNOWN/VERIFICATION_REFUSED; 84 |
| A14_FALSE_CHECK | true; UNKNOWN/VERIFICATION_REFUSED; 83 |
| A15_STRING_CHECK | true; UNKNOWN/VERIFICATION_REFUSED; 82 |
| A16_DUPLICATE_CHECK | true; UNKNOWN/VERIFICATION_REFUSED; 84 |
| A17_UNKNOWN_CHECK | true; UNKNOWN/VERIFICATION_REFUSED; 84 |
| A18_LIST_CHECKS | true; UNKNOWN/VERIFICATION_REFUSED; 85 |
| A19_UNKNOWN_OUTCOME | true; UNKNOWN/VERIFICATION_REFUSED; 84 |
| A20_NOOP_RECEIPT | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 84 |
| A21_ROLLBACK_RECEIPT | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 86 |
| A22_KEYBOARD_INTERRUPT | true; exception-семантика обработана; 84 |
| A23_SYSTEM_EXIT | true; exception-семантика обработана; 82 |
| A24_PRE_REPLACE_ACK | true; UNKNOWN/COMPLETION_UNCERTAIN; cleanup=UNKNOWN_RECORD_UNCONFIRMED; 63 |
| A25_POST_REPLACE_ACK | true; UNKNOWN/COMPLETION_UNCERTAIN; retained_receipt=true; cleanup=UNKNOWN_RECORD_UNCONFIRMED; 63 |
| A26_UNKNOWN_RECORD_FAILURE | true; UNKNOWN/OPERATION_RAISED; unknown_recorded=false; cleanup=UNKNOWN_RECORD_UNCONFIRMED; 38 |
| A27_NESTED_ADMISSION | true; COMPLETED/CALLER_ASSERTION_RECORDED; retained_receipt=true; 176 |
| A28_EMPTY_CHECKS | true; UNKNOWN/VERIFICATION_REFUSED; 85 |
| B01_CLEAN_READONLY | true; CLEAN_IDLE/OBSERVED_ONLY; baseline_valid=true; writers=0; unknown=0; receipts=0; phase=IDLE; 1 |
| B02_LIVE_READONLY | true; LIVE_WRITERS/OBSERVED_ONLY; writers=1; phase=IDLE; 40 |
| B03_UNKNOWN_READONLY | true; UNKNOWN_WRITERS/OBSERVED_ONLY; writers=1; unknown=1; 124 |
| B04_ARMED_READONLY | true; RECOVERY_ARMED/OBSERVED_ONLY; phase=ARMED; 50 |
| B05_RUNNING_READONLY | true; RECOVERY_RUNNING/OBSERVED_ONLY; phase=RUNNING; 106 |
| B06_VALID_STAGE_NOT_PROMOTED | true; STAGE_VALID_UNPROVEN/NO_AUTOREPAIR; stage_valid=true — не promoted; 29 |
| B07_TRUNCATED_STAGE | true; STAGE_REFUSED/INVALID_JSON; stage_valid=false; 30 |
| B08_FOREIGN_STAGE | true; STAGE_UNRELATED/MANUAL_REVIEW_REQUIRED; stage_valid=false; 29 |
| B09_STALE_STAGE | true; STAGE_UNRELATED/MANUAL_REVIEW_REQUIRED; stage_valid=false; 28 |
| B10_DUPLICATE_STAGE_KEYS | true; STAGE_REFUSED/DUPLICATE_JSON_KEY; 27 |
| B11_BOOT_MISMATCH | true; boot mismatch зафиксирован; 0 |
| B12_BAD_MODE | true; BASELINE_REFUSED/PRIVATE_METADATA; baseline_valid=false; writers/unknown/receipts=null (не 0); phase=UNKNOWN; 1 |
| B13_STAGE_SYMLINK | true; STAGE_REFUSED/STORE_IO_OR_UNSUPPORTED; 1 |
| B14_CORRUPT_BASELINE_NO_ZERO_COUNTS | true; BASELINE_REFUSED/INVALID_JSON; counts=null (не 0); 1 |
| B15_ABSENT_STORE_NOT_CREATED | true; отсутствующий store не создан; 0 |
| B16_REAL_BUSY_DIAGNOSTIC | true; bounded_refusal=true; holder_rc=-15; own_child_cleanup_confirmed=true; 379 |
| D01_CONTROLLER_EXIT_FAKE_RESTORE | true; controller_rc=0; expected=observed=FAKE_RESTORED; fake_baseline=true; dispatched=true; launch=true; elapsed_ms=1553; within_budget=true; timing_measured=true; 1820 |
| D02_CONTROLLER_CRASH_FAKE_RESTORE | true; controller_rc=9; FAKE_RESTORED; baseline=true; dispatched=true; launch=true; elapsed_ms=1548; within_budget=true; 1765 |
| D03_UNUSED_EXPIRES | true; controller_rc=0; EXPIRED_UNUSED; baseline=true; dispatched=false; elapsed_ms=1543; within_budget=true; 1758 |
| D04_LATE_DISPATCH_REFUSED | true; controller_rc=0; EXPIRED_UNUSED; baseline=true; dispatched=false (поздний fault не прошёл); elapsed_ms=1548; within_budget=true; 2302 |
| D05_EXPECTED_FAKE_RESTORE_FAILURE | true; controller_rc=0; FAILED; fake_baseline=false; dispatched=true; elapsed_ms=1550; within_budget=true; 1765 |
| D06_FOREIGN_NONCE_REFUSED | true; controller_rc=3; REFUSED; baseline=true; dispatched=false; elapsed_ms=null; within_budget=null; timing_measured=false; 353 |
| D07_BAD_BASELINE_REFUSED | true; controller_rc=3; REFUSED; baseline=false; dispatched=false; elapsed_ms=null; within_budget=null; timing_measured=false; 318 |

Total/passed: **51/51**; NOT_RUN среди cases нет (fail-случаев нет); итог final —
summary.json (не checkpoint/progress). Final marker/shape:
**WRITER_INTEGRATION_BATCH_RECORDED** / DORMANT_ADAPTER_DIAGNOSTIC_AND_FAKE_FILE_DRIVER /
FINAL_SHAPE_VALID=True / ALL_CASES_PASSED=True (командные rc: start 0 / monitor 0 /
show 0 / shape 0 — записаны раздельно; collector_exit_rc=NOT_COLLECTED).
real_process_cases=8/passed=8 (B16 holder + 7 D controllers; terminate собственного
fixture-child ≠ действие над службой XGW). collector_children_started=**8**
(holder 1 + controllers 7; start/status/show/collector в счётчики workload не входят) /
driver_launch_observations=**7** (из artifacts, отдельно). B16: bounded_refusal=true/
holder_rc=-15/own_child_cleanup_confirmed=true. Для всех 7 D:
controller_wait_timeout=false; controller_cleanup_confirmed=true; driver_exit_rc=
**NOT_COLLECTED** (нелюбый grandchild exit code не подменялся); readout_error_class=null.
D05 case PASS ≠ restored (expected failure подтверждён: baseline остался false).
D06/D07 отказали до ARMED: timing_measured=false/elapsed_ms=null/within_budget=null —
не нулевая длительность. Registry clock+boot синтетические; fake D clock настоящий
monotonic **measured=true**, timings_observed=**5** (D01–D05: 1553/1548/1543/1548/1550 мс
— время от fake ARMED до финального file write, не end-to-end/45с сети; budget 4с, все
within_budget=true; late 2с controller отказал fake fault — D04). Six runtime/repair
flags false: installed_runtime_changed/runtime_entrypoints_integrated/
runtime_writer_fence_installed/runtime_recovery_implemented/active_faults_authorized/
repair_implemented = **false** (даже 51/51). Network_requests/live_gateway_operations:
**0/0**. Batch суммарно 16987 мс.

## Решение

Принят полностью в scoped ветвях (A 28/28, B 16/16, D 7/7): A — generic callback
adapter с verifier assertions (завершение с caller assertion+receipt; fenced/unknown
admission отказ без callback; operation/verifier errors → UNKNOWN с cleanup; все
invalid evidence — default/bare bool/false/string/duplicate/unknown/list/empty →
VERIFICATION_REFUSED; KeyboardInterrupt/SystemExit обработаны; pre/post replace ack →
COMPLETION_UNCERTAIN с UNKNOWN_RECORD_UNCONFIRMED; noop/rollback receipts; nested
admission) — COMPLETED есть только caller assertion + registry receipt, не готовый
KERNEL/API verifier; B — read-only диагностика state/stage/boot/metadata (clean/live/
unknown/armed/running; valid stage STAGE_VALID_UNPROVEN — это НЕ разрешение repair,
NO_AUTOREPAIR; truncated/foreign/stale/duplicate/symlink stage классифицированы;
boot mismatch; bad mode/corrupt baseline с counts=null не 0; absent store не создан;
real busy — bounded refusal holder rc=-15 с cleanup собственного child) — не repair;
D — конечный detached fake process вернул файл к BASELINE после exit (D01) и crash
controller (D02 rc 9) в user case,EXPECTED refusal чужого nonce/baseline (D06/D07),
expiry unused/late dispatch (D03/D04), expected failure (D05) — fake file тест, НЕ
сетевой возврат/systemd/reboot/cgroup/suspend/45s proof; после исчезновения controller
collector ничего не восстанавливает, только наблюдает artifact.
Реальные entrypoints/fence/verifier/repair/recovery/bootstrap — NOT_IMPLEMENTED (6
флагов false). Источник partial/непройденных prerequisites/STOP: нет (не было;
все ветви выполнены; repeat не потребовался).
Y snapshot PLANNED_NOT_ARMED; installed runtime не менялся; сеть/продукт не трогались.
Только ThinkCentre; working LAN; host не LAN-client proof. Full wave3 / D1-on / faults /
LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE не
начинались. Исторические evidence AB32/AA22/Z19/Y6/X26/W25/U/V/M/J/L/Npartial/
Pblocked/Q/Rnegative/S/T сохранены без пересмотра (не повторялись).
Дальше (без автоматического live-перехода): fixes по evidence либо следующий укрупнённый
готовый dormant integration/repair/bootstrap dry пакет.

Privacy review всего Markdown выполнен перед единственной публикацией: никаких raw
config/status/logs/kernel/real URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/
UID/home paths/private hashes/boot/registry ids/tokens/nonce/timestamps/raw case files/
unknown child stdout/исключений — только fixed enums/case IDs/bools/counts/timings ms/rc/
Git/source SHA. Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ac-2026-11-03.md,
коммит «Отчёт: XGW 0.2.0, wave3ac — adapters diagnostics и fake-process batch», push в
freepool (REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11
19:56, перехват ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не
было; 5 frozen файлов/started/worker-claimed/progress/summary/sandbox остались в
заметках вне Git.
