# ТЗ Flash: wave3d — автономное окно и обновление с сохранением WAN

После отчёта3195ecc операторский pulse больше не является условием безопасности.
Задание выполняется одной локальной командой; независимый root-unit всегда возвращает
подготовленный исходный off по окончании фиксированного окна. Следующая команда модели
для восстановления не требуется. **Включение VPN и scoped faults в этом прогоне запрещены.**

Код: **28627675218f322185de11d0b569bca531d36aed**. Helper SHA256:
`60bc71cd1b8094e5ac37e6116c1452b1c43b601605ff8a3afcbc9c5b7896e6e7`.
Локально8 затронутых WAN/install +16 recovery проверок, ruff PASS; дополнительно одна
изменённая регрессия sysctl повторена после усиления контракта preserve. Широкая VM suite
не запускалась. Реальные окна/обновление/WAN-отпечатки wave3d: **NOT_RUN**.

## 0. Область и согласие

ThinkCentre, Ubuntu24.04.5, systemd255, клон `~/zcod/xgw`, ветка freepool.
Только существующая установка: unit на диске, исходные явный VPN off, pool off, HEALTHY,
живые владелец и модель. Если сейчас on — STOP, не выключать ради предусловия.
Сохранить текущие версии ядер и pin, Tailscale route/fallback и capture.local.

Проверить действующее согласие владельца: автономный возврат к тому же off с остановкой
контроллера, одна повторная установка, сохранение текущего WAN-профиля. Предварительный опыт
имеет окно25с; установка —45с. Затем stop/kill/nft с таймаутами1/1/3с: номинально около30с
и50с соответственно с дополнительным polling/IO. Это не абсолютная гарантия при отказе
ядра/диска/провайдера; прежний ориентир30с для установки здесь не обещается. До начала
владелец должен знать этот бюджет; отсутствие согласия/отказ — STOP.

Нельзя reboot, nmcli modify/reapply/up/down, netplan apply, reset/force, произвольные nft/ip,
смена профилей/подписок/FreePool/ручного выбора, правка установленного кода. Только точные
шаги этого ТЗ: Git FF, root-helper/snapshot, временные safety/job units, официальный install
под фиксированным окном, его off-rollback, последующий старт xgw. WAN по новой логике сохраняется
именно при повторной/частичной установке; чистая установка ещё имеет legacy IPv6-путь и здесь
запрещена. Не делать новых попыток в других каталогах после ошибки ради PASS.

Не печатать snapshot/capture.json/off.nft/job.log, сырые журналы, адреса, UUID и profiles.
Root-каталоги0700. Безопасный facts выводит только booleans/null сравнения WAN, не его значения.

## 1. Исходная база и код

```bash
mkdir -p "$HOME/xgw-w3d" && chmod 700 "$HOME/xgw-w3d"
cd ~/zcod/xgw && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor 28627675218f322185de11d0b569bca531d36aed HEAD && git diff --exit-code 28627675218f322185de11d0b569bca531d36aed HEAD -- src packaging tests/stand/wave3_safety.py config.example.toml pyproject.toml && git log -1 --format='%H %s' && git rev-parse 'HEAD^{tree}'
systemctl is-active xgw-w3b-safety.service xgw-w3b-job.service xgw-w3c-safety.service xgw-w3c-job.service
sudo xgw status | grep -E '^Состояние|Перехват:|^Xray|^sing-box'
sudo xgw pool | head -1
```

Все прежние safety/job должны быть inactive/not-found (ненулевой is-active ожидаем).
Active/activating/deactivating — STOP, не прерывать старый опыт. Git-ошибка/неHEALTHY/неoff/
poolнеoff — STOP. Не запускать старые ТЗ. Обычный цикл Flash может занимать >25с: это допустимо.

```bash
cd ~/zcod/xgw && test ! -e /run/xgw-w3d && sudo install -d -m 700 /run/xgw-w3d && sudo install -m 700 tests/stand/wave3_safety.py /run/xgw-w3d/safety.py && sudo sha256sum /run/xgw-w3d/safety.py
```

Сумма должна совпасть с заголовком. Каталог существует — STOP, не удалять/перезаписывать.
Замороженная копия остаётся вне /opt/xgw при его обновлении.

## 2. Обязательный реальный off-preflight автономного окна

```bash
sudo python3 -I /run/xgw-w3d/safety.py prepare /run/xgw-w3d/offcheck
sudo python3 -I /run/xgw-w3d/safety.py facts /run/xgw-w3d/offcheck
```

prepare проверяет исходную off-политику, nft -c, наличие unit и сохраняет boot ID, off-правила,
состояние и WAN-отпечатки. Ошибка — STOP. facts: all_verified=true; null означает отсутствие
замера, а не совпадение. Если false/null — INCONCLUSIVE WAN evidence, зависимые шаги NOT_RUN.

```bash
sudo systemd-run --unit=xgw-w3d-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3d/safety.py window /run/xgw-w3d/offcheck 25
```

**Не отправлять pulse/disarm, не поддерживать lease.** Локальное окно непродлеваемое и
закончится через25с. При живой модели можно подождать35с одной командой; если модель занята
дольше — это не срывает опыт. Затем только чтение:

