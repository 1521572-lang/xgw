# Ubuntu 24.04 — T12: счётчики Selective и диагностика проб (bec3009) — 2026-11-17

- RESULT: **PASS на проверках сбора и отказе Selective по CDN; BLOCKED_PROBE для
  активной Selective-фазы, видео и длинного опыта — данные для Codex полные**.
  Установка слоя r3 `a8b177f` сверена по манифесту (8/8 OK на машине), целевые тесты
  `bec3009` — 93 passed, конфиги byte-identical, таймер 90 м (UTC 15:49:43Z → 20:19:43
  МСК). VPN-контроль через браузер — PASS: воспроизведение + example.com через VPN,
  дельта **xray +3.06 МБ за 4.1 c, client_rule=false**. Selective попытка 1
  (page=watch, 12/6 c): **fallback/youtube_page_probe_failed — page {phase:tls,
  kind:timeout, elapsed 5122 мс}**; VPN жив, direct-правил нет, выключено кнопкой.
  Попытка 2 (page=t/terms 57 КБ + та же CDN): **page {ok:true, http:200, bytes:57247,
  elapsed:666 мс} — фикс окна 12/6 c подтверждён на page-пробе**, но **cdn
  {phase:tls, kind:timeout, elapsed 5147 мс} → fallback/youtube_cdn_probe_failed** —
  при живом direct GET (200/31 Б/0.39 c) TLS к CDN через probe-путь не завершается
  даже в расширенном окне. Повтор по ветвлению израсходован → **BLOCKED_PROBE**:
  active-фаза, видео ≥150 c, дельты медиа, длинный опыт — NOT_RUN. Отказы обеих проб
  сохранены с фазой/кодом/временем/байтами. Off кнопкой — PASS (policy_matched/off,
  probes очищен). Отрицательная проверка инструмента — **PASS**: пара снапов,
  пересекающая Selective-цикл, отклонена с новым полем **`field: applied_config`**.
  Возврат accept: panel byte-identical, off/off, VPN/panel 200, таймер остановлен,
  Proton работает. Слой r3 оставлен (не задействовался в r4 — управление через
  принятый бекенд r3+management).
- CODE: `bec3009f0ed36a0f12add909d42f04472eff9240`; база слоя — r3 `a8b177f`
  (манифест 8/8 new_sha сверены с машиной). Целевые тесты bec3009:
  route_evidence + zapret2 + zapret2_panel — **93 passed**.
