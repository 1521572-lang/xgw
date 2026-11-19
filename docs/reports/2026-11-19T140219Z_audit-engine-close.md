# ThinkCentre · ограничение очереди Engine, завершение TCP и состояние off — 2026-11-19

- RESULT: **CONTRACTS PASS (23 passed: accounting-controls, accounting-loss stops
  worker, bounded fail-open queue, disabled-engine no-op, reply-window/synack
  accounting, engine_states, worker), KERNEL SERIES 2/2 PASS (обе серии идентичны:
  6 FIB-строк expected=actual; все контроли healthy — bypass 0, unmarked blocked;
  close_control 12/12 echo/FIN/final_ack/0 ошибок; close_xgw 12/12 echo/FIN с
  final_ack=0 и LAST_ACK=12 на дедлайне → REPRODUCED_IN_LAB; accounting 0/1 —
  unaccounted 8/8 без совпадений, fresh 8/8 ровно 4, existing 8/8 — 0; TUN обе
  фазы PASS), OFF-состояние: фактическая политика = **standalone** (не off) —
  off-проверка NOT_OBSERVED; вместо неё зафиксировано OWNERSHIP подтверждение:
  xgw-zapret2 active, очередь 200, owner_verified=true (netlink-сокет связан с
  MainPID 3276966) на трёх снапах с одинаковой ревизией `875f173c`, тем же
  InvocationID демона, seq/счётчики без роста**. Машина не менялась:
  HOST_BASELINE_SAME (acct=0, конфиги byte-identical), таймеры прежние.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; nftables v1.0.9; кандидат `df93784…`;
  фактическая установленная база (по основной приёмке) — `3630b44…` (по installed:
  daemon.py, net/nft.py, nfqws2.py = байты 3630b44/46c69fd — обе ревизии этих
  файлов одинаковы; watch/zapret2_control.py = 3630b44; OTHER нет).
- Ограничение: CLOSE-числа описывают получателя лабораторного пути (LAST_ACK
  фиксирует состояние на дедлайне); по счётчикам нельзя установить принадлежность
  каждого позднего пакета и влияние на рабочий sing-box. Контроли обеих серий
  здоровы → расхождение пар воспроизводимо: REPRODUCED_IN_LAB (не дефект XGW).

## CONTRACTS (§2) — PASS

23 passed: EngineTests ×4 (accounting controls rules/warnings, accounting-loss
stops worker + skips engine profiles, NFQUEUE bounded/fail-open/loop-free,
disabled engine не трогает runtime), reply-window требует accounting и bounded
first packets, synack-observation только на marked handshakes и выбранной очереди,
engine_states, test_desync_worker (весь модуль). Отказов/пропусков нет.

## KERNEL SERIES ×2 (§3) — PASS, REPRODUCED_IN_LAB

| Строка | expected | серия 1 | серия 2 |
| --- | --- | --- | --- |
| mark 0x1 FIB | audit-tun | ✓ | ✓ |
| mark 0x2 / 0x20000001 / 0x20000012 / 0x10000000 / 0x50000000 FIB | audit0 | ✓ | ✓ |
| bypass_control | 0 | 0 | 0 |
| unmarked_other_uid (отриц. контроль) | 1 | 1 | 1 |
| off_selected_copy | 1 | 1 | 1 |
| closed_selected_copy | 1 | 1 | 1 |
| open_selected_copy | 0 | 0 | 0 |
| open_selected_no_listener | 1 | 1 | 1 |
| engine_copy / engine_no_listener | 0 | 0 / 0 | 0 / 0 |
| engine_other_uid | 1 | 1 | 1 |

### TCP close ×12 (контроль / под XGW)

| Величина | close_control | close_xgw |
| --- | --- | --- |
| client_ok | 12/12 | 12/12 |
| echo (peer) | 12 | 12 |
| client_fin | 12 | 12 |
| final_ack (peer → TCP_CLOSE) | **12** | **0** |
| last_ack_at_deadline | 0 | **12** |
| other_at_deadline | 0 | 0 |
| errors / client_errors | 0 / 0 | 0 / 0 |

