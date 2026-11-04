# Проверка XGW 0.2.0: wave3b — установка и связь со страховкой

## Область и порядок

Прочитать целиком. Исполнитель — Flash в терминале ThinkCentre, Ubuntu24.04/systemd255,
клон `~/zcod/xgw`, ветка `freepool`. Предыдущий отчёт `wave3-2026-11-01` не закрыл волну:
изоляция sing-box подтверждена, но установка оставила capture off, scoped faults не выполнялись.
Сейчас проверяем исправление установки и выясняем потерю связи. Старые cut-сценарии НЕ запускать.
Каждый шаг: действие, точная команда, факт и отклонение. Никакой самостоятельной правки кода.

Код: **`f4a27b7f0893e78f44481087d9fd64e2fd01654f`**. В нём установка останавливает демон
до замены кода, сохраняет on при ошибке и проверяет фактическую политику перед кодом0;
KillMode=mixed позволяет дочерней nft-транзакции закончиться. Это ещё не результат реальной проверки.

Локально:11 узких регрессий recovery,3 затронутых сценария install, ruff и проверка синтаксиса
команд ТЗ. Широкая VM suite повторно не запускалась. Реальные systemd/recovery/установка/связь
для wave3b — **NOT_RUN** до отчёта Flash. Шаблон: `TEST-REPORT-REAL-MACHINE-0.2.0-wave3b-TEMPLATE.md`.

**Потеряв интернет, модель не сможет восстановить его командами.** Поэтому перед любым install
или enable запускается отдельный локальный root-unit со страховкой, из заранее сохранённого
off-состояния. Если Flash не подтверждает связь15с, unit прекращает test-job и сетевых писателей
XGW, возвращает сохранённые off-правила без обращения к сети, установленному Python-пакету и
net.lock. Команды восстановления имеют таймауты2+2+8с; это проектный бюджет, а не гарантия при
неисправном ядре/диске/провайдере. До опыта обязательна реальная проверка страховки при уже off.
Если фактический возврат занимает больше30с либо модель теряет связь — STOP, новый опыт запрещён.

Страховка — инструмент только этого согласованного теста, не новый fail-open продукта.
Начинать только из **явного VPN off и pool off**, как закончил предыдущий отчёт. Если сейчас
владелец включил VPN, не выключать автоматически ради предусловия: STOP и сообщить.
Ничего не обещать о сохранении старых TCP-сессий и не считать reject-счётчик доказательством
выключения физической Ethernet-карты. Снимки carrier/operstate и новых соединений — раздельные факты.

## 0. Запрещено и согласие

Не выполнять reboot, reset, force, flush ruleset, перезапуск NetworkManager/адаптеров/SSH,
смену подписок/FreePool/ручного выбора. Системные действия разрешены только точными шагами:
установка; временные xgw-w3b-safety/job units; восстановление off подготовленным помощником;
старт xgw после срабатывания страховки. Не печатать снимки nft/конфиги/сырые журналы.
Файлы snapshot/job.log находятся в root0700; в отчёт только агрегаты, статусы и времена.

Спросить владельца, если такого согласия ещё нет:
«Повторная проверка волны3: сейчас VPN должен быть выключен. Сначала проверю автономный
возврат к этому же состоянию без включения VPN. Затем установка, короткое включение VPN и,
если связь сохранится, одна переустановка с включённым VPN. Возможен обрыв старых соединений.
Перед каждым опытом локальная страховка уже работает: без моего подтверждения15с она сама
прекратит тест и вернёт исходный прямой режим, оставив демон остановленным для разбора.
Страховка сначала должна реально пройти проверку на этой машине. Можно отказаться от
установки, включения VPN или второй переустановки отдельно». Записать ответ/время без личных данных.
Отказ или отсутствие ответа не дают разрешения. При недоступном владельце новый опыт не начинать.

## 1. Код и исходная база

### 1.1 Обновить только чистую freepool

