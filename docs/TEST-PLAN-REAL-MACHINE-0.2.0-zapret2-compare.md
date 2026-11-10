# ThinkCentre. Сравнение проб через VPN и zapret2

Исполнитель GLM-5.3-Flash. База по отчёту `30ef982`: код `e3c8068`, шлюз HEALTHY, zapret2 off,
`nfqws2` v1.0.7 установлен. В первой приёмке `multisplit` дал `probe_failed` и `rollback_ok`.
Цель — найти этап расхождения, отправив по обоим путям одинаковый запрос к каждому адресу.
Режим `compare` делает только служебные запросы. Пользовательский маршрут остаётся прежним.

Проверять одну стратегию `multisplit`. Никаких новых пакетов, замены ядер, смены WAN, LAN,
Tailscale, пула, подписок, ручного выхода и пользовательских маршрутов. Адреса проб вводит
владелец приватно. В отчёте только числа и перечисленные ниже коды. Экраном не управлять.

## 1. Исходники и состояние

После публикации использовать закреплённый код `CODE` и проверить сумму помощника.

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=c1ec52c945a1d9f1b66264b5e5aaf688a36038ef
BASE=e3c8068ed3962007ec0007538e31c60f52189270
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-compare.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
test "$(git -C "$D/new" rev-parse HEAD)" = "$CODE"
H="$D/new/docs/helpers/zapret2_check.py"
printf '%s  %s\n' '8dec42e25e629efe8489ee1f8f375649fe4f4b474ed588dbc423a9093888d18b' "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидаются `OK baseline`, `capture_on=1`, `route=0`, `queue=0`, `lease=0`, HEALTHY, версия
nfqws2 v1.0.7. При расхождении остановиться и записать причину. Артефакты держать приватно.

## 2. Проверка и установка пяти файлов

```bash
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_zapret2.py tests/test_checks.py tests/test_config.py tests/test_generator.py tests/test_nft.py)
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_daemon.py -k zapret2)
```

Пакетов нет — `NOT_RUN tools`. Новое падение — остановиться. Старое сверить тем же тестом
на базе. Перед заменой пяти файлов получить согласие на изменение установленного XGW.
Сверить через `cmp` каждый установленный `/opt/xgw/lib/xgw/P` с `$D/base/src/xgw/P`.
Перечень `P` — `config.py`, `daemon.py`, `net/nft.py`, `watch/checks.py`, `zapret2.py`.
Сохранить приватные копии файлов с владельцами и правами. Отдельно сохранить байт-в-байт
`/etc/xgw/config.toml`, включая владельца и права. Проверить Python-синтаксис новых файлов.
Остановить только `xgw.service`, заменить пять файлов из `$D/new/src/xgw`, запустить
`xgw.service`. При ошибке вернуть резервные файлы и запустить демон. Xray и sing-box
продолжают работать. Сверить `capture_on=1`, `route=0`, `xray_same=1`, `protected_same=1`.

## 3. Один раунд

Использовать только ранее разрешённые пробы и свежий адрес видеосети. Владелец вводит два
`probe_urls` в приватный конфиг, в порядке `1` страница и `2` файл видеосети. Применить
`[zapret2] mode="compare"`, `strategy="multisplit"`, очередь 200 и порт 19999 как в первой
приёмке. Остальные настройки взять из сохранённого конфига. Проверить, что mode именно
`compare` и предупреждений при чтении нет. Во время раунда не менять конфиг и не перезапускать
службы. В сумме до четырёх GET по 8 с, с одинаковым User-Agent и порогом 16 КиБ.

```bash
sudo python3 -I "$H" compare --state "$D/before.json" --seconds 180 || echo "comparison_rc=$?"
```

`RESULT comparison_done` означает, что записаны четыре результата и служебный путь закрыт.
У каждой строки `PROBE` есть номер, путь, этап, вид отказа, HTTP-код сервера, код отказа CONNECT,
байты тела и итог. Код `0` означает, что соответствующий код не записан. При `comparison_incomplete`
сохранить доступные строки и код причины. При `STOP comparison_guard` сразу восстановить конфиг.

Сопоставить результаты отдельно для пробы 1 и 2. Если VPN проходит, а zapret2 даёт `tls/timeout`,
расхождение на этапе TLS. Если пришёл HTTP-код, соединение дошло до HTTP. Для `403` от файла
видеосети учитывать, что подписанный URL может быть привязан к IP или сроку действия.
Если оба пути падают, причина для zapret2 остаётся неопределённой. Сравнение HTTPS не измеряет видео.

## 4. Возврат и отчёт

После любого исхода восстановить исходный `config.toml` байт-в-байт с прежними владельцем
и правами. Дождаться `state=off`. Выполнить `finish` и повторить `diag --no-net`.
Нужны `rollback_ok`, `route=0`, `lease=0`, `queue=0`, `capture_on=1`, неизменный PID Xray,
исходные защищённые настройки и отсутствие новых FAIL. Если служебный путь остался, сообщить
владельцу и сохранить диагностику. Установленный диагностический код оставить выключенным.

В `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-compare-ДАТА.md` записать коммит, тесты, четыре
строки `PROBE` либо причину неполного сравнения, `CHECK` до и после и результат возврата.
Строки с URL, заголовками, выводом TLS и журналами ядра не публиковать. Стратегию по этому ТЗ
не переключать. Пригодность zapret2 оценивается по каждой паре отдельно.
