# ThinkCentre. Смена выхода при отказе YouTube на отдельном Xray

Исполнитель GLM-5.3-Flash. Отчёт ef11633 подтвердил сбор признака в best. Отказов за окно
не было. Здесь проверяются две реакции на синтетический LOGIN_REQUIRED с настоящим API Xray.

Шлюз работает в прежнем режиме. Не включать best и zapret2, не менять настройки, базу, пул,
подписки, WAN, LAN, Tailscale и ручной выбор. Не перезапускать службы, не скачивать пакеты.
Машинное зрение по окну не кликает. Помощник работает только с временным каталогом
и отдельным процессом уже установленного Xray. Тестовые выходы отбрасывают трафик.

## 1. Сверка и запуск

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=b914cd68b3de5a031dcaec456fc6db6350398b82
umask 077
D=$(mktemp -d "$HOME/xgw-youtube-refusal.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
H="$D/source/docs/helpers/youtube_refusal_check.py"
printf '%s  %s\n' '6e2258337470ece9452ddc20cbf6b66b1d737ba621751ef680176bf651eab40c' "$H" | sha256sum -c -
sudo xgw diag --no-net >"$D/diag-before"
```

До запуска шлюз HEALTHY, capture on, diag без FAIL. Состояние и PID обоих ядер записать приватно.
Sing-box может быть inactive, если мосты не используются. Сверить отсутствие изменений после прогона.

```bash
RC=0
sudo unshare -n -- python3 -I "$H" || RC=$?
printf 'helper_rc=%s\n' "$RC"
sudo xgw diag --no-net >"$D/diag-after"
```

Нет unshare, прав на отдельное сетевое пространство или бинарника — NOT_RUN. Запускать помощник
в общей сети вместо отдельного пространства запрещено. STOP и код 2 — сообщить метку, не повторять.

Ожидаемый вывод:

```text
CHECK baseline=1
CHECK switched_on_refuse=1
CHECK common_on_all_refuse=1
CHECK refusal_events=2 xray_alive=1
RESULT refusal_path_ok
```

Первый отказ убирает выход до истечения hold, тестовое соединение идёт через второго кандидата.
При отказе второго отдельное правило удаляется, следующее соединение идёт общим маршрутом.
Помощник останавливает только свой процесс, в том числе при ошибке. Это проверка реакции на
синтетический ответ. Отказ от реального YouTube и воспроизведение видео здесь NOT_RUN.

## 2. Отчёт

После прогона сверить HEALTHY, capture on, исходные состояния и PID ядер. В ef11633 после
возврата в счётчике появилось одно WARN без пояснения.
Если здесь есть WARN, указать безопасную категорию и было ли оно до прогона. Сырые строки
диагностики, адреса, имена, теги, PID, ID ролика и пути не публиковать.

Одна страница `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-refusal-ДАТА.md`. В отчёт CODE, сверка
суммы, версия бинарника, вывод помощника, его код возврата, diag до и после, итог PASS/STOP/NOT_RUN.
