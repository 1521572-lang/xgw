# ThinkCentre. Запуск Marionette и сохранение этапов видеопробы Firefox

CODE `310bdac22323a8d12ccb26133a987515a0f59292`, предыдущий план `b4f4c25`. Исполнитель GLM-5.3-Flash.
В отчёте r2 прогон остановился до первого результата браузера. Отдельная проверка
показала запуск Marionette за 4–6 секунд на порту вне эфемерного диапазона.
Цель — проверить запуск новым помощником и, если Firefox получает видео, повторный GET.
Запуск из исходников с временным профилем. Службы, маршруты, настройки и sysctl сохраняются.
В отчёте только числа и признаки. Адреса, порты, профили, токены и журналы остаются приватно.

## 1. Подготовка и тесты на ThinkCentre

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
git fetch origin freepool
CODE=310bdac22323a8d12ccb26133a987515a0f59292
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-video-probe-browser-r3.XXXXXXXX")
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

Ожидаются 71 тест при доступных зависимостях. Указать результат и причины пропусков.
Новые тесты проверяют исключение эфемерных портов, занятый порт, отказ от навигации
в чужом профиле и сохранение квитанции при прерывании браузерной фазы. При FAIL перейти к отчёту.
Исполнитель сам проверяет capture on, zapret2 off, свежий статус, наличие Firefox и живого
безлимитного VPN-выхода. При доступной панели XGW открыть нужный экран и сверить статусы
с помощью Vision. Не просить владельца читать их или снимать скриншоты.

## 2. Живой прогон

Исполнитель сам проводит один согласованный запуск с публичной страницей владельца.
До 120 секунд и 16 МиБ переданных прокси данных для Firefox, до 64 КиБ и 8 секунд для GET.
Адрес берётся из youtube_sign_url или watch-адреса в zapret2.probe_urls. Если его нет, владелец
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

Исполнитель читает строки STAGE и сверяет обезличенную квитанцию. Порядок до навигации:
`relay_ready`, `marionette_port_reserved`, `firefox_started`, `marionette_ready`,
`session_ready`, `navigation_started`. При движении плеера добавится `playback_observed`.
В отчёт указать последнюю метку и первый невыполненный шаг. При STOP после запуска
проверить, что временный процесс и профиль закрыты, и зафиксировать только факт.
При доступной панели сверить конечное состояние с Vision. Квитанцию не удалять ради повтора.

## 3. Чтение результатов

- `marionette_ready` подтверждает рукопожатие. `session_ready` подтверждает ожидаемый профиль.
  При `browser_profile_unverified` навигация не выполняется. Для разбора сохранить последнюю метку.
- `marionette_listen_timeout` — процесс остался жив, соединение до срока не открылось.
  `browser_start_failed` — процесс завершился. При `browser_control_failed` записать, дошёл ли
  прогон до рукопожатия, сессии или навигации. Причину без наблюдений не приписывать порту.
- `RESULT browser_video_verified` — Firefox и повторный GET дали подтверждение через VPN.
  Критерий GET — HTTP 200/206, video/* и минимум 16 КиБ. Для прямого пути нужен отдельный прогон.
- Для остальных BROWSER/VIDEO/CHECK и сверок состояния действуют условия r2. Штатную ротацию
  отмечать по событиям, если она случилась. Без неё сценарий живой ротации остаётся NOT_RUN.

Сопоставить диагностику до и после, состояние захвата и режима zapret2. При STOP или NOT_RUN
отчёт публикуется по тем же правилам. Если живой запрос не начинался, отметить это явно.

## 4. Автоматическая публикация отчёта

Исполнитель сам оформляет одну страницу `docs/TEST-REPORT-REAL-MACHINE-0.2.0-video-probe-browser-r3-ДАТА.md`.
Указать CODE, суммы, тесты, согласованный объём прогона, STAGE/BROWSER/VIDEO/CHECK/RESULT или STOP,
причину NOT_RUN, если применимо, и диагностику до и после. Сохранить порядок наблюдений.
После проверки на секреты использовать отдельное рабочее дерево от свежей `origin/freepool`,
добавить в коммит только отчёт, проверить diff, сделать обычный push и сверить файл на GitHub.
При гонке перенести свой коммит на свежую ветку и повторить push без force. Подтверждение
публикации не требуется. В ответе сообщить хеш и ссылку. При сбое push сохранить файл и причину.
