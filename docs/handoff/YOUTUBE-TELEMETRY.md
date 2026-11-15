# Измерение реального плеера YouTube и медиатрафика

Открытая часть T04 и подготовка T09/H10. На Ubuntu **24.04 LTS** обычный Chrome уже
воспроизвёл ролик в 720p через Standalone без VPN в течение 15 минут и ещё 5 после перемотки.
Запущенный через Playwright браузер дал 31,9 с пригодного просмотра в VPN-калибровке и
около 2 мин в Standalone, где плеер дважды показал ошибку. Причина ошибки не установлена.
Для следующего длинного замера используй обычный Chrome из рабочего опыта.
[Отчёт T04](../reports/2026-11-15_desync-t04.md).

Исполнитель сама запускает команды, работает с браузером через vision и публикует отчёт.
Владелец не должен запускать скрипт или переписывать числа с экрана. Если недоступны терминал,
GUI или sudo для сетевого этапа T04, запроси доступ. В этой задаче GUI важен: headless не
считается эквивалентом живого воспроизведения и проверки декодирования.

## Замер в обычном Chrome

Обнови чистый checkout из `origin/integration/zapret2-batch1` и запиши полный SHA. Начни
с короткого измерения на работающем VPN в исходном режиме off/off, затем используй тот же
браузер для Standalone. Сбор веди в отдельном тестовом профиле пользователя рабочего стола.
Ролик `8plwv25NYRo`, 720p, скорость 1×. Закрой автопереход и оставь вкладку видимой.

```bash
set -euo pipefail
umask 077
REPO=$(git rev-parse --show-toplevel)
CODE=$(git rev-parse HEAD)
LAB=$(mktemp -d "$HOME/xgw-youtube-telemetry.XXXXXXXX")
VIDEO=8plwv25NYRo
CHROME=$(command -v google-chrome || command -v google-chrome-stable || command -v chromium)
open_trial() {
  TRIAL=$1
  mkdir "$LAB/$TRIAL"
  "$CHROME" --user-data-dir="$LAB/$TRIAL/profile" --no-proxy-server --disable-quic \
    --log-net-log="$LAB/$TRIAL/netlog.json" about:blank >"$LAB/$TRIAL/chrome.log" 2>&1 &
}
open_trial calibration-vpn
```

В DevTools открой Network, включи Preserve log, отключи эмуляцию скорости и оставь
обычный cache. Затем открой `https://www.youtube.com/watch?v=8plwv25NYRo` в этой вкладке.
Создай Snippet в Sources → Snippets. Сначала вставь содержимое
`docs/helpers/youtube_telemetry.js` из checkout, затем добавь в тот же Snippet этот код и
выполни его до Play. Оба фрагмента читают состояние вкладки и медиасобытия. Каждый замер
ограничен 30 минутами. После перезагрузки вкладки начни новый замер.

```js
(() => {
  if (window.__xgwCapture) return;
  const start = performance.now();
  const rows = [];
  const marks = [];
  const now = () => (performance.now() - start) / 1000;
  const sample = () => rows.push({
    ...window.__xgwTelemetry(),
    t_s: now(),
    unix: Date.now() / 1000
  });
  const timer = setInterval(sample, 1000);
  const stop = () => clearInterval(timer);
  setTimeout(stop, 30 * 60 * 1000);
  window.__xgwCapture = {
    rows, marks, stop,
    mark: name => marks.push({name, t_s: now(), unix: Date.now() / 1000})
  };
  sample();
})();
```

Поставь Play самой через GUI. Открой «Статистику для сисадминов» и сверь её с рядом.
В калибровке собери ≥60 с пригодного просмотра, паузу 10 с и перемотку минимум на минуту.
Сверь высоту кадра, порядок величины буфера и изменение dropped/total. Проверь, что пауза
исключена из сетевых остановок, а скачок позиции — из времени просмотра. Если ошибка видна
и в обычном Chrome, запиши точный текст, время и результат контроля через VPN.

