# ThinkCentre — обновление CDN-пробы без повторного ввода страницы

Исполнитель Flash выполняет действия сам на Ubuntu 24.04 LTS и
автоматически публикует один обезличенный отчёт при любом исходе.
При недоступном терминале, браузере, Qt или sudo запроси нужный доступ
и продолжи сам. Код и сценарий подготовлены Codex.

На проверенном узле уже приняты старт 720p с подтверждённым outbound
zapret2, отдельный контроль VPN и автоматический fallback. Новая работа
проверяет замену только сохранённого CDN-адреса. Старая страница YouTube,
настройки стратегии и бюджет должны сохраниться. Пакет устанавливается
временно и откатывается после проверки.
[Принятый старт](../reports/2026-11-20T111437Z_selective-flow-evidence.md) ·
[Принятый fallback](../reports/2026-11-20T103848Z_selective-media-proof-r2.md)

## 1. Доступ, база и установка

Начни в обычном Bash из репозитория. Выполни `1 и VPN-контроль из `2
[ТЗ r2](MEDIA-PROOF-2026-11-20-R2.md), остановись перед созданием его
таймера. Во всех проверках прав начинай с `sudo -n true`. При отказе
запроси доступ и в TTY авторизуйся обычным способом. Сохрани тот же
shell либо открой одну долгоживущую сессию до завершения теста.
Следующий блок выводит приватный файл `install-location` с путями
для возврата, если сессия оборвётся.

```bash
CANDIDATE=187653f1b3f51db376d166d6f7677cba13c48a70
BASE_CORE=3a00777c21ed017760cb7bfd0bb24478fc1f48ad
BASE_MANAGEMENT=08d31ee93963bb00acb7a2275e7a554efcfb0f05
BASE_UI=3630b44502b872ca3788e0824c6a9d0d8363b561
GUI=/opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64
OVERLAY=--selective-cdn-update
UNIT=xgw-selective-cdn-update-rollback

prepare_cdn_update() {
  git -C "$REPO" fetch origin "$BR" &&
    git -C "$REPO" merge-base --is-ancestor "$CANDIDATE" FETCH_HEAD &&
    git -C "$REPO" worktree add --detach "$D/candidate" "$CANDIDATE" || return
  PACKAGE=$(readlink -e /opt/xgw/lib/xgw) || return
  CFG=$(readlink -e /etc/xgw/config.toml) || return
  PANEL=$(readlink -e /etc/xgw/panel.json) || return
  PAYLOAD=$(sudo -n mktemp -d /opt/xgw/handoff/selective-cdn-update.XXXXXXXX) || return
  sudo -n test -d /var/lib/xgw/handoff ||
    sudo -n install -d -m 0755 /var/lib/xgw/handoff || return
  BACKUP=$(sudo -n mktemp -d /var/lib/xgw/handoff/selective-cdn-update.XXXXXXXX) || return
  HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
  sudo -n mkdir "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base" || return
  git -C "$REPO" archive "$CANDIDATE" \
    src/xgw/watch/zapret2_management.py src/xgw/watch/zapret2_control.py \
    src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js src/xgw/gui/zapret2.py \
    docs/helpers/desync_batch1_install.py docs/helpers/t11_management_restore.sh |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/code" || return
  git -C "$REPO" archive "$BASE_CORE" src/xgw/watch/zapret2_control.py |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/base" || return
  git -C "$REPO" archive "$BASE_MANAGEMENT" src/xgw/watch/zapret2_management.py |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/base" || return
  git -C "$REPO" archive "$BASE_UI" src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/base" || return
  git -C "$REPO" archive "$BASE_UI" src/xgw/gui/zapret2.py |
    sudo -n tar --no-same-owner -x -C "$PAYLOAD/gui_base" || return
  sudo -n chmod -R go-w -- "$PAYLOAD" || return
  GUI_OPTION=()
  if sudo -n cmp -s "$PAYLOAD/gui_base/src/xgw/gui/zapret2.py" "$GUI/src/xgw/gui/zapret2.py"; then
    GUI_OPTION=(--gui "$GUI")
  else
    echo GUI_BASE_UNCONFIRMED
  fi
  sudo -n "$PY" -I "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
    --package "$PACKAGE" --backup "$BACKUP" "${GUI_OPTION[@]}" || return
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
exec 8>"$backup/cdn-restore.lock"
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
apply_cdn_update() {
  sudo -n touch "$BACKUP/network-test-started" &&
    sudo -n "$PY" -I "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
}
if exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run cdn-lock flock -n 9 && sudo -n true &&
   run cdn-prepare prepare_cdn_update && run cdn-apply apply_cdn_update; then
  echo CDN_UPDATE_INSTALLED
else
  echo INSTALL_BLOCKED
fi
```

