# Отчёт: XGW wave3ab — dormant registry foundation в sandbox

Дата/время MSK: 2026-11-03, 13:58:58–14:05+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 353a53b9111f1db1755307c16fb54ed686854d9a /
tree bb716d1e174e887d8088c9f5df55855310a3d4fe (S2.1, предок e64a39b… — отчёт aa;
SOURCE_PREFLIGHT_OK). Product pin 351fb54e074f4a7b497a8a4244fc74c6088788d7.
Source diff ровно A src/xgw/ownership.py: проверено программно в S2.1
(SOURCE_DIFF_SINGLE_DORMANT_ADDITION; иначе STOP) — против pin единственное добавление
нового module, прежние src/packaging/config/CLI/stand helpers неизменны. Старый runtime
unchanged; installed runtime unchanged: **installed_runtime_changed=false** — работающий
XGW новый module НЕ импортирует и НЕ активирует (нет import-time I/O/автоактивации;
установки/pip/xgw install/restart/reload не было). RegistrySHA
2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5; batchSHA
5e3f588aa5aee099af4272b8941511c6d866af40b824efd16f31eb2d8e554c64; owner freeze
0700/0600: REGISTRY_FROZEN 2 + S2.4b REGISTRY_READY rc0 (~/xgw-w3ab 0700, batch.py и
registry.py 0600 nlink=1; CLI только `batch` обычным пользователем python3 -I -B;
internal_peer вручную не вызывался; root-запуск helper отвергает контрактом;
expected_uid=os.getuid() — fixture policy теста, изменения uid/chown не выполнялись,
runtime DAC настоящего /run/xgw и default UID0 — NOT_RUN).
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. Before/after: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (не переключался);
pool «выключен; регион EU (строго)» — без изменений; Xray 26.10.31 / sing-box 1.14.4;
связь живая в обоих концах. Installed 110-module tree повтор, AA22, Z19, старые batches —
NOT_RUN (batch импортирует только private копию ownership.py; AA22/Z19/X26/W25 не
повторялись). Y root material не использовался (snapshot PLANNED_NOT_ARMED, не читался).

| Этап | rc/marker/file | Фактические данные | limits |
|---|---|---|---|
| S1/S2 owner/identity/baseline/freeze | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 13:58:58; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_SINGLE_DORMANT_ADDITION + SOURCE_PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; REGISTRY_FROZEN 2; REGISTRY_READY | Не install/activation; Git fetch/FF — не установка; статус grep-строками |
| S3 controller/helper | rc 0 / **REGISTRY_FOUNDATION_RECORDED** / controller-result.json (0600, EXCL) | command_rc=0; shape_valid=true; passed=**32/32**; real_process_cases=3/passed=**3**; children_started=**4**; virtual_boot_and_clock=true; installed_runtime_changed/runtime_writer_fence_installed/runtime_recovery_implemented/active_faults_authorized = **false**; network_requests=0; live_gateway_operations=0; scope=DORMANT_PRODUCT_REGISTRY_USER_SANDBOX | Только user-sandbox: synthetic state/lock/stage + реальные fsync/rename/flock/children только в тестовом каталоге; kernel/systemd/сеть не вызывались; bootids/lease clock виртуальные |
| S4 final status/pool | rc0 ×2 | HEALTHY с 02.11 19:56/включён; «выключен; регион EU (строго)» — без изменений; связь живая | Bookends, не Y-kernel/RPDB/PID/config after; не непрерывное наблюдение |

## Все 32 cases

По фактическому helper readout (controller-result.json); reason/error_class не
потребовались (fail-случаев нет); порядок совпал с таблицей ТЗ S4.3:

| Case ID | Actual passed/reason/errorclass/details |
|---|---|
| UNIFIED_RECORD_COMPLETION | true |
| SAME_BOOT_REOPEN_RETAINS_WRITER | true |
| OLD_BOOT_REFUSES_READ_AND_ADMISSION | true |
| FOREIGN_REGISTRY_TOKEN_REFUSED | true |
| DUPLICATE_COMPLETION_CANNOT_PUBLISH_TWICE | true |
| UNKNOWN_REQUIRES_FUTURE_REPAIR | true |
| FALSE_COMPLETION_REFUSED | true |
| STRING_COMPLETION_REFUSED | true |
| OUTCOME_RECEIPTS_ALL_INVALIDATE_OLD_GENERATION | true |
| NO_PENDING_BARRIER_BEFORE_DRAIN | true |
| ARMED_BLOCKS_WRITER | true |
| EXPIRED_LEASE_NEVER_UNFENCES | true |
| DISPATCHED_JOB_CANNOT_BE_UNUSED_OR_DISPATCHED_TWICE | true |
| UNUSED_RETIRE_INVALIDATES_OLD_EPOCH | true |
| SYNTHETIC_RESTORED_RECEIPT_ADVANCES_GENERATION | true |
| BOOLEAN_EXPECTED_GENERATION_REFUSED | true |
| BOOLEAN_CLOCK_REFUSED | true |
| BACKWARD_CLOCK_REFUSED | true |
| STATE_PERMISSIONS_REFUSED | true |
| STATE_SYMLINK_REFUSED | true |
| REPLACED_STABLE_LOCK_REFUSED | true |
| DUPLICATE_JSON_KEYS_REFUSED | true |
| OVERSIZED_RECORD_REFUSED | true |
| INTERRUPTED_STAGE_BLOCKS_WITHOUT_AUTOREPAIR | true |
| PRE_REPLACE_FAILURE_PRESERVES_OLD_RECORD_AND_STAGE | true |
| POST_REPLACE_ACK_ERROR_HAS_COHERENT_RECEIPT | true |
| RECEIPT_HISTORY_IS_BOUNDED | true |
| WRITER_CAP_NEVER_EVICTS_LIVE_TICKET | true |
| REAL_PROCESSES_HAVE_DISTINCT_DURABLE_TICKETS | true; details: child_rc=[0,0], fixed_output_matched=true |
| REAL_CHILD_HOOK_FINISHES_WITH_PARENT_TICKET | true; details: child_rc=0, fixed_output_matched=true |
| REAL_OWNER_EXIT_DOES_NOT_PRUNE_DURABLE_TICKET | true; details: child_rc=0, fixed_output_matched=true |
| OWNER_POLICY_MISMATCH_REFUSED | true |

