# Ubuntu 24.04 — единая приёмка GUI и T12 (f4c9945) — 2026-11-18

- RESULT: **GUI PASS (установлен и оставлен; один воспроизводимый дефект клика
  «Мбит/с» зафиксирован), EXPIRY PASS (фикстура и очистка), START/RETRY — обе
  попытки fallback (RETRY_LIVE=FAILED), TLS_PAIR — решающее парное доказательство:
  TLS до CDN не завершается и на прямом WAN-пути (bypass-метка, TCP connected
  66 мс, ClientHello подтверждён acked=178, ответные байты 0) — дефект прямого
  канала к googlevideo, а не пути zapret2; VIDEO/MEDIA_PATH NOT_RUN (active не
  достигнут); VPN_RETURN/RESTORE PASS**. Установка backend 5/5 файлов с
  `--selective-expiry`, таймер 100 мин, конфиги byte-identical, restore accept
  (restore-completed, check_installed 5/5 — слой `f4c9945` оставлен).
- CODE: `f4c994546bab083032ffda87a06ff8c0f28241d0`; Ubuntu 24.04.5 LTS;
  Qt 6.4.2 / PyQt6 6.6.1 / Python 3.12.3 (pytest 7.4.4). §1: **135 passed**
  (8 наборов zapret2/probe_watch/route_evidence/telemetry) + node/bash OK.
  GUI-фикстура на копии действующего релиза: **10 passed** + pulses -k **1 passed**
  (холодный флап прошлого раунда в этом прогоне не воспроизвёлся).

## GUI (§2) — PASS с одним дефектом

| Проверка | Результат | Наблюдение |
| --- | --- | --- |
| gui_install check→apply→check (--catalog-refresh) | PASS | `READY changed files: 3` → `INSTALLED` → `READY changed files: 0` |
| Индикаторы: Рейтинг ×2 | PASS | стрелка ▼/▲ у колонки «Рейтинг», порядок меняется, пропуски внизу |
| Индикаторы: Мбит/с после Рейтинга | PASS | «▼ Мбит/с», порядок по скорости по убыванию (56-серверная подписка) |
| Индикаторы: Серверы→Мбит/с | **FAIL (дефект)** | при активной «Серверы» клик «Мбит/с» не активирует колонку — индикатор остаётся «▼ Серверы», порядок по имени; воспроизведено дважды (пул и подписка) |
| Вкладка «Допущенные» (пул) | PASS | «Серверы (32)» — допущенные строки пула видны; наблюдение обновилось (проверено 278, пригодно 36) |
| Вкладка «Выбранные» | PASS | (0), «По выбранному фильтру серверов нет» — закреплений нет |
| 720×660 / минимальное | PASS | компактный режим с ☰; минимум 566×609 |
| Пульс (2 кадра, 1 с) | PASS | кольцо пульсирует у страны активного VPN |
| zapret2-бейдж vs веб-панель | PASS | «Выключен» == off |
| Тема | PASS | тёмная (исходная) не менялась; переключения в этом проходе не требовались |
| PID и хэши | PASS | services.before == after byte-identical; config.toml+panel.json OK |

## EXPIRY (§3) — PASS

| Проверка | Результат | Наблюдение |
| --- | --- | --- |
| Фикстура expire=1 сохраняется в off | PASS | «Настройки сохранены», ревизия сменилась |
| `expires_at=1` в API | PASS | `probe_expiry: [{probe: 2, expires_at: 1}]` |
| Причина в blockers.selective | PASS | «Истёк срок адреса CDN. Сохраните свежий адрес видео.» |
| Кнопка Selective недоступна | PASS | disabled=true; воркеры inactive |
| GET без полного URL и sig | PASS | строки «xgw-expired-fixture» и «videoplayback» в overview отсутствуют |
| Очистка в off | PASS | saved, transport=true, probe_count=0, probe_expiry пустое, повторное открытие формы подтверждает; блокер сменён на подсказку об адресах |
| LIVE_EXPIRY | NOT_RUN | свежий URL имел запас 359 мин; автоматическое снятие правила покрыто тестами §1 (Controller) |

## START / RECHECK / RETRY (§4) — fallback ×2, RETRY_LIVE=FAILED

| Попытка | Клик (UTC) | Ревизия | page | cdn | Итог |
| --- | --- | --- | --- | --- | --- |
| a (rr5, D=173.194.x.x) | 18:32:15Z | из kit `77f1c2bd` | ok 520 мс | TLS-таймаут 20 310 мс (первый+повтор) | fallback / youtube_cdn_probe_failed |
| b (rr1, B=87.245.x.x) | 18:38:08Z | из kit `d9ba266a` | **TLS-таймаут 10 129 мс** | не начиналась | fallback / youtube_page_probe_failed |

- Попытка b выполнена по ветвлению (off кнопкой → свежий URL от плеера, hostname и
  IPv4 сверены: другой endpoint, другой IP).
