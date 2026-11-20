# ThinkCentre · кто применяет конфигурацию Xray — повтор с гейтом — 2026-11-20

- RESULT: **UNIT_TESTS PASS · DAEMON_BASELINE ok=false (gate блокирует
  установку: changed_failures=12 при new_failures=0) → INSTALL NOT_RUN,
  WRITER_CONTROL/LIVE_PLAY/FLOW/CONFIG_WRITER NOT_RUN · RESTORE NOT_RUN
  (не требовалось: таймер не создавался, машина не менялась — 3 целевых
  файла сверены с базой `3a00777` после gate)**.
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee`); VPN
  baseline 206/65536 + delta xray; тесты — обычным пользователем
  (`/usr/bin/python3`); sudo -n доступен (не потребовался для тестов).
- Исправление Codex подтверждено: **unit-набор кандидата rc=0**
  (test_applier/test_singbox_generations/test_desync_route_evidence/
  test_selective_probe_watch/test_acceptance_gate) — 3 отказа прошлого
  кандидата устранены (`list_outbounds` реализован в стабах).

## §1 Гейт

- worktrees: кандидат `e7bbc4a` + база `3a00777` (оба ancestor FETCH_HEAD).
- `writer-unit` rc=0.
- `test_daemon.py`: candidate rc=1 (17 отказов), baseline rc=1 (17
  отказов), оба JUnit по 158 кейсов, added/missing/new_skips — пусто,
  **new_failures=[]**; гейт `acceptance_test_gate.py` → **ok=false,
  changed_failures=12, matching_baseline_failures=5**.
- Установка блокирована правилом ТЗ до запуска таймера — фаз §2/§3 не было.

## Расшифровка 5 matching (тип/сообщение совпадают с базой)

| Тест | Тип | Первая строка |
| --- | --- | --- |
| test_probes_get_the_stop_event | AttributeError | 'Event' object has no attribute 'bytes_read' |
| test_fail_closed_keeps_capture_while_xray_is_down | AssertionError | assert (['up'] == []) — Left: 'up' |
| test_leak_reloads_rules_only_when_own_traffic_is_captured | AssertionError | assert ['up','up'] == ['up'] |
| test_rules_failure_is_reported_once | AssertionError | assert ['up','up','up','up'] == ['up','up','up'] |
| test_tailscale_goes_direct_while_xray_is_down | AssertionError | assert ([False,True] == [False,True] …['up' |

## Расшифровка 12 changed (у кандидата сообщение изменилось)

На базе все 12 падали `AttributeError: 'Event' object has no attribute
'bytes_read'`; у кандидата — уже поведенческие расхождения сетапа:

| Тест | Сообщение кандидата (первая строка) |
| --- | --- |
| test_all_dead_refreshes_directly_and_rotates_at_once | assert (0 == 1) — len(Harness.applied)=[] |
| test_daemon_names_the_tun_without_an_address | assert False (any(genexpr)) |
| test_daemon_reloads_missing_rules | assert False (any(genexpr)) |
| test_daemon_repairs_lan_path | assert False (any(genexpr)) |
| test_member_failing_the_first_check_is_replaced_at_once ×4 | AssertionError: assert (1 == 2) — len(applied) |
| test_net_event_starts_the_step_early_but_not_too_often | assert 1.5 <= (monotonic() − monotonic()) — дельта ~0 |
| test_rules_event_restores_rules_right_away | assert (Δmonotonic) >= 0.55 — дельта ~0 |
| test_wake_after_resume_reloads_rules_and_scans | assert [] — Harness.scanned пуст |
| test_xray_version_follows_binary_replacement | assert 6 == 4 — len(записей конфига) |

- Читается так: в тестовом сетапе поведение демона изменилось — минимум
  одна фаза (applied/scanned) не выполняется вовсе, а в
  `test_xray_version_follows_binary_replacement` кандидат делает **6
  записей конфига вместо 4** — прямая улика в контекст открытого вопроса
  «кто пишет конфиг Xray»: изменение в daemon.py увеличивает число
  перезаписей даже в стабильных тестовых сценариях.
- Ни один из 12 не является «новым» тестом; сообщения базового AttributeError
  в кандидате исчезли (строки проекта: `src/xgw/daemon.py:3595` и
  `tests/test_daemon.py` стабы — на базе).

## Статусы

| Статус | Значение |
| --- | --- |
| UNIT_TESTS | PASS (unit-набор rc=0) |
| DAEMON_BASELINE | ok=false — gate: changed=12, matching=5, new=0 |
| INSTALL | NOT_RUN (заблокирован гейтом; таймер не создавался) |
| WRITER_CONTROL | NOT_RUN |
| LIVE_PLAY | NOT_RUN |
| FLOW | NOT_RUN |
| CONFIG_WRITER | NOT_RUN |
| RESTORE | NOT_RUN (не требовалось; package = база — cmp 3/3 после gate) |

## Наблюдения для Codex

1. Гейт-механика (JUnit + acceptance_test_gate) работает ровно как
   задумано: caught the diff — candidate daemon.py меняет поведение в
   тестовом сетапе, при этом 5 отказов остаются бит-в-бит.
2. Обратить внимание на `assert 6 == 4` (записи конфига) и
   `assert (0 == 1)` (applied): либо стаб Harness отстал от новых
   событий демона (как было с bytes_read), либо кандидат реально
   увеличивает число записей конфига — второе прямо связано с целью
   этого прохода (перезаписи routing/inbounds/outbounds).
3. После синхронизации сетапа test_daemon на кандидате повтор возможен
   без изменений ТЗ — вся инфраструктура (worktrees, JUnit, gate,
   helpers) подготовлена.
- Publication commit: `09c46c480c45b38c0abed826d353bf9a6f5de7ae` (088a4ac → 09c46c4, ancestor verified).