- Исходное/финальное: off/off, воркеры inactive, очередь пуста (proc-файл
  отсутствует), acct=0, VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`. Диск
  46 ГБ свободно. Tcpdump отсутствует с перезагрузки владельца.

## §1 Подготовка — PASS

- Манифест r3 8/8 == машина (нет дрейфа). Место 46 ГБ; tcpdump отсутствует.
- Тесты: 93 passed (route_evidence 72+ новых, zapret2, zapret2_panel).
- `snap vpn-before`; воспроизведение через VPN в тестовом Chrome (без прокси, QUIC
  off); контрольный example.com — 200 из браузера; `snap vpn-after`;
  **delta vpn-before→vpn-after ACCEPTED**: seconds 4.12, client_zapret2_rule=false,
  xray +3.06 МБ / +126 КБ uplink — VPN-путь подтверждён байтами. Свежая CDN-пара
  собрана из DevTools и проверена (GET 200).

## §2 Установка и таймер — PASS

- Overlay установщиком изbec3009 (база `6f69cc2…` сверена). Таймер
  `xgw-selective-evidence-1794930580.timer` armed 2026-11-17T15:49:43Z, NEXT 20:19:43
  МСК (1 ч 29 мин). Конфиги после apply — byte-identical.

## §4 Selective и две HTTPS-пробы

- **Попытка 1** (форма: multisplit + 6 доменов r3 + transport + page=watch + CDN,
  saved, count=2): включение → worker поднялся, пробы выполнены → **fallback /
  youtube_page_probe_failed**: `page {ok:false, phase:tls, kind:timeout, http:0,
  elapsed_ms:5122}`, CDN отсутствует («Не запускалась» в UI-сводке). VPN — 200,
  direct-правил нет (0 правил tproxy→xgw-zapret2). Выключено кнопкой
  (policy_matched/off, probes очищен).
- **Попытка 2** (page=t/terms — по ветвлению, CDN та же): `page {ok:true, http:200,
  bytes:57247, elapsed_ms:666}` — **page-проба прошла в расширенном окне**; `cdn
  {ok:false, phase:tls, kind:timeout, http:0, bytes:0, elapsed_ms:5147}` →
  **fallback / youtube_cdn_probe_failed** (стабильно через все 120 c наблюдения).
  VPN жив. Выключено кнопкой. Повтор израсходован → **BLOCKED_PROBE**.
- **Диагностика для Codex**: прямое сравнение — тот же CDN-URL с машины: GET 200,
  31 Б, 0.39 c; через probe-путь (probe-inbound → xgw-zapret2 → очередь → CDN):
  TLS-handshake не завершается даже за 12 c (5147 мс → timeout, phase=tls).
  Раньше (r3, до bec3009) CDN-проба через этот же путь проходила за 274 мс. Различие
  r3→bec3009 в путях пробы: не менялось; вероятный кандидат — состояние очереди/марка
  клиента в момент probe (без свежих SYN-меток zapret2_live замедляет первый пакет
  пути) либо рейт-лимит очереди. Прямое направление: воспроизвести probe CDN при
  незаполненном `zapret2_live` и при живом наборе меток отдельно.
- Отказы сохранены с фазой/кодом/временем/байтами; direct-путь из Chrome для той же
  ссылки работал (200/31 Б/0.39 c) — расхождение устойчивое, не HTTP 4xx.

## §3/§5 Не выполнены — BLOCKED_PROBE

- Активная Selective-фаза, фазовые пары снапов, nft/queue/worker старт-энд,
  `ss dst CDN`, видео ≥150 c, одновременный VPN-контроль, длинный опыт — **NOT_RUN**:
  без active нет ни пути медиа, ни очереди для привязки. MEDIA_PATH — не присваивался
  (нет активной фазы).

## Отрицательная проверка прибора — PASS

- Пара снапов через границу Selective-цикла (vpn-after → post-off) отклонена с
  **`field: applied_config`** (новое диагностическое поле bec3009) — существенное
  изменение applied-конфигурации распознано. Пара vpn-before→vpn-after (без смены)
  — ACCEPTED: `config_bytes_changed=false`, дельты читаемы.

## §6 Возврат — PASS

- Off кнопкой после отказа — policy_matched/off, transport_probes очищен.
- Restore **accept**: config.toml/panel.json byte-identical (OK/OK), xgw active,
  воркеры inactive, очередь отсутствует, panel/VPN 200. restore-completed 16:04:27Z.
- Таймер остановлен после сверки; бэкап сохранён. Слой r3 оставлен на машине
  (манифест 8/8 new_sha подтверждён ранее в §1).
- Финал: off/off, очередь пуста, VPN/panel 200; новый запрос контрольного браузера —
  200.

## Наблюдения для Codex

1. Page-фикс (12/6 c) работает: t/terms 57 КБ прошла за 666 мс; watch (1.4 МБ) всё
   ещё не успевает через probe-путь — для page-пробы рекомендован компактный URL
   либо отдельный учёт тела.
2. CDN-проба: TLS-timeout через probe-путь при живом direct — новая проблема после
   bec3009 (в r3 CDN проходила за 274 мс). Сверить изменения пути пробы и состояние
   `zapret2_live` в момент probe.
3. Прибор: поле `applied_config` в отказах — работает; успешная пара
   `config_bytes_changed=false` — читаема (проверено на vpn-паре).
4. Длинный опыт и подтверждение NFQUEUE-пути переносятся на следующую приёмку после
   устранения CDN-пробы.
- Publication commit: `0f10a6cfe5d9716692deb099c1b62338580290c1` (02d24e4 → 0f10a6c, remote verified byte-identical to local HEAD).
