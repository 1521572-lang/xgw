# Отчёт: XGW 0.2.0 — wave3j, parser update и проверка loaded, короткий enable

Дата начала 2026-11-02 (run-start 12:36:52+03), завершение ~12:47+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255, **nftables v1.0.9 (Old Doc Yak #3)** (S1.3, записано буквально; не обновлялся).
Tested HEAD: e024e98f5ebcb0cee6664b26f75520cc56040260; tree:
0b7a83e32477710800b9a61028c3780059b6381a. Code pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; продуктовый diff против b32669a — только src/xgw/net/nft.py
(parser helpers; render/guard прежние), как заявлено ТЗ.
Installed 3 unchanged files (install.py/net/sysctl.py/diag.py) equal×3 до G1; после G1
все 4 (включая новый net/nft.py) совпадают.
Frozen guardian wave3_safety.py SHA256
1f986c99799b840bb88d5b85ff4029de0805b2435d979cf38f7179cd3c900c15, root:root 0700;
frozen sampler wave3_enable_probe.py SHA256
5420893e17b0a80d24e6baa7b53de49999095ed2c02e72aa586781b4e52500b1, root:root 0700;
payload nft.py.new SHA256
10c1df64997c06e49095d0cb418f50b6eb3514e83725e7e6b663a8b606ee4fe7, root:root 0600
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: получено ~12:36+03 до подготовки (AskUserQuestion) — «Согласен
(рекомендую)»: один краткий enable, возможный обрыв прежних direct-сессий и связи модели;
GET к настроенным HTTPS-целям с чтением префикса тела (32769 байт); одно атомарное
обновление только net/nft.py по old/new SHA с root-backup при off/остановленных писателях
(backup остаётся в /run, новый файл остаётся установленным; отрисованные правила не
меняются); обязательный возврат к текущему off через 25 с с остановкой контроллера и его
последующим стартом; номинальный бюджет ~30 с без абсолютных гарантий. Дополнительных
прямых указаний владельца, меняющих scope/окно/rollback, не было.

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 12:01; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b…w3i ×safety/job — 16 units) |
| Связь владельца/модели до окна | живые (владелец ответил на согласие; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 12:36:52+03 (каталог только с plan.md — разрешено S1.2); SUDO_CACHE_OK; S1.3 nft v1.0.9; согласие §2.2 получено |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK (351fb54 предок; diff vs b32669a только nft.py); INSTALLED_SOURCE_OK ×3; OLD_NFT_SOURCE_OK (2739e81c, safe_owner_mode=true); база см. §2 |
| S3 | 3 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (helpers 0700, nft.py.new 0600, все SHA совпали) |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | PASS | {"tracked_job_context": true, "euid_root": true}; success 270 ms; после — inactive (rc 4, ожидаемый) |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED (offcheck); facts all_verified=true, 6/6 true |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit xgw-w3j-safety запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было); daemon left_stopped_for_review |
| P2 | total seconds_since_last_pulse / recovery_seconds | PASS | 25.143 с (всё окно) / 0.143 с |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true (6/6); WAN/LAN up/carrier 1; mismatch_present=false; связь живая |
| G1 | Новый parser nft.py old/newSHA/backup/4 files/dry nft-c | PASS | NFT_CODE_UPDATED old_sha_verified=True new_sha_verified=True backup_verified=True (первая попытка); повторно INSTALLED_SOURCE_OK ×3 + NEW_NFT_SOURCE_OK (10c1df64) + NEW_GUARD_SYNTAX_OK |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | start xgw; «HEALTHY с 02.11 12:01» — таймштамп восстановлен из сохранённого состояния (факт); off; pool off; PIN_STATE_OK; CORE_UNITS_OK ×5 |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED (enable); facts all_verified=true, 6/6 true |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | PASS | schema=1, context=off; off/off; local=true; lan=true (факт); inbound_problem=false; tproxy; loaded=true/measured/complete/rc=0; budget=4; capture_enabled_now=false; mismatch=false; listener tcp_read=true + ipv4_loopback=true; routes unmarked/proxy/bypass → unicast/WAN/main; read_trace 29 calls, truncated=false, active=[], readonly_violation отсутствует (не true); off-guard query=unconfirmed (в off допустимо); diagnostic_gate=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.304 с и marked 0.292 с — оба body/32769/200/prefix_ok) |
| E1 | Одна launch-команда, independent safety→tracked job | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery отдельного enable-окна | PASS | ssLP 25.130; recovery_seconds 0.130 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/carrier 1; facts all_verified=true (6/6) |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=8.034 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc (не rc enable) | PASS | action=enable, state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 02.11 12:39; off; pool off; PIN_STATE_OK spare-de-0b0e; CORE_UNITS_OK ×5; ядра 26.10.31/1.14.4 |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback (job finished rc0) |

