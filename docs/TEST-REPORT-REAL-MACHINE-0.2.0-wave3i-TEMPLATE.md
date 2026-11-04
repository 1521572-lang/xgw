# Отчёт: XGW 0.2.0 — wave3i, guard JSON/native и журнал чтения, короткий enable

Это шаблон. Все фактические значения первоначально NOT_RUN. Ожидаемые значения ТЗ и
исторические измерения не подставлять в результат. Удалить пояснение «шаблон» после заполнения.

## 1. Идентичность и согласие

| Поле | Фактическое значение | Источник |
|---|---|---|
| Начало/конец, таймзона | NOT_RUN | run-start.txt / фактическое завершение |
| Модель/инструмент/машина/ОС/systemd/nft version | NOT_RUN | наблюдение |
| Tested HEAD | NOT_RUN | S2.1 |
| Tested tree | NOT_RUN | S2.1 |
| Code pin | f78c2f1432ae56cdec8e229b59f33b9ee4723760 | ТЗ, проверить ancestry |
| Runtime diff / source marker | NOT_RUN | S2.1 |
| Installed install.py/net/sysctl.py/diag.py/net/nft.py equal×4 | NOT_RUN | S2.3 |
| Frozen guardian SHA256/owner/mode | NOT_RUN | S3.2 |
| Frozen sampler SHA256/owner/mode | NOT_RUN | S3.2 |
| Согласие: scope/ответ/время | NOT_RUN | до P/E |
| Дополнительные прямые указания владельца | NOT_RUN | факты; не цитировать старый отчёт как новое разрешение |

## 2. Исходная база

| Поле | Факт |
|---|---|
| HEALTHY / capture off / pool off | NOT_RUN |
| Xray / sing-box версии | NOT_RUN |
| Pin (только безопасный tag) | NOT_RUN |
| Службы xgw/Xray/SB/DHCP/xgw-net | NOT_RUN |
| Старые safety/job units inactive | NOT_RUN |
| Связь владельца/модели до окна | NOT_RUN |
| Состояние/неизменность настроек Tailscale | NOT_RUN |

## 3. Гейты выполнения

Допустимые категории: PASS / FAIL / INCONCLUSIVE / NOT_RUN. В колонке evidence указать
фактические поля или имя безопасного артефакта. Отсутствующее наблюдение не заменять PASS.

| ID | Проверка | Категория | Фактическое evidence |
|---|---|---|---|
| S1 | Linux/owner shell/новые заметки/sudo/согласие | NOT_RUN | — |
| S2 | Source + installed identity, HEALTHY/off/pool, службы | NOT_RUN | — |
| S3 |2frozen файла: SHA/owner/mode | NOT_RUN | — |
| S3.3 | Read-only context: tracked_job_context/euid_root, job завершился | NOT_RUN | — |
| P1 | Подготовленный off snapshot, WAN facts известны | NOT_RUN | — |
| P2 | Непродлеваемое off-window25с, без pulse | NOT_RUN | — |
| P2 | RESTORED_OFF и nft_rc | NOT_RUN | — |
| P2 | total seconds_since_last_pulse / recovery_seconds | NOT_RUN | — |
| P2 | WAN facts/links и связь после возврата | NOT_RUN | — |
| P3 | Старт контроллера, новая HEALTHY/off база | NOT_RUN | — |
| B1 | Новый snapshot перед enable, WAN all_verified | NOT_RUN | — |
| B1 | Off diagnostic schema/mode/inbound/LISTEN/mismatch/lookup/diagnostic_gate | NOT_RUN | — |
| B1 | Baseline ready_for_enable и baseline_healthy раздельно | NOT_RUN | — |
| E1 | Одна launch-команда, independent safety→tracked job | NOT_RUN | — |
| E1 | Команды/вмешательство внутри окна | NOT_RUN | — |
| R1 | Guardian RESTORED_OFF / nft_rc | NOT_RUN | — |
| R1 | total/recovery отдельного enable-окна | NOT_RUN | — |
| R1 | Capture off / links / WAN unchanged | NOT_RUN | — |
| R1 | Реальный enable-result.rc / seconds | NOT_RUN | — |
| R1 | Sampler job-result.state / rc (не rc enable) | NOT_RUN | — |
| R2 | Разрешённый старт контроллера / HEALTHY/off | NOT_RUN | — |

