# ThinkCentre: сверка лёгкого признака с настоящим браузером по серверам — 2026-11-10

- Дата; CODE 90f1612 (только помощники); суммы OK — **обе** (e985d7a0…, 37570a3d…); файлов шлюза
  изменено — **0** (да, на машине прежний 49f0440).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 32/1/0; режим пула observe.
- Проверка: helper_rc=0; время 6,8 мин, 77,0 МБ (лимиты 35 мин / 500 МБ соблюдены). Все строки
  SIGN, TRIAL, MATCH и INFO как есть:

```
OK on
OK https
OK user
SIGN server=S1 video=plain1 verdict=unknown code=200 where=watch status=- reason=- kb=0
TRIAL server=S1 video=plain1 result=played seconds=27
TRIAL server=S1 video=plain2 result=played seconds=37
SIGN server=S1 video=plain2 verdict=accept code=200 where=watch status=OK reason=- kb=345
MATCH server=S1 sign=unknown browser=accept same=-
SIGN server=S2 video=plain1 verdict=accept code=200 where=watch status=OK reason=- kb=328
TRIAL server=S2 video=plain1 result=played seconds=37
TRIAL server=S2 video=plain2 result=played seconds=42
SIGN server=S2 video=plain2 verdict=accept code=200 where=watch status=OK reason=- kb=348
MATCH server=S2 sign=accept browser=accept same=yes
SIGN server=S3 video=plain1 verdict=accept code=200 where=watch status=OK reason=- kb=340
TRIAL server=S3 video=plain1 result=played seconds=44
TRIAL server=S3 video=plain2 result=played seconds=46
SIGN server=S3 video=plain2 verdict=accept code=200 where=watch status=OK reason=- kb=351
MATCH server=S3 sign=accept browser=accept same=yes
SIGN server=S4 video=plain1 verdict=accept code=200 where=watch status=OK reason=- kb=320
TRIAL server=S4 video=plain1 result=played seconds=41
TRIAL server=S4 video=plain2 result=played seconds=52
SIGN server=S4 video=plain2 verdict=accept code=200 where=watch status=OK reason=- kb=359
MATCH server=S4 sign=accept browser=accept same=yes
SIGN server=S5 video=plain1 verdict=refuse code=200 where=watch status=LOGIN_REQUIRED reason=bot kb=310
TRIAL server=S5 video=plain1 result=bot seconds=37
TRIAL server=S5 video=plain2 result=bot seconds=33
SIGN server=S5 video=plain2 verdict=refuse code=200 where=watch status=LOGIN_REQUIRED reason=bot kb=332
MATCH server=S5 sign=refuse browser=refuse same=yes
INFO servers=5 compared=4 same=4 sign_refuse=1 browser_refuse=1 mb=77.0 minutes=6.8
OK on
OK https
RESULT sign_matches
helper_rc=0
```

- RESULT как есть: **`RESULT sign_matches`** — признак и браузер совпали по всем 4 сравнённым
  серверам, и среди них есть сервер, которому YouTube отказал (S5: лёгкий признак refuse со
  статусом LOGIN_REQUIRED и причиной bot, браузер — оба ролика bot). S1 не сравнивался (первый
  лёгкий запрос вернул пустой ответ, признак unknown; браузер при этом сыграл оба ролика).
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **32/1/0** — прежний некритичный WARN, новых
  FAIL нет; режим пула без изменений (да: observe).
- Границы: качество и плавность видео, режим best как таковой и приложения на телефонах не
  проверялись; «не робот» помощник не проходит, а записывает.
- Итог: **DONE (RESULT sign_matches)** — лёгкий признак говорит то же, что настоящий браузер,
  включая случай отказа; FAIL нет; машина не менялась. На машине: **49f0440**, состояние
  HEALTHY, VPN включён.
