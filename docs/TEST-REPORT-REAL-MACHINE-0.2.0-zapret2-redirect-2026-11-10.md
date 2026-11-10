# ThinkCentre. Конечный адрес файла через VPN и multidisorder — 2026-11-10

- Дата; CODE c5fbf9f (установлен один файл zapret2.py); сумма помощника OK (402849b1…); база
  14c729b — zapret2.py, daemon.py, zapret2_trace.py сверены cmp с BASE: совпадали.
- До: `CHECK state=off route=0 queue=0 lease=0 capture_on=1`; `OK baseline`; HEALTHY; diag до
  (OK/WARN/FAIL): 33/0/0; режим пула observe.
- Тесты: zapret2 + redirect + trace — **63 passed**; daemon `-k zapret2` — 2 passed; новых
  падений нет.
- Согласие владельца на установку и раунд — «разрешаю» в чате (время приватно). Бэкапы zapret2.py
  и config.toml сняты; синтаксис OK; остановлен/запущен только xgw.service; после замены `OK
  baseline`; Xray и sing-box не перезапускались.
- Пробы: 1 — страница (сохранённая с приёмки, вводил владелец), 2 — свежий адрес файла видеосети
  (ранее одобренный способ, приватно). `[zapret2] mode="compare"`, strategy=multidisorder, очередь
  200, порт 19999; предупреждений чтения нет; во время раунда конфиг не менялся.
- Раунд (helper_rc=0): четыре строки PROBE как есть:

```
PROBE n=1 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=66810 ok=1 redirects=0 redirect=none
PROBE n=1 path=zapret2 phase=body kind=ok http=200 connect_http=0 bytes=66298 ok=1 redirects=0 redirect=none
PROBE n=2 path=vpn phase=headers kind=http http=302 connect_http=0 bytes=0 ok=0 redirects=2 redirect=limit
PROBE n=2 path=zapret2 phase=headers kind=http http=302 connect_http=0 bytes=0 ok=0 redirects=0 redirect=none
TRACE state=observed queue_packets=52 hello=2 send_calls=6 send_ok=6 applied=2 lua_errors=0
RESULT comparison_done
```

- Вывод по парам (по ТЗ): **пара 1** — VPN ok и zapret2 ok: начало тела файла/страницы доступно
  **по обоим путям** (multidisorder, тело 66 810 против 66 298 байт). **Пара 2** — VPN ушёл в
  цепочку из 2 переходов и упёрся в лимит (redirect=limit, итог 302) — пригодный контроль не
  получен, **вывод неопределённый**; zapret2 вернул 302 без переходов (Location не следует — так
  задумано). По ТЗ 302 сам по себе не доказывает истечение ссылки — теперь видно, что это цепочка
  длиннее двух переходов. TRACE observed (send 6/6, errors=0); общий TRACE к одному адресу не
  привязывается.
- Возврат: config.toml байт в байт; watch показал state=off до finish (раннего отката не было);
  **`RESULT rollback_ok`**; route=0, queue=0, lease=0, worker_pid нет, capture_on=1, xray_same=1,
  protected_same=1; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; состояние HEALTHY;
  режим пула observe; служебный путь закрыт.
- Границы: видео и качество просмотра не измерены; selective не включался (по ТЗ — даже при
  успехе пары 1); zapret2-выход раскрывает сайтам домашний IP.
- Итог: **DONE (comparison_done)** — сравнение завершено, пара 1 доступна по обоим путям, пара 2
  неопределённая (лимит переходов VPN). На машине: код c5fbf9f (zapret2 off), nfqws2 v1.0.7,
  состояние HEALTHY, VPN включён.