Если установка блокирована, зафиксируй фазу. После создания таймера
выполни `4. При отличии базовых файлов не подменяй их копией из
произвольного коммита. Параметр GUI применяется только к совпавшему
релизу. Если GUI не был установлен, отдельно проверь Qt на том же SHA
из checkout или укажи `QT=NOT_RUN` с причиной.

На ThinkCentre прогони следующие тесты с Linux-блокировкой. Отметь
результат, доступность авторизованной панели и состояние off/off.

```bash
cd "$D/candidate"
export PYTHONPATH="$D/candidate/src:$D/candidate"
"${XGW_TEST_PYTHON:-$PY}" -m pytest -q \
  tests/test_zapret2_management.py tests/test_zapret2_panel.py tests/test_desync_schema.py
node --check src/xgw/ui/zapret2.js
run cdn-off off_status "$D/cdn-off.json"
```

## 2. API, веб-форма и Qt

При off/off открой веб-форму zapret2 в авторизованной панели. Используй
браузер и vision. Через форму сохрани тестовую пару со страницей
`https://www.youtube.com/t/terms` и истёкшей фикстурой
`https://r1.googlevideo.com/videoplayback?expire=1&sig=xgw-expired-fixture`,
включив HTTPS-проверку YouTube. Убедись по карточке, что Selective
заблокирован. Новая возможность `can_replace_cdn_probe=true` должна
быть доступна даже при истёкшем адресе. Оба поля при открытии пустые.

1. Оставь поле страницы пустым, введи только вторую фикстуру
   `https://r2.googlevideo.com/videoplayback?expire=2000000000&sig=xgw-new-fixture`
   и сохрани. Должны измениться ревизия и срок CDN, вид пробы страницы
   останется `terms`, режим — off/off. В сетевых данных формы POST должен
   содержать `cdn_probe_url`. GET и ответ команды содержат только
   метаданные, полные URL и подписи оставь за пределами отчёта.
2. Проверь сохранение с прежней ревизией в другом окне или локальным
   API-клиентом `Client` с `expected` до замены. Ожидается `conflict`
   и та же новая ревизия. С текущей ревизией повтор одинакового адреса
   возвращает `unchanged`. Запрос одновременно с `cdn_probe_url` и
   `probe_urls` или с CDN вне Googlevideo отклоняется.
3. Открой Qt форму настроек, если соответствующее окно доступно.
   Выполни ту же замену, оставив адрес страницы пустым. Если доступна
   только проверка из checkout, используй `QT_QPA_PLATFORM=offscreen`
   и `SettingsDialog.values()`. Заполни только второе поле, ожидается
   `cdn_probe_url`. В отчёте раздели реальную форму и проверку фикстурой.
4. Проверь пустые поля и очистку. Пустые поля сохраняют пару.
   После явной очистки `probe_count=0`, возможность отдельной замены
   пропадает, Selective заблокирован. Попытка одного адреса в API даёт
   `blocked` и сохраняет исходную ревизию. Восстанови тестовую пару
   для следующего этапа. Фикстуры никогда не активируй.

## 3. Один живой цикл со свежим CDN

