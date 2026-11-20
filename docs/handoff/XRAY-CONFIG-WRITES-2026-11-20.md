# ThinkCentre — кто применяет конфигурацию Xray во время просмотра, r3

Flash проводит проверку и публикует один обезличенный отчёт при любом
исходе. Рабочая машина — Ubuntu 24.04 LTS. При недоступном терминале,
панели или sudo запроси нужный доступ у владельца и продолжи сама.
Пакет временный. Сценарий и код подготовлены Codex.

Первый проход завершён. Определения для тестов, установки и отката
используются также в [проверке статуса после ротации](SELECTIVE-ROUTE-STATUS-2026-11-21.md).

В [живом отчёте](../reports/2026-11-20T124752Z_selective-cdn-update-r2.md)
прошли форма, валидация, атомарная замена CDN и 135,1 секунды видео в
720p. В двух окнах изменились `routing`, `inbounds` и `outbounds` Xray
при том же PID. Причина перезаписи осталась открытой. В этом проходе
нужно сопоставить успешную запись конфига с точными границами снимков.
Замеры CDN-формы, fallback и суточное наблюдение здесь уже не повторяются.

В [r2](../reports/2026-11-20T160055Z_xray-config-writes-r2.md)
прошёл обязательный набор, включая три исправленных теста Applier.
Полная проверка демона остановилась на 12 изменившихся диагностических
сообщениях. Установка и замеры не начались. Счётчик в
`test_xray_version_follows_binary_replacement` измеряет вызовы чтения
версии бинарника. Для сравнения r3 обе копии используют одни тесты и
зависимости. В базовой копии три файла оверлея взяты из установленной
базы `3a00777`.

## 1. Тесты и временная установка

Выполни §1 и исходный VPN-контроль §2
[ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md), остановившись до запуска его
таймера. В ссылочных блоках проверяй права через `sudo -n true`.
Для интерактивной авторизации
используй обычный TTY. Продолжай в том же Bash. Исходное состояние
должно быть off/off, VPN и панель доступны.

Тесты запусти обычным пользователем. Если используется окружение
pytest, передай его интерпретатор абсолютным путём в `XGW_TEST_PYTHON`.
Рабочие конфиги и службы при этих проверках остаются вне тестовых
каталогов. Для обеих копий используется один интерпретатор, один
пользователь и общий набор тестов кандидата.

```bash
CANDIDATE=${CANDIDATE:-aedb68cda0980b1dc63c420c92861028e67fc892}
OVERLAY=${OVERLAY:---xray-write-trace}
UNIT=${UNIT:-xgw-write-trace-rollback}
SRC="$D/write-source"
BASE_SRC="$D/write-baseline"
TEST_PY=${XGW_TEST_PYTHON:-$PY}
WRITE_GATE=0
WRITE_FILES=(src/xgw/apply/applier.py src/xgw/apply/singbox_generation.py src/xgw/daemon.py)
if [[ $OVERLAY == --selective-route-status ]]; then
  WRITE_FILES+=(src/xgw/watch/zapret2_control.py src/xgw/watch/zapret2_management.py src/xgw/zapret2.py)
fi

write_worktrees() {
  local changed expected
  git -C "$REPO" fetch origin "$BR" &&
    git -C "$REPO" merge-base --is-ancestor "$CANDIDATE" FETCH_HEAD &&
    git -C "$REPO" worktree add --detach "$SRC" "$CANDIDATE" &&
    git -C "$REPO" worktree add --detach "$BASE_SRC" "$CANDIDATE" &&
    git -C "$BASE_SRC" restore --source="$BASE" --worktree -- "${WRITE_FILES[@]}" || return
  changed=$(git -C "$BASE_SRC" diff --name-only HEAD) || return
  expected=$(printf '%s\n' "${WRITE_FILES[@]}")
  [[ $changed == "$expected" ]]
}
write_test_suite() {
  local tree=$1 label=$2
  shift 2
  (
    cd "$tree" || exit 2
    env PYTHONPATH="$tree/src:$tree" "$TEST_PY" -m pytest -o addopts='' -q --tb=short \
      -p no:cacheprovider --basetemp="$tree/.write-trace-pytest" --junitxml="$D/$label.xml" "$@"
  )
}
write_check() {
  local new_rc=0 old_rc=0
  run writer-unit write_test_suite "$SRC" writer-unit \
    tests/test_applier.py tests/test_singbox_generations.py tests/test_desync_route_evidence.py \
    tests/test_selective_probe_watch.py tests/test_acceptance_gate.py || return
  if [[ $OVERLAY == --selective-route-status ]]; then
    run route-unit write_test_suite "$SRC" route-unit tests/test_zapret2_panel.py \
      tests/test_zapret2.py || return
    run route-rebuild write_test_suite "$SRC" route-rebuild tests/test_daemon.py \
      -k zapret2_tick_uses_api_and_restores_vpn_after_worker_death || return
  fi
  run writer-daemon-current write_test_suite "$SRC" daemon-current tests/test_daemon.py ||
    new_rc=$?
  run writer-daemon-baseline write_test_suite "$BASE_SRC" daemon-baseline tests/test_daemon.py ||
    old_rc=$?
  printf 'daemon exit codes: candidate=%s baseline=%s\n' "$new_rc" "$old_rc"
  (( new_rc <= 1 && old_rc <= 1 )) || return 1
  run writer-daemon-comparison "$PY" "$SRC/docs/helpers/acceptance_test_gate.py" \
    --current "$D/daemon-current.xml" --baseline "$D/daemon-baseline.xml" \
    --current-source "$SRC" --baseline-source "$BASE_SRC"
}
if run writer-worktrees write_worktrees && write_check; then
  WRITE_GATE=1
  echo WRITE_GATE_OK
else
  echo WRITE_GATE_BLOCKED
fi
```

