# Реальная машина: дополнения zapret2, r1 — 2026-11-15

## Происхождение и состояние

- BASE / CODE / delivery TIP: BASE `f1fb5cb1613fa09…` / CODE `c0fc8480d2ded6f5…` / TIP на старте
  `c0fc848`; отчёт публикуется следующим коммитом той же ветки (hotfix-коммитов кода нет).
- Ubuntu 24.04.5 (noble) / kernel 7.0.0-43-generic / nft 1.0.9 / curl 8.5.0 / Chrome 157
  (тестовый, отдельный профиль, QUIC выключен). Bundle: nfqws2 v1.0.7 `038c97e5819df10f…`
  (реальный root-путь `/opt/zapret2/nfqws2`, SHA `4bb2634f…`; `/opt/xgw/zapret2/1.0.7` —
  symlink, отклонён launcher-ом по правилу «без symlink», использован разрешённый реальный
  путь). Lua: zapret-lib/zapret-antidpi SHA в приватном policy-документе (`b81ec5a1…` — SHA256
  всего документа). zapret-auto.lua по-прежнему отсутствует.
- Исходное: zapret2 mode=off, engine=off, dormant strategy hostfakesplit_md5 (сохранён),
  workers inactive, очередь пуста. Конечное (после возврата): идентично исходному.
  PID-эволюция демона: 1200476 → 1292830 (no-op репетиция restore) → 1330850 (сработавший
  штатный rollback-таймер) → 1395941 (финальный restore). Xray main 255025 → 1298489 (apply
  restart в фазе опыта) → перезапущен apply-ом при возврате. Транзитный freepool-pool xray
  появляется/исчезает сам (демон, вне опыта).
- GUI sort acceptance: **выполнено в этом же проходе как шаг 1 ТЗ** — отчёт
  `2026-11-15_gui-sort-indicators.md`, PASS, коммит `5224072`.
- Бюджет: planned 3 ч / 48 media-проб / 2 финалиста / ≤3 GiB; actual ~1 ч 45 мин / 4
  probe-попытки (калибровка прибора) / 1 финалист 16+5 мин / трафик ≈1–1.5 GiB (браузерное
  воспроизведение). Лимиты не достигнуты.
- Команды, серверы, браузер, vision — сама. Доступ root/GUI/desktop имела, запросов не
  требовалось. Владелец ничего не запускал.

## Ключевое открытие окружения: SABR блокирует media-вход прибора

H10/BLOCKED_MEDIA_INPUT, важное для T09/T12:

1. Видимый браузер на прямом пути (тот же выход, подтверждён xray-логом
   `tproxy-in -> direct` с LAN-источника машины) получает современный плеер только в режиме
   **SABR** (`sabr=1` в URL, поле streamingData без url у adaptive-форматов, прогрессирующий
   itag-формат есть, но его классический URL сервером отозван).
2. Plain GET на SABR URL отдаёт 31 байт заглушки (200, application/octet-stream → NOT_MEDIA);
   классический URL (itag 18, video/mp4) — HTTP 403 (пустое тело) на обоих вариантах пиннинга
   (реальный Google-IP и DNS-ответ машины) и с обоими UA (curl/браузерный). Плеер при этом
   продолжает качать медиа — запросы SABR идут POST-протоколом с телом, который GET-прибор
   воспроизвести не может.
3. Прибор `desync.experiment` при этом работает механически корректно: за 4 калибровочных
   попытки отработаны пути HTTP_REFUSED_OR_STALE_URL (403), PROTOCOL_MISMATCH (объявлен h2,
   CDN ответил h1.1), NOT_MEDIA (заглушка) — классификация/сэмплы/ID соответствуют коду.

Следствие: парная timing-матрица C/D (§5), пары Flowseal ALT9/G12 (§6), shortlist-турнир на
реальных пробах (§8) — **NOT_RUN по причине BLOCKED_MEDIA_INPUT**, не сетевой FAIL. Замена
URL с не-YouTube источника не эквивалентна (цель режется именно на googlevideo-пути) и не
делалась. Инструменту нужен SABR-aware клиент (или измерение поверх реального плеера) —
рекомендация в T09 до новой матрицы.

## Условия и измерения

Прямой путь в фазе опыта доказан независимо: правило applied-конфига Xray
«youtube/googlevideo-домены → outboundTag direct (freedom)», журнал Xray
`[tproxy-in -> direct]` для медиа-соединений; ранний bypass — правило
`mark & 0x40000000 → return` стоит перед queue-правилами в `xgw_guard/nfq_output`; очередь
200 ограничена (tcp ct.packets ≤8, udp ≤4, flags bypass). VPN-fallback для тестовых потоков
отсутствовал (единственное правило direct, без fallback-цепочки).

