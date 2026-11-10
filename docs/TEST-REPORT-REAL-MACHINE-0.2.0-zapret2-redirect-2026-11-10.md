# ThinkCentre. Конечный адрес файла через VPN и multidisorder — 2026-11-10

- Дата; CODE c5fbf9f (не установлен); сумма помощника OK (402849b1…); база 14c729b —
  установленные zapret2.py, daemon.py, zapret2_trace.py сверены cmp с BASE: совпадают.
- До: `CHECK state=off route=0 queue=0 lease=0 capture_on=1`; `OK baseline`; HEALTHY; diag до
  (OK/WARN/FAIL): 33/0/0; режим пула observe; nfqws2 v1.0.7 на месте.
- Тесты: test_zapret2 + test_zapret2_redirect + test_zapret2_trace — **63 passed**; daemon
  `-k zapret2` — 2 passed; новых падений нет.
- Согласие на замену zapret2.py: спрошено дважды (время приватно) — **ответа нет**. По границе
  согласия установка не проводилась, раунд compare не проводился, probe_urls не вносились.
- Строки ATTEMPT/PROBE/TRACE: отсутствуют (установка и раунд не начинались).
- Конечное: `CHECK state=off … OK baseline`, on/HTTPS OK; diag после (OK/WARN/FAIL): **33/0/0** —
  новых FAIL нет; режим пула без изменений (да: observe); состояние HEALTHY.
- Границы: редиректы VPN и конечный адрес файла не измерены (раунд требует установленного кода);
  вопрос пары 2 из отчёта zapret2-trace остаётся открытым. Разрешения на YouTube-запросы и
  Firefox использованы не были.
- Итог: **INSTALL_ONLY** (код не устанавливался — согласие не получено; всё измеримое до
  установки — чисто; первый непройденный шаг — 2 (согласие). На машине: **14c729b** (не менялся),
  состояние HEALTHY, VPN включён, zapret2 off, nfqws2 v1.0.7 на месте.