Обязательный набор должен завершиться с кодом 0. Для демона запиши
`matching_baseline_failures` из отчёта сравнения. Совпавшие отказы
остаются прежними отказами. Новые или изменившиеся ошибки, пропавшие
тесты, новые пропуски либо неполный JUnit блокируют установку. Для
каждого `changed_failures` сопоставь один и тот же `classname::name`
в обоих JUnit. Запиши отдельно тип и первую существенную строку
каждого сообщения с позицией в исходниках. Для числового расхождения
сверь по тесту, что измеряет счётчик. Файлы JUnit остаются локально.
Переходи к установке только после `WRITE_GATE_OK`.

Установка сверяет файлы из `WRITE_FILES` с базой `3a00777`, которая включает
принятый `apply/applier.py` из `1e27384`.

```bash
prepare_write_trace() {
  PACKAGE=$(readlink -e /opt/xgw/lib/xgw) || return
  PANEL=$(readlink -e /etc/xgw/panel.json) || return
  CFG=$(readlink -e /etc/xgw/config.toml) || return
  PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/xray-write-trace.XXXXXXXX) || return
  sudo -n test -d /var/lib/xgw/handoff ||
    sudo -n install -d -m 0755 /var/lib/xgw/handoff || return
  BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/xray-write-trace.XXXXXXXX) || return
  HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
  sudo -n mkdir "$PAYLOAD/code" "$PAYLOAD/base" || return
  git -C "$REPO" archive "$CANDIDATE" src/xgw docs/helpers/desync_batch1_install.py \
    docs/helpers/t11_management_restore.sh |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/code" || return
  if [[ $OVERLAY == --selective-route-status ]]; then
    git -C "$REPO" archive "$CANDIDATE" docs/helpers/selective_route_status_watch.py |
      sudo -n tar --no-same-owner -x -C "$PAYLOAD/code" || return
  fi
  git -C "$REPO" archive "$BASE" "${WRITE_FILES[@]}" |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/base" || return
  sudo -n chmod -R go-w -- "$PAYLOAD" &&
    sudo -n "$PY" -I "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
      --package "$PACKAGE" --backup "$BACKUP" &&
    sudo -n cp --preserve=mode,ownership "$PANEL" "$BACKUP/panel.before" &&
    (sudo -n sha256sum "$CFG" "$PANEL" | sudo -n tee "$BACKUP/config-before.sha256" >/dev/null) &&
    sudo -n chmod 0600 "$BACKUP/config-before.sha256" &&
    sudo -n install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" \
      "$BACKUP/restore.sh" || return
  sudo -n tee "$BACKUP/guard.sh" >/dev/null <<'SH' || return
#!/bin/bash
set -euo pipefail
backup=$1
shift
exec 8>"$backup/write-trace-restore.lock"
flock 8
[[ -e "$backup/network-test-started" ]] || exit 0
[[ ! -e "$backup/restore-completed" ]] || exit 0
/bin/bash "$backup/restore.sh" "$1" "$2" "$backup" "$3" rollback "$4"
SH
  sudo -n chmod 0700 "$BACKUP/guard.sh" &&
    printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" "$OVERLAY" "$UNIT" >"$D/install-location" &&
    sudo -n systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
      /bin/bash "$BACKUP/guard.sh" "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY" &&
    sudo -n systemctl is-active "$UNIT.timer"
}
install_write_trace() {
  sudo -n touch "$BACKUP/network-test-started" &&
    sudo -n "$PY" -I "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
}
if [[ ${WRITE_GATE:-0} == 1 ]] && exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run write-lock flock -n 9 && sudo -n true &&
   run write-prepare prepare_write_trace && run write-install install_write_trace; then
  export PYTHONPATH="$SRC/src:$SRC"
  echo WRITE_TRACE_INSTALLED
else
  echo INSTALL_BLOCKED
fi
```