```bash
sleep 35
sudo python3 -I /run/xgw-w3d/safety.py status /run/xgw-w3d/offcheck
sudo python3 -I /run/xgw-w3d/safety.py observe /run/xgw-w3d/offcheck
sudo python3 -I /run/xgw-w3d/safety.py facts /run/xgw-w3d/offcheck
sudo python3 -I /run/xgw-w3d/safety.py probe /run/xgw-w3d/offcheck
```

Ожидается RESTORED_OFF, nft_rc0, capture_enabled=false, links1/up, WAN all_verified=true,
живая связь владельца/модели. seconds_since_last_pulse здесь включает всё время от начала
окна (pulse не было), ориентир25–30с; recovery_seconds — только восстановление, ориентир≤5с.
Более30с/FAILED_*/restoring/проблема связи — STOP, установки нет. Нет job — ненулевой stop/kill
из-за отсутствующего job допустим, но успешные nft и фактическая связь обязательны.
Socket connected — только TCP-сокет, не доказательство внешнего TLS/получения тела.

Только после PASS и подтверждённой связи:

```bash
sudo systemctl start xgw
```

Через5с повторить status/pool из§1. HEALTHY/off/pool off, прежние ядра/pin. Если не так — STOP.

## 3. Одна повторная установка: локальный launch, окно45с

Только после §2 PASS и согласия из§0. **Не запускать install вручную и не запускать bare job.**

```bash
sudo python3 -I /run/xgw-w3d/safety.py prepare /run/xgw-w3d/install
sudo python3 -I /run/xgw-w3d/safety.py facts /run/xgw-w3d/install
```

Опять all_verified=true. Далее **одна команда** запускает сначала независимую страховку,
проверяет armed/active и только затем installer в отдельном unit:

```bash
sudo python3 -I /run/xgw-w3d/safety.py launch /run/xgw-w3d/install install "$HOME/zcod/xgw"
```

Вывод: started=install, fixed_window_seconds45, rollback=always_off, pulse_required=false.
Ошибка/таймаут launch — не повторять. Таймер уже мог запуститься; дождаться его результата.
**Даже при install rc0 rollback всё равно выполнится.** Модель не должна успеть продлить окно
или снять страховку. Локальный pulse-loop не нужен и не разрешён.

После окончания окна (ожидание55с одной командой допустимо, это меньше минуты):

```bash
sleep 55
sudo python3 -I /run/xgw-w3d/safety.py status /run/xgw-w3d/install
sudo python3 -I /run/xgw-w3d/safety.py observe /run/xgw-w3d/install
sudo python3 -I /run/xgw-w3d/safety.py facts /run/xgw-w3d/install
sudo python3 -I /run/xgw-w3d/safety.py probe /run/xgw-w3d/install
```

Нужны RESTORED_OFF, nft_rc0, тот же off, WAN all_verified=true, прежние links и связь.
Job-result action=install/state=finished/rc0 означает штатное завершение установки внутри
окна. aborted_by_safety/rcnull — **INCONCLUSIVE бюджета**, не PASS установки и не доказанный
дефект VPN. finished с rcне0 — FAIL установки. Новых попыток/увеличения окна нет.
Полное seconds_since_last_pulse ориентировочно45–50с; FAILED_* либо >50с — FAIL safety-бюджета,
новых сетевых опытов нет. Отдельно записать фактическое recovery_seconds.

При RESTORED_OFF, nft_rc0 и живой связи можно `sudo systemctl start xgw`, даже если job был
прерван: это только возвращение контроллера в проверенный off. Через5с безопасные status/pool.
Сбой возврата/связи — STOP; не рассчитывать на последующие команды модели после обрыва.

## 4. Итог и идентичность установленного кода

При завершившемся rc0 проверить реальные установленные файлы, а не только HEAD клона:

```bash
sudo python3 -I - "$HOME/zcod/xgw" <<'PY'
import hashlib,sys
from pathlib import Path
repo=Path(sys.argv[1])
for rel in ('install.py','net/sysctl.py','diag.py'):
    expected=(repo/'src/xgw'/rel).read_bytes()
    installed=(Path('/opt/xgw/lib/xgw')/rel).read_bytes()
    print(rel, 'installed_equals_pinned_source=', hashlib.sha256(expected).digest()==hashlib.sha256(installed).digest())
PY
systemctl show xgw.service -p KillMode -p ActiveState -p SubState
```

Все true, KillMode=mixed, HEALTHY/off. Отпечатки не гарантируют, что установка завершилась:
при rcnull это только факт частичной записи, результат остаётся INCONCLUSIVE.
Существующие UID/caps/config permissions и Tailscale проверить безопасным w3check.py из
прошлого прогона (SHA256 ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04):
только modes state/sub/cores/capstate/check/ts, после окончания окна; никаких isolation/cut.
Если проверенного helper нет — соответствующие пункты NOT_RUN, не импровизировать.
Не менять route/fallback Tailscale; его фактическую связь записать отдельно от связи модели.

Отчёт `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3d-<ДАТА>.md` по шаблону, только обезличенный
файл в staging; коммит «Отчёт: XGW 0.2.0, wave3d — автономное обновление», обычный согласованный
push в freepool, без force. Raw snapshot/off.nft/job.log/журнал остаются root0700 на машине.
Несовпадение WAN — факт, не автоматическое доказательство вины XGW (DHCP/RA могли обновиться).
D1 сохранения on, D2 после enable, E4/WAN packets, нагрузка и scoped faults здесь NOT_RUN.
