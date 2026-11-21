# ThinkCentre — один повтор CDN на базе и разбор сохранённых потоков

**Ubuntu 24.04 LTS.** Flash сама запускает команды и при любом исходе
публикует отчёт. Если терминал, панель или sudo недоступны, запроси доступ.
Используй согласованное короткое окно на работающем шлюзе. Сбой прямого
CDN в предыдущих проходах останавливал приёмку до ротации. Последняя
проверка базы завершилась после первого TLS-таймаута. На базе
`3a00777` контроль `control=pass` относится к первому адресу пары,
то есть к странице YouTube через VPN. Для CDN есть отдельная проба
`206/65536` до включения Selective. В этом проходе после первого
таймаута ждём один штатный повтор watchdog. [Отчёт о проверке базы](../reports/2026-11-21T062220Z_selective-direct-preflight.md)

## 1. База, тест помощника и таймер

В обычном чистом Bash выполни **§1**
[MEDIA-PROOF r2](MEDIA-PROOF-2026-11-20-R2.md). Нужны сверка 11 файлов,
off/off и рабочий VPN. Продолжай в том же Bash с `umask 077` и
работающим `run` из §1.

```bash
CANDIDATE=39421a6f1f4e941ea774e43a00ff1d0b74e3c0d5
TRIAL_CODE=f79eec88370ae273abca7d36d684dc967b870a5f
SRC="$D/route-trial"
OVERLAY=--selective-route-status
UNIT=xgw-selective-route-status-rollback
WRITE_FILES=(src/xgw/apply/applier.py src/xgw/apply/singbox_generation.py
             src/xgw/daemon.py src/xgw/watch/zapret2_control.py
             src/xgw/watch/zapret2_management.py src/xgw/zapret2.py)
DEFINE_WRITE_TRACE_ONLY=1
TEST_PY=${XGW_TEST_PYTHON:-$PY}

xgw_trial_source() {
  git -C "$REPO" fetch origin "$BR" &&
    git -C "$REPO" merge-base --is-ancestor "$TRIAL_CODE" FETCH_HEAD &&
    git -C "$REPO" merge-base --is-ancestor "$CANDIDATE" "$TRIAL_CODE" &&
    git -C "$REPO" worktree add --detach "$SRC" "$TRIAL_CODE" &&
    git -C "$SRC" diff --quiet "$CANDIDATE" HEAD -- src/xgw
}
if run trial-source xgw_trial_source &&
   run trial-helper-unit env "PYTHONPATH=$SRC/src:$SRC" "$TEST_PY" -m pytest \
       -o addopts='' -p no:cacheprovider -q "$SRC/tests/test_selective_admission.py" \
       "$SRC/tests/test_selective_probe_watch.py"; then
  echo TRIAL_TOOLS_READY
else
  echo TRIAL_TOOLS_BLOCKED
fi
```

### Сохранённые окна

После `TRIAL_TOOLS_READY` разберись с окнами `writer-media` и
`flow-r2b`, пока не менялась политика. Этот короткий разбор выполняется
даже при последующем блокере линии. Используй сохранённые пары снимков
и JSONL плеера. Команда ищет их в приватных каталогах опытов в домашней
папке. Она выбирает одну пару для каждого имени. При нескольких парах
сверь окно с исходными [отчётом записи](../reports/2026-11-20T181622Z_xray-config-writes-r3.md)
и [отчётом CDN r2](../reports/2026-11-20T124752Z_selective-cdn-update-r2.md).

```bash
xgw_replay_saved() {
  local prefix=$1 label=$2 bounds boot pid begin end
  bounds=$("$PY" -I - "${prefix}-route-before.json" "${prefix}-route-after.json" <<'PY'
import json, math, sys
from pathlib import Path
from uuid import UUID
a, b = (json.loads(Path(p).read_bytes()) for p in sys.argv[1:])
boot, pid, _ = a["xray_epoch"].split(":")
assert a["xray_epoch"] == b["xray_epoch"] and int(pid) > 0
assert 0 < b["unix"] - a["unix"] <= 180
print(UUID(boot).hex, int(pid), math.floor(a["unix"]), math.ceil(b["unix"]) + 1)
PY
  ) || return
  read -r boot pid begin end <<<"$bounds"
  timeout -k 2 12 sudo -n journalctl --quiet --no-pager -b "$boot" -u xgw-xray.service "_PID=$pid" \
    --since "@$begin" --until "@$end" -n 5000 -o json \
    --output-fields=MESSAGE,_PID,_BOOT_ID,_SYSTEMD_UNIT >"$D/$label-journal.jsonl" || return
  [[ -s "$D/$label-journal.jsonl" ]] || return 2
  env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P -m docs.helpers.selective_flow_evidence \
    --observe-applied-change --player "${prefix}-player.jsonl" \
    --before "${prefix}-route-before.json" --after "${prefix}-route-after.json" \
    <"$D/$label-journal.jsonl"
}
for label in writer-media flow-r2b; do
  saved=$(find "$HOME" -maxdepth 3 -type f -path "*/xgw-*/$label-route-before.json" -print -quit)
  if [[ -n $saved ]]; then
    run "replay-$label" xgw_replay_saved "${saved%-route-before.json}" "$label"
  else
    result "replay-$label" NOT_AVAILABLE
  fi
done
```