```bash
mkdir -p "$HOME/xgw-w3b" && chmod 700 "$HOME/xgw-w3b"
cd ~/zcod/xgw && test "$(git branch --show-current)" = freepool && test -z "$(git status --porcelain)" && git fetch -q origin freepool && git merge --ff-only origin/freepool && git merge-base --is-ancestor f4a27b7f0893e78f44481087d9fd64e2fd01654f HEAD && git diff --exit-code f4a27b7f0893e78f44481087d9fd64e2fd01654f HEAD -- src packaging tests/stand/wave3_safety.py config.example.toml pyproject.toml && git log -1 --format='%H %s' && git rev-parse 'HEAD^{tree}'
```

Ошибка/грязный клон/другой runtime — STOP, не reset/checkout. Сохранить HEAD/tree.

### 1.2 Проверенный помощник и исходное состояние

Команда извлекает старый inline-helper, но **не выполняет старое ТЗ**:

```bash
cd ~/zcod/xgw && python3 - <<'PY'
import hashlib,re
from pathlib import Path
text=Path('docs/TEST-PLAN-REAL-MACHINE-0.2.0-wave3.md').read_text()
helper=re.search(r"cat > w3check\.py <<'EOF'\n(.*?)\nEOF",text,re.S)[1]+'\n'
assert hashlib.sha256(helper.encode()).hexdigest()=='ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04'
(Path.home()/'xgw-w3b/w3check.py').write_text(helper)
print('helper fingerprint OK')
PY
cd "$HOME/xgw-w3b" && date -Iseconds | tee before.txt
for m in state sub cores capstate check; do sudo python3 -I w3check.py "$m"; done | tee -a before.txt
sudo xgw pool | head -1 | tee -a before.txt
```

Требуются HEALTHY, capture off (явный выбор), pool off, прежние версии ядер/ручной выбор.
`check=True` при off означает соответствие off-политике, а не работу VPN. Если нет исходной
связи или она нестабильна — STOP. Проверку выше не считать подтверждением всех потоков.

### 1.3 Заморозить независимый rescue-код

```bash
cd ~/zcod/xgw && test ! -e /run/xgw-w3b && sudo install -d -m 700 /run/xgw-w3b && sudo install -m 700 tests/stand/wave3_safety.py /run/xgw-w3b/safety.py && sudo sha256sum /run/xgw-w3b/safety.py && git show f4a27b7f0893e78f44481087d9fd64e2fd01654f:tests/stand/wave3_safety.py | sha256sum
```

Обе суммы обязаны совпасть. Каталог уже существует/суммы разные — STOP, ничего не удалять и
не перезаписывать. Rescue-код и snapshot вне /opt/xgw, замена пакета их не меняет.
Ожидаемая SHA256 frozen safety.py:
`cbdb82994eb674e84b7ca37642a1927bc0b395c85b7f06013ef4887fb1a4e229`.

## 2. Обязательная автономная проба страховки при VPN off

```bash
sudo python3 -I /run/xgw-w3b/safety.py prepare /run/xgw-w3b/check
sudo ln -s /run/xgw-w3b/check /run/xgw-w3b/current
date -Iseconds | tee "$HOME/xgw-w3b/rescue-start.txt"
sudo systemd-run --unit=xgw-w3b-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py watch /run/xgw-w3b/current
```

Должен запуститься unit. В этом единственном шаге **не отправлять pulse**: подождать20с,
интернет уже идёт напрямую, VPN не включается. Затем:

```bash
date -Iseconds | tee "$HOME/xgw-w3b/rescue-end.txt"
sudo python3 -I /run/xgw-w3b/safety.py status /run/xgw-w3b/current | tee -a "$HOME/xgw-w3b/rescue-end.txt"
sudo python3 -I /run/xgw-w3b/safety.py observe /run/xgw-w3b/current | tee -a "$HOME/xgw-w3b/rescue-end.txt"
sudo python3 -I /run/xgw-w3b/safety.py probe /run/xgw-w3b/current | tee -a "$HOME/xgw-w3b/rescue-end.txt"
```

