# Отчёт: XGW wave3y — исправленная сверка guard и snapshot on

MSK дата/время: 2026-11-03, 12:02:33–12:09+03 (сбор 5.705 с). Модель GLM-5.3-Flash
(ZCode), терминал владельца; Ubuntu 24.04.5 LTS. Tested HEAD
5fbc76e944d056f8a75ee4430d2f749c041d0705 / tree
c578dbf1c14a52125221f16f36f770612b2f6cf2. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7. Runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только исправленный тестовый collector
tests/stand/wave3_on_snapshot_v2.py (+док-коммиты, не код продукта); продукт не
устанавливался и не менялся; живые правила не исправлялись ради совпадения.
Collector SHA256 7c4375f3b918c609358454d51234b8571014d36e58066bb31ed29d5f2e5fcb4a
(ON_SNAPSHOT_V2_FROZEN rc 0; /run/xgw-w3y 0700, файл root600; CLI start/status/show,
_worker не вызывался). Исторический X-helper/run (/run/xgw-w3x) не менялся.
Installed tree повтор — NOT_RUN (collector stdlib, не импортирует XGW).
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.2a EXECUTOR_NNP_OK); sudo rc 0; действий
владельца не требовалось. nft v1.0.9 (Old Doc Yak #3). Baseline/финал: HEALTHY с
02.11 19:56; перехват ВКЛЮЧЁН (не переключался); pool «выключен»; Xray 26.10.31 /
sing-box 1.14.4; связь живая в обоих концах.
Start rc 0/ON_SNAPSHOT_V2_STARTED; monitor: BATCH_FINISHED; show rc 0,
wrapper.file=**summary.json**; финальный маркер **ON_SNAPSHOT_V2_PLAN_RECORDED**;
elapsed 5.705 с; network_requests=**0**; plan_status=**PLANNED_NOT_ARMED**;
private_manifest_written=**true** (root600, перечитан с digest-проверкой, private).

| Этап | collection | Факты/role/rc/reason | Semantic decision/limits |
|---|---|---|---|
| Y1_guard_regression_fixtures | RECORDED | 6/6: GUARD_PRODUCT_PRIORITY_TEN_ACCEPTED=true; GUARD_FORWARD_PRIORITY_FIVE_REJECTED=true; GUARD_WRONG_HOST_PRIORITY_REJECTED=true; GUARD_WRONG_FORWARD_HOOK_REJECTED=true; GUARD_HOST_REJECT_REJECTED=true; GUARD_MISSING_FORWARD_REJECTED=true; scope=SIX_NEW_GUARD_CONTRACT_CASES_ONLY | Исправленный guard-контракт подтверждён синтетикой: 10/10 принимается, старое ошибочное ожидание 5 теперь явно отвергается. Исторические X26/W25 НЕ исполнялись (26_ACCEPTED_IN_REPORT_NOT_REEXECUTED) |
| Y2_private_snapshot | RECORDED | cached_on_status_fresh=true; capture_objects=64; guard_objects=34; routes=3; rules=9; units_active=6; private_files=8; **guard_observation**: host_chain_present=true, forward_chain_present=true, host_hook_expected=true, host_priority_expected=true, forward_hook_expected=true, forward_priority_expected=true, host_drop_rules=**5**, host_reject_rules=**0** | Живой guard соответствует исправленному контракту (все priority_expected=true — числа 10; drop_rules — отдельный показатель счётчика, не приоритет). Приватный snapshot/draft собран (IPV4_CAPTURE_TABLE_ONLY, не полная replay-readiness) |
| Y3_nft_check_only | RECORDED | **nft_check_rc=0**; changes_applied=**false**; один `nft -c -j -f -` по scoped JSON stdin | Check прошёл в присутствии текущей таблицы; это НЕ применение и НЕ proof реального replay/отсутствующей таблицы |
| Y4_after_stability | RECORDED | inputs_unchanged=true; optional_absence_unchanged=true; capture/guard/rules/routes/units/boot/markers_unchanged=true ×8; **all_observed_inputs_stable=true** | Фактически прочитанные входы совпали в двух чтениях; bookends, не writer fence/непрерывное доказательство; промежуточную замену/возврат поколения не исключает |

Все 8 полей safe guard observation — из data.guard_observation Y2 (не safe_details —
отказа не было); отсутствующих значений UNKNOWN нет. Qualification: полная —
6/6 fixtures + полный snapshot + check-only rc0 + after stable → manifest записан,
plan_status=**PLANNED_NOT_ARMED**. Если бы был PARTIAL — manifest считался бы не
готовым/не armed (не этот случай). Network_requests=0.
writer_fence_verified=**false**; runtime_recovery_implemented=**false**;
active_faults_authorized=**false** — неизменные флаги, даже при manifest/rc0/check0.
Результаты команды/сборщика/after разделены; raw private material не вскрывался.

## Итог

Исправленный guard contract **подтвердился полностью**: source-level дефект X
(forward5 в тестовом контракте при product render_guard=10; число 5 в старых отчётах —
host_drop_rules count) исправлен новым Y-helper'ом; живой forward priority в X отдельно
не измерялся, теперь forward_priority_expected=true при строгом ожидании 10 без fallback.
Живые правила/продукт не менялись — совпадение достигнуто исправлением теста, не шлюза.
**REC-B qualification принята** (полная): приватный snapshot исходного on собран,
typed JSON-проект прошёл единственный check-only (rc0/changes_applied=false), все
наблюдаемые входы стабильны в двух чтениях, manifest PLANNED_NOT_ARMED перечитан с
digest-проверкой. Ограничения: это check в присутствии текущей таблицы — реальный
replay/отсутствующая таблица/packet/LAN paths/45с восстановления NOT_RUN; стабильность
в точках ≠ writer fence; материал не используется с live driver автоматически (сначала
REC-C/D и review). Конкретного дефекта шлюза не найдено; сеть ради PASS не менялась.
Далее по REC-C-WRITER-INVENTORY без автоматического live-перехода: контракт владения →
полный call-site audit → test adapters → решение bootstrap → REC-D dry qualification
реального независимого driver'а. Ни один gate не «реализован» из W 25/25, snapshot или
nft -c 0.
Only ThinkCentre; working LAN; host-пробы не LAN-client proof. Full wave3 / D1-on /
faults / LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE
не начинались; принятые исторические факты X26/W25/U/V/M/J/L/Npartial/Pblocked/Q/
Rnegative/S/T сохранены без пересмотра.

Privacy review: только этот Markdown; private snapshot/draft/manifest/input hashes/
raw rules/config/status/identifiers/screenshots/исключения не включены (все значения —
bool/counts/fixed enums). Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3y-
2026-11-03.md, коммит «Отчёт: XGW 0.2.0, wave3y — исправленная сверка guard и snapshot
on», push в freepool (REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY
с 02.11 19:56, перехват ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в
прогоне не было.
