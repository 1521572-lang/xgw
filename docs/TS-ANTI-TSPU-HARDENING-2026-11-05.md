# ТЗ: устранение уязвимостей и доработка устойчивости XGW к ТСПУ

Дата аудита: 2026-11-05.

Основание: статический аудит репозитория `https://github.com/1521572-lang/xgw`, локальной ветки `t01-xhttp` с отслеживанием `origin/freepool`, коммита `657745db5e47eab3da67e7bf440e9a891e364394`.

Это техническое задание на доработки, а не отчёт о внедрении. Выводы получены по исходникам и тестам. Реальный стенд, pcap на WAN, замеры JA3/JA4 и нагрузочное тестирование в рамках аудита не выполнялись. Поэтому подтверждённые кодом свойства отделены от характеристик, которые зависят от закреплённых версий Xray/sing-box и серверной конфигурации.

## 1. Оценка текущей эффективности против ТСПУ — Verdict Matrix

### Фактическая архитектура

**Data Plane:**

```text
LAN / локальные приложения / Docker
        │
        ▼
nftables: mark_proxy / mark_containers
        │
        ▼
policy routing
  ├─ TPROXY → 127.0.0.1:12345
  └─ TUN → xgwtun0
        │
        ▼
      Xray
        │
        ├─ direct / block / dns-out
        ├─ freedom.fragment → VPN-сервер
        ├─ обычный outbound → VPN-сервер
        └─ SOCKS 127.0.0.1:<port> → sing-box → VPN-сервер
```

- TPROXY/TUN и маршруты по меткам реализованы в `src/xgw/net/iprule.py:1-50`, `src/xgw/net/nft.py:634-711`, `src/xgw/net/tun.py:99-111`.
- Xray является единственной точкой входа, маршрутизации и балансировки: `src/xgw/generator/builder.py:796-870`, `src/xgw/generator/builder.py:873-926`, `src/xgw/generator/builder.py:958-1011`.
- sing-box не перехватывает трафик сам, а подключён через локальный SOCKS-мост: `src/xgw/generator/singbox.py:1-22`, `src/xgw/generator/singbox.py:205-213`.
- Сокеты Xray получают `sockopt.mark = mark_bypass`; sing-box исключается из перехвата по UID: `src/xgw/generator/builder.py:626-635`, `src/xgw/net/nft.py:266-267`, `src/xgw/net/nft.py:1092-1104`.
- Для TUN предусмотрен постоянный интерфейс и `blackhole`-маршрут, чтобы исчезновение интерфейса не открывало прямой путь: `src/xgw/net/iprule.py:19-39`.
- Отдельный egress-барьер `inet xgw_guard` в `postrouting`/`forward` должен закрывать защищённые пути даже при повреждении основной таблицы: `src/xgw/net/nft.py:1059-1130`.
- eBPF/XDP/TC в data plane не используются. Обработка полезного трафика выполняется Xray/sing-box в userspace.

**Control Plane:**

- Xray сам выполняет `burstObservatory`-пробы участников и работу `leastPing`: `src/xgw/generator/builder.py:983-1010`.
- Демон читает `/debug/vars`, но не считает отсутствующую запись сразу признаком мёртвого узла: `src/xgw/xraycore/metrics.py:22-39`, `src/xgw/xraycore/metrics.py:58-80`.
- Watchdog работает по умолчанию каждые 20 секунд с джиттером ±20%: `src/xgw/config.py:447-458`, `src/xgw/daemon.py:885-917`, `src/xgw/daemon.py:396-398`.
- Машина состояний различает `XRAY_DOWN`, `WAN_DOWN`, `LEAK`, `PROBE_TARGET_UNREACHABLE`, `ALL_DEAD`, `RESERVE`, `DEGRADED`, `HEALTHY`: `src/xgw/watch/states.py:26-34`, `src/xgw/watch/states.py:81-111`.
- Сквозные GET-пробы обнаруживают тишину до/после начала тела, RST и общий тайм-аут. Бесконечного ожидания нет: по умолчанию детектор тишины — 5 секунд, общий предел — 60 секунд: `src/xgw/watch/checks.py:57-99`, `src/xgw/watch/checks.py:239-250`, `src/xgw/watch/checks.py:304-368`.
- Есть пассивный контроль скорости и активный поиск замены при троттлинге: `src/xgw/watch/guard.py:76-106`, `src/xgw/watch/guard.py:122-176`, `src/xgw/daemon.py:5993-6159`.
- Изменения Xray обычно применяются через API; изменения основных inbound/DNS/observatory требуют перезапуска: `src/xgw/generator/diff.py:1-26`, `src/xgw/generator/diff.py:79-124`.
- Новое поколение sing-box проверяется отдельным процессом и реальным запросом до переключения мостов: `src/xgw/apply/singbox_generation.py:126-176`, `src/xgw/apply/singbox_generation.py:196-242`.

