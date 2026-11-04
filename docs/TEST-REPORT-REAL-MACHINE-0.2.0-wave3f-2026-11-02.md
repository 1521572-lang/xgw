# Отчёт: XGW 0.2.0 — wave3f, атрибуция TCP-отказа, короткий enable

Дата начала 2026-11-02 (run-start 09:51:13+03), завершение ~10:01+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255. Tested HEAD: 1c4437bca6574f4fd5c06d1bada2b4d8a84610c9; tree:
16e8c427ddb5976211c1a1f4eb129e599b6c86d3. Code pin
5e75ba90455a5d451d7424301f87673cb0912f65 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; отдельно продуктовый код против 2862767 — diff пуст.
Installed install.py/net/sysctl.py/diag.py equal×3: True (INSTALLED_SOURCE_OK).
Frozen guardian wave3_safety.py SHA256
3bf6e693bcd4e21fd6861b5376bce73271d9f790a23ba1509de87532cbb8de7e, root:root 0700;
frozen sampler wave3_enable_probe.py SHA256
b7a86919db26c8212d80c8ef5b33235744f7b7582233d0e3e321b1a64e9299a6, root:root 0700
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: получено 09:50+03 перед шагами подготовки (AskUserQuestion) — «Согласен
(рекомендую)»: один краткий enable, возможный обрыв прежних direct-сессий и связи модели,
GET к настроенным HTTPS-целям с чтением префикса тела (32769 байт), обязательный возврат
к текущему off через 25 с с остановкой контроллера и его последующим стартом, номинальный
бюджет восстановления ~30 с (stop/kill/nft 1/1/3 с + IO) без абсолютных гарантий.
Отклонение от буквы протокола (с явного разрешения владельца, ответ «Удалить
(рекомендую)»): каталог заметок ~/xgw-w3f был создан мной до старта ТЗ (в нём только
plan.md); удалён, S1.2 создал заново, plan.md переизвлечён из origin/freepool. На сетевые
опыты не повлияло. Отличие от wave3e: sudo-кэш инструментального канала был действующим
сразу (SUDO_CACHE_OK), владелец пароль не вводил.

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 09:49; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b/w3c/w3d/w3e ×safety/job — 8 units) |
| Связь владельца/модели до окна | живые (владелец ответил на согласие; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 09:51:13+03; SUDO_CACHE_OK; согласие §2.2 получено (отклонение с пересозданием каталога — см. §1) |
| S1.3 | Историческое чтение wave3e JSON, hash/наличие/тип loaded | PASS (чтение) | historical_sampler_hash_matches=true; loaded_events=1; loaded_field_present=true; value_kind=unexpected_type (не bool, не null) — расхождение с формулировкой старого отчёта, см. §4.2 |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK; INSTALLED_SOURCE_OK ×3; база см. §2 |
| S3 | 2 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (root:root 0700, обе SHA совпали) |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | PASS | {"tracked_job_context": true, "euid_root": true}; success 244 ms; после — inactive (rc 4, ожидаемый ненулевой) |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED (offcheck); facts all_verified=true, 6/6 true |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit xgw-w3f-safety запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было — допустимо); daemon left_stopped_for_review |
| P2 | total seconds_since_last_pulse / recovery_seconds | PASS | 25.111 с (всё окно, pulse не было) / 0.11 с |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true (6/6); WAN/LAN up/carrier 1; mismatch_present=false; связь живая |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | start xgw; «HEALTHY с 02.11 09:49» — таймштамп восстановлен из сохранённого состояния демона (факт); off; pool off; PIN_STATE_OK; CORE_UNITS_OK (вкл. xgw-net) |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED (enable); facts all_verified=true, 6/6 true |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | PASS | schema=1; requested/effective=off; configured_local=true; configured_lan=true (факт); inbound_problem_present=false; capture_method=tproxy; loaded=true/measured/complete/child_rc=0; mismatch_present=false; listener tcp_read=true + ipv4_loopback=true (ipv4_any=false); routes unmarked/proxy/bypass → unicast/WAN/main (ожидаемо в off); diagnostic_gate=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.251 с и marked 0.226 с — оба body/32769/200/prefix_ok) |
| E1 | Одна launch-команда, independent safety→tracked job | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery отдельного enable-окна | PASS | ssLP 25.146; recovery_seconds 0.146 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/carrier 1; facts all_verified=true (6/6) |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=6.183 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc (не rc enable) | PASS | action=enable, state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 02.11 09:54; off; pool off; PIN_STATE_OK spare-de-0b0e; CORE_UNITS_OK ×5; ядра 26.10.31/1.14.4 |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback (job finished rc0) |

