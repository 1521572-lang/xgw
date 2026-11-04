# Отчёт: XGW wave3w — модель возврата исходного on

Дата/время MSK: 2026-11-03, 09:28:33–09:35+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS. Executor/среда: обычный владелец (не root), Linux,
OWNER_SHELL_OK; канал исполнителя NoNewPrivs=0 (EXECUTOR_NNP_OK, S1.3); sudo rc 0
(S1.4); действий владельца не требовалось.
Tested HEAD d2c24f99eeed6e9181ed73aad610043099edd537 / tree
1f9cf738407b2a4dee561845a15fe0327b957161 (S2.1, предок be1fc1bf… — отчёт V;
SOURCE_PREFLIGHT_OK). Product pin 351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime
diff (src, packaging, tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py,
config.example.toml, pyproject.toml) пуст; новый файл — только тестовая модель
tests/stand/wave3_on_recovery_model.py (+ADR/PR-SPEC/обзоры, не код продукта); продукт
не устанавливался и не менялся.
Модель SHA256 02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe;
MODEL_FROZEN rc 0 — копия в ~/xgw-w3w/model.py (владелец, 0600, тот же bytes; запуск
только `simulate`, python3 -I -B, без -O, как обычный пользователь). Повтор полной
проверки 110-module installed tree — NOT_RUN по ТЗ (модель не импортирует установленный
XGW; прежние принятые проверки V не переписывались).
Baseline/финал: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (не переключался); pool
«выключен»; Xray 26.10.31 / sing-box 1.14.4; связь владельца и модели живая в обоих
концах.

| Этап | rc/marker | Факты | Семантика/ограничения |
|---|---|---|---|
| S1 preflight | rc0 | OWNER_SHELL_OK; NOTES_CREATED 09:28:33; EXECUTOR_NNP_OK; sudo rc 0 | Нет обхода sudo/секретов; NNP канала ≠ NNP ядра sing-box |
| S2 identity/baseline/freeze | rc0 ×5 | SOURCE_PREFLIGHT_OK; HEALTHY с 02.11 19:56/включён; POOL_READ_OK «выключен»; MODEL_FROZEN 02f71d30… | Git fetch/FF — не установка; статус читался grep-строками, raw не сохранялся |
| S3 model/controller/readout | rc0/3.2 rc0 | command_rc=0; marker **ON_RECOVERY_MODEL_RECORDED**; passed=**25/25**; shape_valid=true; all_cases_passed=true; model-started.json/model-result.json — эксклюзивные 0600 в заметках | Только SYNTHETIC_STATE_MACHINE_ONLY; runtime_recovery_implemented=**false**; active_faults_authorized=**false**; network_requests=0; live_operations=0 |
| S4 finalstatus/pool | rc0 ×2 | HEALTHY с 02.11 19:56/включён; «выключен» — без изменений | Bookends, не непрерывное наблюдение/не route/PID proof |

## Все 25 сценариев

По фактическому model readout (model-result.json, показаниям модели):

| Fixed case ID | passed |
|---|---|
| REJECT_UNVERIFIED_DEFAULT | true |
| REJECT_BASELINE_ON | true |
| REJECT_SNAPSHOT_VERIFIED | true |
| REJECT_SAME_BOOT | true |
| REJECT_WRITER_FENCE_VERIFIED | true |
| REJECT_INDEPENDENT_DRIVER_VERIFIED | true |
| REJECT_GUARD_PRESERVED | true |
| REJECT_WAN_UNTOUCHED | true |
| REJECT_OWNED_CAPTURE_TABLE_ONLY | true |
| REJECT_INSTALL_SCOPE | true |
| REJECT_OVERBUDGET | true |
| REJECT_NAN_BUDGET | true |
| REJECT_STRING_BOOL | true |
| EXPIRED_TIMER_NEVER_STARTS_LATE_FAULT | true |
| STALE_GENERATION_REFUSES_JOB | true |
| UNARMED_DRIVER_REFUSES_JOB | true |
| VIRTUAL_CONTROLLER_LOSS_REACHES_ON | true |
| EARLY_JOB_END_STILL_RESTORES_ON | true |
| CORRUPT_SNAPSHOT_NEVER_REPLAYED | true |
| TRANSACTION_FAILURE_NOT_RESTORED_ON | true |
| VERIFY_FAILURE_NOT_RESTORED_ON | true |
| RESTORE_TIMEOUT_NOT_SUCCESS | true |
| VERIFY_TIMEOUT_NOT_SUCCESS | true |
| HARD_DEADLINE_NOT_SUCCESS | true |
| BACKWARDS_CLOCK_REJECTED | true |

Passed/total: **25/25**. Network_requests/live_operations: **0/0**.
runtime_recovery_implemented=**false** (обязательный scope-флаг; true означало бы
неверный scope, не готовность). active_faults_authorized=**false**. Ни одного
timeout/ошибки формата не было; PASS не ставился вручную — из readout.

## Решение и backlog

REC-A model: контракт восстановления исходного on проверен на 25 синтетических
сценариях одним процессом — все отказы небезопасных предусловий (9 REJECT_*), отказ
defaults/D1_INSTALL-scope, валидация бюджета (overbudget/NaN/string bool), отказ
просроченного таймера запускать late-fault, отказ устаревшего поколения и невооружённого
драйвера, достижение on при потере виртуального контроллера и раннем завершении job,
невоспроизведение corrupt snapshot, отказ восстановления при неудаче транзакции/верификации,
таймаутах restore/verify/hard deadline и перевёрнутых часах — модель ведёт себя
согласно контракту во всех 25.
**Реальный driver, writer fence и восстановление сети НЕ реализованы этим прогоном** —
это чистая модель с виртуальными часами; Tick(clock) вызван программой и не доказывает
автономность без контроллера; реальное время восстановления UNKNOWN/NOT_RUN (45с бюджет
задан в модели); RESTORED_ON в сценарии — не статус живого шлюза.
Сетевые мутации/службы/systemd-timer/guardian/установка/active faults: NOT_RUN и не
разрешены этим результатом. Подробные V context flags/110 modules/journal/cache/scan/
граф заново не собирались (обзорная ветвь завершена в V).
Следующие приоритеты по единому PR spec (без автоматического live-перехода):
**REC-B snapshot planning → REC-C writer fence**, затем REC-D/E qualification реального
автономного driver'а; live recovery ещё не реализован — до них D1-on/scoped faults
остаются невозможными без независимого возврата исходного on.
Доступен только ThinkCentre; host-пробы не выдаются за LAN-клиентские; работающая LAN
считается работающей. Full wave3 / D1-on / faults / LAN UDP / IPv6 / DNS / E4 /
performance / all Tailscale — открыты; wave4/DAE не начинались. Принятые факты
M/L/J/Npartial/Pblocked/Q/Rnegative/S/T/U/V — не переписаны; R negative остаётся
фактом своего времени.

Privacy review Markdown выполнен: только этот файл публикуется; notes/model.py/
model-started.json/model-result.json/raw secrets/screenshots/real identifiers в Git не
попадают (модель выдавала только синтетические case IDs; никаких реальных значений).
Фактическая публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3w-2026-11-03.md,
коммит «Отчёт: XGW 0.2.0, wave3w — модель возврата исходного on», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56,
перехват ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не было.
