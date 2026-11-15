# Реальная машина: дополнения zapret2, r1 — YYYY-MM-DD

## Происхождение и состояние

- BASE / CODE / delivery TIP / hotfix commits:
- Ubuntu (ID/VERSION_ID), kernel/nft/curl/browser, bundle/Lua SHA:
- Исходные и конечные mode/engine, daemon/core/worker PID:
- GUI sort acceptance: report/hash или NOT_RUN:
- Бюджет времени/трафика: planned / actual / limit reached:
- Кто выполнил команды и vision; запрошенный доступ и блокеры:

## Условия и измерения

Публично только обезличенные context/target IDs и метрики. Не вставлять signed URL, IP,
конфиги/подписки, полный argv с пользовательскими данными, HAR или pcap.

| UTC / окно / пара | Кандидат / family | client / protocol / context / target ID | Direct path / NFQ доказан | bytes / seconds / max gap | probe verdict | Browser | valid / причина invalid |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Для каждого из двух окон: CD, DC; win/loss/both-pass/both-fail; результаты A0/A1/B/V.
Отдельно: URL свежий и для правильного выхода? Один IP/клиент внутри пары? Настоящий новый
поток? Clone реально вызван? Не сменились offload/протокол/маршрут/правила/версия?
Является ли curl-impersonate совместимым клиентом с подтверждёнными хэшами?

## Покрытие гипотез

Не заменять NOT_IMPLEMENTED словом FAIL. Формулировки из ROADMAP.

| ID | Что реально реализовано/запущено | Результат / сырые агрегаты / ограничение | Вывод / следующий тикет |
|---|---|---|---|
| H01 stream watchdog | Сейчас активная probe; Lua detector отсутствует | | T05/T07 |
| H02 composite key | Exact/prefix context в журнале; runtime key ещё нет | | T07/T08 |
| H03 persistence | История probe / shortlist, не automate_host_record | | T07/T08 |
| H04 autottl cache | NOT_IMPLEMENTED | | T05/T07 |
| H05 clone | Static/clone matched pair; KeyShare не портится | | T06/T07 |
| H06 IPC | NOT_IMPLEMENTED | | T03/T08 |
| H07 shared memory | NOT_IMPLEMENTED | | T03/T05/T08 |
| H08 route fallback events | NOT_IMPLEMENTED | | T03/T04/T08 |
| H09 tournament | NOT_IMPLEMENTED; shortlist не tournament | | T09 |
| H10 stream/client probes | 45s + compatible curl + real browser | | T09/T12 |
| H11 QUIC CRYPTO | NOT_IMPLEMENTED | | T06/T09 |
| H12 obfs | NOT_IMPLEMENTED / external endpoint dependency | | T04/T06 |

## Flowseal / упаковка

- Generator reproducible, 22 parse checks, 22 lua-init checks:
- HTTP/TLS branch match / scope positive replacement / excludes live:
- Старый vs новый launcher, пары ALT9 и general/SIMPLE FAKE:
- Source/adapted/SYN limitations; ничего не «проверено» только по отсутствию ошибки:
- dry-run / intercept=0 / packet handler: три раздельных результата:

## Видео

Публичный video ID, кодек, выбранная и фактическая resolution, 15+5 отдельно по финалисту,
время старта, минутные наблюдения vision, pause/seek/late stall и их причина либо UNKNOWN.
HTTP=PASS / STREAM=PASS / PLAYBACK=FAIL считать отдельным важным результатом.

## Итог и возврат

- Какие изменения дали измеримый эффект; какие не дали; что неизвестно:
- Условия, sample size, invalid observations, ограничения независимости пар:
- Политика/маршрут восстановлены, хэши совпали, offload/acct вернулись:
- Только свои trace-объекты удалены; очередь свободна; timer/service stopped:
- GUI/API/HTTPS после возврата:
- Хотфиксы, повторённые тесты, что осталось установленным:
- Следующий основной этап **T03** и влияющие на него выводы:
- Publication commit (добавить в итоговое сообщение после push):
