# Отчёт: XGW 0.2.0 — wave3e, короткий enable

Дата начала 2026-11-02 (run-start 09:03:54+03), завершение ~09:14+03 (MSK). Модель:
GLM-5.3-Flash (ZCode), терминал владельца; машина ThinkCentre, Ubuntu 24.04.5 LTS,
systemd 255. Tested HEAD: 19548f7ea5efe3fd93c59ed81e499684cbc036cf; tree:
0e40c38cf63ea9989c2768ec8f377411b3f87994. Code pin 1d62fadfc0464912dec3142352cd285718be5e6a —
предок HEAD; runtime diff (src, packaging, tests/stand/wave3_safety.py,
tests/stand/wave3_enable_probe.py, config.example.toml, pyproject.toml) пуст;
отдельно продуктовый код против 2862767 — diff пуст.
Installed install.py/net/sysctl.py/diag.py equal×3: True (INSTALLED_SOURCE_OK).
Frozen guardian wave3_safety.py SHA256
c72f8078a869c04d19e39f17938f8f77b2164f7859f271b19baae276b31ce93b, root:root 0700;
frozen sampler wave3_enable_probe.py SHA256
903f7f3f3ee99ad9ffe560d412e42ad3bbe2569ada238ef4abf55b42821c3feb, root:root 0700
(FROZEN_IDENTITY_OK; sampler_sha256 в baseline.json совпал).
Согласие §2.2: получено перед P1 (AskUserQuestion) — один краткий enable, возможный обрыв
прежних direct-сессий и связи модели, GET к настроенным HTTPS-целям с чтением префикса
(32769 байт), обязательный возврат off через 25 с, остановка и последующий старт контроллера,
бюджет ~30 с без абсолютных гарантий.
Дополнительные прямые указания владельца: (а) разрешение удалить заранее созданный мной
пустой каталог заметок $HOME/xgw-w3e (S1.2 требует новый; содержимое — только мой plan.md
до старта прогона); (б) владелец сам выполнил `sudo -v` в настоящем терминале по моей
просьбе — инструментальный канал без TTY пароль запросить не может. Оба — отклонения от
буквы протокола, зафиксированы; на сетевые опыты не влияли.

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | HEALTHY с 02.11 08:57; «Перехват: СНЯТ (xgw disable)»; «выключен; регион EU (строго)» |
| Xray / sing-box версии | Xray 26.10.31; sing-box 1.14.4 |
| Pin (только безопасный tag) | spare-de-0b0e (down=false), PIN_STATE_OK |
| Службы xgw/Xray/SB/DHCP/xgw-net | active ×5 (xgw-net — отдельным фактом) |
| Старые safety/job units inactive | OLD_TRIALS_INACTIVE (w3b/w3c/w3d ×safety/job) |
| Связь владельца/модели до окна | обе живые (владелец отвечал на согласие; команды проходили) |
| Состояние/неизменность настроек Tailscale | NOT_RUN (не проверялся; не менялся) |

## 3. Гейты выполнения

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | PASS | Linux; OWNER_SHELL_OK; NOTES_CREATED 09:03:54+03; sudo-кэш обновил владелец (см. отклонения); согласие §2.2 получено |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | PASS | SOURCE_PREFLIGHT_OK; INSTALLED_SOURCE_OK ×3; база см. §2 |
| S3 | 2 frozen файла: SHA/owner/mode | PASS | FROZEN_COPY_CREATED; FROZEN_IDENTITY_OK (root:root 0700, обе SHA совпали) |
| S3.3 | Read-only context | PASS | {"tracked_job_context": true, "euid_root": true}; unit завершился success 227 ms; после — inactive |
| P1 | Подготовленный off snapshot, WAN facts известны | PASS | PREPARED; facts all_verified=true (6×true) |
| P2 | Непродлеваемое off-window 25 с, без pulse | PASS | unit запущен; pulse/disarm не отправлялись |
| P2 | RESTORED_OFF и nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| P2 | total / recovery | PASS | seconds_since_last_pulse 25.11; recovery_seconds 0.11 |
| P2 | WAN facts/links и связь после возврата | PASS | all_verified=true; WAN/LAN up/1; plain/marked на B1; связь живая |
| P3 | Старт контроллера, новая HEALTHY/off база | PASS | HEALTHY с 09:09; off; pool off; PIN_STATE_OK; CORE_UNITS_OK |
| B1 | Новый snapshot перед enable, WAN all_verified | PASS | PREPARED; all_verified=true |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | PASS | ready=true; healthy=true (plain 0.306 с, marked 0.278 с — оба body/32769/200) |
| E1 | Одна launch-команда | PASS | {"started":"enable","fixed_window_seconds":25,"rollback":"always_off","pulse_required":false} |
| E1 | Команды/вмешательство внутри окна | PASS | от launch до чтения R1 — только `sleep 35`; pulse/disarm/panel/pin не трогались |
| R1 | Guardian RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0 |
| R1 | total/recovery enable-окна | PASS | ssLP 25.167; recovery_seconds 0.167 |
| R1 | Capture off / links / WAN unchanged | PASS | capture_enabled=false; links up/1; facts all_verified=true |
| R1 | Реальный enable-result.rc / seconds | PASS | rc=0, seconds=9.279 (enable завершился внутри окна) |
| R1 | Sampler job-result.state / rc | PASS | state=finished, rc=0 (сбор завершился целиком) |
| R2 | Разрешённый старт контроллера / HEALTHY/off | PASS | HEALTHY с 09:11; off; pool off; PIN/CORE OK |

