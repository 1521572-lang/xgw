# Отчёт: XGW wave3m — границы доступа при рабочем on

Начало/конец MSK: 2026-11-02, 14:24:34–14:31+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc Yak #3) (S1.3,
записано буквально; не обновлялся). Tested HEAD ea199673039da61e87123bad1cdd5db7d1b36d43
/ tree a1cae09d551ba0bb85c1bccfd429749158c88d3b. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новый файл — только тестовый helper
tests/stand/wave3_permission_probe.py; продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
Два frozen SHA/owner/mode (PERMISSION_HELPERS_FROZEN; /run/xgw-w3m 0700, файлы root600):
wave3_permission_probe.py SHA256
3699bd2ab77831ba46bc09e719e521c0bf2d9ed37535d101e65cc320059391d6;
wave3_on_observer.py SHA256
0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 (прежний reader, не
изменён; его CLI не запускался — использован только новым probe как библиотека).
Исходный/конечный: HEALTHY с 02.11 12:42; перехват ВКЛЮЧЁН (рабочий on, включён
владельцем, модель его не переключала); pool «выключен» (прежний); Xray 26.10.31 /
sing-box 1.14.4. Схема XGW → роутер → устройства сохраняется.
P1 marker/rc: PERMISSION_HELPERS_FROZEN, exit 0. T1 run marker/rc:
PERMISSION_PROBES_PASS, exit 0; show согласован.

| Case | Expected | Actual | Identity_verified | pass_expected/ограничение |
|---|---|---|---|---|
| SB_OWN_CONFIG | ALLOWED | **ALLOWED** | true | PASS — положительный контроль чтения собственного конфига (open+close, содержимое не читалось) |
| SB_XRAY_CONFIG | DENIED_PERMISSION | **DENIED_PERMISSION** | true | PASS |
| SB_XRAY_API | DENIED_PERMISSION | **DENIED_PERMISSION** | true | PASS — connect к существующему UNIX socket без RPC |
| SB_STATE_CREATE | DENIED_PERMISSION | **DENIED_PERMISSION** | true | PASS — уникальный пустой файл не создан; cleanup_pending=None, ручной чистки не требовалось |
| SB_NFT_READ | DENIED_PERMISSION | **DENIED_PERMISSION** | true | PASS — stdout уничтожался; root-контроль nft list tables = true (команда исправна, отказ именно прав) |
| XRAY_SB_CONFIG | DENIED_PERMISSION | **DENIED_PERMISSION** | true | PASS — от UID/GID/групп Xray; отсутствие DAC_OVERRIDE/DAC_READ_SEARCH у Xray проверено отдельно |

6/6 pass_expected=true; identity_verified=true ×6 (UID/GID/доп. группы child совпадали с
целевым процессом, capsets 0×5 и NoNewPrivs перепроверены внутри child до попытки,
bounding set очищен). Tools_available: setpriv/python3/nft — true (setpriv не
устанавливался, был уже). target_preconditions=true ×5.

Обезличенные before/after: рабочий on сохранён — capture true до/после; guard query=ok,
postrouting/10/forward/drop=5/reject=0 в обоих снимках; службы active ×6;
sing-box nonprivileged/uid-gid match/forbidden groups absent/caps 0×5/NoNewPrivs;
DAC expected ×4; pool_mode=off, router ap, tailscale_route=vpn, derp=true;
interfaces distinct; settings_unchanged=true ×3; same_boot=true;
service_pid_same=true ×6; on_context_preserved=true. Первый STOP/ошибок не было; все
шесть cases выполнены, NOT_RUN после первого несовпадения не возникло. Неожиданно
разрешённой записи не было (own_empty_file_removed/private_cleanup_recorded — не
применимо). Изменений VPN/служб/адаптеров/правил/конфигов модель не делала (только
read-only сборы, метаданные, ограниченные child-пробы). Отклонений/действий владельца
в прогоне не было; конечная связь владельца и модели живая; конечный режим — рабочий
HEALTHY/on, pool прежний; VPN в конце остаётся on, отключение/откат не предусмотрены.

Вывод отдельно: положительный контроль прошёл (sing-box читает ровно свой конфиг);
пять границ подтверждены отказами: чужой конфиг Xray, API-socket Xray без RPC,
создание в состоянии XGW, чтение nft-таблиц, конфиг sing-box от Xray-идентичности.
Ограничение scope: проверялись отдельные краткоживущие capless-процессы с реальными
UID/GID/Groups; это не запуск внутри постоянного service sandbox и не доказательство
всех seccomp/AppArmor/mount-namespace ограничений; неподтверждённые ограничения не
дописываются. Запрос изменения ip rule в живое ядро — специальный NOT_RUN (старый
isolation-тест с ip rule add/del не запускался). Рост логов от отказов этих попыток —
следствие проб, не сетевая поломка.

Live ip rule add/del, D1-on reinstall/scoped faults/E4 actual packets/LAN UDP/IPv6/
DNS leak/all Tailscale paths: NOT_RUN. Полная wave3 остаётся открытой; рабочая
эксплуатация продолжается, off-rollback не запускался.

Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-2026-11-02.md, коммит «Отчёт:
XGW 0.2.0, wave3m — проверки границ доступа при on», push в freepool (REPORT_PUBLISHED
в финальном сообщении). В Git только этот Markdown; notes/private JSON/PID/UID/пути
конфигов остались вне репозитория.
