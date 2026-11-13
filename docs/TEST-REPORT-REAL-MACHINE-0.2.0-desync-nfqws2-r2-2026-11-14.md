# TEST-REPORT-REAL-MACHINE-0.2.0-desync-nfqws2-r2-2026-11-14

Дата: 2026-11-14; прогон 22:41–01:05 UTC (13–14.11). CODE 9b58725354799a6b91c7341c41a311371bdfa4d8
(установлен на машину), BASE eb47e83 — только эталон старых падений, откат не требовался.
План e96bd5d, ветка gui-light. Исполнитель GLM-5.3-Flash; Ubuntu 26.04 amd64; Python 3.12.3;
Xray 26.10.21; sing-box 0.1.13; nfqws2 v1.0.7 (038c97e5). Root — один systemd-run --system
юнит с FIFO-очередью команд, остановлен после восстановления. Согласия из отчёта e4a791c
действовали: полный прогон, без `nft flush ruleset` (запрещён планом r2), запуск движка с
живым UDP, публикация отчёта.

## Итог: **PARTIAL** — все этапы до горячей смены профилей PASS; горячая смена FAIL

Первый FAIL: §10 hot-swap (worker не удерживается после смены профиля — см. ниже). Из-за него
зависимые проверки offload/профилей/эскалации не выполнены или NOT_RUN. Обход-функциональность
конфигов обоих ядер, QUIC-матрица, живой UDP-noise, восстановление nftables и fallback-режимы
проверены и работают.

## §2–3: входной контроль — PASS

Снапшот: HEALTHY, capture on, zapret2 selective off, pin нет, diag «OK — 33, WARN — 0,
FAIL — 0», Xray PID 2633138, очередей нет, /opt/zapret2 755 root (правка прошлого прогона на
месте), блобы встроены (не скачивались). Тесты §3: **16 passed** (11,4 с), включая остановку
опроса подписки с параметрами [auto] и [off] — «stop-during-poll» теперь 1,19–1,39 с (регрессия
из e4a791c исправлена). Два повторных запуска параметризованного теста: 2 passed × 2 — все
четыре дополнительных случая прошли. Службы и настройки не изменились, root-действий от тестов
не было.

## §4: установка и реальная работа — PASS

engine="off" задан явно перед установкой (секция создана, оригинал сохранён). `packaging/install.sh
--yes` rc0; после: diag «OK — 33, WARN — 0, FAIL — 0», xgw-nfqws2.service inactive,
цепочка nfq_output отсутствует, HTTPS шлюза 200 (0,5 с), HEALTHY. Приватная копия TOML без
ключа engine читается как **off** при установленном бинарнике, 0 предупреждений — новый дефолт
работает. Разовый перезапуск xgw.service при engine=off: rc0, **0,32 с**, в журнале таймаутов
остановки нет (только штатные INFO-таймауты проб), PID Xray не изменился, HEALTHY, HTTPS 200.

## §5 (генерация на реальных ядрах) — PASS

`xgw generate` rc0: настоящий `xray run -test` и `sing-box check` пройдены (sing-box-конфиг
создан). Проверено приватно: outbound fragment `{tlshello, 5-20, 5-15}` — микрофрагментация
в конфиге; второй outbound (в плане назван «split», фактически тег **fragment-split**)
`{1-3, 10-30, 5-10}`; Cloudflare TCP-правило → balancer auto, catch-all последний; DNS
queryStrategy = UseIPv4 (auto без IPv6-проксирования — ожидаемо). Сингбокс: 43 TLS-блока с
полями фрагментации — все `record_fragment=true, fragment=true, fragment_fallback_delay=30ms`.
Явные варианты DNS без apply: UseIPv4→UseIPv4, PreferIPv4→PreferIPv4, AsIs→AsIs — точные
значения (первая попытка была с неверным именем ключа — ошибка исполнителя, повторена верно).

## §6 (живая фрагментация) — PASS (config_and_xray_test)

5 проб основного сервера до: 4 OK + 1 SLOW, 57620 Б, медиана 0,4 с. `[fragment] mode="always"`
→ apply rc0 → 5 проб: 4 OK + 1 SLOW, те же байты, медиана 0,4 с — новых CONNECT_FAIL/TIMEOUT
нет, HTTPS шлюза 200, HEALTHY. Возврат mode (строка удалена) → apply rc0 → HEALTHY. Захват
tcpdump не согласовывался — разрыв SNI/PQ ClientHello на проводе не доказан (по плану это
допустимый уровень результата).

