# ThinkCentre — 300 секунд 720p после перемотки через штатный VPN

**Ubuntu 24.04 LTS, Read-Only.** Flash сама запускает готовое задание и
публикует один обезличенный отчёт при любом исходе. Если недоступны
терминал, панель или sudo, запроси доступ и выполни команды сама.
В этом проходе используется установленный шлюз в off/off. Код из
checkout служит измерительным инструментом. Снимки выполняет модуль
из установленного пакета. Запуск не меняет настройки и службы XGW.

В предыдущем проходе 900 с видео прошли в 720p с прогрессом 99,66% и
одной секундной остановкой. Снимки Xray запустились поздно, поэтому
маршрут сокетов плеера остался неподтверждённым. Здесь проводим одно
новое окно после перемотки за край буфера, со снимком до запуска mpv.
[Отчёт о 900 секундах](../reports/2026-11-21T105249Z_selective-vpn-playback-900.md)

## 1. Запуск

Запусти весь блок в одном вызове Bash, как обычный пользователь из
checkout XGW с доступом к штатной панели. Если pytest установлен
в отдельном окружении, перед блоком экспортируй абсолютный путь
к интерпретатору в `XGW_TEST_PYTHON`. Проверь `sudo -n true`. При
необходимости подтверди доступ через `sudo -v` в интерактивном терминале.
Запиши версию ОС, ядра, mpv, yt-dlp и curl.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
BR=integration/zapret2-batch1
CODE=a77ef953404e87f3c33736b41e1b81a169b7bf42
REPO=$(git rev-parse --show-toplevel)
WORK=$(mktemp -d "$HOME/xgw-vpn-seek-source.XXXXXXXX")
SRC="$WORK/source"
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" worktree add --detach "$SRC" "$CODE"
trap 'git -C "$REPO" worktree remove "$SRC" && rmdir -- "$WORK"' EXIT
bash "$SRC/docs/helpers/selective_vpn_seek.sh"
BASH
```

Инструмент выводит путь приватного каталога и коды этапов. При отказе
смотри соответствующие `.out` и `.err` в этом каталоге. Блок занимает
до 10 минут. Он проверяет доступ к панели, обе службы, действующий
HTTP-вход, HTTPS и хэши настроек. После успешного исходного контроля
проверки запускаются повторно даже при отказе resolve, снимка или плеера.
Если исходный контроль или первый снимок не прошёл, mpv не запускается.
Отметь этап и причину, оставь состояние шлюза как застал.

yt-dlp получает свежий формат через штатный HTTP-вход. mpv использует
обычный маршрут клиента шлюза. После выхода за край буфера скрипт
считает 300 с по позиции, высоте кадра и флагам mpv. Снимок после
старта берётся примерно через 150 с, чтение журнала ограничено этой
парой снимков и 5000 записями Xray. Записываются метрики, TCP-сокеты
плеера и ограниченный журнал. Предельное время процесса плеера 385 с
плюс 4 с на завершение.

## 2. Что записать в отчёт

| Вердикт | Условия и метрики |
|---|---|
| `WORKSPACE` | Точный SHA, ОС и версии, результат `play-unit`, статус каждого ненулевого этапа. Если этап недоступен, укажи точку отказа и ответ команды в обезличенном виде. |
| `PLAY_SEEK=PASS` | `play-seek.out` содержит `outcome=elapsed`, `seek_observed=true` и `acceptance.ok=true`. Запиши `seek.from`, `cached_until`, `target`, `landed` в секундах ролика. `landed` должен быть правее края буфера. Для полного окна пороги составляют 300 с, 720p ≥99% измеренного времени, прогресс ≥98%, сумма остановок ≤3 с, максимальная остановка ≤5 с и пропуски ≤5 с. Запиши все поля `acceptance`. |
| `FLOW_SEEK=VPN_CONFIRMED` | `flow-seek.out` содержит `state=observed`, минимум один сопоставленный поток, только группы `xray`/`sing-box`, пустой `unmatched` и `client_zapret2_rule=false`. Запиши число подходящих потоков и счётчики групп. Для частичного подтверждения укажи `PARTIAL` и причины из `unmatched`. При несопоставимых или неполных снимках укажи `INCONCLUSIVE` и причину. Пустой журнал и отсутствие подходящих сокетов укажи явно. |
| `CONTROL` | Начальный и конечный off/off fresh/matched, два HTTPS 200, одинаковый SHA настроек. Укажи результат сравнения без хэшей. |

Отдельно приведи `cache_min_seconds`, `cache_buffer_below_5s`,
`cache_read_median_Bps`, `bitrate_bps` и `cache_read_to_bitrate_ratio`.
При `line=THROTTLED` перечисли сработавшие условия старой оценки:
остановки, буфер <5 с, медиана чтения ниже битрейта. Источник
ограничения скорости в этом опыте не измеряется.

Для запущенного плеера, который не достиг порогов или не подтвердил
перемотку, запиши `PLAY_SEEK=FAIL`. Если старт плеера заблокирован,
укажи `PLAY_SEEK=NOT_RUN`. При точном совпадении с группой `other`
или `zapret2` укажи `FLOW_SEEK=UNEXPECTED_ROUTE` и счётчики групп.

Положительный `FLOW_SEEK` подтверждает маршрут сопоставленных сокетов,
на которых вырос объём принятых байтов после перемотки в пределах пары
снимков. Соединение могло быть открыто до перемотки. При смене эпохи
или конфигурации Xray сохраняй вердикт несопоставимого окна. Два вердикта
качества и маршрута публикуются отдельно.

## 3. Публикация

После завершения подготовь отчёт в приватном каталоге. В отчёт идут
обезличенные метрики и итоговое состояние. Исключи URL, IP, порты, PID,
хэши настроек и сырые журналы. Укажи абсолютный путь к подготовленному
отчёту в переменной `REPORT_SRC`, затем сама выполни весь блок из
checkout XGW. При частичном результате или блокере публикуй тем же
способом. Верни ссылку после подтверждения SHA в удалённой ветке.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-vpn-seek-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_selective-vpn-seek-300.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "Report ThinkCentre VPN playback after an uncached seek"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
BASH
```