Ожидается RESTORED_OFF, nft_rc0, capture_enabled=false, прежний carrier/operstate,
новые plain/marked TCP подключаются, модель и владелец остаются на связи. Отсутствующий job
может дать ненулевой stop/kill rc: это не критерий успешного восстановления — нужен nft_rc0
и фактическая связь. Если статус restoring, можно проверить один раз через5с; дальше30с,
FAILED_* или потеря связи — STOP, не приступать к установке. Записать recovery_seconds.

Страховка оставляет xgw/xgw-net остановленными. После успешного опыта:

```bash
sudo systemctl start xgw
```

Подождать5с. Проверить исходную базу командами1.2. Если не HEALTHY/capture off — STOP.
Без прошедшего §2 дальнейшие опасные шаги запрещены, даже если разработчик выполнил unit tests.

## 3. Установка из off под страховкой

```bash
sudo python3 -I /run/xgw-w3b/safety.py prepare /run/xgw-w3b/install
sudo ln -sfn /run/xgw-w3b/install /run/xgw-w3b/current
sudo systemd-run --unit=xgw-w3b-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py watch /run/xgw-w3b/current
sudo python3 -I /run/xgw-w3b/safety.py pulse /run/xgw-w3b/current
sudo systemd-run --unit=xgw-w3b-job --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py job /run/xgw-w3b/current install "$HOME/zcod/xgw"
```

Установка идёт отдельным unit, не блокирует терминал Flash. Каждые5с, **отдельной командой**:

```bash
sudo python3 -I /run/xgw-w3b/safety.py pulse /run/xgw-w3b/current && sudo python3 -I /run/xgw-w3b/safety.py status /run/xgw-w3b/current
```

Не запускать локальный бесконечный pulse-loop: он скрыл бы потерю связи модели.
Не отправлять pulse заранее на минуты вперёд; heartbeat делает сама Flash при живом сеансе.
Нет LEASE_OK/статус не armed — прекратить новые действия. Страховка сама завершает опыт.
`job-result` должен показать action=install, state=finished, rc0. Пока state=running/rc=null,
задача не завершена. job.log целиком не печатать и не публиковать.

При rc0 проверить связь владельца, затем одной короткой командой observe/probe из§2,
обновляя lease между командами. Требуются capture off (сохранён!), carrier/новые подключения
как до установки. После подтверждения владельца:

```bash
sudo python3 -I /run/xgw-w3b/safety.py disarm /run/xgw-w3b/current
```

Через1с status должен быть disarmed. При rcне0 — FAIL установки, прекращение зависимых шагов;
не disarm при неясной связи, дать страховке вернуть исходный off и сохранить статусы.

Только после подтверждённого disarmed собрать свойства и агрегаты журнала. Они не требуют
новых сетевых действий; `KillMode=mixed` должен фактически применяться к службе:

```bash
systemctl show xgw.service -p KillMode -p ActiveState -p SubState -p ExecMainStartTimestamp -p ExecMainExitTimestamp | tee "$HOME/xgw-w3b/controller.txt"
sudo journalctl -u xgw --since "$(cat "$HOME/xgw-w3b/rescue-start.txt")" -o short-unix --no-pager | sudo python3 -I "$HOME/xgw-w3b/w3check.py" log | tee "$HOME/xgw-w3b/log-summary.txt"
```

Наличие новой ошибки nft — FAIL, без приписывания причины только по времени SIGTERM.
Согласие на следующий опыт получать, пока страховка снята. Уже вооружив её, не блокировать
терминал в ожидании ответа: поддерживать lease короткими командами либо допустить возврат off.

## 4. Короткое включение VPN, затем переустановка on

Только при отдельном согласии, успешных §2–3 и живом владельце. Ожидание: возможен разовый
обрыв старой direct-сессии; **новые** соединения должны заработать. Это ещё не тест всех LAN/UDP путей.