Для основных этапов ставь метки в Console, например `__xgwCapture.mark("before-seek")`.
Используй `play`, `before-seek`, `after-resume` и `end`. Поставь метку `play` перед
запуском ролика, `before-seek` перед перемоткой и `after-resume` после возобновления.
Снимай часы шлюза по Unix в моменты начала и конца фаз. Перед закрытием окна в Console выполни
`__xgwCapture.stop(); copy(JSON.stringify({rows: __xgwCapture.rows, marks: __xgwCapture.marks}))`.
Вставь результат в локальный `$LAB/$TRIAL/player.json` через редактор и сохрани.
Построй сводку из уже имеющейся функции, без установки Playwright:

```bash
cd "$REPO"
python3 - "$LAB/$TRIAL/player.json" "$VIDEO" <<'PY'
import json
import sys
from pathlib import Path
from docs.helpers.youtube_telemetry import dump, summarize, write_report

source = Path(sys.argv[1])
run = json.loads(source.read_text(encoding="utf-8"))
rows = run["rows"]
assert rows, "empty player recording"
video = sys.argv[2]
summary = summarize(rows, video, 720)
marks = {mark["name"]: mark["t_s"] for mark in run["marks"]}
for stage, start, end in (("initial", "play", "before-seek"),
                          ("after_seek", "after-resume", "end")):
    if start in marks and end in marks and marks[start] < marks[end]:
        samples = [row for row in rows if marks[start] <= row["t_s"] <= marks[end]]
        summary[stage] = summarize(samples, video, 720)
summary.update(label=source.parent.name, outcome="recorded", video_id=sys.argv[2],
               marks=run["marks"])
dump(source.parent / "summary.json", summary)
write_report(source.parent, summary, rows)
print(json.dumps(summary, indent=2))
PY
```

