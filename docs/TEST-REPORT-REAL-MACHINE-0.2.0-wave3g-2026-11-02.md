# Отчёт: XGW 0.2.0 — wave3g, исправление postrouting guard, короткий enable

Дата начала 2026-11-02 (run-start 10:44:40+03), завершение ~10:56+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255. Tested HEAD: 460bad37b27415e988880a5bb8952ef6c14eee3f; tree:
538605a61fb6ece9bf51c2a3d1d6a3d9ff0a7e81. Code pin
573b233bce881349e5ff4654600d3e077a9515f6 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) против pin пуст; продуктовый diff против 2862767 — только
src/xgw/net/nft.py (render_guard), как заявлено ТЗ. Installed
install.py/net/sysctl.py/diag.py equal×3: True (проверено до и после G1).
Frozen guardian wave3_safety.py SHA256
0a9c67334ad82f5cb09eb4919220b04d6ae42410a10e0a7e0492cdee34585f3d и frozen sampler
wave3_enable_probe.py SHA256
13116c2be9f6533e5edfbae4cd9ab673f85b30545ef7cf4f36118e4777a4aa20, root:root 0700;
payload nft.py.new SHA256
2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547, root:root 0600
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: получено 10:44+03 до подготовки (AskUserQuestion) — «Согласен
(рекомендую)»: один краткий enable, возможный обрыв прежних direct-сессий и связи модели;
GET к настроенным HTTPS-целям с чтением префикса тела (32769 байт); одна атомарная замена
установленного net/nft.py при off/остановленных писателях с SHA и backup (backup остаётся
в /run, новый файл остаётся установленным); обязательный возврат к текущему off через 25 с
с остановкой контроллера и его последующим стартом; номинальный бюджет ~30 с без
абсолютных гарантий. Дополнительных прямых указаний владельца сверх ТЗ не было; каталог
заметок с заранее извлечённым plan.md предусмотрен самим S1.2 (не отклонение).

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 10:30; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b/w3c/w3d/w3e/w3f ×safety/job — 10 units) |
| Связь владельца/модели до окна | живые (владелец ответил на согласие; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 10:44:40+03 (каталог только с plan.md — разрешено S1.2); SUDO_CACHE_OK; согласие §2.2 получено |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK (573b233 предок; diff vs 2862767 только nft.py); INSTALLED_SOURCE_OK ×3; OLD_NFT_SOURCE_OK (old_nft_sha_matches=true, safe_owner_mode=true); база см. §2 |
| S3 | 3 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (helpers 0700, nft.py.new 0600, все SHA совпали) |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | PASS | {"tracked_job_context": true, "euid_root": true}; success 259 ms; после — inactive (rc 4, ожидаемый) |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED (offcheck); facts all_verified=true, 6/6 true |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit xgw-w3g-safety запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было); daemon left_stopped_for_review |
| P2 | total seconds_since_last_pulse / recovery_seconds | PASS | 25.137 с (всё окно) / 0.136 с |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true (6/6); WAN/LAN up/carrier 1; mismatch_present=false; связь живая |
| G1 | Атомарный nft.py update/backup/newSHA/все 4 installed файла | PASS | NFT_CODE_UPDATED old_sha_verified=True new_sha_verified=True backup_verified=True (первая попытка); повторно INSTALLED_SOURCE_OK ×3 + NEW_NFT_SOURCE_OK + NEW_GUARD_SYNTAX_OK |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | start xgw; «HEALTHY с 02.11 10:30» — таймштамп восстановлен из сохранённого состояния (факт); off; pool off; PIN_STATE_OK; CORE_UNITS_OK ×5 |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED (enable); facts all_verified=true, 6/6 true |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | PASS | schema=1; off/off; configured_local=true; configured_lan=true (факт); inbound_problem_present=false; tproxy; loaded=true/measured/complete/child_rc=0; mismatch_present=false; listener tcp_read=true + ipv4_loopback=true; routes unmarked/proxy/bypass → unicast/WAN/main; guard_layout query=not_confirmed (в off допустимо); diagnostic_gate=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.229 с и marked 0.257 с — оба body/32769/200/prefix_ok) |
| E1 | Одна launch-команда, independent safety→tracked job | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery отдельного enable-окна | PASS | ssLP 25.172; recovery_seconds 0.171 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/carrier 1; facts all_verified=true (6/6) |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=8.801 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc (не rc enable) | PASS | action=enable, state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 02.11 10:48; off; pool off; PIN_STATE_OK spare-de-0b0e; CORE_UNITS_OK ×5; ядра 26.10.31/1.14.4 |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback (job finished rc0) |