## 4. Во время on: локальные observations

| Stage | capture_enabled | guard_present | WAN | LAN | Ограничение |
|---|---|---|---|---|---|
| before_enable | false | false | up/1 | up/1 | при off отсутствие guard ожидаемо |
| after_enable | **true** | **true** | up/1 | up/1 | — |
| after_https | **true** | **true** | up/1 | up/1 | сбор завершился до rollback |

Capture.loaded во время окна: **UNKNOWN** (stage=loaded, поля нет — проверка не завершилась;
по матрице не превращать в True/False).

## 5. HTTPS: baseline и on

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | 0 | plain | body | 200 | 32769 | prefix_ok | 0.306 |
| off | 0 | marked | body | 200 | 32769 | prefix_ok | 0.278 |
| on | 0 | plain | **tcp** | — | 0 | **ConnectionRefusedError** | 0.089 |
| on | 0 | marked | body | 200 | 32769 | prefix_ok | 0.289 |

Ready_for_enable: true. Baseline_healthy: true (ограничения сравнения не было).
Одна цель (target 0) в обеих фазах. По матрице интерпретации: plain не работает, marked
работает, carrier 1 — **пути различаются; причина (capture/маршрут/узел/цель) требует
атрибуции**. Это НЕ доказательство выключенного Ethernet и не вывод о ТСПУ: в off тот же
plain-путь читал 32769 байт за 0.306 с. Plain при on может уходить direct по разрешённому
исключению маршрутизации; refused на TCP-фазе при marked-успехе того же этапа — факт
для расследования. VPN-egress, полное тело, все приложения и DNS-on этим не доказаны.

## 6. WAN и связь

| WAN fact | До enable (B1) | После off-rollback (R1) |
|---|---|---|
| profile | true | true |
| addresses | true | true |
| live_gateway_dns | true | true |
| route4 | true | true |
| route6 | true | true |
| mtu | true | true |
| all_verified | true | true |

| Канал | До | Во время on | После off |
|---|---|---|---|
| Владелец | жив | UNKNOWN (не наблюдалось;rollback вернул off до опроса) | подтверждён |
| Модель/инструмент | жив | UNKNOWN (команды внутри окна не требовались и не посылались) | подтверждён |
| Tailscale | NOT_RUN | NOT_RUN | NOT_RUN |

## 7. Отклонения, итог и незакрытые ворота

Последний успешный ID шага: R2. Отказов гейтов не было (все PASS; loaded=UNKNOWN —
категория неизвестности, не отказ). Отклонения: (а) пересоздание каталога заметок с явного
разрешения владельца (каталог создан мной до старта ТЗ); (б) sudo-кэш обновлял владелец в
настоящем терминале — канал модели без TTY; (в) других отклонений и повторных
mutating-действий нет: один enable, один snapshot-набор, новых каталогов/trial не создавалось.
Частичный сбор: нет — sampler finished rc0; единственная неизвестность — loaded=UNKNOWN
(stage записан без поля).
Итоговое: HEALTHY с 09:14; capture off; pool off; ядра 26.10.31/1.14.4; pin
spare-de-0b0e; службы xgw/Xray/SB/DHCP/xgw-net active; связь владельца и модели — живая.
По D2: короткий enable (9.3 с) и rollback (0.17 с) прошли без наблюдаемой потери связи
каналов; внутри on-окна связь не наблюдалась непрерывно (during_on=UNKNOWN) — заявлять
«потерь нет» нельзя; plain-отказ на TCP-фазе при живом marked — отдельный факт для
атрибуции (не «Ethernet выключен»: carrier 1 в обеих точках, marked прошёл, off-plain прошёл).
D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта. Эта проверка enable не смешивается
с успешной отдельной установкой из отчёта wave3d.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3e-2026-11-02.md, коммит
«Отчёт: XGW 0.2.0, wave3e — короткий enable», push в freepool (см. REPORT_PUBLISHED в
финальном сообщении). В Git только этот Markdown; notes/measurements.jsonl/snapshot/
off.nft/job.log/enable-cli.log/URL-адреса остались вне репозитория.
