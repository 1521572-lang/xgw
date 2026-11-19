# Ubuntu 24.04 — admission: бюджет, матрица 18, видео — частичный PASS — 2026-11-19

- RESULT: **TESTS PASS (обязательный 242+10+6 при resumed-коде `08d31ee`, включая
  исправленный TUN-marking тест; BROAD BASELINE_MATCH ok=true — 14 отказов среды с
  теми же сообщениями), INSTALL PASS (11/11 файлов с xgw-net.service
  обновлением правил, network-after: capture=on, loaded=true, acct=0, engine_queue
  отсутствует, expected_close=false — off/off корректен), LOW_BUDGET PASS (главный
  дефект закрыт: при лимите 1 МиБ remaining=0 → UI-блокер в обоих API, прямой POST
  mode → code=probe_budget, job/start → blocked rc=2, воркеры inactive, spent не
  вырос), MATRIX PASS (18/18 строк, complete/restore=pass: fallback 1 + timeout 3 +
  **active 14** — 7 профилей с 2 pass), JOB01/03 регрессия PASS (cancelled/interrupted,
  restore=pass), видео LONG/SEEK NOT_CONFIRMED (две сборки playwright: 1010 и 785
  с — eligible 22.9 и 79.9 с из 900: плеер останавливался «Что-то пошло не так» при
  деградации линии; старые samples отсутствуют), DAY NOT_COMPLETED (наблюдение
  остановлено владельцем на 18.51 ч: off 22685 с / standalone 43745 с, gaps 0,
  api_errors 1, UTC-пара 1), M3_TRAFFIC=NOT_RUN, VPN_RETURN/RESTORE PASS (accept
  11/11, restore-completed, off/off, воркеры inactive, VPN 200)**.
- CODE: `08d31ee…` (resumed, включает TUN-fix тест); OLD-база `3630b44…`; пакет
  установки 11 файлов (zapret2, control, panel, management, jobs, daemon, client,
  profiles, nft, sysctl, nfqws2) — принят и оставлен; конфиги byte-identical
  (восстановлены побайтово), restore-completed присутствует.
- Машина: off/off, воркеры inactive, VPN/panel 200, диск 40 ГБ. Тестовые браузеры
  закрыты. Суточный off-монитор прежний остановлен владельцем на 18.51 ч
  (NOT_COMPLETED), новый суточный Selective не назначался (§7 требует подтверждённого
  §6 — видео NOT_CONFIRMED). Приватные артефакты — в каталоге опыта 0700.

## Прогон §2

| Набор | Результат |
| --- | --- |
| core | 242 passed |
| api (-k zapret2) | 10 passed |
| network-contracts (6, включая исправленный marking_chain) | 6 passed |
| BROAD NEW vs OLD `3630b44` | 354/353 passed; гейт ok=true: 14 matching failures, новых/изменённых нет |

## §3 INSTALL 11/11 — PASS

prepare/apply complete; xgw-net.service обновил правила: network-after.json —
capture=on, loaded=true, has_close=false == expected_close=false (off/off, TUN
не активен), has_engine=false, acct=0. Конфиги byte-identical. CLI status
работает. VPN-сеанс свежий — 200.

## §4 LOW_BUDGET — PASS (дефект закрыт)

| Шаг | Наблюдение |
| --- | --- |
| Нормальная попытка (512 МиБ) | job complete, timeout/trial_timeout 95.5 с (новая механика), restore=pass, spent ровно 1 МиБ, off/off |
| Лимит 1 МиБ | remaining=0 → блокер «Недостаточно остатка для прямых проб и контрольной проверки VPN» в **обоих API**, воркеры inactive |
| Прямой POST mode=selective | `code=probe_budget` — «Для запуска не хватает бюджета прямых проб и резерва VPN либо учёт бюджета недоступен.» |
| job/start | `code=blocked` rc=2 — «Проверьте готовность Selective и бюджет.» |
| Проверка расхода | spent=1048576 не изменился; новый probe-inbound/client-rule отсутствуют; опрос 60 с чистый |
| Возврат 512 МиБ | saved; spent не сброшен (1 МиБ остаётся); нормальная попытка снова разрешена |

## §5 МАТРИЦА 9×2 — PASS (18/18, complete/restore=pass)

