# ThinkCentre. Сравнение HTTPS-проб через VPN и zapret2 — 2026-11-10

- Дата; CODE c1ec52c (только диагностический код); сумма помощника OK (8dec42e2…); база
  e3c8068 — установленные 5 файлов сверены cmp: совпадали; zapret2 off, nfqws2 v1.0.7 на месте
  (v1.0.7 подтверждена помощником).
- До: `CHECK state=off route=0 queue=0 lease=0 capture_on=1 warnings=0`; `OK baseline`;
  HEALTHY; diag до — 32/1/0 (после — 32/1/0); режим пула observe.
- Тесты: первый набор — 5 failed / 227 passed / 15 skipped, все 5 в test_nft.py
  **BASELINE_FAIL** (идентично на базе, «новые падения» — пусто); daemon `-k zapret2` — 2 passed.
- Согласие владельца: замена 5 файлов (config.py, daemon.py, net/nft.py, watch/checks.py,
  zapret2.py) с перезапуском только xgw.service — «Разрешаю». Копии файлов и config.toml сняты
  и сверены; синтаксис 5 файлов OK; Xray и sing-box не перезапускались; после замены `OK
  baseline`, capture_on=1.
- Пробы: 1 — страница YouTube (сохранена с приёмки zapret2, вводил владелец), 2 — свежий адрес
  файла видеосети (извлечён тем же ранее одобренным способом, приватно). Раздел
  `[zapret2] mode="compare"`, strategy=multisplit, очередь 200, порт 19999; config читается без
  предупреждений; во время раунда не менялся.
- Раунд (helper_rc=0): четыре строки PROBE как есть:

```
PROBE n=1 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=66740 ok=1
PROBE n=1 path=zapret2 phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
PROBE n=2 path=vpn phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
PROBE n=2 path=zapret2 phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
RESULT comparison_done
```

- Сопоставление (по ТЗ, без догадок): проба 1 — VPN прошёл (HTTP 200, тело получен), zapret2 —
  **расхождение на этапе TLS** (рукопожатие прямого пути не завершилось). Проба 2 — оба пути
  пали на TLS, причина для zapret2 **неопределённая** (по ТЗ); подписанный URL файла мог быть
  привязан к сроку/IP. Сравнение HTTPS не измеряет видео.
- Возврат: config.toml возвращён байт в байт; `RESULT rollback_ok`; state=off; route=0;
  lease=0; queue=0; capture_on=1; PID Xray не менялся (xray_same=1 по CHECK до/после); защищённые
  настройки совпали; worker_pid нет; diag после — 32/1/0, новых FAIL нет; состояние HEALTHY;
  служебный путь закрыт. Диагностический код (5 файлов) оставлен установленным, режим off.
- Итог: **DONE** — записаны четыре результата, служебный путь закрыт, возврат чистый. Пригодность
  zapret2 по каждой паре: проба 1 — zapret2 не проходил TLS (VPN проходил); проба 2 — не
  определено. Эффективность против ТСПУ не заявляется. На машине: код c1ec52c (режим off),
  состояние HEALTHY, VPN включён.