Сообщи `REPLAY`, `state` и поле `logged_zapret2`, если оно есть.
Положительный счётчик означает точное сопоставление сокета плеера
с записью о принятии на выделенный outbound zapret2 в том же процессе
Xray. Оценка всего изменившегося окна остаётся `inconclusive`.
Нулевой счётчик означает отсутствие подтверждённых совпадений.
Если артефакты или журнал уже недоступны, укажи ограничение.
Сырые данные остаются в приватных каталогах.

### Контроль VPN и подготовка отката

Выполни первый блок §2 [MEDIA-PROOF r2](MEDIA-PROOF-2026-11-20-R2.md)
до таймера. Для живой части нужны `VPN_BASELINE_CAPTURED` и приватный
`VPN_FORMAT`. Затем выполни **второй блок §1**
[ТЗ записи Xray](XRAY-CONFIG-WRITES-2026-11-20.md). При
`DEFINE_WRITE_TRACE_ONLY=1` он определяет функции установки и
восстановления. Для точного SHA `39421a6` засчитывается подтверждённый
в r4 результат writer-unit 109/109, route-unit 134/134, route-rebuild
1/1 и парного гейта без новых или изменившихся отказов. В этом проходе
проверяется совпадение `src/xgw`, а helper сверит шесть установленных
файлов с исходной базой перед любым изменением политики. При несовпадении
останови приёмку и зафиксируй контроль, который не прошёл.

```bash
if exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run trial-lock flock -n 9 && sudo -n true && run trial-stage prepare_write_trace &&
   sudo -n systemctl is-active --quiet "$UNIT.timer" &&
   sudo -n touch "$BACKUP/network-test-started"; then
  echo TRIAL_GUARDED
else
  echo TRIAL_BLOCKED
fi

xgw_trial_live() {
  sudo -n systemctl is-active --quiet "$UNIT.timer" &&
    sudo -n test -f "$BACKUP/network-test-started" &&
    sudo -n test ! -e "$BACKUP/restore-completed"
}
xgw_trial_panel() {
  xgw_trial_live &&
    env "PYTHONPATH=$SRC/src:$SRC" timeout -k 3 440 "$PY" -B -P \
      -m docs.helpers.selective_admission "$@"
}
xgw_route_snapshot() {
  sudo -n env "PYTHONPATH=$PAYLOAD/code/src" "$PY" -B -P \
    -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
xgw_check_direct_rule() {
  "$PY" -I -c 'import json,sys
with open(sys.argv[1]) as f:
    if json.load(f)["client_zapret2_rule"] is not True:
        raise SystemExit("client_rule_absent")' "$D/$1.json"
}
xgw_wait_off() {
  local attempt
  for attempt in {1..20}; do
    off_status "$1" && workers_off && return 0
    sleep 2
  done
  return 2
}
```

## 2. Прямые пробы на установленной базе

После `TRIAL_GUARDED` запусти блок. Настройки временно используют
60 секунд между проверками. Помощник засчитывает только разные штампы
успешных проб после включения Selective, по 206 и 65536 байт на одном
URL. Первый CDN TLS-таймаут позволяет дождаться одного штатного
повтора в том же режиме. Счётчик успешных проб после таймаута начинается
заново. Повторный TLS-таймаут или истечение 360 секунд завершают проверку.
Клиентское правило дополнительно сверяется в применённом Xray.
Записи receipt приватные и используются при возврате off.

```bash
INSTALL_OK=0
if xgw_trial_live &&
   run base-admission xgw_trial_panel admit "$D/base-receipt" \
       --format "$VPN_FORMAT" --checks 2 --recover-cdn-once --timeout 360 &&
   run base-rule xgw_route_snapshot base-ready &&
   run base-rule-check xgw_check_direct_rule base-ready &&
   run base-off xgw_trial_panel off "$D/base-receipt" &&
   run base-off-confirmed xgw_wait_off "$D/base-off.json" &&
   xgw_trial_live &&
   run write-install install_write_trace &&
   run candidate-off xgw_wait_off "$D/candidate-off.json"; then
  INSTALL_OK=1
  echo CANDIDATE_INSTALLED
else
  echo TRIAL_STOPPED
fi
```

