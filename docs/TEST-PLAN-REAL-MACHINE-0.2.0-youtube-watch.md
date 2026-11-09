# ThinkCentre: играют ли настоящие ссылки на ролики YouTube

Исполнитель — GLM-5.3-Flash. Код шлюза не меняется, установки и включения режимов нет. Прежняя проверка
открывала служебную страницу со встроенным плеером. Эта открывает обычные ссылки `youtube.com/watch`
в Firefox без окна: сначала обычным путём через шлюз, затем через несколько отдельных серверов, причём
страница и видео каждый раз идут через один сервер. Внешние устройства не нужны.

Разрешения владельца даны 09.11 только для этой проверки: запросы к адресам YouTube вне настроек XGW и
запуск уже установленного Firefox без окна. Спрашивать отдельно не нужно. Ничего не устанавливается.
Трафик через отдельные серверы — только безлимитные, до 500 МБ, всего до 30 минут.

Что проверяется: играет ли ролик и как именно отказывает, если не играет. Что не проверяется и не
заявляется: качество и плавность, приложения YouTube на телефонах, режим `best` как таковой.
Невидимость для ТСПУ не заявляется. Просьбу YouTube подтвердить, что это не робот, помощник не проходит,
а только записывает. На запросе о cookie он выбирает отказ от необязательных.

Можно: терминал, `xgw status`, `xgw diag --no-net`. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: config.toml, подписки, пул, ручной выбор (ни ставить, ни снимать), «Обновить», замеры, WAN, LAN,
Tailscale и сетевые правила; перезапуск демона, `xgw net down`, перезагрузка, `--force`, установка
программ. В отчёт — только числа, признаки и строки помощника: без ссылок на видео, адресов, имён
серверов и подписок, доменов, тегов, SNI, short_id, сумм файлов и снимков экрана.

## 1. Код и сумма помощника

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=274404543f15da48684f20788c6f1ea190ebfb9a
BASE=49f0440cda315b9b66eff7f33c72ca3ab76058e9
D=$(mktemp -d "$HOME/xgw-watch.XXXXXXXX")
TARGET="$D/new"; H="$TARGET/docs/helpers/youtube_watch_check.py"
git worktree add --detach "$TARGET" "$CODE" &&
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE" &&
printf '%s  %s\n' 'aabb3b9481040d1ff23cecd0f8ba745a56b6ed2d927e01c7f808599f1cf2cfbc' "$H" | sha256sum -c -
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

Идёт до 30 минут, второй раз не запускать, Firefox вручную не открывать. Норма — строки в таком порядке:
`OK on`, `OK https`, `OK user`, `INFO servers_chosen=…`, строки `TRIAL …` (сначала `path=normal`, затем
`path=S1` и далее), `INFO normal_played=…`, `OK on`, `OK https`, затем `RESULT …` и `helper_rc=0`.

Все строки `TRIAL`, `INFO` и `RESULT` переписать в отчёт как есть. Значения `S1`, `S2` — это номера
серверов в прогоне, имён в них нет.

- `RESULT all_accept` — ролики сыграли через все проверенные серверы. Итог DONE.
- `RESULT some_accept` — через часть серверов. Итог DONE.
- `RESULT none_accept` — ни через один, при этом обычным путём сыграло. Итог DONE.
- `NOT_RUN no_browser`, `NOT_RUN no_playback` или `NOT_RUN few_servers`, `helper_rc=4` — сравнить не
  удалось. Итог NOT_RUN, не FAIL. Повторять не надо.
- `STOP on` / `STOP https` — сразу владельцу, ничего не чинить.
- `STOP` с другим словом, `helper_rc=3` — записать слово, итог PARTIAL.

Что значат результаты в `TRIAL`: `played` — ролик шёл; `bot` — YouTube просит подтвердить, что это не
робот; `sign_in` — просит войти; `unavailable` — ролик недоступен; `player_error` — другая ошибка плеера;
`media_err_N` — браузер не смог декодировать видео; `consent` — застряло на запросе о cookie; `ad` —
окно кончилось на рекламе; `stuck` — видео есть, но не идёт; `no_video` — плеера нет; `no_browser` —
Firefox не запустился. Причины не придумывать.

## 4. Конечное состояние и отчёт

```bash
sudo python3 -I "$H" health; sudo xgw diag --no-net >"$D/diag-after"; echo "diag_rc=$?"
```

Норма: `OK on`, `OK https`, новых FAIL нет; режим пула тот же.
DEGRADED из `Состояние:` не называть «обычной волной» и причину не придумывать.

Отчёт — `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-watch-ДАТА.md` в freepool, одна страница, без пути D.
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
