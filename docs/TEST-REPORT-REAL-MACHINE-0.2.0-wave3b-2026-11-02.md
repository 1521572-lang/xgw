# Отчёт: XGW 0.2.0 — wave3b, установка и связь

Это заполненный шаблон. Дата/время: 2026-11-02, 00:06–00:18 MSK (+03).
Исполнитель/модель: GLM-5.3-Flash (ZCode), терминал владельца. Устройство/ОС/systemd:
ThinkCentre, Ubuntu 24.04.5 LTS, systemd 255.
Исходный HEAD: 4395963 → ff-only 9ea3583cd2b9958039e42fcf560a4f865116c14c (tree 22de1806…).
Код f4a27b7f0893e78f44481087d9fd64e2fd01654f — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, config.example.toml, pyproject.toml) после него пуст.
Fingerprint frozen safety.py: cbdb82994eb674e84b7ca37642a1927bc0b395c85b7f06013ef4887fb1a4e229
(обе суммы совпали); старого helper (w3check.py): ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04 (совпал).

## Согласие и исходная база

Ответы: страховка/off-установка/enable/повторная on-установка — «Согласен на всё» (00:07).
Начальный режим: VPN off («Перехват: СНЯТ (xgw disable)» — подтверждено перед согласием),
pool off; ядра Xray 26.10.31 / sing-box 1.14.4; ручной выбор spare-de-0b0e — держится;
изоляция sing-box от wave3 сохранена (xgw-singbox, caps 0x0, конфиг root:xgw-singbox 640/2750,
routing_mark 0); связь владельца — живой сеанс (отвечал на согласие), модель — живой сеанс.
Секреты, адреса, MAC, имена устройств и сырые журналы не включены.

## Результаты

| Шаг | PASS/FAIL/INCONCLUSIVE/NOT_RUN | Факт / evidence |
|---|---|---|
| Код/helper/чистая freepool | PASS | ff-only 4395963→9ea3583; f4a27b7 предок; runtime diff пуст; helper SHA256 совпал; rescue-код заморожен, обе суммы совпали | 
| Предварительный автономный возврат при off | PASS | RESTORED_OFF, nft_rc 0, capture_enabled false, WAN/LAN carrier 1/up, plain/marked connected |
| Время от запуска safety до RESTORED_OFF / recovery_seconds | PASS | 00:08:44 старт → восстановление; recovery_seconds 0.142 |
| Связь модели и владельца после автономного опыта | PASS | сеанс модели жив (команды пошли), владелец на связи; `systemctl start xgw` (разрешено), база повторена: HEALTHY, capture off, pool off |
| Установка из off: job rc / фактический режим | **INCONCLUSIVE** | две попытки, обе прерваны страховкой по истечении lease (операторский ритм, не код/VPN): job-result застыл «running/rc null»; фактически код wave3b установлен прерванной попыткой (см. ниже), демон HEALTHY на нём |
| Enable под независимой страховкой | NOT_RUN | §3 не завершён штатно — зависимые шаги прекращены |
| Новые соединения и связь через 30 с | NOT_RUN | см. выше |
| Переустановка из on: job rc / фактический режим | NOT_RUN | см. выше |
| Guard / SB UID+caps / Capture.loaded / mismatch | PASS (факты) | SB: xgw-singbox, caps 0x0×4, группа xray нет, конфиг root:xgw-singbox 640/2750, routing_mark 0; Capture.loaded True ×2; mismatch нет; guard NOT_RUN (capture off — барьер не требуется) |
| Disarm либо автономный возврат после потери lease | PASS | три срабатывания страховки: §2 плановое (без пульса) и два по lease — все RESTORED_OFF, recovery_seconds 0.142 / 0.137 / 1.018, nft_rc 0; связь модели и владельца не терялась ни разу |
| Итоговый режим и связь владельца | PASS | HEALTHY, перехват СНЯТ (off — исходный и текущий выбор владельца), pool off, pin spare-de-0b0e, 5 служб: xgw active, xgw-net inactive (после страховки; capture off), ядра active; plain/marked connected |

Факт установки: официальный rc0 не получен, но первая прерванная попытка успела заменить код и
юниты до остановки: в `/opt/xgw/lib/xgw/install.py` есть `_pause_daemon` (маркер wave3b),
`systemctl show xgw.service -p KillMode` → **KillMode=mixed** (активно), демон, поднятый
после срабатывания страховки, работает на этом коде (HEALTHY). Идентичность кода — commit
реализации f4a27b7 и пустой runtime diff в клоне; штатный `install rc0` с фиксацией политики —
не выполнен.

## Связь и атрибуция

| Момент | WAN carrier/operstate | LAN carrier/operstate | Новый plain TCP | Новый marked TCP | Сеанс владельца | Состояние safety/job |
|---|---|---|---|---|---|---|
| До | up / 1 | up / 1 | — | — | жив | not armed |
| После off-install (прервана) | up / 1 | up / 1 | connected | connected | жив | RESTORED_OFF |
| После enable | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| После on-install | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Итог | up / 1 | up / 1 | connected | connected | жив | RESTORED_OFF (insurance disarmed by fire) |

Различение: physical link-down не было (carrier 1); отказ маршрута/перехвата не
устанавливался (capture off по замыслу); тестовая цель отвечала; старые direct-сессии — не
актуально (VPN был off всю проверку). Полный E4/WAN-sentinel, старые scoped faults, UDP/IPv6/
LAN payload и 10-минутная нагрузка — NOT_RUN; волну 3 целиком это не закрывает.

## Дефекты и ограничения

D1 (сохранение on/установка): **NOT_RUN** — до enable/reinstall не дошли.
D2 (потеря связи): **NOT_RUN как опыт** — связь владельца и модели не терялась ни разу; жалоба
wave3 («>30 с без автоматического переподключения») в этом прогоне не воспроизводилась и не
опровергнута (enable-опыт не выполнялся).

Срабатывания safety: три, все RESTORED_OFF (0.142/0.137/1.018 с), nft_rc 0, связь жива.
Причина: §2 — плановое отсутствие pulse; §3 дважды — истечение lease: интервал между
командами оператора (инструментальный цикл Flash) превышал окно 15 с; локальный pulse-loop
запрещён планом, поэтому ритм не удержан. **Прекращение по lease не является дефектом VPN** —
это ограничение связки «канал оператора ↔ окно lease» для разработчика: окно/механику pulse
стоит пересмотреть для реального канала Flash.

Прочие ограничения: `prepare` не допускает повторный запуск в тот же каталог
(FileExistsError) — повтор опыта потребовал нового каталога (install2; использован с
сохранением снимка прерванной попытки); job-result остаётся «running/rc null» после
остановки job (устаревший артефакт — отмечено); «ошибок загрузки правил: 0», Traceback 0
(агрегат журнала за окно: 171 строка).

Сырые snapshot/off.nft/job.log остаются root:0700 на машине (`/run/xgw-w3b/`) и не
публикуются; в Git — только этот обезличенный отчёт.

## Итог

Страховка подтверждена на этой машине: три срабатывания, все — быстрый автономный возврат в
исходный off без потери связи (0.142/0.137/1.018 с при бюджете 12 с). Установка wave3b
штатно не завершена (rc не зафиксирован) — обе попытки прерваны страховкой по lease;
фактически код wave3b и KillMode=mixed установлены и работают (демон HEALTHY, capture off).
D1/D2/enable/on-переустановка — NOT_RUN. Итоговый режим: VPN off (выбор владельца, как до
проверки), pool off, связь владельца и модели — есть.
