# ThinkCentre: журнал прогона youtube-route-r2 — почему правило видео не применилось

Исполнитель — GLM-5.3-Flash. В прогоне 2026-11-09 (отчёт youtube-route-r2) режим `best` выбрал выход
для видео, но правило видео не появилось в применённом конфиге, и режим ушёл в `degraded`. Причину
по отчёту установить нельзя. Здесь один помощник читает журнал демона за 2026-11-09 11:15–11:53 и
сводит строки к готовым меткам.

**Только чтение.** Режим `best` не включается, установка не нужна, согласие владельца не требуется.

Можно: только команды этого ТЗ. **Машинное зрение на шлюзе по окну не кликает.**
Нельзя: менять config.toml, подписки, пул, ручной выбор, «Обновить», замеры, WAN, LAN, Tailscale и
сетевые правила; перезапускать службы; `xgw net down`, перезагрузка, `--force`. Журнал не очищать и
не поворачивать.

В отчёт — только вывод помощника: метки и числа. Без исходных строк журнала, имён серверов и
подписок, адресов, доменов, тегов, SNI, short_id. Журнал руками не читать и в отчёт не копировать.

## 1. Помощник и его сумма

```bash
cd ~/xgw && test -z "$(git status --porcelain)" && git switch freepool &&
git fetch origin && git merge --ff-only origin/freepool
CODE=e422b8671d3715992cb96eb74b1c4fe72cc65154
D=$(mktemp -d "$HOME/xgw-journal.XXXXXXXX")
H="$D/youtube_journal_check.py"
git show "$CODE:docs/helpers/youtube_journal_check.py" >"$H" &&
printf '%s  %s\n' '2f7a0c3bece1ed461b78a928465366687bd26737a649e315b5d2d9909b0e3311' "$H" | sha256sum -c -
```

Ожидается `OK`. Иначе — STOP, сообщить владельцу. Путь D — приватно.

## 2. Чтение журнала

```bash
umask 077
sudo python3 -I "$H" 2>&1 | tee "$D/out.txt"
```

Норма: `INFO journal_lines=… first=… last=…`, `OK journal_covers`, `INFO events …`, `INFO video_events
…`, `INFO details …`, строки `T …`, `INFO timeline_rows=… shown=…`, `helper_rc=0`.

- `NOT_RUN journal_gone`, `helper_rc=4` — записи окна уже вытеснены: итог NOT_RUN, не FAIL. Повторять
  прогон `best` не надо, к шагу 3;
- `STOP …`, `helper_rc=3` — записать строку как есть, итог FAIL, к шагу 3.

Пустые `INFO video_events` или `INFO details` — допустимый результат, а не ошибка. Метку `build_started`
без `build_finished` и `build_stale` — переписать как есть. Смысл меток не толковать и причину не
придумывать: разбор делает разработчик.

## 3. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-journal-ДАТА.md` в freepool, одна страница, без пути D.
`git diff --cached --name-only` — только этот файл, `git diff --cached --check`, затем `git pull
--rebase` и обычный push без force.

````text
Дата; CODE; сумма OK (да/нет):
helper_rc; journal_lines, first, last:
Вывод помощника целиком (блоком, без правок):
```
…
```
Итог: DONE (helper_rc=0) / NOT_RUN (journal_gone) / FAIL (STOP …):
````