- Контроль здоров в обеих сериях → пара «контроль ОК, XGW LAST_ACK»
  **REPRODUCED_IN_LAB**: под правилами XGW принимающий сокет остаётся в LAST_ACK
  на дедлайне окна (800 мс), тогда как в контроле доходит до TCP_CLOSE. Фазовые
  дельты close_xgw: all=132, uid=60, marked_zero=60, marked_proxy=72,
  after_guard_wan=60, after_guard_tun=72; close_control: all=72, uid=60,
  marked_zero=72, marked_proxy=0, after_guard_wan=72, after_guard_tun=0.
  Принадлежность каждого позднего пакета и влияние на рабочий sing-box из этих
  чисел не устанавливаются.

### Учёт conntrack (queue bound)

| Фаза | результат |
| --- | --- |
| install_acct_0 | actual=0, **queue=null** |
| unaccounted UDP 8 дейтаграмм | received 8/8, **queue_matches=0** |
| install_acct_1 | actual=1, **queue=200** |
| existing_flow_after_enable | received 8/8, **0 совпадений** |
| fresh_flow_after_enable | received 8/8, **ровно 4 совпадения** |

- queue bound к accounted flows подтверждён: при acct=0 очередь не совпадает ни
  с одним пакетом; при acct=1 новый поток матчится ровно на 4 первых пакета,
  существующий (до включения) — ни разу. Хостовый sysctl сверён отдельно (acct=0
  на рабочей машине, HOST_BASELINE_SAME).

### TUN

| Фаза | серия 1 | серия 2 |
| --- | --- | --- |
| tun_absent | created/usable/routes=true, 111 мс | true/true/true, 176 мс |
| tun_down | created=false, usable/routes=true, 51 мс | true/true/true, 81 мс |

## OFF-состояние (§4) — фактическая политика standalone → NOT_OBSERVED

- Три свежих снимка (span_s 0.11–0.12): policy_key `875f173c` **одинаковый**,
  policy_match=true, fresh=true, status_at обновляется (…799 → …814 → …841);
  daemon InvocationID `52323e88` тот же (поколение не менялось).
- units: xgw-zapret2 **active**, MainPID 3276966, InvocationID `05953aaa`,
  **owner_verified=true** (netlink связывает очередь 200 именно с MainPID),
  euid=0, listed=true; xgw-nfqws2 inactive (pid 0, load not-found — юнит
  фактически не настроен в этой установке).
- reservation = «xgw-zapret2.service» (не пустая), guard_read=true,
  gate_elements=2, queue_counters `zapret2_queue.9`=264882 **без роста** на
  трёх снапах (span ~40 с), seq=269118 стабилен.
- Итог: **OFF_CONSISTENT=NOT_OBSERVED** (фактическая политика standalone с
  активным воркером — наследие исходного panel.json принятой базы); OWNERSHIP
  подтверждён — активный unit держит очередь с owner_verified=true, при этом
  seq/счётчики не растут за 40 с (нет обработки в этом окне; вывод о других
  интервалах не следует).

## Завершение

- HOST_BASELINE_SAME (acct=0, config.toml/panel.json byte-identical);
  таймеры прежние (combined-day-rollback активен до 20.11, основной процесс
  суточного мониторинга не затронут).
- Отчёты: recon [2026-11-19_audit-recon.md](2026-11-19_audit-recon.md) — связанные
  вопросы этого дополнения закрыты: очередь Engine bound к accounted flows
  (candidate-код `df93784`), TCP-close расхождение — REPRODUCED_IN_LAB при
  здоровых контролих, владение очереди подтверждено owner_verified=true.
- Финал: off-политика не трогалась (standalone остаётся фактическим режимом
  базовой панели), воркеры в исходном состоянии, xgw active, VPN работает,
  disk 42 ГБ, приватные артефакты — в каталоге опыта 0700.
- Publication commit: `d11b7e17209c423bf93f4ff585f1c8daaf248fa1` (09860ee → d11b7e1, remote verified ancestor).
