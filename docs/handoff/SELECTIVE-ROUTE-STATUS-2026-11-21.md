# ThinkCentre — статус Selective после замены участника VPN

Ubuntu 24.04 LTS. Flash сама выполняет техническую проверку и при любом
исходе публикует отчёт. При недоступном терминале, панели или sudo запроси
доступ у владельца. Начни с off/off, проверь обычный VPN. Замена участника
наблюдается при штатной работе watchdog. Используй согласованный с
владельцем короткий сеанс установки и проверяй обычный HTTPS до и после.

В r3 `daemon_rebuild` сопоставлен с заменой участника. В отдельном
пассивном окне off/off за 180 с увидели одну атомарную замену файла и
событие `apply` в пределах 10 мс. В сохранённых окнах с Selective
исполнитель встретил `active` одновременно с отсутствием клиентского
правила. Кандидат ниже публикует `pending/route_reconcile` для этого
состояния. После успешной пересборки без правила watchdog сразу
получает запрос на следующий шаг. Контроллер подтверждает маршрут
своими штатными проверками. [Отчёт r3](../reports/2026-11-20T181622Z_xray-config-writes-r3.md) · [Пассивный отчёт](../reports/2026-11-20T182412Z_xray-writer-readonly.md)

## 1. Обязательные тесты и установка

Выполни вводные **§1 и VPN-контроль §2 до таймера** из
[ТЗ MEDIA-PROOF r2](MEDIA-PROOF-2026-11-20-R2.md). Сверь 11 файлов
установленной базы и сохрани свежий `VPN_FORMAT` с ровно 206/65536.
Затем в том же Bash задай:

```bash
CANDIDATE=93d87f196e11e20f6748a80c0978fbb5c0b623ff
OVERLAY=--selective-route-status
UNIT=xgw-selective-route-status-rollback
```

Выполни оба блока **§1** [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md)
из текущей ветки. Проверь, что в первом блоке сохранены эти переменные,
а в `WRITE_FILES` ровно пять файлов. Этот вариант включает Applier,
sing-box generations, daemon, control и management. Control использует
уже проверенный в CDN r2 метод management. Пять файлов должны совпасть
с контрольной базой на соответствующей стороне парного прогона. Включи
тесты с одним интерпретатором и обычными правами. После `WRITE_GATE_OK`
временная установка под guard допускается. Если блок установки вернул
ошибку, переходи к восстановлению по §4 r3 и публикации.

## 2. Один просмотр и наблюдение до четырёх минут

Выполни §2 [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md). Возьми
`FORMAT="$VPN_FORMAT"` и начни с off/off. После положительного контроля
допуска подтверди `fresh=true, policy_matched=true, active,
https_reachable` перед стартом пары. Обычный HTTPS через VPN продолжает
работать. Если CDN из VPN через прямой путь не прошёл, запиши фазу,
код и причину, вернись к off/off и заверши восстановление.

Из §3 [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md) возьми определения
`trace_python` и `trace_playback` по ссылке и используй следующий блок
вместо одиночной фазы. Параллельно работают только плеер и наблюдатель
файлов. Вся запись пройдёт в приватном каталоге опыта.

```bash
TRACE="$SRC"
if live && snapshot route-status-before; then
  run route-status-watch timeout -k 3 255 sudo -n env \
    "PYTHONPATH=$PAYLOAD/code/src:$PAYLOAD/code" "$PY" -B -P \
    -m docs.helpers.selective_route_status_watch --seconds 240 &
  WATCH_PID=$!
  run route-status-player trace_playback route-status-player "$FORMAT"
  wait "$WATCH_PID"
  if snapshot route-status-after; then
    run route-status-writers writers "$D/route-status-before.json" "$D/route-status-after.json"
  fi
  run route-status-vpn site
fi
```

- Запиши счётчики `active_with_rule`, `route_reconcile`,
  `active_without_rule`, `unreadable`. Наблюдатель считает
  `active_without_rule` только при статусе, записанном позднее
  версии конфига. Параллельный опрос может пропустить короткую
  промежуточную публикацию.
- `STATUS=PASS` при наблюдаемом `route_reconcile` после нормальной
  пересборки и последующем `active_with_rule`, если ни один свежий статус
  не показал `active_without_rule`. Сообщи время между этими точками и
  число записей `daemon_rebuild` и `zapret2_route`. Если пересборку или
  промежуточное состояние не наблюдали, отметь `STATUS=NOT_EXERCISED`.
  Свежий `active_without_rule` означает `STATUS=FAIL`.
- Запиши плеер и `FLOW` отдельно. Если смена конфига сделала снимки
  несопоставимыми, укажи `changed_sections` и учти этот интервал как
  `inconclusive`. Источник записи берётся из отчёта writers при
  подтверждённой привязке. Запись без привязки к итоговому снимку
  остаётся наблюдением журнала.

## 3. Откат и публикация

Выполни **§4** [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md) с
исходными переменными. Подтверди SHA, файлы **5/5**, off/off,
выключение обоих воркеров, HTTPS через VPN и остановленный таймер.
Отметь `UNIT_TESTS`, `DAEMON_BASELINE`, `INSTALL`, `ADMISSION`,
`STATUS`, `LIVE_PLAY`, `FLOW`, `RESTORE` и время наблюдения.
Однозначно отдели наблюдение ротации на установленном кандидате от
прежних отчётов, адреса и приватные файлы сохрани на ThinkCentre.

При любом исходе опубликуй один обезличенный Markdown-отчёт в
`integration/zapret2-batch1` по блоку публикации §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md), с суффиксом
`_selective-route-status.md`. Проверь коммит в удалённой ветке и
верни ссылку.
