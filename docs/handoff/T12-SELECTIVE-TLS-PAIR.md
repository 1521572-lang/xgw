# T12 — TLS к одному CDN по WAN и через Selective

ThinkCentre, Ubuntu 24.04 LTS. Код a2eb600dfe86ea9becd133e74672d3ad36fd7ff1. В последнем отчёте обе
проверки CDN завершились таймаутом TLS на одном IPv4. Прямое TCP-соединение к
этому адресу установилось за 51 мс. У помеченного сокета Xray были отправленные
и подтверждённые байты, входящих байтов в выборке не было. Следующий опыт
сравнивает TLS к одному имени и IPv4 в общем временном окне.
[Отчёт Flash](../reports/2026-11-18_desync-t12-selective-media-pairs.md).

Исполнитель сам запускает команды в терминале, вводит данные в панель и
публикует отчёт. При отсутствии терминала, sudo или GUI запроси доступ.
Проверку веди в отдельное окно от приёмки нового GUI. Код запускается из
checkout, штатный демон использует установленную версию. Прямой контроль
отправляет TLS ClientHello с домашнего WAN, получает и проверяет сертификат.
Он закрывает сокет без HTTP-запроса. Снимки счётчиков ограничены по времени.

## 1. Исходное состояние и возврат

Проверь работу панели и обычного сайта через VPN, свежий off/off и
неактивность обоих воркеров. Если исходное состояние другое, запиши блокер
и переходи к отчёту. Начни в checkout проекта в Bash.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=a2eb600dfe86ea9becd133e74672d3ad36fd7ff1
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-tls-pair.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
"${XGW_TEST_PYTHON:-$PY}" -m pytest -q tests/test_selective_probe_watch.py \
  tests/test_desync_schema.py
bash -n docs/helpers/t11_management_restore.sh
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
sudo cmp "$PACKAGE/zapret2.py" src/xgw/zapret2.py
sudo cmp "$PACKAGE/watch/checks.py" src/xgw/watch/checks.py
sudo cmp "$PACKAGE/ui/zapret2.js" src/xgw/ui/zapret2.js
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Тесты ожидаются без падений и пропусков. Для pytest подойдёт существующий
dev-venv через $XGW_TEST_PYTHON. При несовпадении файлов сообщи, какой
файл отличается. Для этого прохода достаточно принятого установленного
кода и помощника из checkout.

До сохранения проб в панели поставь таймер возврата.

```bash
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
UNIT="xgw-selective-tls-pair-$(date +%s)"
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
BACKUP=$(sudo mktemp -d /var/lib/xgw/handoff/selective-tls-pair.XXXXXXXX)
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 docs/helpers/t11_management_restore.sh "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=60m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
```

## 2. Контроль TLS и одна штатная попытка Selective

В отдельном Chrome с выключенным QUIC возьми свежий HTTPS URL
/videoplayback из DevTools, его hostname и Remote Address. URL сохрани только
в панели. Для первой попытки можешь взять IPv4 из предыдущего опыта, если
hostname совпал. Иначе используй наблюдавшийся IPv4 из DevTools. Это кандидат
для сопоставления. Имя CDN передавай в нижнем регистре, без схемы, порта или
пути. Если доступна только IPv6 или имя не относится к googlevideo.com,
отметь отсутствие подходящего адреса.

Сохрани совместимый с прошлым опытом набор настроек в off/off. Используй
multisplit, шесть доменов YouTube, интервал проверки 120 с, HTTPS-опцию,
страницу /t/terms и свежий URL CDN. Проверь отсутствие blockers.selective.
Закрой все вкладки плеера, чтобы по времени различить служебный сокет и видео.

```bash
read -r -p 'WAN interface: ' WAN
read -r -s -p 'CDN hostname: ' CDN_HOST; printf '\n'
read -r -s -p 'CDN IPv4: ' PEER; printf '\n'
read -r -p 'Selected NFQUEUE number: ' QUEUE
wan_tls() {
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_wan_control.py \
    --wan "$WAN" --peer "$PEER" --tls-host "$CDN_HOST" "$@"
}
observe_attempt() {
  local name=$1
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds 110 --socket-stats >"$D/$name-watch.jsonl" &
  WATCH_PID=$!
  wan_tls --during-selective 90 >"$D/$name-pair.json" 2>"$D/$name-ready.log" &
  PAIR_PID=$!
  for _ in {1..40}; do
    if test -s "$D/$name-watch.jsonl" && grep -q '^READY:' "$D/$name-ready.log"; then
      printf 'Наблюдатели готовы. Включи Selective в панели.\n'
      return 0
    fi
    sleep 0.25
  done
  printf 'Наблюдатели не готовы. Проверь локальные файлы.\n' >&2
  return 1
}
sudo -v
wan_tls >"$D/first-direct.json"
observe_attempt first
```

Включи Selective кнопкой после сообщения о готовности. Запиши время клика.
При fallback зафиксируй причину и результат VPN-контроля. При active запиши
итоги первой проверки CDN. Этот проход измеряет служебный TLS и завершает
попытку после появления результата.

```bash
wait "$PAIR_PID"
wait "$WATCH_PID"
```

В файле --during-selective сигнал matched означает новый помеченный сокет
к заданному IPv4, ESTAB, со счётчиком отправленных данных. В отчёте сопоставь
его с фазой CDN, временем и gate из наблюдателя. Первый сокет уже открытый
до старта наблюдения исключён. Если сокет не появился или найдено несколько
одновременно, WAN-запрос в этой фазе не отправляется.