Capture.loaded во время окна: **true (measured)** — впервые за серию прогонов. Источник:
on-observations stage=loaded. Loaded_reason/child_rc/phase: **measured / 0 / complete**;
context=on, child_budget_seconds=8. Schema consistency: schema=1, поля корректных типов.
Четыре задачи (loaded/guard/plain/marked) параллельны; строки найдены по stage+path.

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | 1 / complete | 1 / complete | child дошёл до результата |
| loaded/reason/child_rc | true / measured / 0 | **true / measured / 0** | фактическое True при on |
| capture_method/configured_local/configured_lan | tproxy / true / true | tproxy / true / true | конфиг не менялся |
| requested_mode/effective_mode | off / off | **on / on** | расчёт библиотеки, не trace |
| inbound_problem_present | false | false | не PID/фактический accept |
| mismatch_present | false | false | — |
| guard worker query/source/host_hook/host_priority/forward_hook | query=unconfirmed / — / — / — / — | **query=ok / json / postrouting / 10 / forward** | stage=guard; см. §4.3 |
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
context=on, capture_enabled_now=true, phase=complete, loaded=true/measured/rc=0,
budget=8, read_trace идентичен event-строке — **stage=loaded и checkpoint согласованы**
(расхождений нет). Факты из раннего checkpoint не требовались. context=on — запрос;
активный перехват подтверждается совокупно: capture_enabled_now=true, frames
capture/guard=true, guard-worker before/after=true, оба HTTPS body при on.
Loaded_reason/child_rc/budget у final event: measured/0/8. Pending-значений нет.
G1 — одна новая замена parser nft.py, не full installer; отклонений нет.

### 4.3. Independent guard attempts

stage=guard и on-guard.json **совпадают** (включая metadata). capture_enabled_before/after
= true/true (вместе с frames — подтверждённое on-наблюдение).
**Фактический layout: query=ok, source=json, host_hook=postrouting, host_priority=10,
forward_hook=forward, host_drop_rules=5, host_reject_rules=0** — критерии подтверждения
исправленной политики выполнены (state=ok не «автоматический PASS», но все поля совпали).

| Context | Encoding | State | Rc/error_class | Budget | Seconds | Stdout/stderr bytes |
|---|---|---|---|---|---|---|
| off | json | nonzero | rc=1 (таблица отсутствует; причина не уточнялась) | 3 с | 0.010 | 0 / 85 |
| on | json | **ok** | rc=0 | 3 с | **0.025** | 8116 / 0 |
| on | text fallback | NOT_RUN | — | — | — | — |

Fallback не выполнялся: JSON-попытка при on дала query=ok с полной metadata — по ТЗ
fallback запускается только при неуспехе JSON. В off fallback запрещён. Прошлое
deadline_or_error (wave3h) и прежние seconds (wave3i) — исторические; «конкуренция
внутри child» остаётся гипотезой, а не доказанным объяснением; в этом прогоне
установленных причин прежних deadline не добавилось.

### 4.4. Loaded read trace

readonly_violation: отсутствует (не true). truncated=**true** — достигнут лимит 48
записей; вызовы после 48-й в trace не отражены (отсутствие строки ≠ отсутствие вызова).
**active=[] — ни одной незавершённой границы**; child завершил проверку штатно
(child_rc=0, phase=complete) в бюджете 8 с. Begin_seconds — от начала trace после
создания Capture (не от launch); лимит 8 с — весь child.

