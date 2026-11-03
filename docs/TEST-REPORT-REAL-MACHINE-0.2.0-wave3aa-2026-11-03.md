# Отчёт: XGW wave3aa — lifetime admission в sandbox

Дата/время MSK: 2026-11-03, 13:33:06–13:39+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD c7c82eb27214b533566c567216cc2f93be5689cd /
tree 308871fbe3f91320213ff0974ac2dc1d7921e389 (S2.1, предок 2a5b1fb… — отчёт z;
SOURCE_PREFLIGHT_OK). Product pin 351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime
diff (src, packaging, tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py,
config.example.toml, pyproject.toml) пуст; новый файл — только тестовый helper
tests/stand/wave3_writer_tickets.py (+ADR-REC-C-ADMISSION-LIFETIME/
REC-C-CALLSITES-AND-BOOTSTRAP, не код продукта); продукт не устанавливался и не менялся.
AA helper SHA256 7b3a99ac9ecc6e53f317c4e73389c28deaf8aec48e14c2fd8b3808574cacedfe;
ledger SHA256 be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b
(wave3_writer_fence_dry.py НЕ изменена; скопирована как ledger.py и импортирована
только как библиотека Store/read/create; её batch/peer/main НЕ запускались, Z notes/run
не читались; новый ledger id в AA — не Z lease). Owner freeze 0700/0600:
WRITER_TICKETS_FROZEN 2 + S2.4b WRITER_TICKETS_READY rc0 (~/xgw-w3aa 0700, tickets.py и
ledger.py 0600, nlink=1; CLI только `batch` обычным пользователем python3 -I -B;
internal_peer вручную не вызывался; root-запуск helper отвергает контрактом).
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. Before/after: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (не переключался);
pool «выключен; регион EU (строго)» — без изменений; Xray 26.10.31 / sing-box 1.14.4;
связь живая в обоих концах. Installed runtime/110-module tree и старые batches — NOT_RUN
(helper не импортирует XGW; прежние V-факты сохранены). Y root material / snapshot не
читались и не использовались (PLANNED_NOT_ARMED сохраняется).

| Этап | rc/marker/file | Фактические данные | scope/limits |
|---|---|---|---|
| S1/S2 owner/identity/baseline/freeze | rc0 ×7 | OWNER_SHELL_OK; NOTES_CREATED 13:33:06; EXECUTOR_NNP_OK; sudo 0; SOURCE_PREFLIGHT_OK; baseline HEALTHY/включён/pool «выключен»; WRITER_TICKETS_FROZEN 2; WRITER_TICKETS_READY | Git fetch/FF — не установка; статус grep-строками, raw не сохранялся |
| S3 controller/helper | rc 0 / **WRITER_TICKETS_DRY_RECORDED** / controller-result.json (0600, EXCL) | command_rc=0; shape_valid=true; passed=**22/22**; real_process_cases=3/passed=**3**; children_started=**3**; virtual_lease_boundaries=true; network_requests=0; live_gateway_operations=0; scope=COOPERATIVE_ADMISSION_LIFETIME_USER_SANDBOX | Только user-sandbox: synthetic registry/тickets + реальные fsync/rename/flock/children только в тестовом каталоге; kernel/table/network/API/services не затронуты |
| S4 final status/pool | rc0 ×2 | HEALTHY с 02.11 19:56/включён; «выключен; регион EU (строго)» — без изменений; связь живая | Bookends, не Y-kernel/PID/route after; не непрерывное наблюдение |

## Все 22 cases

По фактическому helper readout (controller-result.json); reason/error_class не
потребовались (fail-случаев нет):

| Case ID | Фактический passed/reason/errorclass/details |
|---|---|
| SUCCESS_PUBLISHES_BEFORE_DRAIN | true |
| LEASE_REFUSED_INSIDE_CALLBACK | true |
| REAL_CHILD_HOOK_ADMITTED_WITH_PARENT_TICKET | true; details: child_rc=0, fixed_output_matched=true |
| REAL_CHILD_LEASE_REFUSED_DURING_CALLBACK | true; details: child_rc=0, fixed_output_matched=true |
| REAL_OWNER_EXIT_DOES_NOT_DRAIN_TICKET | true; details: child_rc=0, fixed_output_matched=true |
| ARMED_PREVENTS_CALLBACK_ENTRY | true |
| DRAIN_REQUIRED_BEFORE_ARM | true |
| FAILED_ACQUIRE_NEVER_SETS_PENDING_BARRIER | true |
| PARTIAL_CALLBACK_ERROR_RETAINS_UNKNOWN | true |
| FALSE_VERIFIER_NEVER_DRAINS | true |
| STRING_VERIFIER_NEVER_DRAINS | true |
| VERIFIER_ERROR_RETAINS_TICKET | true |
| DUPLICATE_COMPLETION_REJECTED | true |
| CROSS_ROLE_TOKEN_REJECTED | true |
| UNKNOWN_HAS_NO_AUTOMATIC_RETIREMENT | true |
| OUT_OF_ORDER_COMPLETIONS_ADVANCE_GENERATION | true |
| ROLE_AND_INFLIGHT_LIMITS_REJECTED | true |
| MALFORMED_REGISTRY_BLOCKS_ADMISSION_AND_LEASE | true |
| EXPIRED_LOGICAL_LEASE_STILL_BLOCKS_WRITERS | true |
| FAILED_GENERATION_PUBLICATION_NEVER_DRAINS | true |
| PUBLISHED_GENERATION_WITH_FAILED_CLEANUP_STAYS_BLOCKED | true |
| REOPEN_NEVER_PRUNES_ORPHAN_TICKET | true |