## §7 (QUIC, noises, маршруты) — PASS

Матрица на копиях (generate + net show, без apply): true+«» → reject-правила UDP/443 в nft
присутствуют (3 шт.), direct-noise нет; false+«» → ни reject, ни noise; true+noise →
direct-noise с noises ровно **3 × {rand, 64-1200, 5-15}**, отдельное UDP-правило с точно
активными портами `443,19294-19344,50000-50100,19302,3478` (Discord + настроенные STUN);
true+proxy → без direct-noise и reject; во всех комбинациях Cloudflare перед catch-all,
catch-all последний. Валидация копий: noise_count 1 и 5 → 3 с предупреждением; неверные
диапазоны packet/delay → дефолты; неизвестный quic_mode → совместимость с block_quic; плохие
CIDR (2 шт.) и STUN (2 шт.) пропущены с предупреждениями, годные сохранены. Живой noise:
применён — `diag --netcheck` «OK — 39, WARN — 2, FAIL — 0» (оба WARN старые: bootstrap-DNS и
MTU PPPoE), **UDP напрямую и через VPN — STUN ответил, рабочие ответы получены через
noise-путь**; TCP HTTPS 200, VPN HEALTHY. HTTP/3 через curl NOT_RUN (curl 8.5.0 без HTTP3);
Discord NOT_RUN (клиента нет). Возврат исходного режима: reject-правила вернулись (3), HEALTHY.

## §8 (reserved CIDR, восстановление nftables) — PASS

Генерации без apply: дефолтные reserved_cidrs и с тестовой сетью 198.51.100.0/24 — в обеих
127.0.0.0/8 (7 упоминаний) и ::1 сохранены, в тестовой сеть добавлена; `nft -c` в `unshare -n`
— обе сборки OK. Свой STUN endpoint — NOT_RUN (нет своего, дефолты оставлены). Удаление таблиц
XGW (`nft delete table ip xgw; nft delete table inet xgw_guard`): демон сам восстановил обе
за **21 с** (норма ≤90), PID Xray не изменился, HEALTHY, HTTPS 200. `nft flush ruleset` —
NOT_RUN (согласие не давалось, план запрещает). Сторонние таблицы (iptables-nft) не трогались.

## §9–10 (nfqws2, NFQUEUE, профили) — частично: NFQ-путь PASS, горячая смена **FAIL**

Подготовка: права 755 root подтверждены; очередь 200 свободна; nf_conntrack_acct 0→1
временно (возврат в §13); блобы встроены — драй-раны профилей rc0. Включение engine=auto:
worker active (PID), статус виден, цепь nfq_output точно по плану: `queue num 200 flags
bypass`, `ct packets <= 8` TCP / `<= 4` UDP, анти-петля `mark & 0x40000000 == … return`,
разрешение метки 0x2 и skuid 992 (sing-box), исключения local/reserved/loopback, policy accept
без безграничной отправки в userspace. Аргументы worker-а — точные для seqovl
(`multisplit:pos=2,sniext+1:seqovl=679`, fwmark, оба lua-init, UDP fake). Попадание трафика:
счётчик очереди в /proc/net/netfilter/nfnetlink_queue вырос на 28 пакетов после двух новых
HTTPS-соединений — путь Xray→NFQUEUE наблюдён.

**FAIL hot-swap**: после правки config.toml демон перечитал настройки и перезапустил свой run
loop («настройки изменены» → новый экземпляр контроллера). Старый worker был остановлен, и с
этого момента каждый перезапуск проигрывает гонку: systemd Startеd → мгновенный Stopping со
стороны демона → `fallback worker_down`, бесконечный цикл (десятки попыток, интервал ~10–20 с,
совпадает с таймаутом 10 с сухого прогона внутри start). Worker не удерживается, offload при
«активном» профиле не отключается (снимки ethtool до/в ходе — без изменений), аргументы
hostfakesplit/disorder-badseq в живом worker-е не наблюдались, метка профиля в статусе не
менялась. PID Xray при всех переключениях не менялся (требование выполнено), HTTPS и VPN
работали весь flap (fail-open подтверждён). Гипотеза для разработчика: `alive()` проверяет
`occupied()` сразу после `systemd-run`, до фактической привязки очереди процессом — нужна
короткая пауза/повтор или проверка через `--wait`; плюс перезапуск run loop создаёт новый
Controller, который глушит worker предыдущего.

