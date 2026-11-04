# Отчёт: XGW wave3o — сохранённые данные частичного wave3n

Начало/конец MSK: 2026-11-02, 16:12:14–16:18+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc Yak #3) (S1.3,
записано буквально; не обновлялся). Tested HEAD ce1f1ed8365c43158a72ebd7c4546af8f2a868f2
/ tree bdf174926fa628e3692a30a3fa5ffc188b2a5765. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только тестовый сборщик
tests/stand/wave3_bridge_diagnostic.py; продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
P1 root700/600, 3 frozen SHA (READ_DIAGNOSTIC_FROZEN; /run/xgw-w3o 0700, файлы root600):
wave3_bridge_diagnostic.py e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068;
wave3_bridge_probe.py 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef
(не изменён; CLI не запускался — библиотека);
wave3_on_observer.py 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46
(не изменён).
Run marker/rc: **READ_DIAGNOSTIC_RECORDED**, exit 0; show согласован. Это сбор
диагностических данных, **не SB-1 PASS и не доказанная причина**.
Исходный/конечный: HEALTHY с 02.11 12:42; перехват ВКЛЮЧЁН (рабочий on, включён
владельцем, не переключался); pool «выключен»; Xray 26.10.31 / sing-box 1.14.4.

Historical валидность: historical_summary_valid=true; интервал N 2.919 с;
clock_basis_compatible=true; current_candidate_count=71 (совпало со старым);
config_file_times_predate_N=true; historical_mapping=
**FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN** — сопоставление поддержано временами файлов
(mtime/ctime текущего SB-config предшествуют N) и совпадением формы результата
(71/2 кандидата, 2 цели, SB-1 две rc=97, SB-2 206/32769), НЕ криптографически
сохранённым историческим hash: исходный N не сохранял fingerprints/configSHA/PID как
private plan — это явное ограничение основания.

| Case | Безопасные current config attrs | Latest scan/verdict/bytes/seconds | Relation_to_N/age | Related journal |
|---|---|---|---|---|
| SB-1 (mapping поддержан, условно) | vless; hostname; порт-класс 443; TLS+SNI; not insecure; **reality+uTLS**; flow xtls-rprx-vision; tcp; без mux; без detour; без bind; 1 static host (global) | query_ok; 1 узел; scan present; **verdict OK**, 305 байт, 0.77 с | **before**; age на старте N 1464.083 с (≈24 мин — устаревший) | matched_rows=**2**, категория tls_auth_or_handshake=2, uncategorized=0 |
| SB-2 (mapping поддержан, условно) | **идентично SB-1** по всем перечисленным attrs | query_ok; 1 узел; verdict OK, 305 байт, 0.43 с | **after**; −1719.36 с (после N) | matched_rows=0 (все категории 0) |

Journal (окно N±2 с, padding 2, limit 2000): query_ok=true, rows=2, truncated=false,
parse_errors=0, error_priority_rows=0; global categories: только tls_auth_or_handshake=2,
остальные (permission/name_resolution/timeout/refused/unreachable/reset_or_eof) = 0.
Связь строк с кандидатом — по тегам/окну, не доказательство привязки к конкретному
curl-сеансу; категории — совпадения слов, пересекаются и возможны в неошибочных сообщениях.

before/after on/guard/services/caps/NNP/DAC/modes: рабочий on сохранён — capture true,
guard ok postrouting/10/forward/drop=5/reject=0 в обоих снимках, службы active ×6,
sing-box nonprivileged/caps 0×5/NoNewPrivs, DAC expected ×4, pool/router/tailscale
режимы прежние. Settings3/bridge_config/SB process/same_boot/PID6/pin readable/unchanged:
все true (on_context_preserved=true, pin_record_unchanged=true).
Первый STOP/ошибок чтения не было; UNKNOWN-полей в данных не возникло.
Действий VPN/ядрами/сетевыми правилами/pin/настройками и новых сетевых запросов не было
(никаких GET/сканов/соединений). Отклонений/действий владельца в прогоне не было;
конечная связь живая; рабочий режим сохранён.

Наблюдения: (1) статические безопасные атрибуты конфигурации SB-1 и SB-2 полностью
идентичны — причина отказа SB-1 не видна в классе конфигурации; (2) в реальном окне N
журнал содержит ровно 2 строки категории TLS-auth/handshake, обе ассоциированы с SB-1,
у SB-2 — ноль; (3) последний health-scan SB-1 был OK, но за ~24 мин до N (устаревший —
между ним и N узел мог стать неработоспособным; кандидаты выбирались по fingerprint,
не по health); scan SB-2 — уже после N (позднее состояние).
Поддержанные гипотезы с ограничениями (не автоматическая причина): временная
неработоспособность upstream-соединения SB-1 на момент N (например, сбой reality/TLS
handshake конкретного сервера) согласуется с journal-категорией, ранним OK-сканом и
идентичными атрибутами; изоляция/конфигурация XGW причиной не выглядят (SB-2 на том же
процессе прошёл). Оставшаяся неизвестность: точная привязка journal-строк к curl-сеансам
и свежий health-статус SB-1 на момент N — для проверки потребовались бы (будущий узкий
вопрос): сохранение fingerprints/configSHA/PID в private plan до опыта, повторный GET
через SB-1 в новом прогоне и/или свежий scan SB-1 — всё вне scope этого read-only прогона
и не выполнялось. Никакой причины не назначено; сервер не чинился/не удалялся/не
ротировался. N остаётся partial (1/2 BODY_OK); O не повторял GET и не подтверждает
исправление.
Full wave3/E4/faults/TPROXY all profiles/LAN UDP/IPv6/DNS/all TS/D1-on: NOT_RUN.
Рабочий on сохранён, off-rollback не запускался.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-2026-11-02.md, коммит «Отчёт:
XGW 0.2.0, wave3o — разбор частичного результата wave3n», push в freepool
(REPORT_PUBLISHED в финальном сообщении). В Git только этот Markdown; notes/
mapping-private.json/raw journal/DB rows/адреса остались вне репозитория.