### Матрица

| Вектор ТСПУ | Статус | Как ТСПУ может пробить или сдеградировать защиту |
|---|---|---|
| **1. L3/L4 Stateful DPI, reassembly, RST, UDP** | **Частично** | Xray умеет дробить `tlshello` и первые `1-3` записи, sing-box — TLS record/TCP fragment: `src/xgw/generator/fragment.py:164-196`, `src/xgw/generator/singbox.py:117-142`. Но stateful DPI с полной TCP/TLS reassembly может восстановить ClientHello. Специальной проверки RST по TTL/window/sequence нет; валидный по TCP-последовательности внедрённый RST завершит внешнее соединение. UDP-транспорты поддерживаются через sing-box, но принудительный UDP-drop лишь приводит к реактивному поиску другого профиля, а не к противодействию самому дропу. |
| **2. TLS/QUIC fingerprinting, JA3/JA4/JA4S, HTTP/2** | **Частично** | `fp`, SNI, ALPN и REALITY переносятся из ссылок; sing-box получает uTLS, по умолчанию `chrome`: `src/xgw/parsers/common.py:214-263`, `src/xgw/parsers/convert.py:185-230`. Это выбранный шаблон, а не доказанная побайтовая идентичность Chrome. Ротации согласованных профилей нет. ECH, часть TLS-настроек и REALITY `mldsa65Verify` не входят в общий переносимый профиль: `src/xgw/parsers/convert.py:209-216`, `src/xgw/parsers/convert.py:354-365`. JA4S и поведение сервера этим клиентским репозиторием не контролируются. |
| **3. Статистический/ML-анализ длин, таймингов и mux** | **Уязвимо** | Дробление затрагивает преимущественно handshake/первые записи, а не весь поток. Общего padding для payload и управления inter-arrival time нет. `h2mux + padding` доступен только ограниченному набору протоколов: `src/xgw/generator/singbox.py:97-114`, `src/xgw/generator/singbox.py:129-130`. Длительные TCP-туннели, периодические пробы и характерная мультиплексация остаются доступными для flow-классификации. |
| **4. Мягкая деградация, blackhole, packet loss** | **Частично** | Есть детектор зависания, RST, пассивная оценка скорости, повторные замеры и гистерезис переключения. Однако при скорости ниже `ACTIVE_FLOOR_MBPS = 1` пассивная оценка не инициирует замер: `src/xgw/watch/guard.py:48-50`, `src/xgw/watch/guard.py:99-103`. Короткий замер с объёмом менее 256 КиБ возвращает `mbps=None`, который не засчитывается как низкая скорость: `src/xgw/watch/speed.py:35-38`, `src/xgw/watch/speed.py:99-108`, `src/xgw/watch/guard.py:122-127`. Поэтому стабильные 16–64 Кбит/с могут долго оставаться «живым» каналом. |
| **5. Self-Fingerprinting healthcheck/speedtest** | **Частично** | Таймеры демона в основном получают джиттер, сканы запрашивают случайный `Range`, speedtest ограничен по времени/объёму: `src/xgw/watch/scan.py:40-49`, `src/xgw/daemon.py:1532-1541`. Но внутренние пробы Xray имеют общие `interval/sampling/timeout` без задаваемого XGW per-server jitter: `src/xgw/generator/builder.py:998-1010`. Основной цикл сканов идёт подряд без пауз: `src/xgw/daemon.py:2964-3003`; диагностика цели может запускать до восьми проб одновременно: `src/xgw/daemon.py:2062-2070`. |
| **6. Active probing, утечки маршрутизации, kill switch** | **Частично** | Loopback-входы не являются публичными SOCKS/HTTP-серверами; IPv6 LAN по умолчанию запрещён, DNS перехватывается, VPN-outbound имеют bypass mark/UID. Но есть сознательные прямые маршруты для RU-доменов/IP, bypass-хостов, Tailscale, DHCP/NTP и connectivity check: `src/xgw/config.py:336-348`, `src/xgw/generator/builder.py:882-900`, `src/xgw/net/nft.py:1103-1114`. Главный дефект — после удаления правил и ошибки полного `capture.up()` независимый барьер отдельно не восстанавливается. Active probing удалённого VPN-сервера этим клиентским аудитом не проверяется. |

