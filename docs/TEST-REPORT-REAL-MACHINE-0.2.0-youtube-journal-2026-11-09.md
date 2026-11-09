# ThinkCentre: журнал прогона youtube-route-r2 — 2026-11-09

- Дата; CODE e422b86 (только помощник); сумма OK — **да**.
- helper_rc=0; journal_lines=1102, first=11:15:50, last=11:52:56 — окно прогона youtube-route-r2
  (установка 11:15:53, окно наблюдения) покрыто.
- Вывод помощника целиком (блоком, без правок):

```
INFO journal_lines=1102 first=11:15:50 last=11:52:56
OK journal_covers
INFO events build_stale=3 build_started=13 generation_not_ready=10 generation_prepare_failed=13 media_chosen=1 media_common=1
INFO video_events generation_not_ready=6
INFO details bridge_request_failed=13 bridges=5/5=13 kinds=tls:5=13
T 11:16:07 build_started
T 11:17:17 media_chosen
T 11:17:52 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:17:56 build_stale
T 11:17:56 build_started
T 11:19:31 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:19:36 generation_not_ready video
T 11:22:26 build_started
T 11:23:46 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:23:56 generation_not_ready video
T 11:24:12 build_started
T 11:25:31 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:25:33 build_stale
T 11:25:33 build_started
T 11:27:13 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:27:24 generation_not_ready
T 11:27:31 build_started
T 11:28:50 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:28:51 generation_not_ready video
T 11:30:55 build_started
T 11:32:15 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:32:16 generation_not_ready
T 11:32:39 build_started
T 11:34:19 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:34:20 generation_not_ready video
T 11:37:42 build_started
T 11:39:04 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:39:05 generation_not_ready video
T 11:42:48 build_started
T 11:44:09 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:44:10 generation_not_ready video
T 11:46:00 build_started
T 11:47:20 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:47:21 generation_not_ready
T 11:48:01 build_started
T 11:49:42 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:49:59 media_common
T 11:50:01 build_stale
T 11:50:02 build_started
T 11:51:36 generation_prepare_failed bridge_request_failed bridges=5/5 kinds=tls:5
T 11:51:51 generation_not_ready
INFO timeline_rows=41 shown=41
helper_rc=0
```

- Метка `build_started` без `build_finished` и `build_stale` — переписана как есть (в выводе выше).
- Итог: **DONE (helper_rc=0)** — журнал прочитан, метки собраны; смысл меток не толковался, разбор —
  за разработчиком. На машине ничего не менялось (только чтение), код шлюза 059d4fc.
