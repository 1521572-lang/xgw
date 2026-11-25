# ThinkCentre · результат прямого CDN и выключение Standalone — 2026-11-25

- RESULT: **ЖИВОЙ ПРОХОД ВЫПОЛНЕН ЦЕЛИКОМ, КОД 0, НО ПАРА НЕ
  ПОДТВЕРЖДЕНА: ПРЯМОЕ ПЛЕЧО — TLS-ТАЙМАУТ (10,0 С, SERVERHELLO 0) С
  ТОЧНОЙ СИГНАТУРОЙ RETRANSMIT_WITHOUT_PAYLOAD_ACK (26 ОТСЧЁТОВ,
  3 619 ОТПРАВЛЕНО, 3 102 РЕТРАНСЛЯЦИИ, 1 БАЙТ ACK, 0 ПРИНЯТО, ПЕРВАЯ
  РЕТРАНСЛЯЦИЯ 644 МС) — КАК 2026-11-24; ПРОШЛОПРОХОДНЫЙ 302 ОКАЗАЛСЯ
  РАЗОВЫМ. НОВОЕ РАБОТАЕТ: DIRECT-VERDICT СОХРАНЁН ДО ВЫКЛЮЧЕНИЯ —
  МАРШРУТ ПРЯМОГО ПЛЕЧА ПОДТВЕРЖДЁН (В ПРОШЛОМ ПРОХОДЕ ЕГО НЕ БЫЛО),
  СВОДКА ОЧЕРЕДИ ОПУБЛИКОВАНА: OBSERVED, 9 НАЗНАЧЕННЫХ ID,
  0 ПЕРЕПОЛНЕНИЙ, 0 NETLINK, ДОЛЯ 0,0 ЗА 11,407 С. ВЫКЛЮЧЕНИЕ
  STANDALONE НА ЭТОТ РАЗ ШТАТНОЕ (OFF_DEADLINE НЕ ПОВТОРИЛСЯ), ВОЗВРАТ
  COMMITTED: SLOT=BLUE MODE=API, ВОЗВРАТ АТРИБУТИРОВАН; ОТКАТ: ФАЙЛЫ
  И ХЭШИ СОВПАЛИ, VPN 200. ВЕРДИКТ ПАРЫ RANGE_UNCONFIRMED (ПРЯМОЙ
  ДИАПАЗОН НЕ ПОДТВЕРЖДЁН, VPN-ПЛЕЧО 206/65 536). ДОПОЛНЕНИЕ FLASH:
  ПЕРЕД ПРОХОДОМ СНЯТ УСТАРЕВШИЙ ФЛАГ resume_managed ИЗ RUNTIME-
  СОСТОЯНИЯ (СЛЕД ПРЕДЫДУЩЕГО СБОЯ, УСТАНОВЛЕННЫЙ КОД ЕГО НЕ ЗНАЕТ);
  ЗАКРЕПЛЁННЫЙ БЛОК НЕ МЕНЯЛСЯ.**
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43-generic; Python 3.12.3,
  pytest 7.4.4 системные; кандидат `7b4ea22…` (приём `f7241f7…`,
  предок подтверждён; закреплён как предок). Окно Standalone
  согласовано; ролик штатный.

## §1 CONTRACTS — 83 passed (2,6 с), 0 failed / 0 skipped

| Проверка | Что подтверждает |
| --- | --- |
| `test_direct_report_preserves_redirect_and_tcp_without_a_vpn_sample` | отчёт прямого плеча сохраняет 302 и TCP без VPN-отсчёта |
| `test_off_snapshot_separates_worker_stop_from_pending_vpn_config` | различение `stop_failed` и `vpn_requested` в снимке выключения |
| `test_off_snapshot_handles_stale_legacy_and_unrecognized_fields` | устаревший статус, legacy и незнакомые поля не ломают снимок |
| `test_only_counters_bracketing_the_direct_probe_are_reported` | счётчики только в окне прямого запроса |
| `test_standalone_exit_evidence` | диагностика выхода собирается в предписанном виде |
| пара/очередь/TCP/допуск | прежние проверки прошли |

## §2 ARCHIVE — пересчёт прежнего опыта, код 0

- `evaluate-direct` по прежним артефактам: **direct_observed,
  http_redirect (302)**, `direct_range_verified=false`.
- `direct-route.out` в прежнем опыте отсутствовал — **привязка
  маршрута остаётся неподтверждённой**, TCP и сводка очереди
  деградировали до `path_unconfirmed` (в новом проходе это закрыто).