К сверке добавь свежий медиазапрос в Network по фильтру `domain:*.googlevideo.com videoplayback`
и запиши его тип (GET/POST), статус, протокол и время. CDN IP нужен локально для сопоставления
с WAN. Перед сменой режима закрой только тестовое окно и дождись записи NetLog. Если нужно
пересмотреть запросы, сохрани приватный HAR из Network. В итоговой сводке укажи источник
медиабайтов: DevTools/NetLog либо счётчик Xray. В этой схеме CSV содержит показатели плеера.
Пустая колонка `media_encoded_bytes` ожидаема, сопоставь её сетевой эквивалент по времени
из NetLog или снимков счётчиков до и после каждой фазы. Экспорт целиком оставь на стенде.
[Snippets](https://developer.chrome.com/docs/devtools/javascript/snippets/),
[Console copy](https://developer.chrome.com/docs/devtools/console/utilities/#copy),
[Network](https://developer.chrome.com/docs/devtools/network/reference/),
[NetLog](https://www.chromium.org/for-testers/providing-network-details/).

### Standalone на уже установленном T04

Проверь XGW в off/off, живой исходный VPN, пустую очередь и неактивные worker. Найди
`PACKAGE`, `CFG`, `PANEL` и `PY` как в [T04](NEXT_STEP.md). Для исходной установки из
отчёта `BACKUP=/var/lib/xgw/handoff/desync-t04-ad81542b57b3dd765ed9c115b356c9dd306aae2b`.
Если после отчёта проводилась другая установка, используй её проверенный каталог.
Сверь установленные файлы с манифестом тех 12 файлов, которые оставили на машине.
Проверь `applier.py` по опубликованному хотфиксу. Старый каталог используй как источник
проверенного `restore.sh`. Сними свежую копию текущего panel и хэши перед любыми изменениями.

```bash
git show 1e27384:src/xgw/apply/applier.py | sha256sum
sudo sha256sum "$PACKAGE/apply/applier.py"
RESTORE_DIR=$(sudo mktemp -d /var/lib/xgw/handoff/youtube-telemetry.XXXXXXXX)
sudo cp --preserve=mode,ownership "$PANEL" "$RESTORE_DIR/panel.before"
sudo install -m 0700 "$BACKUP/restore.sh" "$RESTORE_DIR/restore.sh"
sudo sha256sum "$CFG" "$PANEL" > "$LAB/config-before.sha256"
sudo touch "$RESTORE_DIR/network-test-started"
ROLLBACK_UNIT="xgw-youtube-telemetry-$(date +%s)"
sudo systemd-run --unit="$ROLLBACK_UNIT" --on-active=40m /bin/bash \
  "$RESTORE_DIR/restore.sh" "$PY" unused "$RESTORE_DIR" "$PANEL" accept
sudo systemctl is-active "$ROLLBACK_UNIT.timer"
```

Режим `accept` в проверенном restore-скрипте возвращает сохранённый panel и выполняет
`xgw apply --now`. Аргумент `unused` занимает место установщика, который нужен только для
отката файлов. Если установленная база отличается, сначала сверь различия и состояние.
Выполни [set_standalone](NEXT_STEP.md#активация-standalone) с `hostfakesplit_md5` и теми же
доменами. Дождись активного gate и очереди, сверь applied Xray и VPN-мосты.

Запусти `open_trial standalone-hostfakesplit-md5-r1`. Запиши 15 минут просмотра и ещё 5
после перемотки по тому же сценарию. Отдельно
зафиксируй доступ к звуку. Сопоставь свежие запросы медиапотока, его WAN-выход, дельту
`xgw-zapret2.downlink` и очередь с метками фаз. Проверь остаток времени таймера перед
дополнительной проверкой и при необходимости перезаряди его.

По завершении выполни ту же команду восстановления непосредственно через `sudo /bin/bash`
с теми же аргументами. Сверь `sha256sum -c`, режим off/off, VPN-выход, очередь и offload,
после чего останови именно `$ROLLBACK_UNIT.timer`. Если тест прервался, запиши фактическое
состояние после срабатывания таймера.

Приёмка прибора требует ряда с калибровкой и замера 15+5 в обычном браузере, согласованного
с изображением и независимыми наблюдениями маршрута. Запиши пригодные секунды по каждой
фазе, разрывы, stall, буфер, dropped/total и качество. При неполном ряде опубликуй частичные
данные и конкретный блокер с пометкой `COLLECTOR_INCOMPLETE`.

## Что измеряет сборщик Playwright

`docs/helpers/youtube_telemetry.py` и соседний JS дают три ряда наблюдений:

1. Каждую секунду: позиция, фактический размер видео, буфер впереди текущей позиции,
   total/dropped frames, готовность, пауза, перемотка, реклама, скрытое окно, mute/volume.
   События play/playing/waiting/stalled/seeking/seeked/error сохраняются с временем браузера.
2. CDP Network: реальные GET **и POST** к `*.googlevideo.com/videoplayback`, HTTP-статусы,
   h2/h3/http1, серверный IP, начало/ответ/завершение/ошибка. Байты учитываются и у ещё не
   завершённого SABR-запроса, через dataReceived. Тела и подписанные URL не воспроизводятся.
3. При `--status-file`: небольшой разрешённый набор полей исходного status.json XGW,
   возраст снимка, состояния selected/engine и capture. Это сведения демона, не доказательство
   того, что конкретный видеопоток прошёл через нужную очередь и WAN.

При открытой «Статистике для сисадминов» дополнительно читаются Connection Speed,
Buffer Health и Codecs. Селекторы/названия YouTube могут измениться; отсутствие этих полей
не ломает стандартные метрики HTMLVideoElement. Сверь совпадение вручную через vision.
Mystery Text и sCPN не используются как публичный API и не сохраняются.

Файлы:

| Файл | Содержимое |
|---|---|
| run.json | Условия, версия браузера, время, метка опыта и завершение сборщика |
| samples.jsonl | Плеер + события, накопленные сетевые счётчики и снимок шлюза каждую секунду |
| network.jsonl | Разрешённые поля медиазапросов, включая POST и незавершённые потоки |
| timeline.csv | Числа для графика буфера, разрешения, кадров и медиабайтов |
| summary.json / summary.md | Агрегаты, покрытие измерения и явные UNKNOWN для маршрута/эффекта |

В network.jsonl остаются CDN host/IP: файл оставь приватным на стенде. Cookie, Authorization,
подписанные query, POST body, заголовки и общий HAR не записываются. В отчёт GitHub достаточно
таблицы агрегатов и коротких обезличенных фрагментов. Полные конфиги/pcap не публикуй.

## Дополнительная диагностика в Playwright

При разборе ошибки можно повторить короткий запуск Playwright по исходной инструкции.
Запиши версию Playwright и браузера, условия прогона, время ошибки и покрытие измерений.
Для длительного замера используй сценарий обычного Chrome выше.
[Инструкция запуска Playwright](https://github.com/1521572-lang/xgw/blob/4ab4a745ddf492a4f4940d4f83794ad4b5ecd0cd/docs/handoff/YOUTUBE-TELEMETRY.md#подготовка-и-запуск-исполнителем).

## Последующее сравнение тактик H05/H10

- Контроль VPN подтверждает, что ролик/браузер вообще работоспособны.
- Контроль «direct без обработки» допустим только при уже подготовленном изолированном
  прямом пути с доказанным отсутствием VPN. **Off XGW может означать VPN**, а остановленный
  worker standalone закрывает выбранные домены; оба случая непригодны как direct-baseline.
  Если такого пути пока нет, direct-baseline=NOT_RUN, causal benefit=NOT_ESTABLISHED.
- hostfakesplit-md5 и выбранный кандидат запускать попеременно A/B/B/A либо A/B/A/B,
  по два прохода каждый, в новых профилях. Только в разрешённом сетевом окне и после T04.
  Для первого результата достаточно T04; не задерживай его отчёт всей матрицей кандидатов.
- Одинаковые ролик, целевое качество, скорость 1x, браузер/версия/кодек, сеть, QUIC-политика,
  длина интервала. Зафиксируй смену CDN, рекламу, ошибки входа и CPU/GPU. Начальное ожидание,
  setup, паузы и перемотки учитывай отдельно. Не сравнивай 480p с 1080p одной цифрой скорости.
- Для итоговой таблицы: eligible/playing, доля времени ≥целевого качества, stall count/seconds,
  waiting events, p10/median буфера, dropped/total, media bytes, HTTP errors, protocol,
  подтверждённый маршрут, визуальный результат, звук и ограничения.

Оценки stalls по секундам не захватывают все короткие остановки; для них есть события waiting.
stalled HTMLMediaElement — задержка получения данных, не обязательно остановка видео.
Пропуски кадров с большим буфером могут указывать на декодирование/отрисовку; это гипотеза,
проверяемая CPU/GPU/codec и временным рядом. Connection Speed не равна тарифной скорости.
Автоматического победителя нет: сначала покрытие и маршрут, затем воспроизведение и A/B.

## Отчёт и публикация без дополнительного подтверждения

Создай `docs/reports/YYYY-MM-DD_youtube-telemetry.md`. Включи в него дополнительные проверки
T04, если они выполнены. Укажи ревизионные SHA ТЗ и установленного кода, версию браузера,
условия каждого прогона, контрольные сверки, фактические измерения и ограничения.
Исходный режим шлюза восстанови по T04, частичный результат и блокер также публикуй.
Не используй формулировку «владелец запустил»: все действия выполняет сама модель.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/youtube-telemetry-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_youtube-telemetry.md"
# Сама создай REPORT с фактическими результатами; укажи CODE и оставленное состояние.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: report YouTube telemetry on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch/rebase и обычный push, не force. В финале укажи SHA отчёта.
Локальные точечные исправления прибора разрешены с повторной проверкой и отдельным коммитом.

Основание: [YouTube debug info](https://support.google.com/youtube/answer/7519898),
[Media Playback Quality](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/getVideoPlaybackQuality),
[buffered](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/buffered),
[waiting](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/waiting_event),
[Playwright CDPSession](https://playwright.dev/python/docs/api/class-cdpsession),
[CDP Network](https://chromedevtools.github.io/devtools-protocol/tot/Network/).
