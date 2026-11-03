# Отчёт: XGW wave3ae — bound composite и private file observer

MSK дата/интервал: ... . TestedHEAD/tree: ... . Baseline pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
Source diff6A7M, предыдущие AD114 source bytes unchanged: ... .
HelperSHA df8b24c3b392027304cd5c38a950e374471b5c37edfd2cc4c61943d68a050fb4; SupportSHA 9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917; ManifestSHA b0103bde08c7f2fa51ca2fb5c2b35aed962ab49ef8a56fc43a0696bb1af2d218.
116 source freeze/0700/0600/private frozen_ad import: ... . Installed runtime unchanged: ... .
NNP/sudo/owner actions: ... . HEALTHY/on/pool/versions/connection before/after: ... .
Source checks ≠ installed116; oldAD130/AC51/.../Yroot/installed110 NOT_RUN: ... .

| Этап | rc/file/marker | Actual facts | Limits |
|---|---|---|---|
| S1/S2 | ... | 3artifact+116freeze/baseline | Нет установки |
| start | ... | Popen only | Не worker PASS |
| monitor | ... | actual completed/final | Не case PASS |
| show/shape | ... | final/checkpoint; collector_exit_rc NOT_COLLECTED | Read0 не completion |
| S4 | ... | status/pool/connection bookends | Не kernel/LAN proof |

| Case ID | Actual passed/details/errorclass/publicsource:line/elapsed_ms |
|---|---|
|H_CAPTURE___SAVE|...|
|H_CAPTURE___LOAD|...|
|H_CAPTURE__UP|...|
|H_CAPTURE__ENABLE|...|
|H_CAPTURE__DISABLE|...|
|H_CAPTURE__OPEN|...|
|H_CAPTURE__CLOSE|...|
|H_CAPTURE__DOWN|...|
|H_CAPTURE__RESTORE_TUN|...|
|H_CAPTURE__TIDY|...|
|H_CAPTURE__TAILSCALE_DIRECT|...|
|H_CAPTURE__TAILSCALE_FALLBACK|...|
|H_PEERS___SAVE_PEERS|...|
|H_PEERS___NFT_ELEMENT|...|
|H_PEERS__PREPARE|...|
|H_PEERS__STOP|...|
|H_PEERS__RECONCILE|...|
|H_XRAY__APPLY|...|
|H_XRAY__ROLLBACK|...|
|H_SINGBOX__APPLY|...|
|H_SINGBOX__ROLLBACK|...|
|H_SINGBOX__RESTART|...|
|H_CORES__UPDATE|...|
|H_CORES__ROLLBACK|...|
|H_API__ADD_OUTBOUNDS|...|
|H_API__REMOVE_OUTBOUND|...|
|H_API__ADD_INBOUNDS|...|
|H_API__REMOVE_INBOUND|...|
|H_API__REPLACE_ROUTING|...|
|H_API__PIN|...|
|H_API__UNPIN|...|
|H_PANEL__UPDATE|...|
|M_CAPTURE|...|
|M_PEERS|...|
|M_XRAY|...|
|M_SINGBOX|...|
|M_CORES|...|
|M_API|...|
|M_PANEL|...|
|O_CAPTURE|...|
|O_PEERS|...|
|O_XRAY|...|
|O_SINGBOX|...|
|O_CORES|...|
|O_API|...|
|O_PANEL|...|
|B_INCOMPLETE|...|
|B_EXTRA|...|
|B_WRONG_TYPE|...|
|B_NO_VERIFIER|...|
|B_WRONG_COORDINATOR|...|
|B_WRONG_REGISTRY|...|
|B_REGISTRY_DRIFT|...|
|B_VERIFIER_DRIFT|...|
|B_CALL_DRIFT|...|
|B_FOREIGN_PID|...|
|B_FOREIGN_THREAD|...|
|B_NESTED|...|
|P_EMPTY|...|
|P_LIST|...|
|P_TOO_MANY|...|
|P_WRONG_STEP|...|
|P_UNKNOWN_WRITER|...|
|P_UNKNOWN_METHOD|...|
|P_ARGS_LIST|...|
|P_KWARGS_DICT|...|
|P_DUP_KEY|...|
|P_OWNER_KEY|...|
|P_USED|...|
|P_FENCED|...|
|P_NO_CHECKER|...|
|C_SB_XRAY|...|
|C_SB_XRAY_API|...|
|C_PANEL_PEERS|...|
|C_FAILED_RESULT|...|
|C_VERIFIER_EXCEPTION|...|
|C_FALSE_VERIFIER|...|
|C_STEP_EXCEPTION|...|
|C_AFTER_UNBIND|...|
|C_AFTER_HOOK_DRIFT|...|
|C_AFTER_VERIFIER_DRIFT|...|
|C_AFTER_REGISTRY_DRIFT|...|
|C_NO_EARLY_LEASE|...|
|C_CHECKER_FALSE|...|
|C_CHECKER_EXCEPTION|...|
|C_FILE_MISMATCH|...|
|C_SECOND_REJECT|...|
|C_SECOND_TERMINAL|...|
|F_PRESENT|...|
|F_ABSENT|...|
|F_TWO|...|
|F_DIGEST_MISMATCH|...|
|F_MODE|...|
|F_OWNER|...|
|F_HARDLINK|...|
|F_SYMLINK|...|
|F_PARENT_SYMLINK|...|
|F_ROOT_SYMLINK|...|
|F_FIFO|...|
|F_OVERSIZE|...|
|F_MISSING|...|
|F_ABSENT_PRESENT|...|
|F_ABSENT_SYMLINK|...|
|F_ABSENT_MISSING_PARENT|...|
|F_DIRECTORY_MODE|...|
|F_ROOT_MODE|...|
|F_DUPLICATE|...|
|F_TRAVERSAL|...|
|F_BAD_DIGEST|...|
|F_BOOL_OWNER|...|
|F_BOOL_MODE|...|
|F_EMPTY|...|

Expected/completed/passed/remainingNOT_RUN: ... . 32 hook/14 missing+foreign/12 boundary/
13 plan/17 composite/24 file case counts: ... .
Positive composites4 vs expected negatives13: ... . Positive file3/refusals21: ... .
No early receipt/partial first effect/UNKNOWN/no automatic retry: ... .
Audit registered/violations/workload subprocesses/global scope stop/source files116: ... .
Actual nullable counts, не нули из ожиданий: ... . Семь runtime gatesfalse: ... .
network_requests/live_gateway_operations0/0: ... . collector_exit_rcNOT_COLLECTED: ... .

## Решение

Принят/partial только declared source boundary + private file scope: ... .
Missing binding/hook drift failclosed ВНУТРИ explicit bundle; глобальный runtime wiring
не готов. None legacy по-прежнему unfenced. Один receipt не atomic side-effect transaction;
private file observations не KERNEL/API/process/production verifier. UID fixture не rootDAC;
boot/clock synthetic. Нет install/real fault/recovery/repair/bootstrap authorization.
Only ThinkCentre/workingLAN/host не LAN proof. Fullwave3/DAE gates прежние.
Privacy review всего Markdown: ... . Reportfile/commit/push или точный безопасный сбой: ... .
Конечный режим/связь/owner actions: ... .
