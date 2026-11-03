# Разбор wave3w: REC-A принят как синтетическая модель

[Фактический отчёт](https://github.com/1521572-lang/xgw/blob/e670cebfb49dfe2e42e34ed0196ce289caef4dd2/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3w-2026-11-03.md),
commit **e670cebfb49dfe2e42e34ed0196ce289caef4dd2**, принят fast-forward.
Прогон 03.11.2026,09:28:33–09:35 MSK. Tested HEAD
**d2c24f99eeed6e9181ed73aad610043099edd537**, tree
**1f9cf738407b2a4dee561845a15fe0327b957161**.
Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime diff пуст.
SHA модели **02f71d306a99ebb8929c31b163c3739309da5cf4f24f02537a18729207270ffe**,
owner freeze0600, Python-I-B/simulate без оптимизации, command rc0.

## Принято

ON_RECOVERY_MODEL_RECORDED, shape_valid/all_cases_passed=true,
**25/25** строк fixed case ID имеют passed=true. Не было timeout/ошибки readout.
Проверены отказ неподтверждённых gates/defaults, scope и бюджета, запрет позднего fault,
старое поколение/unarmed driver, virtual controller loss и раннее завершение job,
corrupt snapshot, отказ транзакции/verification, restore/verify/hard deadlines, обратные часы.

runtime_recovery_implemented=**false**, active_faults_authorized=**false**,
network_requests/live_operations=0/0. Никакого реального восстановления/армирования,
timer/guardian, изменения служб/правил, установки или fault не было.
NNP канала0/sudo0, действий владельца не понадобилось. Status bookends: HEALTHY/on,
pool и версии прежние, связь живая. Подробные V context flags и110-module tree заново
не собирались и не принимаются как новые W measurements.

Фраза отчёта «9 REJECT_*» относится к defaults+восьми предусловиям; всего строк с таким
префиксом13, включая scope/budget/NaN/string bool. Таблица25 сценариев и итог25/25
согласованы; это терминологическое уточнение, не провал теста.

## Пределы результата

Tick(virtual clock) вызван той же программой: VIRTUAL_CONTROLLER_LOSS_REACHES_ON
доказывает переходы модели, не независимость реального процесса. Бюджет45с не измерен
на живом восстановлении. RESTORED_ON в сценарии не является сетевым verdict шлюза.
Реальный driver, writer fence и snapshot REC-B–D пока не приняты. Полная wave3 открыта.

Исходный код модели не меняется; повтор25 сценариев для следующего пакета не нужен.
U/V diagnostic branch завершена: не запускать ещё один journal/cache/R probe ради PASS.
Missing_identity и writer остаются недоказанными вопросами, не установленным runtime bug.

## Следующий единый пакет REC-B

Новый tests/stand/wave3_on_snapshot.py — отдельный stdlib-сборщик, не импортирует XGW
или старую страховку. Он собирает приватные bytes текущих config/capture/panel,
SB/Xray, scoped kernel nft/RPDB, boot/process и создаёт typed JSON-план только для
**IPv4 capture table ip xgw**. Guard и прочие таблицы не входят в операции плана.

Единственное обращение с проектом транзакции — **nft -c -j -f -**, без применения.
[Официальная документация](https://netfilter.org/projects/nftables/manpage.html)
определяет --check как проверку команд без применения изменений. Нельзя удалять -c
или запускать сохранённый проект вручную. Проверка относится к текущему случаю
существующей таблицы; случай её отсутствия и реальный replay НЕ проверены.

[ТЗ X](TEST-PLAN-REAL-MACHINE-0.2.0-wave3x.md) объединяет четыре автоматических этапа:
26 отрицательных/граничных fixtures, приватный snapshot/typed draft, один bounded
kernel check, after/stability и один итоговый Markdown. Старые25W/graph/cache/scan
не повторяются. Root material только /run/xgw-w3x0700/0600, никакого cat/private Git.

ON_SNAPSHOT_PLAN_RECORDED/PLANNED_NOT_ARMED означают завершение именно этой qualification.
writer_fence_verified/runtime_recovery_implemented/active_faults_authorized остаются
false. Стабильность в двух чтениях не устраняет промежуточную гонку писателей.
Snapshot не вооружён, не доказывает packet/LAN path и не разрешает fault/D1-on.

Список проверяемых писателей и оставшихся задач REC-C находится в
[инвентаризации](REC-C-WRITER-INVENTORY.md). Продуктовый fence этим PR не установлен.
Новый код ограничен test/stand-инструментарием. WAN/LAN/Tailscale/pin/pool/службы/правила
не меняются. Локально: пять узких mocked checks child containment/finalization и Ruff
прошли.26 реальных fixture cases и collector на шлюзе **NOT_RUN** до отчёта X.
18 командных блоков ТЗ прошли bash-n, семь встроенных Python-блоков — AST parsing;
runtime и все прежние stand helpers неизменны. Полных VM suites не запускалось.

Ожидается `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3x-ДАТА.md`.
У Flash только ThinkCentre; LAN считается работающей. LAN UDP/IPv6/DNS/E4, D1-on,
scoped faults, performance/all Tailscale/full wave3 открыты; wave4/DAE не начинать.