## 2. Реестр найденных проблем в коде и архитектуре

### Critical

#### C-01. Восстановление перехвата может оставить шлюз без kill switch

- **Локация:** `Daemon._guard_capture()`, `src/xgw/daemon.py:2218-2228`, `src/xgw/daemon.py:2263-2275`; `Capture.loaded()`, `src/xgw/net/capture.py:866-883`; `Capture.guard_loaded()`, `src/xgw/net/capture.py:617-641`.
- **Суть:** при `loaded() is False` вызывается полный `capture.up()`. Если он выбрасывает исключение, обработчик только логирует ошибку и проверяет `guard_loaded()`. Отдельного `nft.apply(render_guard(...))` или `restore_guard()` нет.
- **Сценарий:** сторонний `flush ruleset` удалил и `ip xgw`, и `inet xgw_guard`; затем полное восстановление упало, например из-за TUN, маршрута, IPv6 или другой части конфигурации. До следующего успешного полного восстановления защищённый TCP/UDP может идти напрямую.
- **Последствие:** нарушение основного обещания `fail_mode=closed`; утечка реального IP и DNS/прикладного трафика. Периодический повтор не устраняет окно fail-open.

### High

#### H-01. `hold=block` не закрывает сеть при отсутствующем или повреждённом `xray.json`

- **Локация:** `Capture._applied()` и `Capture.hold_mode()`, `src/xgw/net/capture.py:336-342`, `src/xgw/net/capture.py:385-400`; закрепляющий тест — `tests/test_net.py:367-378`.
- **Суть:** `_applied() is None` приводит к `off`, даже если `capture.hold_blocks` истинно.
- **Последствие:** при первичной загрузке без конфига или повреждении JSON трафик идёт напрямую. Это задокументированный bootstrap-компромисс, но его нельзя считать fail-closed поведением.

#### H-02. Слепая зона для сильного, но неполного троттлинга

- **Локация:** `Guard.sample()`, `src/xgw/watch/guard.py:76-106`; `Guard.note_total()`, `src/xgw/watch/guard.py:122-142`; `speed.measure()`, `src/xgw/watch/speed.py:77-108`; параметры — `src/xgw/config.py:248-293`.
- **Суть:** пассивная скорость от 0 до 1 Мбит/с не ставит активный замер в очередь. При `max_seconds=8` канал 64 Кбит/с передаст около 64 КБ; это меньше `MIN_BYTES=256 КиБ`, поэтому результат становится ошибкой измерения с `mbps=None`, а не низкой оценкой.
- **Последствие:** живой, но практически непригодный канал не проходит пороги `low_count=3` и не запускает обычный поиск замены. Плановые замеры по умолчанию выполняются раз в шесть часов. Отдельная YouTube-проверка может обнаружить частный случай деградации Google-трафика, но не заменяет общий детектор: `src/xgw/watch/youtube.py:78-123`.

