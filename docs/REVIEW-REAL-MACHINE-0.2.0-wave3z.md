# Разбор wave3z: принят sandbox-контракт, runtime fence ещё отсутствует

Обновление: [AA22/22 принята](REVIEW-REAL-MACHINE-0.2.0-wave3aa.md); [AB](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ab.md) проверяет новый dormant sourceRegistry без установки. Старое AA NOT_RUN ниже — исторический статус.

[Отчёт Z](https://github.com/1521572-lang/xgw/blob/2a5b1fbfa722c7995a783e2b3c0744cd3757aba5/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-2026-11-03.md)
принят fast-forward, commit2a5b1fbfa722c7995a783e2b3c0744cd3757aba5.
03.11.2026,13:03:13–13:09MSK. Tested044f92bc2f40622fd2b0d9c7870ef158923e3d3d,
treef8565216309a7727b48e673d981a4d35957d3789; pin351fb54e074f4a7b497a8a4244fc74c6088788d7,
runtime diff пуст. SHA helperbe2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b.
Ownerfreeze0700/0600; обычный UID/NNP0/sudo0; owneractions0.

## Факты и границы принятия

- Controller command_rc0, shape_validtrue, WRITER_FENCE_DRY_RECORDED, finalcontroller-result.
- Все19/19casebools true; три realprocesscases passed; children_started4.
- Конкурирующие writers: committed1/stale1/busy0/fenced0/other0/childrc[0,0].
- Выход собственного lockholder освобождает OSlock; отдельный сохранённый ARMED lease
  переживает выход его владельца. Это разные свойства.
- Lease boundaries виртуальные; synthetic RESTORED_ON не проверяет сеть.
- network_requests0/live_gateway_operations0. Реальные fence/recovery/activeflagsfalse.
- HEALTHY/on, pool, версии и связь прежние в statusbookends. Новых kernel/RPDB/PID/config
  after в Z нет; не переносить Y наблюдения в Z. Installed110treeNOT_RUN.
- Yrootmaterial не читался; manifestYPLANNED_NOT_ARMED. Старые helpers неизменны.

В отчёте фраза «предок1440d51» двусмысленна: по Git Y1440d51 является предком testedZ044f92bc,
а не наоборот. Проверка источника S2.1 требует именно Y→Z. Это редакционное уточнение,
не основание повторять прогон. Общее время13:03–13:09 не объявляется временем helper:
отдельного elapsed измерения в Z нет.

Принимается cooperative synthetic writer qualification. Продуктового дефекта отчёт не
выявил. Не принимать19/19 за отсутствие всех productwriters/ABBA, реальное восстановление,
autonomy/45s/packet/LANproof. Z19/Y6/X26/W25 не повторять.

## Дальнейшая работа по исходникам

[Аудит границ записи](REC-C-CALLSITES-AND-BOOTSTRAP.md) обнаружил конкретный риск нового
lockdesign: parent удерживает ownership во время systemctlrestart, ExecStartPost вызывает
xgwnettun, которому предлагается тот же ownership. Такую глобальную критическую секцию
нельзя механически поставить вокруг Applier.apply. Это вывод о предлагаемом патче,
не утверждение, что существующий Z вызвал deadlock на шлюзе.

[ADR admission lifetime](ADR-REC-C-ADMISSION-LIFETIME.md) уточняет контракт: краткая блокировка
учёта + durable ticket на весь writer, без PENDING барьера при занятых writers. Закрытие
ticket только после публикации поколения. Неизвестный результат остаётся blocking;
продуктовый repair ещё не реализован. Тестовый AA не устанавливается в XGW.

[Единое ТЗ AA](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aa.md) содержит22 новых сценария, включая
три processcases/три child: вложенный hook, отказ lease внутри callback, выход владельца
с незакрытым ticket. Времена lease синтетические; fsync/flock/processes реальные только
в пользовательском sandbox. Реальный AA NOT_RUN. Локально3узких теста/RuffPASS,
старые batches не исполнялись. Общие livegatesfalse.

Flash только ThinkCentre; LANworkingbaseline. Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/
performance/allTS открыты, неwave4/DAE. Ожидается один reportwave3aa-ДАТА.md.
