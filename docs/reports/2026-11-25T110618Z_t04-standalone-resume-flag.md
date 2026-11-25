# ThinkCentre · восстановление состояния поколений sing-box — 2026-11-25

- RESULT: **БЛОК ПРОЙДЕН, КОД 0, НО С ОДНИМ ДОПОЛНЕНИЕМ FLASH: В
  ЗАКРЕПЛЁННОЙ ВЫДЕРЖКЕ АРХИВА НЕТ КАТАЛОГА packaging, А НОВЫЕ ТЕСТЫ
  ЧИТАЮТ packaging/xgw-singbox.service — ПЕРВЫЙ ЗАПУСК ДАЛ 2 FAILED
  (FILE NOT FOUND) ИЗ 71. ДОПОЛНЕНИЕ — ТОЛЬКО В ТЕСТОВУЮ КОПИЮ:
  packaging ДОБАВЛЕН В ВЫДЕРЖКУ ТОГО ЖЕ КОММИТА; ПОВТОР — 71 PASSED.
  ТОПОЛОГИЯ ШЛЮЗА STABLE: АКТИВЕН BLUE, МАРКЕР НА МЕСТЕ,
  PENDING/DRAINING НЕТ, RESUME_MANAGED FALSE, STALE_RESUME_MANAGED
  FALSE, СЛУЖБА blue ACTIVE, legacy INACTIVE. ШЛЮЗ НЕ ИЗМЕНИЛСЯ
  (СНИМКИ И ХЭШИ СОВПАЛИ). В ДЕЙСТВУЮЩЕЙ ЗАПИСИ УСТАРЕВШЕГО ПОЛЯ УЖЕ
  НЕТ (СНЯТО В ПРЕДЫДУЩЕМ ПРОХОДЕ), ПОЭТОМУ ЕГО ОБРАБОТКА ПОДТВЕРЖДЕНА
  КОНТРАКТАМИ: ГЕЙТ ПРИНИМАЕТ УСТАРЕВШИЙ ФЛАГ У MANAGED-СЛОТА,
  ВОССТАНОВЛЕНИЕ СНИМАЕТ ТОЛЬКО ЕГО И СОХРАНЯЕТ LEGACY-ЗАПРОС.
  ПРЯМОЙ ДИАПАЗОН CDN И ПРИЧИНА ПРЕЖНЕГО OFF_DEADLINE ОСТАЮТСЯ
  ОТКРЫТЫМИ.**
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43-generic; Python 3.12.3,
  pytest 7.4.4 системные; кандидат `fe93c57…` (приём `d4490a5…`,
  предок подтверждён; закреплён как предок). TOPOLOGY-фаза — только
  чтение состояния; шлюз в off/off, blue managed.

## §1 CONTRACTS — 71 passed (19,7 с), 0 failed / 0 skipped (после дополнения)

| Проверка | Что подтверждает |
| --- | --- |
| `test_managed_topology_accepts_an_obsolete_resume_flag` | готовность blue/green принимает прежний формат с устаревшим флагом, если служба и маркер подтверждены, переходы завершены |
| `test_recovery_clears_only_obsolete_resume_flag_for_a_managed_slot` | восстановление демона удаляет только устаревшее поле и только у managed-слота |
| `test_recovery_preserves_legacy_resume_request` | запрос возврата у legacy сохраняется |
| `test_legacy_return_and_pause_require_a_resume_request` | legacy-возврат и пауза требуют запроса resume |
| `test_standalone_return_keeps_legacy_until_managed_bridge_is_verified` | возврат держит legacy, пока мост managed не подтверждён |
| `test_unused_marker_is_cleared_after_legacy_recovery` | лишний маркер снимается после legacy-восстановления |
| `test_ready_process_dies_before_api_old_remains` и прежние | отказ готовности при pending, остановке, отсутствии живой службы; прежние проверки прошли |

## §2 TOPOLOGY — `stable`, код 0

| Поле | Значение |
| --- | --- |
| Активный слот | **blue** |
| Маркер managed | **есть** |
| pending / draining | нет / нет |
| `resume_managed` | false |
| `stale_resume_managed` | false |
| `standalone_stopping` | false |
| Службы | `xgw-singbox-blue` active, `xgw-singbox` inactive |

- Исходное состояние рабочего шлюза не менялось — только чтение.

## §3 Шлюз

- **T04_GATEWAY_UNCHANGED** — снимки наблюдения хоста до и после
  совпали; хэши config.toml и panel.json — совпали.

## Наблюдения для Codex

1. **Выдержка архива в блоке неполная**: `git archive $CODE src tests
   docs/helpers vpn_ui pyproject.toml` не содержит `packaging/`, а
   `test_singbox_generations.py` читает `packaging/xgw-singbox.service`.
   На свежей машине блок детерминированно даёт 2 failed. Достаточно
   добавить `packaging` в список (что я и сделал — дополнение только
   в тестовую копию).
2. **Ловушка прошлого прохода закрыта контрактом**: гейт baseline
   теперь принимает устаревший `resume_managed` у managed-слота —
   именно этот флаг уронил прошлый проход в `topology_not_confirmed`.
   Вмешательство FLASH (ручное снятие флага) больше не потребуется.
3. **Восстановление аккуратно разделяет два смысла флага**: для
   managed-слота поле устаревшее и снимается; для legacy — это
   действующий запрос resume и сохраняется. Это совпадает с тем, что
   наблюдалось на машине (после сбоя off флаг остался, а blue был
   поднят штатно).