Если таймер уже был создан, при любом сбое переходи к §4. Если база
разошлась, запиши имя файла. При успехе выполни
`run write-off off_status "$D/write-off.json"` после рестарта демона.

## 2. Проверка журнала в контролируемой фазе

Инструменты читают существующий журнал `xgw.service` до 5000 строк
за строго ограниченное окно. Сопоставляются монотонное время, загрузка
Linux и отпечаток фактически записанного файла. Отпечатки и сырые
записи в отчёт не включай.

```bash
snapshot() {
  sudo -n env PYTHONPATH="$PAYLOAD/code/src" "$PY" -B -P \
    -m xgw.desync.route_evidence snapshot >"$D/$1.json"
}
live() {
  sudo -n systemctl is-active --quiet "$UNIT.timer" &&
    sudo -n test -f "$BACKUP/network-test-started" &&
    sudo -n test ! -e "$BACKUP/restore-completed"
}
writers() {
  local before=$1 after=$2 range begin end
  range=$("$PY" -c 'import json, math, sys
from pathlib import Path
a, b = (json.loads(Path(p).read_text())["unix"] for p in sys.argv[1:])
assert 0 < b - a <= 300
print(math.floor(a), math.ceil(b) + 1)' "$before" "$after") || return
  read -r begin end <<<"$range"
  timeout 15 sudo -n journalctl --quiet --no-pager --unit=xgw.service \
    --since "@$begin" --until "@$end" --lines 5000 --grep=xray_config_write --output=json \
    --output-fields=MESSAGE,_BOOT_ID,_SYSTEMD_UNIT,_UID |
    "$PY" -m docs.helpers.xray_config_writes --before "$before" --after "$after"
}
if live && snapshot writer-off-before; then
  run writer-off-site site
  if snapshot writer-off-after; then
    run writer-off writers "$D/writer-off-before.json" "$D/writer-off-after.json"
  fi
fi
```

`none_observed` в спокойном окне означает, что в журнале совпадений
нет и байтовый хэш на границах тот же. При штатной фоновой записи
сохрани фактический результат. Оставаясь в off/off, задай `FORMAT="$VPN_FORMAT"`
для свежего формата, прошедшего 206/65536 в исходном VPN-контроле. В §2
[ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md) выполни только блок, начинающийся с
`if live && run before-settings off_status`, в рамках уже активного таймера.
При отказе допуска для этого CDN сохрани причину и перейди к §4.
Для бытового трафика VPN должен быть доступен на всём протяжении опыта.

Сразу после `SELECTIVE_SETTINGS_READY`, перед кликом Selective,
запусти `snapshot writer-admission-before`. По достижении
fresh/matched/active возьми `snapshot writer-admission-after`.
Запусти `run writer-admission writers "$D/writer-admission-before.json" "$D/writer-admission-after.json"`.
Положительный контроль атрибуции — итог `state=attributed` и
`by_source.zapret2_route≥1`. Если последнюю запись сделала другая
подсистема, укажи её отдельно. Если новый конфиг виден, а журнал
к нему не привязан, отметь `UNATTRIBUTED` и не назначай писателя.

