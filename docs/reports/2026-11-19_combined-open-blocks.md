# Ubuntu 24.04 — единая приёмка открытых блоков XGW (3630b44) — 2026-11-19

- RESULT: **TESTS PASS (обязательный набор 199 passed — patch4/Flowseal-контракт
  исправлен; расширенный BROAD — BASELINE_MATCH ok=true: 14 отказов среды с теми же
  сообщениями на OLD `3d117b1`, без новых/исчезнувших/изменившихся), INSTALL PASS
  (8/8 файлов, таймер 240 мин), UI/JOB блоки PASS (UI01/02/03/07/08 подтверждены
  живыми проверками; UI04 — PASS со ссылкой на принятый probe-watch прогон, тестовый
  Chrome терял панельную сессию — парольное восстановление недоступно без владельца;
  UI06 NOT_RUN — рабочий сервер владельца не менялся), JOB01–JOB05 PASS
  (cancelled/restoring/interrupted/busy/права 0700-0600, restore=pass во всех),
  A/B/B/A PASS-механика (4 строки complete/restore=pass: подписанный и без подписи
  CDN дают одинаковый fallback TLS на том же authority — подпись не причина отказа),
  матрица 18 NOT_RUN (пригодной пары нет — обе ветки TLS-деградация), Flowseal PASS
  (PINNED_ASSETS_OK, import saved, Selective отклонён «requires Standalone»),
  Standalone PASS (4/4 пар 100 % usable 720p: multisplit и ALT9 паритет; 15+5 лучшего
  — 59/59 + 19/20 usable), SIGKILL_STANDALONE PASS (fail-closed: blocked/worker_down,
  воркер не поднялся, VPN сам не включился), малый бюджет — **дефект-наблюдение**:
  UI-блокер при remaining<786432 не показан при старте (blockers пусты, воркер
  поднялся в preparing; spent не вырос; фактический stop происходит на пробе),
  UTC_ROLLOVER NOT_RUN вживую (часовая фикстура PASS), DAY=RUNNING (26h rollback
  таймер + user-монитор xgw-combined-monitor-1795041850 активны, day.jsonl пишется),
  M3: pool stats/diag сняты (до/после), реального трафика пула в окне не было →
  M3_TRAFFIC=NOT_RUN, VPN_RETURN/RESTORE PASS (accept, restore-completed,
  check_installed 8/8 — слой `3630b44` оставлен)**.
- CODE: `3630b44502b872ca3788e0824c6a9d0d8363b561`; OLD-база `3d117b1…`; GUI-релиз
  `7c20f590…`; Ubuntu 24.04.5 LTS; Qt 6.4.2 / PyQt6 6.6.1 / Python 3.12.3.
- Тесты §2: обязательный набор — **199 passed** (test_desync_jobs 208 строк новых,
  test_acceptance_gate, test_zapret2_management с исправленным Flowseal-контрактом —
  patch4/`strategy=flowseal_alt9` больше не сохраняется ручным settings-запросом);
  расширенный — 374 passed + 14 baseline-failures (гейт: matching_baseline_failures
  14, added/missing/changed/new_failures/new_skips — все пустые); api-tests 9 passed.
- Установка: cmp zapret2.py/flowseal.py/zapret2_control.py с OLD — OK; 7 CORE +
  gui/zapret2.py применены, конфиги byte-identical до/после, CLI
  `xgw.desync.client status` без sudo — PASS (тот же сохранённый сеанс).
- Живой CDN-URL, IP, hostname — только в приватном каталоге опыта (0700).

## Проверки

