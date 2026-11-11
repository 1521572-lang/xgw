# ThinkCentre. Повторный GET с учётом размеров ресурсов Firefox

CODE `e4bedaf85f8a12d55d496a95ee1cff36e5c58583`, отчёт r6 `4c94d9b`. Исполнитель GLM-5.3-Flash.
В r6 Firefox воспроизвёл YouTube через VPN, два повторных GET вернули HTTP 200 и 31 байт.
В r7 проверяем порядок кандидатов по transferSize и новые поля квитанции.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
Адреса, порты, профили, токены и журналы оставить приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=e4bedaf85f8a12d55d496a95ee1cff36e5c58583
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r7.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  841019c704465839f7ddcfb14c67d59b371a2528a2aeee7bfdffcfacc1c085fe "$H" \
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

Ожидаются 85 тестов при доступных зависимостях. Указать результат и причины пропусков.
Новые проверки охватывают порядок кандидатов, дубли, нулевые и неизвестные размеры,
передачу полей из Firefox и совпадение ATTEMPT с квитанцией. При FAIL перейти к отчёту.
Исполнитель сам сверяет capture on, zapret2 off, свежий статус, Firefox и живой
безлимитный VPN-выход. Если панель доступна, открыть статусы шлюза и прочитать их с Vision.

## 2. Живой прогон

Исполнитель сам проводит один согласованный запуск с публичной страницей владельца.
Firefox ограничен 120 с и 16 МиБ через реле. После подтверждения воспроизведения выбираются
до трёх уникальных допустимых адресов из 16 последних записей о видеоресурсах. Порядок
по убыванию transferSize, при равенстве сначала подсказка video MIME, затем свежесть.
На серию GET 8 с. Каждый запрашивает `Range: bytes=0-16383` и читает до 16 КиБ тела.
Серия читает до 48 КиБ тела, отдельно учитываются заголовки и TLS. После первого HTTP
200/206 с video/* и минимум 16 КиБ тела серия завершается.

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
Сверить число кандидатов, последовательные номера попыток и совпадение с replay_attempts.
Для каждой попытки указать attempt, candidate_index, transfer_size и decoded_body_size
в байтах, итог, HTTP, байты ответа, video_mime и verdict, если они есть. candidate_index
считает записи Firefox с 1 в порядке от новых к старым и может идти с пропусками.
Размер null означает недоступное значение. Для порядка приравниваем null к 0, в отчёте
оставляем значения как есть. Проверить невозрастающий порядок transfer_size.
При STOP прочитать квитанцию и сохранить завершённые попытки. Проверить завершение
временного Firefox и удаление профиля. При доступной панели сверить статусы с Vision.

## 3. Чтение результатов

- `browser_video_verified` — указать успешную попытку и размеры исходной записи Firefox.
- `replay_failed` или `replay_not_video` — показать завершённые попытки и сопоставить
  браузерные размеры с байтами повторного GET. При нулевых или недоступных размерах
  указать, удалось ли в этом прогоне сравнить кандидатов по transferSize.
- `replay_time_budget` — указать оставшихся кандидатов по счётчикам и завершённые попытки.
- При отсутствии естественной ротации живой сценарий ротации остаётся NOT_RUN.

Сопоставить capture, zapret2 и диагностику до и после. При отсутствии условий для запуска
оформить NOT_RUN. Один живой запуск на ТЗ. После любого исхода перейти к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r7-ДАТА.md`.
Указать CODE, суммы, тесты, фактические действия, наблюдения Firefox, число кандидатов,
все завершённые ATTEMPT, итог и конечную диагностику. Проверить отчёт на секреты,
использовать отдельное рабочее дерево от свежей `origin/freepool`, закоммитить только
отчёт, проверить diff, сделать обычный push и сверить файл в GitHub. При гонке перенести
свой коммит на свежую ветку и повторить push без force. Подтверждение публикации
не требуется. Сообщить хеш и ссылку. При сбое push сохранить файл и указать причину.
