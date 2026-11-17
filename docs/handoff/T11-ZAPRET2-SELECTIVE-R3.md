# T11.3 r3 — техническая приёмка Selective и диагностики HTTPS

Исполнитель — Flash на ThinkCentre с Ubuntu 24.04 LTS. Сама запускай команды
и браузер, используй vision для проверки экрана. При отсутствии терминала,
sudo или GUI запроси доступ. Код, тесты и установщик подготовил Codex.
Работа Flash ограничена проверками, возвратом шлюза и публикацией отчёта.
При сбое запиши шаг, наблюдение и состояние машины. Код, тесты и пороги
исправляет Codex по опубликованному результату.

Коммит для проверки — `a8b177f6deec1e2c20c4effef977bf144bdf4f24`.
База установки — `6f69cc278868bae07ae58c484b8f5b728ada1c29`, к которой привёл
откат r2. [Отчёт r2](../reports/2026-11-17_desync-zapret2-management-r2.md)
подтвердил M01–M13 и Standalone (181 с 720p, частичная привязка пути медиа).
Selective дважды отказал на пробе страницы. Повтор прервал таймер. В r3
повтори только перечисленные ниже проверки.

## 1. Подготовка на реальной машине

В одном сеансе bash, из чистого checkout:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=a8b177f6deec1e2c20c4effef977bf144bdf4f24
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t11-selective-r3.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
df -h /home /var/lib/xgw
systemctl show xgw.service -p MainPID -p ActiveState -p ExecStart
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json > "$D/config-original.sha256"
python3 -m pytest -q tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_zapret2_management.py tests/test_zapret2_management_linux.py \
  tests/test_desync_route_evidence.py \
  tests/test_panel.py::test_zapret2_overview_uses_panel_session_and_limits_state \
  tests/test_panel.py::test_zapret2_commands_require_session_origin_and_revision \
  tests/test_desync_schema.py::test_deploy_refuses_drift_before_stopping_service \
  tests/test_desync_schema.py::test_partial_deploy_failure_restores_old_files_and_restarts
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_install.sh
bash -n docs/helpers/t11_management_restore.sh
```

Если pytest доступен в прежнем dev-venv, используй его Python. Падение теста
или недоступное окружение — остановка до установки с результатом в отчёте.
Исходное состояние — off/off, неактивные воркеры, пустая очередь, VPN и панель
работают. Если работающий режим изменился, запроси окно проверки. Сверь рабочие
пути по ExecStart и GUI dispatcher с путями из установщика. До установки
подготовь браузер и профиль, проверь контрольную страницу через VPN и запиши её
наблюдаемый выход приватно. Свежую CDN-ссылку получи перед включением Selective.

## 2. Установка и проверка таймера

Overlay из 8 файлов. Базовый каталог `/opt/xgw/lib/xgw` содержит
`watch/panel.py`, `watch/zapret2_control.py`, новый `watch/zapret2_management.py`,
`ui/zapret2.html`, `ui/zapret2.css`, `ui/zapret2.js` и `zapret2.py`. Восьмой
файл — `src/xgw/gui/zapret2.py` внутри принятого Proton-релиза `7c20f59…`.
Установщик сверяет базу, ставит таймер возврата на 90 минут и применяет overlay.
Несовпадение базы — BLOCKED_BASE с именем файла. Повторный запуск поверх
того же каталога запрещён самим установщиком. При ошибке после apply — раздел 6.

```bash
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/zapret2-management-$CODE"
BACKUP="/var/lib/xgw/handoff/zapret2-management-$CODE"
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
UNIT=xgw-zapret2-management-rollback
bash docs/helpers/t11_management_install.sh "$CODE"
PY=$(sudo cat "$BACKUP/python.path")
date -u +%FT%TZ
systemctl list-timers "$UNIT.timer" --no-pager
sudo sha256sum -c "$D/config-original.sha256"
verify_manifest() {
  sudo "$PY" - "$BACKUP" "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path
rows = json.loads((Path(sys.argv[1]) / "manifest.json").read_text())
assert len(rows) == 8
for row in rows:
    path = Path(row["target"])
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    assert actual == row[sys.argv[2] + "_sha"], path
    print(path, actual)
PY
}
verify_manifest new
```

Запиши NEXT/LEFT и UTC. Перед сетевой фазой нужно ≥30 мин, перед дополнительным
длинным опытом ≥35 мин. Оставь последние 10 минут на возврат. Если окна не хватает,
верни состояние и укажи пропущенные шаги. При срабатывании таймера прекрати тест
и подтверди `restore-completed`, хэши и работу VPN. Таймер активен до сверки.

## 3. Изменения интерфейса при off/off

1. Заново открой `xgw gui` от пользователя. Сверь доступность панели/VPN.
   В веб-карточке обе новые строки показывают «Нет данных». В `/api/state`
   и `/api/zapret2/overview` `evidence.transport_probes={}`. В обеих темах при
   ширине 390 px строки остаются читаемыми, горизонтального переполнения нет.
2. В веб-форме проверь выбранную стратегию и сохранение настройки retry при off/off.
   Дождись новой ревизии, сверь её в двух API и настройки в Proton. Наблюдай
   inactive у обоих воркеров. При ошибке GUI, записи или целостности начни возврат.

## 4. Selective и две HTTPS-пробы

Тестовый Chrome должен захватываться XGW. QUIC отклоняется, исключения
устройства и пула не перекрывают YouTube. Веди проверку через UI, счётчики и
наблюдение Chrome. Новый tcpdump этому заданию не нужен.

```bash
LOCK_ROOT=${XDG_RUNTIME_DIR:-$HOME}
exec 9>"$LOCK_ROOT/xgw-t09-live.lock"
flock -n 9
sudo systemctl is-active "$UNIT.timer"
systemctl list-timers "$UNIT.timer" --no-pager
sudo touch "$BACKUP/network-test-started"
snap() {
  sudo env PYTHONPATH="$PYTHONPATH" python3 -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
delta() {
  python3 -m xgw.desync.route_evidence delta "$D/$1.json" "$D/$2.json"
}
snap initial
```

1. В off сохрани `multisplit`, проверку YouTube/CDN и шесть доменов
   `domain:youtube.com`, `domain:googlevideo.com`, `domain:youtubei.googleapis.com`,
   `domain:youtube-nocookie.com`, `domain:ytimg.com`, `domain:ggpht.com`.
   Первая ссылка — `https://www.youtube.com/watch?v=8plwv25NYRo`, вторая — свежая
   подписанная HTTPS CDN `/videoplayback` из DevTools тестового Chrome. Вводи
   обе через форму. Проверь `saved`, count=2 и отсутствие подписанной ссылки
   в ответе, двух GET и на экране. Нажми «Домены через zapret2» и подтверди.
   Жди первый итог до 120 с. Запиши UTC, текущую ревизию, state/reason,
   `evidence.transport_probes`. Сверь ok, phase, kind, http, connect_http,
   bytes и elapsed_ms. Проверь, что VPN остаётся работоспособным.
2. Развилки первого результата:
   - При `youtube_page_probe_failed` есть неуспешная page, CDN отсутствует,
     интерфейс сообщает «Не запускалась». Проверь отсутствие прямого правила
     для клиентов и новый запрос через VPN. Выключи режим кнопкой.
   - При `youtube_cdn_probe_failed` page прошла, CDN показывает свой отказ,
     прямого правила для клиентов нет. Проверь VPN и выключи режим кнопкой.
   - При `active/youtube_transport_ok` две строки успешны и правило активно.
     Page должна получить ≥16 КиБ, CDN — завершённый HTTP 200/204.
     `transport=https_reachable`, `playback=not_tested`. Переходи к разделу 5.
   - При другом отказе запиши точную причину и маршрут. Если возврат на VPN
     не подтверждён, сразу раздел 6. Если VPN работает, заверши сетевую фазу.
3. После off разрешён один повтор. При отказе page возьми
   `https://www.youtube.com/t/terms` и ту же свежую CDN-ссылку. Если CDN истёк,
   обнови и укажи, что изменилась пара, а не только страница. При отказе CDN
   возьми прежнюю страницу и свежую CDN. Заполни обе ссылки. Повтори включение
   и запиши обе строки. Если подходящей ссылки нет — BLOCKED_PROBE.
4. Для каждого отказа сохрани фазу, код, время и байты, даже если загрузка из
   Chrome работает. В live-запросах не меняй код, схему, пороги или настройки
   маршрута вручную. При смене ревизии прежние строки должны исчезнуть до
   нового результата.

## 5. Видео и одновременный VPN-контроль

Используй [готовый замер обычного Chrome](YOUTUBE-TELEMETRY.md#замер-в-обычном-chrome),
только запись и сводку. Ролик `8plwv25NYRo`, 720p вручную, 1×, видимая вкладка.
Запусти сниппет, нажми Play, подтверди кадр и движение позиции через vision.
Перед интервалом `snap selective-before`. После `snap selective-after` и
`delta selective-before selective-after > "$D/selective-delta.json"`.

Цель — ≥150 с пригодного 720p. Запиши паузы, буфер, stalls, свежие SABR-запросы
DevTools Network/CDP и дельты Xray/NFQUEUE в том же интервале. Одновременно
загрузи контрольный сайт в браузере и сверяй его VPN-выход с исходным. Отдельно
оцени наличие VPN-маршрута и доступность сайта. Общий счётчик Xray не заменяет
браузерный контроль. Без привязки медиа к прямому пути — MEDIA_PATH=PARTIAL.

При успешном коротком опыте и остатке таймера ≥35 минут выполни 15 минут
пригодного просмотра, перемотку минимум на 6 минут и ещё 5 минут. Раздели фазы
метками плеера и парами счётчиков. При нехватке окна длинный опыт NOT_RUN.
Закрой тестовый Chrome после экспорта. Пауза UI исключается из времени просмотра.

## 6. Выключение и возврат

Выключи выбранный режим кнопкой. Проверь `policy_matched/off`, пустой
`transport_probes` и новый запрос YouTube через VPN. Если управление, диагностика
и возврат исправны, оставь код и верни исходный panel побайтово. Недоступную
пробу отрази отдельным результатом. При регрессии выполни rollback кода.

```bash
# При исправном коде:
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" accept
# При регрессии вместо accept:
# sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
sudo systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
if sudo test -e /proc/net/netfilter/nfnetlink_queue; then
  sudo cat /proc/net/netfilter/nfnetlink_queue
fi
```

Выполни `verify_manifest new` при accept или `verify_manifest old` при rollback.
Заново открой Proton от пользователя. Проверь off/off, пустую очередь, VPN и
панель 200 и новый запрос контрольного браузера. Затем
`sudo systemctl stop "$UNIT.timer"`. При ошибке возврата сообщи её и запроси
доступ для необходимой диагностики. После потери сеанса восстанови переменные
из раздела 2 по закреплённому CODE, PY бери из `python.path`. При ошибке
установки после apply PY также бери из `python.path`.

## 7. Автопубликация отчёта

Укажи SHA, хэши установки, время таймера в UTC, результаты тестов и интерфейса,
диагностику обеих попыток, воспроизведение, проверку маршрута, одновременный
VPN-контроль и финальное состояние. Отметь PASS, FAIL, BLOCKED либо NOT_RUN
для каждого этапа. URL, IP, токены, конфиги, HAR и NetLog оставь приватно.
Даже при блокере опубликуй только новый файл отчёта.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t11-selective-r3-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-zapret2-selective-r3.md"
# Заполни REPORT по фактам выполнения.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective HTTPS diagnostics on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push. Сверь удалённый SHA, сообщи
ссылку на отчёт и фактическое состояние шлюза.