| ID | Результат | Наблюдение |
| --- | --- | --- |
| UI01 | PASS | новые кнопки на карточке: «Сохранить CDN-пробу без подписи», «Подготовить проверенный Flowseal ALT9», «Проверить девять стратегий», «Отменить и вернуть настройки», «Сохранить/Вернуть профиль» |
| UI02 | PASS | /api/state и /api/zapret2/overview: mode/config_key/budget/job.state=idle идентичны |
| UI03 | PASS | stale-правка (expected старой ревизии) → `conflict` «Настройки изменены в другом окне. Перечитайте…», не перезаписывает B; актуальная сохраняет |
| UI04 | PASS* | поведение poll/resume принято в probe-watch прогоне (5/5); в этом проходе тестовый Chrome потерял панельную сессию (парольное восстановление — владельческая сессия), политика не менялась (panel.json sha стабилен) |
| UI05 | PASS | сортировка принята в selective-status прогоне (стабильные границы) |
| UI06 | NOT_RUN | рабочий сервер владельца не менялся (риск нарушения рабочего маршрута); hover/анимация — прошлые приёмки |
| UI07 | PASS | 403 «Запрос не со страницы панели» без header; invalid-тело не меняет политику; signed URL/cookie в публичном выводе отсутствуют |
| UI08 | PASS | «desync: Flowseal ALT9 requires Standalone and YouTube domains» при попытке Selective с ALT9; политика сохранена off; engine=auto — только фикстуры |
| JOB01 | PASS | немедленная отмена: job=cancelled, restore=pass, off/off, воркеры inactive, VPN 200; отмена после preparing: restoring → cancelled |
| JOB02 | PASS | UI закрыт 30 с: job продолжал running, после возврата тот же id `975e0644` и results; final complete с result-строкой (fallback/youtube_page_probe_failed, 71.6 с) |
| JOB03 | PASS | restart xgw.service во время preparing: job=interrupted, restore=pass, off/off, воркеры остановлены |
| JOB04 | PASS | второй старт → `busy` «Дождитесь возврата текущего задания»; нет второго runner |
| JOB05 | PASS | /var/lib/xgw/desync-jobs: каталог 0700 root, job.json/cancel/lock 0600 root; GET job — только whitelist (id/state/started/finished/candidates/rounds/results/restore/budget_seconds); original политики в GET отсутствует |
| A/B/B/A | PASS (механика) | 4 строки complete, restore=pass: A1 fallback/CDN-TLS 83.1 с; B1 90.6 с; B2 81.1 с; A2 72.4 с — **подписанный и без подписи дают одинаковый TLS-отказ на том же authority** |
| Матрица 18 | NOT_RUN | пригодной пары нет (обе ветки — TLS-деградация прямого канала к googlevideo); запуск не имел смысла — «На пригодной паре проб» |
| pin/reset | NOT_RUN | нет профиля с двумя HTTPS pass |
| Flowseal | PASS | PINNED_ASSETS_OK; import-flowseal saved (e6b5a17a, ALT9+6 доменов, gate off, off); Selective отклонён; импорт из UI-кнопки проверен CLI-эквивалентом |
| Standalone | PASS | 4/4 пар: multisplit-a 12/12, alt9-a 12/12, alt9-b 11/11, multisplit-b 11/11 usable 720p (1280×720, 0 пауз); worker/queue 200/nft-правило/остальное напрямую |
| 15+5 лучшего | PASS | multisplit: 59/59 usable 720p (0 пауз, буфер 35–79 с, vp 3→53); seek +400 с: 19/20 usable (восстановление после перемотки) |
| SIGKILL_STANDALONE | PASS | SIGKILL main → blocked/worker_down, MainPID=0, воркер сам не поднялся, VPN сам не включился; off вернул штатный VPN |
| Бюджет-регрессия | **Дефект-наблюдение** | лимит 27 МиБ при spent 26.7 МиБ (remaining 262144): mode-selective старт НЕ заблокирован (blockers пусты, воркер поднялся в preparing/unconfirmed); spent не вырос; фактический стоп — на пробе (как в принятом budget-проходе). Job/start дал отказ другого рода («Выключите оба режима») |
| UTC_ROLLOVER | NOT_RUN (вживую) | граница не наступила в окне; фикстура exhausted_budget — PASS в §1 |
| DAY | RUNNING | 26h rollback-таймер активен; user-монитор xgw-combined-monitor-1795041850 (RuntimeMaxSec 25h, day.jsonl 0600, whitelist-агрегаты); на момент публикации elapsed ~1 ч, инцидентов нет; команда пост-обработки: `python3 -m xgw.desync.client analyze $D/day.jsonl` |
| M3 | PARTIAL/NOT_RUN | pool stats/diag сняты до/после (файлы в $D); реального трафика пула в окне не было → M3_TRAFFIC=NOT_RUN; R32/R35 не объявляются |
| VPN_RETURN | PASS | restore accept → новый YouTube-сеанс через VPN (fsess 30 c, 1500 кадров), ipify 200 |
| RESTORE | PASS | accept: restore-completed, конфиги OK/OK byte-identical, check_installed 8/8 — слой `3630b44` оставлен |

## Финал

off/off, воркеры inactive, xgw/xray active, VPN/panel 200, nfnetlink_queue пуст,
конфиги `89bf2a67…`/`33916cb5…` byte-identical (восстановлены побайтово), spent дня
(28 МиБ) сохранён, лимит 256 МиБ, диск 42 ГБ; активны только: 26h rollback-таймер
(автовозврат) и суточный user-монитор (чтение API). Тестовые Chrome закрыты. Установленный
слой: `3630b44` (7 CORE + gui/zapret2.py). IPv6 WAN — NOT_APPLICABLE_ON_THIS_HOST.

## Наблюдения для Codex

1. **Дефект UI-блокера малого бюджета**: blockers.selective пуст при remaining
   (262144) < 786432; mode=selective сохранился и воркер поднялся в preparing.
   Контракт бюджет-ТЗ §5.1 («панель показывает блокер Selective») не выполняется на
   старте; стоп происходит при списании пробы. Дефект не блокирует день (лимит
   восстановлен), но старт с заведомо нехватающим бюджетом должен отклоняться до
   подъёма воркера.
2. **flowseal_alt9-контракт исправлен корректно**: ручной settings-запрос отклоняет
   стратегию, импорт — единственный путь (тест patch4 и UI08 подтверждены).
3. **A/B/B/A закрыл гипотезу подписи**: без подписи (/generate_204 of the same
   authority) TLS-отказ идентичен подписанному — служебная проверка не зависит от
   подписи; прямой канал к googlevideo деградирует независимо. Матрица стратегий
   имеет смысл только при восстановлении прямого TLS.
4. **Суточная фаза продолжается автономно**: unit читает только API (без проб),
   rollback-таймер вернёт конфиги в 04:1x+26h; день стартует с off/off — SELECTIVE_DAY
   останется NOT_RUN, но UTC-переход и стабильность VPN будут измерены в day.jsonl.
- Publication commit: `добавляется после push` (отчёт в чистом checkout поверх 3c0b592).
