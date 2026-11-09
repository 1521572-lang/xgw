# ThinkCentre: вид отказа мостов sing-box и история сборок — 2026-11-09

- Дата; CODE 90dbf8b (только помощник); сумма OK — **да**.
- helper_rc=0; время работы помощника — 2 минуты (до 10 по ТЗ).
- Вывод помощника целиком (блоком, без правок):

```
INFO now=11-09_13:49
INFO generation active=blue pending=0 draining=0 api_dirty=0 switches_24h=5 last_switch_age_h=11.3 last_parts=['dns_hosts'] config_same=1
INFO candidate present=1 age_min=8 inbounds_active=168 inbounds_candidate=168 added=0 removed=0 changed_servers=21 parts=['server_settings', 'dns']
INFO bridges total=5 tested=5 inbounds_active=168
B1 role=spare letter=d found=1 in=mixed cred=1 type=hysteria2 net=tcp sec=tls detour=0 mux=0 addr=ip curl=97 px=reply_1 t=15.00 tcp=skip
B2 role=spare letter=d found=1 in=mixed cred=1 type=hysteria2 net=tcp sec=tls detour=0 mux=0 addr=ip curl=97 px=reply_1 t=15.00 tcp=skip
B3 role=spare letter=d found=1 in=mixed cred=1 type=hysteria2 net=tcp sec=tls detour=0 mux=0 addr=ip curl=97 px=reply_1 t=15.00 tcp=skip
B4 role=spare letter=d found=1 in=mixed cred=1 type=hysteria2 net=tcp sec=tls detour=0 mux=0 addr=ip curl=97 px=reply_1 t=15.00 tcp=skip
B5 role=spare letter=d found=1 in=mixed cred=1 type=hysteria2 net=tcp sec=tls detour=0 mux=0 addr=ip curl=97 px=reply_1 t=15.01 tcp=skip
LOG B1 timeout=1
LOG B2 timeout=1
LOG B3 timeout=1
LOG B4 timeout=1
LOG B5 timeout=1
LOG test_window_all timeout=5
LOG active_24h other=541 refused=1 timeout=110
LOG candidate_24h other=791 timeout=281
INFO journal_lines=181408 first=10-26_13:51 last=11-09_13:51
DAY 11-04 build_finished=19 build_started=22
DAY 11-05 build_finished=154 build_stale=18 build_started=174 generation_changed=10 generation_failed=1
DAY 11-06 build_finished=156 build_stale=41 build_started=198 generation_changed=42 generation_failed=2
DAY 11-07 build_finished=162 build_stale=27 build_started=189 generation_changed=20
DAY 11-08 build_finished=246 build_stale=21 build_started=275 generation_changed=5 generation_failed=7
DAY 11-09 build_finished=114 build_stale=37 build_started=187 generation_changed=1 generation_failed=59
INFO fail_kinds 0/0 - x1 | 5/5 tls 5 x59 | no_bridge_summary x9
INFO last build_finished=11-09_06:49 build_stale=11-09_13:41 build_started=11-09_13:41 generation_changed=11-09_02:32 generation_failed=11-09_13:43
INFO streak count=59 first=11-09_07:38 last=11-09_13:43 finished_inside=0
helper_rc=0
```

- `px=reply_1` при `curl=` не 0 — переписано как есть (допустимо по ТЗ).
- Итог: **DONE (helper_rc=0)** — вид отказа по каждому мосту и история сборок за 14 дней собраны;
  смысл меток не толковался, разбор — за разработчиком.
- Что менялось на машине: **ничего (да)** — только чтение; код шлюза d7c672b, режим best выключен.