## §3 LIVE — шаги и исходы

| Этап | Исход |
| --- | --- |
| База: off, топология, VPN, resolve | все код 0 |
| VPN-подготовка | `vpn_range_verified` 206/65 536, `content_range_ok`, TLS 1/1/0 |
| Временная установка кандидата | stage/apply/candidate-* — код 0 |
| Standalone | поднят, пауза подтверждена, ревизия confirmed |
| Страница по прямому пути | 200, TLS ok |
| **Прямой CDN** | код 2, **tls_timeout** (10,0 с, rc 28, ServerHello 0, alert 0) |
| Прямой маршрут | **verified** (впервые в артефактах живого прохода) |
| **direct-verdict** | сохранён до выключения — код 0 |
| **Выключение Standalone** | **код 0** (штатное, off_deadline не повторился) |
| VPN-плечо | `range_complete` 206/65 536, `content_range_ok`, TLS 1/1/0 |
| **pair-verdict** | **range_unconfirmed**, код 2 (прямой диапазон не подтверждён) |
| Возврат managed | `resume committed: slot=blue mode=api`, ATTRIBUTED |

- **Прямое плечо, TCP**: `retransmit_without_payload_ack`, 26 отсчётов,
  отправка 176 мс, первая ретрансляция 644 мс, ACK полезных данных нет,
  приём 0; окно 3 619 Б отправлено / 3 102 ретрансляции / 1 Б ACK.
- **Прямое плечо, очередь**: `observed`, 11,407 с, назначенных ID 9,
  переполнение 0, netlink 0, доля 0,0 — за всё время таймаута очередь
  ничего не теряла.
- **Счётчики за окно прямого запроса**: zapret2 uplink 517 / downlink 0
  за 12,4 с (данные уходили, обратных не было); за окно VPN-плеча:
  xray uplink 14 662 / downlink 128 585 за 1,2 с; конфигурация не
  менялась.
- Вердикт пары: `same_target=true`, `same_connected_peer=true`,
  `vpn_route_verified=true`, `vpn_range_verified=true`, попытка
  контроля — первая.

## §4 Возврат и итог

- Возврат: `resume committed: slot=blue mode=api` +
  `STANDALONE_LIVE_RETURN_ATTRIBUTED`; откат `rollback: complete`,
  config.toml и panel.json OK, restore-completed подтверждён; final-*
  все код 0.
- Текущее состояние: blue managed, маркер на месте, pending/resume нет;
  мой пост-контроль: VPN HTTPS 204 за ~0,3 с, режим off.

## Наблюдения для Codex

1. **Диагностика выхода готова, а сбой выключения не повторился**:
   в этом проходе standalone-off подтвердился штатно, поэтому
   `off-daemon.out`/`off-topology.out` не создавались (они пишутся
   только при отказе). Прошлый `off_deadline` остаётся эпизодом —
   стоит проверить, не был ли он следом состояния после прямого 302.
2. **Сигнатура прямого плеча вернулась**: tls_timeout и
   retransmit_without_payload_ack с почти теми же числами, что 2026-11-24
   (3 619 / 3 102 / 1 / 0). Значит 302 прошлого прохода — свойство
   конкретного CDN-хоста/сессии, а не новое поведение сети. Сводка
   очереди при этом нулевая (0/0, 9 назначенных ID за 11,4 с) — потеря
   не в очереди NFQUEUE; ACK не приходит снаружи.
3. **Устаревший `resume_managed` блокирует следующий проход**
   (дополнение FLASH): после прошлого сбоя выключения штатный демон сам
   поднял managed blue, но флаг `resume_managed: true` из
   кандидатского кода остался, и гейт baseline (`not resume`) дал
   `topology_not_confirmed`. Установленный код поле не читает; я снял
   его из runtime-состояния перед повтором, блок не менял. Предлагаю:
   гейт baseline считать выполненным при `active in blue/green` +
   маркер + не pending/draining (флаг resume — только для legacy), и
   очищать флаг в пути возврата после сбоя.
4. **`direct-verdict` до выключения теперь закрывает дымку прошлого
   прохода**: маршрут прямого плеча сохранён и подтверждён, очередь
   опубликована (9/0/0), pair-verdict собран полностью с
   `range_unconfirmed`. Для дальнейшей локализации остаётся только
   вопрос «кто теряет SYN-ACK/ServerHello» — по TCP-счётчикам это
   не очередь и не zapret2-правило (правило было активно).
