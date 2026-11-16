# Ubuntu 24.04 — T07/H01: shadow-watchdog остановок и pin zapret-auto — 2026-11-16

- RESULT: **PASS** — закреплённый `zapret-auto.lua` сверен с UPSTREAM по SHA и загружается
  штатным бинарником (smoke `XGW_T07_LUA_OK`: `--dry-run` + `--intercept=0` с assert-ами
  API `circular`/`automate_host_record`/`inseq==4096`). Пробел H05 по `reassembled` закрыт
  изолированными прогонами: обычный MTU — **`reassembled=0`** (полный ClientHello в одном
  пакете), MTU 400 — **`reassembled=1`** (TCP reassembly), fake с MD5 доставлены в обоих
  режимах. Shadow-watchdog на четырёх живых записях обычного Chrome: **ложных срабатываний
  ноль** (VPN-контроль, S1, S2 20 мин — `signals=[]`), **все три порога 15/30/60 с —
  истинные срабатывания (TP 3/3, FP 0, FN 0)** на контролируемом истощении буфера
  (Offline-эмуляция: истинная остановка подтверждена позицией/readyState и vision-кадром,
  ожидание 72 c > 70 c порога, восстановление ~40–50 c после network_on).
  Слой не устанавливался (T07 — инструмент анализа и pin апстрима); политика off/off
  восстановлена byte-identical.
- CODE: `beaa2ac4bdeb4aba495cde128bddfc6a7f4022b3`; BASE `fbfe9a1` (мой отчёт H05 — предок).
  pytest `--portable` (shadow, youtube_telemetry, experiment): **76 passed, 1.81s**.
- Исходное: off/off, PID демона 2054084→(рестарты моих фаз не затрагивали основной процесс —
  panel вернулась штатным restore), очередь пуста, acct=0, offload on/on/on, VPN 200.

## 1. Прежний захват

- PID 1935908 жив (14 ч), команда/файл совпадают с прежним опытом. **User namespaces
  идентичны**: `/proc/1/ns/user`, `/proc/self/ns/user`, `/proc/1935908/ns/user` — все
  `user:[4026531837]`; гипотеза о другом userns-контексте исключена, «нового доступа» не
  появилось. Повторный TERM от root → **EPERM**; рост файла замедлился до ~23 КБ/с
  (114 КБ за 5 c; ранее ~1 МБ/с — зависит от трафика 443). Диск: ~30 ГБ свободно.
  **Требуется помощь администратора хоста** (загрузка/консоль с иными полномочиями) —
  сигнал передан в отчёте; новый WAN-захват не запускался.

## 2. Закреплённый Lua и пробел H05

- SHA-256: `zapret-auto.lua` в UPSTREAM.json — OK; установленные `zapret-lib.lua`/
  `zapret-antidpi.lua` — OK по тому же манифесту; бинарник — `v1.0.7 (038c97e5…)`.
- Smoke: временная копия в `/run` (root 0700→**точечное исправление окружения: chmod 0755**,
  mktemp создаёт 0700 и nfqws2 после сброса привилегий её не читал) → `--dry-run`
  «command line parameters verified», `--intercept=0` исполнил все три Lua →
  **`XGW_T07_LUA_OK`**. Остатков stage нет. Запуск `circular` на потоке и ротация профилей —
  следующие этапы (по ТЗ).
- **Лаборатории**: `h05` — `reassembled=0` у static и clone (полный CH), тела byte-exact;
  `h05-small-mtu` (MTU 400) — **`reassembled=1`** у обоих (reassembly); MD5-fake на
  серверном интерфейсе в обоих режимах (normal: 1 MD5-сегмент, MTU 400: 2–3 сегмента —
  сегментированная отправка). Двухпутевое разделение получилось — полное покрытие.
  Акct и namespace возвращены автоматически (0 / пусто).

## 3. Shadow-watchdog на обычном Chrome

Методика: `youtube_telemetry.js` + capture-стаб через CDP, метки `__xgwCapture.mark`,
обработка `python3 -m xgw.desync.shadow player.json --video 8plwv25NYRo`
(`media_network=unavailable` ожидаемо — без CDP Network-данных; `cause=unknown` по дизайну).
Формат `samples.jsonl` CDP-коллектора на стенде отсутствует — NOT_RUN.

