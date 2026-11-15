# Ubuntu 24.04 — замер YouTube в обычном Chrome, Compare и vpn_control — 2026-11-16

- RESULT: **PASS** — открытое задание T04 закрыто: калибровка VPN и основной замер 15+5 мин
  выполнены в обычном Chrome по обновлённому ТЗ телеметрии (хелпер-сводка,eligible-секунды,
  метки фаз), Compare дал **4/4 строки `zapret2.probes` ok** (`compared/comparison_done`),
  Selective-прерывание дало свежий `fallback/probe_failed` со снятием маршрута и закрытием
  gate. Итоговое состояние машины: off/off, byte-identical конфиги, VPN-выход жив, T04-слой
  (12/12 манифеста с хотфиксом) оставлен.
- BASE разработки: `1e27384` (T04-отчёт); CODE документа: `fd969a1`; установленная база —
  без изменений (T04-слой `ad81542`, манифест 12/12, applier.py хотфикс `ecac82aa…`
  = `1e27384` сверен перед фазой).
- Ubuntu 24.04.5 / kernel 7.0.0-43 / nfqws2 v1.0.7; Chrome 157 (обычный, тестовый профиль,
  --no-proxy-server --disable-quic, NetLog на каждый trial).
- Установка в этом проходе не требовалась (T04 уже на машине; сверено по манифесту и хотфиксу
  до начала). Предохранитель: отдельный RESTORE_DIR с panel.before и проверенным
  restore-скриптом (режим accept), таймер 40 м; сработал штатно по расписанию в конце —
  восстановил panel; мой поздний экспериментальный set_desync перекрыт финальным restore
  accept (итог: byte-identical, сверкано).
- Бюджет: один проход ~1 ч; два независимых браузерных замера (180 c + 25 мин) + compare + два
  selective-цикла.

## A. Калибровка VPN (off/off, обычный Chrome)

- Trial `calibration-vpn`, свежий профиль, DevTools-эквивалент Snippet: инжекция
  `youtube_telemetry.js` + capture-стаба через CDP (исполнитель = оператор), метки
  play/pause-10s/before-seek/after-resume.
- Первый опыт отзабракован сам (мой клик поставил паузу на уже игравший автозапуск ролик —
  60 c окна ушли в паузу); повторен с проверкой `paused=false` до метки play.
- Хелпер-сводка: samples=97, **eligible_seconds=84.0** (≥60 ✓), initial-фаза **63.6 с** ✓,
  estimated_stall 0.0, play→playing 0.025 c, буфер median 55 c, 720p 89% времени (9 c —
  стартовая адаптация 480p), dropped_ratio 0.37 (кадры браузера), route UNKNOWN (по дизайну
  калибровки).
- Свежий медиазапрос: netlog trial — 86 videoplayback, все `sabr=1` (классического GET нет —
  ожидаемо).
- Пауза 10 c исключена из времени просмотра (сводка initial не содержит её секунд), скачок
  позиции — после метки before-seek.

## B. Standalone 15+5 на установленном T04

- Верификация: off/off, workers inactive, очередь пуста, хотфикс applier сверен с `1e27384`,
  манифест 12/12; RESTORE_DIR свежий (panel.before + restore.sh accept + network-test-started),
  таймер 40 м.
- `set_standalone` → gate active немедленно (worker PID 1814427, очередь 200 peer=PID,
  generation 1).
- Trial `standalone-hostfakesplit-md5-r1`: play-метка unix 1794774760.7; 720p вручную —
  фактическая 720p.
- 15 мин (внешний сэмплер + capture-ряды): 23:33:44→23:48:47, t=47→804→855, каждый сэмпл
  60 c/мин, readyState=4, пауз нет.
- Seek +6 мин (метки before-seek/after-resume) → продолжение из буфера; 5 мин: 1535→1895,
  60 c/мин, 720p.
