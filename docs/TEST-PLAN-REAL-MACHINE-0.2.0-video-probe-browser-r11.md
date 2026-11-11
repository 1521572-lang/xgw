# ThinkCentre. Медленная навигация Firefox и сравнение ALPN

CODE `18fe804d84961d620d7546f76be7b6b85d95b3cb`, отчёт r10 `0a78d75`. Исполнитель GLM-5.3-Flash.
В r10 ответ Navigate не пришёл в окно чтения, хотя через реле прошло 5,3 МиБ.
Проверяем наблюдение Firefox без ожидания полной загрузки страницы, затем сравнение ALPN.
Исполнитель сам запускает команды и скрипты в терминале ThinkCentre, читает квитанцию
и публикует отчёт. Оба блока выполняются в одной сессии обычного пользователя с sudo.
При недоступности запуска исполнитель фиксирует NOT_RUN с причиной и публикует отчёт.
Службы, маршруты, настройки и sysctl сохраняются. Адреса, порты, профили, токены,
полные заголовки, тела и журналы остаются приватными.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=18fe804d84961d620d7546f76be7b6b85d95b3cb
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r11.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  0d360899f3a97833eabc95a0b57c5cdc2790a017e61c641ade43025f4519e51e "$H" \
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

Ожидаются 110 тестов. Указать результат и причины пропусков. Проверки охватывают
pageLoadStrategy=none, продолжение после ответа Firefox с кодом timeout, медленную
страницу в пределах срока наблюдения, его истечение и сбой канала. При FAIL перейти к отчёту.
Исполнитель сам сверяет capture on, zapret2 off, свежий статус, Firefox и живой
безлимитный VPN-выход. При доступной панели открыть статусы шлюза и прочитать их с Vision.
Помощник проверяет поддержку HTTP/2 установленным curl (8.4.0 или новее).

## 2. Живой прогон

Исполнитель сам запускает один согласованный прогон с публичной страницей.
Firefox работает через временное реле к тому же служебному VPN-входу, который использует
curl. Лимит Firefox — 120 с и 16 МиБ. WebDriver начинает навигацию с pageLoadStrategy=none.
На ответ Navigate отводится до 15 секунд в пределах общего срока. Состояние начального
about:blank помечается navigation_pending. Наблюдение за плеером идёт по общему сроку.

После подтверждённого воспроизведения curl запрашивает HTTP/1.1, затем HTTP/2 для первого
кандидата. URL с параметрами, VPN-выход, User-Agent и `Range: bytes=0-16383` совпадают.
Лимит пары — 8 с и до 16 КиБ тела на попытку, до 32 КиБ на пару. Заголовки и TLS отдельно.

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

Исполнитель сам читает STAGE, MARIONETTE_ERROR, BROWSER, ATTEMPT, VIDEO, CHECK и RESULT/STOP.
Сверить navigation_started, navigation_returned и observation_started. Указать
navigation_pending и playback_observed, если они появились. При сбое указать метод,
класс ошибки и код Firefox, если он есть. Сверить ATTEMPT с replay_attempts.
Для каждой попытки указать candidate_index, browser_protocol, http_requested,
http_version, alpn_offered, alpn_selected, http, bytes, content_length, content_encoding,
content_type, video_mime, curl_exit и verdict. При STOP прочитать сохранённую квитанцию.
Проверить завершение Firefox и удаление профиля. При доступной панели сверить статусы с Vision.

## 3. Чтение результатов

- При появлении observation_started указать, успел ли плеер продвинуться и появился ли кандидат.
- При browser_control_failed указать последний этап и MARIONETTE_ERROR. Байты реле учитывать
  отдельно от признаков загрузки страницы и воспроизведения.
- Для ALPN сравнить browser_protocol с alpn_offered, alpn_selected и http_version.
  alpn_selected=none означает явное отсутствие выбора, null — отсутствие наблюдаемой
  метки. HTTP/2 считается измеренным, когда получен ответ с http_version=2.
- При отсутствии естественной ротации сценарий ротации остаётся NOT_RUN.

Сопоставить capture, zapret2 и диагностику до и после. После любого исхода перейти к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r11-ДАТА.md`.
Указать CODE, суммы, тесты, кто запустил скрипты, этапы, завершённые ATTEMPT и конечную
диагностику. Проверить отчёт на секреты. В отдельном рабочем дереве от свежей
`origin/freepool` закоммитить только отчёт, проверить diff, сделать обычный push и сверить
файл на GitHub. При гонке перенести коммит на свежую ветку и повторить push без force.
Подтверждение публикации не требуется. Сообщить хеш и ссылку. При сбое push сохранить
файл и указать причину.
