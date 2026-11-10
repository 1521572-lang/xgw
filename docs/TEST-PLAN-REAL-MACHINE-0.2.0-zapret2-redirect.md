# ThinkCentre. Конечный адрес файла через VPN и multidisorder

Исполнитель GLM-5.3-Flash. База — отчёт 2b522be, установленный код 14c729b,
nfqws2 v1.0.7. HEALTHY, diag 33/0/0, zapret2 off. Страница через multidisorder дала 200,
для файла VPN дал 302 в обоих раундах. Причина редиректа и пригодность файла неизвестны.
Цель — получить тело файла через VPN и запросить тот же конечный адрес через zapret2.
Использовать закреплённый ниже CODE и проверить сумму помощника перед запуском.
Новых пакетов, стратегий, захвата пакетов и полного debug не запускать. WAN, LAN, Tailscale,
пул, подписки и ручной выбор не менять. Адреса только из настроек владельца, ввод приватно.
Экраном не управлять. Только mode=compare, selective не включать.

## 1. Подготовка

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=c5fbf9fefc0e64ad28bed06f4a4fb24feee11fb6
BASE=14c729bfc4d018edf6b0665871a7568c2d1925e4
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-redirect.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
test "$(git -C "$D/new" rev-parse HEAD)" = "$CODE"
H="$D/new/docs/helpers/zapret2_check.py"
printf '%s  %s\n' '402849b1de6656b18640661960228da1c56e7f2b31a94e04ac6ecbfe37cd9c24' "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны OK baseline, state=off, route=0, queue=0, lease=0, capture_on=1, HEALTHY.
При расхождении остановиться. Приватные артефакты не публиковать.

## 2. Установка одного файла

```bash
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_zapret2.py tests/test_zapret2_redirect.py tests/test_zapret2_trace.py)
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_daemon.py -k zapret2)
```

Нет инструментов — NOT_RUN tools, ничего не устанавливать. Новое падение — STOP.
Перед заменой получить согласие владельца. Сверить cmp установленный
`/opt/xgw/lib/xgw/zapret2.py` с `$D/base/src/xgw/zapret2.py`; daemon.py и zapret2_trace.py
тоже должны совпадать с базой. При расхождении STOP. Сохранить zapret2.py и config.toml
байт-в-байт с владельцем и правами. Проверить синтаксис нового zapret2.py.
Остановить только xgw.service, заменить zapret2.py из CODE, сохранив права, запустить демон.
Xray и sing-box не перезапускать. Сверить capture_on=1, route=0, xray_same=1, protected_same=1.
При ошибке вернуть сохранённый файл и конфиг, запустить демон, раунд не начинать.

## 3. Один раунд

Владелец задаёт ранее разрешённые probe_urls: 1 — страница, 2 — свежий адрес файла видеосети,
полученный ранее согласованным способом. Порядок не менять. Нужен бюджет хотя бы 2 МиБ.
Применить mode="compare", strategy="multidisorder", очередь 200, порт 19999.
Остальное оставить как в сохранённом конфиге. Предупреждений чтения быть не должно.
Во время раунда конфиг и службы не трогать. До 8 GET, VPN-цепочка до 8 с, прямой GET до 8 с.
VPN допускает два перехода в разрешённых доменах; zapret2 запрашивает тот же конечный адрес.

```bash
sudo python3 -I "$H" compare --state "$D/before.json" --seconds 180 || echo "comparison_rc=$?"
```

Сохранить 4 PROBE, TRACE и RESULT. redirects — число переходов VPN; redirect=followed означает
выполненный переход, blocked/loop/limit — границу проверки. Прямой запрос не следует Location.
comparison_done подтверждает завершение, не успешную загрузку. При STOP восстановить конфиг.

## 4. Возврат и вывод

После любого исхода восстановить config.toml байт-в-байт с владельцем и правами.
Дать демону перечитать его, дождаться off; ранний finish не считать окончательным откатом.

```bash
sudo python3 -I "$H" watch --state "$D/before.json" --seconds 120
sudo python3 -I "$H" finish --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны rollback_ok, off, route=0, queue=0, lease=0, worker_pid отсутствует, capture_on=1,
xray_same=1, protected_same=1, HEALTHY и отсутствие новых FAIL. Если возврат не подтверждён,
STOP и сообщить владельцу; автоматических новых раундов нет. Код оставить установленным в off.
Оценка по каждой паре отдельно: VPN ok и zapret2 ok — начало тела доступно по обоим путям;
VPN ok и zapret2 TLS timeout — расхождение TLS; HTTP-отказ — дошло до HTTP, причина неизвестна.
VPN не ok, в том числе 302/blocked/loop/limit — пригодный контроль не получен, вывод неопределённый.
302 сам по себе не доказывает истечение ссылки. Общий TRACE нельзя приписывать одному адресу.
Видео и качество просмотра не измерены. Даже при успехе обеих пар selective не включать.
Отчёт на страницу: `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-redirect-ДАТА.md`.
Записать CODE, тесты, 4 PROBE, TRACE, CHECK до/после, rollback и выводы. Без URL, Location,
доменов, имён серверов и сырых журналов. Частичные результаты и NOT_RUN обозначать явно.
