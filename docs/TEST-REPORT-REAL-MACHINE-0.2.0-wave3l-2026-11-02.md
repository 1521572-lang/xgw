# Отчёт: XGW wave3l — наблюдение рабочего on

Начало/конец MSK: 2026-11-02, 13:41:50–13:55+03 (интервал наблюдения ≈13:44–13:55).
Модель GLM-5.3-Flash (ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255,
nftables v1.0.9 (Old Doc Yak #3) (S1.3, записано буквально; не обновлялся).
Tested HEAD fe5348ef9af9d3f4bb2992e8143a37a90bd81e60 / tree
96a9e57f2283cc0fb0c435d7f2f2c18d45b4c6cc. Product code pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только тестовый сборщик
tests/stand/wave3_on_observer.py; продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
Frozen observer SHA256
0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46
(ON_OBSERVER_FROZEN; /run/xgw-w3l/observer.py, root:root 0600, каталог 0700).
Исходная рабочая схема: XGW → Wi-Fi-роутер (CLIENT-A из wave3k) → устройства; со слов
владельца, baseline (ТЗ §1). Начальные: HEALTHY с 02.11 12:42; перехват ВКЛЮЧЁН (рабочий
on, включён владельцем — модель его не включала и не переключала); pool «выключен»
(фиксация текущего выбора, не менялся); Xray 26.10.31 / sing-box 1.14.4. Конечные
значения — те же (см. ниже).

| Шаг | Факт/маркер/rc | Категория |
|---|---|---|
| S1/S2 подготовка/идентичность/исходный on | Linux; OWNER_SHELL_OK; NOTES_CREATED 13:41:50+03; SUDO_CACHE_OK; nft v1.0.9; SOURCE_PREFLIGHT_OK; HEALTHY/on прочитан и не переключался; INSTALLED_SOURCE_OK ×4 | PASS |
| P1 новый сборщик root700/600/SHA | ON_OBSERVER_FROZEN, SHA совпал, root:root 600 в /run/xgw-w3l | PASS |
| O1 start | ON_OBSERVATION_STARTED, exit 0 (sample 0.08 с) | PASS |
| Ожидание: число вызовов, READY, elapsed | 11 wait-вызовов (лимит 20): 10×WAIT_MORE + READY_FOR_END на elapsed 600.0 | PASS |
| O2 end/show/finalstatus | ON_OBSERVATION_RECORDED, exit 0; show согласован; финально HEALTHY/on, pool прежний | PASS |

Обезличенные start/end summaries (start-summary.json/end-summary.json, согласованы):
- capture before/after=true в обоих снимках (книжные концы, не непрерывное измерение);
  sample_seconds 0.08/0.075; files_unchanged_during_read=true ×3 в обоих.
- services active ×6 (xgw, xgw-net, xgw-xray, xgw-singbox, xgw-dhcp, tailscaled) — в
  обоих снимках; в конце service_pid_same=true ×6, restart_count_delta=0 ×6.
- singbox (оба конца, один и тот же процесс — same_singbox_process_bookends=true;
  same_process_during_read=true): account_nonprivileged=true, uid_all_match_service=true,
  gid_all_match_service=true, forbidden_groups_absent=true, cap_sets_zero: CapInh/Prm/
  Eff/Bnd/Amb = true ×5, no_new_privs=true — фактические свойства процесса в точках
  снимка, не полный набор negative isolation tests.
- config_dac: xray/singbox directory+file dac_expected=true ×4 (метаданные по stat).
- guard (оба конца): query=ok, source json, host_hook=postrouting, host_priority=10,
  forward_hook=forward, host_drop_rules=5, host_reject_rules=0.
- Режимы: pool_mode=off (не менялся — pool_mode_unchanged=true), router_mode=ap,
  tailscale_route=vpn, derp_fallback_configured=true (настройка; путь не тестировался),
  interfaces_distinct=true, roles_same=true, carrier 1/1.
- End: elapsed_seconds=608.141; bookends_on=true; settings_unchanged=true ×3;
  clock_step_suspected=false.
- interface_byte_deltas: WAN rx +24 971 138 / tx +40 816 905; LAN rx +4 780 /
  tx +3 410 — передача байт на интерфейсах, не привязка к конкретному клиенту или
  VPN-egress.
- journals: query_ok=true, limit 2000, rows=0, truncated=false, error_priority_rows=0,
  traceback_rows=0, permission_rows=0, fatal_rows=0, parse_errors=0 — в выбранных
  журналах/интервале соответствующих строк не найдено (ноль ошибок не доказан глобально).

Обычная эксплуатация устройств за роутером в интервале: НЕ наблюдалась лично (владелец
не сообщал о факте использования в интервале; путь XGW → роутер → устройства не
наблюдался) — рабочая схема сохранена как baseline; косвенно передача данных видна в
дельтах интерфейсов, без атрибуции. Без имён/адресов.
Существующий канал управления/Tailscale в интервале: наблюдение владельца не
фиксировалось; служба active, route=vpn сохранён (настройка, не проверенный путь).
Действия владельца/внешние изменения/STOP/отклонения: владелец вернул рабочий on до
старта (действующее указание ТЗ §1); STOP и отклонений в прогоне не было; WAIT_OWNER_ON
не потребовался. Модель не меняла VPN/службы/адаптеры/настройки: верно (только
read-only сборщик и чтения).
Итоговый рабочий режим: HEALTHY с 02.11 12:42; перехват ВКЛЮЧЁН; pool «выключен»
(прежний); Xray 26.10.31 / sing-box 1.14.4. Рабочий режим сохраняется; rollback-to-off
не запускался; после отчёта шлюз остаётся рабочим.

Решение отдельно: эксплуатационное наблюдение — зафиксированы книжные концы on через
608 с без перезапусков служб и с нулём ошибочных строк в проверенных журналах (это не
непрерывный capture и не синтетический E4); процессные свойства sing-box — изоляция
(nonprivileged/caps0×5/NoNewPrivs/DAC) подтверждена в обеих точках на одном и том же
процессе; журналы — покрытие по query_ok, полный ноль ошибок не доказан.
ON_OBSERVATION_RECORDED не является автоматическим PASS всех проверок.
D1-on reinstall/scoped faults/E4 actual packets/LAN UDP/IPv6/DNS leak/all Tailscale
paths: NOT_RUN — остаются отдельными задачами. Полная wave3 открыта.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md, коммит «Отчёт:
XGW 0.2.0, wave3l — наблюдение рабочего on», push в freepool (REPORT_PUBLISHED в
финальном сообщении). В Git только этот Markdown; notes/start-private.json/raw
journals/PID/addresses остались вне репозитория.
