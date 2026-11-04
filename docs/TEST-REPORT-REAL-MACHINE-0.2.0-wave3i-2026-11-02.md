# Отчёт: XGW 0.2.0 — wave3i, guard JSON/native и журнал чтения, короткий enable

Дата начала 2026-11-02 (run-start 11:55:06+03), завершение ~12:07+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255, **nftables v1.0.9 (Old Doc Yak #3)** (S1.3, записано буквально; nft не
обновлялся). Tested HEAD: 1dded4839a6333f475e6044af78e7ae488368188; tree:
659a8cfb0629c82ffcc8ceaff99cd252b3a554f8. Code pin
f78c2f1432ae56cdec8e229b59f33b9ee4723760 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; продуктовый код против 573b233 — diff пуст (guard fix 2739e81c
остаётся установленным; замен/установок в этом прогоне не было).
Installed install.py/net/sysctl.py/diag.py/net/nft.py equal×4: True (INSTALLED_SOURCE_OK).
Frozen guardian wave3_safety.py SHA256
2403ac15034b7251198927855e92a79ad3e2d0779e4ce3652345daaa32832d57 и frozen sampler
wave3_enable_probe.py SHA256
5420893e17b0a80d24e6baa7b53de49999095ed2c02e72aa586781b4e52500b1, root:root 0700
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: получено ~11:55+03 до подготовки (AskUserQuestion) — «Согласен
(рекомендую)»: один краткий enable, возможный обрыв прежних direct-сессий и связи модели;
GET к настроенным HTTPS-целям с чтением префикса тела (32769 байт); обязательный возврат
к текущему off через 25 с с остановкой контроллера и его последующим стартом (при
длительном enable диагностика/guard может быть прервана таймером — штатный
PARTIAL/INCONCLUSIVE, окно не продлевается); номинальный бюджет ~30 с без абсолютных
гарантий. Дополнительных прямых указаний владельца, меняющих scope/окно/rollback, не было.

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 11:47; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b…w3h ×safety/job — 14 units) |
| Связь владельца/модели до окна | живые (владелец ответил на согласие; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 11:55:06+03 (каталог только с plan.md — разрешено S1.2); SUDO_CACHE_OK; S1.3 nft v1.0.9; согласие §2.2 получено |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK (f78c2f1 предок; diff vs 573b233 продуктового пуст); INSTALLED_SOURCE_OK ×4 (вкл. net/nft.py); база см. §2 |
| S3 | 2 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (root:root 0700, обе SHA совпали) |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | PASS | {"tracked_job_context": true, "euid_root": true}; success 264 ms; после — inactive (rc 4, ожидаемый) |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED (offcheck); facts all_verified=true, 6/6 true |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit xgw-w3i-safety запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было); daemon left_stopped_for_review |
| P2 | total seconds_since_last_pulse / recovery_seconds | PASS | 25.113 с (всё окно) / 0.113 с |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true (6/6); WAN/LAN up/carrier 1; mismatch_present=false; связь живая |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | start xgw; «HEALTHY с 02.11 11:47» — таймштамп восстановлен из сохранённого состояния (факт); off; pool off; PIN_STATE_OK; CORE_UNITS_OK ×5 |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED (enable); facts all_verified=true, 6/6 true |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | PASS | schema=1, context=off; off/off; local=true; lan=true (факт); inbound_problem=false; tproxy; loaded=true/measured/complete/rc=0; budget=4; capture_enabled_now=false; mismatch=false; listener tcp_read=true + ipv4_loopback=true; routes unmarked/proxy/bypass → unicast/WAN/main; read_trace: 29 calls, truncated=false, active=[], readonly_violation отсутствует (не true); off-guard query=unconfirmed (в off допустимо); diagnostic_gate=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.270 с и marked 0.266 с — оба body/32769/200/prefix_ok) |
| E1 | Одна launch-команда, independent safety→tracked job | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery отдельного enable-окна | PASS | ssLP 25.126; recovery_seconds 0.126 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/carrier 1; facts all_verified=true (6/6) |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=8.524 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc (не rc enable) | PASS | action=enable, state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 02.11 11:57; off; pool off; PIN_STATE_OK spare-de-0b0e; CORE_UNITS_OK ×5; ядра 26.10.31/1.14.4 |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback (job finished rc0) |

