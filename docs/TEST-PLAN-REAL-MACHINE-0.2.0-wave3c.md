# ТЗ Flash: wave3c — ритм оператора и автономная страховка

Это ограниченный диагностический прогон после отчёта cc0b021. **Install и enable не запускать.**
При wave3b15с оказалось меньше инструментального цикла Flash; обе установки прерваны.
Нужно сначала доказать работоспособный операторский ритм без изменения сетевой политики,
затем проверить новые таймауты восстановления при уже выключенном VPN.
См. `ADR-WAN-LAN-TAILSCALE.md`: WAN-профиль сохраняется, Tailscale иногда нужен через VPN.
Нельзя автоматически выключать capture.local, менять route/fallback Tailscale или править WAN.

Код helper: **cc126060a478ed30550ad6bac4f82d37a02b9668**. Он не устанавливается как продукт.
Текущий runtime src/packaging соответствует f4a27b7; этот прогон его не заменяет.
Локально:12 узких recovery-тестов и ruff PASS. Реальный wave3c: NOT_RUN.
Шаблон отчёта: `TEST-REPORT-REAL-MACHINE-0.2.0-wave3c-TEMPLATE.md`.

## Ограничения

Устройство ThinkCentre, Ubuntu24.04.5, systemd255, рабочий клон `~/zcod/xgw`, ветка freepool.
Исходная база: явный VPN off, pool off, работающие модель и владелец. Если сейчас VPN on,
не выключать его для опыта: STOP. Перед off-preflight подтвердить действующее согласие
владельца на автономный возврат к этому же off и краткую остановку контроллера. Ранее данное
согласие можно использовать, если оно действует; отказ/неясность — STOP до действий.

Нет reboot, смены профилей, nmcli modify/up/down/reapply, netplan apply, произвольных nft/ip,
переустановки, включения VPN, изменения ядер/подписок/FreePool. Разрешены только точные шаги
ниже: Git fast-forward, локальные root-файлы, временный safety-unit, его подготовленное
off-восстановление и старт контроллера после успеха. Сырые snapshot/job.log/nft/profile не печатать.
Каталоги root0700; в отчёт только статусы, времена, версии и обезличенные агрегаты.

## 1. Идентичность и исходное состояние

```bash
cd ~/zcod/xgw && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor cc126060a478ed30550ad6bac4f82d37a02b9668 HEAD && git diff --exit-code cc126060a478ed30550ad6bac4f82d37a02b9668 HEAD -- src packaging tests/stand/wave3_safety.py config.example.toml pyproject.toml && git log -1 --format='%H %s' && git rev-parse 'HEAD^{tree}'
```

Ошибка/грязный клон/другой код — STOP, без reset/force. Не выполнять старые ТЗ.
Сначала проверить, что xgw-w3b-safety.service и xgw-w3b-job.service inactive либо not-found:

```bash
systemctl is-active xgw-w3b-safety.service xgw-w3b-job.service
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
sudo xgw pool | head -1
```

Для is-active здесь ненулевой код ожидаем при inactive/not-found. Если active/activating/
deactivating — STOP: не останавливать старый опыт вручную. База HEALTHY, off, pool off;
служба xgw-net может быть inactive после прежней страховки — записать факт, не скрывать.

```bash
cd ~/zcod/xgw && test ! -e /run/xgw-w3c && sudo install -d -m 700 /run/xgw-w3c && sudo install -m 700 tests/stand/wave3_safety.py /run/xgw-w3c/safety.py && sudo install -d -m 700 /run/xgw-w3c/calibration && sudo sha256sum /run/xgw-w3c/safety.py
mkdir -p "$HOME/xgw-w3c" && chmod 700 "$HOME/xgw-w3c"
```

Ожидаемая SHA256: `013be016c64162104dca7d0368736652902e79c5f4bead2a373ddc14c4b25041`.
Каталог существует/не та сумма — STOP, не удалять и не перезаписывать.

## 2. Dry-калибровка — без сетевых действий

```bash
sudo systemd-run --unit=xgw-w3c-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3c/safety.py watch-dry /run/xgw-w3c/calibration
```

В отдельном операторском цикле (как Flash действительно работает через терминал/зрение):

```bash
sudo python3 -I /run/xgw-w3c/safety.py pulse /run/xgw-w3c/calibration
```

