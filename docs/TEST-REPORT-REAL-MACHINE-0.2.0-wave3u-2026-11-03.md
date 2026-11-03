# Отчёт: XGW wave3u — расширенное покрытие источников и поколений конфигурации

Дата/время MSK: 2026-11-03, 08:04:52–08:12+03 (сбор 3.442 с). Модель GLM-5.3-Flash
(ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc
Yak #3) (S1.3, записано буквально; не обновлялся). Ядра: Xray 26.10.31 / sing-box 1.14.4.
Executor_NoNewPrivs=0 в канале ZCode (S1.2a, EXECUTOR_NNP_OK — новая проверка канала до
sudo; NNP=1 у ядра sing-box — другая роль, там ожидается и не проверялась как дефект);
sudo rc 0; действий владельца не требовалось (вчерашний эпизод с NoNewPrivs и перезапуском
ZCode зафиксирован в отчёте T).
Tested HEAD 44d0fc496e32ef84430dedf88dae0ae2c926362f / tree
7d03c1282a74b8a5f1dbd003955b3516acf5a794. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_coverage_batch.py +
unit-тест); продукт не устанавливался и не менялся. Installed4: True ×4
(INSTALLED_SOURCE_OK); полное .py-дерево: equal=True, 110=110 (INSTALLED_PARSER_TREE_OK).
7 frozen SHA (COVERAGE_BATCH_FROZEN; /run/xgw-w3u 0700, файлы root600):
wave3_coverage_batch.py f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48
(единственный CLI start/status/show; _worker вручную не вызывался); wave3_extended_batch.py
9e467188… (Tsource проверен, НЕ переисполнялся; использованы чистые функции independent
record/compare/graph); wave3_reality_contract.py 3fbc8fdd…; wave3_single_bridge.py
66128dda…; wave3_bridge_diagnostic.py e77d441e…; wave3_bridge_probe.py 2f023032…;
wave3_on_observer.py 0db2acf6… — библиотеки.
Start rc 0, маркер COVERAGE_BATCH_STARTED; monitor: BATCH_FINISHED сразу (сбор без
интервалов наблюдения — 3.442 с); show rc 0, wrapper.file=**summary.json** (финальный
итог); финальный маркер **COVERAGE_BATCH_RECORDED**; elapsed 3.442 с;
**network_requests=0**; executor_scope=THINKCENTRE_ONLY_CONFIRMED_BY_OWNER.
Исходный/конечный: HEALTHY с 02.11 19:56 (ночь простояла без перезапуска — таймштамп
не менялся); перехват ВКЛЮЧЁН (рабочий on); pool «выключен»; Tailscale route=vpn;
связь владельца и модели живая.

