# ThinkCentre. До пяти переходов к файлу через VPN и multidisorder — 2026-11-10

- Дата; CODE bfb8218 (установлен один файл zapret2.py); сумма помощника OK (d0f0e387…); база
  c5fbf9f — zapret2.py, daemon.py, zapret2_trace.py сверены cmp с BASE: совпадали.
- До: `CHECK state=off route=0 queue=0 lease=0 capture_on=1`; `OK baseline`; HEALTHY; diag до
  (OK/WARN/FAIL): 33/0/0; режим пула observe; nfqws2 v1.0.7 на месте.
- Тесты: zapret2 + redirect + trace — **65 passed**; daemon `-k zapret2` — 2 passed; новых
  падений нет.
- Согласие владельца — «Разрешаю» в ответе на вопрос (время приватно). Бэкапы zapret2.py и
  config.toml сняты; синтаксис OK; остановлен/запущен только xgw.service; после замены `OK
  baseline`; Xray и sing-box не перезапускались.
- Пробы: 1 — страница (сохранённая, вводил владелец), 2 — свежий адрес файла видеосети (ранее
  одобренный способ, приватно). `[zapret2] mode="compare"`, strategy=multidisorder, очередь 200,
  порт 19999; предупреждений нет; во время раунда конфиг не менялся. До 14 GET, бюджет ≥ 3,5 МиБ.
- Раунд (helper_rc=0): четыре строки PROBE как есть:

```
PROBE n=1 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=65540 ok=1 redirects=0 redirect=none
PROBE n=1 path=zapret2 phase=body kind=ok http=200 connect_http=0 bytes=66298 ok=1 redirects=0 redirect=none
PROBE n=2 path=vpn phase=body kind=ok http=200 connect_http=0 bytes=65536 ok=1 redirects=2 redirect=followed
PROBE n=2 path=zapret2 phase=headers kind=http http=302 connect_http=0 bytes=0 ok=0 redirects=0 redirect=none
TRACE state=observed queue_packets=53 hello=2 send_calls=6 send_ok=6 applied=2 lua_errors=0
RESULT comparison_done
```

- Вывод по парам (по ТЗ): **пара 1** — VPN ok и zapret2 ok: начало тела доступно **по обоим
  путям** (65 540 против 66 298 байт). **Пара 2** — VPN ok: тело файла получено через VPN после
  2 переходов (200, 65 536 байт; redirect=followed) — пригодный контроль наконец получен;
  zapret2 — **HTTP 302, дошёл до HTTP** (не TLS timeout: рукопожатие прямого пути на видео-хосте
  через multidisorder завершилось), 302 — HTTP-отказ, причина неизвестна (прямой запрос Location
  не следует — по конструкции; ссылка подписанная, возможна привязка к IP/сроку). TRACE observed
  (send 6/6, errors=0); общий TRACE к одному адресу не привязывается. Сравнение HTTPS не измеряет
  видео; эффективность против ТСПУ не заявляется.
- Возврат: config.toml байт в байт; watch зафиксировал state=off до finish; **`RESULT
  rollback_ok`**; route=0, queue=0, lease=0, worker_pid нет, capture_on=1, xray_same=1,
  protected_same=1; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; состояние HEALTHY;
  режим пула observe; служебный путь закрыт.
- Границы: видео и качество просмотра не измерены; selective не включался (по ТЗ — даже при
  успехе пар); zapret2-выход раскрывает сайтам домашний IP. Новые раунды и увеличение пределов —
  по ТЗ не проводились (лимит 5 переходов оказался достаточным для тела файла).
- Итог: **DONE (comparison_done)** — тело файла через VPN получено, обе пары оценены; пара 2:
  zapret2 доходит до HTTP (302), TLS через multidisorder на видео-хосте завершается. На машине:
  код bfb8218 (zapret2 off), nfqws2 v1.0.7, состояние HEALTHY, VPN включён.
