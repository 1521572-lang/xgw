# T12 — проверка счётчиков Selective и длинный прогон

На ThinkCentre с Ubuntu 24.04 LTS оставлен слой r3 `a8b177f`. Flash прошла
два коротких прогона 720p и одновременный VPN-контроль. Сборщик отклонил
три пары снимков. В отчёте описана перезапись JSON Xray. Требуется
установить причину по новым диагностическим полям и подтвердить путь медиа.
[Отчёт r3](../reports/2026-11-17_desync-zapret2-selective-r3.md).

Код проверки — `bec3009f0ed36a0f12add909d42f04472eff9240`.
Flash запускает опубликованные команды и тесты, выполняет проверку
браузера через vision, возвращает шлюз и публикует отчёт. При отсутствии
терминала, sudo или GUI запрашивает доступ. Исправления делает Codex.
Сборщик запускается из закреплённого checkout. Установленный слой r3
сверяется по манифесту и используется для управления режимом.

## 1. База, тесты и исходный снимок

Из чистого checkout, в одном сеансе bash:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=bec3009f0ed36a0f12add909d42f04472eff9240
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-selective.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest -q tests/test_desync_route_evidence.py tests/test_zapret2.py \
  tests/test_zapret2_panel.py
df -h /home /var/lib/xgw
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
R3=a8b177f6deec1e2c20c4effef977bf144bdf4f24
INSTALLED="/var/lib/xgw/handoff/zapret2-management-$R3"
sudo python3 - "$INSTALLED/manifest.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads(Path(sys.argv[1]).read_text())
assert len(rows) == 8
for row in rows:
    path = Path(row["target"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["new_sha"], path
PY
PANEL=$(readlink -f /etc/xgw/panel.json)
CFG=$(readlink -f /etc/xgw/config.toml)
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" python3 -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  python3 -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
snap vpn-before
```

Если pytest доступен в прежнем dev-venv, используй его Python. При
расхождении манифеста, падении тестов или недоступности метрик зафиксируй
блокер до переключения режима. Исходное состояние — off/off, неактивные
воркеры, VPN и панель работают. Проверь обычный сайт и внешний VPN-выход
в тестовом Chrome. Сверь, что этот браузер захватывается XGW, QUIC
отключён, правила устройства и пула не перекрывают эксперимент.
Сделай `snap vpn-after` после короткого воспроизведения через VPN
и `delta vpn-before vpn-after >"$D/vpn-control.json"`. Сохрани локально
подписанный CDN-адрес из Network. Перед этапом Selective проверь свежесть.

## 2. Возврат и включение Selective

Подготовь браузер и измерения до запуска таймера. Для этого раунда
сохрани свежий panel, взятый с машины после проверки исходного off/off.
Известный скрипт возврата используется с действием `accept`, чтобы
восстановить настройки и применить их к работающему шлюзу.

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-evidence.XXXXXXXX)
UNIT="xgw-selective-evidence-$(date +%s)"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 docs/helpers/t11_management_restore.sh "$BACKUP/restore.sh"
sudo touch "$BACKUP/network-test-started"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" /usr/bin/python3 unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
systemctl list-timers "$UNIT.timer" --no-pager
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" >"$D/restore-location.txt"
```

Включи Selective через форму по [разделу 4 r3](T11-ZAPRET2-SELECTIVE-R3.md#4-selective-и-две-https-пробы).
Используй `multisplit`, HTTPS-проверку YouTube/CDN и шесть доменов r3.
В поле «Проверка каждые, с» поставь 120, чтобы короткий замер пересёк
как минимум одну повторную пробу.
Для подтверждения запуска нужны `policy_matched=true` и
`active/youtube_transport_ok`. Если проба отказала, выполни одну замену
по ветвлению r3, затем зафиксируй результат и в случае повторного отказа
верни шлюз. Таймер держи активным, оставляй 10 минут на возврат.

## 3. Дельты и подтверждение маршрута

1. При active сними пару фоновых снимков за 20–30 секунд с закрытым
   плеером. Затем проведи опыт с видео минимум 150 секунд пригодного
   720p. Для записи используй [готовый сниппет и сводку](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome).
   Верхний раздел запуска браузера и телеметрия применимы. Смена режимов
   выполняется по этому ТЗ через веб-панель.
2. В каждой фазе сохрани снимки в начале, после очередной проверки
   HTTPS, в конце и при смене состояния. Момент повторной пробы виден
   по переносу срока `zapret2.valid_until` примерно на 120 с в
   `/run/xgw/status.json`. Возьми `snap media-start`,
   `snap media-checkpoint`, `snap media-end`. Перед каждым снимком отметь
   UTC и позицию видео. Сохрани счётчики очереди, хэндл правила и PID
   воркера в начале и конце:

   ```bash
   sudo nft -a list chain inet xgw_guard zapret2_queue >"$D/queue-start.txt"
   sudo cat /proc/net/netfilter/nfnetlink_queue >"$D/nfq-start.txt"
   systemctl show xgw-zapret2.service -p MainPID >"$D/worker-start.txt"
   ```

   Повтори эти три команды в конце с суффиксом `-end`. Разницу очереди
   считай при совпадении хэндла, номера и владельца. Проверь, что новое
   соединение к адресу CDN из CDP действительно идёт на ожидаемом пути.
   Во время медиапередачи локально сохрани `sudo ss -Hntp dst "$CDN_IP"`
   для замеченного адреса и сопоставь с Xray. Не публикуй адрес, счётчики
   отдельных клиентов или списки VPN-узлов.
3. Выполни для соседних пар и отдельно для полного интервала:

   ```bash
   for pair in "media-start media-checkpoint" "media-checkpoint media-end" "media-start media-end"; do
     read -r first last <<<"$pair"
     if delta "$first" "$last" >"$D/$first--$last.delta.json"; then
       printf 'Accepted %s %s\n' "$first" "$last"
     else
       printf 'Rejected %s %s\n' "$first" "$last"
     fi
   done
   ```

   При `config_bytes_changed=true` успешная дельта фиксирует подтверждённый
   сценарий переформатирования, если семантические хэши равны. Сравнивать
   только JSON этого раунда. При отклонении запиши поле `field` и частоту
   отказов. `xray_epoch` означает смену процесса, `applied_config` —
   изменение конфигурации или клиентского правила. Если один снимок
   попал на применение, повтори его через 3 секунды один раз и запиши
   перенос границы фактического измерения. Отказ между соседними точками
   исключает доказательство непрерывности по одной лишь полной паре.
4. В том же интервале загрузи обычный сайт вне списка zapret2 и проверь
   VPN-выход в браузере. Запиши прирост директ и VPN по группам отдельно.
   Для `MEDIA_PATH=CONFIRMED` нужны сопоставимые дельты, прирост NFQUEUE
   при том же владельце, свежая передача CDN с наблюдаемым путём и
   успешный параллельный контроль VPN. Сравни с фоном служебных проб.
   При неоднозначности маршрута, смене поколения или недоступном
   счётчике укажи `MEDIA_PATH=PARTIAL` и конкретную недостающую привязку.
5. При рабочем Selective и остатке таймера ≥35 минут начни длинный
   прогон. Нужны 15 минут пригодного просмотра, перемотка минимум на
   6 минут и ещё 5 минут просмотра 720p. Сними отдельные дельты и параметры
   плеера до перемотки и после возобновления. В обеих фазах выполни
   VPN-контроль. Если таймер оставляет меньше 10 минут, начни возврат.

## 4. Выключение, возврат и публикация

Выключи режим кнопкой. Проверь свежий off, отсутствие клиентского правила,
неактивные воркеры, пустую очередь и новый сеанс YouTube через VPN. Короткая
отрицательная проверка инструмента — попытайся сравнить `vpn-before` с
`media-start` при пройденном Selective. Должен быть
`incomparable_snapshots` из-за смены Xray либо клиентской конфигурации.

```bash
sudo /bin/bash "$BACKUP/restore.sh" /usr/bin/python3 unused "$BACKUP" "$PANEL" accept
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Подтверди off/off в панели, работу VPN и одновременную доступность обычного
сайта и панели. Затем `sudo systemctl stop "$UNIT.timer"`. При истечении
таймера прекрати тест, проверь `restore-completed` и выполни эту же
финальную сверку. Если сеанс потерян, пути записаны в `restore-location.txt`.
При ошибке возврата запроси необходимый доступ и опиши состояние.

Опубликуй только новый отчёт. Укажи SHA, результат каждой фазы, число
валидных и отклонённых пар с причинами, совокупные дельты, длительности
видео и результат возврата. Для каждого шага используй PASS, FAIL,
BLOCKED или NOT_RUN. URL, IP, конфиги и сырые выгрузки остаются приватными.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-evidence-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-route-evidence.md"
# Заполни REPORT по фактам, включая блокеры и состояние шлюза.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective route counters on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch/rebase и обычный push. Сверь удалённый SHA и сообщи
ссылку на отчёт.