Capture.loaded во время окна: **null** (неизвестность). Источник: on-observations
stage=loaded. Loaded_reason/child_rc/phase: **child_deadline / null / loaded**; context=on,
child_budget_seconds=8. Schema consistency: schema=1, обязательные поля присутствуют
корректных типов; UNKNOWN с явной причиной, не False и не ошибка формата. Четыре задачи
(loaded/guard/plain/marked) параллельны; строки найдены по stage+path; в массиве guard
отмечен раньше https-строк (порядок готовности).

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | 1 / complete | 1 / loaded | child дошёл до Capture.loaded |
| loaded/reason/child_rc | true / measured / 0 | **null / child_deadline / null** | null не False |
| capture_method/configured_local/configured_lan | tproxy / true / true | tproxy / true / true | конфиг не менялся |
| requested_mode/effective_mode | off / off | **on / on** | расчёт библиотеки, не trace |
| inbound_problem_present | false | false | не PID/фактический accept |
| mismatch_present | false | false | — |
| guard worker query/source/host_hook/host_priority/forward_hook | query=unconfirmed / — / — / — / — | **query=ok / json / postrouting / 10 / forward** | stage=guard; подтверждение политики см. §4.3 |
| guard worker host_drop_rules/host_reject_rules | — / — | **5 / 0** | число правил, не пакетов |
| context/capture_enabled_now/child_budget_seconds | off / false / 4 | on / **true** / 8 | context — запрос; capture_enabled_now — отдельное чтение live state |
| tcp_read/ipv4_any/ipv4_loopback/tcp_other_address | true/false/true/false | true/false/**true**/false | только LISTEN на точном порту |
| tcp6_read/ipv6_any/ipv6_loopback/tcp6_other_address | true/false/false/false | true/false/false/false | V6ONLY не измерен |
| routes.unmarked | unicast/WAN/main | unicast/WAN/main | unmarked→WAN не обход |
| routes.proxy | unicast/WAN/main | **local/loopback/tproxy** | lookup, не поток |
| routes.bypass | unicast/WAN/main | unicast/WAN/main | lookup, не поток |
| diagnostic_gate | true | неприменимо | gate не PASS VPN |

Отсутствующие поля — UNKNOWN, из off не восстанавливались. Ни имён NIC, ни table ID, ни
адресов не выводилось.

### 4.2. Checkpoint и неполные измерения

Все **7 категорий** присутствуют: baseline, off-diagnostic, enable-result,
on-observations, kernel-diagnostic, off-guard, on-guard. kernel-diagnostic.json:
context=on, capture_enabled_now=true, phase=loaded, loaded=null/child_deadline/null,
budget=8, read_trace идентичен event-строке — **stage=loaded и checkpoint согласованы**
(расхождений нет). Факты из раннего checkpoint не требовались. context=on — запрос;
активный перехват подтверждается совокупно: capture_enabled_now=true, frames
capture/guard=true, guard-worker before/after=true, оба HTTPS body при on.
Loaded_reason/child_rc/budget у final event: child_deadline/null/8. Pending-значений нет.
Последняя phase=loaded — граница прогресса, не диагноз syscall. Повторной установки/G1/
замены nft.py не было; отклонений нет.

### 4.3. Independent guard attempts

stage=guard и on-guard.json **совпадают** (включая metadata). capture_enabled_before/after
= true/true (вместе с frames — подтверждённое on-наблюдение).
**Фактический layout: query=ok, source=json, host_hook=postrouting, host_priority=10,
forward_hook=forward, host_drop_rules=5, host_reject_rules=0** — критерии подтверждения
исправленной политики (postrouting/10/forward/drop≥1/reject=0) выполнены; state=ok не
«автоматический PASS исправления», но здесь совпал со всеми ожидаемыми полями.

| Context | Encoding | State | Rc/error_class | Budget | Seconds | Stdout/stderr bytes |
|---|---|---|---|---|---|---|
| off | json | nonzero | rc=1 (таблица отсутствует; причина не уточнялась) | 3 с | 0.010 | 0 / 85 |
| on | json | **ok** | rc=0 | 3 с | **0.064** | 8116 / 0 |
| on | text fallback | NOT_RUN | — | — | — | — |

