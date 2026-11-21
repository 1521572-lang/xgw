# ThinkCentre · пересчёт метрик плеера и проверка правил XGW — 2026-11-21

- RESULT: **REPLAY_900 = PASS и REPLAY_SEEK = PASS** — пересчёт обоих
  принятых окон новым инструментом (`06cad10`) дал acceptance.ok=true,
  `differing_fields=[]` (метрики воспроизведены бит-в-бит), у обоих окон
  `cache_buffer_below_5s=true` выделено отдельным полем и
  `cache_read_below_bitrate=false`. **PLAYER_UNIT 8/8** (-k headless).
  **RULES_UNIT: 9 failed / 206 passed / 15 skipped** — все 9 отказов
  воспроизведены и на базе `08d31ee` (nft.py идентичен), то есть
  предсуществующие с 11-19; первый отказ — assert на порядок правил v6
  guard. **NETNS_NFT: все 9 фикстур rc=0** (nft --check в изолированном
  netns). **CONTROL: off/off fresh до и после, SHA настроек не
  изменился**. Read-only, установки не было.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; nftables v1.0.9; инструмент
  `06cad10…`; базы не касались.

## §1 REPLAY сохранённых окон

| Поле | replay-900 | replay-seek |
| --- | --- | --- |
| acceptance.ok / outcome-окно | true / 900с | true / 300с |
| progress_ratio | 0.9966 | 0.9977 |
| 720p / пропуски | 1.0 / 0.0с | 1.0 / 0.0с |
| остановки (сумма/макс) | 1.0005с / 1.0005с | 0.0 / 0.0 |
| **differing_fields** | **[]** | **[]** |
| **cache_buffer_below_5s** | **true** | **true** |
| cache_min_seconds | 0.56с | 2.02с |
| cache_read_median_Bps | 130 035 | 152 058 |
| cache_read_to_bitrate_ratio | 1.282 | 1.499 |
| **cache_read_below_bitrate** | **false** | **false** |

- Короткий буфер зафиксирован отдельной метрикой в обоих окнах; вердикт
  принятых окон воспроизведён без различий (differing_fields=[]).
  Условие «медиана чтения ниже битрейта» в обоих окнах не выполняется —
  THROTTLED сводится к буферному критерию (согласуется с отчётами 900с
  и seek r2).
- Остановки: 1.0с в окне 900с, 0 в окне seek — суммы соответствуют
  исходным отчётам.
- Архивы найдены штатно (по одному кандидату на метку), сверь с
  приватными сводками исходных отчётов выполнена по метаданным окон.

## §2 UNIT-наборы

- **PLAYER_UNIT**: 8 passed / 0 failed / 0 skipped (35 deselected по -k
  headless).
- **RULES_UNIT** (test_nft, test_zapret2, test_tailscale,
  test_tailscale_t2): **9 failed / 206 passed / 15 skipped**.
  - Первая ошибка (обезличенно): `tests/test_tailscale.py::test_v6_guard_…`
    — AssertionError на позиции правила `oifname "tailscale0" accept`
    в ожидаемом списке строк v6 guard (порядок правил отличен от
    ожидаемого тестом).
  - Затронуты: 5 тестов test_nft (gateway/loopback/ip6-capture/blocked/
    v6-guard) + 4 параметризации test_tailscale (blocked-through-always,
    v6-guard on/blocked/off).
  - **Сверка с базой**: тот же набор на worktree `08d31ee` даёт
    **идентичные 9 failed** (110 passed / 15 skipped на двух файлах),
    `src/xgw/net/nft.py` базы и кандидата побайтово совпадают,
    тесты не менялись с 11-19 → **отказы предсуществующие**, кандидатом
    `06cad10` не внесены; гейты предыдущих проходов эти файлы не
    запускали, поэтому не встречались.
  - Пропуски (15 в обоих наборах) — тесты nft, требующие root/фактического
    применения правил; при обычном пользователе пропускаются штатно
    (в netns-части ниже они компенсированы).

## §3 NETNS_NFT (T03–T05, изолированные namespace)

| Фикстура | rc | | Фикстура | rc |
| --- | --- | --- | --- | --- |
| off | 0 | | tailscale-direct | 0 |
| capture | 0 | | tailscale-vpn | 0 |
| selected | 0 | | containers | 0 |
| selected-replies | 0 | | blocked | 0 |
| engine | 0 | | | |

- Все 9 фикстур прошли `nft --check` внутри `unshare --net` на ядре
  7.0.0-43 / nftables 1.0.9 — синтаксис ветвей, включая счётчики
  conntrack (selected-replies, engine), валиден для этого ядра.
  unshare доступен, BLOCKED не зафиксирован.

## §4 CONTROL

vpn-before и vpn-after: обе службы active, off/off fresh/matched;
control-unchanged rc=0 — SHA config.toml+panel.json не изменился.
Машина в финале: off/off fresh/matched, политика не менялась.

## Наблюдения для Codex

1. **9 отказов nft/tailscale — предсуществующие с 11-19** и не
   покрытые ни одним гейтом этой серии (гейты гоняли applier/singbox/
   route_evidence/probe_watch/daemon-срез). Если v6-guard-порядок —
   след последних изменений nft.py (7ace100/87382f9 от 11-19), тесты
   отстали от кода; если код верен — отстали тесты. Требуется базовая
   линия Codex: бежать эти два файла в гейте следующего кандидата,
   чтобы класс не маскировал новые отказы (как ранее с test_daemon).
2. **Пересчёт подтверждает метрику буфера** как самостоятельный признак:
   оба окна `cache_buffer_below_5s=true` при `cache_read_below_bitrate=
   false` — троттлинг-вердикт теперь выражается явно, и его можно
   исключать из строгих порогов остановок.
3. netns-проверка синтаксиса работает на этом ядре для всех девяти
   фикстур — можно встраивать `nft --check` в гейты кандидатов, меняющих
   net/nft.py, без прав на живые правила.
- Publication commit: _заполняется при публикации_.
