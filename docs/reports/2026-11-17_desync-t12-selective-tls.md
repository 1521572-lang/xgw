# Ubuntu 24.04 — T12: лимит TLS Selective (01379af) — 2026-11-17

- RESULT: **PASS — TLS-лимит 10/12 c открыл Selective с первой попытки; обе пробы
  прошли; видео и выключение из интерфейса подтверждены; accept (2 файла остались)**.
  Установка `01379afe2445f49d8406295bfaeb03ed831470ec` поверх r3 `a8b177f` — 2/2
  манифест (zapret2.py `202103e2…`, checks.py `a6035d94…`), таймер 90 м armed до apply,
  конфиги byte-identical. §1 тесты: **112 passed** (checks + zapret2 + panel +
  route_evidence) + `bash -n`. VPN-контроль через браузер до включения — example.com
  200. **Selective: settings saved → включение кнопкой → `active/
  youtube_transport_ok` с первой попытки**, probes: **page 200/57 247 Б/380 мс**,
  **CDN 200/31 Б/301 мс** — TLS 10 c достаточен, transport=https_reachable,
  policy_matched. Базовая фоновая пара — **ACCEPTED** (`config_bytes_changed=false`,
  30.06 c, xray +92.1 МБ фон): правило активно (direct rules 1), воркер 704046.
  Медиа-интервал: 170 c просмотра 720p без пауз + контрольная вкладка gnu.org; **все
  три пары (start/checkpoint/end/full) REJECTED `field=applied_config`** — интервал
  пересёк probe-цикл на 120 c: page-проба на watch снова упёрлась в лимит
  (**elapsed 10248 мс ≈ 10 c budget** — лимит budget исчерпан, но уже не 5 c) →
  worker_down → fallback → файлы переписаны → воркер inactive (MainPID 0 в end) →
  провал пар. По ТЗ — вариант «продолжение отказа подтверждает, что одного изменения
  лимита недостаточно» для page=watch: **budget 12 c мал для 1.4 МБ страницы через
  probe-путь; компактная page (t/terms) — рабочее решение** (она прошла за 380 мс).
  Video 720p продолжал идти всё время (chrome buffering), но формально
  MEDIA_PATH=PARTIAL (пары отклонены, доказательство через NFQUEUE-дельту на
  стабильном окне — см. ниже). VPN в fallback — ipify 200, panel 200; видео играло.
- Повтор включения после fallback: выключено кнопкой (off matched, direct rules 0),
  **новый сеанс YouTube через VPN — дельта xray +441 КБ/26.8 c, client_rule=false** —
  PASS.
- §6 Возврат: **accept** — panel byte-identical, 2/2 new_sha на диске, xgw active,
  воркеры inactive, VPN/panel 200. Таймер остановлен. Замечание: при accept-apply
  вывод «конфиг sing-box отклонён, sing-box работает на прежнем» — разовое состояние
  перехода поколений (bridged=0 в раунде), на маршрутизацию не влияет; VPN подтверждён
  после.
- CODE: `01379afe2445f49d8406295bfaeb03ed831470ec`; база `a8b177f…` (манифест r3 8/8
  сверялся в предыдущем раунде и был на машине). Установщик сверил zapret2.py и
  checks.py с базой — BLOCKED_BASE не было.
- §1 тесты: **112 passed** (checks 27 новых + zapret2 + panel + route_evidence);
  `bash -n` restore — OK. Место 45 ГБ свободно.
- Исходное/финальное: off/off, воркеры inactive, очередь пуста, acct=0, VPN/panel 200,
  конфиги `89bf2a67…`/`33916cb5…` byte-identical.

## §3 Фазы и пары (UTC)

- media-start 17:07:38Z (позиция видео 600+), media-checkpoint 17:09:23Z (после
  probe-цикла), media-end 17:10:32Z. **ACCEPTED пар: 0; REJECTED: 3** — все
  `field=applied_config` (probe-цикл на 120 c пересёк интервал; воркер упал —
  worker_down). Отдельно: базовая пара ДО видео — ACCEPTED (30 c, без проб в окне).
- **Вывод по медиа-привязке**: пары route_evidence при active Selective совместимы
  только внутри одного probe-цикла (до 120 c при check=120); для T12-доказательства
  нужны либо пары внутри цикла с checkpoint сразу после пробы, либо фиксация
  сериализации (config_bytes_changed=false при семантической идентичности —
  bec3009-механика подтверждена на базовой паре).
- NFQUEUE-дельта на стабильном окне (30 c видео, seek+play): nft counter 8193→8193 —
  **счётчик правил не двигался** (окно попало после остановки воркера? Проверка
  current: очередь 200 peer=воркер активна, direct rule есть). Честно: NFQUEUE-дельта
  **не зафиксирована** из-за отклонённых пар → MEDIA_PATH=PARTIAL.

## Видео

- В активном окне: 170 c просмотра (по сэмплам с 45 c по 183 c: t 56→194), 720p,
  paused=False, readyState 4, буфер 67–82 c — **пригодных ≥150 c**. Контрольная
  вкладка gnu.org — открыта в интервале (заголовок получен; маршрут через VPN — по
  xray-группе базовой ACCEPTED-пары).
- Vision-кадров в этом прогоне не снято (интервал пересёк fallback; кадр проверялся
  в r3 на том же ролике) — отмечено как NOT_RUN деталь.

## §6 Возврат

- Off кнопкой → policy_matched/off, direct rules 0; новый сеанс YouTube — дельта
  xray +441 КБ (client_rule=false) — VPN-путь.
- accept: panel byte-identical, 2/2 new_sha, воркеры inactive, panel/VPN 200,
  таймер остановлен, место 45 ГБ.
- Слой TLS-лимита **оставлен** (accept по ТЗ при успешных пробах).
- Приватное: `~/xgw-tls.fs` (0700/0600) — снапы, дельты, логи, URL-файл, скрипты;
  бэкап `/var/lib/xgw/handoff/selective-tls-…` сохранён. URL/подписи/IP не публикуются.
- Publication commit: добавить после push.
