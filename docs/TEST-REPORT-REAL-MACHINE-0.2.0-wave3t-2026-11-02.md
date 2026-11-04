# Отчёт: XGW wave3t — расширенный автоматический пакет из семи этапов

Дата/время MSK: 2026-11-02, 22:02:45–22:15+03 (сбор 364.31 с + подготовка отчёта).
Модель GLM-5.3-Flash (ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255,
nftables v1.0.9 (Old Doc Yak #3) (S1.3, записано буквально; не обновлялся). Ядра:
Xray 26.10.31 / sing-box 1.14.4.
Tested HEAD 1e02778c3779d81b5fd0dd3bc82ef3c30472d5f2 / tree
e2aeefb513d5650dae41afe7ea806ae8e26a1068. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_extended_batch.py +
unit-тест); продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
Полное .py-дерево: installed_python_tree_equal=True, 110=110 модулей
(INSTALLED_PARSER_TREE_OK).
6 frozen SHA (EXTENDED_BATCH_FROZEN; /run/xgw-w3t 0700, файлы root600):
wave3_extended_batch.py 9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb
(единственный CLI start/status/show; _worker вручную не вызывался); wave3_reality_contract.py
3fbc8fdd…; wave3_single_bridge.py 66128dda…; wave3_bridge_diagnostic.py e77d441e…;
wave3_bridge_probe.py 2f023032…; wave3_on_observer.py 0db2acf6… — библиотеки, их
main/run/request/journal не вызывались; T2 разбирал кэши НЕЗАВИСИМОЙ реализацией (без
parse_body/parse_links_text/convert XGW).
Исходный/конечный: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (рабочий on, не
переключался); pool «выключен»; Tailscale route=vpn; связь владельца и модели живая.
Отклонение старта: первый `sudo -n true` отказал — NoNewPrivs=1 на процессе ZCode
(появился между 21:26 и 22:02; наследовался всему дереву; sudo в канале невозможен в
принципе, причина не в кэше/пароле). Повтор после первого ответа владельца — снова
отказ. Владелец перезапустил ZCode; после его сообщения выполнена ТОЛЬКО повторная
read-only проверка: SUDO_OK, NoNewPrivs=0 — прогон продолжен с S1.2b в том же сеансе.
Сеть/продукт во время паузы не трогались.
Start command rc: 0, маркер EXTENDED_BATCH_STARTED; monitor: BATCH_PROGRESS
T7 samples 1–11 → BATCH_FINISHED; show rc 0, wrapper.file=**summary.json** (финальный
итог, не partial/progress); финальный маркер **EXTENDED_BATCH_RECORDED**; elapsed
364.31 с; network_requests=**0** (ни одного нового соединения или активной проверки).

| Этап | Collection | Факты/числа/bools | Semantic decision | Ограничения |
|---|---|---|---|---|
| T1 history | RECORDED | S_source_consistency=true; current_config_matches_R_plan=**false**; lineage NOT_ESTABLISHED; old_endpoint_identity=UNPROVEN | Контекст R: конфиг уже ≠ R-плану (дрейф после S); reference-кейс остаётся по сохранённому ключу, R-атрибуция сверх ключа невозможна | Совпадение digest — не доказательство lineage; дрейф не назначается владельцу/сервису |
| T2 independent | RECORDED | configured=3, read=3; supported_records=8 (все из BASE64_LINKS); 2 PLAIN_JSON — 0 supported; unsupported_or_ambiguous=9; лимиты (32/2MiB/8MiB/5000) не достигнуты; fp-конвенция: ABSENT_FP_USES_PRODUCT_CHROME_CONVENTION_NOT_SOURCE_EXPLICIT | Покрытие — только явно поддержанное подмножество (VLESS TCP/raw); 0 records в PLAIN_JSON ≠ пусто/ошибка | Это не свежий ответ сервера/не wire; unsupported не додумываются |
| T3 all VLESS | RECORDED | default_vless_outbounds=67; equal_supported=**6**; mismatched=**0**; no_unique_supported_record=**61**; reference_case: NO_UNIQUE_SUPPORTED_RECORD (matching_records=0, distinct=0) | Сверок с уникальной записью: 6/67 равны, 0 несовпадений; 61 — NOT_RUN сверка (не mismatch); reference 12-полевая сверка NOT_RUN | Равенство подмножества ≠ семантика DNS/staticIPs/bind/extras; «лучший вариант» не выбирался |
| T4 all graph | RECORDED | bridges=141 (d=71, f=67, m=3); reality_outbounds=135; xray_bridge_references=3; bad_xray_references=0; duplicate_listener_ports=0; noncanonical=0; reality invalid key/short_id form=0/0; route_schema_violations=0; routing_mark_key_count=0; unmatched_local_socks_references=0; final_reject=true | Статический граф файлов согласован (все bad-counts нулевые) | Граф ФАЙЛОВ, не живой Xray-API/packetproof; нулевые bad-counts ≠ работа всех профилей; форма ключей ≠ серверные ожидания |
| T5 health | RECORDED | query_ok=true; rows=90; truncated=false; verdicts: OK=76, CONNECT_FAIL=7, TIMEOUT=6, SLOW=1; OK_bodies_under_32769=38; age_under_300s=**0**, age_over_300s=**90**; core_identity UNSPECIFIED_IN_SCAN_SCHEMA | Вся сохранённая история устаревшая (свежих сканов нет — active health по ТЗ не запускался); OK 305B ≠ BODY 32769 | Возраст записи ≠ новый успех; verdicts не привязаны к конкретному узлу в отчёте (identity в схеме отсутствует) |
| T6 journals | RECORDED | xgw: query_ok, rows=8, error_priority=0, все категории 0; xgw-singbox: query_ok, rows=0, категории 0; parse_errors=0, truncated=false (оба) | В свежих 10-минутных окнах ошибок по категориям не найдено; пусто/ноль ≠ «ошибок нет глобально» | counts пересекаются/могут быть INFO; не приписываются старым R/SB1 |
| T7 passive LAN | RECORDED | samples=12, elapsed 33..364 с; carrier=1 ×12; LAN_identity_same/context_ok/settings_same/singbox_process_same=true ×12; дельты LAN rx +35 774 669 / tx +924 284 684 байт (суммарно) | Счётчики двигались, носитель и контекст стабильны весь интервал; pассивно, без новых проб | Byte counters включают служебный трафик; positive ≠ VPN egress/конкретный клиент; не повтор L 608 с |

Каждая строка заполнена; недоступных этапов не было (ни одного phase UNAVAILABLE,
global stop, after stop, error class; финальный summary, не partial).

## Контекст и остановки

Before/after (оба сняты): capture true до/после; guard query=ok, postrouting/10/
forward/drop=5/reject=0 в обоих; службы active ×6; sing-box nonprivileged, uid/gid
match, forbidden groups absent, caps 0×5, NoNewPrivs; DAC expected ×4; pool_mode=off,
router ap, tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1;
files_unchanged_during_read=true ×3 в обоих.
on_context_preserved=true; settings_unchanged=true ×3; bridge_config_unchanged=true
(внутри T — дайджест до/после совпал; при этом T1: конфиг ≠ R-плану — дрейф ДО старта T,
не внутри); xray_config_unchanged=true; same_singbox_process=true; same_boot=true;
service_pid_same=true ×6; pin_record_readable_before_after=true/true;
pin_record_unchanged=true; cache_inputs_unchanged=true (3 прочитанных входа — реальное
сравнение); all_context_checks_ok=true (не заменяет отдельные поля).
Остановки: первый STOP только S1.2b (BLOCKED_TOOL_SUDO, устранён перезапуском ZCode
владельцем — см. выше); внутри worker'а остановок не было. NETWORK_REQUESTS=0; никаких
мутаций продукта/сети/служб/правил/pin/пула; off-rollback/таймер не запускались;
действий владельца в пакете не было (кроме описанного перезапуска приложения между
попытками S1.2b — вне сетевого контура шлюза); конечная связь живая.

## Консолидированное решение

Принятые факты (scope сохранён): M 6/6 permission boundaries; L 608 с on-observation;
J parser speedup (short-host + loaded=true); SB-2 positive (206/32769); S REALITY
contract consistency (на тот момент 12/12, digest=R-плану); R negative (curl97/0 body,
journal REALITY literal). Сохранены без пересмотра: N partial (1/2 BODY_OK);
P blocked (request 0, UNRECORDED); Q readonly принят (currentgate против O).
ТСПУ/падение сервера/дефект изоляции не назначены.

Обнаруженные static mismatch/coverage gap (без raw, без ремонта):
1. **Дрейф конфига SB повторился**: в T1 current_config_matches_R_plan=false — после S
   (где было true) конфиг снова отличается от сохранённого плана. bridge_config_unchanged
   внутри T=true → изменение между прогонами, не внутри пакета. Наблюдение → гипотеза:
   конфиг SB регулярно регенерируется (расписание/события сервиса), и digest-сверки со
   старыми планами будут расходиться после каждой регенерации; недостающий факт —
   механизм и момент регенерации (writer config lineage), вне досягаемости этого пакета.
2. **Reference-кейс не привязывается к независимым записям**: T3 reference NO_UNIQUE_
   SUPPORTED_RECORD (0 совпадений среди 8 supported records) — 12-полевая сверка
   reference-кейса NOT_RUN. Гипотеза: нужная запись находится в неподдержанной части
   источников (9 unsupported_or_ambiguous, 2 PLAIN_JSON с 0 supported) либо ключ/запись
   устарели вместе с дрейфом конфига; недостающий факт — разбор остальных носителей
   безопасным независимым парсером будущего тестового helper'а (не продукт).
3. **Static mismatch НЕ обнаружен**: 0 mismatched contracts (T3), все bad-counts T4
   нулевые, формы REALITY корректны (135/135), дубликаты портов/битые ссылки Xray
   отсутствуют. Дефектных свидетельств в статических слоях нет — так и зафиксировано,
   выдумывать нечего.
4. **Health-история вся устаревшая** (90/90 старше 300 с; исторические вердикты
   OK=76/CONNECT_FAIL=7/TIMEOUT=6/SLOW=1, короткие OK-тела 38): свежего состояния узлов
   пакет намеренно не даёт (active health запрещён) — недостающий факт для REALITY-
   гипотезы R.

Упорядоченный backlog (не патчить продукт; шаги — будущие отдельные решения разработчика):
1. Свежее health-состояние reference-сервера: измерено — только устаревшая история (T5)
   и два отказных окна (N, R); не хватает — одного разрешённого активного скана конкретного
   случая по согласию владельца либо проверки владельцем свежести подписки/сервера вне
   теста; минимальный шаг — узкое ТЗ с одним активным health одного кейса.
2. Config lineage SB: измерено — digest-отношения Q/S/T и file-times; не хватает —
   журналов/механики writer'а конфига (когда и что регенерирует); минимальный шаг —
   read-only разбор единиц регенерации в журналах/юнитах отдельным ТЗ.
3. Расширение независимого покрытия источников (T2/T3): измерено — 8 supported/9
   unsupported/2 PLAIN_JSON пустых по поддержанному подмножеству; не хватает — безопасной
   независимой обработки остальных носителей; минимальный шаг — новый тестовый helper
   (не продукт), только чтение локальных кэшей.
4. Продуктовый runtime-патч НЕ обоснован: статических дефектов не найдено; gateway
   не менялся.

| Открытый этап | Статус | Причина/недостающее доказательство |
|---|---|---|
| D1-on install | NOT_RUN | Нет согласованного клиентского опыта и независимого возврата on; install/g1 запрещены этим ТЗ |
| Scoped faults | NOT_RUN | Внесение отказов при рабочем on требует отдельного согласия и recovery-плана; здесь исполнителя нет |
| E4 packet attribution | NOT_RUN | Packet capture/promiscuous запрещены; нет безопасно подготовленного исполнителя |
| LAN UDP | NOT_RUN | Активные UDP-пробы = новые соединения, запрещены; «LAN сломана» не утверждается |
| IPv6 | NOT_RUN | Нет разрешённых активных проверок; сводится к отсутствию исполнителя, не к дефекту |
| DNS end-to-end | NOT_RUN | Активные DNS-пробы запрещены; leak-проверка вне scope пакета |
| All Tailscale paths | NOT_RUN | Активные пути требуют согласия; derp-настройка фиксирована, путь не тестировался |
| VPN speed/ping | NOT_RUN | speed/ping/benchmarks запрещены; time_total/счётчики ≠ скорость (включая T7) |

Acceptance по scope: пакет wave3t принят как ЕДИНЫЙ read-only сбор семи этапов с
полным сохранением рабочего контекста (EXTENDED_BATCH_RECORDED, summary.json,
network_requests=0). Wave3 целиком НЕ закрыта: D1-on/E4/faults/UDP/IPv6/DNS/allTS/
performance остаются открытыми; wave4/DAE не начинались. Рабочая LAN работает и не
объявлена неисправной. Одно финальное уведомление владельцу — этим сообщением.
Privacy просмотр ДО gitadd: только этот Markdown; private план/дайджесты/значения
полей/show.json/raw кэши/journal остались вне Git. Путь
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3t-2026-11-02.md, коммит «Отчёт: XGW 0.2.0,
wave3t — расширенный автоматический пакет из семи этапов», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56,
перехват ВКЛЮЧЁН, pool прежний; связь живая.