Command rc 0; helper marker **REGISTRY_FOUNDATION_RECORDED**; итог final
(controller-result.json, filetype final), registry-result/registry-progress checkpoint не
потребовались; UNKNOWN/NOT_RUN среди cases нет. Passed/total: **32/32**. Real process
cases 3/3: конкурентный admit 2 child → два различных durable tickets (child_rc=[0,0]);
nested hook 1 child (rc 0); owner exit 1 child (rc 0); везде fixed_output_matched=true.
children_started: **4** (2+1+1; bounded communicate 4с/own cleanup 1+1с; controller
timeout 60с не достигнут). virtual_boot_and_clock=true (boot fixtures синтетические,
не читались как реальный bootid). installed_runtime_changed=false;
runtime_writer_fence_installed=false; runtime_recovery_implemented=false;
active_faults_authorized=false — обязательные scope-флаги; если бы любой стал true —
scope неверен (не этот случай). Network_requests/live_gateway_operations: **0/0**.
Статус команды не подменялся helper PASS — command/shape/all_cases согласованы.

## Решение

Foundation candidate **принят полностью** (32/32): новая unified schema
generation/writers/receipts/lease в одном atomic record проверена в пользовательском
sandbox на реальных fsync/rename/flock с инъекциями file commit ошибок. Подтверждено:
завершение единого record; reopen в том же boot сохраняет writer; старый boot отказывает
в read/admission; чужой registry token отвергнут; duplicate completion не публикует
дважды; UNKNOWN требует будущего repair и не снимается автоматически; false/string
completion отвергнуты; outcome receipts инвалидируют старое поколение; нет PENDING
barrier до drain; ARMED блокирует writer; истёкший lease никогда не разворачивает
fence; dispatched job не может быть unused/dispatched дважды; unused retire инвалидирует
старый epoch; synthetic restored receipt двигает generation; boolean expected_generation/
boolean clock/backward clock/permissions/symlink/replaced stable lock/duplicate JSON keys/
oversized record/owner policy mismatch — всё отвергнуто; interrupted stage блокирует без
autorepair; pre-replace failure сохраняет старый record+stage; post-replace ack error даёт
coherent receipt (COMMIT_UNCERTAIN с целиком новым receipt/generation/removal — не
доказательство no-commit); receipt history ограничена; writer cap не выселяет live ticket.
Это **новая source implementation**, но installed XGW её не импортирует/не активирует.
Atomic record/receipt ≠ distributed kernel/API transaction; verifier assertion ≠ network
proof; synthetic boot/clock/owner policy ≠ root runtime attestation; pre/post rename
error cases ≠ powerloss proof; interrupted stage ≠ repair/prune; 32/32 ≠ C-ENTRY
integration/полный C-REG repair/driver/autonomy/45с recovery/fault authorization.
Root runtime DAC/bootid NOT_RUN. Y snapshot PLANNED_NOT_ARMED и не читался. Настоящие
config/locks/services/rules не менялись; сеть ради PASS не менялась.
Следующая работа (без автоматического live-перехода): C-REG2 repair protocol /
C-ENTRY dormant adapters / C-VERIFY receipts, независимый D fake и отдельный bootstrap
rescue.
Только ThinkCentre; working LAN; host-пробы не LAN-client proof. Full wave3 / D1-on /
faults / LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE
не начинались. Исторические доказательства AA22/Z19/Y6/X26/W25/U/V/M/J/L/Npartial/
Pblocked/Q/Rnegative/S/T сохранены без пересмотра (не повторялись).

Privacy review Markdown выполнен: никаких raw state/registry ids/boot/tokens/inodes/
UID/home paths/private hashes/исключений/unknown child stdout/raw status/config/logs/
URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/screenshots — только fixed
case IDs/bools/counts/enums/Git/source SHA/rc. Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ab-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3ab — dormant registry foundation в sandbox», push в freepool (REPORT_PUBLISHED в
финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56, перехват ВКЛЮЧЁН, pool
прежний; связь живая; действий владельца в прогоне не было; batch.py/registry.py/
started/result/sandbox остались в заметках вне Git.
