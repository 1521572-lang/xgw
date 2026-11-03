# Разбор wave3ad: 130/130 принято в scope source hooks с подставными эффектами

[Фактический отчёт AD](https://github.com/1521572-lang/xgw/blob/ae185ddccf056c7212c829d23d49c30303587cb7/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ad-2026-11-03.md#L1)
получен fast-forward, commit ae185ddccf056c7212c829d23d49c30303587cb7.
03.11.2026,16:22:27–16:36 MSK; batch 20200 мс. Tested HEAD
9f0bbbbab15d49d4bbace45f11a6ec3aae54a6e2, tree cb1bbd23683f3b02ad01f5016ec4009d92b0791e.
Baseline pin351fb54e074f4a7b497a8a4244fc74c6088788d7, exact4A7M; SHA helper/manifest,
114 source files и freeze0700/0600 соответствуют ТЗ. Не installed114 attestation.

## Принятые факты

Start/monitor/show/shape rc0 отдельно, final summary.json,
SOURCE_HOOK_BATCH_RECORDED, FINAL_SHAPE_VALID/ALL_CASES_PASSED true.
collector_exit_rc=NOT_COLLECTED. Итого130/130/130, remaining NOT_RUN нет:
38 LEGACY,38 OWNED,38 FENCED и16 extras. Таблица содержит130 уникальных AD case IDs;
112 относится только к новому AE, не к этому отчёту.

LEGACY: ожидаемый business return/receipts0. OWNED: ожидаемый return/receipt1,
без промежуточной публикации вложенных helpers. FENCED: refusal до body effect,
fixture_unchanged=true/stub_calls0/receipts0. Все данные относятся к private frozen_ad.
Все сетевые/process/service/API действия заменены fixtures; реальные команды не исполнялись.

Все16 extras passed: отсутствие verifier, вложенные роли, taint/exception/terminal,
deferred и nested deferred, thread/foreign context, backend compensation/failed outcome/
sing-box rollback и4 readers. H_THREAD receipts2 — два самостоятельных tickets;
это не один composite. E_BACKEND_COMPENSATION:6 stub calls, receipt0;
E_SINGBOX_ROLLBACK:1 receipt. Expected negative case PASS не business completion.
Без callable verifier Coordinator отказывает ДО admission/callback, а не только
отказывается подтверждать результат. Все7 runtime gates false, workload subprocesses0,
audit_registered=true/unexpected_forbidden_io0, network/live operations0.

NNP канала0/sudo0/owner actions0. HEALTHY/on/pool «выключен, EU строго»/версии
Xray26.10.31/sing-box1.14.4/связь сохранены в bookends. Метка HEALTHY изменилась с
прошлого прогона: сам факт смены метки принят, причина **не установлена**. Указание
«внешний рестарт» в отчёте — предположение исполнителя; нет новых PID/journal/boot/
kernel данных для доказательства причины. Это не основание для сетевых диагностик
или вмешательства в работающий шлюз.

Фразу «предок04a21bd» уточняем по Git: reportAC04a21bd является предком testedAD9f0bbbb,
не наоборот. Исправление A-сводки AC в AD отражено верно:10 COMPLETED/2 REFUSED/
14 UNKNOWN/2 terminal cases, общий51casePASS не изменён. Старые отчёты не переписаны.

## Пределы принятия и следующий готовый пакет

Продуктового дефекта по AD не выявлено; AD130 не повторяется. Source hooks приняты
только с explicit injected coordinator и fake effects. Existing runtime callers
по-прежнему не передают coordinator: None legacy остаётся unfenced. Нет глобального
actor/version handshake, concrete KERNEL/API/process verifier, repair/recovery/bootstrap.
Установленный XGW не менялся. Старые AC51/AB32/.../Yroot/installed110 не запускались.

[ADR AE](ADR-REC-C-BOUND-COMPOSITE-AND-FILES.md) и
[единое ТЗ AE](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ae.md) содержат следующий весь готовый
safe объём:112 НОВЫХ cases. Два новых dormant модуля требуют полный explicit boundary
объектов, проверяют hook/registry/verifier drift, держат один ticket для составного
применения и читают exact named private files. Все прежние114 source bytes, старые
helpers/units/config сохранены. Текущий source diff6A7M, manifest116, не installed116.

Один start/автопереходы/partial data/один отчёт, без установки или сетевого отказа.
Локально11 узких regressions/Ruff проходят, полный112-case batch и thread fixture
переданы ThinkCentre, нами NOT_RUN. Внутри этих11 два helper contracts: первый SB→Xray
успешен только по fixture files; второй оставляет UNKNOWN после отказа второго шага.
Это не повтор AD130 и не работа с установленными ядрами.

LiveCinstallation BLOCKED_BOOTSTRAP. Независимый исходный on/code/unit rescue нужен
ДО реального вмешательства; исходящий on не заменять always_off. Incoming outage>1мин
не исправляется следующей командой модели. Working LAN принят baseline, host не LAN
UDP/IPv6/DNS/E4 proof. Fullwave3/D1-on/faults/performance/allTS ещё открыты; не wave4/DAE.
Ожидается один TEST-REPORT-REAL-MACHINE-0.2.0-wave3ae-ДАТА.md.