```bash
sudo python3 -I /run/xgw-w3b/safety.py prepare /run/xgw-w3b/enable
sudo ln -sfn /run/xgw-w3b/enable /run/xgw-w3b/current
sudo systemd-run --unit=xgw-w3b-safety --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py watch /run/xgw-w3b/current
sudo python3 -I /run/xgw-w3b/safety.py pulse /run/xgw-w3b/current
sudo systemd-run --unit=xgw-w3b-job --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py job /run/xgw-w3b/current enable "$HOME/zcod/xgw"
```

Снова каждые5с отдельный pulse/status из§3. После rc0: observe, pulse, probe, pulse — раздельно,
сохранять агрегаты и время в файлы `$HOME/xgw-w3b/`. Спросить владельца о новых подключениях.
`probe: connected` означает только принятие нового TCP-сокета; при TPROXY это мог быть локальный
Xray. Оно не доказывает TLS, получение тела или работоспособность внешнего сервера. Без фактических
новых подключений владельца и живого сеанса модели страховку не снимать. После enable проверить
cores/guard/capstate/check по одному, с pulse перед каждым, как ниже; это нужно и при отказе от
повторной установки on.
Если связь теряется — **не рассчитывать на следующую команду модели**: independent unit уже
вооружён. При возвращении связи только status/observe; RESTORED_OFF означает прерванный опыт,
не успешное включение. Не включать VPN повторно в этом прогоне.

Если30с связь стабильна и владелец разрешил повторную установку с VPN on, не снимать страховку:
сохранить результат enable и запустить **один** новый install-job, продолжая pulse каждые5с:

```bash
sudo cp /run/xgw-w3b/enable/job-result.json /run/xgw-w3b/enable/enable-result.json
sudo python3 -I /run/xgw-w3b/safety.py pulse /run/xgw-w3b/current
sudo systemd-run --unit=xgw-w3b-job --collect --property=TimeoutStopSec=2 /usr/bin/python3 -I /run/xgw-w3b/safety.py job /run/xgw-w3b/current install "$HOME/zcod/xgw"
```

После action=install, state=finished, rc0: capture_enabled=true, новые соединения и связь владельца работают; это проверка
сохранения режима при обновлении. Проверить `w3check.py` **по одному режиму**, с pulse перед
каждым: cores, guard, capstate, check. Guard существует, capability-наборы SB0, mismatchнет,
checkTrue. Если один вызов дольше15с, страховка может сработать: отметить ограничение/факт,
не выдавать отменённый прогон за дефект VPN и не повторять автоматически.

После подтверждения владельца и ещё30с стабильности при поддержании lease — disarm из§3,
status disarmed. Если владелец не хочет оставлять VPN on, не disarm: дать watchdog штатно
вернуть исходный off; после RESTORED_OFF и подтверждённой связи можно `sudo systemctl start xgw`.
Переустановка on при отсутствии согласия — NOT_RUN. Без неё D1 проверен только для off-установки.

## 5. Итог и отчёт

После disarmed либо RESTORED_OFF, без новых сетевых действий: сохранить времена, status/observe,
job-results и агрегаты старого помощника. **Не копировать snapshot, off.nft, job.log или строки
журнала в Git.** Ссылка на реальный отчёт старой wave3 остаётся в истории и не переписывается.

Файл: `docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3b-<ДАТА>.md`, по шаблону рядом.
Коммит «Отчёт: XGW 0.2.0, wave3b — установка и связь»; staging только этот обезличенный файл,
push в freepool по обычному согласованному порядку. При конфликте/грязном клоне STOP, без force.

D1 — сохранён ли on и проверено ли завершение установки; D2 — фактические carrier/operstate,
plain/marked и связь владельца. Carrier1 при неработающем plain не называть «отключён адаптер».
Множество rejects не определяет причину и не подтверждает блокировку конкретного приложения.
Полный E4/WAN-sentinel, старые scoped faults и10минутная нагрузка здесь NOT_RUN; волну3 целиком
не закрывать. Даже успешная страховка не доказывает устойчивость к любой неисправности сети.
