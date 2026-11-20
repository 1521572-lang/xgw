# ThinkCentre · кто применяет конфигурацию Xray во время просмотра, r3 — 2026-11-20

- RESULT: **UNIT_TESTS PASS · DAEMON_BASELINE ok=true (changed=0, matching=12,
  new=0) · INSTALL PASS · WRITER_CONTROL PASS (`none_observed`, writes=0) ·
  АДМИССИЯ: attributed ({zapret2_route: 2}) · LIVE_PLAY PASS (135.1с, 720p
  100%, stall 0) · FLOW inconclusive (конфиг сменился — теперь объяснён) ·
  **CONFIG_WRITER РЕШЁН: `state=attributed`, во время просмотра запись
  `daemon_rebuild` — причина из смежного apply-события: «замена участника»
  (штатная ротация участника VPN-балансировщика с пересборкой
  routing/outbounds)** · RESTORE VERIFIED**.
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee`); кандидат
  `aedb68c` — 3 файла (applier, singbox_generation, daemon) поверх `3a00777`;
  тесты обычным пользователем, оба worktree из одного коммита (baseline =
  кандидат с 3 файлами, восстановленными из `3a00777`; diff-only проверен).

## §1 Гейт (r2-аномалия закрыта)

- writer-unit rc=0; daemon-current rc=1, daemon-baseline rc=1, оба 158
  кейсов; **gate ok=true: matching_baseline_failures=12 (бит-в-бит),
  changed_failures=[], new_failures=[], added/missing/new_skips пусто**.
- Прошлые 12 «changed» (r2) были артефактом сравнения копий из разных
  коммитов; в r3 обе копии на одних тестах/зависимостях — поведение
  идентично. Уточнение Codex подтверждено отчётом r2-счётчика: «6 vs 4»
  измеряло вызовы чтения версии бинарника, не записи конфига.

## §2 Контролируемые окна

- **Спокойное off-окно**: `none_observed`, writes=0,
  `same_config_at_boundaries=true` — фон чистый, инструмент работает.
- **Окно допуска** (пара t/terms + действующий прямой адрес; Standing
  snapshot → Selective → active/https_reachable → snapshot):
  `state=attributed`, **writes=2, by_source={zapret2_route: 2}**,
  final_write.source=zapret2_route (offset 50.6с). Положительный контроль:
  каждая запись привязана к журналу; источник — API-путь маршрута zapret2
  (настройки/включение Selective), «других подсистем» не было.

## §3 Фаза просмотра — CONFIG_WRITER

- Плеер: **ok=true** — 135.1с eligible, прогресс 99.1%, 720p 100%, stall 0,
  gaps 0, медиана чтения 198 КБ/с.
- Журнал на границах: **`state=attributed`, writes=2,
  by_source={"daemon_rebuild": 1, "zapret2_route": 1},
  final_write.source=daemon_rebuild** (offset 110.9с — внутри просмотра).
- Смежное apply-событие (время записи 63мс до сообщения):
  **«apply: замена участника: применено через API без перезапуска: ado:
  …, spare-…; adrules: routing»** — health-check демона заменил участника
  VPN-балансировщика на запасной и пересобрал routing/outbounds/inbounds.
  Причина подтверждена совпадением времени проверки.
- Первая запись окна — `zapret2_route` (старт фазы: применение маршрута
  zapret2), вторая — `daemon_rebuild`.
- FLOW (атрибуция потока плеера): inconclusive — `field=applied_config`,
  `changed_sections=["routing","inbounds","outbounds"]` — но теперь это
  объяснено (rebuild на замене участника), а не открыто. Принятый
  FLOW=ZAPRET2 из отчёта потока остаётся сведением.
- **Ответ на вопрос прохода**: перезаписи routing/inbounds/outbounds в живых
  окнах — штатная замена участника балансировщика демоном (dae-style
  health-check) с API-применением без перезапуска. Не детекция, не проба,
  не внешний процесс. Совпадение с прежними окнами: в каждом было ~135с
  просмотра — окно попадает в цикл ротации участников.

## §4 Восстановление

off/off штатно до guard; guard rollback rc 0; marker; sha256 конфигов OK;
**3 файла оверлея cmp = базе `3a00777`**; xgw.service active; воркеры
inactive; off/off fresh (3-й опрос); ipify ок; таймер остановлен
(ActiveState=inactive) → **RESTORE VERIFIED**. Сырые журналы/URL/IP — на
машине в каталоге опыта 0700.

## Наблюдения для Codex

1. **Полный ответ по перезаписям**: writer-инструмент + journal-события
   дают сквозную атрибуцию (source, method, fingerprint, mono_ns). Вопрос
   закрыт: daemon_rebuild на замене участника. Опциональное углубление —
   помечать такие записи в route_evidence как «ожидаемая ротация», чтобы
   окна с заменой участника не падали в inconclusive (например, сравнивать
   routing-only-дельты при том же наборе outbound-тегов).
2. Гейт-механика выровнена и стабильна (обе копии из одного коммита) —
   будущие кандидаты могут сравниваться без шума.
3. Адмиссия делает 2 записи маршрута (settings + mode) — если желательно
   сократить перезаписи конфига при включении, можно батчить settings+mode
   в один apply.
- Publication commit: `добавляется после push`.