| Кандидат | r1 | r2 |
| --- | --- | --- |
| multisplit | fallback / youtube_cdn_probe_failed (83.3 с) | timeout / trial_timeout (95.5 с — отдельный job §4.1) |
| multidisorder | **active / youtube_transport_ok** (84.6 с) | **active** (91.7 с) |
| fake_md5_split | **active** (82.4 с) | **active** (86.9 с) |
| fake_seq | **active** (91.5 с) | **active** (88.6 с) |
| fake_seq_split | **active** (91.7 с) | timeout (95.4 с) |
| fake_md5 | **active** (82.3 с) | **active** (90.5 с) |
| hostfakesplit_md5 | timeout (95.7 с) | **active** (86.7 с) |
| fake_static_md5 | **active** (85.9 с) | **active** (85.8 с) |
| fake_clone_md5 | **active** (87.6 с) | timeout (95.3 с) |

- Обратный порядок круга 2 соблюдён; таймауты дают строку timeout/trial_timeout,
  подтверждённый off и следующий профиль — новая механика `46c69fd` работает.
- **7 профилей с двумя pass** (multidisorder, fake_md5_split, fake_seq, fake_md5,
  fake_static_md5 + hostfakesplit_md5 r2-active, fake_md5_split) — TLS-деградация
  линии преодолима другим профилем: гипотеза «CDN недоступен всем» опровергнута.
- JOB-регрессия: cancel → cancelled/restore=pass; restart xgw → interrupted/
  restore=pass; off/off; VPN 200.
- pin/reset: pin fake_md5 → saved (selected=fake_md5, mode=off, ревизия сменилась);
  reset → saved (selected=multisplit); только стратегия меняется.
- monitor matrix-full.jsonl — 118 строк агрегатов (приватно).

## §6 ВИДЕО — NOT_CONFIRMED (две сборки)

| Сборка | wall | eligible | причина |
| --- | --- | --- | --- |
| admission-1 (ad-hoc play) | 1019.1 с | 115.8 с | плеер остановлен скрытием окна (ZCode перекрыл) |
| admission-2 (`watch2`, playwright) | 1019.4 с | 22.9 с | видео не запущено (клик до ready) |
| admission-3 (`watch3`, playwright + F5/k) | 794.2 с | 79.9 с | «Что-то пошло не так» — line media stalls |

- Старые samples отсутствуют → прежнее «15+5» = **NOT_CONFIRMED** (как требовало
  ТЗ; числа 59/59 и 19/20 сами по себе не подтверждают 900/300 с).
- Прогресс/720p-фрагменты в фрагментах играли (720p ratio 1.0 в watch3, media
  bytes 17.2 МБ), но 900/300 с пригодных не набрано из-за остановок плеера.
- Причина остановок — деградация линии на media-стримах (консистентно с TLS-
  деградацией CDN в этих же окнах); различие клиента/пути — гипотеза для Codex.
- route_verdict=UNKNOWN — маршрут доказывается отдельно; Selective-active строки
  матрицы показывают transport_ok на 7 профилях, но длительной передачи не было.

## §7 DAY_SELECTIVE — NOT_RUN

Требует подтверждённого §6; видео NOT_CONFIRMED → новые сутки Selective не
назначались (по ТЗ).

## §8 RESTORE — PASS

- Отмена/выключение перед возвратом: off/off; RESULT_MODE=accept;
  restore-completed present; check_installed 11/11; конфиги byte-identical;
  расход дня (1 МиБ) сохранён; таймер admission погашен (rollback отработал
  раньше по 240-мин лимиту — файлы не откатились: accept поверх, что подтверждено
  cmp 11/11). Старые таймеры (combined-day-rollback, combined jobs) погашены ранее.
- Финал: off/off, воркеры inactive, VPN 200, panel 200, диск 40 ГБ, установленный
  слой `08d31ee` (11 файлов) оставлен. Тестовые браузеры закрыты.

## Наблюдения для Codex

1. **Матрица на деградирующей линии дала ключевой положительный результат**:
   7 из 9 профилей способны пройти HTTPS-пробу и активироваться при том же
   CDN/окне, где multisplit и hostfakesplit деградируют — «CDN недоступен всем»
   опровергнуто; автоперебор профилей (jobs) подтверждён как рабочий механизм.
2. LOW_BUDGET-контракт закрыт полностью: UI-блокер, probe_budget на прямом POST,
   blocked на job — с неизменными policy/spent/PID.
3. timeout/trial_timeout механика: строка + подтверждённый off + следующий
   кандидат — работает как спроектировано (3 таймаута в матрице).
4. Прибор playback: для линий с нестабильной доставкой нужен retry-режим
   плеера/верификации (остановки «Что-то пошло не так» после ~2 мин) — иначе
   eligible падает из-за внешних остановок, не застрахованных сборщиком.
5. Суточный off-монитор 18.51 ч: NOT_COMPLETED по вине расписания (остановлен
   владельцем для продолжения приёмки); интервалы и UTC-пара сохранены в
   previous-day-summary.json.
- Publication commit: `добавляется после push`.