## §11 (отказы) — 11.2 PASS, 11.3 PASS, 11.1 NOT_RUN, 11.4 PASS

- 11.2: тестовый listener занял очередь 200 (transient unit, без desync); при engine=auto демон
  показал `fallback queue_busy` (в первом окне не успел перечитать конфиг — латентность ~1 мин
  фиксирую как наблюдение; повтор с удержанием listener — увидено в журнале). Чужой listener не
  пострадал, Xray не менялся.
- 11.3: приватная копия бинарника и Lua, group-writable Lua → `fallback unsafe_files`, worker не
  запущен; пути восстановлены. Отдельная находка: копия в приватном каталоге исполнителя
  (0700, /home) недоступна демону (ProtectHome=read-only + sandbox), и `find_installation`
  падает **необработанным PermissionError** на stat недоступного пути вместо чистого fallback —
  стоит обернуть is_file()/glob в try и считать путь not_found.
- 11.4: engine=off останавливает worker, после `xgw enable` nfq_output отсутствует, offload
  идентичен исходному, VPN/direct работают. «Отсутствующий движок» NOT_RUN — бинарник
  установлен, чужой файл не прятался.
- 11.1: NOT_RUN — из-за hot-swap FAIL нет длительно активного worker-а, остановку и
  автовосстановление в активном состоянии проверить нельзя.

## §12 (эскалация) — NOT_RUN; §5-видео — NOT_RUN

Естественного вердикта FROZEN/BODY_RESET/STALL в окне наблюдения не было; NFQ-ступени лестницы
заблокированы hot-swap FAIL. VIDEO_DIRECT: VPN работает, согласованного direct-пути YouTube вне
VPN на машине нет, маршруты без поручения не добавляются.

## §13: возврат — PASS

engine удалён из config.toml (конфиг **байтово идентичен** исходному — diff пуст), acct
возвращён в 0, panel.json идентичен, diag «OK — 33, WARN — 0, FAIL — 0», HEALTHY, capture on,
zapret2 selective off, тестовый юнит остановлен и отсутствует, offload идентичен, сторонние
таблицы не тронуты, PID Xray 262461 (сменился штатно при apply в §6–7, при профилях — нет).
HTTPS шлюза 200.

## Что осталось на машине

1. Установленный пакет XGW = CODE 9b58725 (штатный установщик; отката не было — все
   установочные проверки прошли). Движок off по отсутствию ключа.
2. /opt/zapret2 0755 (исправление прав из прошлого прогона).
Больше отличий нет: конфиги, panel.json, подписки, пул, pin, WAN/LAN/Tailscale — исходные.

## Сводка вердиктов

TESTS 16+4 PASS; INSTALL PASS; GENERATE PASS; FRAGMENT_LIVE PASS (config_and_xray_test);
QUIC_MATRIX PASS; VALIDATION PASS; NOISE_LIVE PASS; CIDR PASS; NFT_RESTORE PASS (21 с);
NFQ_PATH PASS (счётчики); HOT_SWAP **FAIL** (alive-гонка после рестарта run loop);
OFFLOAD NOT_RUN (неактивный worker); FAILURES: queue_busy PASS, unsafe_files PASS, off PASS,
stop-worker NOT_RUN; ESCALATION NOT_RUN; VIDEO_DIRECT NOT_RUN; RESTORE PASS.

Нерешённое: гонка старта worker-а (блокирует профили/offload/эскалацию/11.1) и необработанный
PermissionError в find_installation. Обход-доказательства (видео/невидимость) по-прежнему не
заявляются: проверены конфиги обоих ядер, попадание трафика в NFQUEUE и живой UDP-noise с
ответами STUN.

Отчёт без снимков, IP/доменов, имён серверов/устройств, URL и ключей; приватные журналы — в
каталоге прогона (mode 0700), worktree CODE сохранён до разбора отчёта.
