# ADR REC-C: владение поколением и cooperative fence

Статус03.11.2026: контракт и test-only candidate, **не установлен в XGW**.
REC-B принят по Y1440d51 в scope snapshot/check-only; manifest PLANNED_NOT_ARMED.
Реальные writer fence/recovery driver/active faults не реализованы и не разрешены этим ADR.

## 1. Ресурс, критическая секция и граница доверия

Test resource — маленькая synthetic generation record в ~/xgw-w3z/sandbox/case-NN.
Stable lock file отделён от атомарно заменяемого state.json. Пока writer держит lock,
он проверяет phase/generation и делает commit той же synthetic record **внутри той же
критической секции**. Получить permit, отпустить lock и затем записать вне секции нельзя.

Используется [fcntl.flock Python3.12](https://docs.python.org/3.12/library/fcntl.html).
[Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html) — advisory locking:
неучаствующий писатель может его игнорировать; он не даёт автоматического deadlock detection.
Это контракт cooperating actors, не защита от скомпрометированного root/того же UID.
Поведение в test filesystem не является аттестацией будущих runtime mount/namespace.

Lock UID/mode/nlink/inode проверяются, lock не заменяется обычным commit. Все
данные private0700/0600. В негативном случае заменяется только собственный synthetic lock;
чужие/product locks не открываются. Никаких /run/xgw, /etc/xgw, /var/lib/xgw или root snapshot
входов в этом кандидате нет.

## 2. Состояние и токен

Version1: epoch≥0, generation, phase(IDLE/ARMED/RUNNING), owner,
acquired_ns/deadline_ns. IDLE имеет owner/times=null. Epoch монотонно увеличивается
при каждом acquisition; retirement не возвращает старый номер. Token содержит точные
epoch+owner+generation. Старый, чужой, неполный или уже retired token не начинает job.

Acquisition только IDLE и с expected_generation=current. Длительность>0/≤45с,
clock int/nonnegative. Срок фиксируется; метода renew/heartbeat нет.
Begin_job требует ARMED, точный token и acquired_ns≤now<deadline. Сначала persist RUNNING,
потом будущий adapter мог бы начинать mutation. Поздний либо повторный job запрещён.
В Z эти события — только synthetic record updates, не мутации шлюза.

Writer разрешён только IDLE и с exact expected generation. Expiry не снимает fence:
при ARMED/RUNNING writer получает FENCED даже после deadline. Потеря OS lock при выходе
процесса и логический retirement lease — разные события. Сохранённая ARMED запись
после выхода владельца продолжает запрещать cooperating writers.

## 3. Retirement и результаты ошибки

- UNUSED допускается только ARMED: job ещё не был dispatched. Token атомарно retiring,
  поздний begin_job отвергается. Если другой actor успел persist RUNNING, UNUSED запрещён.
- RESTORED_ON допускается только RUNNING, с verified именно bool True и совпавшим
  observed_generation. В Z это явно synthetic verification, не проверка работающей сети.
- Ошибка/неизвестное/строка "true" не снимают fence. Настоящий verifier ещё не реализован.

Bounded lock acquisition использует LOCK_NB, budget150мс; истечение не разрешает ломать
чужой lock. Это bound попытки с обычным scheduler, а не45с сетевого восстановления.
Write/fsync/replace/fsync-directory выполняются под lock. При ошибке до replace старый
state сохраняется, незавершённый state.part блокирует повторный commit. После ошибки
после replace исход операции может быть UNKNOWN: нельзя автоматически повторить запись
или объявить отсутствие commit. Этот кандидат не реализует journal repair/power-loss recovery.

## 4. Что реально проверяет Z

Один batch/19 независимых сценариев, case failure не прекращает остальные.
Generation/owner/epoch/expiry/clock cases используют заданные synthetic times. Они
не измеряют15/45с recovery. Filesystem records и три process cases используют реальные
системные вызовы на ThinkCentre. Временный writer не имеет доступа к gateway API в коде.

Real-process cases:

1. Два процесса с expected g0: один COMMITTED, другой STALE_GENERATION; итог g1.
2. Собственный child удерживает только synthetic lock; parent получает LOCK_BUSY,
   завершает именно этот child и после закрытия fd выполняет synthetic writer.
3. Child сохраняет ARMED lease и выходит; следующий cooperating writer всё ещё FENCED.

Child argv только Python-I-B/этот же frozen source/_peer/sandboxcase/fixed mode.
_peer вручную запрещён. Child holder ждёт максимум3с release; parent budgetы2/4с,
cleanup terminate/kill только своих children. Это не service/guardian/autonomy proof.
Если общий controller timeout, нельзя объявлять все сценарии/отсутствие children успешными.

Все epoch/owner/generation/inode и sandbox data остаются private, source constants
synthetic. В report только fixed case IDs/bools/counts/child rc/fixed error enums.
runtime_writer_fence_installed/runtime_recovery_implemented/active_faults_authorized=false.

## 5. Будущая product integration: незакрытые задачи

Начальная инвентаризация дополняется host FreePool backend fp_peers writers, lifecycle
и путями удаления таблиц. Нужен полный call-site audit всех entry points, rollback,
API/config generation и background activity. Не заменять его поиском одной nft.apply.

Предлагаемый порядок для будущих adapters: top-level ownership admission → domain
apply/net/panel lock → validate current generation → bounded operation → durable generation
publication → release. Это **не доказанный порядок существующего графа**: реальные пути
уже могут держать apply.lock при входе в capture/net.lock. Вставка fence внутрь такого
пути без аудита создаёт риск ABBA. Нужен реальный dependency graph и отсутствие reverse
acquisition. Driver не должен ждать живой net.lock30с после fault.

До product patch остаются: полный call graph; failure/rollback publication; drainage
in-flight writers; stale owner/repair protocol; реальный verifier; bootstrap установки
без незастрахованного обрыва. Нельзя устанавливать adapter и проверять его на работающем
шлюзе без конкретного пакета с независимым исходным on возвратом.
Z не создаёт такой bootstrap и не переносит sandbox leases в product. Далее REC-D только
после решения этих вопросов; D1-on/real scoped faults/WAN/core faults не разрешены Z.
