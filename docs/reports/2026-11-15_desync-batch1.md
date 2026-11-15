# Ubuntu 24.04 — desync batch 1 — 2026-11-15

- RESULT: **PARTIAL** — установка не выполнялась (стоп по §7 перед apply): новый загрузчик
  конфига падает `PolicyError` на реальном panel.json этого шлюза (легаси-zapret2 с
  стратегией эпохи freepool). Всё до apply пройдено, payload/бэкап подготовлены, Live/API/GUI
  на реальном backend — NOT_RUN, PREVIEW карточки на fixtures — PASS.
- BASE: 48f7ebae15096c40aaa4b82b7f3b19488ab24dd3
- CODE / PLAN / HOTFIX commits: CODE = `557e51501cb0e85318c1a6992ba3ea4b4443942f` (единственный
  коммит, меняющий NEXT_STEP.md в delivery-ветке); хотфиксов кода нет; один
  fixture-хотфикс-коммит исполнителя `0a4b664` (тест-ожидание managed.load — см. ниже).
  Отчёт публикуется следующим коммитом той же ветки.
- Executor: GLM 5.3 Flash; команды и vision выполнены исполнителем на шлюзе; root — один
  systemd-run --system юнит с FIFO; GUI-прогоны — от пользователя через `systemd-run --user`.
- OS ID / VERSION_ID / kernel: `ubuntu` / `24.04` (Ubuntu 24.04.5 LTS, noble) /
  `7.0.0-43-generic`. Замечание исполнителя: прежние отчёты r2/r3/flowseal ошибочно называли
  ОС «26.04» — фактический os-release на машине: 24.04.5; уточнение владельца совпадает с фактом.
- Python 3.12.3 (демон /usr/bin/python3.12) / nft 1.0.9 / nfqws2 v1.0.7 (038c97e5…) —
  только `--version` / curl 8.5.0 **без HTTP3** в возможностях (no HTTP3 string in
  `curl --version`; QUIC-пробы не запускались по скоупу).
- Installed backend path: `/opt/xgw/lib/xgw` (readlink, без symlink); GUI: установленный
  freepool-релиз `/opt/xgw/gui/releases/7c20f59…` с dispatcher-ом из отчёта vpn-ui-install
  (ACTIVE) — накладки батча на него **не** применялись (установка заблокирована).
- GUI mode: **PREVIEW** (полный checkout GUI_BASE 7c20f59 + два файла из CODE; overlay на
  установленный релиз не выполнялся, т.к. backend-установка остановлена).

## Checks