| UTC-окно / попытка | Кандидат / family | client / context | Direct / NFQ доказан | bytes / seconds | verdict | Browser | valid? |
|---|---|---|---|---|---|---|---|
| 16:04 instr-1 | hostfakesplit-md5 | curl / a6652b2d… | да (§3-доказательства) | — | HTTP_REFUSED_OR_STALE_URL | играет | нет (SABR-URL устарел) |
| 16:05 instr-retry | hostfakesplit-md5 | curl / a6652b2d… | да | — | PROTOCOL_MISMATCH (h2≠h1.1) | играет | нет (прибор-калибровка) |
| 16:06 instr-h1 | hostfakesplit-md5 | curl / a6652b2d… | да | 31 / 0.25 | NOT_MEDIA (SABR-заглушка) | играет | нет (прибор-калибровка) |
| 16:07 instr-itag18 | hostfakesplit-md5 | curl / a6652b2d… | да | — | HTTP_REFUSED_OR_STALE_URL | играет | нет (классический URL отозван) |

- Матрица 8 пар C/D × 2 окна: **NOT_RUN** (BLOCKED_MEDIA_INPUT; пар не существует — честно,
  без выдуманных измерений).
- Browser-playback свип (замещающее наблюдение, одно окно 16:26–16:47, прямой путь
  неизменен): A1 pass — страница/innertube проходят, медиа нет; C fake-static-md5 — метод
  исполняется (debug: `fake_1_1: desync` + `multisplit_1_2: desync` на googlevideo
  ClientHello, hostlist positive), медиа нет; D fake-clone-md5 — clone исполняется (debug:
  `tls_client_hello_clone: cloned to desync.xgw_tls_clone`, clone не пропущен, multisplit
  desync), медиа нет; A0 engine off — страница проходит, медиа нет. Ограничение: одно окно,
  n=1 на кандидата, browser-критерий — не timing-измерение.
- Инцидент честно: 30-мин rollback-таймер сработал ровно по расписанию в 16:12:19 во время
  фазы (возврат байт-в-байт, рестарт демона) → фаза после срабатывания INVALID по ТЗ;
  состояние проверено, фаза перевыполнена заново (direct-правила, engine B, preflight),
  таймер перезаряжен. Свидетельства 15:56–16:06 (первое окно) сохранены отдельно.
- shortlist CLI: rc=0, `apply:false`, TTL 86400, воспроизводим между запусками; с 0 PASS
  записей семейства пусты — корректно. Глубокие кейсы (TTL24h/future/повреждённый JSON/доступ)
  на PASS-записях — NOT_RUN (записей нет).

## Покрытие гипотез

| ID | Что реально реализовано/запущено | Результат / сырые агрегаты / ограничение | Вывод / следующий тикет |
|---|---|---|---|
| H01 stream watchdog | Активная probe отработала (4 попытки); Lua-detector отсутствует | Verdict-пути прибора отработаны; late-stall не измерен | T05/T07 |
| H02 composite key | context_id/prefix_context_id присутствуют в каждой записи журнала | Один IP в опыте → prefix-пользу измерить нельзя | T07/T08 |
| H03 persistence | shortlist CLI: rc=0, apply:false, TTL 86400, reproducible | Runtime-состояния automate_host_record нет | T07/T08 |
| H04 autottl cache | NOT_IMPLEMENTED | — | T05/T07 |
| H05 clone | C/D собраны launcher-ом (preflight 0), debug-доказательство исполнения обоих (fake+multisplit; clone в blob xgw_tls_clone) | KeyShare не портится (по конструкции); эффект на линии: пар нет → NOT_ESTABLISHED, не FAIL | T06/T07 |
| H06 IPC | NOT_IMPLEMENTED | — | T03/T08 |
| H07 shared memory | NOT_IMPLEMENTED | — | T03/T05/T08 |
| H08 route fallback events | NOT_IMPLEMENTED | — | T03/T04/T08 |
| H09 tournament | NOT_IMPLEMENTED (blockcheck2 нет); shortlist не турнир | — | T09 |
| H10 stream/client probes | Прибор работает, но media-вход заблокирован SABR (см. выше); браузер — рабочее свидетельство; curl-impersonate не установлен | 4 калибровки, 0 валидных проб; PLAYBACK-канал дал единственное положительное свидетельство | T09/T12 (переработать прибор) |
| H11 QUIC CRYPTO | NOT_IMPLEMENTED | — | T06/T09 |
| H12 obfs | NOT_IMPLEMENTED / внешний узел недоступен | — | T04/T06 |

## Flowseal / упаковка

- Generator reproducible: make_flowseal из pinned `2401b7a`-источника воспроизвёл
  byte-identical `flowseal_lab.py` и `flowseal-translation.json` (cmp ✓, §1).
- 22 конфигурации × 2 scope: parse + intercept=0 — **44/44 OK** (DATA: root 755, файлы 644,
  blobs в конвенции `fl_*`, пустые user-списки созданы и зафиксированы как входы).