#### H-03. Активные проверки сохраняют предсказуемые фазы и burst-паттерны

- **Локация:** `burstObservatory`, `src/xgw/generator/builder.py:998-1010`; очередь сканов — `src/xgw/daemon.py:2698-2725`; исполнение — `src/xgw/daemon.py:2964-3003`; параллельная диагностика — `src/xgw/daemon.py:2062-2070`.
- **Суть:** XGW задаёт один интервал для всех участников Xray и не задаёт случайный per-server phase. В основном `_scan_step()` нет пауз между запросами; порядок запасных детерминирован рейтингом. Функция `scan_spares()` с shuffle/jitter существует в `src/xgw/watch/scan.py:156-172`, но основной daemon flow её не использует.
- **Последствие:** на WAN могут наблюдаться повторяющиеся серии однотипных TLS-сессий к пулу VPN-адресов. Это упрощает связывание и последующую блокировку пула. При этом одновременный старт всех внутренних проб Xray кодом XGW не доказан — это надо проверить pcap на закреплённой версии ядра.

#### H-04. Нет целостной защиты от статистического анализа всего потока

- **Локация:** профили — `src/xgw/generator/profiles.py:1-29`, `src/xgw/generator/profiles.py:181-197`; ограничения mux — `src/xgw/generator/singbox.py:97-114`; fragmentation — `src/xgw/generator/fragment.py:164-196`.
- **Суть:** реализованы полезные механизмы обхода сигнатур handshake, но нет согласованной с сервером схемы padding/noise для всего сеанса, управления burst size и таймингами. Mux-профиль нельзя применить ко всем протоколам и ко всем VLESS с `flow`.
- **Последствие:** после отказа от простой SNI-фильтрации ТСПУ может классифицировать длительный туннель по распределению размеров, направлению всплесков, RTT и межпакетным интервалам. TCP-over-TCP также сохраняет проблемы производительности при потерях: внешний и внутренний TCP независимо повторяют передачи.

### Medium

#### M-01. Внедрённые RST не анализируются по сетевым аномалиям

- **Локация:** классификация обрыва — `src/xgw/watch/checks.py:277-280`, `src/xgw/watch/checks.py:328-333`; прямой TCP-check возвращает только bool — `src/xgw/watch/checks.py:467-474`.
- **Суть:** нет сбора TTL, TCP window/options, расстояния до expected sequence или сопоставления RST с предыдущими пакетами. RST корректно становится признаком отказа и может запустить смену профиля, но поддельный пакет не отбрасывается.
- **Последствие:** DPI способен дешёво вызывать обрывы и failover. TLS защищает содержимое от незаметной модификации, но не предотвращает denial of service через TCP reset.

#### M-02. Перенос TLS/REALITY между ядрами покрывает только общее подмножество

- **Локация:** `src/xgw/parsers/convert.py:1-16`, `src/xgw/parsers/convert.py:129-171`, `src/xgw/parsers/convert.py:185-231`, `src/xgw/parsers/convert.py:354-365`.
- **Суть:** XHTTP, mKCP, H2, некоторые цепочки/mux/pinning не конвертируются; ECH и TLS version/cipher/curve controls при обратном преобразовании отклоняются; `mldsa65Verify` не переносится в sing-box.
- **Последствие:** часть серверов не может пройти всю лестницу профилей. Это безопасный отказ от неподдерживаемой конвертации, а не молчаливое отключение проверки сертификата, но он уменьшает число доступных путей обхода.

#### M-03. Политика по умолчанию не означает «весь трафик только через VPN»

- **Локация:** `src/xgw/config.py:336-348`, `src/xgw/generator/builder.py:882-926`, `src/xgw/net/nft.py:57-64`, `src/xgw/net/capture.py:690-722`.
- **Суть:** `.ru/.su/рф` и `geoip:ru` по умолчанию идут direct; отдельные устройства, сети, Tailscale и служебные сервисы также имеют исключения. При `tailscale.route=vpn` падение Xray намеренно переводит Tailscale напрямую.
- **Последствие:** это не скрытая утечка, а явная split-routing политика. Однако при требовании полного скрытия всего исходящего трафика конфигурация по умолчанию ей не соответствует.

