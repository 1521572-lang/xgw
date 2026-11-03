# ADR REC-C: краткий registry lock и ticket на весь writer

Статус03.11.2026: design + test-only candidate AA. Не product implementation.
Z19/19 принят, но его Store.writer меняет только одну syntheticrecord под flock.
Расширение такой секции на systemctlrestart создаёт cross-process dependency, описанную
в [аудите](REC-C-CALLSITES-AND-BOOTSTRAP.md). AA проверяет другую границу admission.

## 1. Решение и отказ от механической обёртки

Registry flock удерживается только при чтении/изменении ownership state и списка tickets.
Операция writer выполняется после отпускания flock, но пока её durable ticket существует.
Lease acquire под тем же flock требует пустой список tickets и IDLE ownership; затем
атомарно сохраняет ARMED. Все дальнейшие cooperating admissions видят FENCED.
Значит permit не потерян: lifetime защищает ticket, а не свободный OSlock.

Если tickets непусты, acquire сразу возвращает WRITERS_IN_FLIGHT. Он **не** выставляет
PENDING и не ждёт освобождения net/apply/panel locks. Уже работающий parent может
допустить childhook, закончить свой servicejob и закрыть ticket. Нет гарантии fairness:
при постоянном потоке writers arming может быть недоступен; fault тогда NOT_RUN.
До ARMED нет обещания45с. Обычные задачи нельзя останавливать ради окна для эксперимента.

Этот протокол не разрешает реальные callbacks/внешние writers игнорировать admission.
Advisory trust boundary прежняя. Прямой root/editor/внешний systemctl вне инструментированных
entrypoints не становится автоматически fenced. Все реальные gates остаются false.

## 2. Сохраняемый учёт и публикация

В AA отдельно stableZlock/state.json и tickets.json(version1,serial,tickets).
Ticket={id,role,phase}; id уникален в одном registry, role из fixedsyntheticallowlist,
phase LIVE/COMMITTING/UNKNOWN. Токен{id,role} должен точно совпасть. Это идентичность
testoperation, не аутентификация непривилегированного клиента. Нет PID-based pruning.

Порядок успешного completion под registrylock:

1. Точный LIVEticket + verified именно boolTrue + stateIDLE.
2. Сохранить COMMITTING. Дублированный completion уже не допускается.
3. Durable publication следующего syntheticgeneration.
4. Durable removal ticket. Только теперь acquisition может увидеть пустой registry.

Любой crash между шагами оставляет ticket либо уже совершённое полноценное завершение.
При ошибке generationpublication ticketCOMMITTING остаётся. При публикации g1 и ошибке
cleanup g1 уже возможен/записан, но lease запрещён. Повтор completion не увеличивает
поколение второй раз. Двухфайловой атомарной транзакции нет; safety достигается
консервативным запретом при промежуточном состоянии, не автоматическим repair.

Mutation/verifier error → best-effort UNKNOWN, но и оставшийся LIVE/COMMITTING блокирует
lease. UNKNOWN/COMMITTING блокируют новые обычные admissions. Если процесс умер с LIVE,
AA не определяет это по PID/clock и не снимает запись: lease остаётся запрещённым;
другие LIVE admissions ещё могут проходить. Это admission candidate, не liveness/crash
recovery. Сетевая работа в AA вообще не выполняется.

Publication-before-remove сохраняется и при callbacks, которые ничего не изменили:
AA консервативно увеличивает поколение. Productadapter должен различать истинный noop,
pendingcleanup и неизвестный частичный apply. Outcome(mode="unchanged") нельзя использовать
как универсальное доказательство no-write: SB удаляет pending даже в этой ветви.

## 3. Почему это снимает найденную зависимость только в модели

Parent ticket CORE остаётся LIVE; его registryflock уже освобождён. Child TUN_HOOK получает
свой ticket, выполняет syntheticcompletion и выходит. Попытка recovery между ними
получает WRITERS_IN_FLIGHT. Parent публикует своё поколение и удаляет ticket; только
теперь новый snapshot/arming может продолжиться. Child не обходит fence по root/envtoken.

В настоящем XGW hook может ждать net.lock, другие callbacks — apply.lock, и отдельные
job могут длиться дольше45с. AA не доказывает отсутствие существующих domain-level
циклов и не требует driver ждать их после fault. Полный registry→domain→registry lockgraph
нельзя трактовать как вложенный: domain→registry completion допустим лишь если никакой
registrycriticalsection не ждёт domain/process. Это инвариант будущей реализации.

## 4. Что AA проверяет и что ещё нужно

22 новых cases проверяют drainbeforearm, отказ lease внутри callback, reentrant lifecycle
child без PENDING, неизвестный результат, строгую verification, publication/cleanup failures,
дублированные/чужие tickets и отсутствие orphanpruning. Три childprocesscases выполняются
обычным UID в ~/xgw-w3aa. Fullbatch локально NOT_RUN, mainvalidation — FlashThinkCentre.
Реальные operations заменены callbackзаглушками; leaseclock synthetic. Нет измеренных
45с, systemdexperience, восстановления nft, install/arm/fault.

Следующие атомарные implementationtasks после AA:

- C-REG: отдельный product registry с bootidentity, fixedpaths/DAC, bounds, journalrepair
  и auditfailclosed. Никогда не переносить AArecords в /run/xgw.
- C-ENTRY: инструментировать конкретные top-level writers по матрице аудита; lowerlayers
  получают контекст/ticket, а не повторно захватывают долгий flock. Перед touch/unlink,
  backendpreparecleanup и api.pin тоже admission. Не подавлять отказ как успех.
- C-VERIFY: receipt для noop/success/rollback/failed/UNKNOWN. Verifier реальной generation
  включает kernel+files+API/process dependencies; одного digest недостаточно.
- C-BOOT: отдельно решить versionhandshake всех entrypoints и безопасную активацию;
  старый daemon с новым CLI не считается fenced. Ни один из этих патчей не устанавливать
  до независимого исходного onвозврата и отдельного ТЗ.

REC-D/E пока закрыты. Writerfenceinstalled/recoveryimplemented/activefaultsauthorized=false.
