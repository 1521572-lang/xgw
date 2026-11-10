# ThinkCentre: дополнительный выход zapret2 — первая приёмка

Исполнитель — GLM-5.3-Flash. Одно изменение, ASSUMPTIONS п. 355, версия остаётся 0.2.0.
Код и помощник зафиксированы в CODE ниже; контрольная сумма сверена с этим коммитом.
База разработки — 059258a; установленная база ожидается 49f0440.
youtube-sign уже выполнен: sign_matches. Признак в данном коде не меняется.

Цель: включение только выбранных доменов, сохранение остальных путей, проверка отказа/возврата.
HTTP 2xx не доказывает воспроизведение или победу над ТСПУ. Невидимость не заявляется.
Режим раскрывает сайтам домашний IP. Никакого полного туннеля, изменения подписок или ручного выбора.
Скачивание/установка nfqws2 и включение прямого режима требуют отдельного согласия владельца.
Машинное зрение по окну не кликает. Подписку вводит только владелец. DEGRADED — не «обычная волна».
Не выводить конфиги, reality.json, URL, домены, адреса, серверы, теги, SNI, short_id и снимки окна.
Приватные журналы и резервные копии — только под umask 077; в отчёт лишь числа и признаки.

## 1. Проверка исходников

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)" || exit 1
git fetch origin freepool
CODE=e3c8068ed3962007ec0007538e31c60f52189270
BASE=059258a4f232c958ae235b2cc9eda92892940cbb
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2.XXXXXXXX")
TARGET="$D/new"; PREV="$D/base"
git worktree add --detach "$TARGET" "$CODE"
git worktree add --detach "$PREV" "$BASE"
H="$TARGET/docs/helpers/zapret2_check.py"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE"
printf '%s  %s\n' 'ad5374912cb59bd669f806eb0b993c1e48ebaf8c8ee9d8e0f813332ea7e980e4' "$H" | sha256sum -c -
```

Ожидается OK. Любое несовпадение — STOP до установки. Работать только из этих worktree.
Не брать новый произвольный HEAD. Никаких коммитов/push в этом ТЗ без разрешения владельца.

## 2. До установки

```bash
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Записать CHECK и OK baseline, числа OK/WARN/FAIL diag, режим пула, версию установленного кода.
Если путь перехвата не on, Xray не работает, есть неизвестная правка или активный zapret2 — STOP.
Сначала объяснить расхождение, не продолжать «для проверки».

## 3. Минимальные тесты

На машине, без установки пакетов:
```bash
(cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_zapret2.py tests/test_config.py tests/test_generator.py tests/test_diff.py tests/test_nft.py)
(cd "$TARGET" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_daemon.py -k 'zapret2 or media or youtube')
```

Новый FAIL — STOP. Старое падение сверить тем же тестом на PREV и явно записать BASELINE_FAIL.
Полный набор не запускать. Пакетов нет — NOT_RUN tools, согласие на их установку отдельно.

## 4. Установка только кода XGW

Показать владельцу перечень ниже и получить согласие на замену файлов/перезапуск только xgw.service.
nfqws2 на этом шаге не скачивается. config.toml, WAN, LAN, Tailscale, пул и ядра не менять.
Сначала сравнить каждый существующий файл /opt/xgw/lib/xgw/P с PREV/src/xgw/P через cmp.
zapret2.py — новый: установленного файла ещё не должно быть. Несовпадение — STOP installed_differs.

Перечень P: config.py, daemon.py, diag.py, generator/builder.py, generator/diff.py,
net/nft.py, watch/status.py, zapret2.py. Только эти восемь файлов.
Скопировать /opt/xgw/lib/xgw целиком в приватную резервную копию "$D/lib-before";
config.toml — в "$D/config-before", права 0600. Проверить копии cmp, ничего не печатая.
Проверить синтаксис новых файлов через compile() без исполнения импортов.
Остановить только xgw.service; заменить восемь файлов из TARGET/src/xgw с правами 0644 root:root;
запустить xgw.service. Xray и sing-box не перезапускать. Остановленный демон не оставлять без запуска.
Ошибка копирования — вернуть файлы из резервной копии, убрать только новый zapret2.py, запустить демон.

Проверить status и diag --no-net. Режим должен быть off, старый VPN работать, новых FAIL не должно быть.
Наблюдать 5 минут; helper inspect сравнивает сохранённые настройки и PID Xray:
```bash
sudo python3 -I "$H" inspect --state "$D/before.json"
```

Ожидаются capture_on=1, route=0, xray_same=1, protected_same=1. Иначе STOP и возврат кода.

## 5. Подготовка zapret2 и согласие на прямой выход

