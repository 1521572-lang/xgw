# Разбор wave3y: REC-B принят в границе snapshot/check-only

[Отчёт Y](https://github.com/1521572-lang/xgw/blob/1440d51558636a6059c4b7f211abc4561908aee7/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3y-2026-11-03.md),
commit **1440d51558636a6059c4b7f211abc4561908aee7**, принят fast-forward.
Прогон03.11.2026,12:02:33–12:09 MSK; сбор5.705с. Tested HEAD
**5fbc76e944d056f8a75ee4430d2f749c041d0705**, tree
**c578dbf1c14a52125221f16f36f770612b2f6cf2**; product pin351fb54e074f4a7b497a8a4244fc74c6088788d7,
runtime diff пуст. Collector SHA
**7c4375f3b918c609358454d51234b8571014d36e58066bb31ed29d5f2e5fcb4a**,
root freeze0700/0600, старый X/run не менялся. Installed tree повтор NOT_RUN.

## Принятые факты

Start rc0/ON_SNAPSHOT_V2_STARTED; monitor BATCH_FINISHED; show rc0/final summary.json;
**ON_SNAPSHOT_V2_PLAN_RECORDED**, plan_status=**PLANNED_NOT_ARMED**,
private_manifest_written=true; network_requests0. NNP канала0/sudo0, owner actions0.

| Этап | Факт и принимаемый scope |
|---|---|
| Y1 |6/6 новых synthetic guard cases; X26/W25 не исполнялись |
| Y2 |8 private files; capture_objects64/guard_objects34/routes3/rules9/activeunits6; обе цепочки/hook/priority_expected true; host_drop_rules5/host_reject_rules0 |
| Y3 |Один nft -c -j -f -: rc0/changes_applied=false в текущем контексте существующей таблицы |
| Y4 |Прочитанные config inputs и optional absence, capture/guard/rules/routes/units/boot/markers совпали в двух чтениях; manifest перечитан с digest-проверкой |

В Y живой guard подтвердил строгие source expectations: host postrouting priority10 и
forward priority10. Ошибка тестового X с ожиданием5 устранена без изменения продукта или
живых правил. Исторический live priority X не был записан и не подменяется новым Y.

В таблице отчёта «capture/guard/rules/routes/units/boot/markers ×8» перечислены семь
структурных flags. Дополнительно есть inputs_unchanged и optional_absence_unchanged.
Принимаются поимённые true/общийall_observed_inputs_stable, не ошибочный множитель.

Рабочие HEALTHY/on, pool, версии и связь сохранены в status bookends. Snapshot/RPDB/
process/config observations относятся к двум конечным чтениям collector, не непрерывной
пакетной трассе. Нормализация handles/counters не является доказательством отсутствия
промежуточной замены и возврата поколения.

## Что закрыто и что остаётся открытым

REC-B snapshot/check-only qualification принимается в описанном scope. Guard test defect
закрыт. Реальный replay, случай отсутствующей таблицы,45с восстановления, LAN/packet paths
и автономность не проверены. Manifest не вооружён и не передаётся live driver.
writer_fence_verified/runtime_recovery_implemented/active_faults_authorized остаются false.
Продуктовый дефект не найден; продуктовая установка по Y не требуется.

Доступен только ThinkCentre; рабочая LAN принимается как исходная схема. Fullwave3/
D1-on/scoped faults/LAN UDP/IPv6/DNS/E4/performance/all Tailscale открыты, неwave4/DAE.
Исторические M/J/L/Npartial/Pblocked/Q/Rnegative/S/T/U/V/W/X26 сохраняются по scope.

## Следующий единый этап REC-C

[ADR владения](ADR-REC-C-OWNERSHIP.md) задаёт token/epoch/generation, запрет позднего job,
поведение после expiry и правила retirement. tests/stand/wave3_writer_fence_dry.py
реализует **только sandbox candidate** для cooperating synthetic writers. Он не встроен
в XGW, не читает Y root material и не трогает живые locks/config/службы/правила.

[ТЗ Z](TEST-PLAN-REAL-MACHINE-0.2.0-wave3z.md) объединяет19 сценариев в одном обычном
пользовательском запуске: основные token/generation boundaries и три real-process cases
(два конкурирующих writer, завершение своего lock holder, lease после выхода владельца).
Виртуальные lease boundaries и реальные filesystem/process observations разделены.
Сетевых действий, timer, guardian и fault нет; реальные fence/driver gatesfalse.

Локально прошли три узких теста failure atomicity/lock budget/false verification и Ruff.
Полный19-case batch и процессы перенесены на ThinkCentre: **реальная wave3z NOT_RUN**.
16 командных блоков ТЗ прошли bash-n, девять встроенных Python-блоков — AST parsing;
прежние helpers и product/runtime сохранены, broad VM suites не запускались.
Ожидается один `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-ДАТА.md`.

Дополнен [аудит писателей](REC-C-WRITER-INVENTORY.md): FreePool backend отдельно меняет
ip xgw/fp_peers; учёт использует другую таблицу xgw_acct, а agent — другой table/namespace.
Отсутствие режима FreePool on не доказывает общего fence. Все реальные writers ещё
предстоит интегрировать; sandbox PASS не является принятой REC-C product integration.