Capture.loaded во время окна: **null** (неизвестность проверки). Источник: on-observations
stage=loaded. Loaded_reason/child_rc/phase: child_deadline / null / loaded. Schema
consistency: schema=1, все обязательные поля (loaded, loaded_reason, child_rc) присутствуют —
строка корректна, UNKNOWN с явной причиной, не False и не ошибка формата.

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | 1 / complete | 1 / loaded | — |
| loaded/reason/child_rc | true / measured / 0 | **null / child_deadline / null** | null не False |
| capture_method/configured_local/configured_lan | tproxy / true / true | tproxy / true / true | конфиг не менялся |
| requested_mode/effective_mode | off / off | **on / on** | расчёт библиотеки, не trace |
| inbound_problem_present | false | false | не PID/фактический accept |
| mismatch_present | false | false | — |
| tcp_read/ipv4_any/ipv4_loopback/tcp_other_address | true/false/true/false | true/false/**true**/false | только LISTEN на точном порту |
| tcp6_read/ipv6_any/ipv6_loopback/tcp6_other_address | true/false/false/false | true/false/false/false | V6ONLY не измерен |
| routes.unmarked | unicast/WAN/main | unicast/WAN/main | unmarked→WAN не обход |
| routes.proxy | unicast/WAN/main | **local/loopback/tproxy** | lookup, не поток |
| routes.bypass | unicast/WAN/main | unicast/WAN/main | lookup, не поток |
| diagnostic_gate | true | неприменимо | gate не PASS VPN |

Быстрые факты on-стадии атомарно сохранены до дедлайна child (4 с): mode/listener/routes
известны; сам вызов loaded не завершился — child_deadline. В on три child параллельны;
строки сохранены по готовности. Ни имён NIC, ни table ID, ни адресов не выводилось.

### 4.2. Историческое чтение wave3e без сетевых действий

historical_sampler_hash_matches=**true** (преждеший sampler подтверждён); loaded events=**1**;
loaded_field_present=**true**; value_kind=**unexpected_type** (значение не bool и не null;
безопасный фильтр значение не печатает). HISTORICAL_READ_FINISHED.
**Расхождение переноса данных:** отчёт wave3e сформулировал «stage=loaded, поля нет»,
артефакт содержит поле `loaded` с неожиданным типом. Старый отчёт не переписывался; тип
значения не вскрывался; это историческое наблюдение, не результат wave3f и не переносится
в новый on. Вывод о kernel loaded или о работе VPN из него не делается.

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.251 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.226 |
| on | 0 | plain | **tcp** | — | 0 | **ConnectionRefusedError** | 0.065 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.293 |

Ready_for_enable: true. Diagnostic_gate: true. Baseline_healthy: true. Ограничение
сравнения: не было (обе off-пробы дочитали префикс). Одна цель (target 0) в обеих фазах.
Sampler rc0 подтверждает завершение сбора, не работоспособность VPN. Prefix 32769 — только
проверенный префикс. Plain может идти direct по исключению; VPN-egress/полное тело/все
приложения этим не доказываются. DNS-on не измерен: IP готовы до on.

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
категория неизвестности с причиной child_deadline, не отказ). Отклонения: единственное —
пересоздание каталога заметок с явного разрешения владельца (каталог создан мной до старта
ТЗ; содержимое — только plan.md). Новых каталогов/повторных enable/повторной установки
нет: один enable, один snapshot-набор (offcheck + enable). Частичный сбор: нет — job
finished rc0, все четыре категории JSON присутствуют (baseline, off-diagnostic,
enable-result, on-observations); единственная неизвестность — сам вызов loaded при on
(child_deadline, быстрые факты сохранены).

Итоговое: HEALTHY с 02.11 09:54; capture off; pool off; ядра Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и
модели — живая.

**Атрибуция plain-отказа (главный вопрос волны):**
- Отказ воспроизведён на новом коде: plain при on — ConnectionRefusedError на tcp-фазе
  за 0.065 с (в wave3e — 0.089 с), marked при on — 32769/200; carrier 1 в обеих точках;
  в off тот же plain читал 32769/200 за 0.251 с. Пути различаются — подтверждено.
- «Известная неисправная база» НЕ найдена (STOP-условие не сработало): off-diagnostic
  полностью чист (loaded=true/measured, mismatch=false, inbound_problem=false, IPv4
  listener на loopback); on-кандидаты из матрицы исключены: hold-block/effective-blocked —
  нет (requested=on, effective=on, inbound_problem=false); «TPROXY IPv4 listener
  отсутствует» — нет (ipv4_loopback=true, tcp_read=true при on); proxy-lookup при on →
  lo/local/tproxy — модель policy-lookup ведёт на lo, как ожидается для tproxy.
- Причина этими данными НЕ локализована: policy lookup не доказывает фактический проход
  пакета, LISTEN не доказывает accept/PID; по матрице следующим отдельным опытом нужно
  наблюдение конкретного flow. Это НЕ доказательство выключенного Ethernet и не вывод о
  ТСПУ: в off plain работал, marked при on работает, carrier 1.
- Проверка соответствия политики (Capture.loaded) при on осталась неизвестной в обоих
  прогонах: wave3e — поле с неожиданным типом, wave3f — null/child_deadline (child не
  уложился в 4 с). Loaded=true при on не получено ни разу; guard_present=true и
  capture_enabled=true — косвенные признаки, не замена loaded.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта. Эта проверка enable не смешивается
с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3f-2026-11-02.md, коммит «Отчёт: XGW
0.2.0, wave3f — короткий enable», push в freepool (REPORT_PUBLISHED в финальном сообщении).
В Git только этот Markdown; notes/measurements.jsonl/snapshot/off.nft/job.log/
enable-cli.log/URL-адреса остались вне репозитория.
