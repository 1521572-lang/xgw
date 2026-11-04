# Разбор wave3v: локальная диагностика завершена в своём scope

[Отчёт V](https://github.com/1521572-lang/xgw/blob/be1fc1bf8b5bcc9a6e0f9b1b68eeaa8680ad1acf/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3v-2026-11-03.md)
принят fast-forward, commit **be1fc1bf8b5bcc9a6e0f9b1b68eeaa8680ad1acf**.
Прогон 03.11.2026 08:51:43–08:55 MSK; сбор **1.747 с**.
Tested HEAD **e8151bce2006a434f2c217ae838467bd4f4a51c6**,
tree **4331a5b76b78e3b4f19e13ec9969d2096e8b4934**.
Product pin **351fb54e074f4a7b497a8a4244fc74c6088788d7**; runtime diff пуст,
installed4 совпали, Python-дерево110/110, восемь frozen SHA верны.

## Принимаемые результаты

Start rc0/EVIDENCE_CLOSURE_STARTED, monitor BATCH_FINISHED, show rc0/final summary.json;
**EVIDENCE_CLOSURE_RECORDED**, четыре collection RECORDED, сетевых запросов0.
Внутри V сохранены рабочий HEALTHY/on, settings3, SB/Xray configs, три cache body,
одно поколение last-good, boot/process/шесть PID/pin. Конечная связь живая.
NNP канала0/sudo0; изменения владельца не понадобились. Полная волна3 этим не закрыта.

| Этап | Принятый факт | Что из него не следует |
|---|---|---|
| V1 | Current SB bytes равны U; Xray bytes отличаются от U | Не установлены время, writer или причина изменения Xray |
| V2 | Те же три cache body; 101 supported; 67 default VLESS =66 equal+0 mismatch+0 ambiguity+1 missing_identity | Отсутствие supported-тройки server/port/uuid не доказывает runtime/parser/server bug |
| V3 | В текущей паре current/last-good изменены44 объекта VLESS; только группа полей tls=44, остальные категории0; tags added/removed0; pending отсутствует | Не установлены конкретное TLS-поле, автор, причина и время; это не44 физических сервера |
| V4 | Один журнал2ч, EOF/rc0/query_ok=true;364930 bytes,708 строк, нет row/byte/time limit, parse errors0; reloaded1/systemd_reload_word2 | Слова не устанавливают точную запись конфигурации, конкретный writer или причину дрейфа |

### Оставшаяся запись

[contract_gaps](https://github.com/1521572-lang/xgw/blob/e8151bce2006a434f2c217ae838467bd4f4a51c6/tests/stand/wave3_evidence_closure.py#L36-L76)
проверяет точную тройку server/port/uuid только среди supported records.
При совпавших SB и трёх cache body связь V с прежним U gap хорошо обоснована в этой
границе. Полная историческая связь manual/config inputs отдельно не записывалась;
ни происхождение отсутствующей записи, ни идентичность endpoint времён R/N не установлены.
Это не основание выбирать приблизительное совпадение, удалять вход или менять pin/pool.

Предложение отчёта о fingerprint-only/расширенном соответствии оставляем в backlog.
Такое соответствие может быть диагностическим evidence, но не заменяет точное сравнение
и не разрешает назначить правильный источник по сходству. Новый микропрогон ради одного
missing_identity сейчас не нужен. Static mismatch отсутствует; продуктовый fix не обоснован.

### TLS и журнал

[generation_categories](https://github.com/1521572-lang/xgw/blob/e8151bce2006a434f2c217ae838467bd4f4a51c6/tests/stand/wave3_evidence_closure.py#L79-L134)
разделил VLESS и группы: в наблюдаемой паре V изменение групп не объясняет44 различия.
Категория tls включает весь вложенный объект: из неё нельзя выбрать сертификат, SNI,
REALITY key/short-id или uTLS fingerprint как причину. Содержимое не раскрывалось.
Identity(server/port/uuid/password) в этой паре не менялась. Непрерывная идентичность
last-good между U и V отдельно не проверялась; результат V не переписывает старое U.

[bounded_journal](https://github.com/1521572-lang/xgw/blob/e8151bce2006a434f2c217ae838467bd4f4a51c6/tests/stand/wave3_evidence_closure.py#L174-L244)
успешно завершился в пределах бюджета. Cleanup собственного journalctl child не понадобился.
Прежний U8 TimeoutExpired остаётся фактом своего прогона. Новое чтение не назначает причину
старого timeout. Отсутствие слов rollback/rejected в ограниченной выборке не доказывает
отсутствия всех ошибок. Повтор/расширение журнала не требуется для завершения этой ветви.

R negative остаётся отрицательной попыткой своего времени. Static reference12/12 и короткий
saved OK не превращают её в PASS. Причины «ТСПУ», «сервер мёртв» или «TLS-поле неверно»
не установлены; активную попытку R сейчас не повторять.

## Следующая работа: возврат исходного on

Наблюдательная ветвь U/V завершена в заявленном scope; новых runtime-дефектов не найдено.
Следующий открытый барьер перед scoped faults — независимое восстановление **исходного on**.
Старый helper [restore](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/tests/stand/wave3_safety.py#L97-L137)
восстанавливает off и оставляет демон остановленным; его нельзя превратить в on-механизм
сменой одного строкового маркера. Ожидание следующей команды модели после обрыва>1мин
не является восстановлением.

[ADR](ADR-RECOVERY-ORIGINAL-ON.md) и [единое ТЗ реализации](PR-SPEC-WAVE3-ON-RECOVERY.md)
разделяют модель контракта, fencing писателей, snapshot, независимый driver и реальный опыт.
Первый кандидат REC-A — чистая state machine в tests/stand/wave3_on_recovery_model.py.
Драйвер, writer fence и восстановление реальной системы **не реализованы** этим кандидатом.
Все реальные proof flags по умолчанию false. Синтетические true явно задаются только fixture.

[ТЗ W](TEST-PLAN-REAL-MACHINE-0.2.0-wave3w.md) даёт Flash один пакет из25 синтетических
сценариев на ThinkCentre и один итоговый отчёт. Модель не импортирует XGW и не имеет I/O
с сетью/службами/правилами/config. Simulated controller loss не доказывает автономность
процесса на реальной машине. W не запускает timer/guardian и не разрешает faults/D1-on.
Локально выполнены только AST/static safety и Ruff;16 блоков ТЗ прошли bash-n,
девять встроенных Python-блоков прошли AST parsing. Сами сценарии переданы реальной машине.
**Реальная wave3w NOT_RUN.** Ожидается TEST-REPORT-REAL-MACHINE-0.2.0-wave3w-ДАТА.md.

Доступен только ThinkCentre. LAN UDP/IPv6/DNS/E4 не подменять запросами шлюза. Рабочая LAN
считается работающей. D1-on/scoped faults, performance, all Tailscale и полная wave3 открыты;
wave4/DAE не начинать. WAN/LAN/Tailscale/pin/pool/службы/правила остаются неизменными.

## После фактического W

[Review W](REVIEW-REAL-MACHINE-0.2.0-wave3w.md):25/25 synthetic cases приняты,
status HEALTHY/on и pool сохранены. Реальное recovery/автономность не проверены.
Следующий X — REC-B candidate private snapshot/26fixtures/nft-check-only/after;
writer fence/runtime driver не реализованы, live faults не разрешены этим результатом.
Readonly TLS/cache/journal ветвь не возобновляется.