```bash
NAME=first
"$PY" - "$D" "$NAME" <<'PY'
import json
import sys
from pathlib import Path

root, name = Path(sys.argv[1]), sys.argv[2]
pair = json.loads((root / f"{name}-pair.json").read_text())
direct = json.loads((root / f"{name}-direct.json").read_text())
rows = [json.loads(line) for line in (root / f"{name}-watch.jsonl").read_text().splitlines()]
print(json.dumps({"direct": direct, "pair": pair}, ensure_ascii=False))
socket_id = pair["trigger"].get("socket", {}).get("socket")
reported = set()
for row in rows:
    cdn = row["probes"].get("cdn")
    if cdn and cdn["started_at"] not in reported:
        reported.add(cdn["started_at"])
        print(json.dumps({"revision": row["revision"], "state": row["state"], "cdn": cdn}))
    sockets = [sock for sock in row.get("tcp", {}).get("sockets", [])
               if socket_id is None or sock["socket"] == socket_id]
    if sockets:
        print(json.dumps({"tcp_at": row["tcp_at"], "gate": row["gate"],
                          "invocation": row["worker_invocation"], "sockets": sockets}))
PY
```

Вывод приватный. Для сопоставимости нужны тот же hostname, IPv4 и интервал
одной CDN-пробы. Если есть first_tls_timeout_ms, граница первого запроса
равна started_at + first_tls_timeout_ms / 1000, конец второго равен
started_at + elapsed_ms / 1000. Укажи, в каком запросе был сопоставлен сокет.
Используй общий интервал WAN TLS и наблюдений того же сокета в этой фазе.
Сверь, что gate отмечал рабочую фазу, control_route и selective_route дали
тот же WAN-интерфейс, шлюз и предпочитаемый исходный адрес, а
source_matches_lookup подтверждён. Если результат успел появиться раньше
замера или привязка осталась неоднозначной, укажи конкретную причину.

Разрешён один дополнительный запуск после выключения Selective. Он нужен,
если в первом окне выбрали другой IPv4 или промахнулись по времени. По
локальным данным укажи IPv4, однозначно соответствующий фактическому сокету
CDN. Если обновляешь подписанный URL, сверь также hostname. При новом имени
и неопределённом IP отметь результат как несопоставимый.

```bash
read -r -s -p 'CDN hostname for repeat: ' CDN_HOST; printf '\n'
read -r -s -p 'CDN IPv4 for repeat: ' PEER; printf '\n'
sudo -v
wan_tls >"$D/second-direct.json"
observe_attempt second
```

После сообщения о готовности повтори клик, обе команды wait и локальный
разбор с NAME=second.

| Наблюдение | Что записать |
|---|---|
| WAN TLS успешно проверил сертификат, одновременно Selective дал TLS-таймаут | Подтверждена разница путей в этом окне. Приведи входящие байты помеченного сокета и ретрансляции. Участок потери ответа пока открыт. |
| Оба пути истекли на TLS | Срыв воспроизведён на прямом контроле. Укажи интервалы, исход TCP и наблюдавшийся IPv4. |
| Selective дошёл до HTTP | Запиши HTTP-результат или успешную пробу. Раздельно отметь исход WAN. |
| Разные адреса, неизвестное совпадение по времени, ошибка сертификата или TCP | Запиши факты и недостающее условие. Результат TLS по этому окну несопоставим. |

## 3. Возврат и автоматическая публикация

Выключи Selective. Подтверди свежий off/off, остановку воркеров и новый рабочий
сеанс YouTube на VPN. Закрой тестовый Chrome. Дождись завершения обоих
наблюдателей, если попытка прервалась. Оставь 10 минут на возврат.

```bash
sudo /bin/bash "$BACKUP/restore.sh" "$PY" unused "$BACKUP" "$PANEL" accept
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Сверь обычный сайт, панель и off/off после возврата. При успехе останови таймер
sudo systemctl stop "$UNIT.timer". Если таймер уже сработал, сверь
restore-completed и хэши в сохранённом каталоге.

В отчёте укажи CODE, версию ОС, результаты тестов, стадии TCP/TLS для обоих
путей, факт совпадения hostname/IP и интервалов, локальные счётчики в числах,
результат сравнения и статус возврата. MEDIA_PATH относится к отдельному
измерению трафика плеера. Укажи MEDIA_PATH=NOT_RUN для этого задания.
Используй нейтральные обозначения адресов и сокетов. IP, hostname CDN,
подписанный URL, маршруты и сырые JSON не публикуй.

Опубликуй только обезличенный отчёт даже при блокере. Если подготовка
прервалась до создания $D, задай REPO через git rev-parse --show-toplevel,
BR=integration/zapret2-batch1 и D=$(mktemp -d).

```bash
cd "$REPO"
git fetch origin "$BR"
git worktree add --detach "$D/report" FETCH_HEAD
cd "$D/report"
REPORT="docs/reports/$(date +%F)_desync-t12-selective-tls-pair.md"
# Здесь создай отчёт с фактическими наблюдениями.
git add -- "$REPORT"
git diff --cached --check
git diff --cached --stat
git commit -m "docs: compare WAN and Selective TLS on ThinkCentre"
git push origin "HEAD:refs/heads/$BR"
git ls-remote origin "refs/heads/$BR"
```

Если ветка продвинулась, перенеси коммит отчёта на свежий FETCH_HEAD и
выполни обычный push. Если по тому же пути уже опубликован чужой отчёт,
сохрани оба файла под разными именами.
