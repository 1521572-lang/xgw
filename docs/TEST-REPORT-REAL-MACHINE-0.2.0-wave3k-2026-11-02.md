# Отчёт: XGW wave3k — предпосылки LAN/E4/Tailscale, только off/read-only

Дата MSK начала/конца: 2026-11-02, 13:04:55–13:12+03. Модель GLM-5.3-Flash (ZCode),
терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc Yak #3).
Tested HEAD adb59d18b33df2132f3ddb86a27dcd020a346b9d / tree
956d46ccf119dc2c52b6eca2bec4a03ac2bdfcb7; code pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст — код не менялся, нового кода не устанавливалось.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK;
nft.py = 10c1df64, wave3j-версия).
Исходные: HEALTHY с 02.11 12:42; перехват СНЯТ; pool off; Xray 26.10.31 / sing-box
1.14.4; pin spare-de-0b0e; службы active ×5 + tailscaled active.

| Шаг | Факт | Категория |
|---|---|---|
| S1 owner/sudo/notes | Linux; OWNER_SHELL_OK; NOTES_CREATED 13:04:55+03; SUDO_CACHE_OK; nft v1.0.9 | PASS |
| S2 source/installed/off | SOURCE_PREFLIGHT_OK; INSTALLED_SOURCE_OK ×4; HEALTHY/off/pool off (после устранения отклонения, см. ниже) | PASS |
| I1 collector marker/rc | INVENTORY_READ_FINISHED, exit 0; capture_off before/after true; files_unchanged true×3 | PASS |
| I2 declared prerequisites | 4 ответа владельца получены ~13:10+03 (см. таблицу предпосылок) | PASS (DECLARED) |
| Итоговый status/pool | HEALTHY с 02.11 12:42; перехват СНЯТ; pool off | PASS |

Все агрегаты коллектора (только bool/count/enum):
- interfaces_distinct=true; WAN: configured/query_ok=true, operstate=UP, carrier=1;
  LAN: configured/query_ok=true, operstate=UP, carrier=1;
  lan_address_matches_config=true.
- lan_neighbour_states (локальный кэш): STALE=2, FAILED=3, REACHABLE=1.
- dhcp_lease_rows=4; dhcp_unexpired_or_static=4.
- tools_available: tcpdump=true; dumpcap=false; tshark=false; ethtool=true; curl=true;
  ip=true; nft=true; tailscale=true; ssh=true. Захват данным протоколом не выполнялся
  (NOT_RUN); наличие tcpdump — только обнаружение инструмента.
- services: xgw/xgw-net/xgw-xray/xgw-singbox/xgw-dhcp/tailscaled — active ×6.
- Tailscale: configured_route=vpn, derp_fallback=true,
  runtime_direct_marker=false, runtime_vpn_fallback_marker=false — состояние
  конфигурации/маркеров, не доказательство пути/непрерывной связности.
- files_unchanged=true ×3 (config/managed/nft.py); capture_off_after=true.
Никаких исходных имён/IP/MAC/UUID/учётных данных не публиковалось.

| Предпосылка | DECLARED владельцем | OBSERVED данным протоколом | Ограничение |
|---|---|---|---|
| Независимый физический CLIENT-A/ОС | Да: потребительский Wi-Fi-роутер (CLIENT-A; модель не публикуется), подключён к физической LAN; ожидаемая роль — раздавать интернет, прошедший через XGW | LAN up/carrier 1, кэш соседей 6 записей, leases 4/4 — наличие/роль CLIENT-A не проверялись | cache не online |
| Способ выполнения команд на клиенте | Да: SSH (детали подключения не публикуются) | NOT_RUN — не входили | не входили |
| SENTINEL-A/журналы либо только WAN capture | UNKNOWN («пока неизвестно») | NOT_RUN | не подключались |
| Tailscale роль/доступ для будущего опыта | Да: подключение действует; владелец проверит позже; роль канала управления — сохранить | active service; route=vpn; маркеров нет; путь не тестировался | путь не тестировался |

Ответ владельца получен (все 4 строки; UNKNOWN только по sentinel).
Первый STOP: при первом чтении S2.2 перехват был ВКЛЮЧЁН (владелец включил VPN после
wave3j) — STOP по ТЗ («не выключать ради подготовки»); владелец по запросу сам снял
перехват («Выключу сам, продолжай»); модель сеть не трогала, новый каталог/прогон не
создавались, повторное чтение зафиксировало HEALTHY/СНЯТ/pool off — отклонение
стартового состояния, устранённое действием владельца, зафиксировано и не повлияло на
read-only сбор.
Состояние до/после: off до и после; files_unchanged true×3. Системных изменений не было
(ничего не устанавливалось, службы не стартовали, сеть не переключалась).

Loaded/on/enable/recovery/LAN/UDP/IPv6/DNS-on/Tailscale/E4/scoped faults/load: NOT_RUN.
Этот отчёт не повторяет и не заменяет принятый результат wave3j (loaded measured true,
guard postrouting/10/forward/5/0). Полная wave3 открыта: LAN/E4/Tailscale/UDP/IPv6/
DNS-on/scoped faults/нагрузка остаются NOT_RUN; этот протокол — только опись предпосылок.
DECLARED ≠ OBSERVED/PASS: доступ по SSH и роль CLIENT-A предстоит испытать отдельным ТЗ.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3k-2026-11-02.md, коммит «Отчёт:
XGW 0.2.0, wave3k — read-only inventory», push в freepool (REPORT_PUBLISHED в финальном
сообщении). В Git только этот Markdown; notes/inventory-агрегаты сверх отчёта/raw logs/
leases/addresses остались вне репозитория.
