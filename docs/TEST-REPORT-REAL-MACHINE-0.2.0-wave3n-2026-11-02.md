# Отчёт: XGW wave3n — HTTPS через постоянный sing-box при рабочем on

Начало/конец MSK: 2026-11-02, 15:40:21–15:46+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc Yak #3) (S1.3,
записано буквально; не обновлялся). Tested HEAD 7d2344c618237627276555c2caee312aea4c1ea2
/ tree 4378599f67e0ca31addcaee6fc79c9f23923ac45. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только тестовый сборщик
tests/stand/wave3_bridge_probe.py; продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
Два frozen SHA/owner/mode (BRIDGE_HELPERS_FROZEN; /run/xgw-w3n 0700, файлы root600):
wave3_bridge_probe.py SHA256
2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef;
wave3_on_observer.py SHA256
0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 (не изменён; CLI не
запускался — использован как библиотека).
Исходный/конечный: HEALTHY с 02.11 12:42; перехват ВКЛЮЧЁН (рабочий on, включён
владельцем, модель его не переключала); pool «выключен» (прежний); Xray 26.10.31 /
sing-box 1.14.4.
Run marker/rc: **BRIDGE_PROBES_RECORDED**, exit 3 — **не PASS** (частичный результат;
run не повторялся). Show согласован.
Curl_available=true, version 8.5.0, eligible=true (≥8.4.0); routing_mark_key_count=0
(routing_mark в постоянном конфиге SB отсутствует).
Candidates_total=71, selected_count=2 (максимум 2 базовых входа, профиль d),
target_count=2, configured_targets_only=true (только cfg-цели; новые не создавались).

| Case | Protocol/profile | Target ordinal | Rc/HTTP/bytes/seconds/TLS/encoding | Listener before/after | Body_ok |
|---|---|---|---|---|---|
| SB-1 | vless / d | 1 | rc=97 (ошибка SOCKS-прокси) / HTTP 0 / 0 байт / 1.599 с / TLS verify 0 / identity | true / true | false |
| SB-1 | vless / d | 2 | rc=97 (ошибка SOCKS-прокси) / HTTP 0 / 0 байт / 0.709 с / TLS verify 0 / identity | true / true | false |
| SB-2 (выбран) | vless / d | 1 | rc=0 / HTTP **206** / **32769 байт** / 0.372 с / TLS verify 0 / identity | true / true | **true** |

Fallback: первая cfg-цель не прошла на SB-1 — разрешённая единственная другая cfg-цель
попробована (target 2), обе попытки сохранены отдельно; поздним успехом первая не
затиралась. Listener ownership подтверждён до/после каждой попытки (LISTEN inode —
именно fd текущего PID sing-box, netns совпадает); одна пара bridge/target не
повторялась; URL/пароли/порты/имена серверов не выводились (пароль и URL передавались
curl через stdin).

Обезличенные before/after: рабочий on сохранён — capture true до/после; guard query=ok,
postrouting/10/forward/drop=5/reject=0 в обоих снимках; службы active ×6;
sing-box nonprivileged/uid-gid match/forbidden groups absent/caps 0×5/NoNewPrivs;
DAC expected ×4; pool_mode=off, router ap, tailscale_route=vpn, derp=true;
interfaces distinct; settings_unchanged=true ×3; bridge_config_unchanged=true;
same_boot=true; service_pid_same=true ×6; same_singbox_process=true;
on_context_preserved=true.
Pin_record_readable_before/after=true/true; pin_record_unchanged=true (только факт
неизменности записи; тест запись не выполнял).
Первый STOP/ошибок контекста не было; все разрешённые действия выполнены, NOT_RUN
после первого несовпадения не возникло. Смена настроек/выбора/служб/адаптеров моделью
отсутствовала. Действий владельца в прогоне не было; отклонений нет; конечная связь
живая; рабочий режим сохранён (HEALTHY/on, pool прежний).

Вывод: scoped HTTPS compatibility **частично подтверждена**: через один из двух
выбранных постоянных SOCKS-входов (SB-2) постоянный capless sing-box передал HTTPS-тело
206/32769 байт за 0.372 с с валидным TLS и identity-encoding — полезная совместимость
изоляции доказана для этого входа. Через второй вход (SB-1) обе попытки не прошли
(curl rc=97, ошибка внутри SOCKS-цепочки); окончательная причина этими данными не
установлена — по матрице это отрицательный/неполный запрос, не автоматический диагноз
ТСПУ или падения сервера, и не дефект изоляции (SB-2 на том же процессе прошёл).
BRIDGE_PROBES_PASS не достигнут: 1 из 2 выбранных входов с body_ok.
GET seconds не RTT/скорость; 32769 байт — лимит чтения приложения, не жёсткий лимит
WAN-трафика (TLS/заголовки расходуют дополнительный трафик; множители тарифа не
измерялись).

TPROXY→Xray→SB на всех профилях, LAN UDP/IPv6/DNS leak/E4 actual packets/scoped
faults/D1-on reinstall/all Tailscale paths: NOT_RUN. Полная wave3 открыта, рабочая
эксплуатация продолжается; off-rollback не запускался; pin/подписка/серверы не менялись.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-2026-11-02.md, коммит «Отчёт:
XGW 0.2.0, wave3n — HTTPS через постоянный sing-box», push в freepool (REPORT_PUBLISHED
в финальном сообщении). В Git только этот Markdown; notes/private JSON/curl raw/
пароли/URL остались вне репозитория.
