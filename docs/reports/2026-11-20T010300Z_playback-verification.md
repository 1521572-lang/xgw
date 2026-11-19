# Ubuntu 24.04 — playback verification: автоматизированный плеер детектируется, обычный Chrome играет — 2026-11-20

- RESULT: **BASE_CHECK PASS (11/11 файлов = BASE `08d31ee`, off/off fresh, 57 tests),
  MATRIX RECOUNT PASS (full_matrix=true, 18 строк, two_https_pass: multidisorder,
  fake_md5_split, fake_seq, fake_md5, fake_static_md5 — восстановлен из matrix-result.json
  через client matrix), VPN_PLAYER_FAIL ×2 (desktop-chrome и playwright: player_error
  «Что-то пошло не так» после ~38–45 с, eligible 27.9/35.3/39.2 с из 120), ОБЫЧНЫЙ
  CHROME БЕЗ СБОРЩИКА — играет (кадры меняются, 720p, движение сцены между
  скриншотами 21:59→22:02), диагностический исход зафиксирован как самостоятельный:
  подключение CDP-сборщика ломает плеер; дальнейшие измерения на одном ролике
  не выполнялись (по ТЗ §2 — самостоятельный исход), политика не менялась
  (restore не вооружался), финал off/off, VPN 200**.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; Chrome 158.0.8127.36; кандидат-инструменты
  `402cda1…`; BASE `08d31ee…` — cmp 11/11 файлов совпали.
- §2 тесты: test_youtube_telemetry + test_desync_jobs — **57 passed**.

## MATRIX RECOUNT — PASS

`client matrix matrix-result.json`: ok=true, job_id `8d4c328e…`, full_matrix=true,
observed=expected=18 строк, states: active 13 / fallback 1 / timeout 4;
**two_https_pass**: multidisorder, fake_md5_split, fake_seq, fake_md5,
fake_static_md5 (5 профилей × 2 active). Ревизия прошлого job подтверждена
снимком, строки не подставлялись.

## §2 Плеер — диагностика (самостоятельный исход)

| Запуск | Плеер | Исход |
| --- | --- | --- |
| vpn-desktop control, attempt 1 | desktop-chrome + CDP | player_error после 38.2 с (eligible 27.9 с из 120; failed: duration, eligible, progress, sampling_gaps; media 5.2 МБ успело) |
| vpn-launcher control ×1 | playwright | player_error после 44.2 с (eligible 35.3 с из 120; h_ratio=1.0 — 720p играл до ошибки) |
| Обычный Chrome без сборщика | играет | кадры 21:59→22:02 — сцены меняются (720p), нет ошибки плеера |

- Линия в этот период исправна: t/terms direct 200/0.40 с; googlevideo (rr5,
  173.194.x.x) TLS handshake — OK (openssl).
- Причина player_error: подключение CDP/инъекция телеметрии → YouTube рвёт
  медиа-стрим («Что-то пошло не так»). Это различие **сборщик vs чистый браузер**,
  а не линии: тот же ролик, тот же профиль off/off, тот же период.
- Влияние: измерения 900/300 с под сборщиком невозможны на этом YouTube-клиенте;
  требуется обход детекции (Codex: убрать/замаскировать CDP-инъекцию или собирать
  данные из обычного Chrome через внешний канал — например, чтение
  performance-логов через расширение/профиль без CDP-attach во время записи).
- Ограничение: «обычный Chrome играет» — наблюдение по кадрам/движению сцены,
  без численных 900 с; это диагностика, не результат проверки.

## Состояние машины

off/off, воркеры inactive, VPN 200, panel 200 (база `08d31ee` 11 файлов не
менялась — cmp 11/11), restore не вооружался (изменений политики не было),
день не назначался, диск 42 ГБ. Тестовые браузеры закрыты. Приватные артефакты
(logs, verification.json ×2) — в каталоге опыта 0700.

## Наблюдения для Codex

1. **CDP-attach ломает YouTube-плеер** (воспроизводимо: desktop-chrome и
   playwright — player_error «Что-то пошло не так» ~40 с; чистый Chrome — играет).
   Для измерений 900/300 с нужен сборщик без CDP-вмешательства во время записи:
   профиль Chrome с включённым Chrome-расширением-логгером, или внешние
   performance-log через отдельный debug-порт только после конца записи, или
   WebRTC/DASH-счётчики через обычный профиль.
2. `--desktop-chrome` и playwright дают одинаковый исход — различие каналов не
   влияет; определяет именно CDP.
3. matrix recount работает: full_matrix=true, two_https_pass 5 профилей — готово
   для pin в следующих проходах.
- Publication commit: `добавляется после push`.
