# Отчёт: XGW wave3s — локальная сверка REALITY без запросов

Дата/время MSK: 2026-11-02, 21:23–21:26+03 (NOTES_CREATED 21:23:06). Модель
GLM-5.3-Flash (ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables
v1.0.9 (Old Doc Yak #3) (S1.3, записано буквально; не обновлялся). Ядра: Xray 26.10.31 /
sing-box 1.14.4 (из status; S не запускал ни curl --version, ни любых команд).
Tested HEAD b35ef584c87317b4e071e45b3213e04e6c4efdd0 / tree
02d31a1f812f66ea51aef76174b8bf290ea8834c. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_reality_contract.py +
unit-тест); продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
Полное .py-дерево: installed_python_tree_equal=True; source_module_count=110,
installed_module_count=110 (INSTALLED_PARSER_TREE_OK, S2.4 — байтовое сравнение, без
импорта/запуска). 5 frozen SHA/modes (REALITY_CONTRACT_FROZEN; /run/xgw-w3s 0700,
файлы root600): wave3_reality_contract.py
3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c (единственный
запускаемый CLI); wave3_single_bridge.py
66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93;
wave3_bridge_diagnostic.py e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068;
wave3_bridge_probe.py 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef;
wave3_on_observer.py 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 —
библиотеки (context/selector/reader), их request/journal/main не вызывались; старый
Rsource читался по SHA 38b40524…, не импортировался/не запускался.
Исходный/конечный: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (рабочий on, не
переключался); pool «выключен» (прежний); Tailscale route=vpn; связь владельца и модели
живая в обоих концах.

## Исполнение

Run command rc: 0; collector marker: **REALITY_CONTRACT_RECORDED**;
stage=STATIC_CONTRACT_RECORDED; show rc 0 (чтение, согласовано). STOP не было;
stop_code/error_class/after_stop_code — отсутствуют; INTERRUPTED_UNKNOWN — нет.
**network_requests=0** — ни одного GET/curl/journal/scan/повтора R; S инициировала
ноль новых соединений.
current_config_matches_R_plan=**true** → contract_relation_to_R=
**CONFIG_DIGEST_MATCHES_R_PLAN**: текущий SB-config совпадает с сохранённым R-планом —
сверка выполнена ровно на входе, измеренном в R (не CURRENT_ONLY режим).
syntax_flags (только форма, НЕ серверное ожидание/не проверка правильности ключа):
public_key_base64url_32_bytes=true; short_id_even_hex_at_most_8_bytes=true;
server_name_present=true; tls_enabled=true; reality_enabled=true; utls_enabled=true —
6/6, базовая форма applied REALITY корректна; новые ключи не генерировались.
source_coverage: configured_sources=3; sources_read=3; missing_or_unreadable=0;
parse_errors=0; sources_with_parser_warnings=0; coverage_limited=false;
manual_links_parsed=false (manual-часть в текущем конфиге отсутствовала — parse не
требовался; settings3 before/after защищают эту часть). Пределы не достигнуты
(32 источника/2MiB/8MiB/5000 узлов); чтение кэша через O_NOFOLLOW/O_NONBLOCK, не
Store/load/save.
source_comparison: **matching_parsed_source_rows=1**; distinct_parsed_contracts=**1**
(однозначный view, ambiguity НЕ возникала — сравнение не NOT_RUN);
comparison=PARSED_CONTRACT_COMPARED; source_boundary=
**AFTER_PRODUCT_PARSER_NOT_ORIGINAL_WIRE** — источники разобраны штатным парсером
продукта: равенство НЕ является независимой проверкой URI-парсера, достоверности
подписки или сервера, и не покрывает DNS static IPs/bind/socketoptions/extras.
При однозначном view — **все 12 field_equal=true**: server, server_port, uuid, flow,
server_name, tls_enabled, reality_enabled, public_key, short_id, utls_enabled,
fingerprint, transport; **all_compared_fields_equal=true**. Значения полей не
выводились; сверка — передача parsed source→applied config, не доказательство
корректности исходной подписки/парсера/сервера.

## Контекст

Before и after (оба сняты, sample 0.052/0.049 с): capture true до/после; guard query=ok,
postrouting/10/forward/drop=5/reject=0 в обоих; службы active ×6; sing-box
same_process_during_read, nonprivileged, uid/gid match, forbidden groups absent, caps
0×5 (Inh/Prm/Eff/Bnd/Amb), NoNewPrivs; DAC expected ×4; pool_mode=off, router ap,
tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1;
files_unchanged_during_read=true ×3 в обоих.
on_context_preserved=true; settings_unchanged=true ×3; bridge_config_unchanged=true
(не null — дайджест читался в обоих концах и совпал; дополнительно совпадение с
R-планом зафиксировано отдельно).
same_singbox_process=true; same_boot=true; service_pid_same=true ×6;
pin_record_readable_before_after=true/true; pin_record_unchanged=true.
**cache_inputs_unchanged=true** при 3 прочитанных файлах — реальное сравнение дайджестов
до/после (не пустое). all_context_checks_ok=true (не заменяет отдельные поля).
UNKNOWN/NOT_RUN/STOP не возникли; отклонений и действий владельца в прогоне не было.
Recovery не потребовалось; off-rollback/таймер не запускались; продукт/сеть/службы/
правила/pin/пул тестом не менялись; ноль новых соединений.

## Вывод

Наблюдение: applied REALITY-контракт текущего входа (он же — вход R: digest совпадает с
R-планом) имеет корректную базовую форму (6/6) и **точно совпадает по всем 12
сравнённым полям с единственным однозначным parsed-view из локальных кэшей подписок**
(3/3 источников прочитано, ноль ошибок/предупреждений парсера, кэш не менялся за прогон).
Гипотеза (с ограничениями): передача parsed source→applied config локально
консистентна — расхождение «конфиг ≠ подписка» как причина REALITY failure из R
не подтверждается и сузает пространство гипотез к слоям вне этой сверки: фактическое
состояние сервера против сохранённых в подписке параметров (reality key/short_id могли
устареть на стороне источника), upstream-сеть, либо исходный wire-формат до парсера.
Mismatch/дрейф не обнаружены, но и равенство не PASS узла: это не объясняет REALITY
failure и не доказывает корректность URI-парсера/подписи/сервера (boundary после
парсера; семантика DNS/bind/extras не покрыта). Недостающий факт: вид сервера
(его актуальные reality-параметры и логи) и исходный wire-формат подписки до парсера —
оба вне досягаемости локального ТЗ; lineage свежести кэша подписки не устанавливался.
S ничего не исправляла и R не повторяла; отрицательный факт R принят как есть:
Npartial 1/2 / P blocked 0 / Q readonly / R negative / M 6/6 / L 608 с / J /
SB-2 positive — сохраняются. «ТСПУ/сервер мёртв/изоляция исключена» не назначается.
Full wave3 / D1-on / E4 / scoped faults / LAN UDP / IPv6 / DNS / all Tailscale paths —
открыты; wave4/DAE не начинались. Рабочая LAN не объявлена неисправной; S ничего не
отключала.

Privacy просмотр ДО gitadd: только этот Markdown; private план/R-артефакты/show.json/
raw кэш/значения полей остались вне Git (значения parsed полей даже локально не
выводились helper'ом). Путь docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3s-2026-11-02.md,
коммит «Отчёт: XGW 0.2.0, wave3s — локальная сверка REALITY без запросов», push в
freepool (REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с
02.11 19:56, перехват ВКЛЮЧЁН, pool прежний; связь живая.
