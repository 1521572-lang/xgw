# Ubuntu 24.04 — admission: бюджет, матрица, видео — BLOCKED_TEST — 2026-11-19

- RESULT: **BLOCKED_TEST — расширенный гейт ок=false: одна новая ошибка, не в
  baseline-списке**. `tests/test_nft.py::test_tun_leaves_tproxy_for_lan_only_and_
  keeps_the_marking_chain` — FAIL на NEW `d818e80`, PASS на OLD `3630b44`. Точная
  причина (воспроизведена): тест сравнивает `output`-цепочку с рендером старой
  фикстуры `_cfg()`, а изменённый `nft.build_rules` теперь добавляет в output
  singbox TCP-close-правило: `meta skuid 992 … fib daddr type unicast update
  @singbox_tcp_close { … } ct mark set ct mark or 0x4000000 counter return`.
  Дифф на индексе 1: новое close-правило вместо `meta skuid 992 return`; Left
  contains 2 more items. Тест в пакете не синхронизирован с новым поведением
  build_rules — ошибка кода пакета. По ТЗ «Новый/изменившийся отказ… блокирует
  установку». Установка §3 не начиналась (payload/backup не создавались).
- Обязательный набор §2 — **PASS**: core **242 passed**, api **10 passed**,
  network-contracts **5 passed** (включая оба singbox_close теста — контракт
  исправления TCP close из `46c69fd` подтверждён на уровне правил), bash OK.
- Расширенный §2: NEW — **353 passed, 15 failed, 15 skipped, 4 deselected**;
  OLD (`3630b44`, с теми же deselect) — **354 passed, 14 failed, 15 skipped**;
  гейт: matching_baseline_failures=14, added/missing/changed_failures/new_skips
  пусты, **new_failures=[test_tun_leaves_tproxy_for_lan_only…] → ок=false**.
  Посторонние 14 отказов (nft/applier/freepool/nfqws2 среда) — как в прежних
  отчётах, с теми же сообщениями.
- CODE: `d818e809ea42221e70882b61c75d29e8f1eb3048`; OLD-база `3630b44…`;
  Ubuntu 24.04.5 LTS; nftables v1.0.9; ядро 7.0.0-43. Установка §3 (11 файлов,
  xgw-net.service) — NOT_RUN; §4 LOW_BUDGET — NOT_RUN; §5 матрица 18 — NOT_RUN;
  §6 видео с acceptance_playback_check — NOT_RUN (зависят от установки).
- Прежние сутки (§1): unit `xgw-combined-monitor-1795041850` **ещё активен**,
  elapsed ≈18.2 ч из 24 (файл 1090 строк, каталог `/home/xxx/xgw-combined.fO8GhFid`),
  LARGE/BACKWARD gaps 0, api_errors 1, UTC-пара снята (UTC_BOUNDARY_VIEW —
  resets_at сменился на 1795046400; UTC_LIVE_PROBES — NOT_OBSERVED при off/off).
  День продолжается — финализация (analyze, старый restore accept, погашение
  старых таймеров) будет выполнена по достижении 24 ч отдельным шагом; новым
  монитор не дублировался. M3_TRAFFIC=NOT_RUN (трафика пула нет).
- Машина: off/standalone-политика базы не тронута (root-операций не было),
  воркеры в исходном состоянии, конфиги byte-identical, VPN/panel 200, диск 42 ГБ.
- Ждёт исправления Codex: синхронизировать фикстуру/тест `…marking_chain` с
  новым output-рендером build_rules (singbox TCP-close-строки), либо ограничить
  добавление close-правил условием. После фикса — тот же гейт должен дать
  ок=true, установка продолжится с §3 без изменений.
- Publication commit: `добавляется после push`.
