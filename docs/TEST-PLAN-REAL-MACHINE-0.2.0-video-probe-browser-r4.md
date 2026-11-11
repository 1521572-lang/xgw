# ThinkCentre. Создание сессии Marionette и продолжение видеопробы

CODE `b5137ec2050d2b39eb922562af35048755141964`, отчёт r3 `bc2c4bc`. Исполнитель GLM-5.3-Flash.
В r3 рукопожатие прошло. В отдельной проверке NewSession ответил через 13,4 с, что
превысило прежнее окно чтения в 8 с. Проверяем отдельный лимит в 30 с для NewSession
и живой прогон видеопробы. Порт выбирается по прежним правилам.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
В отчёт включать числа и признаки. Адреса, порты, профили, токены и журналы оставить приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=b5137ec2050d2b39eb922562af35048755141964
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r4.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  cb2fece43b98fbf16ca0d1aa9e035e1321855bdde516c2050be1849f62d301a6 "$H" \
  725d9f81f39164123336aa2855bc7a2610dd609d5059122190694a844d272b7a \
  "$D/new/docs/helpers/video_probe_check.py" | sha256sum -c -
python3 -I "$H" --help
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_video_probe_browser_check.py tests/test_video_probe.py \
  tests/test_video_browser.py tests/test_checks.py)
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидаются 75 тестов при доступных зависимостях. Указать результаты и причины пропусков.
Новые сценарии проверяют успешный ответ через 13,4 с, истечение одного срока при получении
ответа по частям, остаток общего бюджета, прежние 8 с для другой команды и отсутствие
навигации после таймаута сессии. При FAIL перейти к отчёту.

Исполнитель сам сверяет capture on, zapret2 off, свежий статус, Firefox и живой безлимитный
VPN-выход. При доступной панели XGW открыть нужный экран и прочитать статусы с помощью Vision.

## 2. Живой прогон

Исполнитель сам проводит один согласованный запуск с публичной страницей владельца.
Лимиты прежние: до 120 с и 16 МиБ через прокси для Firefox, до 64 КиБ и 8 с для GET.
NewSession получает до 30 с из оставшегося времени Firefox. Отдельный прогрев не нужен.
Используется youtube_sign_url или watch-адрес из zapret2.probe_urls. Если его нет, владелец
предоставляет одну строку в приватном `$D/page.txt` (0600). Настройки шлюза не править.

```bash
rc=0
if test -f "$D/page.txt"; then
  sudo python3 -I "$H" --state "$D/result.json" --page-file "$D/page.txt" || rc=$?
else
  sudo python3 -I "$H" --state "$D/result.json" || rc=$?
fi
printf 'helper_rc=%s\n' "$rc"
sudo xgw diag --no-net >"$D/diag-after"
```

Исполнитель читает STAGE и сверяет сохранённую квитанцию. После `marionette_ready` ожидаются
`session_requested` и, при совпадении профиля, `session_ready`. Затем возможны
`navigation_started` и `playback_observed`. Указать последнюю метку и первый невыполненный шаг.
Проверить завершение временного Firefox и удаление профиля. При доступной панели сверить
конечные статусы с Vision. Квитанцию не удалять ради повтора.

## 3. Чтение результатов

- `session_ready` подтверждает ответ NewSession и совпадение профиля в живом прогоне.
- `RESULT browser_session_timeout` с последней меткой `session_requested` означает
  истечение срока вызова сессии. Навигация в этом случае не начиналась.
- `browser_control_failed`, `browser_profile_unverified` и STOP фиксировать с последней
  достигнутой меткой и наблюдениями. Причину без наблюдений не угадывать.
- `RESULT browser_video_verified` подтверждает повторный GET через VPN с HTTP 200/206,
  video/* и минимум 16 КиБ. Прямой путь zapret2 проверяется отдельным экспериментом.
- Для BROWSER, VIDEO, CHECK и прочих исходов применять условия r2 и r3. При естественной
  ротации сверить события пула. Без неё отметить NOT_RUN для живой ротации.

Сопоставить capture, zapret2 и диагностику до и после. При отсутствии условий для запуска
оформить NOT_RUN. После любого исхода переходить к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r4-ДАТА.md`.
Указать CODE, суммы, тесты, объём прогона, STAGE/BROWSER/VIDEO/CHECK/RESULT или STOP,
последнюю метку, первый невыполненный шаг и конечную диагностику.
Проверить отчёт на секреты, использовать отдельное рабочее дерево от свежей `origin/freepool`,
закоммитить только отчёт, проверить diff, сделать обычный push в `freepool` и сверить файл на GitHub.
При гонке перенести свой коммит на свежую ветку и повторить push без force. Подтверждение
публикации не требуется. Сообщить хеш и ссылку. При сбое push сохранить файл и указать причину.