| Id | Label | State/error_class | Begin seconds | Seconds если завершён |
|---|---|---|---|---|
| 1 | method_inbound_problem | returned | 0.042 | 2.922 |
| 2 | method_rules | returned | 0.043 | 2.908 |
| 3 | method_effective_mode | returned | 2.965 | 0.012 |
| 4 | method_inbound_problem | returned | 2.966 | 0.011 |
| 5 | method_rules | returned | 2.966 | 0.008 |
| 6 | method_rules | returned | 2.979 | 0.005 |
| 7 | method_guard_loaded | returned | 2.987 | 0.052 |
| 8 | method_effective_mode | returned | 2.987 | 0.013 |
| 9 | method_inbound_problem | returned | 2.987 | 0.012 |
| 10 | method_rules | returned | 2.987 | 0.005 |
| 11 | method_rules | returned | 3.001 | 0.005 |
| 12 | nft_generation | returned | 3.007 | 0.000 |
| 13 | nft_list_table_inet_xgw_guard | returned | 3.012 | 0.021 |
| 14 | nft_generation | returned | 3.040 | 0.000 |
| 15 | nft_list_table_ip_xgw | returned | 3.041 | **0.814** |
| 16 | nft_generation | returned | 3.856 | 0.000 |
| 17 | nft_list | returned | 3.857 | 0.009 |
| 18 | nft_generation | returned | 3.868 | 0.000 |
| 19 | nft_list | returned | 3.869 | 0.019 |
| 20 | nft_generation | returned | 3.889 | 0.000 |
| 21 | nft_list | returned | 3.893 | 0.014 |
| 22 | nft_generation | returned | 3.909 | 0.000 |
| 23 | nft_list | returned | 3.910 | 0.020 |
| 24 | nft_generation | returned | 3.931 | 0.000 |
| 25 | nft_list | returned | 3.935 | 0.028 |
| 26 | nft_generation | returned | 3.964 | 0.000 |
| 27 | nft_list | returned | 3.970 | **1.158** |
| 28 | method__v6_guard_loaded | returned | 5.150 | 0.016 |
| 29 | nft_generation | returned | 5.151 | 0.000 |
| 30 | nft_list_table_ip6_xgw6 | returned | 5.153 | 0.012 |
| 31 | method__ts_loaded | returned | 5.166 | 0.000 |
| 32 | nft_generation | returned | 5.168 | 0.000 |
| 33 | **method__desired_problem** | **returned** | 5.179 | **1.099** |
| 34 | nft_generation | returned | 6.277 | 0.000 |
| 35 | method__tables_digest | returned | 6.280 | 0.016 |
| 36 | nft_generation | returned | 6.281 | 0.000 |
| 37 | nft_list_table_ip6_xgw6 | returned | 6.283 | 0.011 |
| 38 | nft_generation | returned | 6.295 | 0.000 |
| 39 | method__ts_loaded | returned | 6.298 | 0.001 |
| 40 | nft_generation | returned | 6.333 | 0.000 |
| 41 | method__tun_problem | returned | 6.334 | 0.019 |
| 42 | ip_link_read | returned | 6.339 | 0.004 |
| 43 | ip_addr_read | returned | 6.345 | 0.006 |
| 44 | ip_route_read | returned | 6.355 | 0.007 |
| 45 | ip_rule_read | returned | 6.364 | 0.009 |
| 46 | ip_rule_read | returned | 6.375 | 0.012 |
| 47 | ip_rule_read | returned | 6.393 | 0.007 |
| 48 | ip_rule_read | returned | 6.402 | 0.005 |

Off-read_trace: 29 calls, активных нет; method_inbound_problem 2.618 с;
nft_list_table_inet_xgw_guard — exception CommandError ×3 по 0.006–0.007 с (таблицы нет
в off — ожидаемо). Nested времена перекрываются; returned не означает значение bool;
overhead wrappers/checkpoint включён; truncated=true — часть вызовов не видна. Никаких
argv/адресов/текстов исключений не выводилось.

### 4.5. Новый G1 parser update

