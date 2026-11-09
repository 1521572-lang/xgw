# ThinkCentre: играет ли YouTube напрямую, повтор с исправленным помощником — 2026-11-10

- Дата; CODE 9a8fd17 (только помощник); сумма OK (46adc34f…); файлов шлюза изменено — **0** (да,
  на машине прежний 49f0440).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 32/1/0; режим пула observe.
- Проверка: helper_rc=4; время 19,0 мин. Временный Xray поднят и убран (`OK temp_xray`). Все
  строки PRECHECK, TRIAL и INFO как есть:

```
OK on
OK https
OK user
OK temp_xray
PRECHECK path=normal url=page curl=0 code=204 first_s=0.5 mbps=0.0
PRECHECK path=normal url=video curl=0 code=204 first_s=0.5 mbps=0.0
PRECHECK path=normal url=file curl=0 code=206 first_s=0.5 mbps=17.3
PRECHECK path=direct url=page curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=direct url=video curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=direct url=file curl=0 code=206 first_s=0.9 mbps=6.3
PRECHECK path=fragment url=page curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=fragment url=video curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=fragment url=file curl=0 code=206 first_s=0.9 mbps=6.2
PRECHECK path=split url=page curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=split url=video curl=28 code=000 first_s=0.0 mbps=0.0
PRECHECK path=split url=file curl=0 code=206 first_s=1.2 mbps=5.6
TRIAL path=normal video=plain1 result=played start_s=8 stalls=0 seconds=40
TRIAL path=normal video=plain2 result=played start_s=2 stalls=0 seconds=41
TRIAL path=normal video=music1 result=played start_s=2 stalls=0 seconds=42
TRIAL path=normal video=music2 result=played start_s=2 stalls=0 seconds=43
TRIAL path=direct video=plain1 result=navigate_hang start_s=- stalls=0 seconds=78
TRIAL path=direct video=plain2 result=navigate_hang start_s=- stalls=0 seconds=73
TRIAL path=direct video=music1 result=navigate_hang start_s=- stalls=0 seconds=76
TRIAL path=direct video=music2 result=navigate_hang start_s=- stalls=0 seconds=72
TRIAL path=fragment video=plain1 result=navigate_hang start_s=- stalls=0 seconds=72
TRIAL path=fragment video=plain2 result=navigate_hang start_s=- stalls=0 seconds=73
TRIAL path=fragment video=music1 result=navigate_hang start_s=- stalls=0 seconds=72
TRIAL path=fragment video=music2 result=navigate_hang start_s=- stalls=0 seconds=72
TRIAL path=split video=plain1 result=navigate_hang start_s=- stalls=0 seconds=71
TRIAL path=split video=plain2 result=navigate_hang start_s=- stalls=0 seconds=71
TRIAL path=split video=music1 result=navigate_hang start_s=- stalls=0 seconds=72
TRIAL path=split video=music2 result=navigate_hang start_s=- stalls=0 seconds=71
INFO normal=4/4 direct=0/0 fragment=0/0 split=0/0 minutes=19.0
OK on
OK https
NOT_RUN direct_unmeasured
helper_rc=4
```

- NOT_RUN как есть: **`NOT_RUN direct_unmeasured`** — прямые пути не измерены: все 12 браузерных
  запусков зависли (`navigate_hang`, по ~71–78 с), по исправленной методике зависания не
  считаются измеренными. По ТЗ — не FAIL, повторять не надо. Причины не интерпретируются.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; режим пула без
  изменений (да: observe).
- Факты без толкования: PRECHECK показал, что через все прямые пути (с дроблением и без) страница
  и видеосеть не отвечают вовсе (curl=28, таймаут), при этом файл замера из настроек по тем же
  прямым путям отвечает (206, 5,6–6,3 Мбит/с; через обычный путь — 17,3); браузерные испытания
  прямых путей согласуются — навигация висит. Обычный путь через шлюз: 4/4, старт 2–8 с,
  stalls=0.
- Итог: **NOT_RUN** (прямые пути не измерены) — FAIL нет; машина не менялась. На машине:
  **49f0440**, состояние HEALTHY, VPN включён.
