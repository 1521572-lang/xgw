# ThinkCentre — проверка прямого CDN до установки кандидата

**Ubuntu 24.04 LTS.** Flash сама запускает команды и при любом исходе
публикует отчёт. Если терминал, панель или sudo недоступны, запроси доступ.
Используй согласованное короткое окно на работающем шлюзе. Сбой прямого
CDN в предыдущих проходах останавливал приёмку до ротации. В r4 через
VPN наблюдался `302 → 302`, а минутой позже тот же URL вернул
`206/65536`. Это разные моменты измерения. Начни с двух отдельных
успешных проб CDN на установленной базе. [Отчёт r4](../reports/2026-11-21T003445Z_selective-route-status-r4.md)

## 1. База, тест помощника и таймер

В обычном чистом Bash выполни **§1 и первый блок §2 до таймера**
[MEDIA-PROOF r2](MEDIA-PROOF-2026-11-20-R2.md). Нужны сверка 11 файлов,
off/off, рабочий VPN, `VPN_BASELINE_CAPTURED` и приватный `VPN_FORMAT`.
Продолжай в том же Bash с `umask 077` и работающим `run` из §1.

```bash
CANDIDATE=39421a6f1f4e941ea774e43a00ff1d0b74e3c0d5
TRIAL_CODE=4c9379e964ee63c17a2731d82ad84aa9d2a8ee24
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
       -o addopts='' -p no:cacheprovider -q "$SRC/tests/test_selective_admission.py"; then
  echo TRIAL_TOOLS_READY
else
  echo TRIAL_TOOLS_BLOCKED
fi
```

После `TRIAL_TOOLS_READY` выполни **второй блок §1**
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
    env "PYTHONPATH=$SRC/src:$SRC" timeout -k 3 270 "$PY" -B -P \
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

## 2. Две прямые пробы на установленной базе

После `TRIAL_GUARDED` запусти блок. Настройки временно используют
60 секунд между проверками. Помощник засчитывает только разные штампы
успешных проб после включения Selective, по 206 и 65536 байт на одном
URL. Клиентское правило дополнительно сверяется в применённом Xray.
Записи receipt приватные и используются при возврате off.

```bash
INSTALL_OK=0
if xgw_trial_live &&
   run base-admission xgw_trial_panel admit "$D/base-receipt" \
       --format "$VPN_FORMAT" --checks 2 --timeout 180 &&
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

Если база дала таймаут, fallback или недостаточно подтверждений,
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

Включи `BASE_DIRECT`, число свежих проб и их интервалы, `INSTALL`,
`ADMISSION`, `STATUS`, `LIVE_PLAY`, `FLOW`, `RESTORE`. Публикуй
обезличенную сводку при любом исходе по §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) одним коммитом с суффиксом
`_selective-direct-preflight.md` в `integration/zapret2-batch1`.
Проверь наличие коммита в удалённой ветке и верни ссылку.
