# ThinkCentre: играет ли YouTube напрямую, без сервера VPN — 2026-11-10

- Дата; CODE 831dd5f (только помощник); сумма OK (527204bc…); файлов шлюза изменено — **0** (да,
  на машине прежний 49f0440, установки и смены настроек не было).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 32/1/0; режим пула observe.
- Проверка: helper_rc=0; время 29,6 мин. Временный Xray поднят и убран помощником (`OK
  temp_xray`). Все строки TRIAL и INFO как есть:

```
OK on
OK https
OK user
OK temp_xray
TRIAL path=normal video=plain1 result=played start_s=13 stalls=0 seconds=117
TRIAL path=normal video=plain2 result=played start_s=5 stalls=0 seconds=130
TRIAL path=normal video=music1 result=played start_s=5 stalls=0 seconds=135
TRIAL path=normal video=music2 result=played start_s=5 stalls=0 seconds=192
TRIAL path=direct video=plain1 result=no_browser start_s=- stalls=0 seconds=135
TRIAL path=direct video=plain2 result=no_browser start_s=- stalls=0 seconds=110
TRIAL path=direct video=music1 result=no_browser start_s=- stalls=0 seconds=131
TRIAL path=direct video=music2 result=no_browser start_s=- stalls=0 seconds=119
TRIAL path=fragment video=plain1 result=no_browser start_s=- stalls=0 seconds=123
TRIAL path=fragment video=plain2 result=no_browser start_s=- stalls=0 seconds=136
TRIAL path=fragment video=music1 result=no_browser start_s=- stalls=0 seconds=138
TRIAL path=fragment video=music2 result=no_browser start_s=- stalls=0 seconds=103
TRIAL path=split video=plain1 result=no_browser start_s=- stalls=0 seconds=50
TRIAL path=split video=plain2 result=no_browser start_s=- stalls=0 seconds=53
TRIAL path=split video=music1 result=no_browser start_s=- stalls=0 seconds=59
TRIAL path=split video=music2 result=no_browser start_s=- stalls=0 seconds=47
INFO normal=4/4 direct=0/4 fragment=0/4 split=0/4 minutes=29.6
OK on
OK https
RESULT none_ok
helper_rc=0
```

- RESULT как есть: **`RESULT none_ok`** — ни один прямой путь (direct, fragment, split) не дал
  хотя бы 3 из 4: во всех 12 испытаниях прямых путей `no_browser` (Firefox для них не
  запустился); обычный путь через шлюз — 4/4, старт видео 5–13 с, ожиданий данных нет. Причины
  не интерпретируются, повтор по ТЗ не делался.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **32/1/0** — прежний некритичный WARN, новых
  FAIL нет; режим пула без изменений (да: observe). Примечание: машина перезагружалась после
  прогона (выключение 00:16, загрузка 00:35) — конечное состояние снято после загрузки; на
  работу прогона это не влияло.
- Границы: качество видео и скорость не проверялись; работа программы zapret не заявляется;
  «не робот» помощник не проходит, а записывает.
- Итог: **DONE (RESULT none_ok)** — FAIL нет; машина вернулась к исходному коду (изменений не
  было). На машине: **49f0440**, состояние HEALTHY, VPN включён.