Исходный NFT SHA: 2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547 —
совпал (S2.4 до замены и old_sha_verified в G1). Новый NFT SHA:
10c1df64997c06e49095d0cb418f50b6eb3514e83725e7e6b663a8b606ee4fe7 — NEW_NFT_SOURCE_OK
после замены. G1: фазы preconditions→backup→stage→replace→verify,
result=NFT_CODE_UPDATED (три True), backup_verified=True (backup nft.py.before-wave3j,
root0600, в /run, в Git не включён). Все 4 installed файла совпадают после G1
(3 прежних + новый nft.py). Dry nft-c: NEW_GUARD_SYNTAX_OK (без загрузки). Писатели
xgw/xgw-net остановлены до G1 (после RESTORED_OFF, проверено командой G1). Installer не
запускался; WAN/config/sysctl/ядра не менялись. Ошибок G1 не было; классификационный
блок не потребовался. Новый файл остаётся установленным после опыта; guardian вернул
сетевой off, не версию кода. Синтетические времена ТЗ (WSL-фикстура) в результат не
подставлялись.

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.304 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.292 |
| on | 0 | plain | **body** | 200 | 32769 | **prefix_ok** | 0.307 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.290 |

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

Последний успешный ID шага: R2. Отказов гейтов не было (все PASS). Отклонений от
штатного протокола нет; прямых указаний владельца, меняющих scope/окно/rollback, не
было. Новых каталогов/повторных enable/повторной установки нет: одна попытка G1(j),
один enable, snapshot-набор offcheck+enable. Частичный сбор: нет — job finished rc0,
все 7 категорий присутствуют; trace обрезан лимитом 48 записей (truncated=true) после
уже полученного loaded=true — это ожидаемое ограничение журнала, не неполнота вердикта.

Итоговое: HEALTHY с 02.11 12:39; capture off; pool off; ядра Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и
модели — живая. Установленный net/nft.py — parser-версия 10c1df64 (правила render/guard
не менялись, dry nft-c OK); backup прежней (2739e81c) — root0600 в /run.

**Главные результаты:**
- **Capture.loaded при on впервые завершилась фактическим измерением: loaded=true,
  measured, phase=complete, child_rc=0** в бюджете 8 с — после пяти прогонов с
  неизвестностью (wave3e unexpected_type; wave3f/g/h/i null/child_deadline). Ключевая
  граница trace: **method__desired_problem returned за 1.099 с** (в wave3i — незавершённая
  running при дедлайне); после неё child прошёл ещё ~15 границ (tables_digest, tun_problem,
  ip_* reads) и вернул результат. Сравнение с прежними прогонами — историческое, парное,
  не benchmark и не доказательство причины (никакой контрфактический запуск со старым
  parser в этом прогоне не выполнялся).
- **Фактический guard-layout при on подтверждён повторно**: query=ok/json 0.025 с,
  postrouting/10/forward/drop=5/reject=0; capture_enabled_before/after=true.
- **По матрице короткий host-кейс закрыт полнее прежних**: capture=true + actual layout +
  plain/marked prefix_ok + rollback PASS **и** loaded=measured true — проверка
  соответствия политики при on впервые прошла измерением, а не осталась неизвестностью.
- **plain при on — четвёртый прогон подряд** (0.307 с; wave3g 0.354, wave3h 0.466,
  wave3i 0.428) при работающем marked; enable rc0 за 8.034 с; rollback 0.130 с; WAN 6/6.
- Оговорка к исторической формулировке wave3i: «конкуренция внутри child» остаётся
  гипотезой о wave3h; этот прогон причину прежних deadline не устанавливает и не
  опровергает.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта (заявление ТЗ «волна3 этим целиком
не закрывается» сохраняется; VPN-egress/полное тело/все приложения/DNS-on не доказаны).
Эта проверка enable не смешивается с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3j-2026-11-02.md, коммит «Отчёт: XGW
0.2.0, wave3j — короткий enable», push в freepool (REPORT_PUBLISHED в финальном сообщении).
В Git только этот Markdown; notes/measurements.jsonl/snapshot/off.nft/job.log/
enable-cli.log/*-guard-*.stdout/.stderr/URL-адреса остались вне репозитория.