Если база завершила окно с fallback или недостаточно подтверждений,
отметь `BASE_DIRECT=UNSTABLE` с причиной и перейди к §4.
Укажи, успел ли запускаться `write-install`. При недоступности панели
или ошибке установки зафиксируй соответствующий блокер.
До `CANDIDATE_INSTALLED` переход в §3 закрыт.

## 3. Просмотр и наблюдение ротации на кандидате

После `CANDIDATE_INSTALLED` используй тот же URL в сохранённых
настройках. Запусти один POST для кандидата, снимок правила и переход
к окну плеера только при подтверждении допуска.

```bash
CANDIDATE_READY=0
if [[ $INSTALL_OK == 1 ]] && xgw_trial_live &&
   run candidate-admission xgw_trial_panel admit "$D/candidate-receipt" \
       --checks 1 --timeout 160 &&
   run candidate-rule xgw_route_snapshot candidate-ready &&
   run candidate-rule-check xgw_check_direct_rule candidate-ready; then
  CANDIDATE_READY=1
fi
```

При fallback или таймауте кандидатского допуска сохрани оба результата
раздельно по времени, проверь обычный VPN и перейди к §4. В отчёте
поля `attempts[].redirect.http` и `attempts[].http` означают исходный
и конечный HTTP-код соответственно. Два значения 302 вместе с
`hop_limit` подтверждают два редиректа. Подписанные адреса остаются
на машине.

При `CANDIDATE_READY=1` возьми определения `trace_python` и
`trace_playback` из [ТЗ медиапотока, §1](MEDIA-FLOW-2026-11-20.md).
Для журнала писателей определи функцию `writers` из §2
[ТЗ записи Xray](XRAY-CONFIG-WRITES-2026-11-20.md). Используй блок:

```bash
TRACE="$SRC"
XGW_SNAPSHOT_FUNCTION=xgw_route_snapshot
if [[ $CANDIDATE_READY == 1 ]] && xgw_trial_live && xgw_route_snapshot route-status-before; then
  run route-status-watch timeout -k 3 255 sudo -n env \
    "PYTHONPATH=$PAYLOAD/code/src:$PAYLOAD/code" "$PY" -B -P \
    -m docs.helpers.selective_route_status_watch --seconds 240 &
  WATCH_PID=$!
  run route-status-player trace_playback route-status-player "$VPN_FORMAT"
  wait "$WATCH_PID"
  if xgw_route_snapshot route-status-after; then
    PYTHONPATH="$SRC/src:$SRC" run route-status-writers writers \
      "$D/route-status-before.json" "$D/route-status-after.json"
  fi
  run route-status-vpn site
fi
```

Оцени `STATUS`, `LIVE_PLAY`, `FLOW` по критериям §3
[ТЗ статуса r4](SELECTIVE-ROUTE-STATUS-2026-11-21.md). В частности,
если в окне не наблюдалась ротация, пиши `STATUS=NOT_EXERCISED`.
Для `PASS` нужны `route_reconcile` и следующее `active_with_rule`
после штатной записи `daemon_rebuild`. В обеих фазах сохрани
обычный HTTPS через VPN.

## 4. Восстановление и публикация

Если есть непустой receipt последнего запуска и активен guard,
попробуй возврат off командой `xgw_trial_panel off "$D/candidate-receipt"`
или с `base-receipt`, если активировалась только база. При отказе
сразу выполни восстановление. Выполни §4
[ТЗ записи Xray](XRAY-CONFIG-WRITES-2026-11-20.md) с текущими переменными.
При опыте только на базе guard восстанавливает политику. После попытки
установки он также возвращает файлы оверлея. Подтверди SHA настроек,
6/6 файлов базы, off/off, остановленные воркеры, таймер и обычный VPN.

Включи `REPLAY`, `BASE_DIRECT`, число свежих проб и их интервалы, `INSTALL`,
`ADMISSION`, `STATUS`, `LIVE_PLAY`, `FLOW`, `RESTORE`. Публикуй
обезличенную сводку при любом исходе по §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) одним коммитом с суффиксом
`_selective-recovery-replay.md` в `integration/zapret2-batch1`.
Проверь наличие коммита в удалённой ветке и верни ссылку.