#### M-04. Применение конфигурации Xray не является общей транзакцией

- **Локация:** `src/xgw/apply/applier.py:122-190`, `src/xgw/apply/applier.py:192-204`; смена sing-box — `src/xgw/apply/singbox_generation.py:196-242`.
- **Суть:** API-план состоит из последовательности операций. В обычном режиме ошибка API помечает конфигурацию частично применённой и ведёт к перезапуску; в режиме смены поколения sing-box восстановление прежних объектов выполняется best effort.
- **Последствие:** возможны временное частичное состояние и дополнительный restart. Блокировки, precheck и candidate/drain снижают риск, но не делают два процесса и несколько API-вызовов атомарной транзакцией.

#### M-05. Производительность ограничена userspace-конвейером, но узкое место не измерено

- **Локация:** TPROXY/TUN — `src/xgw/net/nft.py:634-711`, `src/xgw/generator/builder.py:821-853`; дополнительный SOCKS-hop — `src/xgw/generator/singbox.py:1-18`.
- **Суть:** пакеты проходят kernel→userspace→kernel; при sing-box добавляется второй userspace-процесс и локальная SOCKS-инкапсуляция. Python-демон и его блокировки не находятся на горячем пути пакетов.
- **Последствие:** потенциально выше CPU usage, задержка и число копирований, особенно при TCP-over-TCP. Код не доказывает конкретную деградацию: нужны `perf`, нагрузочный тест и сравнение TPROXY/TUN, Xray-only и Xray→sing-box. Преждевременный переход на eBPF не оправдан.

## 3. Конкретные технические доработки — Engineering Proposals

### C-01: сделать восстановление барьера независимым

1. Добавить `nft.apply_guard(rules, runner)`, который одной `nft -f` транзакцией заменяет только `inet xgw_guard`.
2. В `Capture` добавить `restore_guard()` с отдельной проверкой manifest и обновлением `guard_baseline/guard_spec`.
3. В обработчике ошибки `_guard_capture()` вызывать восстановление барьера, если `guard_loaded() is False`, независимо от успешности основного `capture.up()`.
4. Не переводить ошибку полного восстановления в молчаливый `off`; показывать отдельные состояния `capture_failed` и `guard_failed`.
5. Добавить стендовый сценарий: удалить обе таблицы, сломать основную загрузку, проверить исходящее TCP/UDP-соединение к контрольному WAN-адресу. Оно должно быть заблокировано после аварийного восстановления guard.

### H-01: устранить bootstrap fail-open

- Если выбран `hold=block`, отсутствие конфига должно приводить к `blocked`, а не `off`.
- Для первичной установки оставить только явно ограниченный provisioning-канал: DHCP/время и запросы демона к подпискам с `mark_bypass`. Не открывать весь LAN/хост.
- Обновить тест `tests/test_net.py:367-378`: `None` и повреждённый JSON должны давать `blocked` при `hold=block`.

### H-02: исправить измерение очень низкой скорости

- Если загрузка остановлена по `max_body_seconds`, скорость нужно считать даже при объёме меньше `MIN_BYTES`. Минимальный объём должен отклонять только слишком короткий завершённый файл, но не полноценный восьмисекундный замер.
- Добавить счётчик последовательных окон с ненулевым, но очень низким клиентским трафиком. Например, три окна `0 < mbps < 1` должны запускать активный замер. Нулевой трафик по-прежнему не означает деградацию.
- Добавить в классификацию jitter RTT, долю неудачных E2E и, при доступе к netlink/`/proc/net/netstat`, рост TCP retransmissions. Это отличит медленный сервер от полного blackhole и поможет обнаружить периодический packet loss.
- Сохранить существующие гистерезис `gain_pct`, `min_mbps`, cooldown и суточный бюджет — они предотвращают бесконечную карусель: `src/xgw/watch/guard.py:154-188`.