| Этап | Collection | Факты/counts/bools | Semantic decision | Ограничения |
|---|---|---|---|---|
| U1 T | RECORDED | T_scope_accepted=true; current_sb_matches_T=**false**; current_xray_matches_T=**false**; reference_key_available=true. Аудит счётчиков T: RX reported 35 774 669 = **сумма кумулятивных дельт** (matches_sum=true, matches_last=false), фактический трафик интервала T = last rx 5 517 331 / tx 139 736 077; samples=12 | Конфиг SB/Xray снова ≠ T-базе (ночная регенерация); цифры «суммарно» из таблицы отчёта T — суммы кумулятивных дельт, НЕ реальный трафик: фактический объём интервала T ≈ rx 5.5 МБ / tx 139.7 МБ (поправка к моей формулировке в отчёте T; там слова «суммарно» были точны, но это не итоговый трафик) | Сумма кумулятивных значений НЕ трафик; last-счётчик ≠ скорость/клиентская атрибуция |
| U2 sources | RECORDED | configured=3, supported_total=**101**: S1 PLAIN_JSON (139 candidates, 40 containers, **46** supported, 86 ignored non-VLESS/service, 7 UNSUPPORTED_XRAY_TRANSPORT_OR_CHAIN, 220 visited, **legacy_T=0**); S2 PLAIN_JSON (186/52/**47**/118/21/291/**0**); S3 BASE64_LINKS (19 candidates, **8** supported, 9 UNSUPPORTED_URI_TRANSPORT, **legacy_T=8**). same_cache_digests_as_T=false; limits не достигнуты | **Эффект исправления containerwalk на тех же носителях**: два PLAIN_JSON источника, дававших в T 0 supported, дали 46+47=93 records (T-разбор не раскрывал массивы полных конфигов до вложенных outbounds); BASE64_LINKS без изменений (8=8) | Не свежий ответ сервера/не wire; unsupported reasons фиксированы (не сырой текст); cache обновился между T и U (digests≠T) — сравнение coverage на «те же bytes» ограничено носителем: для PLAIN_JSON честное сравнение на идентичных bytes недоступно, фикс T2 воспроизведён функцией legacy-T на текущих bytes |
| U3 contracts | RECORDED | default_vless=67; equal=**66**; mismatched=**0**; no_unique_record=**1**; reference_case: outcome=**COMPARED**, matching_records=1, distinct_contracts=1, **все 12 field_equal=true** (server/port/uuid/flow/SNI/TLS/REALITY/public_key/short_id/uTLS/fingerprint/transport) | **Reference-кейс теперь имеет уникальную запись-совпадение и равен по всем 12 полям** — пункт 3 backlog T (запись в нераскрытых JSON-контейнерах) закрыт: applied REALITY-контракт reference-входа полностью совпадает с независимым разбором источников. 66/67 равны, 0 несовпадений, 1 без уникальной записи | Равенство ≠ сервер/health/DNS/bind/extras/socketoptions; no_unique ≠ mismatch |
| U4 graph | RECORDED | bridges=141 (d=71, f=67, m=3); reality_outbounds=135; xray_bridge_references=3; bad_xray_references=0; duplicate_listener_ports=0; noncanonical=0; reality invalid key/short_id form=0/0; route_schema_violations=0; routing_mark_key_count=0; unmatched_local_socks=0; final_reject=true | Граф согласован, все bad-counts нулевые — воспроизводит T4 на новой базе | Граф файлов, не живой API/packetproof; форма ключей ≠ серверные ожидания |
| U5 generations | RECORDED | current_matches_T_digest=false; last_good: available=true, bytes_equal_current=false, **shared_endpoint_objects_changed=44**, tags 0/0, dns/log/route/experimental_changed=false, json_values_equal=false; last_good matches_T=false; pending: ABSENT; writer NOT_ATTRIBUTED_BY_FILE_METADATA | Разница current↔last-good — 44 изменённых endpoint-объекта при неизменных разделах dns/log/route/experimental и без добавлений/удалений тегов: согласуется с обновлением параметров серверов (например, ночное обновление подписки); гипотеза, не установленное время/автор | Поколения не применялись/не откатывались; writer identity не устанавливается; «каждая регенерация меняет digest» — неверная blanket-гипотеза |
| U6 keyed health | RECORDED | default_bridges=71; unique_current_node_rows=71; mapped_scans=71; missing_or_ambiguous_nodes=0; rows=90; reference: outcome=PERSISTED_SCAN_MAPPED_TO_CURRENT_NODE, verdict=**OK**, bytes=306, seconds=1.09, age=985.2 с (≈16.4 мин до U), fresh_active_check=false, core UNSPECIFIED_IN_SCHEMA | У reference-узла есть сохранённый скан OK свежестью ~16 мин (свежее R-отказа ~10 ч); но OK 306B ≠ BODY 32769 и core неизвестен — не реабилитация R | Join только по tag/probe_tag; age ≠ ping; seconds ≠ RTT; активный health не запускался |
| U7 units | RECORDED | SINGBOX и XRAY: properties_seen=14/14, query_ok=true, все bools true (user/group expected; caps ambient/bounding expected; **no_new_privileges=true**; protect_system_strict; protect_home; private_tmp; read_write_paths_empty; run_explicit_read_only; address_families; lock_personality; restrict_suid_sgid; restrict_realtime) | Изоляция обоих юнитов на уровне systemd подтверждена (без reload); согласуется с capless-пробами M | RW_paths_empty — только данный параметр; это не все возможные writable mounts |
| U8 writer journal | RECORDED | query_ok=**false**; error_class=**TimeoutExpired** (общий bounded-запрос двух служб за 24ч превысил бюджет 3 с); counts НЕ получены | Coverage-неполнота: writer-journal фразы apply/reload/deferred/rollback не посчитаны; это НЕ «никогда не перечитывалось» и не причина чего-либо; loglevel не повышался | Пустой/queryfalse ≠ отсутствие событий; повтор в этом прогоне не выполнялся (правило одного run) |

## Контекст

Before/after (оба сняты): capture true до/после; guard query=ok, postrouting/10/forward/
drop=5/reject=0 в обоих; службы active ×6; sing-box nonprivileged, uid/gid match,
forbidden groups absent, caps 0×5, NoNewPrivs; DAC expected ×4; pool_mode=off, router ap,
tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1.
on_context_preserved=true; settings_unchanged=true ×3; bridge_config_unchanged=true
(внутри U); xray_config_unchanged=true; same_singbox_process=true; same_boot=true;
service_pid_same=true ×6; pin_record_readable_before_after=true/true;
pin_record_unchanged=true; cache_inputs_unchanged=true; local_generation_files_unchanged=true
(поколения не менялись под наблюдением); all_context_checks_ok=true.
Остановки: нет (global stop/after stop/error class — отсутствуют; U8 TimeoutExpired —
локальный результат этапа, worker продолжил по ТЗ). NOT_RUN этапа U8 — только counts
фраз (этап выполнен, ответ не получен); пакетный not_run список: active_health /
client_LAN_UDP_IPv6_DNS / performance / faults / D1_on_install / E4_packet_attribution /
all_Tailscale_paths — вне scope по ТЗ. NETWORK_REQUESTS=0; мутаций нет; off-rollback/
таймер не запускались; отклонений и действий владельца в прогоне не было; конечная
связь живая.

## Консолидированное решение и backlog

**Эффект исправления тестового JSON-coverage**: дефект был в ТЕСТОВОМ парсере T2 (не
раскрывал массивы полных конфигов → мог вернуть 0 supported без ошибки). U2 на текущих
bytes: legacy-T-функция даёт 0/0/8, расширенный containerwalk — 46/47/8 (итого 101
supported vs 8 у T). **Исторический T не переписан**: 6/67 T3 остаётся принятым фактом
в своём scope; **runtimebug XGW НЕ подтверждён и не обоснован** — продукт не менялся,
продуктовый патч не требуется: это устранённый недочёт тестового инструментария.
Дополнительный артефакт исправления: reference-кейс (вход по ключу R) теперь COMPARED —
уникальная запись найдена, все 12 полей равны (закрыт пункт 3 backlog T: запись была в
нераскрытых JSON-контейнерах).

**Atomic fixspecs по конкретному mismatch**: статических mismatches НЕ обнаружено
(U3: 0 mismatched; U4: все bad-counts 0; U7: все свойства true). Формулировать fixspec
не по чему — так и написано, не выдумываю. Точечные недостающие evidence:
1. **U8 writer-journal**: один bounded-запрос упёрся в 3 с (TimeoutExpired). Минимальный
   будущий шаг: тот же запрос с меньшим окном (например, 1–2 ч) или большая квота бюджета
   — отдельным ТЗ; в этом прогоне не повторялся.
2. **Config lineage**: дрейф SB/Xray относительно T (U1) и 44 изменённых endpoint-объекта
   относительно last-good (U5) — согласуется с ночным обновлением подписки; недостающее —
   время/инициатор регенерации (writer identity). Минимальный шаг: успешный variant U8.
3. **Reference-верdict R**: у reference-узла свежий persisted OK (985 с) — не
   реабилитирует R (OK 306B ≠ BODY 32769, core неизвестен). Минимальный шаг при желании
   владельца: один активный проверочный запрос по отдельному ТЗ либо проверка подписки/
   сервера владельцем вне теста.
4. **Поправка к моему отчёту T**: таблица T7 «суммарные дельты» были суммами кумулятивных
   значений (audit U1: matches_sum=true) — реальный объём интервала T ≈ rx 5.5 МБ /
   tx 139.7 МБ. Публикация T не меняется (исторический отчёт не переписывается), факт
   зафиксирован здесь.

**Принятые scope**: T (364с семиэтапный сбор, 141 граф, T7 12 точек), M 6/6, L 608с,
J, SB-2 positive, S consistency, R negative (curl97), N partial 1/2, P blocked 0,
Q readonly — сохранены без пересмотра. **Scans дают node-identity через tag; core
неизвестен** (UNSPECIFIED_IN_SCHEMA); writer identity автоматически не приписывается.

**Доступен ТОЛЬКО ThinkCentre** (подтверждено владельцем 03.11): управляемого LAN-клиента
нет. Проверки с самого шлюза НЕ выдаются за LAN-клиентские; внешнее устройство не
предлагается как факт. D1-on / faults / E4 / LAN UDP / IPv6 / DNS end-to-end /
performance / all Tailscale — остаются открытыми: нет независимого восстановления on и
согласованного клиентского опыта в этой задаче; full wave3 НЕ закрыта; wave4/DAE не
начинались. Рабочая LAN через роутер считается работающей; шлюз HEALTHY/on не менялся.

Privacy просмотр ДО gitadd: только этот Markdown; private baseline/дайджесты/значения
полей/show.json/raw кэши остались вне Git. Путь
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3u-2026-11-03.md, коммит «Отчёт: XGW 0.2.0,
wave3u — расширенное покрытие источников и поколений конфигурации», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56,
перехват ВКЛЮЧЁН, pool прежний; связь живая.