## 4. Во время on: локальные observations

Frames имеют логический порядок; не придумывать для них точное время, если timestamp
не сохранён. Carrier/guard/query не являются атомарным снимком всей сети.

| Stage | capture_enabled | guard_present | WAN operstate/carrier | LAN operstate/carrier | Ограничение |
|---|---|---|---|---|---|
| before_enable | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | при off отсутствие guard ожидаемо |
| after_enable | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | guardfalse не доказывает ENOENT |
| after_https | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | может отсутствовать при deadline |

Capture.loaded во время окна: NOT_RUN. Источник: on-observations stage=loaded.
Loaded_reason/child_rc/phase: NOT_RUN. Schema consistency: NOT_RUN.
UNKNOWN/null не превращать вFalse/True. Отсутствующая строка — partial, строка без поля —
ошибка формата/переноса; не объявлять её автоматически таймаутом.

### 4.1. Диагностика off/on

| Поле | OFF (off-diagnostic.json) | ON (stage=loaded) | Ограничение |
|---|---|---|---|
| schema/phase | NOT_RUN | NOT_RUN | — |
| loaded/reason/child_rc | NOT_RUN | NOT_RUN | null не False |
| capture_method/configured_local/configured_lan | NOT_RUN | NOT_RUN | конфиг не менялся |
| requested_mode/effective_mode | NOT_RUN | NOT_RUN | расчёт библиотеки, не trace |
| inbound_problem_present | NOT_RUN | NOT_RUN | не PID/фактический accept |
| mismatch_present | NOT_RUN | NOT_RUN | — |
| guard worker query/source/host_hook/host_priority/forward_hook | NOT_RUN | NOT_RUN | stageguard, postrouting10/forward приon |
| guard_layout host_drop_rules/host_reject_rules | NOT_RUN | NOT_RUN | >=1/0; число правил, не пакетов |
| context/capture_enabled_now/child_budget_seconds | NOT_RUN | NOT_RUN | context — запрос, не доказательствоon |
| tcp_read/ipv4_any/ipv4_loopback/tcp_other_address | NOT_RUN | NOT_RUN | только LISTEN на точном порту |
| tcp6_read/ipv6_any/ipv6_loopback/tcp6_other_address | NOT_RUN | NOT_RUN | V6ONLY не измерен |
| routes.unmarked type/device_role/table_role или query/rc | NOT_RUN | NOT_RUN | unmarked→WAN не обход |
| routes.proxy type/device_role/table_role или query/rc | NOT_RUN | NOT_RUN | lookup, не поток |
| routes.bypass type/device_role/table_role или query/rc | NOT_RUN | NOT_RUN | lookup, не поток |
| diagnostic_gate | NOT_RUN | неприменимо | gate не PASS VPN |

В on четыре задачи параллельны; строки сохраняются по готовности, не по порядку протокола.
Отсутствующие поля — UNKNOWN, не восстанавливать из off. Ни имён NIC, ни table ID, ни адресов.

### 4.2. Checkpoint и неполные измерения

Наличие7 категорийJSON: NOT_RUN. Kernel-diagnostic.json context/capture_enabled_now/phase:
NOT_RUN. Stage=loaded и checkpoint согласованы/отсутствуют/расходятся: NOT_RUN.
Какие факты взяты из раннего checkpoint при неполном event: NOT_RUN. Не переносить off вon.
Loaded_reason/child_rc/budget у final event: NOT_RUN. Pending checkpoint не False/не PASS.
Последняяphase подтверждает границу прогресса, а не конкретный syscall/причину задержки.
Повторной установки/G1/замены nft.py не предусмотрено; фактические отклонения: NOT_RUN.

### 4.3. Independent guard attempts

Stageguard и on-guard.json совпадают: NOT_RUN. Capture_enabled_before/after: NOT_RUN.
Query/source/host_hook/host_priority/forward_hook/drop_rules/reject_rules: NOT_RUN.

| Context | Encoding | State | Rc/error_class | Budget | Seconds | Stdout/stderr bytes |
|---|---|---|---|---|---|---|
| off | json | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| on | json | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| on | text fallback | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

