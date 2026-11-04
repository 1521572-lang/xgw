# Отчёт: XGW 0.2.0 — wave3h, фактический guard и стадии диагностики, короткий enable

Дата начала 2026-11-02 (run-start 11:18:33+03), завершение ~11:31+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255. Tested HEAD: 8d62db84627d2ed498d73722d2c1d65e6693634d; tree:
44e247788e2f9626c19ada1394454989537e5f7b. Code pin
fcaf04f6c60d6d45d974524d6ef7c1b9eb8dd6d9 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; продуктовый код против 573b233 — diff пуст (guard fix 2739e81c
остаётся установленным, замен/установок в этом прогоне не было).
Installed install.py/net/sysctl.py/diag.py/net/nft.py equal×4: True (INSTALLED_SOURCE_OK).
Frozen guardian wave3_safety.py SHA256
fce2dd78ae9a87fe04bda93a94aeefe0b617b2b8a4c85a9ec30ae8724f92fe22 и frozen sampler
wave3_enable_probe.py SHA256
096ec1b38fbdb76770a391ddf311d2207ff351e58126dcf78b86e19d940911fe, root:root 0700
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: первый AskUserQuestion в 11:18+03 вернулся без ответа (владелец отсутствовал);
владелец затем явно попросил задать вопрос ещё раз; повторный вопрос — ответ «Согласен
(рекомендую)» ~11:20+03: один краткий enable, возможный обрыв прежних direct-сессий и связи
модели; GET к настроенным HTTPS-целям с чтением префикса тела (32769 байт); обязательный
возврат к текущему off через 25 с с остановкой контроллера и его последующим стартом (при
длительном enable диагностика может быть прервана таймером — штатный PARTIAL/INCONCLUSIVE,
окно не продлевается); номинальный бюджет ~30 с без абсолютных гарантий. До ответа были
выполнены только безопасные S1–S3 и локальные заметки; сетевые шаги (разделы 5–8) начаты
после ответа — по карте переходов. Дополнительных прямых указаний, меняющих scope/окно/
rollback, не было.

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 10:53; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b…w3g ×safety/job — 12 units) |
| Связь владельца/модели до окна | живые (владелец ответил на повторный вопрос согласия; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 11:18:33+03 (каталог только с plan.md — разрешено S1.2); SUDO_CACHE_OK; согласие получено на повторном вопросе ~11:20 (первый остался без ответа — см. §1) |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK (fcaf04f предок; diff vs 573b233 продуктового пуст); INSTALLED_SOURCE_OK ×4 (вкл. net/nft.py); база см. §2 |
| S3 | 2 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (root:root 0700, обе SHA совпали) |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | PASS | {"tracked_job_context": true, "euid_root": true}; success 265 ms; после — inactive (rc 4, ожидаемый) |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED (offcheck); facts all_verified=true, 6/6 true |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit xgw-w3h-safety запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было); daemon left_stopped_for_review |
| P2 | total seconds_since_last_pulse / recovery_seconds | PASS | 25.105 с (всё окно) / 0.104 с |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true (6/6); WAN/LAN up/carrier 1; mismatch_present=false; связь живая |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | start xgw; «HEALTHY с 02.11 10:53» — таймштамп восстановлен из сохранённого состояния (факт); off; pool off; PIN_STATE_OK; CORE_UNITS_OK ×5 |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED (enable); facts all_verified=true, 6/6 true |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | PASS | schema=1, context=off; off/off; configured_local=true; configured_lan=true (факт); inbound_problem_present=false; tproxy; loaded=true/measured/complete/child_rc=0; child_budget_seconds=4; capture_enabled_now=false; guard_layout query=not_confirmed (в off допустимо); mismatch_present=false; listener tcp_read=true + ipv4_loopback=true; routes unmarked/proxy/bypass → unicast/WAN/main; diagnostic_gate=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.250 с и marked 0.238 с — оба body/32769/200/prefix_ok) |
| E1 | Одна launch-команда, independent safety→tracked job | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery отдельного enable-окна | PASS | ssLP 25.161; recovery_seconds 0.161 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/carrier 1; facts all_verified=true (6/6) |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=8.533 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc (не rc enable) | PASS | action=enable, state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 02.11 11:23; off; pool off; PIN_STATE_OK spare-de-0b0e; CORE_UNITS_OK ×5; ядра 26.10.31/1.14.4 |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback (job finished rc0) |

Capture.loaded во время окна: **null** (неизвестность). Источник: on-observations
stage=loaded. Loaded_reason/child_rc/phase: **child_deadline / null / loaded**; context=on,
child_budget_seconds=8. Schema consistency: schema=1, обязательные поля присутствуют
корректных типов — строка валидна; UNKNOWN с явной причиной, не False и не ошибка формата.
Строки HTTPS найдены по stage+path; в массиве marked отмечена раньше plain (порядок
готовности задач, не последовательность).

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | 1 / complete | 1 / loaded | child дошёл до Capture.loaded |
| loaded/reason/child_rc | true / measured / 0 | **null / child_deadline / null** | null не False |
| capture_method/configured_local/configured_lan | tproxy / true / true | tproxy / true / true | конфиг не менялся |
| requested_mode/effective_mode | off / off | **on / on** | расчёт библиотеки, не trace |
| inbound_problem_present | false | false | не PID/фактический accept |
| mismatch_present | false | false | — |
| guard_layout query/host_hook/host_priority/forward_hook | query=not_confirmed / — / — / — | **query=deadline_or_error** / не получено / не получено / не получено | 0.8-с запрос не завершился при on; UNKNOWN, не PASS |
| guard_layout host_drop_rules/host_reject_rules | — / — | **не получено** / **не получено** | >=1/0; число правил, не пакетов |
| context/capture_enabled_now/child_budget_seconds | off / false / 4 | on / **true** / 8 | context — запрос; capture_enabled_now — отдельное чтение live state |
| tcp_read/ipv4_any/ipv4_loopback/tcp_other_address | true/false/true/false | true/false/**true**/false | только LISTEN на точном порту |
| tcp6_read/ipv6_any/ipv6_loopback/tcp6_other_address | true/false/false/false | true/false/false/false | V6ONLY не измерен |
| routes.unmarked | unicast/WAN/main | unicast/WAN/main | unmarked→WAN не обход |
| routes.proxy | unicast/WAN/main | **local/loopback/tproxy** | lookup, не поток |
| routes.bypass | unicast/WAN/main | unicast/WAN/main | lookup, не поток |
| diagnostic_gate | true | неприменимо | gate не PASS VPN |

