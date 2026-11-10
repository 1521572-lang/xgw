# ThinkCentre. Признак допуска YouTube в выборе выхода — 2026-11-10

- Дата; CODE fbd4c28 (установлен, оставлен); сумма помощника OK (ab48cc8e…); база bfb8218 — все 6
  файлов (config.py, daemon.py, diag.py, watch/checks.py, watch/status.py, watch/youtube.py)
  сверены cmp с BASE: совпадали; sing-box inactive зафиксирован как исходное состояние (helper —
  учёт прошлого отчёта: проверяется сохранение состояния, не работа службы).
- До: `CHECK healthy=1 capture_on=1 best=0 sign_enabled=0 route=0 warnings=0`; HEALTHY; diag до
  (OK/WARN/FAIL): 33/0/0; пул observe; nfqws2 v1.0.7 вне этой проверки.
- Тесты: config + youtube + checks — **107 passed**; daemon `-k media` — **19 passed**; новых
  падений нет.
- Согласия владельца (в чате): код — «Разрешаю код»; временный best — «Разрешаю best»; адрес
  ролика — «ролик возьми сам с youtube» (использован данный владельцем ранее в этой серии,
  приватно; в отчёте адреса нет).
- Установка: копии 6 файлов и config.toml сняты; синтаксис 6 файлов OK; остановлен/запущен только
  xgw.service; после замены `CHECK healthy=1 capture_on=1 best=0 sign_enabled=0 route=0
  warnings=0`; Xray PID сохранён (1889), sing-box остался в исходном inactive.
- Раунд: SINCE зафиксирован до правки; в [media] временно mode=best + sign_url (приватно);
  штатное перечитывание демоном; `CHECK best=1 sign_enabled=1 warnings=0`; проверки [speed]
  YouTube штатные, порог положительный (5 Мбит/с). Окно 8 минут, сводка раз в минуту; метки SIGN
  как есть (итоговая):

```
CHECK healthy=1 capture_on=1 best=1 sign_enabled=1 route=1 warnings=0
SIGN accept=3 refuse=0 unknown=0 refused_active=0 all_refused=0
```

  Признак собирал свежие допуски (accept 1→2→3), route=1 с первой минуты, HEALTHY всё окно,
  предупреждений нет. Отказа (refuse) за окно не встретилось — смена выхода по отказу не
  происходила: **событие смены — NOT_RUN** (это не FAIL: у всех опрошенных серверов YouTube
  допуск был). refused_active=0, all_refused=0.
- Возврат: config.toml байт в байт; через шаг демона — `CHECK healthy=1 capture_on=1 best=0
  sign_enabled=0 route=0 warnings=0`; ядра в исходных состояниях (xray active 1889, singbox
  inactive 0); diag после (OK/WARN/FAIL): **32/1/0** — прежний некритичный WARN, новых FAIL нет;
  HEALTHY; пул observe.
- Границы: смена выхода при отказе на живом сервере не наблюдена (отказов не было); плавность и
  качество видео не измерялись; zapret2, подписки, ручной выбор не трогались.
- Установленный код fbd4c28 оставлен (6 файлов); [media] в config нет; nfqws2 не привлекался.
- Итог: **PASS** — признак допуска встроен: собирается в живом режиме best, попадает в статус
  (строка допуска есть), маршрут выбирается при accept, отказ-ветка — NOT_RUN (отказов не было);
  возврат чистый. Первый непройденный шаг — отсутствует. На машине: код fbd4c28, HEALTHY, VPN
  включён.
