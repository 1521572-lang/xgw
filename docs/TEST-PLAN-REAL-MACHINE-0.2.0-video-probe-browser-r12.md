# ThinkCentre. Повторный GET из вкладки Firefox

CODE `efd27747a7e21313345b11b82b1bd6488ee32f78`, отчёт r11 `4c31a59`. Исполнитель GLM-5.3-Flash.
В r11 Firefox загрузил 393 101 байт тела по HTTP/1.1. curl по HTTP/1.1 получил 31 байт.
Сравниваем один fetch из той же вкладки с парой curl на выбранном ресурсе.

## 1. Доступ и запуск исполнителем

Исполнитель открывает терминал ThinkCentre или подключается инструментом удалённого запуска.
При недоступности терминала или требуемых прав исполнитель запрашивает доступ у владельца.
Получив доступ, исполнитель сам запускает весь блок ниже от обычного пользователя с sudo.
Владелец предоставляет доступ или согласие. Ручной запуск команд остаётся за исполнителем.
Если получить доступ не удалось, исполнитель оформляет и публикует NOT_RUN с причиной.
В отчёте указать инструмент запуска, время UTC из вывода и фактически выполненные действия.
При доступной панели исполнитель сам открывает статусы шлюза и читает их с Vision.
До запуска сверить capture on, zapret2 off, свежий статус и живой безлимитный VPN-выход.

Используется настроенный youtube_sign_url или watch-адрес из zapret2.probe_urls. Если
нужен другой уже согласованный публичный адрес, исполнитель сам передаёт путь к приватному
файлу с одной строкой через переменную XGW_PAGE_FILE. При отсутствии адреса будет NOT_RUN.
Службы, маршруты, настройки и sysctl сохраняются. Адреса, порты, профили, токены,
полные заголовки, тела и журналы остаются приватными.

## 2. Один блок подготовки, тестов и живого прогона

```bash
(
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
sudo -v
git fetch origin freepool
CODE=efd27747a7e21313345b11b82b1bd6488ee32f78
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r12.XXXXXXXX")
printf 'private_run_directory=%s\n' "$D"
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  f2253a5461c10ecc48ffa1067d906ed628d6966a6455800285f4bea7b84164ad "$H" \
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
args=(--state "$D/result.json" --compare-http --compare-context)
if test -n "${XGW_PAGE_FILE:-}"; then
  cp -- "$XGW_PAGE_FILE" "$D/page.txt"
  chmod 600 "$D/page.txt"
  args+=(--page-file "$D/page.txt")
fi
printf 'live_start_utc=%s\n' "$(date -u +%FT%TZ)"
rc=0
sudo "${HELPER[@]}" "${args[@]}" || rc=$?
printf 'live_end_utc=%s helper_rc=%s\n' "$(date -u +%FT%TZ)" "$rc"
sudo xgw diag --no-net >"$D/diag-after"
exit "$rc"
)
```

Ожидаются 117 тестов. При FAIL или STOP указать этап, фактический результат и причину.
Исполнитель сам читает диагностику, STAGE, MARIONETTE_ERROR, PAGE_FETCH, BROWSER,
ATTEMPT, CHECK и RESULT/STOP. Путь приватного каталога в отчёт не переносить.
Проверить завершение Firefox и удаление профиля. При доступной панели сверить статусы с Vision.

## 3. Чтение результатов

Один живой запуск. Firefox работает через прежнее реле, лимит 120 с и 16 МиБ.
После подтверждения воспроизведения fetch обращается к выбранному ресурсу с Range
`bytes=0-16383` в той же вкладке. У запроса обычный CORS, credentials=omit,
cache=no-store и запрет перехода по редиректу. Таймер fetch — 4 с, счётчик тела
ограничен 16 КиБ, весь трафик Firefox учитывается в бюджете реле.
Оба curl после Firefox используют тот же кандидат и служебный вход, лимит 8 с и до 32 КиБ.

- В PAGE_FETCH сверить candidate_index с ATTEMPT и указать outcome, http, bytes, video_mime.
  Поле browser_fetch в квитанции должно совпасть со строкой PAGE_FETCH.
- С HTTP 200/206, 16 КиБ и video_mime=true вкладка подтвердила чтение видео через fetch.
  Если curl получил короткое тело, записать разницу в этой паре.
- При unreadable без HTTP-статуса причина недоступности ответа остаётся открытой. Не
  приравнивать такой исход к нулю байт или ошибке сервера. При timeout записать доступные поля.
- При control_failed, browser_budget или отсутствии PAGE_FETCH указать достигнутые этапы.
  При смене выбранного пути сохранить наблюдения и пометить сравнение непроверенным.
- Сопоставить capture, zapret2 и диагностику до и после. При отсутствии естественной
  ротации сценарий ротации остаётся NOT_RUN.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r12-ДАТА.md`.
Указать CODE, суммы, результат тестов, способ самостоятельного запуска, время UTC,
PAGE_FETCH, завершённые ATTEMPT и конечную диагностику. При NOT_RUN указать, какой доступ
запрашивался и почему запуск остался недоступен. Проверить отчёт на секреты.
При любом исходе в отдельном рабочем дереве от свежей `origin/freepool` закоммитить только
отчёт, проверить diff, сделать обычный push и сверить файл на GitHub. При гонке перенести
коммит на свежую ветку и повторить push без force. Сообщить хеш и ссылку. При сбое push
сохранить файл и указать причину. Отдельное подтверждение публикации отчёта не требуется.