### H-03: убрать синхронные серии проверок

- Внутри `_scan_step()` добавить небольшие случайные паузы между запасными, учитывая их в `SCAN_BUDGET`.
- Сохранять приоритет участников и аварийных альтернатив, но рандомизировать порядок внутри одного класса/рейтингового диапазона.
- Ограничить `_diagnose_target()` двумя параллельными пробами или выполнять их каскадом с рандомизированным стартом; восемь одновременных TLS-сессий не должны быть обычным диагностическим паттерном.
- Для Xray нужен отдельный per-outbound probe scheduler либо поддержка `jitter/phase` в самом ядре. Поля `burstObservatory` с такими параметрами в текущем генераторе отсутствуют; нельзя просто добавить выдуманный ключ JSON и считать проблему решённой.
- На стенде записывать начало/конец каждой пробы с outbound tag и синхронно снимать pcap на WAN. Проверять распределение inter-probe time отдельно для каждого VPN-IP и для всего пула.

### H-04 и M-01: перейти от сигнатурного обхода к проверяемым транспортным профилям

- Не полагаться на fragmentation как на защиту от stateful reassembly. Оставить её как первую дешёвую ступень.
- Использовать padding/noise только там, где их понимает сервер. Односторонняя вставка произвольных байтов в TLS/TCP нарушит протокол и не создаст корректной маскировки.
- Для подходящих серверов предпочитать REALITY/современный UDP-транспорт с серверной obfuscation; mux включать выборочно, сравнивая выигрыш против появления устойчивого H2-паттерна.
- RST не следует отбрасывать только по «необычному TTL»: законный путь может менять TTL, а атакующий способен его подобрать. eBPF/TC или AF_PACKET стоит использовать прежде всего для телеметрии TTL/window/seq и корреляции сбоев. Решение о failover принимать по повторяемости RST на нескольких путях и фазе соединения.
- `SO_MARK` уже корректно применён. `TCP_WINDOW_CLAMP` не является защитой от DPI и не должен вводиться как таковая. BBR уже включается глобально в `src/xgw/net/capture.py:828-851`; его влияние на остальные соединения машины нужно учитывать при изменении sysctl.

### M-02: сделать TLS-профили проверяемыми

- Для каждого сервера хранить согласованный набор: протокол, transport, SNI, ALPN, uTLS fingerprint, REALITY/ECH/PQ-параметры.
- Не менять fingerprint случайно на каждом соединении: несогласованная ротация сама становится аномалией. Выбирать стабильный профиль на сервер и проверять его pcap/JA3/JA4.
- При невозможности переноса ECH, PQ или certificate pinning явно помечать профиль недоступным, как сейчас делает `Unsupported`, а не упрощать TLS.
- Серверный active-probing checklist должен включать поведение при неверном UUID/SNI/shortId, REALITY fallback, соответствие сертификата/ALPN, отсутствие открытых SOCKS/WebSocket management-портов и отсутствие специфического ответа на malformed handshake. Эти свойства нельзя подтвердить кодом XGW.

### M-03–M-05: эксплуатационная прозрачность и производительность

- В `xgw status` показывать отдельно: трафик через VPN, direct по домену/IP, bypass-хосты, Tailscale direct, служебные исключения, текущее состояние guard.
- Для режима «полный VPN» предложить профиль, который отключает `direct_domains`, `direct_ips`, `kernel_direct` и необязательные bypass-исключения.
- Перед оптимизацией измерять throughput, CPU на Гбит/с, retransmissions и latency для четырёх путей: direct, Xray TPROXY, Xray TUN, Xray→sing-box. eBPF имеет смысл рассматривать только после подтверждения kernel/userspace bottleneck.

## 4. Пошаговый план патчей — Ready-to-Implement Specs

### PR-1. Независимое аварийное восстановление `xgw_guard`

