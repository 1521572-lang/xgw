# ThinkCentre. Обработка ClientHello и две стратегии zapret2 — 2026-11-10

- Дата; CODE 14c729b (только диагностический код); сумма помощника OK (3ed341db…); база c1ec52c —
  daemon.py и zapret2.py совпали с установленными, zapret2_trace.py отсутствовал (норма).
- До: `CHECK state=off route=0 queue=0 lease=0 capture_on=1`; `OK baseline`; HEALTHY; diag до —
  32/1/0 (после — 33/0/0); режим пула observe; nfqws2 v1.0.7 и Lua на месте.
- Самопроверка без сети: **`RESULT trace_selftest_ok`** (Lua, сохранение verdict, восстановление
  отправки при ошибке; intercept=0, очередь не открывалась).
- Тесты: test_zapret2 + test_zapret2_trace — **50 passed**; daemon `-k zapret2` — 2 passed; новых
  падений нет.
- Согласие владельца на установку 3 файлов — «Разрешаю» (время приватно). Замена с остановкой/
  запуском только xgw.service; копии daemon.py, zapret2.py и config.toml сняты; синтаксис 3 файлов
  OK; после установки `OK baseline`; Xray и sing-box не перезапускались.
- Раунд A (multisplit, compare; страница — сохранённая владельца, файл — свежий через ранее
  одобренный способ; 4 GET):

```
PROBE n=1 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=66666 ok=1
PROBE n=1 path=zapret2 phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
PROBE n=2 path=vpn phase=headers kind=http http=302 connect_http=0 bytes=0 ok=0
PROBE n=2 path=zapret2 phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
TRACE state=observed queue_packets=14 hello=7 send_calls=21 send_ok=21 applied=7 lua_errors=0
RESULT comparison_done
```

  Возврат: config вернулся байт в байт, но первый finish снял `rollback_failed` (опрос раньше
  перечитывания конфига); через 90 с — state=off, `OK baseline`, HEALTHY. **Отклонение**: раунд B
  запущен по отдельному разрешению владельца (формальный rollback_ok раунда A не выдавался).
- Раунд B (multidisorder, те же адреса, не обновлялись; 4 GET; всего 8 GET — лимит соблюдён):

```
PROBE n=1 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=66740 ok=1
PROBE n=1 path=zapret2 phase=body kind=ok http=200 connect_http=0 bytes=66424 ok=1
PROBE n=2 path=vpn phase=headers kind=http http=302 connect_http=0 bytes=0 ok=0
PROBE n=2 path=zapret2 phase=tls kind=timeout http=0 connect_http=0 bytes=0 ok=0
TRACE state=observed queue_packets=47 hello=1 send_calls=3 send_ok=3 applied=1 lua_errors=0
RESULT comparison_done
```

  Возврат: config байт в байт, демон принял off, **`RESULT rollback_ok`**, state=off, worker_pid
  нет, route=0, queue=0, lease=0, capture_on=1, xray_same=1, protected_same=1.
- Вывод по парам (по ТЗ, только с удачным VPN-контролем): **пара 1** — VPN ok в обоих раундах;
  multisplit — TLS timeout, **multidisorder — страница загрузилась напрямую (HTTP 200, ~66 КБ)**;
  обработка ClientHello наблюдалась в обоих раундах (observed, send_ok=send_calls, lua_errors=0) —
  это не подтверждает доставку/обход ТСПУ, но различие стратегий на одном пути зафиксировано.
  **Пара 2** — VPN-контроль неудачен в обоих раундах (TLS timeout, затем 302 истёкшей ссылки) —
  вывод неопределённый. HTTP 302 объясним сроком/IP подписанного URL. Сравнение HTTPS не измеряет
  видео; эффективность против ТСПУ не заявляется.
- Конечное: diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; состояние HEALTHY; режим пула
  observe; zapret2 off; диагностический код оставлен установленным (3 файла), режим off.
- Итог: **DONE** — оба раунда сравнения завершены, TRACE подтверждён, откат чистый. Отклонение
  последовательности: раунд B по разрешению владельца без формального rollback_ok раунда A
  (возврат был подтверждён позже — state=off). На машине: код 14c729b, состояние HEALTHY, VPN
  включён.
