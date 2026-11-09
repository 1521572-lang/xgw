# ThinkCentre: настоящие ссылки на ролики YouTube — 2026-11-09

- Дата; CODE 2744045 (только помощник); сумма OK (aabb3b94…); файлов шлюза изменено — **0** (да).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 33/0/0; режим пула observe.
- Проверка: helper_rc=4; время 18,9 мин, 78,1 МБ (лимиты 30 мин / 500 МБ соблюдены). Все строки
  TRIAL и INFO как есть:

```
OK on
OK https
OK user
INFO servers_chosen=4
TRIAL path=normal video=plain1 result=consent seconds=115
TRIAL path=normal video=plain2 result=consent seconds=117
TRIAL path=normal video=music1 result=consent seconds=117
TRIAL path=normal video=music2 result=consent seconds=132
TRIAL path=S1 video=plain2 result=bot seconds=45
TRIAL path=S1 video=music2 result=stuck seconds=121
TRIAL path=S2 video=plain1 result=consent seconds=117
TRIAL path=S2 video=music1 result=consent seconds=120
TRIAL path=S3 video=plain2 result=played seconds=54
TRIAL path=S3 video=music2 result=played seconds=68
TRIAL path=S4 video=plain1 result=played seconds=65
TRIAL path=S4 video=music1 result=played seconds=56
INFO normal_played=0/4 servers_played=[0, 0, 2, 2] mb=78.1 minutes=18.9
OK on
OK https
NOT_RUN no_playback
helper_rc=4
```

- RESULT или NOT_RUN как есть: **`NOT_RUN no_playback`** — сравнение не удалось: обычным путём не
  сыграло ни одного (0/4, все застряли на запросе о cookie), а итоговое сравнение требует
  сыгравшей базовой линии. По ТЗ — не FAIL, повторять не надо. Причины не интерпретируются.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; режим пула без
  изменений (да: observe).
- Факты без толкования: через отдельные серверы сыграло 4 из 8 (S3: 2/2, S4: 2/2; S1 — bot и
  stuck; S2 — consent ×2); обычный путь — 0 из 4 (consent ×4). Помощник на запросе о cookie
  выбирал отказ от необязательных; «подтвердить, что не робот» он не проходит и записывает как
  bot.
- Итог: **NOT_RUN** — первое непройденное по сути событие: базовая линия не сыграла (шаг 3,
  NOT_RUN, не FAIL). FAIL нет; машина не менялась. На машине: **49f0440** (код шлюза прежний),
  состояние HEALTHY, VPN включён.