Если fallback не выполнялся, отметить NOT_RUN с фактической причиной, не подставлять успех.
State timeout отличается от nonzero/parse-schema. Raw stdout/stderr не включать.

### 4.4. Loaded read trace

Readonly_violation/truncated: NOT_RUN. Последняяphase и active stack: NOT_RUN.

| Id | Label | State/error_class | Begin seconds | Seconds если завершён |
|---|---|---|---|---|
| NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

Перенести все полученные records (максимум48), не придумать отсутствующие. Nested времена
перекрываются; returned не означает loadedTrue; active не является syscall trace. Overhead
wrappers/checkpoint включён. Приtruncated часть вызовов не видна. Никаких argv/адресов.

## 5. HTTPS: baseline и on

Включить все фактически полученные строки baseline, если использовалась вторая цель.
Цели обозначать только номером; домен/IP/URL/HTTP-тело не включать. bytes=null не равно0.

| Момент | Цель№ | Путь | phase | HTTP status | bytes | outcome | seconds |
|---|---|---|---|---|---|---|---|
| off | NOT_RUN | plain | NOT_RUN | — | — | — | — |
| off | NOT_RUN | marked | NOT_RUN | — | — | — | — |
| on | NOT_RUN | plain | NOT_RUN | — | — | — | — |
| on | NOT_RUN | marked | NOT_RUN | — | — | — | — |

Ready_for_enable: NOT_RUN. Diagnostic_gate: NOT_RUN. Baseline_healthy: NOT_RUN. Ограничение сравнения при unhealthy
baseline: NOT_RUN. Sampler rc0 подтверждает завершение сбора, не работоспособность VPN.
Prefix32769 означает только проверенный префикс. Plain может идти direct по исключению;
VPN-egress/полное тело/все приложения этим не доказываются. DNS-on не измерен: IP готовы до on.

## 6. WAN и связь

| WAN fact | До enable (B1) | После off-rollback (R1) | Интерпретация |
|---|---|---|---|
| profile | NOT_RUN | NOT_RUN | — |
| addresses | NOT_RUN | NOT_RUN | — |
| live_gateway_dns | NOT_RUN | NOT_RUN | — |
| route4 | NOT_RUN | NOT_RUN | — |
| route6 | NOT_RUN | NOT_RUN | — |
| mtu | NOT_RUN | NOT_RUN | — |
| all_verified | NOT_RUN | NOT_RUN | — |

False — изменение, null — неизвестность. DHCP/RA могли меняться самостоятельно; причинность
без evidence не установлена. Успешный повторный контакт не доказывает непрерывную связь.

| Канал | До | Во время on | После off | Источник наблюдения |
|---|---|---|---|---|
| Владелец | NOT_RUN | UNKNOWN | NOT_RUN | — |
| Модель/инструмент | NOT_RUN | UNKNOWN | NOT_RUN | — |
| Tailscale | NOT_RUN | NOT_RUN | NOT_RUN | — |

## 7. Отклонения, итог и незакрытые ворота

Последний успешный ID шага: NOT_RUN. Первый отказ/недоступность: NOT_RUN.
Отклонения/действия владельца вне штатного протокола: NOT_RUN.
Новых каталогов/повторных enable/повторной установки: NOT_RUN (записать факт, не образец).
Частичный сбор/отсутствующие категории JSON и причина неопределённости: NOT_RUN.

Итоговое HEALTHY/capture off/pool off/ядра/pin/службы и связь: NOT_RUN.
Самостоятельные выводы о D2 ограничить полученными фактами. Не объявлять ТСПУ/физический
link-down по одному CDN/ошибке или отсутствие потерь по sampled carrier.

D1-on-reinstall, E4/actualWAN packets, LAN/UDP/IPv6/DNS-on/Tailscale-on/scoped faults/
нагрузка: NOT_RUN по scope. Полная wave3 не закрыта. Не смешивать эту проверку enable с
успешной отдельной установкой из отчёта wave3d.

Публикация: фактический путь/commit/ссылка либо конкретный сбой. В Git только этот Markdown,
без notes/runtime/snapshot/probe-plan/enable-cli.log/job.log/тел HTTP/сырых журналов и адресов.
