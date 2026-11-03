# Отчёт: XGW wave3ae — bound composite и private file observer

MSK дата/интервал: 2026-11-03, 17:46:48–17:57+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 737c72037f01caa66ba0309181dbe268128edd01 /
tree 5bdb358a6ea811be14663276568f2058d0d30cb9 (S2.1, предок ae185dd… — отчёт ad;
SOURCE_PREFLIGHT_OK; включает fix-коммит пинования Git LF-хешей артефактов). Baseline
pin 351fb54e074f4a7b497a8a4244fc74c6088788d7. Source diff 6A7M (проверено программно в
S2.1/F3: SOURCE_DIFF_SIX_ADD_SEVEN_MODIFY): A = ownership.py/ownership_adapters.py/
ownership_diagnostics.py/ownership_hooks.py/ownership_binding.py/ownership_files.py;
M = те же семь модулей AD, сохранены БАЙТ-В-БАЙТ (сверены manifest'ом 116).
HelperSHA fd45da562e6a93bf9d695b79131d2548e331bda9f364618deffd5808d0f67680;
SupportSHA 9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917
(неизменённый AD helper; его старый CLI/batch НЕ вызывался, AD cases не повторялись);
ManifestSHA d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0.
116 source freeze 0700/0600: BOUND_COMPOSITE_FROZEN 116 + S2.4b BOUND_COMPOSITE_READY
rc0 (~/xgw-w3ae 0700; batch.py/support.py/manifest.json/source/** 0600, dirs 0700;
импорт только private frozen_ad package; worker ДО source imports поставил принятый AD
CPython audit guard с self-test и двумя manual events; новые registry/file tests —
синтетические boot/clock и UID владельца; observer открывал readonly directory ancestors
ради NOFOLLOW, содержимое/секреты каталогов не читал). Installed runtime unchanged: все
7 gates false; daemon/CLI/installer не используют новый bundle; None-путь по-прежнему
legacy; глобального mandatory binding нет. NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3
EXECUTOR_NNP_OK); sudo rc 0; действий владельца не требовалось. HEALTHY/on/pool/versions/
connection before/after: HEALTHY с 03.11 15:31 (та же метка, что и в AD — межпрогонной
смены не было; причина смены AC→AD не диагностировалась по ТЗ); перехват ВКЛЮЧЁН (не
переключался); pool «выключен; регион EU (строго)» — без изменений; Xray 26.10.31 /
sing-box 1.14.4; связь живая в обоих концах. Source checks ≠ аттестация installed 116;
oldAD130/AC51/AB32/AA22/Z19/Y6/X26/W25 и installed 110-tree NOT_RUN; Fake D не
исполнялся; Y root material не читался (snapshot PLANNED_NOT_ARMED).

| Этап | rc/file/marker | Actual facts | Limits |
|---|---|---|---|
| S1/S2 | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 17:46:48; EXECUTOR_NNP_OK; sudo 0; SOURCE_DIFF_SIX_ADD_SEVEN_MODIFY + SOURCE_MANIFEST_MATCHED 116 + PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; BOUND_COMPOSITE_FROZEN 116/READY | Нет установки; manifest public ≠ аттестация живых модулей |
| start | rc 0 / **BOUND_COMPOSITE_BATCH_STARTED** | Popen collector, EXCL claim/atomic progress | Не worker PASS; повторный start запрещён |
| monitor | rc 0 / **BATCH_FINISHED BOUND_COMPOSITE_BATCH_RECORDED 112 112** | Прогресс 85 (5с опрос, предел 300с) | summary найден ≠ case PASS |
| show/shape | rc 0 / wrapper.file=**summary.json** / FINAL_SHAPE_VALID True / ALL_CASES_PASSED True | Финальный итог (не checkpoint); командные rc раздельно; collector_exit_rc=**NOT_COLLECTED** | Read 0 не completion |
| S4 | rc0 ×2 | HEALTHY с 03.11 15:31/включён; «выключен; регион EU (строго)»; связь живая | Не kernel/LAN proof |

## Все 112 cases

Все passed=true; errorclass/public source:line не потребовались (fail-случаев нет,
unexpected audit denials нет). Сокращения: rc/g/uw/sc = registry_receipts/registry_
generation/unknown_writers/stub_calls; rej = rejection_observed; cv = completion_verified;
fc/fm = file_checked/file_matched; «—» = поле не применимо/неизвестно (null, не 0).

| Case ID | Actual passed/details/elapsed_ms |
|---|---|
| H_CAPTURE___SAVE | true; подмена hook отказана: rej=true, rc=0, g=0, uw=0, sc=0; 59мс |
| H_CAPTURE___LOAD | true; rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| H_CAPTURE__UP | true; rej=true, rc=0/g=0/uw=0/sc=0; 58мс |
| H_CAPTURE__ENABLE | true; rej=true, rc=0/g=0/uw=0/sc=0; 59мс |
| H_CAPTURE__DISABLE | true; rej=true, rc=0/g=0/uw=0/sc=0; 54мс |
| H_CAPTURE__OPEN | true; rej=true, rc=0/g=0/uw=0/sc=0; 51мс |
| H_CAPTURE__CLOSE | true; rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| H_CAPTURE__DOWN | true; rej=true, rc=0/g=0/uw=0/sc=0; 58мс |
| H_CAPTURE__RESTORE_TUN | true; rej=true, rc=0/g=0/uw=0/sc=0; 58мс |
| H_CAPTURE__TIDY | true; rej=true, rc=0/g=0/uw=0/sc=0; 64мс |
| H_CAPTURE__TAILSCALE_DIRECT | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| H_CAPTURE__TAILSCALE_FALLBACK | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| H_PEERS___SAVE_PEERS | true; rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| H_PEERS___NFT_ELEMENT | true; rej=true, rc=0/g=0/uw=0/sc=0; 61мс |
| H_PEERS__PREPARE | true; rej=true, rc=0/g=0/uw=0/sc=0; 53мс |
| H_PEERS__STOP | true; rej=true, rc=0/g=0/uw=0/sc=0; 58мс |
| H_PEERS__RECONCILE | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| H_XRAY__APPLY | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| H_XRAY__ROLLBACK | true; rej=true, rc=0/g=0/uw=0/sc=0; 65мс |
| H_SINGBOX__APPLY | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| H_SINGBOX__ROLLBACK | true; rej=true, rc=0/g=0/uw=0/sc=0; 58мс |
| H_SINGBOX__RESTART | true; rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| H_CORES__UPDATE | true; rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| H_CORES__ROLLBACK | true; rej=true, rc=0/g=0/uw=0/sc=0; 65мс |
| H_API__ADD_OUTBOUNDS | true; rej=true, rc=0/g=0/uw=0/sc=0; 54мс |
| H_API__REMOVE_OUTBOUND | true; rej=true, rc=0/g=0/uw=0/sc=0; 50мс |
| H_API__ADD_INBOUNDS | true; rej=true, rc=0/g=0/uw=0/sc=0; 50мс |
| H_API__REMOVE_INBOUND | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| H_API__REPLACE_ROUTING | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| H_API__PIN | true; rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| H_API__UNPIN | true; rej=true, rc=0/g=0/uw=0/sc=0; 51мс |
| H_PANEL__UPDATE | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс (включая новый 32-й hook PanelWriter.update) |
| M_CAPTURE | true; missing coordinator отказан: rej=true, rc=0/g=0/uw=0/sc=0; 63мс |
| M_PEERS | true; rej=true, rc=0/g=0/uw=0/sc=0; 53мс |
| M_XRAY | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| M_SINGBOX | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс |
| M_CORES | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| M_API | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс |
| M_PANEL | true; rej=true, rc=0/g=0/uw=0/sc=0; 76мс |
| O_CAPTURE | true; foreign coordinator отказан: rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| O_PEERS | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс |
| O_XRAY | true; rej=true, rc=0/g=0/uw=0/sc=0; 70мс |
| O_SINGBOX | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс |
| O_CORES | true; rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| O_API | true; rej=true, rc=0/g=0/uw=0/sc=0; 59мс |
| O_PANEL | true; rej=true, rc=0/g=0/uw=0/sc=0; 60мс |
| B_INCOMPLETE | true; неполный boundary отказан: rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| B_EXTRA | true; лишний объект отказан: rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| B_WRONG_TYPE | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| B_NO_VERIFIER | true; rej=true, rc=0/g=0/uw=0/sc=0; 76мс |
| B_WRONG_COORDINATOR | true; rej=true, rc=0/g=0/uw=0/sc=0; 78мс |
| B_WRONG_REGISTRY | true; rej=true, rc=0/g=0/uw=0/sc=0; 59мс |
| B_REGISTRY_DRIFT | true; drift registry отказан: rej=true, rc=0/g=0/uw=0/sc=0; 51мс |
| B_VERIFIER_DRIFT | true; rej=true, rc=0/g=0/uw=0/sc=0; 59мс |
| B_CALL_DRIFT | true; rej=true, rc=0/g=0/uw=0/sc=0; 57мс |
| B_FOREIGN_PID | true; rej=true, rc=0/g=0/uw=0/sc=0; 54мс |
| B_FOREIGN_THREAD | true; rej=true, rc=0/g=0/uw=0/sc=0; 59мс |
| B_NESTED | true; вложенное объявление отказано: rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| P_EMPTY | true; shape-отказ: rej=true, rc=0/g=0/uw=0/sc=0; 55мс |
| P_LIST | true; rej=true, rc=0/g=0/uw=0/sc=0; 52мс |
| P_TOO_MANY | true; rej=true, rc=0/g=0/uw=0/sc=0; 71мс |
| P_WRONG_STEP | true; whitelist-отказ: rej=true, rc=0/g=0/uw=0/sc=0; 64мс |
| P_UNKNOWN_WRITER | true; rej=true, rc=0/g=0/uw=0/sc=0; 65мс |
| P_UNKNOWN_METHOD | true; rej=true, rc=0/g=0/uw=0/sc=0; 69мс |
| P_ARGS_LIST | true; rej=true, rc=0/g=0/uw=0/sc=0; 66мс |
| P_KWARGS_DICT | true; rej=true, rc=0/g=0/uw=0/sc=0; 64мс |
| P_DUP_KEY | true; rej=true, rc=0/g=0/uw=0/sc=0; 65мс |
| P_OWNER_KEY | true; rej=true, rc=0/g=0/uw=0/sc=0; 56мс |
| P_USED | true; первый запуск реальный NOOP в panel fixture (rc=1/g=1), второй one-use запуск отказан (rej=true); 161мс |
| P_FENCED | true; fenced admission: ни одного body/lockfile, rc=0/g=0; 149мс |
| P_NO_CHECKER | true; отсутствие checker отказано: rej=true, rc=0/g=0/uw=0/sc=0; 61мс |
| C_SB_XRAY | true; ПОЛОЖИТЕЛЬНЫЙ composite: cv=true, rc=1/g=1, uw=0, sc=3, fc=2, fm=true; 289мс |
| C_SB_XRAY_API | true; ПОЛОЖИТЕЛЬНЫЙ composite: cv=true, rc=1/g=1, sc=4, fc=2, fm=true; 258мс |
| C_PANEL_PEERS | true; ПОЛОЖИТЕЛЬНЫЙ composite: cv=true, rc=1/g=1, sc=0, fc=1, fm=true; 202мс |
| C_FAILED_RESULT | true; expected negative: отказ верификации, rc=0/g=0, uw=1; 131мс |
| C_VERIFIER_EXCEPTION | true; expected negative: verifier exception, rc=0/g=0, uw=1, sc=3, fc=2, fm=true (файлы наблюдены — receipt НЕ выдан); 229мс |
| C_FALSE_VERIFIER | true; expected negative: false verifier, rc=0/g=0, uw=1, sc=3, fc=2, fm=true; 228мс |
| C_STEP_EXCEPTION | true; expected negative: шаг exception, rc=0/g=0, uw=1; 152мс |
| C_AFTER_UNBIND | true; expected negative: drift после шага останавливает: rc=0/g=0, uw=1, sc=1; 204мс |
| C_AFTER_HOOK_DRIFT | true; expected negative: rc=0/g=0, uw=1, sc=1; 234мс |
| C_AFTER_VERIFIER_DRIFT | true; expected negative: rc=0/g=0, uw=1, sc=1; 277мс |
| C_AFTER_REGISTRY_DRIFT | true; expected negative: rc=0/g=0, uw=1, sc=1; 222мс |
| C_NO_EARLY_LEASE | true; ПОЛОЖИТЕЛЬНЫЙ composite без раннего lease: ранний lease-запрос отказан (rej=true), итог cv=true, rc=1/g=1, sc=3, fc=2, fm=true; 310мс |
| C_CHECKER_FALSE | true; expected negative: rc=0/g=0, uw=1, sc=1; 252мс |
| C_CHECKER_EXCEPTION | true; expected negative: rc=0/g=0, uw=1, sc=1; 254мс |
| C_FILE_MISMATCH | true; expected negative: receipt заблокирован реальным сравнением bytes (fc=0, fm=false), rc=0/g=0, uw=1; 223мс |
| C_SECOND_REJECT | true; expected negative: partial effect первого sing-box шага, второй шаг отклонён — НЕ rollback, остановка до Xray write, rc=0/g=0, uw=1, sc=1; 197мс |
| C_SECOND_TERMINAL | true; expected negative: терминальный второй шаг, rc=0/g=0, uw=1, sc=1; 185мс |
| F_PRESENT | true; ПОЛОЖИТЕЛЬНАЯ file observation: fc=1, fm=true; 62мс |
| F_ABSENT | true; ПОЛОЖИТЕЛЬНАЯ exact-absence observation: fc=1, fm=true; 86мс |
| F_TWO | true; ПОЛОЖИТЕЛЬНАЯ observation двух файлов: fc=2, fm=true; 54мс |
| F_DIGEST_MISMATCH | true; expected read-refusal: fc=0, fm=false; 53мс |
| F_MODE | true; expected read-refusal (mode drift): fc=0, fm=false; 60мс |
| F_OWNER | true; expected read-refusal: owner-policy mismatch на root (не root privilege test): fc=0, fm=false; 67мс |
| F_HARDLINK | true; expected read-refusal: fc=0, fm=false; 93мс |
| F_SYMLINK | true; expected read-refusal: fc=0, fm=false; 56мс |
| F_PARENT_SYMLINK | true; expected read-refusal: fc=0, fm=false; 94мс |
| F_ROOT_SYMLINK | true; expected read-refusal (root ancestor): fc=0, fm=false; 65мс |
| F_FIFO | true; expected read-refusal: fc=0, fm=false; 68мс |
| F_OVERSIZE | true; expected read-refusal (>2MiB): fc=0, fm=false; 91мс |
| F_MISSING | true; expected read-refusal: fc=0, fm=false; 70мс |
| F_ABSENT_PRESENT | true; expected read-refusal (absence нарушена): fc=0, fm=false; 70мс |
| F_ABSENT_SYMLINK | true; expected read-refusal: fc=0, fm=false; 64мс |
| F_ABSENT_MISSING_PARENT | true; expected read-refusal: fc=0, fm=false; 65мс |
| F_DIRECTORY_MODE | true; expected read-refusal (drift каталога): fc=0, fm=false; 69мс |
| F_ROOT_MODE | true; expected read-refusal (mode root-каталога): fc=0, fm=false; 67мс |
| F_DUPLICATE | true; expected constructor refusal: rej=true; 67мс |
| F_TRAVERSAL | true; expected constructor refusal: rej=true; 59мс |
| F_BAD_DIGEST | true; expected constructor refusal: rej=true; 87мс |
| F_BOOL_OWNER | true; expected constructor refusal: rej=true; 62мс |
| F_BOOL_MODE | true; expected constructor refusal: rej=true; 66мс |
| F_EMPTY | true; expected constructor refusal: rej=true; 56мс |

Expected/completed/passed/remaining NOT_RUN: **112/112/112/0** (global_scope_stop=false).
Группы: 32 H (подмена каждого hook — блокировка всего boundary до admission) + 14 M/O
(missing/foreign coordinator) + 12 B (boundary/context: incomplete/extra/wrong type/
no verifier/wrong coordinator/registry/verifier drift/call drift/foreign pid/thread/nested)
+ 13 P (shape/whitelist/one-use/fenced admission) + 17 C (composite) + 24 F (files) = 112.
Positive composites **4** vs expected negatives **13**: четыре (C_SB_XRAY, C_SB_XRAY_API,
C_PANEL_PEERS, C_NO_EARLY_LEASE) — receipt/generation=1, роли union, один внешний
LIFECYCLE ticket, одна final verification, exact fixture file observation (fm=true);
отрицательные — receipt/generation=0 и UNKNOWN=1 при passed=true (case PASS ≠ business
completion). Нет промежуточной receipt в composites. C_SECOND_REJECT/TERMINAL
подтверждают partial effect первого шага и остановку до Xray write — **не** rollback, без
автоматического повтора/лечения (не атомарная kernel/file transaction). C_FILE_MISMATCH
блокирует receipt по реальному сравнению bytes. C_AFTER_* — drift после шага останавливает
продолжение. Positive file observations **3**/refusals **21** (6 constructor + 15 read):
exact hash/mode/uid/nlink либо exact absence; anchored openat/NOFOLLOW по root ancestors;
F_OWNER — owner-policy mismatch на root (не root privilege test); fc/fm null в
constructor-refusal ветви — null ≠ 0. Actual nullable counts приведены как в readout, не
нули из ожиданий. Audit: audit_registered=true, unexpected_forbidden_io=**0**,
workload_subprocesses=**0** (thread fixture — не процесс), global_scope_stop=false,
source_files=**116**. Batch суммарно 13030 мс. collector_exit_rc=NOT_COLLECTED.
Семь runtime gates false: installed_runtime_changed/runtime_actor_binding_implemented/
runtime_writer_fence_verified/runtime_verifier_implemented/runtime_recovery_implemented/
repair_implemented/active_faults_authorized = **false** (даже 112/112).
Network_requests/live_gateway_operations: **0/0**.

## Решение

Принят полностью только в declared source boundary + private file scope (112/112):
explicit writer binding работает как замкнутый контур — BoundWriters требует все семь
объектов с одним exact Coordinator, intактными 32 hooks (31 AD + новый PanelWriter.update)
и pinned registry/verifier; ЛЮБАЯ подмена одного hook/координатора/registry/verifier,
drift до или после шага, чужой PID/thread, вложенное объявление — fail-closed до admission
или останавливает продолжение. Composite — строго whitelisted шаги с callable accept
(только exact True пускает следующий шаг), один LIFECYCLE ticket и одна final
verification/receipt; отрицательные ветви дают ровно UNKNOWN/receipt 0 без промежуточных
публикаций. PrivateFiles — named subset observation с exact hash/mode/uid/nlink, NOFOLLOW
и bounded reads: все 24 контракта (3 положительных, 21 отказ) подтверждены; checked —
число уже подтверждённых файлов, не полная перепроверка после отказа.
Missing binding/hook drift fail-closed ВНУТРИ explicit bundle; **глобальный runtime wiring
не готов**: daemon/CLI/installer bundle не используют, None-путь legacy unfenced,
mandatory all-writer handshake/protected path policy/real KERNEL/API/process verifier —
не реализованы. Один receipt ≠ atomic side-effect transaction (partial effect первого шага
возможен и зафиксирован как UNKNOWN без rollback); private file observations ≠ KERNEL/API/
process/production verifier; UID fixture ≠ root DAC; boot/clock synthetic. Нет install/
activation/real fault/recovery/repair/bootstrap authorization — по успешному отчёту НЕТ
установки. Источник partial/STOP: нет (не было; все 112 выполнены, guard не блокировал
ничего неожиданного). Only ThinkCentre; working LAN; host не LAN-client proof.
Full wave3/D1-on/faults/LAN UDP/IPv6/DNS/E4/performance/all Tailscale — открыты; не
wave4/DAE. Исторические evidence AD130/AC51/AB32/AA22/Z19/Y6/X26/W25/U/V/M/J/L/Npartial/
Pblocked/Q/Rnegative/S/T сохранены без пересмотра (не повторялись).

Privacy review всего Markdown выполнен перед единственной публикацией: никаких raw
configs/status/logs/kernel/URI/IP/MAC/UUID/keys/passwords/SNI/ports/fp/tags/PID/NIC/UID/
home paths/registry ids/boot/tokens/private hashes/case files/raw exceptions/argv/result
texts — только фиксированные case IDs/enums/bools/counts/timings ms/rc/Git/source SHA;
116 хешей манифеста в отчёт не вставлялись; private fixture contents/hashes не публиковались.
Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ae-2026-11-03.md, коммит «Отчёт:
XGW 0.2.0, wave3ae — bound composite и private file observer», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 03.11 15:31, перехват
ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не было; 3+116 frozen
файлов/started/worker-claimed/progress/summary/cases остались в заметках вне Git.
