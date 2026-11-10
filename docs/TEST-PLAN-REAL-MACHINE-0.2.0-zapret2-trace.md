# ThinkCentre. Обработка ClientHello и две стратегии zapret2

Исполнитель GLM-5.3-Flash. База — отчёт `0c749fc`, установленный код `c1ec52c`.
Шлюз HEALTHY, zapret2 off, nfqws2 v1.0.7. Страница прошла через VPN, multisplit дал
TLS timeout; файл видеосети дал TLS timeout по обоим путям. Эффективность не установлена.
Задача — увидеть обработку ClientHello и, если она подтверждена, сравнить multidisorder.
Только служебные пробы в mode=compare. Клиенты продолжают пользоваться прежним маршрутом.

Использовать закреплённый ниже CODE и проверить сумму помощника перед запуском.
Никаких новых пакетов, смены WAN, LAN, Tailscale, пула, ручного выбора или подписок.
Адреса только из приватных настроек владельца. Экраном не управлять. Не запускать blockcheck,
полный debug, захват пакетов или перебор стратегий. Два ограниченных раунда, без автоповторов.

## 1. Подготовка и самопроверка без сети

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=14c729bfc4d018edf6b0665871a7568c2d1925e4
BASE=c1ec52c945a1d9f1b66264b5e5aaf688a36038ef
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-trace.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
test "$(git -C "$D/new" rev-parse HEAD)" = "$CODE"
H="$D/new/docs/helpers/zapret2_check.py"
printf '%s  %s\n' '3ed341dbfb624b896cc3b5062cc06e69ec8fa1b75c0545ec3ca6b39ea9fc0930' "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
sudo python3 -I "$H" selftest --state "$D/before.json"
```

Нужны `OK baseline`, off, capture_on=1, route=0, queue=0, lease=0, HEALTHY, без новых FAIL.
Версию nfqws2 v1.0.7 и соответствующие Lua сверить локально, пути не публиковать.
`trace_selftest_ok` проверяет Lua, сохранение verdict и восстановление отправки при ошибке.
Используется intercept=0, все отправки заменены заглушками. Очередь не открывается.
Любая ошибка — STOP, без установки и без раундов. Сырые сообщения команд не публиковать.

## 2. Проверка и установка трёх файлов

```bash
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_zapret2.py tests/test_zapret2_trace.py)
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_daemon.py -k zapret2)
```

Нет инструментов — NOT_RUN tools; ничего не устанавливать. Новое падение — STOP.
Перед изменением установленного XGW получить согласие владельца. Сверить cmp установленные
`/opt/xgw/lib/xgw/daemon.py` и `zapret2.py` с `$D/base/src/xgw/`; `zapret2_trace.py` должен
отсутствовать. При расхождении STOP. Сохранить приватно копии первых двух файлов и config.toml
байт-в-байт с владельцами и правами. Проверить Python-синтаксис трёх новых файлов.
Остановить только xgw.service; установить из `$D/new/src/xgw/` daemon.py, zapret2.py,
zapret2_trace.py с прежними владельцами и правами (новый — как zapret2.py); запустить демон.
Xray и sing-box не перезапускать. Сверить capture_on=1, route=0, xray_same=1, protected_same=1.
При ошибке вернуть прежние два файла, удалить только добавленный zapret2_trace.py, вернуть
конфиг и запустить xgw.service. Диагностировать причину приватно, раунды не начинать.

## 3. Раунд A — multisplit

Владелец задаёт два ранее разрешённых HTTPS-адреса: 1 — страница, 2 — свежий файл видеосети.
Файл брать тем же ранее согласованным способом. В отчёте только номера 1 и 2.
Применить `[zapret2] mode="compare"`, strategy="multisplit", очередь 200 и порт 19999.
Остальные настройки — как до прогона, предупреждений чтения конфига быть не должно.
Во время раунда конфиг и службы не трогать. До 4 GET по 8 с, резерв 1 МиБ на раунд.

```bash
sudo python3 -I "$H" compare --state "$D/before.json" --seconds 180 || echo "comparison_rc=$?"
```

Сохранить 4 строки PROBE, одну TRACE и RESULT. comparison_done означает завершение раунда.
После него восстановить исходный config.toml с владельцем и правами, дождаться off:

```bash
sudo python3 -I "$H" finish --state "$D/before.json"
```

Нужен rollback_ok. При STOP, неполном сравнении, отсутствии off или новом FAIL — закончить.

## 4. Решение по TRACE и раунд B

TRACE — сумма за раунд, не отдельный адрес. Повторные ClientHello могут увеличивать счётчики.
- state=observed, queue_packets>0, hello>0, applied>0, send_calls=send_ok и lua_errors=0:
  обработка и отправка сегментов наблюдались; это не подтверждает доставку или обход ТСПУ.
- send_calls>send_ok либо lua_errors>0: сбой обработки/отправки; остановиться, нужен разбор.
- Нули, state=incomplete/unavailable или queue_packets=-1: недостаточно свидетельств;
  остановиться. Это не доказательство, что ClientHello не обрабатывался.

Раунд B разрешён только после первой строки условий выше и rollback_ok раунда A.
Если оба адреса в A прошли через VPN и zapret2, B пропустить: выбрать кандидата multisplit
для отдельной приёмки, без включения selective. Иначе нужен хотя бы один удачный VPN-контроль
в A. Если оба VPN-контроля неудачны, B не запускать; сначала нужен пригодный контроль.
С теми же двумя адресами повторить раздел 3 ровно один раз с strategy="multidisorder".
Перед B убедиться, что исходный mode=off уже принят. Новый раунд начинается сменой настроек,
без рестарта демона. Перед ним повторно сверить baseline помощником inspect.
После B снова вернуть исходный конфиг и выполнить finish. Максимум 8 GET за всё ТЗ.
Адреса между A и B не обновлять: если ссылка перестала проходить VPN, её пара неопределённая.

## 5. Вывод и возврат

Оценить каждый адрес отдельно и только с успешным VPN-контролем того же раунда.
VPN ok + zapret2 TLS timeout — расхождение TLS. HTTP-код означает, что дошло до HTTP.
IP/срок подписанного URL может объяснять HTTP-отказ, но не TLS timeout до отправки запроса.
Если оба пути неудачны, вывод по обходу для этой пары неопределённый.
Счётчики rawsend и DROP подтверждают действия на шлюзе, не результат на проводе/сервере.
Ни положительная страница, ни comparison_done не подтверждают видео и качество просмотра.

После любого исхода исходный config.toml должен быть восстановлен байт-в-байт с правами.
Нужны off, route=0, queue=0, lease=0, worker_pid отсутствует, capture_on=1, xray_same=1,
protected_same=1, rollback_ok, HEALTHY и отсутствие новых FAIL в diag --no-net.
Диагностический код оставить установленным в off. Если возврат не подтверждён — STOP,
сообщить владельцу, сохранить диагностику приватно. Новые стратегии не пробовать.
Отчёт на одну страницу: `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-trace-ДАТА.md`.
Записать CODE, selftest, тесты, по 4 PROBE и TRACE каждого выполненного раунда, пропуски с
причинами, CHECK до/после, rollback и вывод по каждой паре. Без сырых журналов, адресов,
доменов, идентификаторов процессов/запусков или серверов. NOT_RUN не заменять на PASS.
