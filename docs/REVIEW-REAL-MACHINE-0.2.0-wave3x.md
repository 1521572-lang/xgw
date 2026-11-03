# Разбор wave3x: ошибочное ожидание приоритета в тестовом сборщике

[Отчёт X](https://github.com/1521572-lang/xgw/blob/283bb12942e0bb3dbe946721e24193619644c30f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3x-2026-11-03.md),
commit **283bb12942e0bb3dbe946721e24193619644c30f**, принят fast-forward.
Прогон03.11.2026,11:24:12–11:31 MSK; сбор1.842с. Tested HEAD
**b1b7bc35a3360ba3a67b1245bbdd23f0a3551165**, tree
**5dcc72dd724fa932e1662720e2fdd558de1789b5**; runtime diff относительно product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 пуст.
Collector SHA **efa8524fe962f6b9207e1ea1659f5c269c0dc6455bea92a0b02aba3bc824c664**,
root freeze0700/0600. Installed runtime/110-module tree заново не проверялись.

## Фактический результат

Start rc0/ON_SNAPSHOT_STARTED, monitor BATCH_FINISHED, show rc0/final summary.json,
**ON_SNAPSHOT_PARTIAL**. Это завершённый сбор с неполной qualification, не PASS REC-B.

| Этап | Принимаемый факт |
|---|---|
| X1 |26/26 конкретных synthetic validation cases прошли; guard priority в них не проверялся |
| X2 |UNAVAILABLE/Refuse/GUARD_LAYOUT; до полного before snapshot не дошло |
| X3 |UNAVAILABLE/NO_COMPLETE_SNAPSHOT; nft check не начинался, его rc NOT_RUN, не отказ nft |
| X4 |UNAVAILABLE/NO_BEFORE_SNAPSHOT; after/stability не измерены |

Manifest не создан, qualification_reason=INCOMPLETE_COLLECTION. Fence/driver/active gates
false. Новый partial нельзя использовать как armed snapshot. NNP канала0/sudo0;
owner actions0. HEALTHY/on, pool, версии и связь сохранены **в статусных bookends**.
Новых доказательств неизменности шести PID, RPDB, kernel/config material внутри X нет.
Сетевых запросов0; продукт и живые правила не менялись.

## Установленная ошибка тестового контракта

[guard_gate X](https://github.com/1521572-lang/xgw/blob/b1b7bc35a3360ba3a67b1245bbdd23f0a3551165/tests/stand/wave3_on_snapshot.py#L308-L324)
требовал `forward.prio == 5`. Но неизменённый
[product render_guard](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/nft.py#L1115-L1120)
задаёт обеим base chains priority **10**: output hook=postrouting, forward hook=forward.
Число **5** в прежних отчётах — количество **host_drop_rules**, не приоритет forward.

[Исторический observer](https://github.com/1521572-lang/xgw/blob/b1b7bc35a3360ba3a67b1245bbdd23f0a3551165/tests/stand/wave3_on_observer.py#L69-L103)
выводит host_priority и forward_hook, но не forward_priority. Поэтому прежние фразы
«postrouting10/forward/drop5/reject0» не доказывали priority5 у forward. Уточнение относится
к интерпретации отчётов и неверному тесту; переносить его в живые правила запрещено.

Новая узкая регрессия извлекает chain metadata **из AST реального render_guard**, строит
source-shaped fixture и воспроизводит: исторический X отвергает её, исправленный Y
принимает. Priority5 в Y специально отвергается; это не ослабление проверки до «5 или10».
Ошибка ожидания теста установлена по исходникам. Какой именно predicate не прошёл в
реальном X, тогда не было записано: фактический живой forward priority подтвердит Y.
По одному GUARD_LAYOUT нельзя приписать все остальные поля успешными.

## Исправление и полный следующий пакет

Исторические Xhelper/SHA/run/отчёт сохраняются. Новый standalone файл
tests/stand/wave3_on_snapshot_v2.py использует /run/xgw-w3y и отдельные markers.
Изменения ограничены guard-контрактом10/10, безопасной диагностикой, шестью новыми
guard fixtures и namespace результата. Read/query/transaction/snapshot primitives
сохранены без изменения; product/runtime не меняется.

В успешном Y2 и при guard-ошибке выводятся только восемь безопасных наблюдений:
две chain_present, четыре hook/priority_expected bool, host_drop_rules/host_reject_rules.
Ни фактическое неожиданное значение priority, ни raw rules/имена/адреса не выводятся.
Ошибки layout и verdict различаются; readout не требует ручного nft/cat/скриншота.

[ТЗ Y](TEST-PLAN-REAL-MACHINE-0.2.0-wave3y.md) объединяет:

1. Шесть новых guard contract cases. Принятые X26/W25 не повторяются.
2. Полный новый кандидат snapshot и наблюдаемые признаки guard.
3. Один `nft -c -j -f -`, только после полного snapshot, без применения.
4. After/stability/private manifest qualification и один итоговый Markdown.

При optional failure продолжаются все разрешённые независимые фазы. Общие STOP
baseline/identity/privacy сохраняются; зависимые данные не подменять PASS. Рабочие
HEALTHY/on/WAN/LAN/Tailscale/pin/pool/службы/правила не менять.

Локально прошли четыре узких regression/mocked checks и Ruff. Они проверяют source
contract, безопасные детали отказа, partial с зависимыми NOT_RUN и отдельный v2 worker
без повторного старта.26 старых checks/VM/network suites не запускались.
Реальные Y6 fixtures/collector/nft check **NOT_RUN**; ожидается один
`docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3y-ДАТА.md`.

REC-B пока не закрыт. REC-C остаётся следующим этапом после qualification текущего дефекта.
Driver/fence/live recovery не реализованы,45с/absent-table replay/автономность не проверены.
Доступен только ThinkCentre; LAN считается работающей, host не LAN-client proof.
Full wave3/D1-on/faults/LAN UDP/IPv6/DNS/E4/performance/all Tailscale открыты, неwave4/DAE.
