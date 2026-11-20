# ThinkCentre · кто пишет конфиг Xray на работающем шлюзе (read-only) — 2026-11-20

- RESULT: **CORRELATED_ONLY** — в off/off окне 180с помощник `6eb92d1`
  (backend **inotify**) наблюдал **1 переход целевого файла** (`moved_to` =
  штатный atomic `os.replace`; inode и байты сменились; диффы секций:
  routing=2, inbounds=3, outbounds=9 ханков) и однозначно сопоставил его по
  времени (±10мс) с событием `apply` в state.db и журнале `xgw.service`
  («apply: замена участника … через API без перезапуска»), при этом за те же
  180с в журнале прошли цепочки **DEGRADED → rotation → apply → HEALTHY ×1**
  и вторая DEGRADED. Уровень PROCESS_CONFIRMED недостижим: **audit-инструменты
  отсутствуют на хосте (ausearch/auditctl → rc=127)** — SYSCALL/PATH-связка
  невозможна, существующих audit-правил нет. Итог класса: применитель —
  демон XGW (correlated), процесс на уровне syscall — UNKNOWN.
- HTTPS контроль через штатный Xray (http-in): 200 до и после; режим off/off
  в обеих точках; settings sha256 неизменны (settings_rc=0); VPN жив.
- SHA помощника: `6eb92d1f3ebe2efdf6960bc84332e6f54aa096c9`; наблюдение
  180с (181 чтение, 9 heartbeats, batches_with_multiple_events=0 —
  ни одного пропуска очереди), watchdog-фазы sleep/tick в норме
  (возраст ≤17с), измерение ~21:17–21:21 UTC+3, публикация сразу после.

## Событие (агрегаты; сырые данные остаются на машине)

| Поле | Значение |
| --- | --- |
| backend | inotify (poll не потребовался) |
| файл-события / версии | 1 / 1 (moved_to, inode+bytes changed) |
| секции диффа (ханки) | routing 2, inbounds 3, outbounds 9 |
| DB events в окне | DEGRADED → rotation → **apply** → HEALTHY (+ вторая DEGRADED в хвосте окна) |
| корреляция | sample 764.732 ≈ apply 764.742 (Δ≈10мс); journal «замена участника: proxy-de-… → запасной (CONNECT_FAIL)» |
| audit | rc=127 — инструменты отсутствуют; покрытие SYSCALL недоступно в Read-Only |

## Ретроспектива CDN r2 (до 60с, по ТЗ §2.4)

- Полные критерии запроса (rule=true на границах + diff={routing,inbounds,
  outbounds} + ≤300с) не удовлетворила **ни одна** из 9 сохранённых пар:
  пары с секциями (CDN r2 `flow-r2b`, writers r3 `writer-media`) имеют
  `client_zapret2_rule=false` на обеих границах при формально active
  Selective — отдельный наблюдательный факт, вынесен для будущей проверки.
- Смягчённый запрос по окну `flow-r2b` (epoch совпадает, секции = три
  целевых, 141.6с): журнал жив (не ротирован), в окне **4 apply-события**:
  «zapret2: маршрут» ×2 с периодом ~26–50с (периодический re-apply
  маршрута), «профиль обхода» (rmo+ado: spare-ru), «rotation: замена
  участников» + «apply: замена участника» на 131-й секунде окна. Ретро-
  атрибуция ограничена (без audit того времени) — как и ожидает ТЗ.

## Сопоставление с r3 (установка)

Независимое read-only наблюдение подтверждает вывод r3: записи конфига
Xray на этом шлюзе производит демон XGW (источник `daemon_rebuild`/маршрут)
через штатный atomic replace, синхронно с циклом health-check/rotation
участников VPN и периодическим re-apply маршрута zapret2. Два прохода,
два метода (inotify+audit-ladder против journalctl по границам снимков) —
один вывод.

## Ограничения

- PROCESS_CONFIRMED не достигнут (нет audit) — если потребуется syscall-
  уровень, это отдельный Mutating-проход с transient-правилом audit
  (§2.4 лестницы), с учётом 32-битных процессов как пробела покрытия.
- Окно 180с в off/off не закрывает вопрос о частоте записей в Selective.
- Пары с rule=false на границах при active Selective — приоритет для
  следующей проверки (возможно, route_evidence кандидатов считает правило
  по live-конфигу после rebuild — сверить с nft на границах).
- Publication commit: `79145d2d600059a6468846b2a666615ce4600e13` (360e1a0 → 79145d2, ancestor verified).
