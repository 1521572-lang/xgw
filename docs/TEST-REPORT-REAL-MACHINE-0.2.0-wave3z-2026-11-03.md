# Отчёт: XGW wave3z — cooperative writer fence в sandbox

Дата/время MSK: 2026-11-03, 13:03:13–13:09+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Tested HEAD 044f92bc2f40622fd2b0d9c7870ef158923e3d3d /
tree f8565216309a7727b48e673d981a4d35957d3789 (S2.1, предок 1440d51… — отчёт Y;
SOURCE_PREFLIGHT_OK). Product pin 351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime
diff (src, packaging, tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py,
config.example.toml, pyproject.toml) пуст; новый файл — только тестовый adapter
tests/stand/wave3_writer_fence_dry.py (+ADR-REC-C-OWNERSHIP/инвентарь/обзоры, не код
продукта); продукт не устанавливался и не менялся.
Helper SHA256 be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b;
FENCE_DRY_FROZEN rc 0 — ~/xgw-w3z/fence.py (владелец 0600, каталог 0700; CLI только
`batch` обычным пользователем python3 -I -B; root-запуск helper отвергает; _peer вручную
не вызывался). Installed runtime/110-module tree повтор — NOT_RUN (helper не импортирует
XGW; прежние V-факты сохранены).
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.3 EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. Baseline/финал: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (не
переключался); pool «выключен»; Xray 26.10.31 / sing-box 1.14.4; связь живая в обоих
концах. Y snapshot/root material НЕ использовался и не читался.

| Этап | rc/marker/file | Фактические данные | scope/limits |
|---|---|---|---|
| S1/S2 owner/identity/baseline/freeze | rc0 ×5 | OWNER_SHELL_OK; NOTES_CREATED 13:03:13; EXECUTOR_NNP_OK; sudo 0; SOURCE_PREFLIGHT_OK; HEALTHY с 02.11 19:56/включён; POOL_READ_OK «выключен»; FENCE_DRY_FROZEN | Git fetch/FF — не установка; статус grep-строками, raw не сохранялся |
| S3 controller/helper | rc 0 / **WRITER_FENCE_DRY_RECORDED** / controller-result.json (0600, EXCL) | command_rc=0; shape_valid=true; passed=**19/19**; real_process_cases=3/passed=3; children_started=**4**; virtual_lease_boundaries=true; network_requests=0; live_gateway_operations=0; scope=COOPERATIVE_SYNTHETIC_WRITERS_USER_SANDBOX | Только user-sandbox: синтетические records + реальные fsync/rename/flock только в тестовом каталоге; kernel/table/network/API не затронуты |
| S4 final status/pool | rc0 ×2 | HEALTHY с 02.11 19:56/включён; «выключен» — без изменений; связь живая | Bookends, не Y-kernel/PID/route after; не непрерывное наблюдение |

## Все 19 case IDs → bool

По фактическому helper readout (controller-result.json):

| Fixed case ID | passed | Группа |
|---|---|---|
| WRITER_COMMIT | true | Commit/generation |
| STALE_WRITER | true | Commit/generation |
| WRITER_BLOCKED_DURING_LEASE | true | Exclusive owner/expiry |
| SECOND_OWNER_BLOCKED | true | Exclusive owner/expiry |
| EXPIRY_NEVER_UNFENCES_WRITER_OR_STARTS_JOB | true | Exclusive owner/expiry |
| FOREIGN_TOKEN | true | Token/epoch/job |
| LATE_JOB_AFTER_RETIRE | true | Token/epoch/job |
| REACQUIRE_INVALIDATES_OLD_EPOCH | true | Token/epoch/job |
| NO_DUPLICATE_JOB_OR_UNUSED_AFTER_DISPATCH | true | Token/epoch/job |
| UNVERIFIED_RECOVERY_KEEPS_FENCE | true | Retirement |
| SYNTHETIC_VERIFIED_RETIRE_THEN_WRITER | true | Retirement |
| INVALID_DURATION | true | Invalid inputs |
| BOOLEAN_CLOCK_REJECTED | true | Invalid inputs |
| WRITABLE_STATE_REJECTED | true | Invalid inputs |
| LOCK_INODE_REPLACEMENT_REJECTED | true | Invalid inputs |
| TWO_REAL_PROCESSES_ONE_COMMIT | true | Real-process (details ниже) |
| OWN_CHILD_EXIT_RELEASES_OS_LOCK | true | Real-process |
| LEASE_PERSISTS_AFTER_OWNER_PROCESS_EXIT | true | Real-process |
| CLOCK_BEFORE_LEASE_REJECTED | true | Invalid inputs |