- Scope static (22/22): в scope=youtube исходные положительные hostlist/ipset-формы удалены,
  excludes сохранены, `--hostlist-domains=` с точным набором YouTube присутствует; двойных
  hostlist нет. L7 static: блоки HTTP помечены `filter-l7=http` (15 конфигов × 2 блока), TLS —
  `filter-l7=tls` (21 конфиг × 3; ALT5 — без fake-блоков по исходнику).
- Live-подтверждение выбранного блока на новых соединениях: NOT_RUN (потребовало бы второй
  очереди/подмены воркера поверх активного B; приоритет отдан debug C/D и видео по ТЗ).
- Старый vs новый launcher, пары ALT9 и general/SIMPLE FAKE: NOT_RUN (BLOCKED_MEDIA_INPUT).
- S09/syndata: NOT_RUN_DEPENDENCY (нет pre-SYN допуска T05); очередь не расширялась.
- Уровни разделены честно: dry-run — NOT_RUN в этом проходе; intercept=0 — 44/44; реальный
  packet handler — только штатные кандидат-профили C/D/B (debug-доказательства выше).

## Видео

- Финалист один: **hostfakesplit-md5** (штатный профиль, candidate B) — единственный,
  воспроизводивший YouTube в обоих окнах (15:58–16:06 и 16:48–17:14).
- Публичный ролик: YouTube ID `8plwv25NYRo` («10 Hours of Rain Sound…», 10 ч). Отдельный
  видимый профиль Chrome, QUIC off, без расширений, без no-sandbox/игнорирования
  сертификатов. Свежая навигация на каждого кандидата (about:blank → watch), play —
  пользовательский клик (CDP Input).
- 15 мин непрерывно (16:51–17:07): t=60 c/мин ровно (619→1520), paused=false, readyState=4 в
  каждом минутном сэмпле, качество авто 480p без единого зависания.
- Seek вперёд +6 мин: продолжилось из буфера <8 c; после ручной установки 720p — фактическая
  **720p**, ещё 5 мин (2073→2313, 60 c/мин, readyState=4). Vision-кадры: реальное видео
  (лес/дождь), не чёрный экран; звука в сэмплах не было (не проверялось).
- Кандидаты A1/C/D/A0 в том же окне: страница и innertube-ответы проходили, медиа не
  стартовало (t=0) — значит страница/HTTP ≠ медиа-путь; HTTP=PASS / STREAM=FAIL / PLAYBACK=FAIL
  как паттерн подтверждён для них, для B — STREAM=PASS/PLAYBACK=PASS.
- Пауза 60 с / заполненный буфер (контроли будущего watchdog): NOT_RUN — время окна ушло на
  SABR-диагностику; поздний stall не наблюдался ни разу.
- Второй финалист: не выбран — валидных probe-побед нет, C/D в окне не проиграли.

## Итог и возврат

- Измеримый эффект на этой линии в этом проходе: только штатный hostfakesplit-md5 дал
  PLAYBACK (SUPPORTED_ON_THIS_LINK, 720p, 16+5 мин); fake-static-md5 и fake-clone-md5
  корректно исполняются (debug-доказательства) и в этом окне воспроизведение не восстановили
  (одно окно, n=1 — не «NO_BENEFIT» на все условия); pass и off — медиа-fail (обход
  необходим). Процент/пары не считаются — валидных пар нет (INCONCLUSIVE для C vs D по
  числам; честно).
- Главное окружение-ограничение: SABR. T09/T12 probe требует SABR-aware клиента до новой
  timing-матрицы; H05-пары и Flowseal-пары блокированы тем же входом.
- Возврат: config.toml/panel.json byte-identical (`89bf2a67…`/`33916cb5…`, cmp с R-копиями),
  acct=0, offload TSO/GSO/GRO on как до опыта, workers off, очередь пуста, YouTube
  direct-правила убраны штатным apply, selected/engine off, dormant strategy сохранён.
- Только свои объекты удалены: 2 LAB-каталога в /opt/xgw/lib, DATA в /run; своих nft-правил
  не создавалось (кроме штатного apply), flush не делался; чужие процессы/службы не тронуты
  (браузеры владельца/ZCode работают).
- Rollback timer/service остановлены после успешного возврата; R-каталог и приватный D
  сохранены для разбора (netlog'и 46+34 МБ — приватно).
- GUI/API/HTTPS после возврата: panel 200, HTTPS 302, карточка zapret2 off/fresh/
  policy_matched/schema=1, main и pin не менялись, окно владельца GUI открыто (тот же PID).
- Хотфиксов кода нет; ничего нового на машине не осталось установленным (backend/GUI — как
  после gui-sort шага: sidebar `661aedfa…`).
- Следующий основной этап **T03** (единый контроллер queue/generation) с учётом: (1) probe
  должен научиться SABR до новой timing-матрицы; (2) hostfakesplit-md5 — референс линии;
  (3) debug-канал nfqws2 (hostlist/profile/lua per-connection) достаточно подробен для H01
  наблюдений без нового IPC.
- Publication commit: добавить после push.
