# Ubuntu 24.04 — T07/T08: кэш контекстов и перенос между IP CDN — 2026-11-16

- RESULT: **PASS с открытым H02** — реальные записи Chrome по обеим стратегиям импортированы
  в shadow-кэш (ровно 11 полей метаданных, единый endpoint подтверждён по CDP Network,
  маршруту и очереди), CLI `compare/rebuild/lookup` работают, `apply:false` везде;
  **`compare` = `inconclusive`** (1 endpoint/1 prefix, оба раунда `abstained_fail`) —
  естественной смены IP не было, оба окна обслужил один адрес `77.37.252.211`
  (`rr8---sn-gvnuxaxjvh-c35d.googlevideo.com`, http/1.1, 28/27 SABR POST) — **перенос
  между IP не получил проверочной выборки, H02 остаётся открытым** (честно по ТЗ).
  Блок атомарности/TTL на файловой системе — **полный PASS**: miss→hit, параллельные
  rebuild+lookup, инъекция ENOSPC на rename (rc=2) и SIGKILL (rc=137) не повредили снимок,
  stale_history/invalid_snapshot/input_or_storage_error/miss-after-fail — точные коды,
  TTL заканчивается по возрасту более старого из двух раундов (граница найдена на
  +85600 c от now при старом раунде 800 c). Слой не менялся; off/off восстановлен.
- CODE: `3ac83052185b7c7d921c067721648ed9656123df`; BASE `29e10fd` (мой отчёт T07 — предок).
  pytest `--portable` (cache, shadow, experiment, youtube_telemetry): **81 passed, 3.79s**.
  Измерения из checkout; слой H05 остаётся на машине (панель менялась временно и
  восстановлена штатным restore таймера, конфиги byte-identical `89bf2a67…`/`33916cb5…`).

## 1. Исходное и прежний захват

- off/off, очередь пуста, acct=0, offload on, VPN 200; диск ~27 ГБ свободно.
- Старый tcpdump (1935908): жив, рост всплесками (1.09 МБ за 4 c в момент сверки) — EPERM
  сохраняется (T07 установил идентичность user-namespace); остановка передана администратору
  хоста. Новый WAN-захват не запускался.

## 2. Реальные записи Chrome (standalone через H05-слой)

Таймер возврата 45 м; контроль `hostfakesplit_md5` ≥2 мин (200 c, 720p, буфер до 83).
Дальше два окна с противоположным порядком и отдельным Chrome на фазу; в каждой фазе —
gate/владелец очереди/netlink ✓, свежий SABR, дельта `xgw-zapret2`, мосты inactive,
CDP Network-события (hostname + remoteIPAddress + protocol) — собраны только для
googlevideo-запросов.

| Фаза | Стратегия | Просмотр | SABR endpoint (hostname/IP/протокол) | Δ xgw-zapret2 | Импорт |
|---|---|---|---|---|---|
| контроль | hostfakesplit_md5 | 200 c, 720p | — (не импортируется) | — | нет |
| **A'** wan-window-1 | fake_static_md5 | 193.5 c измеренных, 720p | **rr8---sn-gvnuxaxjvh-c35d.googlevideo.com / 77.37.252.211 / http/1.1** (28 SABR POST) | +43.6 МБ | **да** |
| **B'** wan-window-2 | fake_clone_md5 | 204.3 c измеренных, 720p | **тот же адрес** (27 SABR POST) | +75.4 МБ | **да** |

- Обе фазы — один hostname/IP/протокол, `verified_direct_single_endpoint=true` по
  независимым признакам (CDP + счётчик bypass + очередь peer=PID + мосты off).
  Честные примечания: (1) первые импорты отклонены валидатором — `missing_trial_coverage`
  (дыра наблюдения 7–10 c в момент старта плеера: жест запуска блокировал main-thread и
  capture-интервал); принята запись от первого ряда **после** дыры — непрерывные 193.5/204.3 c
  измеренного воспроизведения (≥120 c). (2) Итоговые `outcome=playback_failed` у обеих —
  по строгим критериям валидатора (оценённая доля играющего времени 92.5 %/недобор и
  `estimated_stall` 3.8 c при 15-с гранулярности сэмплов), при фактически наблюдавшемся
  бесстоповом 720p; валидатор консервативен — исходы импортированы как есть.
- policy_sha256 = SHA-256 канонического документа: эффективная политика **без поля
  strategy** + code_commit/bundle/network/chrome-флаги/QUIC/mode/queue — одинаков для
  A' и B' (`18ba4cd9…`). client_sha256 — реального бинарника Chrome (`aea09d69…`).
- **Естественных смен IP не было** (оба окна — один адрес); H3/IPv6 маршрутов на стенде нет;
  подписанные запросы на другие адреса не перенаправлялись. **H02 (перенос) остаётся
  открытым** — проверочной выборки нет.
- Кэш: `compare` → **`inconclusive`** (observations 2, endpoints 1, prefixes 1; все скоупы
  exact/prefix_other_ip/host_other_ip/host_other_prefix — `with_history 0`,
  `abstained_fail 2`); `rebuild` → contexts 0 (fail-исходы подсказок не создают);
  `lookup` → **`miss`**; `apply:false` во всех ответах.
- Приватные права соблюдены (0600 на json, 0700 на каталоги); длина одного из history при
  первой записи была 0644 — CLI отклонил (`private_path_required`), исправлено на 0600 —
  ограничение приватности работает как задумано.

## 3. Атомарность и TTL (фикстуры, фиктивные хэши)

- miss → rebuild → **hit** (candidate=static, expires=last_success старого раунда+TTL);
  параллельные rebuild+5 lookup — без повреждений; **ENOSPC инъецирован на rename**
  (rc=2; физический раздел не заполнялся), **SIGKILL на rename** (rc=137) — в обоих случаях
  `sha256sum -c` снимка OK, lookup сохраняет hit; temp-остатков после следующего rebuild нет.
- Изменённый context → **`miss`**; свежий FAIL того же кандидата → после rebuild **`miss`**
  (подсказка вытеснена); свежий FAIL другого кандидата → подсказка другого кандидата
  сохраняется (hit) — семантика per-candidate; старый снимок при новой истории →
  **`stale_history`**; повреждённый JSON → `input_or_storage_error` (rc=2, подсказок нет);
  правка срока в корректном JSON → **`invalid_snapshot`** (digest-сверка поймала).
- TTL/откат часов — `cache.lookup(state, rev, ctx, now+Δ)`: hit при Δ=0 и 84000;
  **miss на Δ=85600** (800 c возраст старого раунда + Δ = 86400 = TTL — срок считается
  от более старого из двух успешных раундов ✓); за пределами built+TTL — `stale_clock`.
  Часы машины не менялись.
- Права: history/snapshot 0600, каталог 0700 — проверены.

## 4. Возврат

- Штатный restore таймера: panel byte-identical, apply с перезапуском Xray, → **off/off**,
  воркеры inactive, очередь пуста, acct=0, offload on/on/on, VPN 200, окно владельца
  открыто (PID 1243747), таймер остановлен после сверки. Измерения из checkout; полный
  Network/player.json/адреса/снимки кэша остались на стенде (0600/0700).
- Publication commit: добавить после push.