| Запись | Путь | Фазы | signals | TP/FP/FN (15/30/60) |
|---|---|---|---|---|
| vpnctl (289 сэмплов) | VPN | advancing 208.0 c, buffered 3.0, **paused 71.0**, seeking 5.9 | **[]** | 0 / **0** / 0 |
| истощение (244) | VPN (Offline) | advancing 125.9, **starved 115.0** | **15+30+60 c** | **3 / 0 / 0** |
| S1 (133) | standalone hostfakesplit_md5 | advancing 128.3, buffered 3.1 | **[]** | 0 / **0** / 0 |
| S2 15+5 (1204) | standalone fake_clone_md5 | advancing 1194.1, buffered 7.8, transition 1.0 | **[]** | 0 / **0** / 0 |

- **VPN-контроль**: ≥1 мин стабильного просмотра (720p, буфер до 81), пауза ≥65 c
  (метки pause-for-buffer/buffer-full/resume; watchdog паузу не счёл — интервал закрыт),
  resume, перемотка +6 мин (буфер 23→76 через сеть). Конец 10-часового ролика не
  наблюдаем — состояние `ended` осталось непроверенным (честно). Смена CDN: в окне не
  фиксировалась отдельно (один источник googlevideo) — сценарий оставлен открытым.
- **Истощение**: отдельная вкладка; `network_off` (CDP Offline) → буфер 22→0,
  **истинная остановка на t=127** (позиция замерла, readyState 2) → `visible_wait` +
  vision-кадр (замерший кадр леса, диалогов ошибок нет) → ожидание **72 c (> 70 c)** →
  `network_on` → восстановление за ~40–50 c (буфер 78, воспроизведение продолжилось).
  Фатальной ошибки плеера не было — проверены все три порога. Задержка сигналов от начала
  голодания: 15/31/61 c (start 112.0 → observed 127/143/173) — ровно пороги. TP 3/3,
  FP 0, FN 0. Повтор с ограничением скорости вместо Offline — не проводился (окно отдало
  standalone-фазе; механика starvation эквивалентна).
- **Standalone**: panel.before + таймер 45 м (перезарядка перед 15+5), мосты inactive
  подтверждены в обеих фазах; очередь 201 peer=MainPID, netlink Eth=12 owner ✓.
  - S1 `hostfakesplit_md5` ≥2 мин: 130 c, 720p, `signals=[]`, +9312 пакетов очереди.
  - S2 `fake_clone_md5` 15+5: 1204 сэмпла, **`signals=[]`** (advancing 1194 c — медиа-время
    = стене, остановок нет), seek +6 мин, **+409.1 МБ** через `xgw-zapret2` (43.8→452.9 МБ),
    очередь 193 336 пакетов, drops 0/0. Свежий SABR: медиапоток обслуживался через
    bypass-очередь (worker PID, generation 2).
  - Честная оговорка S2: после ~530 c ABR снизил качество до 480p **при здоровом буфере
    (63–84 c)** и не вернул 720p до конца (включая пост-seek). В 200-с прогонах H05 clone
    держал 720p; static в 20-минутном прогоне H05 — тоже. Один прогон: признак не
    приписывается стратегии достоверно, отмечено для следующих измерений.
- Поздний TCP RST и контексты кэша H02/H03 — следующий этап (по ТЗ).

## 4. Возврат

- Штатный restore таймера: panel восстановлен byte-identical (`89bf2a67…`/`33916cb5…` OK),
  apply с перезапуском Xray (burstObservatory/dns/inbounds/outbounds), мосты вернулись →
  **off/off**, воркеры inactive, очередь пуста, acct=0, offload on/on/on, VPN 200, panel 200,
  окно владельца открыто (PID 1243747). Таймер остановлен после подтверждения.
- Установленный слой не менялся (T04+vpn-control+synack+replies+preflight+h05 остаются);
  временная политика standalone применялась и снята штатно.
- Приватное на стенде: записи vpnctl/deplete/S1/S2 (player json, скриншот истощения),
  лабораторные каталоги, panel.before в `/var/lib/xgw/handoff/t07-shadow-standby`. В отчёте
  — агрегаты и коды, без URL/IP/полных логов.
- Publication commit: добавить после push.
