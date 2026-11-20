# ThinkCentre — маршрут конкретного медиасоединения T12

Исполнитель Flash выполняет проверку на Ubuntu 24.04 LTS сам. При отсутствии
терминала, доступа к журналу systemd или панели запроси недостающий доступ.
Команды ниже подготовлены Codex. Результат и обезличенные числа опубликуй
в GitHub после прохода при любом исходе.

В пересчёте initial 42 из 42 совпадений сокетов и очереди дали ровно
нулевой downlink zapret2. Рост общего счётчика Xray в тех же интервалах
не даёт привязки к плееру. В seek есть одно полное совпадение. Проверка
повторяет только старт воспроизведения и сопоставляет TCP-соединения
mpv с конкретными записями маршрута Xray. Исторические JSONL не содержат
локального порта, поэтому старому initial оставляем PARTIAL.
[Пересчёт](../reports/2026-11-20T105122Z_selective-counter-replay.md) ·
[Живой отчёт r2](../reports/2026-11-20T103848Z_selective-media-proof-r2.md)

## 1. Подготовка и контроль VPN

В одном Bash выполни `1 и контроль VPN из `2
[принятого ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md), до блока запуска таймера.
Сохрани тот же shell до завершения восстановления. На текущей сессии
ThinkCentre все проверки `sudo -v` в r2 и здесь выполняй через
`sudo -n true`. Если это не проходит и sudo требует вход, авторизуйся
в терминале с TTY и повтори проверку.
До старта должны быть подтверждены исходные off/off и свежий VPN-контроль.

Проверка читает существующий журнал `xgw-xray.service` лишь для PID
из снимка и короткого интервала. Временные записи mpv остаются
локальными с правами 0600. Запускай строго по одному плееру.
[Откуда Xray берёт входящий TCP-адрес](https://github.com/XTLS/Xray-core/blob/v26.3.27/proxy/tun/handler.go#L95-L125) ·
[Где записывается выбранный outbound](https://github.com/XTLS/Xray-core/blob/v26.3.27/app/dispatcher/default.go#L475-L491)

Выполни следующий блок в том же shell, пока off/off и временная политика
ещё не включалась. Он записывает отдельную короткую фазу VPN и подтверждает,
что текущий формат журнала годится для сопоставления.

```bash
TRACE_CODE=c9d39fbdcdc92778389c2a619f4411226f2d60e0
TRACE="$D/flow-source"

trace_tree() {
  git -C "$REPO" fetch origin "$BR" &&
    git -C "$REPO" merge-base --is-ancestor "$TRACE_CODE" FETCH_HEAD &&
    git -C "$REPO" worktree add --detach "$TRACE" "$TRACE_CODE"
}
trace_python() {
  env PYTHONPATH="$TRACE/src:$TRACE" "$PY" -B -P "$@"
}
trace_playback() {
  local label=$1 media=$2 begin until pid
  snapshot "$label-route-before" || return
  pid=$(trace_python -c 'import json, sys
with open(sys.argv[1]) as stream:
    print(int(json.load(stream)["xray_epoch"].split(":")[1]))' "$D/$label-route-before.json") ||
    return
  begin=$(date +%s) || return
  run "$label-player" timeout 155 env PYTHONPATH="$TRACE/src:$TRACE" "$PY" -B -P \
    -m docs.helpers.headless_playback "$media" play --seconds 120 --peers \
    --samples "$D/$label-player.jsonl" >&2
  snapshot "$label-route-after" || return
  until=$(date +%s) || return
  timeout 15 sudo -n journalctl --quiet --no-pager --unit=xgw-xray.service "_PID=$pid" \
    --since "@$begin" --until "@$((until + 1))" --lines 5000 --output=json \
    --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT |
    trace_python -m docs.helpers.selective_flow_evidence --player "$D/$label-player.jsonl" \
      --before "$D/$label-route-before.json" --after "$D/$label-route-after.json"
}

if sudo -n true && run trace-tree trace_tree && run trace-vpn-off off_status "$D/trace-off.json"; then
  run flow-vpn trace_playback flow-vpn "$VPN_FORMAT"
fi
```

Посмотри обезличенный `$D/flow-vpn.out` и сводку
`$D/flow-vpn-player.out`. Для положительного контроля нужны
`client_zapret2_rule=false`, работающий плеер и хотя бы одно
совпадение `groups.xray` или `groups.sing-box`. Если совпадений нет,
зафиксируй `BLOCKED_LOGS` с причиной или `CONTROL_FAIL` при отказе плеера.
Заверши публикацией. Политику включай только после положительного контроля.

## 2. Один старт в Selective и восстановление

Выполни оставшуюся часть `2 [ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md)
с общим lock и таймером. Используй уже принятый профиль и свежий
формат, зарегистрированный штатным способом. Подтверди
`fresh/matched/active/https_reachable`. Пропусти `3 и `4 r2, в этом
проходе вместо них выполняется один старт плеера.

```bash
if sudo -n true && live && run trace-selective-state "$PY" -m xgw.desync.client status; then
  if trace_python -c 'import json, sys
with open(sys.argv[1]) as stream:
    v = json.load(stream)
assert v["fresh"] and v["policy_matched"]
assert (v["mode"], v["engine_mode"], v["state"]) == ("selective", "off", "active")
assert v["evidence"]["transport"] == "https_reachable"' "$D/trace-selective-state.out"; then
    run flow-selective trace_playback flow-selective "$FORMAT"
    run trace-selective-end "$PY" -m xgw.desync.client status
  fi
fi
```

При любом исходе после включения выполни `5
[ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md). До снятия таймера подтверди
SHA файлов настроек, off/off, работоспособность демона и закрытие
прямого правила. При отказе зафиксируй оставшееся состояние и сообщи
владельцу. Сохрани `RESTORE` в отчёте.

## 3. Критерии и публикация

- `FLOW=ZAPRET2`, `VPN` или `MIXED`, если записи Xray сопоставлены с
  тестовыми TCP-соединениями mpv, и обе границы окна в той же ревизии
  Selective active с `client_zapret2_rule=true`. Для `ZAPRET2` или
  `VPN` все пригодные соединения должны получить один вид маршрута.
  Для `MIXED` нужны подтверждённые потоки обоих видов. Укажи отдельно
  число пригодных и неидентифицированных соединений.
- `PARTIAL` при неполном совпадении, изменении ревизии/состояния
  или найденном `other`. `INCONCLUSIVE`, если сопоставления отсутствуют
  или журнал обрезан. Совпадение Xray означает выбор выходного
  обработчика для этого TCP-соединения. Работу медиа подтверждает
  сводка плеера отдельно.
- Если повтор пошёл к другому CDN, отметь это без IP и оставь вывод
  о старом initial открытым. Совпадение на повторе относится к этому
  интервалу. VPN fallback и окно seek учитываются по принятому отчёту r2.

Опубликуй один обезличенный Markdown-отчёт при любом исходе. Укажи SHA
анализатора, Ubuntu, итог VPN-контроля, сводку плеера по обеим фазам,
`qualified_flows`, группы, причины отсутствия совпадений и `RESTORE`.
Публикуй только численные агрегаты и коды. Для коммита и push используй
блок из `3 [ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md), заменив
суффикс имени на `_selective-flow-evidence.md`. Проверь, что коммит
доступен в ветке `integration/zapret2-batch1`, и верни ссылку.
