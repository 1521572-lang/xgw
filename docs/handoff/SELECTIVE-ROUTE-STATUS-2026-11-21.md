# ThinkCentre — контроль CDN через VPN и статус Selective после ротации

Ubuntu 24.04 LTS. Flash сама выполняет техническую проверку и при любом
исходе публикует отчёт. При недоступном терминале, панели или sudo запроси
доступ у владельца. Начни с off/off, проверь обычный VPN. Замена участника
наблюдается при штатной работе watchdog. Используй согласованный с
владельцем короткий сеанс установки и проверяй обычный HTTPS до и после.

В первом проходе тесты, установка и откат прошли. Прямые пробы двух
CDN дошли до TLS-таймаута. Ранее в том же прогоне один из этих узлов
дал 206/65536 через VPN. Переход статуса при ротации не проверен.
В повторе одна штатная попытка Selective даёт измеримый результат и
при таком отказе. После снятия прямого правила контроллер проверяет
тот же URL CDN через VPN. [Первый отчёт](../reports/2026-11-20T224355Z_selective-route-status.md)

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
CANDIDATE=d4b9a7b7f9919808b9fb13662f9abe4e92f6eb97
OVERLAY=--selective-route-status
UNIT=xgw-selective-route-status-rollback
```

Выполни оба блока **§1** [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md)
из текущей ветки. Проверь, что в первом блоке сохранены эти переменные,
а в `WRITE_FILES` ровно шесть файлов. Этот вариант включает Applier,
sing-box generations, daemon, control, management и `zapret2.py`.
Control использует уже проверенный в CDN r2 метод management.
Шесть файлов должны совпасть
с контрольной базой на соответствующей стороне парного прогона. Включи
тесты с одним интерпретатором и обычными правами. После `WRITE_GATE_OK`
временная установка под guard допускается. Если блок установки вернул
ошибку, переходи к восстановлению по §4 r3 и публикации.

## 2. Один допуск Selective

Возьми определения `snapshot`, `live` и `writers` из первого
блока §2 [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md).
В том же Bash задай `FORMAT="$VPN_FORMAT"` и начни с off/off.
Из §2 [MEDIA-PROOF r2](MEDIA-PROOF-2026-11-20-R2.md) возьми
только блок сохранения настроек `if live && run before-settings off_status`.
Подтверди `SELECTIVE_SETTINGS_READY`. Используй один свежий URL,
проверенный через VPN. Переходи с off напрямую в Selective следующим
блоком. Предыдущий ручной Standalone и перебор IP пропусти.

```bash
if live && snapshot route-admission-before; then
  run route-admission timeout -k 3 125 "$PY" -u -B -P - <<'PY'
import http.client
import json
import time

from xgw.desync.client import Client

client = Client()
overview = "/api/zapret2/overview"
initial = client.request(overview)["zapret2"]
if not (initial["fresh"] and initial["policy_matched"]
        and initial["mode"] == initial["engine_mode"] == initial["state"] == "off"
        and initial.get("blockers", {}).get("selective") == []):
    raise SystemExit("settings_not_ready")
reply = client.request("/api/zapret2/mode", {
    "mode": "selective", "expected": initial["config_key"],
})
if reply.get("ok") is not True or not reply.get("config_key"):
    raise SystemExit("mode_rejected")

deadline = time.monotonic() + 105
while time.monotonic() < deadline:
    try:
        current = client.request(overview)["zapret2"]
    except (OSError, http.client.HTTPException, KeyError, ValueError):
        time.sleep(1)
        continue
    if current["config_key"] != reply["config_key"]:
        raise SystemExit("policy_changed")
    if (current["fresh"] and current["policy_matched"]
            and current["mode"] == "selective" and current["engine_mode"] == "off"):
        state = current["state"]
        evidence = current["evidence"]
        if ((state == "active" and evidence["transport"] == "https_reachable")
                or state in ("fallback", "blocked", "error")):
            cdn = evidence["transport_probes"].get("cdn", {})
            print(json.dumps({
                "state": state, "reason": current["reason"],
                "cdn_phase": cdn.get("phase"), "cdn_kind": cdn.get("kind"),
                "vpn_control": evidence.get("vpn_control"),
                "vpn_control_target": evidence.get("vpn_control_target"),
                "vpn_control_reason": evidence.get("vpn_control_reason"),
            }))
            break
    time.sleep(1)
else:
    raise SystemExit("admission_deadline")
PY
fi
```

- При `fallback` сними `snapshot route-admission-after` и подтверди
  `client_zapret2_rule=false`. Проверь обычный VPN. Значения
  `cdn_phase=tls, cdn_kind=timeout, vpn_control_target=cdn,
  vpn_control=pass` подтверждают доступность одного URL CDN через
  VPN после прямого отказа. DNS и фактический IP могли отличаться.
  `fail` означает отказ контрольного запроса. Для `not_run` укажи
  причину. Плеер и проверку ротации отметь `NOT_RUN` и перейди к §4.
- При `blocked`, `error`, дедлайне или отказе API опубликуй
  соответствующую фазу и перейди к §4. Одна попытка POST на одну
  ревизию. После потери ответа сверить состояние панели и восстановить.
- При `active` сними `snapshot route-admission-after`, проверь
  `client_zapret2_rule=true` и переходи к §3. При расхождении
  зафиксируй обе точки и перейди к §4.

## 3. Один просмотр и наблюдение до четырёх минут

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

## 4. Откат и публикация

Выполни **§4** [ТЗ записи r3](XRAY-CONFIG-WRITES-2026-11-20.md) с
исходными переменными. Подтверди SHA, файлы **6/6**, off/off,
выключение обоих воркеров, HTTPS через VPN и остановленный таймер.
Отметь `UNIT_TESTS`, `DAEMON_BASELINE`, `INSTALL`, `ADMISSION`,
`CDN_VPN_CONTROL` с `target/result/reason`, `STATUS`, `LIVE_PLAY`,
`FLOW`, `RESTORE` и время наблюдения.
Однозначно отдели наблюдение ротации на установленном кандидате от
прежних отчётов, адреса и приватные файлы сохрани на ThinkCentre.

При любом исходе опубликуй один обезличенный Markdown-отчёт в
`integration/zapret2-batch1` по блоку публикации §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md), с суффиксом
`_selective-route-status-r2.md`. Проверь коммит в удалённой ветке и
верни ссылку.
