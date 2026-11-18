# Ubuntu 24.04 — T12: короткие пары Xray/NFQUEUE и путь видеотрафика Selective (a1ad5d0) — 2026-11-18

- RESULT: **MEDIA_PATH=NOT_RUN — active не достигнут ни в одной из двух попыток:
  попытка 1 — fallback/youtube_cdn_probe_failed (page ok 701 мс, CDN TLS-таймаут
  20 310 мс); разрешённый один повтор после off со свежим URL от плеера (фактический
  IP НЕ изменился) — снова fallback/youtube_cdn_probe_failed (page ok 402 мс, CDN
  TLS-таймаут 20 333 мс). Пары media-pairs: 0 accepted / 118 rejected — все
  `route_sample_missing` (state != active → Xray-снап не снимался; ожидаемо без
  active)**. Главный вклад раунда — новое TCP-доказательство на попытке 2: в окне
  CDN-пробы сокеты к тому же CDN-IP (D) — **ESTAB с bytes_acked=518** (SYN и
  ClientHello ушли и подтверждены, retrans=5), но **bytes_received=0,
  data_segs_in=0 на каждой строке за 20 с** — ни одного входящего сегмента. При
  этом bypass-WAN TCP к тому же IP — **connected за 51 мс** (wan-diag до повтора,
  маршруты обеих меток идентичны). Это сужает дефект: рукопожатие и исходящие
  данные дошли и подтверждены (вероятно, fake-ACK механикой nfqws2 при
  gate{marked,fake}=true), а настоящий ответный поток не возвращается на
  помеченный сокет; тот же IP direct — быстрый. §1: checkout `a1ad5d0`, **20
  passed**, bash OK, cmp трёх файлов панели — OK (установка не требовалась), таймер
  60 м armed до изменения настроек. Подготовка: контрольный example.com через VPN
  (200), свежий CDN от плеера (endpoint D), комплект (multisplit, 6 доменов,
  retry 120, HTTPS, `/t/terms`, CDN) — off/off, blockers пуст; плеер закрыт;
  snap vpn-before; collect first 180 с (media-pairs+socket-stats, очередь 200) →
  клик 15:56:12Z → fallback (строка выше). §2.5: off кнопкой → свежий URL
  (harvest повторной загрузкой; host и IP D те же — отмечено) → kit2
  (ревизия `2ed55427`) → collect second 180 с → клик 16:03:44Z → fallback.
  §3: off кнопкой (probes очищен, воркеры inactive), **новый сеанс YouTube через
  VPN — дельта ACCEPTED client_rule=false, xray +5.0 МБ downlink / +571.5 КиБ
  uplink за 42.1 c**. Возврат **accept**: конфиги OK/OK, xgw active, воркеры
  inactive, off/off, VPN/panel 200, таймер остановлен (за ~43 мин), тестовый
  Chrome закрыт. Решение accept: слой/сборщик исправны (пары честно отклонены без
  active), TLS-отказ — сетевой дефект пути пробы, не регрессия.
- CODE: `a1ad5d03bd97503e15e021c94af8752bd7c3f494`; §1 тесты: 20 passed
  (probe_watch с media-pairs + route_evidence). Таймер unit
  xgw-selective-media-1795017221, armed 18:53:42 МСК, остановлен после сверки.
- TCP-факты окна CDN-пробы попытки 2 (обезличено; IP = D; JSONL локально в $D
  0700): сокеты s7, s8 → D, states {ESTAB, FIN-WAIT-1}, max bytes_acked=518,
  retrans=5, bytes_received=0, data_segs_in=0 на всех 7 строках окна; gate
  {marked:true, fake:true}; outgoing 43→52 pkt; kernel_drops=0. В попытке 1 —
  0 сокетов в выборке (окно между замерами 3 с; короткая фаза не попала — по ТЗ
  «быстрая успешная проба может целиком пройти между двумя замерами»; fallback
  зафиксирован overview-JSON).
- Финал: off/off, воркеры inactive, очередь пуста, VPN/panel 200, конфиги
  `89bf2a67…`/`33916cb5…` byte-identical. Место 43 ГБ. Захват пакетов не вёлся.

## Таблица попыток (UTC)

| Параметр | Попытка 1 | Попытка 2 (повтор) |
| --- | --- | --- |
| Клик | 15:56:12Z | 16:03:44Z |
| Ревизия | `50b58ba9` | `2ed55427` (новый URL, тот же IP D) |
| page | ok 701 мс / 57 247 Б | ok 402 мс / 57 247 Б |
| cdn | TLS-таймаут 20 310 мс | TLS-таймаут 20 333 мс |
| TCP в окне CDN | сокет D не попал в выборку (3 с шаг) | ESTAB, acked=518, retrans=5, recv=0, segs_in=0 |
| bypass-WAN к D (маршруты идентичны) | — | connected 51 мс (diag до повтора) |
| Итог | fallback / youtube_cdn_probe_failed | fallback / youtube_cdn_probe_failed |

- Принятых пар: 0; отклонено: 118 (59+59), причина у всех `route_sample_missing`
  (без active). RETRY_LIVE: не применим (встроенный повтор CDN выполнялся в обеих
  попытках — first_tls_timeout_ms присутствовал в обоих overview-JSON — и отклонён).
- MEDIA_PATH=**NOT_RUN** (active не было); пригодных секунд видео в Selective — 0;
  VPN-контроль — PASS (новый сеанс, xray +5.0 МБ / 42.1 c, client_rule=false).

## Наблюдения для Codex

1. **Ответный поток не возвращается на помеченный сокет при подтверждённой отправке**:
   ESTAB + bytes_acked=518 (ClientHello принят и подтверждён) + recv=0/segins=0 за
   20 с, при bypass к тому же IP за 51 мс и идентичных решениях маршрута. Это
   уточняет картину TCP-раунда (там был SYN-SENT к недоступному B): теперь видно,
   что даже на доступном IP (bypass OK) probe-путь теряет именно ответные данные.
   Подтверждение acked с большой вероятностью генерируется fake-ответом nfqws2
   (gate fake=true) — настоящий ответ от сервера не доходит/не размечается обратно.
2. **Гипотеза «недоступные endpoint'ы» сужена**: доступность direct (bypass) не
   гарантирует успех probe-пути (D: bypass 51 мс — probe TLS-таймаут). Прошлый
   успех WAN-раунда (CDN 193 мс через probe) при том же механизме — ключ к
   сравнению: чем отличался тот endpoint/момент (endpoint C, первый tick после
   старта воркера?).
3. **Флап цели отказа продолжается** (page 701/402 ok, CDN падает) при стабильном
   bypass; page и CDN идут в одну секунду — различие только в целевом IP/пути
   ответа.
4. media-pairs механика работает (пары считаются, окна/гейты проверяются) — при
   активном Selective в следующем раунде готова к сбору; шаг 3 с достаточен.
- Publication commit: `356be6a489a2b22b9c7d5344da763bb7df211666` (ba62c75 → 356be6a, remote verified byte-identical to local HEAD).