**Файлы:** `src/xgw/net/nft.py`, `src/xgw/net/capture.py`, `src/xgw/daemon.py`, сетевые unit/stand-тесты.

Каркас реализации:

```python
# src/xgw/net/nft.py
def apply_guard(rules: Rules, runner: Runner) -> None:
    text = render_guard(rules)
    if not text:
        raise CommandError("защищённый режим требует inet xgw_guard")
    runner(["nft", "-f", "-"], input=text)
```

```python
# src/xgw/net/capture.py
def restore_guard(self) -> None:
    with self._lock():
        rules = self.rules(self.effective_mode())
        with self._own_rules():
            nft.apply_guard(rules, self.runner)

        guard = nft.listing(self.lister, "inet", nft.GUARD)
        wanted = nft.render_guard(rules)
        if guard is None or nft.manifest_problem(
            nft.manifest(wanted, "inet", nft.GUARD),
            nft.manifest(guard, "inet", nft.GUARD),
            f"inet {nft.GUARD}",
        ):
            raise CaptureError("барьер inet xgw_guard не восстановлен")

        self._save(
            guard_baseline=nft.tables_digest(
                nft.structure(guard, "inet", nft.GUARD)
            ),
            guard_spec=nft.tables_digest(wanted),
        )
```

В `Daemon._guard_capture()` ветка ошибки должна пытаться восстановить барьер:

```python
        except Exception as exc:
            text = f"правила перехвата не загружены: {exc}"
            guard_loaded = getattr(capture, "guard_loaded", None)
            restore_guard = getattr(capture, "restore_guard", None)
            if guard_loaded is not None:
                try:
                    if guard_loaded() is False and restore_guard is not None:
                        restore_guard()
                        text += "; независимый барьер восстановлен отдельно"
                    elif guard_loaded() is True:
                        text += "; барьер соответствует политике и остаётся загруженным"
                    else:
                        text += "; состояние независимого барьера не подтверждено"
                except Exception as guard_exc:
                    text += f"; КРИТИЧНО: барьер не восстановлен: {guard_exc}"
            # Далее существующие log/notifier.
```

**Приёмка:** после внешнего удаления таблиц и намеренной ошибки `capture.up()` guard восстанавливается; тестовое исходящее соединение без bypass mark блокируется. При явных `off/open` аварийное восстановление не должно менять выбранную пользователем политику.

### PR-2. Истинный `hold=block` до появления рабочего конфига

Минимальное изменение:

```python
# src/xgw/net/capture.py
def hold_mode(self) -> str:
    if self.cfg.capture.hold_blocks:
        return "blocked"
    return "off"
```

**Приёмка:**

- отсутствует `xray.json` + `hold=block` → `blocked`;
- повреждённый JSON + `hold=block` → `blocked`;
- `hold=direct` или `fail_mode=open` → прежнее поведение;
- DHCP, время и provisioning-подписка работают через разрешённые исключения;
- LAN без bypass не получает прямой интернет.

### PR-3. Детектор шейпинга 16–64 Кбит/с

Сначала исправить результат ограниченного по времени замера:

```python
# src/xgw/watch/speed.py, в measure()
seconds = round(result.body_seconds, 2)
if not result.ok:
    return SpeedResult(None, result.downloaded, seconds, result.error)

capped_by_time = (
    cfg.speed.max_seconds > 0
    and result.body_seconds >= cfg.speed.max_seconds - 0.25
)
if result.downloaded < MIN_BYTES and not capped_by_time:
    return SpeedResult(
        None, result.downloaded, seconds,
        f"файл замера слишком мал: {result.downloaded} байт — "
        "укажите speed.url побольше",
    )
if result.downloaded <= 0 or result.body_seconds <= 0:
    return SpeedResult(None, result.downloaded, seconds, "нет данных для оценки скорости")

mbps = result.downloaded * 8 / result.body_seconds / MB
return SpeedResult(round(mbps, 3), result.downloaded, seconds)
```

