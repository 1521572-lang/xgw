# Отчёт: XGW wave3q — read-only разбор STOP до запроса P

Дата/время MSK: 2026-11-02, 20:39–20:47+03 (NOTES_CREATED 20:40:23). Модель
GLM-5.3-Flash (ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables
v1.0.9 (Old Doc Yak #3) (S1.3, записано буквально; не обновлялся). Ядра продукта:
Xray 26.10.31 / sing-box 1.14.4 (из status, не менялись).
Tested HEAD 58841d2a86d9d9475952561d83af45d024b5d06f / tree
ee76159096f98fa74d02a4a959719d52c04e3001. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_gate_diagnostic.py +
его unit-тест); продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
4 frozen SHA/modes (GATE_DIAGNOSTIC_FROZEN; /run/xgw-w3q 0700, файлы root600):
wave3_gate_diagnostic.py e793106474f7a7910886cecd0d11a65f084d123f440473dba8d596f2a36f648b
(единственный запускаемый CLI); wave3_bridge_diagnostic.py
e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068,
wave3_bridge_probe.py 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef,
wave3_on_observer.py 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 —
библиотеки, их CLI не запускались; старый rootPsource проверен по SHA
66128dda… и не импортировался/не изменялся.
Начальный/конечный: HEALTHY с 02.11 19:56 (буквальный таймштамп; сам по себе не
доказывает перезапуск VPN владельцем); перехват ВКЛЮЧЁН (рабочий on, не
переключался); pool «выключен» (прежний); Tailscale route=vpn; связь владельца и
модели живая в обоих концах.

## Исполнение

Run command rc: 0; collector marker: **GATE_DIAGNOSTIC_RECORDED**;
stage=CURRENT_STATIC_READS_COMPLETE; show rc 0 (чтение, согласовано с run).
Первого STOP не было; stop_code/error_class/after_stop_code — отсутствуют.
historical_P_valid=true; P_request_count=0 (запрос в P не начинался — это НЕ
отрицательный результат SB-1);
**P_source_derived_stage_range=AFTER_CONFIG_DIGEST_BEFORE_CURL_VERSION_EMISSION** —
диапазон исходного кода при известных эмитированных полях P: configdigest был
вычислен, версия curl не выдана; это диапазон, не точная ветвь.
P_exception_site=**UNRECORDED** (в P не записывался; задним числом не
восстанавливался догадкой; raw не вскрывался).
P_plan_persisted_flag_present=false; P_plan_persisted_flag_true=false;
P_curl_version_field_present=false; P_O_digest_flag_present=false — старый P-summary
не содержал этих полей (прочитаны как факты отсутствия).
P_plan_file_present_now=**false** — только современная метаинформация о наличии
файла плана сейчас; содержимое плана не читалось и не доказывает его прошлое
состояние.
current_static_checks, все 11 отдельно: O_recorded_marker=true;
O_historical_summary_valid=true; O_mapping_basis_supported=true;
mapping_basis_supported=true; N_summary_digest_matches_O=true;
**current_config_digest_matches_O=false**; SB1_key_shape_valid=true;
current_route_canonical=true; mapped_SB1_unique=true; mapped_SB1_vless=true;
current_routing_marks_absent=true.
current_first_unmet_gate=**current_config_digest_matches_O**;
current_all_mapping_and_route_gates_ok=false (следствие единственного false).
current_config_warnings_present=false; current_valid_configured_HTTPS_target_count=2;
current_curl_path_available=true (путь найден через which, curl НЕ запускался);
curl_version_rechecked=false — намеренно, по ТЗ.
clock_basis_compatible_with_P=true; config_file_times_predate_P=true;
current_config_relation_to_P=**FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN** — поддержка
связи временами файлов, НЕ сохранённый P-configdigest и НЕ доказанный общий boot.
Современный currentgate — факт Q о текущем состоянии, НЕ точная старая ветвь P
(по ТЗ прямо запрещено объявлять её точным местом старого ValueError).
current_diagnostic_complete=true. Q_network_requests=**0** — никаких curl/GET/
journal-чтений/сканов/healthscan/повтора P/O/N/Q-run; helper только читал
существующие артефакты и текущее состояние.

## Сохранение контекста

Before и after (оба сняты, sample 0.082/0.08 с): capture true до/после; guard
query=ok, postrouting/10/forward/drop=5/reject=0 в обоих; службы active ×6 (xgw,
xgw-net, xgw-xray, xgw-singbox, xgw-dhcp, tailscaled); sing-box
same_process_during_read, nonprivileged, uid/gid match, forbidden groups absent,
caps 0×5 (Inh/Prm/Eff/Bnd/Amb), NoNewPrivs; DAC expected ×4; pool_mode=off,
router ap, tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1;
files_unchanged_during_read=true ×3 в обоих.
on_context_preserved=true; settings_unchanged=true ×3;
bridge_config_unchanged=true — совпадение before/after **Q** (не автоматически с
O/P; null означал бы, что при раннем STOP baseline не прочитан — не этот случай).
same_singbox_process=true; same_boot=true; service_pid_same=true ×6.
pin_record_readable_before_after=true/true; pin_record_unchanged=true;
all_context_checks_ok=true (не заменяет отдельные поля — все перечислены выше).
STOP/ошибок чтения/UNKNOWN-полей в данных не возникло; отклонений и действий
владельца в прогоне не было; модель не меняла VPN/службы/правила/конфиги/пул/pin
и не делала сетевых запросов. Recovery сетевого возврата не требовалось; сеть не
менялась; off-rollback/таймер не запускались.

## Вывод

Наблюдение (факты Q): (1) диапазон сбоя P локализован эмитированными полями в
AFTER_CONFIG_DIGEST_BEFORE_CURL_VERSION_EMISSION; точная ветвь — UNRECORDED;
(2) из текущих статических проверок единственный false —
current_config_digest_matches_O: содержимое текущего SB-config отличается от
дайджеста, записанного в O; при этом file-times предшествуют старту P, т.е. с
момента старта P файл не менялся — текущее содержимое совпадает с тем, что P
читал бы как baseline; (3) checks N↔O согласованы (N_summary_digest_matches_O=true),
расхождение именно O↔current.
Гипотеза (с ограничениями, не назначенная причина): изменение конфига произошло в
интервале O→P (вне окон P и Q) и может быть обычным следствием перезапуска VPN
владельцем между прогонами — таймштамп HEALTHY сменился на 19:56 (факт
таймштампа; действие владельца НЕ утверждается). Если ветка сравнения digest с O
существовала в диапазоне сбоя P, такое расхождение согласуется с ValueError в P —
но это НЕ доказано как точная ветвь: в диапазоне также mapping/route/marks/
targets/tool/version, и ТЗ прямо запрещает объявлять currentgate старой точной
причиной. Откат digest/удаление mapping/узла не выполнялись и не требуются —
изменение может быть нормальным; рабочая схема не тронута.
Недостающий факт: точная точка ValueError внутри P (UNRECORDED) и точное время/
основание изменения конфига относительно O — для получения нужен отдельный узкий
шаг разработчика (например, read-only воспроизведение проверок P на сохранённых
артефактах O/P вне рабочего шлюза); этим ТЗ повтор P и вскрытие raw запрещены.
P_request_count=0 — прогон P не является ни отрицательным health SB-1, ни
реабилитацией; N остаётся partial (1/2 BODY_OK), SB-2 positive приняты.
M 6/6 / L 608 с / J short-host+loaded — приняты и не повторялись.
Npartial / full wave3 / D1-on / E4 / scoped faults / LAN UDP / IPv6 / DNS / all
Tailscale paths — остаются открытыми; wave4/DAE не начинались. Это не указание на
неисправность рабочей LAN.

Публикация: только этот Markdown; private план/root файлы/raw JSON/старые
summary/mapping остались вне Git. Реальный путь
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3q-2026-11-02.md, коммит «Отчёт: XGW 0.2.0,
wave3q — read-only разбор STOP до запроса P», push в freepool (REPORT_PUBLISHED в
финальном сообщении). Рабочий режим в конце: HEALTHY с 02.11 19:56, перехват
ВКЛЮЧЁН, pool прежний; связь живая.