Fallback не выполнялся: JSON-попытка при on дала query=ok с полной metadata — по ТЗ
fallback запускается только при неуспехе JSON; «удобное» второе чтение не требовалось.
В off fallback запрещён. Замечание об исторической формулировке wave3h: там
«deadline_or_error» объединял timeout/OSError/JSON/schema; в этом прогоне тот же
read-only запрос как независимый worker занял 0.064 с — прежнее значение не может
интерпретироваться как доказанный таймаут nft (не повторяем ту формулировку как факт).

### 4.4. Loaded read trace

readonly_violation: отсутствует (не true — защиты не нарушались). truncated=false
(все 48 мест хватило). Последняя phase=loaded; **active при deadline: [id=33,
method__desired_problem, running, begin 5.626]** — единственная незавершённая граница.
Begin_seconds отсчитывается от начала trace после создания Capture (не от launch);
лимит 8 с — весь child. Длительность running неизвестна и не вычисляется как 8−5.626.

| Id | Label | State/error_class | Begin seconds | Seconds если завершён |
|---|---|---|---|---|
| 1 | method_inbound_problem | returned | 0.056 | 3.625 |
| 2 | method_rules | returned | 0.056 | 3.616 |
| 3 | method_effective_mode | returned | 3.683 | 0.010 |
| 4 | method_inbound_problem | returned | 3.683 | 0.009 |
| 5 | method_rules | returned | 3.683 | 0.004 |
| 6 | method_rules | returned | 3.694 | 0.007 |
| 7 | method_guard_loaded | returned | 3.704 | 0.036 |
| 8 | method_effective_mode | returned | 3.704 | 0.015 |
| 9 | method_inbound_problem | returned | 3.705 | 0.012 |
| 10 | method_rules | returned | 3.705 | 0.004 |
| 11 | method_rules | returned | 3.720 | 0.003 |
| 12 | nft_generation | returned | 3.725 | 0.000 |
| 13 | nft_list_table_inet_xgw_guard | returned | 3.726 | 0.011 |
| 14 | nft_generation | returned | 3.741 | 0.000 |
| 15 | nft_list_table_ip_xgw | returned | 3.743 | **0.692** |
| 16 | nft_generation | returned | 4.437 | 0.000 |
| 17 | nft_list | returned | 4.437 | 0.008 |
| 18 | nft_generation | returned | 4.449 | 0.000 |
| 19 | nft_list | returned | 4.450 | 0.013 |
| 20 | nft_generation | returned | 4.464 | 0.000 |
| 21 | nft_list | returned | 4.465 | 0.011 |
| 22 | nft_generation | returned | 4.478 | 0.000 |
| 23 | nft_list | returned | 4.481 | 0.010 |
| 24 | nft_generation | returned | 4.493 | 0.000 |
| 25 | nft_list | returned | 4.499 | 0.012 |
| 26 | nft_generation | returned | 4.512 | 0.000 |
| 27 | nft_list | returned | 4.513 | **1.071** |
| 28 | method__v6_guard_loaded | returned | 5.601 | 0.022 |
| 29 | nft_generation | returned | 5.602 | 0.000 |
| 30 | nft_list_table_ip6_xgw6 | returned | 5.604 | 0.013 |
| 31 | method__ts_loaded | returned | 5.619 | 0.003 |
| 32 | nft_generation | returned | 5.625 | 0.000 |
| 33 | method__desired_problem | **running** | 5.626 | — (не завершён) |

Off-read_trace (для сравнения, тот же инструмент): 29 calls, активных нет; самая тяжёлая
граница off — method_inbound_problem 2.709 с; nft_list_table_inet_xgw_guard в off —
exception CommandError ×3 по ~0.01 с (таблицы нет — ожидаемо; CommandError ≠ parser
exception). Nested времена перекрываются; returned не означает loadedTrue; active не
является syscall-трассой; overhead wrappers/checkpoint включён в seconds. Никаких argv/
адресов/текстов исключений не выводилось.

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.270 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.266 |
| on | 0 | plain | **body** | 200 | 32769 | **prefix_ok** | 0.428 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.436 |