| Check | PASS / FAIL / NOT_RUN | Evidence / reason |
|---|---|---|
| Ubuntu 24.04 confirmed | **PASS** | `/etc/os-release`: ID=ubuntu, VERSION_ID=24.04, 24.04.5 LTS/noble |
| Baseline hashes | **PASS** | config.toml `89bf2a67…`, panel.json `33916cb5…`; backend-файлы пакета = BASE (config 28aa76b4…, managed e51ab5b7…, daemon 4911fdef…, watch/panel 0e0e13ce…); workers xgw-nfqws2/xgw-zapret2 inactive; приватные снимки nft/ip-rule/ip-route в каталоге прогона |
| Portable unit tests | **PASS** | `pytest --portable tests/test_desync_schema.py tests/test_zapret2_panel.py` — **51 passed** (pytest 9.2.0) |
| Targeted Linux regression tests | **PASS с 1 пред-существующим провалом** | `pytest -q test_config test_managed test_zapret2 test_nfqws2 test_panel` — **194 passed, 1 failed**. FAIL: `test_panel.py::test_free_pool_card_switches_observation` — воспроизводится и на чистом BASE 48f7eba (ключ `pin` в карточке free_pool появился в gui-light раньше батча) — **вне скоупа батча**, не скрывался, не правился |
| Ruff | **PASS** | `ruff check` по всем изменённым файлам: All checks passed (0.17.5) |
| Hotfix: тест-ожидание managed.load | **PASS** | Батч намеренно добавляет `zapret2`/`desync` в результат `managed.load`; старый `test_junk_inside_the_file_is_ignored` падал на Linux (полный набор на Windows не гонялся). Хотфикс `0a4b664`: два ключа добавлены в ожидаемый словарь (assert не ослаблен); test_managed.py 31 passed |
| Payload + helper prepare | **PASS (после исправления прав каталогов)** | `git archive`-payload в `/opt/xgw/handoff/desync-batch1-<CODE>/{code,base,gui_base}`; первая попытка prepare отказалась: tar создавал каталоги **0775** → helper `trusted()` справедливо требовал отсутствие group-write; после `chmod -R g-w` — `prepare: complete`, манифест **9 строк** (4 модификации backend, 3 новых файла backend, 2 накладки GUI), все BASE-файлы совпали, backup 0700 с old/new 0600 |
| Rollback timer armed before apply | **NOT_RUN** | apply не выполнялся — таймер не вооружался (проверка `is-active`: inactive; таймер-юнит не создавался) |
| Daemon / API LIVE_OFF | **NOT_RUN** | установка остановлена до apply (см. Blocker); карточка в живом API не проверялась |
| policy_matched / fresh | NOT_RUN | — |
| FIXTURE_ACTIVE / ERROR / ABSENT / STALE | **PASS (PREVIEW)** | Отдельный видимый процесс на checkout GUI_BASE + 2 накладки из CODE, состояние через fixture-мост (Client из tests), сеть/сервисы не тронуты: 16 кадров. Note-подписи точны: missing→«Нет данных», off→«Выключен», off+mode=selective→«Не используется», active→«Обработчик готов» (+штатная оговорка про YouTube), error→«Ошибка обработчика», absent→«Не установлен», fresh=false→«Не подтверждён», pending→«Применяется», preparing→«Запускается», blocked→«Ошибка», fallback→«Прямой путь отключён», compared→«Сравнение завершено», unknown→«Не подтверждён», legacy без policy_key→«Выключен». Обе темы (светлая/тёмная), зелёная рамка кнопки у ok-тонов, текст без обрезок и без None. `Client.sent` за все переходы: **0** |
| GUI main screen / details / both themes | **PASS (PREVIEW)** — как выше; LIVE — NOT_RUN | — |
| Config migration, idempotence, temporary-file flock/0600 | **PASS (на копиях)** | Копии panel.json/config.toml в приватном каталоге прогона (рабочие файлы не перезаписывались): `migrate(legacy, source="gui-light")` → policy v1 (mode=off, strategy=hostfakesplit_md5, 10 доменов), повторная миграция идемпотентна; `managed.set_desync()` на временном файле в D: первая запись changed=True, режим 0600, повторная запись той же политики не переписывает файл (mtime не изменился), reload читает политику; flock конфликтов не выявил |
| Configuration unchanged | **PASS** | SHA config.toml/panel.json до и после раунда идентичны |
| Xray PID / other services / network structure unchanged | **PASS** | MainPID 26204 (ActiveEnter 14.11 21:52 — не перезапускался), xgw-net/xgw-xray active как в baseline, xgw-singbox inactive; nft-snapshot снят только на чтение; никаких изменений правил/маршрутов батчем не производилось |
| Installed hashes after timer cancellation | **NOT_RUN / N/A** | таймер не вооружался; установленная часть пакета сверена с BASE — изменений нет (gui/app.py c1a461ab… — это dispatcher Proton GUI из предыдущего раунда, к батчу не относится) |
| Restore, if required | **N/A** | откат не требовался — файлы пакета не заменялись |

## Blocker: остановка перед apply (главный результат раунда)

Проверка §4 «new config reader» на **реальных** конфигах шлюза завершилась ошибкой:

```
xgw.desync.schema.PolicyError: desync: selected strategy requires batch T04 on gui-light
(из config.load → _merge_managed → project(cfg.desync))
```

Причина: `/etc/xgw/panel.json` содержит легаси-секцию `zapret2` эпохи freepool/r6 —
`{"mode": "off", "strategy": "hostfakesplit_md5", "domains": [10 адресов], "probe_urls": […]}`
(напечатаны только нечувствительные поля). `schema.migrate` сохраняет такую политику корректно
и идемпотентно, но `config.load()` всегда выполняет `project(cfg.desync, target="gui-light")`,
а `project()` отклоняет любую стратегию вне {multisplit, multidisorder} **даже при mode=off**.
Следствие: после установки батча демон не смог бы загрузить конфиг при любом рестарте
(helper `apply` в этом случае вернул бы файлы по except-ветке, но установка состоялась бы
только как мгновенный откат). По §7 («неподдерживаемый режим», «конфликт политик») исполнитель
остановился до apply; таймер не вооружался; манифест/бэкап остаются подготовленными.