В VPN извлеки свежий 720p-формат через прежний `resolve`. Параметры и
ссылку храни локально. Подставь только CDN в форму и проверь, что
сохранённая страница условия не менялась. Актуальный адрес извлеки из JSON
через `docs.helpers.headless_playback.read_format`. Если текущий
VPN-адрес естественно недоступен напрямую, допустим один новый
адрес того же ролика из разрешения Standalone по `2 старого r2,
в рамках уже активного таймера. Сверь тот же `VIDEO` и off/off перед
следующей записью. Прямой контроль должен дать `206/65536`.

При нормальном бюджете включи принятый Selective. Запиши свежую ревизию,
`active/https_reachable` или фактическую фазу отказа. Для успешного окна
выполни один `trace_playback` из [ТЗ потока](MEDIA-FLOW-2026-11-20.md).
Корневой снимок берётся прежним `snapshot`, загрузка инструмента и журнал
ограничены теми же командами, формат передай через аргумент.
Сверь группу выхода и 720p. Настоящее истечение учитывай только при
естественном наступлении за время опыта. В ином случае укажи
`LIVE_EXPIRY=NOT_RUN`. Для исправного API и формы возможен отдельный
PASS при недоступном сетевом пути.

Если в том же окне есть второй действующий адрес того же ролика,
замени только CDN при активном Selective. Зафиксируй новую ревизию
и исход её штатной проверки. Старый успех пробы следует исключить из
оценки новой ревизии. При отсутствии второго адреса отметь
`LIVE_ACTIVE_UPDATE=NOT_RUN`.

## 4. Откат, VPN и публикация

Если был сетевой этап, верни off/off в панели, пока восстановление ещё
не началось. Вызови тот же guard вручную. Ручной вызов и таймер
используют один lock и маркер. Если терминал оборвался, путь
`install-location` содержит по одной строке `BACKUP`, `HELPER`, `PANEL`,
`OVERLAY` и `UNIT`. Перечитай их из приватного файла.

```bash
verify_cdn_files() {
  sudo -n "$PY" -I - "$BACKUP/manifest.json" <<'PY'
import hashlib, json, sys
from pathlib import Path

rows = json.loads(Path(sys.argv[1]).read_text())
assert len(rows) in (4, 5)
for row in rows:
    target = Path(row["target"])
    assert hashlib.sha256(target.read_bytes()).hexdigest() == row["old_sha"]
print(f"restored files: {len(rows)}")
PY
}
if [[ -n ${BACKUP:-} && -n ${UNIT:-} ]] && sudo -n true; then
  if sudo -n test -f "$BACKUP/network-test-started"; then
    run cdn-restore sudo -n /bin/bash "$BACKUP/guard.sh" \
      "$BACKUP" "$PY" "$HELPER" "$PANEL" "$OVERLAY"
    if run cdn-restored-marker sudo -n test -f "$BACKUP/restore-completed" &&
       run cdn-restored-hashes sudo -n sha256sum -c "$BACKUP/config-before.sha256" &&
       run cdn-restored-files verify_cdn_files &&
       run cdn-restored-daemon systemctl is-active xgw.service &&
       run cdn-restored-workers workers_off &&
       run cdn-restored-off off_status "$D/cdn-restored.json" &&
       run cdn-restored-vpn site; then
      run cdn-timer-stop sudo -n systemctl stop "$UNIT.timer"
    else
      echo RESTORE_UNCONFIRMED
    fi
  elif sudo -n bash -c 'test -f "$1/guard.sh" && test ! -e "$1/network-test-started"' bash "$BACKUP"; then
    sudo -n systemctl stop "$UNIT.timer"
  fi
  run cdn-timer-final systemctl show "$UNIT.timer" -p ActiveState -p SubState
fi
exec 9>&-
```

Если панель после отката только запускается, повтори блок после её
готовности. Сверка возвращённых файлов входит в проверку до снятия
таймера. Проверь `ActiveState=inactive` в результате последней команды. При сбое восстановления
сохрани состояние таймера и сразу сообщи владельцу. После off/off
подтверди новый VPN-запрос. Обнови страницу браузера или перезапусти
тестовое графическое окно, чтобы оно использовало возвращённый код.

В отчёте отдельными строками укажи `INSTALL`, `API`, `WEB`, `QT`,
`LIVE_PLAY`, `FLOW`, `LIVE_ACTIVE_UPDATE`, `LIVE_EXPIRY` и `RESTORE`. Сырые URL, IP, cookie
и скриншоты с секретами оставь на ThinkCentre. Для автоматической
публикации используй блок из `3 [ТЗ пересчёта](MEDIA-COUNTERS-2026-11-20.md)
с суффиксом `_selective-cdn-update.md`. При блокере доступа всё равно
опубликуй отчёт доступным способом и верни ссылку на коммит.