Если бинарника/Lua нет: предложить владельцу конкретный официальный выпуск bol-van/zapret2,
точный URL архива, архитектуру и место /opt/zapret2. До скачивания получить отдельное согласие.
Зафиксировать release/commit и SHA-256 приватно; не смешивать бинарник и Lua разных выпусков.
Не запускать install_easy, общий unit zapret2, blockcheck или правку sysctl/firewall.
Если нужны зависимости — показать список до установки. Отказ/нет согласия: INSTALL_ONLY, шаг 8.
Подготовить nfqws2 и два Lua-файла как в docs/ZAPRET2.md, с root ownership и без group/other write.
Проверить --version и свободные очередь 200 / порт 19999. Чужие процессы не останавливать.

Получить согласие на 20 минут выбранных доменов напрямую, до 256 МиБ проб и отдельный просмотр
владельцем до 500 МиБ. Владелец приватно задаёт HTTPS-страницу YouTube и рабочий HTTPS-файл видеосети
в probe_urls; не подставлять адрес файла Google или адрес вне настроек. Ссылки в отчёт не идут.
Нет двух пригодных адресов — NOT_RUN probe_urls, сохранить off и перейти к шагу 8.
Добавить только [zapret2] по примеру docs/ZAPRET2.md, mode=selective, strategy=multisplit.
Настройки media/best и признак youtube-sign не трогать. Сохранить копию config.toml до правки.

## 6. Проверка режима и отказа

```bash
sudo python3 -I "$H" watch --state "$D/before.json" --seconds 180
```

Возможны preparing → active либо fallback с указанной причиной. Активный режим: route=1, queue=1,
lease=1, xray_same=1, protected_same=1, capture_on=1. Проверить, что обычный VPN продолжает работать.
Если active не получен: записать reason из status только как код; не угадывать причину ТСПУ.
probe_failed — тест доступности не пройден; dependency_missing/runtime_failed — ошибка подготовки.
NOT_RUN direct_unavailable — включить off и к шагу 8. Не менять стратегии вслепую в этом прогоне.

Если active: владелец открывает два обычных ролика на клиенте LAN и на самом шлюзе; записать
played/refuse/unmeasured, без URL. Плавность отдельно со слов владельца. Без просмотра NOT_RUN video.
До/после просмотра снять CHECK: прирост zapret_bytes больше 2 МиБ при неизменном PID подтверждает
клиентский трафик выхода (пробы дают лишь до 256 КиБ тела за круг). Иначе NOT_RUN route_bytes.
Отсутствие окна/клиента — NOT_RUN соответствующей части, а не отрицательный результат.
Проверить ещё один обычный VPN-сайт через выбранный владельцем адрес из настроек.

С согласия на этот сценарий остановить только xgw-zapret2.service и наблюдать до 180 секунд:
```bash
sudo systemctl stop xgw-zapret2.service
sudo python3 -I "$H" watch --state "$D/before.json" --seconds 180
```

Ожидается fallback, route=0, lease=0, queue=0, xray_same=1. Новые запросы — прежним VPN-маршрутом.
Старые соединения не обязаны выжить; открыть страницу заново. blocked — FAIL возврата, не PASS.
После retry_seconds демон сам заново поднимает очередь и проверяет путь; разрешить это в пределах
20 минут и зафиксировать active или fallback. Самостоятельно nft-правила не удалять.

## 7. Выключение и откат

Вернуть config.toml из приватной копии байт в байт, сохранив прежние owner/mode. Ждать до 180 секунд.
```bash
sudo python3 -I "$H" finish --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Нужны RESULT rollback_ok, route=0, worker_pid=0 (проверить приватно), lease=0, protected_same=1.
Если остался blocked/маршрут: STOP, сохранить новый код, прямой путь закрыт; сообщить владельцу.
Не откатывать модуль, пока его правило не снято. Не снимать защитные таблицы, не перезагружать машину.
После подтверждённого выключения при необходимости вернуть восемь файлов из lib-before,
удалить только добавленный zapret2.py и перезапустить лишь xgw.service. Снова status и diag.
Подготовленный внешний zapret2 без разрешения не удалять и не включать постоянно.

## 8. Отчёт на одну страницу

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-ДАТА.md. Код, дата, согласованные действия;
до/после: on, PID Xray сохранён или нет, OK/WARN/FAIL diag, защищённые настройки совпали или нет.
Тесты: PASS/BASELINE_FAIL/NOT_RUN. CHECK и состояния, причина fallback только кодом.
Видео LAN/шлюз отдельно; отказ обработчика; повторная проверка; подтверждённое выключение.
Итог PASS только при active, проверенном возврате и чистом выключении; видео может быть NOT_RUN.
INSTALL_ONLY/PARTIAL/NOT_RUN честно отделить от FAIL. Эффективность против ТСПУ без видео не заявлять.
Не публиковать секреты, приватные журналы, суммы локальных конфигов, имена/адреса серверов.