Затем добавить в `Guard` счётчик низких ненулевых пассивных окон:

```python
# Поле Guard:
low_active_windows: dict[str, int] = field(default_factory=dict)

# В sample(), после вычисления mbps:
if 0 < mbps < self.cfg.speed.low_mbps:
    self.low_active_windows[key] = self.low_active_windows.get(key, 0) + 1
else:
    self.low_active_windows.pop(key, None)

if (
    key not in self.throttled
    and self.low_active_windows.get(key, 0) >= 3
):
    self.recheck_at.setdefault(key, now)
```

Существующую ветку `ACTIVE_FLOOR_MBPS <= ...` можно сохранить для немедленного реагирования на диапазон 1–10 Мбит/с, а новый счётчик использовать для диапазона ниже 1 Мбит/с.

**Обязательные тесты:**

- 64 КБ за 8 секунд → приблизительно `0.064 Мбит/с`, а не `None`;
- три таких итога → `throttled`;
- нулевой клиентский трафик не запускает замер;
- короткий полностью скачанный файл по-прежнему отклоняется;
- высокая оценка очищает серию;
- поиск замены сохраняет бюджет и гистерезис.

### PR-4. Рандомизация активных проверок без потери аварийности

Для `_scan_step()`:

```python
previous_role = None
while self.scan_queue and self.clock() - started < SCAN_BUDGET and not self.stopping:
    probe_tag = self.scan_queue[0]
    info = nodes.get(probe_tag)
    if (
        info is not None
        and info.role == "spare"
        and previous_role == "spare"
    ):
        remaining = SCAN_BUDGET - (self.clock() - started)
        if remaining <= 0.2:
            break
        self._stop.wait(random.uniform(0.2, min(1.5, remaining)))
    previous_role = info.role if info is not None else None

    probe_tag = self.scan_queue.popleft()
    # Далее существующая обработка.
```

Дополнительно:

- ограничить `PROBE_WORKERS` в `_diagnose_target()` до 2;
- рандомизировать порядок запасных внутри равного рейтингового класса;
- участников, аварийные альтернативы и ручные запросы не задерживать;
- завести отдельную задачу на per-server jitter/phase внутри Xray или на внешний scheduler с доказанной интеграцией в выбор балансировщика.

**Приёмка:** unit-тесты подтверждают соблюдение `SCAN_BUDGET` и отмену через `_stop`; pcap показывает отсутствие одинаковых серий запросов и одновременного восьмипоточного burst.

### PR-5. Проверяемая матрица транспортов и TLS

Для каждого поддерживаемого профиля зафиксировать:

- `protocol / transport / security / fingerprint / SNI / ALPN`;
- допустимость `fragment`, `split`, `mux_padded`;
- причину недоступности профиля;
- pcap ClientHello и вычисленные JA3/JA4;
- поведение при fragmentation reassembly, RST на handshake, RST после тела, UDP-drop и packet loss 1–10%;
- результат failover и время восстановления.

Не объявлять профиль «browser-like» до прохождения pcap-проверки на фактически установленных Xray `26.10.21` и sing-box `1.14.3`: `src/xgw/config.py:400-421`.

### PR-6. Политика маршрутизации и измерение производительности

- Добавить явный режим полного туннелирования без RU/direct/Tailscale-исключений, кроме минимально необходимых для загрузки и управления.
- Отображать все активные исключения в статусе.
- Измерить четыре варианта data plane под одинаковой нагрузкой и только затем решать вопрос о eBPF или изменении моста.
- Добавить fault-injection тесты для частичного Xray API, падения candidate sing-box, SIGTERM во время применения и шторма RST; проверять отсутствие роста FD/потоков и восстановление guard после каждого сценария.

**Итоговый приоритет:** сначала PR-1 и PR-2, поскольку они устраняют реальные fail-open пути; затем PR-3 и PR-4, закрывающие деградацию и самовыдачу мониторинга; только после этого — усложнение маскировки и оптимизация data plane.
