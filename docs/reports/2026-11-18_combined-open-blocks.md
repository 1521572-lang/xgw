# Ubuntu 24.04 — расширенная приёмка открытых блоков (2b78617) — BLOCKED_TEST — 2026-11-18

- RESULT: **BLOCKED_TEST — целевой набор пакета падает на параметре, привязанном к
  коду этого пакета; установка остановлена до prepare** (по ТЗ §2: «Ошибки в коде
  этого пакета блокируют установку. Известную постороннюю ошибку сравни с OLD»).
  `tests/test_zapret2_management.py::test_invalid_edit_is_private_and_never_writes
  [patch4]` — **FAIL**: параметр `patch = {"strategy": schema.LIVE_STRATEGY}`
  (= `flowseal_alt9`); settings-запрос возвращает `ok=true` (стратегия сохраняется),
  тест закрепляет противоположное — «невалидная правка отклоняется и никогда не
  пишется». **Контраст OLD/NEW** (по ТЗ): на OLD `3d117b1` этот же тест — **10 passed**
  (patch4 отклоняется); на NEW `2b78617` — 9 passed + 1 failed. Точная причина:
  валидация `zapret2_management.candidate` в 2b78617 разрешает сохранить
  `strategy=flowseal_alt9` произвольным settings-запросом — вероятно, whitelist
  стратегий расширен для нового UI-импорта Flowseal без ограничения источника правки
  (импорт должен сохранять её, а не ручная правка). Установка не начиналась:
  payload/backup не создавались, конфиги byte-identical, off/off, VPN/panel 200.
- Остальные результаты этого прогона (до остановки):
  - **api-tests**: tests/test_panel.py -k zapret2 — **9 passed**;
  - **Qt-фикстура** на копии установленного релиза с новым gui/zapret2.py:
    **11 passed** (включая пульс-тест);
  - node --check zapret2.js — OK; bash -n restore — OK;
  - **посторонние отказы (среда), воспроизводятся на OLD** — 14 из 15:
    test_nft.py ×5, test_applier.py ×3, test_freepool_backend.py ×3,
    test_freepool_traffic.py ×2, test_nfqws2.py ×1 (сравнение выполнено в отдельном
    worktree OLD `3d117b1` тем же списком: 14 failed, 1 passed — разница только
    patch4). Эти строки не блокер кода `2b78617`, среда ThinkCentre/nft-версии;
  - итого main-набор: **562 passed, 15 failed, 15 skipped** (15 skipped — как на OLD).
- CODE: `2b78617075e289e5ce9930e092101a565bfe60c8`; база OLD `3d117b1…`;
  Ubuntu 24.04.5 LTS. Установка: **NOT_RUN** (cmp-блок §3 не выполнялся); таймер:
  NOT_RUN; CLI/jobs/CDN-проба/Flowseal-импорт/матрица 18 — NOT_RUN (зависят от
  установки). Машина: off/off, воркеры inactive, xgw/xray active, VPN 200, панель
  200 (401 без cookie), конфиги `89bf2a67…`/`33916cb5…` byte-identical, диск 42 ГБ.
- Финал: машина в исходном состоянии; тестовые worktree OLD/NEW удалению не
  подлежали в рамках прохода (локальные, 0700).
- Ждёт исправления Codex: ограничить источник сохранения `strategy=flowseal_alt9`
  импортом Flowseal (settings-запросы с ручной стратегией — отклонение), либо
  обновить закрепление теста, если приём ручной стратегии стал намеренным контрактом.

## Точная диагностика

```
param: {"strategy": schema.LIVE_STRATEGY}   # = flowseal_alt9
NEW 2b78617: send(cfg, patch) → ok=true     # стратегия пишется
OLD 3d117b1: send(cfg, patch) → ok=False    # отклоняется
assert not result["ok"]  → FAIL
```

- Управление `zapret2_management.py` в этом пакете изменено (расширение Flowseal-
  импорта); test_zapret2_management.py в пакете не менялся относительно OLD —
  закрепление осталось прежним.
- Publication commit: `f9a04e74d3e2600be04b2c1602eb14c054d8836b` (b534c3b → f9a04e7, remote verified byte-identical to local HEAD).