- **Capture-сводка хелпером**: rows=1504, **playing rows=1504/1504** (0 пауз в ряду),
  eligible_seconds=**1489**, target_height_ratio=**0.997**, buffer median 80 c,
  estimated_stall_seconds=56.7 в 44 коротких событиях (3.8% — отметка честно), initial-фаза
  eligible 1058 c.
- Маршрут/объём: дельта `xgw-zapret2.downlink` за фазу = **241 МБ** (15.33→256.63 МБ),
  очередь 200 — 212 164 copy-пакетов; звук: muted=false, volume=1, аудио декодируется.

## C1. Compare (off/off → compare → off)

- Предпроверка через VPN: `ru.wikipedia.org/wiki/Россия` 200 / 3,270,734 байт;
  `www.wikipedia.org/` 200 / 122,506 байт (оба ≥16 KiB, без редиректов и авторизации).
- Политика: mode=compare, strategy=multisplit, domains=оба домена, probe_urls=оба URL,
  engine=off, queue 201. Воркер xgw-zapret2 active (generation 2).
- **`zapret2.probes`: 4/4 строки ok** — probe 1 vpn/zapret2 (200, 65,536 B каждый),
  probe 2 vpn (200, 78,951 B) / zapret2 (200, 65,536 B); phase=body, redirects=0.
  Итог состояния: **`compared` / `comparison_done`**.
- Клиентский поток в ходе раунда: оба домена отвечали (VPN-выход, как задан compare-режимом).
- Выход из compare: gate закрыт на t+3 c, очередь пуста, клиентский поток 3.27 МБ через
  VPN-конфиг (proxy-outbound на месте), reservation None.

## C2. Selective и raw vpn_control

- Попытка на заблокированном домене (youtube + probe_url страницы): устойчивое
  `fallback / waiting_for_probe_urls` — прямой забор самой probe-страницы невозможен, прибор
  не инициализируется, worker не стартует. Зафиксировано как точное условие.
- Вторая попытка на необструкированном endpoint (ru.wikipedia.org, оба пути живы — compare
  доказал 4/4 ok): state-машина observed — blocked → off → preparing/probe_inbound →
  **preparing/nfqueue (worker active, окно ~10–15 c)** → fallback.
- Прерывание: SIGKILL не успел примениться — контроллер сам завершил окно до команды
  (юнит not loaded); зафиксировано **свежее состояние после прерывания worker:**
  `state=fallback, reason=probe_failed`, валид_until=null.
- Условия закрытия проверены по списку ТЗ: клиентское правило wikipedia снято (остался только
  probe-канал), воркер inactive, очередь отвязана, gate fail-closed, VPN-участники живы
  (443), probe_port=19999/check_seconds=180 — бюджет и отмена присутствуют, учётные данные
  пробы не выводились.
- **`zapret2.vpn_control` = `not_run`** (raw): причина — цикл завершился `probe_failed` до
  этапа, на котором формируется vpn_control-сравнение; новый клиентский запрос получил полное
  тело (3,270,734) через VPN-маршрут. Повторно воспроизводимо: то же значение в обоих циклах.

## Итог и возврат

- Замер в обычном Chrome: калибровка 84 с eligible + standalone 1489 c eligible (0 пауз,
  99.7% 720p, 44 коротких буфер-события) — ряды и сводки хелпера сохранены на стенде
  (player.json/summary.json/network/netlog приватно).
- Compare: механика и 4/4 probe-строки подтверждены; cleanup корректен.
- vpn_control: остаётся `not_run` с точным условием (probe_failed до измерения; на
  необструкированном endpoint у bypass нет пользы — fallback по дизайну).
- Возврат: panel byte-identical (`33916cb5…`), off/off, workers inactive, очередь пуста,
  acct=0, offload on, VPN-выход жив, API 200, окно владельца открыто. Таймер остановлен после
  штатного срабатывания. T04-слой оставлен (12/12).
- Publication commit: добавить после push.
