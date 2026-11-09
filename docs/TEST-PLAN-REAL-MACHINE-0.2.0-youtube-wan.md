# ThinkCentre: играет ли YouTube напрямую, без сервера VPN

Исполнитель — GLM-5.3-Flash. Код шлюза не меняется, ничего не устанавливается, настройки не правятся.
Помощник запускает уже установленный Firefox без окна и открывает обычные ссылки `youtube.com/watch` по
четырём путям: обычным через шлюз, напрямую с домашнего адреса и напрямую с двумя видами дробления
ClientHello, которые XGW уже умеет. Для прямых путей он поднимает временный Xray: тот слушает только
127.0.0.1, работает лишь во время проверки и удаляется вместе со своим файлом. Внешние устройства не нужны.

Разрешение владельца дано 09.11 только для этой проверки: запросы к YouTube вне настроек XGW, запуск уже
установленного Firefox без окна и запросы к YouTube напрямую с домашнего адреса. Спрашивать отдельно не
нужно. Всего до 45 минут; видео небольшого размера, расход ориентировочно несколько сотен мегабайт.

Что проверяется: играет ли ролик, сколько секунд ждали старта, сколько раз плеер ждал данные. Что не
проверяется и не заявляется: качество видео, скорость канала, приложения YouTube на телефонах и работа
программы `zapret`. Невидимость для ТСПУ не заявляется. Просьбу YouTube подтвердить, что это не робот,
помощник не проходит, а только записывает. На запросе о cookie он выбирает отказ от необязательных.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: config.toml, подписки, пул, ручной выбор (ни ставить, ни снимать), «Обновить», замеры, WAN, LAN,
Tailscale и сетевые правила; перезапуск демона, `xgw net down`, перезагрузка, `--force`, установка
программ. В отчёт — только числа, признаки и строки помощника: без ссылок на видео, адресов, имён
серверов и подписок, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=831dd5ff54fc9cf13cf18da2fa3d05b7cdd49e0b
BASE=49f0440cda315b9b66eff7f33c72ca3ab76058e9
D=$(mktemp -d "$HOME/xgw-wan.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/youtube_wan_check.py"
git worktree add --detach "$TARGET" "$CODE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' '527204bc9f7f6cead4a754811f6455eb0f55750c454bb8252c54e2a98c9fd2e3' "$H" | sha256sum -c -
git -C "$TARGET" diff --name-only "$BASE" "$CODE" -- src packaging | wc -l
```

Ожидается `OK` и `0`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Исходное состояние (только чтение)

```bash
umask 077
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-before"; echo "diag_rc=$?"
```

Ожидаются `OK on`, `OK https`, `helper_rc=0`. Записать числа OK/WARN/FAIL diag и режим пула. Иначе —
STOP, сообщить владельцу, проверку не запускать.

## 3. Проверка

```bash
sudo python3 -I "$H" run "$D" 2>&1 | tee "$D/run.txt"
```

Идёт до 45 минут, второй раз не запускать, Firefox вручную не открывать. Норма — строки в таком порядке:
`OK on`, `OK https`, `OK user`, `OK temp_xray`, строки `TRIAL …` (пути `normal`, `direct`, `fragment`,
`split`), `INFO normal=… direct=… fragment=… split=… minutes=…`, `OK on`, `OK https`, затем `RESULT …` и
`helper_rc=0`. Все строки `TRIAL`, `INFO` и `RESULT` переписать в отчёт как есть.

- `RESULT direct_ok` — напрямую сыграло минимум 3 ролика из 4. Итог DONE.
- `RESULT fragment_ok` — напрямую без дробления нет, с одним из видов дробления минимум 3 из 4. Итог DONE.
- `RESULT none_ok` — ни один прямой путь не дал 3 из 4. Итог DONE.
- `NOT_RUN no_browser`, `NOT_RUN no_xray` или `NOT_RUN no_playback` (обычным путём сыграло меньше двух
  роликов), `helper_rc=4` — сравнить не удалось. Итог NOT_RUN, не FAIL. Повторять не надо.
- `STOP on` / `STOP https` — сразу владельцу, ничего не чинить.
- `STOP temp_xray` или `STOP` с другим словом, `helper_rc=3` — записать слово, итог PARTIAL.

Что значат значения в `TRIAL`. `start_s` — секунд до начала видео (`-` — не началось), `stalls` — сколько
раз при опросе плеер ждал данные. `result`: `played` — сыграло 20 секунд ролика; `bot` — YouTube просит
подтвердить, что это не робот; `sign_in` — просит войти; `unavailable` — ролик недоступен; `player_error`
— другая ошибка плеера; `media_err_N` — браузер не смог декодировать видео; `consent_page` — осталась
страница запроса о cookie; `consent_dialog` — окно запроса поверх плеера, а видео не пошло; `ad` — время
кончилось на рекламе; `stuck` — видео есть, но не идёт; `no_video` — плеера нет; `no_browser` — Firefox не
запустился. Причины не придумывать.

## 4. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.
DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-wan-ДАТА.md` в freepool, одна страница, без пути D.
`git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

```text
Дата; CODE; сумма OK; файлов шлюза изменено (ожидается 0):
До: helper_rc; on/HTTPS; diag (OK/WARN/FAIL); режим пула:
Проверка: helper_rc; все строки TRIAL и INFO как есть:
RESULT или NOT_RUN как есть:
Конечное: on/HTTPS; diag после; режим пула без изменений (да/нет):
Итог: DONE / NOT_RUN / PARTIAL; первый непройденный шаг; что стоит на машине:
```