Дополнительная проверка: та же политика со стратегией `multisplit` проектируется успешно
(`project → PASS, mode=off`) — блокер именно в непредставимой legacy-стратегии при off-режиме.

Варианты разработчику (решение не принималось исполнителем — это семантика):
(a) проецировать политику с `mode=off` в off, не требуя представимости стратегии (ничего не
запущено — семантической потери нет; стратегию сохранять в документе);
(b) считать такую политику «не используется» с pending-состоянием карточки;
(c) требовать очистки легаси-секции перед батчем (операторское действие + проверка в helper).

## Observations and hotfixes

1. **Хотфикс-коммит `0a4b664`** (fixture-ожидание, разрешён §7): `tests/test_managed.py`
   `test_junk_inside_the_file_is_ignored` — добавлены ожидаемые новые ключи `zapret2: {}` и
   `desync: None` результата `managed.load`. Причина: батч расширил результат осознанно
   (контракт, Windows-отчёт), полный Linux-набор на Windows не гонялся. Проверка:
   test_managed.py 31 passed; assert не ослаблен.
2. **Механика payload**: `git archive | tar` создаёт каталоги 0775; helper `trusted()`
   требует отсутствие group-write → первый prepare корректно отказал. Исправлено
   `chmod -R g-w` на payload (усиление, не ослабление). Рекомендация: в NEXT_STEP добавить
   `chmod` после распаковки либо `--no-same-owner --mode=`-замечание.
3. **Пред-существующий провал** `test_panel.py::test_free_pool_card_switches_observation`
   (ключ `pin` в карточке free_pool) воспроизводится на BASE 48f7eba — к батчу не относится,
   к отчёту для разработчика: тест-ожидание отстало от gui-light-кода.
4. Прежние отчёты исполнителя (r2/r3/flowseal) называли ОС «Ubuntu 26.04» — фактически
   24.04.5 LTS; уточнение владельца 24.04 совпадает с реальностью.
5. PREVIEW-заметка: карточка `state=active` с `policy_matched=false` и `strategy=null` в
   fixture показывает «Обработчик готов» — GUI доверяет `state` и не ветвится по
   `policy_matched`. По контракту backend не должен излучать active без подтверждения
   политики; для GUI это наблюдение, не дефект.
6. Сетевые пробы/YouTube в батче не выполнялись (скоуп); nfqws2 — только `--version`;
   HTTP3 в curl 8.5.0 отсутствует (для будущих QUIC-батчей учесть).

## Final machine state

- Backend: **previous (gui-light BASE 48f7eba)** — файлы пакета побайтово BASE
  (config 28aa76b4…, managed e51ab5b7…, daemon 4911fdef…, watch/panel 0e0e13ce…);
  `gui/app.py` c1a461ab… — dispatcher Proton GUI из предыдущего раунда (ACTIVE, не менялся).
- GUI: **unchanged** (установленный релиз 7c20f59 без накладок батча; PREVIEW в отдельном
  checkout, окно закрыто штатно).
- Worker / selected mode / engine: xgw-nfqws2 inactive, xgw-zapret2 inactive, policy off —
  как до раунда.
- Config files restored or unchanged: **unchanged** (SHA совпадают).
- Rollback timer/service state and backup availability: таймер не создавался (inactive);
  `/var/lib/xgw/handoff/desync-batch1-<CODE>/` подготовлен (manifest 9 строк, old/new 0600,
  helper 0700-каталог); payload в `/opt/xgw/handoff/desync-batch1-<CODE>/` (права 0755/0644
  после chmod) — **оставлены до разбора отчёта** по инструкции.
- Remaining blockers for T03: разрешить коллизию легаси-panel.json (см. Blocker) — без неё
  установка батча на шлюзе с legacy-стратегией невозможна; затем обычная цепочка §5–§6.
- Publication commit: отчёт публикуется следующим коммитом ветки
  `integration/zapret2-batch1` (хотфикс `0a4b664` — предыдущий; self-hash не требуется).
