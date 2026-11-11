# TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-standalone-2026-11-12

Дата: 2026-11-12; CODE 4a0e3eb (самостоятельный режим zapret2 без VPN), база f2a6057 (отчёт
r12), план 05537f7; сумма помощника 7ef6f6c8… сверена с CODE — OK. Исполнитель GLM-5.3-Flash;
запуск в среде агента и терминале ThinkCentre, инструмент — bash исполнителя через агент.

Статус: **исполнение остановлено на тестовых воротах §3 до любых изменений машины**. Ни один
шаг установки и переключения не выполнялся: машина в исходном состоянии — VPN исправен,
zapret2 off, capture on, файлы пакета не менялись, xgw.service не перезапускался.

Предварительная сверка исполнителем (до выполнения плана): ancestry CODE на freepool OK,
`git diff --check` чист, diff — 21 файл, +772/−35 (новый watch/standalone.py, helper,
test_zapret2_standalone.py, изменения config/daemon/engine/builder/gui/managed/nft/panel/
status/control/zapret2, config.example.toml, ZAPRET2.md).

Тестовые ворота §3 (командой плана, без установки пакетов):

- `tests/test_zapret2_standalone.py tests/test_zapret2.py tests/test_zapret2_panel.py
  tests/test_generator.py tests/test_nft.py tests/test_net.py` —
  **5 failed, 281 passed, 15 skipped**;
- `tests/test_gui_qt.py -k zapret2` (offscreen) — 1 passed, 18 deselected.

Разбор пяти падений — все в tests/test_nft.py (test_gateway_with_lan_and_local_capture,
test_loopback_guard_refuses_marked_packets_to_loopback, test_ip6_table_captures_the_machine_
when_ipv6_is_proxied, test_blocked_mode_lets_only_xray_and_service_traffic_out,
test_v6_guard_lets_xray_sockets_out): новый код добавляет в цепочку loopback_guard правило
`meta skuid 992 ct direction original ip daddr 127.0.0.0/8 counter reject` (запрет демону
loopback при standalone), а ожидания правил в тестах остались прежними — смещение на одну
строку в каждой из пяти проверок цепочек. Это устаревшие ожидания тестов при намеренном
изменении генерации правил, а не дефект генерации.

Пятнадцать пропусков — давние средовые (`нужны nft и root` — 9+5+1), к изменению не относятся.

По оговорке плана («новый FAIL — не ставить код до разбора») установка исходников,
переключение режимов и проверки §4–§6 не выполнялись. Отчёт публикуется по §7 «при любом
исходе». Ожидается от разработчика: обновить пять ожиданий в tests/test_nft.py под новое
guard-правило (или пояснить, если правило не предполагалось), после чего план исполняется
с нуля. Примечание: для самостоятельного исполнения §1–§6 исполнителю нужен доступ с sudo —
сейчас среда агента работает без него; восстановление доступа — перезапуск агента с правами
root, как в предыдущих раундах, либо эквивалентный канал.

Хеш коммита ТЗ: 05537f7; код: 4a0e3eb. Отчёт без секретов, адресов и содержимого конфигов.