Passed/total: **19/19**; fail-случаев нет (reason/error_class не потребовались).
TWO_REAL_PROCESSES_ONE_COMMIT details (фиксированные counts): committed=1, stale=1,
busy=0, fenced=0, other=0, child_rc=[0,0] — ровно ожидаемый исход двух реальных
child-процессов. Filetype: controller-result.json прочитан (final); fence-result/
checkpoint не потребовались (controller сохранил итог); UNKNOWN/NOT_RUN среди cases нет.
Network_requests/live_gateway_operations: **0/0**. runtime_writer_fence_installed=
**false**; runtime_recovery_implemented=**false**; active_faults_authorized=**false** —
обязательные scope-флаги; real_process_cases=3 (все passed); virtual_lease_boundaries=
true. Статус команды не подменялся helper PASS — все уровни согласованы.

## Решение

Test candidate scope **принят полностью** (19/19): cooperative fence-контракт —
generation/epoch/owner/lease, exclusive owner и expiry-семантика (expiry НЕ разворачивает
writer и НЕ запускает job), token/epoch invalidation, no-duplicate-job, retirement
(unverified recovery держит fence; verified retire возвращает writer), invalid inputs
(duration/boolean clock/writable state/lock-inode replacement/clock-before-lease — все
отвергнуты) — проверены в пользовательском sandbox на реальных fsync/rename/flock с
3 real-process cases и 4 собственными children; собственный child exit освобождает OS
lock, логический lease переживает выход owner-процесса (разные свойства).
**Это НЕ продуктовый fence и НЕ автономный recovery**: flock advisory — все реальные
writers ещё требуют интеграции; lease time boundaries синтетические (времена 1/2/10/11
в кейсах — не реальные timestamps и не измеренные 15/45с); RESTORED_ON в test record —
simulated verification; 19/19 ≠ отсутствие всех product writers/ABBA/гарантированный
возврат рабочего on; Y snapshot остаётся PLANNED_NOT_ARMED и не использован; реальные
locks/config/службы/правила не менялись; сетевая проверка/45с NOT_RUN.
Дальше (без автоматического live-перехода, по ADR-REC-C-OWNERSHIP/REC-C-WRITER-
INVENTORY): полный product call-site/lockorder/rollback/drainage/bootstrap дизайн —
НЕ установка test Store в реальный XGW. Новое наблюдение аудита: host FreePool backend
напрямую меняет fp_peers в ip xgw — его нельзя пропустить из admission; Usage/agent
имеют другие таблицы/namespace scopes — не каждое nft слово является writer'ом
capture-таблицы.
Только ThinkCentre; working LAN; host не LAN-client proof. Full wave3 / D1-on / faults /
LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE не
начинались. Исторические доказательства Y6/X26/W25/U/V/M/J/L/Npartial/Pblocked/Q/
Rnegative/S/T сохранены без пересмотра.

Privacy review Markdown выполнен: никаких raw state/identity/tokens/inodes/путей home/
реальных секретов/screenshots/исключений (child stdout классифицирован фиксированными
counts; неизвестный текст не печатался). Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3z — cooperative writer fence в sandbox», push в freepool (REPORT_PUBLISHED в
финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56, перехват ВКЛЮЧЁН, pool
прежний; связь живая; действий владельца в прогоне не было; fence.py/started/result/
sandbox остались в заметках вне Git.