- kit: multisplit, 6 доменов, check 180, retry 120, бюджет 256 — сохранён перед
  стартом; плеер закрыт перед служебной пробой.

## TLS_PAIR (§4) — решающее наблюдение

- *a-wan.json (до включения, bypass-метка, проверка сертификата к hostname): TCP
  connected 66 мс, source_matches_lookup=true, маршруты bypass и Selective
  идентичны (enp3s0f0 → 192.168.50.1, prefsrc совпадает).
- *a-tls.json (--during-selective 90, тот же hostname/IP): **TCP connected 68 мс,
  но TLS = timeout** (tls_started …786.5 → tls_finished …796.7 ≈ 10.2 c). Триггер —
  сокет CDN ESTAB: bytes_sent=857, **bytes_acked=178**, bytes_retrans=340,
  bytes_received=0, data_segs_in=0.
- *a-start.jsonl (окно CDN-пробы попытки a): два сокета к тому же IP — ESTAB,
  sent 2897/2557, **acked=178 (оба)**, recv=0, segs_in=0, retrans 7/6; gate открыт
  в начале окна, outgoing 0→68, дропов нет. Совпадение hostname/IP и пересечение
  окна подтверждены (tcp_started …786.45 внутри probe-окна …785.9–…807.3).
- Попытка b: page-сокет (страница) — ESTAB/LAST-ACK, acked=161, **recv=1**,
  retrans=6 — страница тоже не получила ответа; b-tls корректно не сработал
  (CDN-проба не начиналась — не_observed).
- **Вывод**: TLS до googlevideo-CDN не завершается на обоих прямых путях (bypass и
  probe-путь zapret2) при одинаковом маршруте и работающем TCP; работает только
  VPN-путь (контрольный ресурс через VPN — 200 весь проход). «TLS прошёл только по
  WAN» — НЕ подтверждено; подтверждено противоположное: различие «VPN vs любой
  прямой путь», а не «probe vs bypass». Прямой канал к googlevideo по TLS деградирует
  (ClientHello подтверждается, ответы не возвращаются) — причина вне zapret2.
- Прошлые различия раундов объясняются этим: «рабочие» пробы шли на endpoint'ах,
  где прямой TLS в тот момент проходил; флап — состояние прямого канала провайдера.

## PLAYBACK / MEDIA_PATH (§5) — NOT_RUN

- Active не достигнут ни в одной попытке → VIDEO=NOT_RUN, MEDIA_PATH=NOT_RUN
  (причина: fallback после TLS-таймаута на прямом пути; критерии CONFIRMED
  недостижимы без active).

## VPN_RETURN / RESTORE (§6) — PASS

- Off кнопкой → off/off, воркеры inactive; **новый сеанс YouTube через VPN — дельта
  ACCEPTED client_rule=false, xray +1.68 МБ downlink / +231 КиБ uplink за 46.5 c**
  (снята на осевшей карточке; первая пара — pending-переход, честно переснята).
- restore.sh accept: конфиги OK/OK, `restore-completed` присутствует,
  check_installed **5/5** — слой `f4c9945` оставлен; таймер
  xgw-selective-expiry-rollback остановлен (запас ~35 мин до срабатывания).
- Финал: off/off, воркеры inactive, VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`,
  диск 43 ГБ; тестовый Chrome закрыт; JSONL/IP/URL — в приватном каталоге опыта
  (0700), захват пакетов не вёлся.

## Наблюдения для Codex

1. **Диагноз CDN-проб закрыт парным измерением**: прямые пути (bypass и probe) не
   получают TLS-ответов от googlevideo (ClientHello подтверждается, данные — нет),
   VPN-путь работает. Автоповтор и смена endpoint'а не помогут, пока прямой канал
   режет TLS; рабочий сценарий Selective на этой линии — только через рабочие на
   прямом TLS endpoint'ы (как в WAN-раунде, где проба прошла за 193 мс), что
   недетерминировано. Рекомендация: при youtube_cdn_probe_failed сразу предлагать
   свежий адрес от плеера и/или показывать в форме статус прямого TLS к CDN.
2. **Дефект GUI «Серверы→Мбит/с»**: клик по «Мбит/с» при активной сортировке
   «Серверы» не активирует колонку (индикатор и порядок остаются на «Серверы»,
   направление реверсируется); после клика «Рейтинг» колонка «Мбит/с» активируется
   нормально. Фикстура этот сценарий не покрывает (10 passed).
3. EXPIRY-механика (expires_at=1, блокер, недоступная кнопка, очистка) работает
   штатно на форме и в API; утечки подписанных URL в GET нет.
4. Пары media-pairs готовы к сбору при первом же active — механика проверена в
   media-раунде; в этом проходе не потребовалась.
- Publication commit: `добавляется после push` (worktree report от FETCH_HEAD поверх 80d0260).
