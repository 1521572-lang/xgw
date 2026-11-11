# ThinkCentre. Повторный GET одного видеоресурса по HTTP/1.1 и HTTP/2

CODE `39c5e3c491d6aa88352d93c222b79de5c8a3175c`, отчёт r8 `e2c85df`. Исполнитель GLM-5.3-Flash.
В r8 с Range и без него совпали HTTP 200, 31 байт и метка MIME other.
В r9 один клиент сравнивает версии HTTP и пишет длину и кодировку из заголовков.
Исполнитель сам запускает все команды и скрипты в терминале ThinkCentre, читает квитанцию
и публикует отчёт. Оба блока выполняются в одной сессии обычного пользователя с sudo.
При отсутствии доступа, полномочий или инструментов оформить NOT_RUN с причиной.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
Адреса, порты, профили, токены, полные заголовки, тела и журналы оставить приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=39c5e3c491d6aa88352d93c222b79de5c8a3175c
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r9.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  8d4c840e31bf1a5e583a8f6ffe5540d03aa0c62035c7dfb35c2d95b6d7b76195 "$H" \
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
  tests/test_video_probe_http.py tests/test_video_browser.py tests/test_checks.py)
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидаются 103 теста. Указать результат и причины пропусков. Проверки охватывают
выбор версии HTTP, предел тела, фактический протокол при согласовании HTTP/1.1,
фильтрацию метаданных и сохранение квитанции. При FAIL перейти к отчёту.
Исполнитель сам сверяет capture on, zapret2 off, свежий статус, Firefox и живой
безлимитный VPN-выход. При доступной панели открыть статусы шлюза и прочитать их с Vision.
Нужен уже установленный системный curl 8.4.0 или новее с HTTP2 в Features. Помощник
проверит это сам и вернёт NOT_RUN при отсутствии поддержки. Установки в ТЗ нет.

## 2. Живой прогон

Исполнитель сам запускает один согласованный прогон с публичной страницей.
Firefox ограничен 120 с и 16 МиБ через реле. После подтверждения воспроизведения берётся
первый допустимый кандидат по порядку r7. Один curl запрашивает HTTP/1.1, затем HTTP/2.
URL с параметрами, VPN-выход, User-Agent и `Range: bytes=0-16383` совпадают.
Лимит пары 8 с. Предел тела 16 КиБ на попытку и 32 КиБ на пару, заголовки и TLS отдельно.
При заявленной длине больше предела curl может остановиться до чтения тела.
Публиковать фактически полученные байты, даже если тело не было прочитано.

Используется youtube_sign_url или watch-адрес из zapret2.probe_urls. Если нужен другой
уже согласованный публичный watch-адрес, исполнитель сам записывает его в приватный
`$D/page.txt` (0600). При отсутствии адреса помощник вернёт NOT_RUN.

```bash
args=(--state "$D/result.json" --compare-http)
if test -f "$D/page.txt"; then
  args+=(--page-file "$D/page.txt")
fi
rc=0
sudo "${HELPER[@]}" "${args[@]}" || rc=$?
printf 'helper_rc=%s\n' "$rc"
sudo xgw diag --no-net >"$D/diag-after"
```

Исполнитель сам читает STAGE, BROWSER, ATTEMPT, VIDEO, CHECK и RESULT/STOP. Сверить
ATTEMPT с replay_attempts. У пары совпадают candidate_index, transfer_size и
decoded_body_size, range_header=true в обеих строках. Записать http_requested,
http_version, http, bytes, content_length, content_encoding, content_type, video_mime,
curl_exit и verdict. Пустой или неразобранный заголовок длины даёт null. Неизвестная
кодировка даёт other, отсутствующая — null. При STOP читать уже сохранённые попытки.
Проверить завершение Firefox и удаление профиля, при доступной панели сверить статусы с Vision.

## 3. Чтение результатов

- Считать сравнение HTTP состоявшимся при двух HTTP-ответах с фактическими версиями
  1.1 и 2 соответственно. comparison_complete сообщает о записи двух попыток.
- При согласовании HTTP/1.1 вместо HTTP/2, отсутствии ответа или истечении срока
  отметить, какое сравнение осталось непроверенным, и привести сохранённые наблюдения.
- При двух ответах сравнить HTTP, байты и метки. Совпадение метрик фиксировать для
  данной пары. Тела не сохраняются, побайтное сравнение этим прогоном не выполняется.
- При `body_limit` записать заявленную длину и фактические байты. При
  `browser_video_verified` указать фактическую версию успешной попытки.
- При отсутствии естественной ротации сценарий ротации остаётся NOT_RUN.

Сопоставить capture, zapret2 и диагностику до и после. После любого исхода перейти к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r9-ДАТА.md`.
Указать CODE, суммы, тесты, фактические действия, наблюдения Firefox, завершённые ATTEMPT,
итог пары и конечную диагностику. Проверить отчёт на секреты. В отдельном рабочем дереве
от свежей `origin/freepool` закоммитить только отчёт, проверить diff, сделать обычный push
и сверить файл на GitHub. При гонке перенести коммит на свежую ветку и повторить push
без force. Подтверждение публикации не требуется. Сообщить хеш и ссылку. При сбое push
сохранить файл и указать причину.
