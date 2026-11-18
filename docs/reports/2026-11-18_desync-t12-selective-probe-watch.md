# Ubuntu 24.04 — T12: возврат веб-панели и счётчики очереди при HTTPS-пробе (1fc4e69) — 2026-11-18

- RESULT: **PANEL_RESUME=PASS (все проверки §2); обе сетевые попытки — fallback без
  active: попытка 1 — page `/t/terms` TLS-таймаут 10 129 мс (CDN не начиналась),
  попытка 2 — page прошла (200/57 247 Б/627 мс), CDN TLS-таймаут 20 232 мс с
  `first_tls_timeout_ms: 10156` (встроенный повтор выполнен и тоже отклонён) →
  `RETRY_LIVE=FAILED`, MEDIA_PATH=NOT_RUN, видео/rechecks — NOT_RUN**. Установка
  `zapret2.js 59e56f4a…` (манифест 1/1), cmp zapret2.py/zapret2_control.py с принятым
  `a382971` — OK (BLOCKED_BASE не было), таймер armed до apply, конфиги
  byte-identical. §1 тесты: 24 passed (panel-overview + management +
  route_evidence), node/bash OK. §2: уход вкладки в фон на 15 с — 0 периодических
  GET; возврат — GET сразу (0 мс), карточка готова через 3 мс; свёрнутое окно —
  0 GET за 15 с, возврат → 2 GET (visibility + плановый), карточка 9 мс; возврат из
  истории — GET через 0.54 с, карточка свежая без ручного обновления; throttling
  2.5 с/1.5 КБ/с: GET в полёте при скрытии — `net::ERR_ABORTED` (t+1.3 с), при
  возврате свежий GET без параллельных, плановый следующий через 8 с; черновик
  (retry 300→180) пережил скрытие окна 15 с без POST и ревизия формы сохранилась,
  отмена без записи. §3: комплект сохранён из формы (multisplit, 6 доменов
  подстановки, retry 120, HTTPS, `/t/terms`+CDN#1), off/off, blockers пуст.
  Попытка 1 (клик 04:41:07Z, кнопка доступна): preparing/probe_inbound →
  nfqueue → fallback/youtube_page_probe_failed (page {phase:tls, kind:timeout,
  elapsed_ms:10129, page_kind:terms}). Контроль при fallback: host GET той же
  страницы 200/0.47 c/57 247 Б, host GET того же CDN 200/0.26 c/31 Б. Попытка 2
  (off кнопкой, новый CDN#2 из DevTools, та же `/t/terms`, клик 04:46:36Z):
  page {ok:true, http:200, bytes:57247, elapsed_ms:627}, cdn {phase:tls,
  kind:timeout, elapsed_ms:20232, first_tls_timeout_ms:10156} →
  fallback/youtube_cdn_probe_failed. Контроль: страница 200/0.39 c, CDN#2 с хоста
  200/0.34 c/31 Б. Счётчики (selective_probe_watch, очередь 200): обе пробы шли при
  живом воркере (invocation 9e4be866 / 1a2549b1), очередь без backlog (0) и без
  дропов (kernel_drops=0, socket_drops=0) на каждой строке; gate {marked:true,
  fake:true} в течение всей пробы; outgoing-счётчик (handle 9) рос: попытка 1 —
  0→10 пакетов/3 187 Б (окно пробы 10 с), попытка 2 — скачок 39 пакетов/3 411 Б в
  первую секунду (page-передача 57 КБ через очередь), далее только 39→49
  пакетов/4 456 Б за 20 с двух CDN-попыток — исходящие TLS-пакеты уходят, ответа
  нет. §5: off кнопкой (policy_matched/off, probes очищен), новый сеанс YouTube —
  дельта ACCEPTED client_rule=false, xray +646.5 КиБ / +371.6 КиБ uplink за 40.1 c.
  Возврат **accept**: конфиги OK/OK, манифест new 1/1 на диске, xgw active, воркеры
  inactive, VPN/panel 200, таймер остановлен (за 67 мин), тестовый Chrome закрыт.
  Решение accept: панель/установщик исправны, TLS-нестабильность — отдельная сетевая
  проблема (оценивалась отдельно от обновления панели, как в ТЗ).
- CODE: `1fc4e69d569bbf583ffeb4e7799ff165741b3cc7`; база сетевого опыта — принятый
  слой `a382971` (cmp обоих контроллеров OK до apply). Манифест new (1):
  zapret2.js `59e56f4acf1623d5…`. Таймер 90 м armed до apply (NEXT 08:58:45 МСК),
  остановлен после сверки. Установленный слой оставлен (accept).
- §1: 24 passed + node --check + bash -n. Место 45 ГБ; tcpdump не запускался (по ТЗ
  захват пакетов запрещён; сборщик читал только локальные счётчики и статус).
- Финал: off/off, воркеры inactive, VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`
  byte-identical. Сырые JSONL (start-1/start-2), адреса CDN и снапы — локально в
  рабочей папке раунда (0700), в отчёт не включены.

## Таблица попыток (UTC)

| Параметр | Попытка 1 | Попытка 2 |
| --- | --- | --- |
| Клик Selective | 04:41:07Z (кнопка доступна) | 04:46:36Z (кнопка доступна) |
| Ревизия | `3ab4948b` | `3ab4948b` (тот же kit, новый CDN#2) |
| page | `{ok:false, phase:tls, kind:timeout, elapsed_ms:10129, page_kind:terms}` | `{ok:true, http:200, bytes:57247, elapsed_ms:627, page_kind:terms}` |
| cdn | не начиналась | `{ok:false, phase:tls, kind:timeout, elapsed_ms:20232, first_tls_timeout_ms:10156, bytes:0}` |
| Итог | fallback / youtube_page_probe_failed | fallback / youtube_cdn_probe_failed |
| Воркер invocation | 9e4be866 | 1a2549b1 |
| gate в пробе | marked+fake = true | marked+fake = true |
| Очередь | backlog 0, дропы 0, seq 0→10 | backlog 0, дропы 0, seq 39→49 |
| outgoing (handle 9) | 0→10 pkt / 3 187 Б | 39 pkt/3 411 Б (page) → 49 pkt/4 456 Б |
| Контроль с хоста | страница 200/0.47 c; CDN#1 200/0.26 c | страница 200/0.39 c; CDN#2 200/0.34 c |

- `RETRY_LIVE=FAILED` (TLS-таймаут был, встроенный повтор CDN выполнен —
  `first_tls_timeout_ms` присутствует, elapsed включает обе попытки, — но повтор
  отклонён сетью; финал fallback). MEDIA_PATH=NOT_RUN (active не было); пригодного
  720p в Selective — 0 с; VPN-контроль — PASS (новый сеанс через VPN, дельта
  xray +646.5 КиБ, client_rule=false).

## Наблюдения для Codex

1. **Проба через очередь уходит, но ответ не возвращается**: при открытом gate
   (marked+fake), живом воркере, backlog=0 и нулевых дропах исходящий счётчик
   растёт (ClientHello + ретрансмиты ≈ 10 пакетов за 10 с), TLS не завершается.
   Тот же адрес с хоста — 200 за 0.26–0.34 c. При этом в попытке 2 page-проба
   прошла через тот же probe-путь за 627 мс в той же секунде, когда CDN-проба
   стартовала в таймаут. Различие цели — www.youtube.com vs
   `rr*---sn-*.googlevideo.com`: похоже, ответный поток от googlevideo не
   возвращается в путь пробы (маршрут/маркировка/клиентское правило для CDN),
   а не потеря исходящих.
2. **Флап цели отказа** (r2: page отказала, CDN не начиналась; сейчас попытка 2:
   page прошла, CDN отказала) при стабильном host-контроле обеих целей — согласуется
   с зависимостью от состояния пути в момент пробы, а не от конкретного хоста.
3. PANEL_RESUME-фикс работает во всех сценариях, включая отмену зависшего GET при
   скрытии; «Загрузка…» больше не зависает после возврата видимости.
4. Сборщик selective_probe_watch дал полную картину (gate/outgoing/queue/invocation
   1 Гц) без захвата пакетов — достаточен для локализации следующего шага.
- Publication commit: `ce8c78b8f1334e85abef9902ad34d62d160ab893` (2fa54b8 → ce8c78b, remote verified byte-identical to local HEAD).