Capture.loaded во время окна: **null** (неизвестность). Источник: on-observations
stage=loaded. Loaded_reason/child_rc/phase: **child_deadline / null / config**. Schema
consistency: schema=1, поля loaded/loaded_reason/child_rc присутствуют корректных типов —
строка валидна; это UNKNOWN с явной причиной, не False и не ошибка формата. Важно: в этой
строке быстрые факты ОТСУТСТВУЮТ (routes={}, поля mode/inbound/listener/guard_layout
отсутствуют) — child завершил бюджет раньше, чем в волне3f (там phase=loaded с
сохранёнными фактами, здесь phase=config). Fast facts при on: UNKNOWN без догадок.

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | 1 / complete | 1 / config | child on остановился на config |
| loaded/reason/child_rc | true / measured / 0 | **null / child_deadline / null** | null не False |
| capture_method/configured_local/configured_lan | tproxy / true / true | UNKNOWN (полей нет) | конфиг не менялся |
| requested_mode/effective_mode | off / off | UNKNOWN (полей нет) | расчёт библиотеки, не trace |
| inbound_problem_present | false | UNKNOWN (полей нет) | не PID/фактический accept |
| mismatch_present | false | UNKNOWN (полей нет) | — |
| guard_layout query/host_hook/host_priority/forward_hook | query=not_confirmed / — / — / — | **UNKNOWN** (не получено) | требуется postrouting10/forward при on |
| guard_layout host_drop_rules/host_reject_rules | — / — | **UNKNOWN** (не получено) | >=1/0 при on, не счётчики пакетов |
| tcp_read/ipv4_any/ipv4_loopback/tcp_other_address | true/false/true/false | UNKNOWN (полей нет) | только LISTEN на точном порту |
| tcp6_read/ipv6_any/ipv6_loopback/tcp6_other_address | true/false/false/false | UNKNOWN (полей нет) | V6ONLY не измерен |
| routes.unmarked | unicast/WAN/main | UNKNOWN (routes={}) | unmarked→WAN не обход |
| routes.proxy | unicast/WAN/main | UNKNOWN (routes={}) | lookup, не поток |
| routes.bypass | unicast/WAN/main | UNKNOWN (routes={}) | lookup, не поток |
| diagnostic_gate | true | неприменимо | gate не PASS VPN |

Отдельной строки с guard_layout при on нет; после rollback правила не подгружались и
enable не повторялся (запрещено ТЗ). В on три child параллельны; отсутствующие поля —
UNKNOWN, из off не восстанавливались. Ни имён NIC, ни table ID, ни адресов не выводилось.

### 4.2. Выборочное обновление кода

Исходный установленный nft.py SHA: 75057aaf1846a386fb694e9d1116d7a1c0569dfc60c3425f9a950ae4894a2b96
— совпал (S2.4 до замены и old_sha_verified в G1). Новый установленный nft.py SHA:
2739e81c63b78e2409c915ec1ad4fe794df3023173b4f65d924610bdf1b62547 — NEW_NFT_SOURCE_OK
после замены. G1: phase пройдены preconditions→backup→stage→replace→verify,
result=NFT_CODE_UPDATED (три True), backup_verified=True. Остальные 3 installed файла
(install.py/net/sysctl.py/diag.py) equal×3 — до и после замены. Новый guard nft -c syntax
check: NEW_GUARD_SYNTAX_OK (проверка applicability без загрузки). Приватный backup
root0600 сохранён в /run (в Git не включён). До замены xgw/xgw-net: stopped (после
RESTORED_OFF, проверено командой G1). Installer/WAN/config/sysctl/обновление ядер не
запускались. Сбоев замены не было; классификационный блок не потребовался. Новый файл
остаётся установленным после опыта; guardian вернул сетевой off, не версию кода.

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.229 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.257 |
| on | 0 | plain | **body** | 200 | 32769 | **prefix_ok** | 0.354 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.380 |

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

Последний успешный ID шага: R2. Отказов гейтов не было (все PASS; loaded=null и пустые
fast facts при on — категория неизвестности с причиной child_deadline/phase=config, не
отказ гейта). Отклонений от штатного протокола нет; прямых указаний владельца сверх
согласия §2.2 не было; новых каталогов/повторных enable/повторной замены nft.py нет:
одна попытка G1, один enable, snapshot-набор offcheck+enable. Частичный сбор: job
finished rc0, все четыре категории JSON присутствуют; внутри on-diagnostic не получены
быстрые факты и guard_layout (child-бюджет исчерпан на phase=config) — перенесено как
UNKNOWN, не восстанавливалось предположением.

Итоговое: HEALTHY с 02.11 10:48; capture off; pool off; ядра Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и
модели — живая. Установленный net/nft.py — новая версия (2739e81c), backup прежней
(75057aaf) — root0600 в /run.

**Главный результат:**
- Функционально дефект wave3e/wave3f НЕ воспроизвёлся: plain при on впервые прошёл
  (body/32769/200/0.354 с) после переноса host guard на postrouting; в двух прежних
  прогонах на том же пути был ConnectionRefusedError на tcp-фазе (0.065–0.089 с).
  Это факт одного запуска, не доказательство устойчивости и не полное доказательство
  механизма: guard_layout при on не подтверждён (UNKNOWN), VPN-egress не доказан.
- Атрибуция механизма (query=ok, host_hook=postrouting, priority 10, forward hook,
  drop≥1/reject=0) при on НЕ получена — по R1.4 исправленная фактическая политика не
  подтверждена layout-проверкой; матричная строка «короткий host TCP кейс» применена
  лишь частично: enable rc0, plain/marked prefix_ok и успешный rollback есть, layout —
  unknown. Наблюдение конкретного flow остаётся отдельной будущей проверкой.
- Проверка Capture.loaded при on неизвестна в третьем прогоне подряд (wave3f —
  child_deadline на phase=loaded с сохранёнными фактами; wave3g — child_deadline на
  phase=config, факты не успели). Loaded=true при on не получено ни разу; косвенные
  признаки on: capture_enabled=true, guard_present=true, mismatch_present=false,
  успешный plain/marked body.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта. Эта проверка enable не смешивается
с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3g-2026-11-02.md, коммит «Отчёт: XGW
0.2.0, wave3g — короткий enable», push в freepool (REPORT_PUBLISHED в финальном сообщении).
В Git только этот Markdown; notes/measurements.jsonl/snapshot/off.nft/job.log/
enable-cli.log/URL-адреса/backup остались вне репозитория.