Выполнить команду **всего три раза вручную**, отдельными вызовами инструмента, прочитывая результат между
вызовами. Не `for`, не локальный auto-pulse-loop, не «пачка команд без участия модели».
Каждая команда печатает LEASE_OK и previous_gap_seconds. Цель — обычный ритм5–10с; допустимый
максимум наблюдаемого разрыва20с, окно25с оставляет5с запаса. Сохранить три значения и максимум.
Если первое или любое следующее значение >20с, нет LEASE_OK или появился DRY_EXPIRED —
INCONCLUSIVE ритма, не дефект VPN. Весь §3 NOT_RUN; записать отчёт и STOP. Не увеличивать lease
на месте и не повторять в новых каталогах ради PASS. Dry-unit при истечении правил не меняет.
Dry-режим программно запрещает install/enable-job.

При трёх успешных циклах:

```bash
sudo python3 -I /run/xgw-w3c/safety.py disarm /run/xgw-w3c/calibration
```

Через1с:

```bash
sudo python3 -I /run/xgw-w3c/safety.py status /run/xgw-w3c/calibration
```

Ожидается disarmed. Если последний disarm запоздал — §3 NOT_RUN. Не запускать новый unit,
пока этот не завершился. В этом разделе nft/маршруты/адаптеры не менялись.

## 3. Реальная автономная проба при уже off

Только после §2 PASS, живой связи и согласия из предусловий:

```bash
sudo python3 -I /run/xgw-w3c/safety.py prepare /run/xgw-w3c/offcheck
date -Iseconds | tee "$HOME/xgw-w3c/rescue-start.txt"
sudo systemd-run --unit=xgw-w3c-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3c/safety.py watch /run/xgw-w3c/offcheck
```

prepare проверяет исходную off-политику и nft -c. Ошибка — STOP; ничего не включать/чинить.
Здесь **не отправлять pulse**:25с lease должно истечь автономно. Подождать28с одной командой:

```bash
sleep 28
sudo python3 -I /run/xgw-w3c/safety.py status /run/xgw-w3c/offcheck
sudo python3 -I /run/xgw-w3c/safety.py observe /run/xgw-w3c/offcheck
sudo python3 -I /run/xgw-w3c/safety.py probe /run/xgw-w3c/offcheck
date -Iseconds | tee "$HOME/xgw-w3c/rescue-end.txt"
```

Ожидается RESTORED_OFF, nft_rc0, capture_enabled=false, unchanged carrier1/up и живая связь
модели/владельца. Probe — только принятие TCP-сокета, не доказательство TLS/внешнего payload.
Таймауты stop/kill/nft1+1+3с: номинальный бюджет от последнего pulse около30с с polling/IO,
не жёсткая гарантия при отказе ядра/диска/провайдера. `recovery_seconds` не включает25с ожидания;
`seconds_since_last_pulse` включает его. Зафиксировать оба поля раздельно. Часы модели/время
чтения status не подменяют записанную локальным unit длительность. Если status ещё restoring, один повтор через2с;
FAILED_* либо не завершилось к30с — STOP, новых сетевых опытов нет. Не рассчитывать на модель
для починки входящего интернета после обрыва: watchdog уже должен работать локально.
Нет job в этом прогоне — ненулевой stop/kill rc из-за отсутствующего job допустим, но nft_rc0
и фактическая связь обязательны. Таймаут nft3с должен пройти именно реальную проверку.

После RESTORED_OFF и подтверждения связи:

```bash
sudo systemctl start xgw
```

Подождать5с, повторить безопасные status/pool из§1. Требуются HEALTHY/off/pool off и прежние
ядра/ручной выбор. Tailscale-политику не переключать; если владельцу он сейчас нужен — подтвердить
его прежнюю работоспособность, отдельно от канала Flash. При проблеме STOP без новой установки.

## 4. Отчёт

`docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3c-<ДАТА>.md` по шаблону. Записать HEAD/tree/helperSHA,
исходный режим, три интервала pulse и максимум, DRY_EXPIRED/disarmed, длительность ожидания
и restore раздельно, nft_rc, carrier/operstate, связь владельца/модели, финальный режим и
состояния служб. Установка/enable/D1/D2/E4/нагрузка остаются NOT_RUN.
Прерванный настоящий job в новом helper получает aborted_by_safety; здесь запуск job запрещён,
поэтому не придумывать его результат. WAN-профиль и Tailscale-маршрут в опыте не перенастраивались.
В staging только обезличенный отчёт, коммит «Отчёт: XGW 0.2.0, wave3c — ритм Flash», обычный
согласованный push в freepool. Не публиковать snapshot/capture.json/off.nft/job.log/сырой журнал.