Command rc 0; helper marker **WRITER_TICKETS_DRY_RECORDED**; итог final
(controller-result.json), checkpoint/tickets-result/tickets-progress не потребовались
(READOUT завершился на первом файле; UNKNOWN/NOT_RUN среди cases нет). Passed/total:
**22/22**; порядок case IDs совпал с таблицей ТЗ S4.3. Real process cases 3/3:
каждый REAL_* — один собственный child (hook admission при parent ticket, lease refusal
внутри callback, owner exit без drain), все child_rc=0/fixed_output_matched=true.
children_started: **3** (собственные Python-children helper, bounded communicate 4с/
cleanup 1+1с; controller timeout 30с не достигнут). virtual_lease_boundaries=true
(время lease виртуальное). runtime_writer_fence_installed=**false**;
runtime_recovery_implemented=**false**; active_faults_authorized=**false** —
обязательные scope-флаги; если бы любой стал true — scope неверен (не этот случай).
Network_requests/live_gateway_operations: **0/0**. Статус команды не подменялся helper
PASS — command/shape/all_cases уровни согласованы.

## Решение

Test candidate scope **принят полностью** (22/22): новый test-only ticket gate —
lifetime admission поверх Z-fence контракта проверён в пользовательском sandbox на
реальных fsync/rename/flock с 3 real-process cases. Ключевые семантики подтверждены:
успешная публикация поколения до drain; lease запрещён внутри callback; admission
child-hook при parent ticket; lease refusal во время callback; owner exit НЕ снимает
durable ticket; ARMED блокирует вход в callback; drain обязателен до arm; failed
acquire НЕ ставит PENDING barrier; частичная ошибка callback сохраняет UNKNOWN; false/
string/errored verifier НЕ drain'ит; duplicate completion отвергнут; cross-role token
отвергнут; UNKNOWN без автоматического retirement; out-of-order completions двигают
generation; role/inflight limits работают; malformed registry блокирует admission и
lease; истёкший логический lease всё ещё блокирует writers; failed publication и
published generation с failed cleanup остаются заблокированными; reopen НЕ подрезает
orphan ticket. Это НЕ продуктовая интеграция: durable tickets/drain/publication/unknown
≠ product call-site integration/crash repair/автономный возврат on/45с recovery/
network proof. Callback verifier — заглушка; lifecycle hook child — не настоящий
service/TUN; порядок registry operations реальный, но calls не настоящий systemctl/TUN.
Первые два REAL_* cases показывают новый lifecycle протокол, а не повтор Z concurrent
generation case. Y snapshot остаётся PLANNED_NOT_ARMED и не использован; реальные
config/locks/services/rules не менялись; сеть ради PASS не менялась.
Дальше (без автоматического live-перехода, по ADR-REC-C-ADMISSION-LIFETIME/
REC-C-CALLSITES-AND-BOOTSTRAP): audit product registry/entrypoints/receipts, затем
fake-only независимый driver и отдельный bootstrap rescue. Код AA не устанавливать
в XGW.
Только ThinkCentre; working LAN; host-пробы не LAN-client proof. Full wave3 / D1-on /
faults / LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE
не начинались. Исторические доказательства Z19/Y6/X26/W25/U/V/M/J/L/Npartial/Pblocked/
Q/Rnegative/S/T сохранены без пересмотра (Z19/Y6/X26/W25 не повторялись).

Privacy review Markdown выполнен: никаких raw ledger/tickets/tokens/identities/inodes/
case files/raw stdout детей/URL/URI/IP/MAC/UUID/ключей/паролей/SNI/портов/реальных
tags/PID/NIC/home paths/raw status/config/logs/private hashes/screenshots/исключений —
только fixed case IDs/bools/counts/enums/source SHA/Git/rc. Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3aa-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3aa — lifetime admission в sandbox», push в freepool (REPORT_PUBLISHED в финальном
сообщении). Конечный режим: HEALTHY с 02.11 19:56, перехват ВКЛЮЧЁН, pool прежний;
связь живая; действий владельца в прогоне не было; tickets.py/ledger.py/started/result/
sandbox остались в заметках вне Git.
