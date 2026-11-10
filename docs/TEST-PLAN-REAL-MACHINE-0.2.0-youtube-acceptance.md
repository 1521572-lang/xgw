# ThinkCentre. Признак допуска YouTube в выборе выхода

Исполнитель GLM-5.3-Flash. Отчёт 059258a подтвердил признак, HANDOVER §4.2 определяет доработку.
Отчёт 3ee7093 зафиксировал рабочий шлюз на bfb8218 и допустимый inactive sing-box.
Архив и пересборка nfqws2 для этой проверки не требуются.
Машинное зрение по окну не кликает. Вывод конфигов, сырых статусов, журналов и содержимого базы
в отчёт запрещён. Адрес ролика задаёт владелец приватно. Подписки, WAN, LAN, Tailscale, ручной
выбор, пул и zapret2 не менять. Службы ядер не перезапускать.

## 1. Подготовка

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=fbd4c28c2b1fd60f4f01d640f8a979c5d184824c
BASE=bfb82184aabd913b145e9a6cef68b4168012d56c
umask 077
D=$(mktemp -d "$HOME/xgw-youtube-acceptance.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/youtube_acceptance_check.py"
printf '%s  %s\n' 'ab48cc8eb0f121c87857cd94d12614375aef76d8d05c964332b632408240c5c8' "$H" | sha256sum -c -
sudo python3 -I "$H"
sudo xgw diag --no-net >"$D/diag-before"
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_config.py tests/test_youtube.py tests/test_checks.py)
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_daemon.py -k media)
```

Нужны HEALTHY, capture on, best=0, route=0, отсутствие FAIL. Нет инструментов — NOT_RUN tools.
Расхождение базы или новое падение — STOP. Снять приватно MainPID и ActiveState обоих ядер.
Xray активен; sing-box может быть inactive при отсутствии используемых мостов. Проверяется
сохранение исходного состояния sing-box, а не обязательная работа службы.

## 2. Установка кода и один раунд

До установки получить согласие владельца. Сверить шесть установленных файлов
в /opt/xgw/lib/xgw с исходниками BASE: config.py, daemon.py, diag.py, watch/checks.py,
watch/status.py и watch/youtube.py. При расхождении STOP. Сохранить их и config.toml
с владельцами и правами. Сверить синтаксис, остановить только xgw.service, заменить эти
шесть файлов из CODE с прежними владельцами и правами, запустить xgw.service. Сверить HEALTHY
и ядра. При ошибке вернуть сохранённые файлы и настройки и запустить демон.

Для раунда получить отдельное согласие на временный best. Нужны штатные проверки [speed]
YouTube с положительным порогом, не менее одного свежего замера пригодного безлимитного
участника, запас суточного бюджета и подходящий адрес ролика от владельца.
Перед изменением записать `SINCE=$(date +%s)`. Временно задать `youtube_mode = "best"` и
`youtube_sign_url` в [media]. Суммы и пути записывать приватно. Проверить появление best=1,
sign_enabled=1 и отсутствие новых предупреждений. Для применения использовать штатное чтение
настроек демоном. Не включать повторные проверки вручную, не сбрасывать базу или бюджет.

```bash
sudo python3 -I "$H" --since "$SINCE"
sudo xgw diag --no-net >"$D/diag-run"
```

Окно до 12 минут. Снимать сводку не чаще раза в минуту. После свежего accept/refuse можно
завершить окно, при отказе дать два шага демона на применение. Повторяющийся refused_active>0
после двух шагов, потеря HEALTHY или смена состояния ядер — STOP и возврат. Если свежего
результата нет — NOT_RUN no_sample. Только unknown — PARTIAL unknown. Нет отказа — смена выхода
по отказу на машине остаётся NOT_RUN. Плавность и качество видео здесь не измеряются.

## 3. Возврат и отчёт

Во всех исходах восстановить исходный config.toml байт в байт, дождаться best=0 и route=0,
сверить HEALTHY, capture on и неизменное состояние ядер. Повторить diag --no-net.
Успешно установленный код оставить. При ошибке установки вернуть и файлы из резервной копии.
При неудаче возврата остановиться и сообщить владельцу.

Одна страница `docs/TEST-REPORT-REAL-MACHINE-0.2.0-youtube-acceptance-ДАТА.md`. Записать CODE,
сверку суммы, тесты, согласие, метки CHECK и SIGN, наличие строки допуска в статусе и diag,
событие смены при отказе (да/нет/NOT_RUN), результат возврата и какие шаги не выполнялись.
Без адресов, доменов, имён, тегов, ID ролика и сырых журналов.
