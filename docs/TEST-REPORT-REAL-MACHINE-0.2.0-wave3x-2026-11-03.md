# Отчёт: XGW wave3x — приватный snapshot исходного on и check-only плана

MSK дата/время: 2026-11-03, 11:24:12–11:31+03 (сбор 1.842 с). Модель GLM-5.3-Flash
(ZCode), терминал владельца; Ubuntu 24.04.5 LTS. Tested HEAD
b1b7bc35a3360ba3a67b1245bbdd23f0a3551165 / tree
5dcc72dd724fa932e1662720e2fdd558de1789b5. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7. Runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только тестовый collector
tests/stand/wave3_on_snapshot.py (+REC-C-WRITER-INVENTORY.md, не код продукта); продукт
не устанавливался и не менялся.
Collector SHA256 efa8524fe962f6b9207e1ea1659f5c269c0dc6455bea92a0b02aba3bc824c664
(ON_SNAPSHOT_FROZEN rc 0; /run/xgw-w3x 0700, файл root600; CLI start/status/show, _worker
не вызывался). Installed runtime/110-module tree повтор — **NOT_RUN** (collector stdlib,
не импортирует XGW); прежние scoped доказательства V не переписаны.
NNP канала: EXECUTOR_NoNewPrivs=0 (S1.2a EXECUTOR_NNP_OK); sudo rc 0; действий владельца
не требовалось. nft v1.0.9 (Old Doc Yak #3). Baseline/финал: HEALTHY с 02.11 19:56;
перехват ВКЛЮЧЁН (не переключался); pool «выключен»; Xray 26.10.31 / sing-box 1.14.4;
связь живая в обоих концах.
Start rc 0/ON_SNAPSHOT_STARTED; monitor: BATCH_FINISHED; show rc 0, wrapper.file=
**summary.json**; финальный маркер **ON_SNAPSHOT_PARTIAL** (завершённый сбор, НЕ полная
квалификация); elapsed 1.842 с; network_requests=**0**.
plan_status: **квалификация НЕ достигнута** (без manifest; qualification_error_class=
Refuse, qualification_reason=INCOMPLETE_COLLECTION); private_manifest_written=false.

| Этап | collection | bool/count/fixed enum/role/rc | Semantic decision/limits |
|---|---|---|---|
| X1_negative_fixtures | RECORDED | **passed 26/26**; все 26 case bool=true (список ниже); scope=SYNTHETIC_VALIDATION_NOT_LIVE_FAULT | Синтетическая валидация контрактов валидатора, не живые отказы шлюза |
| X2_private_snapshot | **UNAVAILABLE** | error_class=Refuse; reason=**GUARD_LAYOUT** (фиксированный enum; raw не вскрывался) | Валидатор отказал сверке макета guard-таблицы при сборе приватного snapshot; точное расхождение ожидаемого контракта helper и живого layout из этого прогона НЕ извлекаемо (по ТЗ raw/ручные nft-команды запрещены) |
| X3_nft_check_only | **UNAVAILABLE** | error_class=Refuse; reason=NO_COMPLETE_SNAPSHOT; command_rc **UNKNOWN/NOT_RUN** (check не начинался) | Check-only не выполнялся; это НЕ неуспех nft и НЕ применённая транзакция |
| X4_after_stability | **UNAVAILABLE** | error_class=Refuse; reason=NO_BEFORE_SNAPSHOT | After-сравнение невозможно без before; before НЕ подменялся after; «не изменилось» НЕ утверждается |

Фиксированные 26 case ID→bool (X1, все true): DUPLICATE_JSON, NONFINITE_JSON,
NFT_ROOT_SCHEMA, FOREIGN_FAMILY, FOREIGN_TABLE, NFT_COMMAND_IN_LISTING,
DYNAMIC_EXPIRATION, COUNTERS_IGNORED, VERDICT_CHANGE_DETECTED,
PACKETS_OUTSIDE_COUNTER_PRESERVED, RESERVED_ROUTE_TABLE, TUN_SCOPE, STALE_STATUS,
DEFAULT_FALSE_STATUS, TRANSACTION_GENERATED_SCOPE, GLOBAL_FLUSH_REJECTED,
SYMLINK_REJECTED, WRITABLE_FILE_REJECTED, SIZE_LIMIT_REJECTED,
MANIFEST_DIGEST_REJECTED, MUTATION_COMMAND_DENIED, ONESHOT_ACTIVE_EXITED_ALLOWED,
DAEMON_ZERO_PID_REJECTED, MANIFEST_MISSING_MEMBER, MANIFEST_ACTIVE_GATE_REJECTED,
MANIFEST_INSTALL_SCOPE_REJECTED.
Недоступные этапы: X2/X3/X4 (причины выше); command_rc для X3 — UNKNOWN (не подменялся 0).
Network_requests=0. writer_fence_verified=**false**; runtime_recovery_implemented=
**false**; active_faults_authorized=**false** — неизменные флаги; PARTIAL означает: raw
файлы в run-каталоге НЕ являются armed manifest/готовым планом (manifest не создан).

## Итог и backlog

REC-B scope принят **частично**: контракты валидатора (26/26 синтетических) подтверждены;
квалификация приватного snapshot исходного on НЕ состоялась — сборщик отказал на
проверке макета guard-таблицы (Refuse/GUARD_LAYOUT), зависимые check-only и after-
стабильность корректно помечены UNAVAILABLE (не PASS). Реальный replay/driver/fence/45с
recovery — NOT_RUN и не разрешены этим прогоном; случай отсутствующей таблицы в живом
kernel не тестировался.
Конкретный дефект/недостающее evidence (без назначения причины): расхождение между
ожидаемым контрактом guard-layout в helper и фактическим живым макетом guard не
локализовано этим ТЗ (raw запрещён). Контекст серии: guard postrouting/10/forward,
drop=5/reject=0 стабильно читался во всех предыдущих wave3-прогонах и является
принятым фактом; отказ принадлежит паре «новый helper-контракт ↔ текущий layout» и
требует узкой сверки, а не сетевой правки. Минимальные будущие шаги (решение
разработчика): (1) atomic-сверка контракта GUARD_LAYOUT helper против фактически
выдаваемого kernel JSON (check-only/расширение допустимой формы либо уточнение
валидатора) — отдельное ТЗ; (2) после уточнения — НОВЫЙ прогон REC-B квалификации
(этот run эксклюзивен и не повторяется); (3) REC-C по инвентаризации:
контракт владения → полный call-site audit → test adapters → решение bootstrap →
REC-D dry qualification реального независимого driver'а. Ни один gate не считается
реализованным из W 25/25, этого snapshot или будущего nft -c 0.
Сеть/продукт на шлюзе не менялись; «ТСПУ/сервер умер» не назначается; работающая LAN
не перекрашена.
Доступен только ThinkCentre; host-пробы не client proof. Full wave3 / D1-on / scoped
faults / LAN UDP / IPv6 / DNS / E4 / performance / all Tailscale — открыты; wave4/DAE
не начинались. Принятые исторические факты W/U/V/M/J/L/Npartial/Pblocked/Q/Rnegative/
S/T сохранены без пересмотра.

Privacy review до gitadd: только этот Markdown; private snapshot/draft/manifest/input
hashes/raw config/cached status/правила/логи/идентификаторы/screenshots/исключения не
включены (причины отказов — фиксированные enum). Публикация:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3x-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3x — приватный snapshot исходного on и check-only плана», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56,
перехват ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне не было.
