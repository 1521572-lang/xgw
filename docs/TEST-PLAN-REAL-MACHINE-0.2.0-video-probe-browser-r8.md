# ThinkCentre. Повторный GET одного видеоресурса с Range и без него

CODE `40ab56ad9f4de9b4aafcada13c86ff5b0494222c`, отчёт r7 `503bba4`. Исполнитель GLM-5.3-Flash.
В r7 Firefox получил 533 325 байт тела крупнейшего ресурса. Повторный GET дал 31 байт.
Сравниваем две попытки одного ресурса и фиксируем нормализованный Content-Type.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
Адреса, порты, профили, токены, полные заголовки, тела и журналы оставить приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=40ab56ad9f4de9b4aafcada13c86ff5b0494222c
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r8.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  d58323bfffda2c64e479ca73041ed22f91ab09615c987d231d0efc51384a07e7 "$H" \
  725d9f81f39164123336aa2855bc7a2610dd609d5059122190694a844d272b7a \
  "$D/new/docs/helpers/video_probe_check.py" | sha256sum -c -
HELPER=(python3 -I -c '
import runpy
import sys
from pathlib import Path

helper = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(helper.parents[2] / "src"))
runpy.run_path(str(helper), run_name="__main__")
' "$H")
"${HELPER[@]}" --help
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_video_probe_browser_check.py tests/test_video_probe.py \
  tests/test_video_browser.py tests/test_checks.py)
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидается 91 тест при доступных зависимостях. Указать результат и причины пропусков.
Проверки охватывают общий срок, оба значения Range, предел тела, сохранение успешной
попытки и обезличивание MIME. При FAIL перейти к отчёту.
Исполнитель сам сверяет capture on, zapret2 off, свежий статус, Firefox и живой
безлимитный VPN-выход. При доступной панели открыть статусы шлюза и прочитать их с Vision.

## 2. Живой прогон

Исполнитель сам проводит один согласованный запуск с публичной страницей владельца.
Firefox ограничен 120 с и 16 МиБ через реле. После подтверждения воспроизведения берётся
первый допустимый кандидат по порядку r7. Для этого адреса выполняются две попытки, сначала
с `Range: bytes=0-16383`, затем без заголовка Range. Полный адрес с параметрами, VPN-выход
и User-Agent одинаковы. Серия ограничена 8 с, до 16 КиБ тела на попытку и до 32 КиБ на серию.
Заголовки и TLS учитываются отдельно. При успехе первой попытки вторая всё равно выполняется
при наличии времени. Ответы 3xx учитываются в квитанции по HTTP и verdict=redirect.

Используется youtube_sign_url или watch-адрес из zapret2.probe_urls. Если адреса нет,
владелец предоставляет одну строку в приватном `$D/page.txt` (0600). Настройки не править.

```bash
args=(--state "$D/result.json")
if test -f "$D/page.txt"; then
  args+=(--page-file "$D/page.txt")
fi
rc=0
sudo "${HELPER[@]}" "${args[@]}" || rc=$?
printf 'helper_rc=%s\n' "$rc"
sudo xgw diag --no-net >"$D/diag-after"
```

Исполнитель читает STAGE, MARIONETTE_ERROR, BROWSER, ATTEMPT, VIDEO, CHECK и RESULT/STOP.
Сверить ATTEMPT с replay_attempts в квитанции. У пары совпадают candidate_index,
transfer_size и decoded_body_size. range_header ожидается true, затем false.
Для каждой попытки указать HTTP, объём тела, content_type, video_mime и verdict,
если поля есть. content_type содержит метку из закрытого списка, other для прочих значений
или null при отсутствии MIME. Указать comparison_complete, если поле сохранено.
При STOP прочитать квитанцию и сохранить завершённые попытки. Проверить завершение
временного Firefox и удаление профиля. При доступной панели сверить статусы с Vision.

## 3. Чтение результатов

- `browser_video_verified` — указать режим запроса с HTTP 200/206, video/* и 16 КиБ тела.
  Если успешны оба режима, указать оба.
- При двух полученных HTTP-ответах сопоставить коды, размеры и MIME. Если оба по 31 байту,
  отметить совпадение в этой паре. Если ответы различаются, записать наблюдаемую разницу.
- При `replay_time_budget` или `comparison_complete=false` указать, какие попытки успели
  завершиться. При транспортном сбое одного режима указать его отдельно от HTTP-ответа.
- При отсутствии естественной ротации живой сценарий ротации остаётся NOT_RUN.

Сопоставить capture, zapret2 и диагностику до и после. При отсутствии условий для запуска
оформить NOT_RUN. Один живой запуск на ТЗ. После любого исхода перейти к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r8-ДАТА.md`.
Указать CODE, суммы, тесты, фактические действия, наблюдения Firefox, все завершённые
ATTEMPT, итог пары и конечную диагностику. Проверить отчёт на секреты, использовать
отдельное рабочее дерево от свежей `origin/freepool`, закоммитить только отчёт, проверить
diff, сделать обычный push и сверить файл на GitHub. При гонке перенести свой коммит на
свежую ветку и повторить push без force. Подтверждение публикации не требуется.
Сообщить хеш и ссылку. При сбое push сохранить файл и указать причину.
