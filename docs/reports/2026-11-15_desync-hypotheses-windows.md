# Дополнения к T01–T12: подготовка и локальные проверки

Дата: 2026-11-15. Среда: Windows 11. База: `f1fb5cb1613fa09dd57e2b25fd114a12c2079fc6`,
ветка `integration/zapret2-batch1`. Перед публикацией выполнен fetch: нового отчёта после
ffbf901 не обнаружено; f1fb5cb остаётся последним удалённым коммитом до этого батча.

## Изменения

- [Единый план](../handoff/DESYNC-ROADMAP.md): все 12 предложений H01–H12 включены в исходные
  T01–T12, с зависимостями, отрицательными контролями и ограничениями. Следующий основной
  кодовый этап T03 сохранён. GUI-проверка стрелок не потеряна, перенесена в архив задания.
- Исправлен `scope_swap` Flowseal для реальных форм hostlist/ipset без @ и для inline-domain;
  исключения сохраняются. TLS/HTTP на общих портах разделены filter-l7. Генератор и оба
  его результата обновлены для 22 конфигураций; POSIX-пути не зависят от Windows.
- Добавлены opt-in `fake-static-md5` и `fake-clone-md5` (нативный engine и lab launcher).
  Обе цепочки используют одинаковые rnd/rndsni, MD5, split 1,midsld. Изменяется только
  источник fake blob. При отсутствии clone fake пропускается; факт применения проверяется
  живым trace. Default и автоматическая VPN-лестница прежние. Убрана неподдерживаемая
  pinned Lua опция altorder=1, обновлено прежнее Linux test expectation.
- `python -m xgw.desync.experiment`: opt-in 45s media GET, pinned IP, h1/h2/h3-only,
  явный curl executable, ограничение времени/скорости/объёма, samples и классификация.
  URL только в приватном JSON/stdin; результаты без URL/IP. HTTP403, короткий EOF и
  поздняя остановка отделены. Заявленный direct сам по себе не подтверждает маршрут.
- История опытов и shortlist ≤3 семейств: TTL24h, context привязан к policy/network/client/
  protocol/exact-IP, две последние успешные пробы разных round, новый FAIL отменяет победы.
  Prefix key сохранён только для сравнения гипотезы; авто-применения/circular нет.
- В build_release dry-run не смешивается с intercept=0; packet handler требует живого
  трафика. Дистрибутив не собирался, vendor/C-код не изменён.

## Проверки

```text
pytest --portable tests/test_desync_experiment.py tests/test_desync_schema.py
91 passed
ruff check изменённых runtime-модулей, обычных tests, nfq_lab и build_release: PASS
ruff check --select F,E9 make_flowseal.py flowseal_lab.py: PASS
```

Portable guard запрещает subprocess/сетевые вызовы в тестах. Проверены в том числе
22 цепочки Flowseal, корректность HTTP/TLS/scope/excludes, static/clone argv, контексты,
TTL, поздний FAIL, разнообразие shortlist и классификация media. Полный lint старого
сгенерированного каталога не заявляется; у генератора проверены F/E9 и воспроизводимость.

Linux/systemd/NFQUEUE, исполнение Lua на пакетах, поток из сети и браузер:
**NOT_RUN в среде разработчика**. Минимальные локальные тесты не являются проверкой обхода.
Основная приёмка передана в [NEXT_STEP](../handoff/NEXT_STEP.md) и
[парную матрицу](../handoff/DESYNC-EXPERIMENTS-r1.md). Исполнитель запускает всё сам,
запрашивает недостающий доступ и автоматически публикует отчёт даже при блокере.

## Открытые границы

T03–T10 не объявляются закрытыми. Нет Lua stream detector, runtime cache, общего контроллера,
автоматического blockcheck2, C IPC/shared memory/QUIC CRYPTO, obfs endpoint. Для них заданы
конкретные этапы и испытания. Ни эффект clone, ни заявленные «5–8x»/«95%», ни причина прошлых
сбоев на ThinkCentre этим коммитом не доказаны. Рабочая машина разработчиком не изменялась.
