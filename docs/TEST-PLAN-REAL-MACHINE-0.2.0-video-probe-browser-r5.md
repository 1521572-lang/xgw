# ThinkCentre. Диагностика команд Marionette после запуска Firefox

CODE `77db4ecb3a1c1cc62f651f53d2212b33b449bb2b`, отчёт r4 `3b05311`. Исполнитель GLM-5.3-Flash.
В r4 сессия Firefox открылась, началась навигация и через реле прошло 5,3 МиБ.
Проверяем, отвечает ли Navigate, начинается ли наблюдение и появляется ли
видео. При ошибке определяем команду и класс исключения по квитанции.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
В отчёт включать числа и признаки. Адреса, порты, профили, токены и журналы оставить приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=77db4ecb3a1c1cc62f651f53d2212b33b449bb2b
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r5.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/video_probe_browser_check.py"
printf '%s  %s\n' \
  f1e972b47bc13e28d002b382cc97354a319db1dab67e76a1ba0de23ced6d6294 "$H" \
  725d9f81f39164123336aa2855bc7a2610dd609d5059122190694a844d272b7a \
  "$D/new/docs/helpers/video_probe_check.py" | sha256sum -c -
python3 -I "$H" --help
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_video_probe_browser_check.py tests/test_video_probe.py \
  tests/test_video_browser.py tests/test_checks.py)
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидаются 78 тестов при доступных зависимостях. Указать результат и причины пропусков.
Новые сценарии проверяют обезличивание ответа с ошибкой, запись EOF с именем метода,
сохранение последней ошибки до завершения и различение ответа Navigate и наблюдения.
При FAIL перейти к отчёту. Исполнитель сам проверяет capture on, zapret2 off, свежий статус,
Firefox и живой безлимитный VPN-выход. При доступной панели сверить статусы с Vision.

## 2. Живой прогон

Исполнитель сам проводит один согласованный запуск с публичной страницей владельца.
Лимиты прежние: до 120 с и 16 МиБ через прокси для Firefox, до 64 КиБ и 8 с для GET.
NewSession получает до 30 с из оставшегося времени. Используется youtube_sign_url или
watch-адрес из zapret2.probe_urls. Если адреса нет, владелец предоставляет одну строку
в приватном `$D/page.txt` (0600). Настройки шлюза не править.

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

Исполнитель читает STAGE, MARIONETTE_ERROR, BROWSER, VIDEO, CHECK и RESULT/STOP.
В квитанции проверить порядок этапов и последнее поле marionette_error, если оно появилось.
Рукопожатие обозначается Greeting. Ответ Firefox с ошибкой получает ограниченный код.
Текст ошибки, стек и параметры в отчёт не добавлять. При STOP сверить сохранённую квитанцию,
завершение временного Firefox и удаление профиля. При доступной панели сверить Vision
и конечную диагностику. Квитанцию не удалять ради повтора.

## 3. Чтение результатов

- `navigation_returned` означает успешный ответ Navigate. `observation_started` означает
  переход к циклу наблюдения. Последний метод и класс ошибки брать из MARIONETTE_ERROR.
- Ошибка ответа Navigate может предшествовать переходу к наблюдению. Отметить последовательность
  меток, результат наблюдения и метод последнего сбоя. Если EOF, таймаут канала или ошибка
  рамки произошли на Navigate, не считать цикл наблюдения начатым.
- `RESULT browser_video_verified` подтверждает повторный GET через VPN с HTTP 200/206,
  video/* и минимум 16 КиБ. Прямой путь zapret2 проверяется отдельным экспериментом.
- Для BROWSER, VIDEO, CHECK и остальных исходов применять условия r2–r4. При естественной
  ротации сверить события пула. Без неё отметить NOT_RUN для живой ротации.

Сопоставить capture, zapret2 и диагностику до и после. При отсутствии условий для запуска
оформить NOT_RUN. После любого исхода переходить к публикации.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r5-ДАТА.md`.
Указать CODE, суммы, тесты, объём прогона, STAGE/MARIONETTE_ERROR/BROWSER/VIDEO/CHECK/RESULT
или STOP, последнюю метку, первый невыполненный шаг и конечную диагностику.
Проверить отчёт на секреты, использовать отдельное рабочее дерево от свежей `origin/freepool`,
закоммитить только отчёт, проверить diff, сделать обычный push в `freepool` и сверить файл на GitHub.
При гонке перенести свой коммит на свежую ветку и повторить push без force. Подтверждение
публикации не требуется. Сообщить хеш и ссылку. При сбое push сохранить файл и указать причину.
