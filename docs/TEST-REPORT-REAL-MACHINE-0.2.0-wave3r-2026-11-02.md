# Отчёт: XGW wave3r — один запрос с новой базой

Дата/время MSK: 2026-11-02, 21:03–21:11+03 (NOTES_CREATED 21:03:53). Модель
GLM-5.3-Flash (ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables
v1.0.9 (Old Doc Yak #3) (S1.3, записано буквально; не обновлялся). Ядра: Xray 26.10.31 /
sing-box 1.14.4; curl 8.5.0 (одна разрешённая проверка версии в R, eligible ≥8.4).
Tested HEAD 3ec17cf6dba4cce9b85ecd1c5fa3e6c72db98829 / tree
5b52cd788d20b64fb60b5017ac6ec9757c2201f3. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_current_bridge.py +
unit-тест); продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
5 frozen SHA/modes (CURRENT_BRIDGE_FROZEN; /run/xgw-w3r 0700, файлы root600):
wave3_current_bridge.py 38b40524dad5aa76742100cea46b07853b9c9d06940ffc17da3094384bdd59f4
(единственный запускаемый CLI; переиспользует неизменённые функции request/journal/context
из P-источника, не Pmain); wave3_single_bridge.py
66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93;
wave3_bridge_diagnostic.py e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068;
wave3_bridge_probe.py 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef;
wave3_on_observer.py 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 —
библиотеки; root Qsource SHA e7931064… подтверждён (источник/summary читались, CLI не
вызывался); старые /run файлы не переписывались.
Исходный/конечный: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (рабочий on, не
переключался); pool «выключен» (прежний); Tailscale route=vpn; связь владельца и модели
живая в обоих концах.

## Исполнение

Run command rc: 0; collector marker: **CURRENT_BRIDGE_RECORDED**;
stage=CURRENT_REQUEST_RECORDED; show rc 0 (чтение, согласовано). Первого STOP не было;
stop_code/error_class/after_stop_code — отсутствуют; INTERRUPTED_UNKNOWN — нет.
case=**R-CURRENT-1**; selection_basis=**CURRENT_UNIQUE_VLESS_AT_O_CASE_KEY** (текущий
unique vless/d-вход по ключу SB-1 из сохранённого Omapping; не first-new, не другой узел,
не SB-2, без health-фильтра); historical_endpoint_identity=**UNPROVEN** — короткий ключ
8hex не доказывает неизменность старых endpoint/ключей/TLS и не исключает коллизию;
имя случая R-CURRENT-1, не «доказанно тот же SB-1».
current_config_equals_O=**false** — зафиксированное различие старой базы и новой; R
разрешён решением разработчика после Q, старая O-база не откатывалась, mapping не
пересоздавался. Qsource/evidence и O/N reference прошли до запроса (STOP не возник).
Current config безопасные attrs: vless; hostname; порт-класс 443; TLS+SNI present; not
insecure; reality+uTLS; flow xtls-rprx-vision; tcp_or_default; без mux; без detour; без
bind; 1 static host, all global (safe-класс идентичен прежним наблюдениям O/N).
private_plan_persisted_before_request=**true** (план с current config+target digest/
key/process/boot/6 service identity/временем сохранён и fsync ДО запроса; без raw
endpoint/URL/auth; не является историческим identity-proof N).
request_count=**1** (ровно один; attempt зарегистрирован). listener_owned_before/after=
**true/true** (LISTEN inode — fd текущего PID sing-box).

## Единственный новый запрос

outcome=**PROBE_FAILED**; curl_rc=**97** (ошибка SOCKS-прокси); http_status=**0**;
bytes=**0**; seconds=0.977; tls_verify_result=0 (не доказывает target TLS — соединение
до цели не дошло); content_encoding_identity=true; **body_ok=false** (<32769 байт).
error: message_present=true; socks5_reply_code=**1** (общий ответ отказа SOCKS, не
установленная upstream-причина); socks_auth_failure_text=false (не auth); details=[].
request_window: begin/end realtime записаны; mono elapsed 1.007 с;
clock_basis_compatible=true (запрос отдельно от time — не ping/RTT/скорость; body-лимиты
— лимиты приложения, не wire-квота).
Journal НОВОГО окна (padding ±2 с, limit 2000): query_ok=true; rows=**1**; truncated=
false; parse_errors=0; error_priority_rows=0. Global categories: tls_auth_or_handshake=
**1**, остальные (permission/name_resolution/timeout/refused/unreachable/reset_or_eof)=0.
Related SB-1: matched_rows=**1**, tls_auth_or_handshake=1, uncategorized_rows=0.
Literal counts: **reality_verification_failed=1**; certificate_failure/tls_alert/
handshake_failure/permission/dns/timeout/refused/unreachable/reset_or_eof=0.
Message levels: error=1 (leading level), остальные 0. Связь строки с запросом — по
тегу+времени окна, НЕ привязка к конкретному curl-сеансу; литеральные фразы и широкие
категории — раздельные слои; ERROR в message при error_priority_rows=0 — не противоречие.
Неполноты журнала/blocked clock basis/UNKNOWN в этом прогоне не возникло.
Нет fallback/ретраев/других узлов/сканов/новых listeners. **N partial (1/2 BODY_OK) и
P blocked (request 0) новым результатом не переписаны**; Q закрыт как read-only сбор
(принят). Успехом R это не было и быть не могло — зафиксирован отрицательный результат.

## Сохранение контекста

Before и after (оба сняты, sample 0.084/0.113 с): capture true до/после; guard query=ok,
postrouting/10/forward/drop=5/reject=0 в обоих; службы active ×6; sing-box
same_process_during_read, nonprivileged, uid/gid match, forbidden groups absent, caps
0×5 (Inh/Prm/Eff/Bnd/Amb), NoNewPrivs; DAC expected ×4; pool_mode=off, router ap,
tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1;
files_unchanged_during_read=true ×3 в обоих.
on_context_preserved=true; settings_unchanged=true ×3; **bridge_config_unchanged=true**
— current baseline зафиксирована и не менялась внутри R (дайджест до/после запроса
совпал; это свойство R, не доказательство совпадения с O).
same_singbox_process=true; same_boot=true; service_pid_same=true ×6.
pin_record_readable_before_after=true/true; pin_record_unchanged=true;
all_context_checks_ok=true (не заменяет отдельные поля — все перечислены).
STOP/UNKNOWN/NOT_RUN после старта не возникло; отклонений и действий владельца в
прогоне не было. Recovery не потребовалось; off-rollback/таймер не запускались;
продукт/сеть/службы/правила/pin/пул тестом не менялись; из сетевых действий — только
одна проверка версии curl и один разрешённый запрос через существующий owned вход.

## Вывод

Наблюдение: текущий вход, выбранный по ключу SB-1 из O-mapping (R-CURRENT-1, new
baseline), не передал тело — curl rc=97/0 байт за 0.977 с при capless worker и полном
сохранном контексте; в journal нового окна ровно одна related-строка с литералом
reality_verification_failed (уровень error), остальные категории нулевые. Гипотеза
(с ограничениями, не назначенная причина): upstream reality/TLS-верификация соединения
этого входа в обоих независимо измеренных окнах (N и R) завершилась неудачей — два
окна с SOCKS-отказом + TLS-auth/handshake-классом строк converge; но привязка строк к
сеансам — по тегу+времени, ключ не доказывает идентичность старого endpoint, и причина
на стороне сервера/сети upstream остаётся вне измерения. ТСПУ/падение сервера/дефект
изоляции по одному enum не назначаются: SB-2 на том же процессе (N) прошёл, изоляция
подтверждена контекстом R. Недостающий факт: криптографическая привязка journal-строк
к сеансу и вид upstream-сервера (его health/логи) — вне досягаемости этого ТЗ.
Старый SB-1 «не починен» и не «ухудшен» новым результатом: Npartial 1/2 / P blocked
request0 / Q readonly accepted / M 6/6 / L 608 с / J / SB-2 positive — остаются как
были. Full wave3 / E4 / D1-on / scoped faults / LAN UDP / IPv6 / DNS / all Tailscale
paths — открыты; wave4/DAE не начинались. Рабочая LAN не объявлена неисправной.
Следующий атомарный шаг — решение разработчика (например, свежий health-scan входа или
опрос владельца о состоянии upstream-сервера — вне этого ТЗ).

Privacy просмотр ДО gitadd: только этот Markdown; private план/дайджесты/show.json/raw
заметки остались вне Git. Путь docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3r-2026-11-02.md,
коммит «Отчёт: XGW 0.2.0, wave3r — один запрос с новой базой», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Конечный режим: HEALTHY с 02.11 19:56,
перехват ВКЛЮЧЁН, pool прежний; связь живая.