## 3. Одна фаза просмотра

Если прошёл допуск, возьми определения `trace_python` и
`trace_playback` из §1 [ТЗ потока](MEDIA-FLOW-2026-11-20.md).
Вместо нового checkout используй уже проверенный `TRACE="$SRC"`.
Запусти одну фазу, пользуясь тем же `snapshot`.

```bash
TRACE="$SRC"
if live; then
  run writer-media trace_playback writer-media "$FORMAT"
  if [[ -s "$D/writer-media-route-before.json" && -s "$D/writer-media-route-after.json" ]]; then
    run writer-media-journal writers \
      "$D/writer-media-route-before.json" "$D/writer-media-route-after.json"
  fi
fi
```

Вынеси отдельно результаты плеера, группы выхода, число записей и
`final_write.source`. Если снимки несопоставимы, укажи
`changed_sections`. Связь с конкретным источником подтверждается
`state=attributed` и совпадением последней записи с итоговым снимком.
Для `daemon_rebuild` или `daemon_pending` можно указать причину из
смежного события «apply» только при совпадении времени проверки.
Если записей нет, а конфигурация сменилась, источник открыт.
Если финальный хэш вернулся к исходному, но в интервале есть записи,
это окно также не подтверждает неизменность маршрута.
При `none_observed` и сравнимых снимках укажи, что перезапись
в этом коротком опыте не наблюдалась. Достаточно одной успешной
фазы или одного зафиксированного блокера.

## 4. Восстановление и отчёт

Верни off/off штатной кнопкой, если guard ещё не сработал. Если shell
оборвался, восстанови `BACKUP`, `HELPER`, `PANEL`, `OVERLAY` и `UNIT`
из приватного `install-location`. Остальные пути и переменные относятся
к тому же каталогу опыта.

```bash
verify_write_base() {
  local file
  for file in "${WRITE_FILES[@]}"; do
    git -C "$REPO" show "$BASE:$file" | sudo -n cmp - "$PACKAGE/${file#src/xgw/}" || return
  done
}
if [[ -n ${BACKUP:-} && -n ${UNIT:-} ]] && sudo -n true; then
  if sudo -n test -f "$BACKUP/network-test-started"; then
    run write-restore sudo -n /bin/bash "$BACKUP/guard.sh" \
      "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY"
    if run restore-marker sudo -n test -f "$BACKUP/restore-completed" &&
       run restore-sha sudo -n sha256sum -c "$BACKUP/config-before.sha256" &&
       run restore-files verify_write_base &&
       run restore-daemon systemctl is-active xgw.service &&
       run restore-workers workers_off &&
       run restore-off off_status "$D/write-restored.json" &&
       run restore-vpn site; then
      run restore-timer-stop sudo -n systemctl stop "$UNIT.timer"
    else
      echo RESTORE_UNCONFIRMED
    fi
  elif sudo -n bash -c 'test -f "$1/guard.sh" && test ! -e "$1/network-test-started"' bash "$BACKUP"; then
    run unused-timer-stop sudo -n systemctl stop "$UNIT.timer"
  fi
  run restore-timer-final systemctl show "$UNIT.timer" -p ActiveState -p SubState
fi
exec 9>&-
```

При задержке панели после отката повтори проверку из блока и только
потом сними таймер. Сверь `ActiveState=inactive`. При сбое восстановления
сообщи владельцу наблюдаемое состояние. Публикуй статусы `UNIT_TESTS`,
`DAEMON_BASELINE`, `INSTALL`,
`WRITER_CONTROL`, `LIVE_PLAY`, `FLOW`, `CONFIG_WRITER` и `RESTORE`,
правильные SHA кода, источники и число записей. Адреса, теги отдельных
серверов, отпечатки конфига, PID, подписанные URL и сырые журналы
остаются на машине. Для публикации используй блок из §3
[ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md) с именем
`_xray-config-writes-r3.md`. Опубликуй при любом исходе и верни ссылку.
