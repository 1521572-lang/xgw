# T04/T12 — HTTPS-проверка YouTube CDN и смешанный маршрут

ThinkCentre, Ubuntu 24.04 LTS. Прочитай [отчёт Selective](../reports/2026-11-17_desync-selective-youtube.md).
Контрольный VPN подтверждён для Xray и sing-box. В двух наблюдавшихся сеансах
видео шло через SABR POST. GET на CDN дал 204 или 200 с 31 байтом, поэтому прежний
порог 16 КиБ оставил клиентское видео на VPN.

Новая опция `youtube_transport_probe` выключена по умолчанию. Она позволяет
проверить HTTPS до CDN перед открытием Selective. Первая проба страницы по-прежнему
требует ≥16 КиБ. Вторая строго ограничена HTTPS на `*.googlevideo.com/videoplayback`
и принимает завершившийся 200 или 204. Эти ответы подтверждают доступность HTTPS.
Длинное воспроизведение и истощение буфера проверяются отдельно в Chrome.

Исполнитель сама запускает команды и браузер, использует vision и автоматически
публикует отчёт. Если нет терминала, sudo или браузера, запроси доступ. При блокере
проведи независимые проверки и опубликуй частичный отчёт.

## 1. Снимок и обратимая установка

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor d11e60c "$CODE"
D=$(mktemp -d "$HOME/xgw-yt-transport.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest --portable tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_desync_schema.py tests/test_desync_route_evidence.py
```

До установки проверь диск и состояние обращения по старому WAN-захвату, который
уже занимал значимую часть раздела. Для этой проверки достаточно ограниченных
выгрузок Chrome и счётчиков. Новый WAN-захват не нужен. Сверь исходные off/off,
штатный VPN, панель, очередь, acct и offload. Используй один lock на сетевую фазу,
как в [предыдущем задании](T04-SELECTIVE-YOUTUBE.md#2-https-пробы-и-возврат).

Установку выполни по [схеме T05](T05-SYNACK.md#установка-четырёх-файлов-и-независимый-возврат).
Сверь `PACKAGE`, `PY`, `CFG` и `PANEL` по установленной службе. В prepare, apply
и rollback, в том числе внутри restore.sh, подставь флаг `--youtube-transport`.
Используй 45-минутный таймер, проверь его до apply. Прежний опыт ALT9 снял свой
слой, поэтому для четырёх существующих файлов исходной установленной версией
должен быть T09. Новые файлы могут отсутствовать.

```bash
BASE=e25b7a5
BASE_FILES=(src/xgw/config.py src/xgw/desync/schema.py src/xgw/zapret2.py
            src/xgw/watch/zapret2_control.py)
DEPS=(src/xgw/desync/flowseal.py src/xgw/desync/experiment.py)
FILES=("${BASE_FILES[@]}" "${DEPS[@]}")
UNIT=xgw-selective-youtube-transport-rollback
PAYLOAD="/opt/xgw/handoff/yt-transport-$CODE"
BACKUP="/var/lib/xgw/handoff/yt-transport-$CODE"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${FILES[@]}" docs/helpers/desync_batch1_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" "${BASE_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
for rel in "${DEPS[@]}"; do
  if sudo test -e "$PACKAGE/${rel#src/xgw/}"; then
    git archive d11e60c "$rel" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
  fi
done
```

Если prepare обнаружит другую базу, сверь происхождение установленного файла.
При неизвестной базе опубликуй блокер и оставь установленное приложение. После
apply проверь SHA, исходные конфиги, выключенный режим, доступ и свободную очередь.
Перед изменением политики создай `"$BACKUP/network-test-started"` и удостоверься,
что независимый возврат остаётся активен.

## 2. Строгий контроль и HTTPS CDN

В приватном `"$D/probes.json"` с 0600 укажи массив из двух HTTPS URL. Сначала
пригодная страница YouTube, затем фактический CDN-адрес из Network той же машины
с путём `/videoplayback`. Если запрос без подписанных параметров даёт 200 или 204,
используй его. Иначе попробуй свежий URL, на котором реальный GET дал 200 или 204
в прошлом опыте. Подпись не передавай в argv. Отметь HTTP-статус и пригодность в
режиме A. Истечение подписи и TLS-сбой ведут к повторной проверке или закрытию
маршрута. При недоступности обеих проб зафиксируй причину.

```bash
QUEUE=201
set_phase() {
  sudo env PYTHONPATH="$(dirname "$PACKAGE")" "$PY" - "$CFG" "$1" "$QUEUE" "$D/probes.json" <<'PY'
import json
import sys
from dataclasses import asdict
from pathlib import Path

from xgw import config, managed
from xgw.desync import schema
from xgw.desync.flowseal import YOUTUBE_DOMAINS

path, phase, queue, probes = sys.argv[1:]
assert phase in ("off", "strict", "transport")
path = Path(path)
cfg, _ = config.load(path)
policy = schema.migrate(asdict(cfg.zapret2))
policy["selected"].update(
    mode="off" if phase == "off" else "selective",
    strategy="multisplit", domains=list(YOUTUBE_DOMAINS),
    probe_urls=[] if phase == "off" else json.loads(Path(probes).read_bytes()),
    youtube_transport_probe=phase == "transport",
    check_seconds=300, retry_seconds=300, observe_synack=False, observe_reply_packets=0,
)
policy["runtime"]["queue_num"] = int(queue)
policy["engine"]["engine"] = "off"
policy = schema.migrate(policy)
managed.set_desync(managed.path_for(path), policy)
actual, _ = config.load(path)
assert schema.migrate(asdict(actual.zapret2)) == policy
PY
}
```

1. Сначала `set_phase strict`. Для короткого 204/200 прежний контроллер должен
   снять прямое правило. Сними `probe_failed` и факт продолжения VPN. Если CDN
   вернёт ≥16 КиБ, зафиксируй иной исход, без искусственной подмены.
2. Перейди через `off`, дождись освобождения очереди, затем `set_phase transport`.
   Дождись `active / youtube_transport_ok`, нового поколения и клиентского правила.
   В сыром статусе и API сверяй ревизию и свежесть. Карточка должна показать
   `evidence.transport=https_reachable`, `evidence.playback=not_tested`.
3. Если gate отказал, различи `youtube_page_probe_failed` и
   `youtube_cdn_probe_failed`. Можно обновить только соответствующий URL и
   повторить измерение. Уточни код, TLS и редирект. При недоступном XGW probe
   сравни штатную служебную проверку VPN с отдельным клиентским контролем.
4. Выполни отрицательный контроль с непригодным ответом CDN только если его можно
   получить от того же разрешённого хоста. Код 302/403, TLS-ошибка или истечение
   прямой проверки должны оставить новые соединения на VPN. Для неподходящего
   домена или пути ожидается отказ валидации ещё до применения политики.

## 3. Живой маршрут и проверка отказа

После открытия выполни [одновременные фазы Selective](T04-SELECTIVE-YOUTUBE.md#3-контроль-живая-фаза-и-отказ).
В этой версии вместо `probes_ok` ожидай `youtube_transport_ok`.

- До и после замеряй `xgw.desync.route_evidence snapshot/delta` с фактическим
  Xray-конфигом и одной эпохой процесса. Независимо сверь новые прямые исходящие
  соединения Xray к CDN, действующий gate и NFQUEUE. CDP должен показать свежие
  SABR POST с медиабайтами, обычный Chrome и vision — запуск и продвижение 720p.
- Во время того же просмотра замерь контрольный сайт через штатный VPN.
  Если доступны оба ядра, проведи отдельную фазу с нативным выходом Xray и
  с мостом sing-box. Паспортируй положительные байты на правильных подвыходах.
- При активном маршруте прерви только MainPID `xgw-zapret2.service`. Проверь
  снятие прямого правила и **новый** браузерный сеанс YouTube через VPN. Сверь
  служебный `vpn_control` и реальное видео отдельно. При стабильном результате
  прогони 15 минут 720p, перемотку и ещё 5 минут. Смотри NetLog, CDP и временные
  метки, чтобы раздельно оценить сетевой голод, паузу интерфейса и состояние gate.

Укажи также практическую границу опции. Успешный короткий CDN-ответ не видит
остановку SABR при живом HTTPS. Автоматический возврат этой версии реагирует
на сбой воркера и отказ проб. Автоматическое распознавание деградации плеера
остаётся отдельной работой в плане.

## 4. Возврат и отчёт

Вызови `set_phase off` и верни исходный panel через restore.sh. Выбери accept,
если установленный слой прошёл проверку и подтверждены обычный маршрут и off/off.
При дефекте верни файлы по флагу `--youtube-transport`. Проверь хэши, очередь,
VPN, панель, acct и offload, затем останови таймер и освободи lock.

```bash
ACTION=accept  # при дефекте используй rollback
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$ACTION"
sudo sha256sum -c "$D/config-before.sha256"
# Сначала сверь исходную политику и VPN.
sudo systemctl stop "$UNIT.timer"
flock -u 9
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/yt-transport-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-selective-youtube-transport.md"
# Сама запиши REPORT, даже если опыт остался частичным.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective YouTube HTTPS CDN gate on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Запиши точный SHA, результаты старого и нового gate, измерения обычного клиента
и VPN, факт rollback или accept, состояние системы после возврата. URL, подписи,
IP, приватные теги, конфиги и полные записи CDP остаются на машине. При гонке
сделай fetch, rebase и обычный push.
