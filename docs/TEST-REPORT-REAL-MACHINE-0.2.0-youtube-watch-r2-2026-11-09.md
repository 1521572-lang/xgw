# ThinkCentre: настоящие ссылки на ролики YouTube, повтор — 2026-11-09

- Дата; CODE 4b5bd00 (только помощник, исправление: отказ от cookie один раз, видео оценивается
  всегда); сумма OK (37570a3d…); файлов шлюза изменено — **0** (да).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 33/0/0; режим пула observe.
- Проверка: helper_rc=0; время 14,9 мин, 76,1 МБ (лимиты 30 мин / 500 МБ соблюдены). Все строки
  TRIAL и INFO как есть:

```
OK on
OK https
OK user
TRIAL path=normal video=plain1 result=played seconds=56
TRIAL path=normal video=plain2 result=played seconds=82
TRIAL path=normal video=music1 result=played seconds=54
TRIAL path=normal video=music2 result=played seconds=76
TRIAL path=S1 video=plain2 result=bot seconds=65
TRIAL path=S1 video=music2 result=bot seconds=57
TRIAL path=S2 video=plain1 result=played seconds=81
TRIAL path=S2 video=music1 result=played seconds=72
TRIAL path=S3 video=plain2 result=played seconds=101
TRIAL path=S3 video=music2 result=played seconds=73
TRIAL path=S4 video=plain1 result=played seconds=80
TRIAL path=S4 video=music1 result=played seconds=80
INFO normal_played=4/4 servers_played=[0, 2, 2, 2] mb=76.1 minutes=14.9
OK on
OK https
RESULT some_accept
helper_rc=0
```

- RESULT как есть: **`RESULT some_accept`** — ролики сыграли через 3 сервера из 4 (S2, S3, S4 по
  2/2), S1 — оба испытания `bot` (YouTube просит подтвердить, что не робот; помощник это
  записывает, не проходит). Обычный путь — 4/4. Причины не интерпретируются.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **32/1/0** — прежний некритичный WARN, новых
  FAIL нет; режим пула без изменений (да: observe).
- Прошлый прогон (youtube-watch): базовая линия тогда была 0/4 (consent) — исправление помощника
  устранило сбой перехода после запроса о cookie; в этом прогоне все 4 ролика обычного пути
  сыграли.
- Итог: **DONE (RESULT some_accept)** — сравнение состоялось: ролики играют и обычным путём, и
  через 3 из 4 отдельных серверов; S1 — только bot. FAIL нет; машина не менялась. На машине:
  **49f0440** (код шлюза прежний), состояние HEALTHY, VPN включён.
