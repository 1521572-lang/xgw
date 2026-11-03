# Разбор wave3ag: HOLD — итог заявлен, таблица противоречит закреплённому сборщику

[Полученный отчёт](https://github.com/1521572-lang/xgw/blob/62ae684af177b60e8e52683251caacab771c5760/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-2026-11-03.md#L1)
принят в Git fast-forward, commit62ae684af177b60e8e52683251caacab771c5760.
**AG129 пока не принят как доказанный результат.** Оригинальный отчёт сохраняется.
Заявлены tested8045d3a34020e201e0d8c744236bd0e65896264b,
treefa4165a6aeabf3ae0a14995ca496109bbf9aba41,source6A10M/116/3changed113same,
129/129/129/0,POOL_FLOW_BATCH_RECORDED/shape/allcasestrue,batch21933мс,
audit0/network0/liveops0/7flagsfalse,collector_exit_rcNOT_COLLECTED.
Эти заявления не заменяют прямого чтения сохранённого JSON.

## Конкретные противоречия

[S_UNAVAILABLE_EMPTY](https://github.com/1521572-lang/xgw/blob/62ae684af177b60e8e52683251caacab771c5760/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-2026-11-03.md#L68)
указан TRUE=TRUE, но [store_operation](https://github.com/1521572-lang/xgw/blob/8045d3a34020e201e0d8c744236bd0e65896264b/tests/stand/wave3_pool_flow.py#L287)
задаёт FALSE для UNAVAILABLE, LIST для prune/retire, NONE для save_candidates.
[P_CHECK_TUNNEL](https://github.com/1521572-lang/xgw/blob/62ae684af177b60e8e52683251caacab771c5760/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3ag-2026-11-03.md#L133)
указан OUTCOME, но [pool_operation](https://github.com/1521572-lang/xgw/blob/8045d3a34020e201e0d8c744236bd0e65896264b/tests/stand/wave3_pool_flow.py#L327)
возвращает ONE для check_some и ZERO для cancel; OUTCOME относится к _check_proxy.
Refresh возвращает LIST, refresh_backend EMPTY_TEXT. Противоречия expected_return
найдены в54поимённых строках, включаяFENCEDexpectedfields, не только в двух примерах.

88строк используют приблизительные времена «~N» вместо exactelapsed_ms. Объяснение
«pattern одинаков» не подтверждает точность индивидуальных полей. В ряде строк sc0
также не согласуется с вызываемыми заглушками. Нельзя исправить эти поля sourceожиданием:
нужно прочитать actual summary, сохранив его bool/null/counts/exacttime.

Правильный закреплённый worker не может одновременно вернуть passed=true и указанные
в таблице неправильные expected/observed enums: он проверяет equality до casePASS и
публикует expected_return из фиксированного scenario. Возможна ошибка ручного переноса;
возможны другие расхождения. Причина пока не установлена. Нет основания обвинять
исполнителя, объявлять реальные тесты неисполненными или признавать129PASS по одному
marker. Публичная таблица и exact saved data должны быть сверены независимо.

## Что известно о работающем шлюзе

Отчёт сообщает HEALTHY/on/poolвыключенEUстрого/XR26.10.31/SB1.14.4/связь вbookends,
NNP0/sudo0/owneractions0. МеткаHEALTHY19:28 отличается от AF15:31. Заявленная причина
или точное «между прогонами» не доказаны;19:28 попадает в заявленный интервал AF19:17–19:30.
Не выводить из этого рестарт/ТСПУ/причину и не начинать сетевую диагностику. WorkingLAN/on
сохраняется базой, новых kernel/PID/RPDB/installed116/rootDAC/realboot доказательств нет.

## Один следующий пакет: readback без новых тестов

[ТЗ AH](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ah.md) и
[ADR AH](ADR-REC-EVIDENCE-READBACK.md) читают существующие AG129/AF145/AE112 notes:
до386existingrows,НЕ386новыхcases. Нет start/_batch/newworker/fixtures/retry/kill/repair,
нет Source imports, сети, служб, Yroot/casefiles/registry/config/log reads.
Всеsrc/units/config/прежние stand artifacts байт-в-байт8045d3a. Следующая productwave
не начинается при незакрытом AG evidence defect.

Новый boundedreadonly collector проверяет exact frozenSHA/inventory/owner/mode/NOFOLLOW,
читает summary или checkpoint, извлекает whitelistfields и сравнивает их отдельно с
sourcecontract/publicreportedfields. Таблицы генерируются автоматически и защищены от
случайного редактирования prefixпроверкой. Mutableownerfiles не криптографически
аутентифицированы; readback улучшает целостность передачи, не доказывает происхождение.
AF/AE независимы: отсутствие одного архива не требует повторного batch и не блокирует
сбор других. Missingactual остаётсяUNKNOWN/null, не0/ожидаемое значение.

Локально9 узких synthetic parser/privacy/render tests/RuffPASS; roundtrip regression
обнаружила и закрыла зависимость Markdown от dictionaryorder. Реальный AHreadback NOT_RUN.
InstalledXGW/сеть/службы не менялись. LiveC BLOCKED_BOOTSTRAP; все прежние fullwave3/
independentoriginalon/code/unitrescue/LAN/performance/DAE gates сохраняются.
Ожидается один TEST-REPORT-REAL-MACHINE-0.2.0-wave3ah-ДАТА.md с автоматически перенесёнными
данными. Если реальных файлов нет, это недоступность evidence, не разрешение rerun.