Новый порядок стадий сработал: guard_query выполнялся первым (его результат
deadline_or_error сохранён), затем импорт/config/create/быстрые факты/routes — всё
сохранено; child остановился на самом вызове Capture.loaded при бюджете 8 с. В on три
child параллельны; отсутствующие поля — UNKNOWN, из off не восстанавливались. Ни имён
NIC, ни table ID, ни адресов не выводилось.

### 4.2. Checkpoint и неполные измерения

Все 5 категорий JSON присутствуют: baseline, off-diagnostic, enable-result,
on-observations, kernel-diagnostic. kernel-diagnostic.json: context=on,
capture_enabled_now=true, phase=loaded, loaded=null/child_deadline/child_rc=null,
child_budget_seconds=8 — **полностью совпадает с event-строкой stage=loaded**
(согласованы; расхождений нет; при finished job checkpoint повторяет final result без
stage — ожидаемо). Факты из раннего checkpoint не требовались: event содержит все быстрые
факты. context=on — только запрошенный контекст; активный перехват подтверждается
совокупно: capture_enabled_now=true, frames capture/guard=true, plain/marked body при on.
Loaded_reason/child_rc/budget у final event: child_deadline/null/8. Pending-значений в
checkpoint нет. Последняя phase=loaded — граница прогресса: guard/routes/inbound_check
завершены, Capture.loaded началась и не завершилась; конкретный syscall/причина задержки
этим не установлен. Повторной установки/G1/замены nft.py не было; отклонений нет.

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.250 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.238 |
| on | 0 | plain | **body** | 200 | 32769 | **prefix_ok** | 0.466 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.292 |

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

Последний успешный ID шага: R2. Отказов гейтов не было (все PASS; loaded=null и
guard query deadline_or_error — категории неизвестности с явными причинами, не отказы).
Отклонений от штатного протокола нет; прямых указаний, меняющих scope/окно/rollback, не
было (повтор вопроса согласия — по прямой просьбе владельца, до любых сетевых шагов).
Новых каталогов/повторных enable/установок/G1 нет: один enable, snapshot-набор
offcheck+enable. Частичный сбор: нет — job finished rc0, все 5 категорий присутствуют,
event полон по быстрым фактам; неизвестности — Capture.loaded при on (child_deadline на
8 с) и guard query (deadline_or_error на 0.8 с при on).

Итоговое: HEALTHY с 02.11 11:23; capture off; pool off; ядра Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и
модели — живая.

**Главные результаты:**
- plain при on прошёл второй прогон подряд (body/32769/200/0.466 с; в wave3g — 0.354 с;
  в wave3e/f — ConnectionRefusedError на tcp). Функциональный факт стабилизации после
  postrouting-исправления; два запуска — не доказательство устойчивости.
- Новый порядок стадий локализовал задержку точнее всех прежних прогонов: child прошёл
  guard-запрос → импорт → config → create → факты → routes → inbound_check (полная
  сборка rules(on) успела) и остановился на самом вызове Capture.loaded при бюджете 8 с
  (phase=loaded, child_deadline). Задержка — в Capture.loaded при on, НЕ в config.load/
  GeoIP/импорте (те завершились). Граница checkpoint — не трасса syscall.
- Фактический guard_layout при on НЕ получен в третьем прогоне, с новой измеренной
  причиной: read-only `nft -j list table` с лимитом 0.8 с не завершился при включённом
  перехвате (query=deadline_or_error). По матрице это UNKNOWN, не PASS: postrouting/10/
  forward/drop≥1/reject=0 не подтверждены; матричная строка «короткий host-кейс» применена
  частично (enable rc0, plain/marked prefix_ok, rollback PASS — есть; actual layout — нет).
- Согласованность event/checkpoint: kernel-diagnostic.json идентичен строке stage=loaded —
  несогласованности нет.
- Косвенные признаки on в этом прогоне полнее прежних: capture_enabled_now=true,
  IPv4 TPROXY listener на loopback, proxy-route → lo/local/tproxy, inbound_problem=false,
  mismatch=false, оба HTTPS body при on, guard_present=true во всех on-frames.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта. Эта проверка enable не смешивается
с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3h-2026-11-02.md, коммит «Отчёт: XGW
0.2.0, wave3h — короткий enable», push в freepool (REPORT_PUBLISHED в финальном сообщении).
В Git только этот Markdown; notes/measurements.jsonl/snapshot/off.nft/job.log/
enable-cli.log/URL-адреса остались вне репозитория.