Ready_for_enable: true. Diagnostic_gate: true. Baseline_healthy: true. Ограничение
сравнения: не было. Одна цель (target 0) в обеих фазах. Sampler rc0 подтверждает
завершение сбора, не работоспособность VPN. Prefix 32769 — только проверенный префикс.
Plain может идти direct по исключению; VPN-egress/полное тело/все приложения этим не
доказываются. DNS-on не измерен: IP готовы до on.

## 6. WAN и связь

| WAN fact | До enable (B1) | После off-rollback (R1) | Интерпретация |
|---|---|---|---|
| profile | true | true | — |
| addresses | true | true | — |
| live_gateway_dns | true | true | — |
| route4 | true | true | — |
| route6 | true | true | — |
| mtu | true | true | — |
| all_verified | true | true | — |

| Канал | До | Во время on | После off | Источник наблюдения |
|---|---|---|---|---|
| Владелец | жив | UNKNOWN (не наблюдалось; rollback вернул off до опроса) | подтверждён | согласие/команды до; чтение R1/R2 после |
| Модель/инструмент | жив | UNKNOWN (команды в окне не требовались) | подтверждён | выполнение шагов |
| Tailscale | NOT_RUN | NOT_RUN | NOT_RUN | вне scope |

## 7. Отклонения, итог и незакрытые ворота

Последний успешный ID шага: R2. Отказов гейтов не было (все PASS; loaded=null —
неизвестность с причиной child_deadline, guard-off unconfirmed — ожидаемость off).
Отклонений от штатного протокола нет; прямых указаний владельца, меняющих scope/окно/
rollback, не было. Новых каталогов/повторных enable/установок/G1 нет: один enable,
snapshot-набор offcheck+enable. Частичный сбор: нет — job finished rc0, все 7 категорий
присутствуют; единственная внутренняя неизвестность — Capture.loaded при on (child умер
на method__desired_problem, running с 5.626 с при бюджете 8 с на весь child).

Итоговое: HEALTHY с 02.11 11:57; capture off; pool off; ядра Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и
модели — живая.

**Главные результаты:**
- **Фактический guard-layout при on подтверждён впервые за серию**: независимый worker,
  query=ok, source=json, 0.064 с (native fallback не потребовался): host_hook=postrouting,
  priority=10, forward_hook=forward, drop_rules=5, reject_rules=0 — исправленная
  фактическая политика соответствует ожидаемой. По матрице строка «короткий host-кейс
  прошёл» выполнена целиком впервые: capture=true + actual layout + plain/marked
  prefix_ok + rollback PASS (loaded-неизвестность учитывается отдельно).
- **Прежняя формулировка wave3h опровергнута данными**: тот же read-only запрос, который
  в wave3h внутри общего диагностического child получил deadline_or_error, как отдельный
  worker завершился за 0.064 с. Формулировка «nft не завершился за 0.8 с» была сильнее
  данных — причина была в конкуренции внутри child, не в самом nft.
- **read_trace локализовал незавершённость точнее некогда**: 32 границы вернулись
  (включая тяжёлую первую сборку rules(on) — method_inbound_problem 3.625 с и медленные
  nft-чтения 0.692/1.071 с), при deadline ровно одна активная граница —
  method__desired_problem (running, begin 5.626). Это сохранённая незавершённая граница,
  не доказанный зависший syscall; длительность неизвестна (лимит 8 с — весь child).
- **plain при on — третий прогон подряд** (0.428 с; wave3g 0.354, wave3h 0.466) при
  работающем marked иcarrier 1; enable rc0 за 8.524 с; rollback 0.126 с; WAN 6/6.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта (loaded при on остаётся неизвестным:
в off-loaded=true/measured, при on child завершается по бюджету на method__desired_problem).
Эта проверка enable не смешивается с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3i-2026-11-02.md, коммит «Отчёт: XGW
0.2.0, wave3i — короткий enable», push в freepool (REPORT_PUBLISHED в финальном сообщении).
В Git только этот Markdown; notes/measurements.jsonl/snapshot/off.nft/job.log/
enable-cli.log/*-guard-*.stdout/.stderr/URL-адреса остались вне репозитория.
