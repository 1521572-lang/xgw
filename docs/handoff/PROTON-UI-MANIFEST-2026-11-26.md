# Приёмка Proton UI на ThinkCentre · Ubuntu 24.04 LTS

**Исполнитель — Flash, код для проверки — `92053147a07a923a662bc91edc9ff1e8a00db1db`.** Один проход в сеансе обычного пользователя ThinkCentre. Нужны терминал, рабочий стол с треем и доступ к панели XGW. При отсутствии доступа Flash запрашивает его и сама выполняет команды. Результат каждого пункта — PASS, FAIL или NOT_RUN с причиной. Исходники и рабочие службы шлюза во время проверки GUI не изменять.

### 1. Получить и установить клиент из одного дерева

В текущем локальном клоне XGW открыть Bash. Если объекта ещё нет, получить вместе с ТЗ файл `xgw-proton-p1.bundle` и задать `BUNDLE` равным его абсолютному пути. Для импорта нужен базовый коммит `9e4c025`. Если его нет в клоне, выполнить `git fetch origin integration/zapret2-batch1`. Если файла bundle нет на машине, запросить его у владельца. Команды ниже выполнять подряд в одном терминале.

```bash
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(id -u)" != 0
/usr/bin/python3 -I -c 'from PyQt6 import QtWidgets, QtSvg'
repo=$(git rev-parse --show-toplevel)
pin=92053147a07a923a662bc91edc9ff1e8a00db1db
if ! git -C "$repo" cat-file -e "$pin^{commit}" 2>/dev/null; then
    git -C "$repo" bundle verify "${BUNDLE:?нужен путь к переданному bundle}"
    git -C "$repo" fetch "$BUNDLE" refs/heads/feat/reproducible-proton-ui-and-manifest
fi
umask 077
d=$(mktemp -d)
mkdir "$d/source" "$d/previous" "$d/clean" "$d/update" "$d/prefs"
git -C "$repo" archive "$pin" | tar -x -C "$d/source"
git -C "$repo" archive 2c98b28 src packaging config.example.toml | tar -x -C "$d/previous"
stage_client() {
    XGW_ROOT="$2" PYTHONPATH="$1/src" /usr/bin/python3 -P -c \
      'from xgw.config import Config; from xgw.install import Installer; from xgw.paths import Paths; Installer(Config(), Paths.from_env())._code()'
}
cd "$d"
stage_client "$d/source" "$d/clean"
stage_client "$d/previous" "$d/update"
stage_client "$d/source" "$d/update"
ui=opt/xgw/lib/xgw/_desktop/vpn_ui
for prefix in clean update; do
    (cd "$d/$prefix/$ui" && find . -name __pycache__ -prune -o -type f -printf '%P\n' | LC_ALL=C sort) > "$d/installed-files"
    LC_ALL=C sort "$d/source/src/xgw/gui/proton-files.txt" | diff -u - "$d/installed-files"
    (cd "$d/source/vpn_ui" && xargs -d '\n' sha256sum < ../src/xgw/gui/proton-files.txt) |
        (cd "$d/$prefix/$ui" && sha256sum --check --quiet)
    test -x "$d/$prefix/usr/local/bin/xgw"
done
```

Это штатный этап установки системного кода `Installer._code()` в два пользовательских префикса на реальной машине. Он проверяет и чистую поставку, и переход с предыдущей ревизии. Полное обновление ОС, пакетов и служб в это окно не входит. Ошибку импорта Qt записать отдельно с версиями `python3-pyqt6` и `python3-pyqt6.qtsvg`.

### 2. Окно, трей и живые данные

```bash
export XGW_ROOT="$d/update" XDG_CONFIG_HOME="$d/prefs"
export XGW_GUI_INSTANCE="xgw-p1-$(id -u)-$(basename "$d")"
export XGW_GUI_SESSION="$d/session.json"
if [ -r "$HOME/.config/xgw/gui.json" ]; then
    install -m 600 "$HOME/.config/xgw/gui.json" "$XGW_GUI_SESSION"
fi
app="$XGW_ROOT/usr/local/bin/xgw"
XGW_ROOT="$d/clean" "$d/clean/usr/local/bin/xgw" gui >"$d/clean.log" 2>&1 & clean_pid=$!
```

1. Убедиться глазами, что чистая установка открыла Proton с картой и каталогом. Проверить авторизацию существующей сессией или штатной кнопкой входа. Закрыть это окно и выполнить `wait "$clean_pid"`. Запустить обновлённый значок командой `"$app" tray --run >"$d/tray.log" 2>&1 & tray_pid=$!`. Нажать на появившийся значок и выбрать открытие окна XGW. Проверить, что в списке своих процессов виден именно `$app gui`. Повторить из трея и командой `"$app" gui`. Ожидается то же окно с тем же PID, сессия сохранена.
2. Сверить выбранную подписку, строки серверов и наличие страны у записи с известным GeoIP. Навести на строку, открыть диалог выбора, отменить. Активный сервер и карта должны остаться прежними. Сверить страну активного сервера с определением по адресу в данных XGW. При доступном VPN убедиться, что маркер и анимация соответствуют активному соединению. При неизвестном GeoIP записать состояние отдельно.
3. Для проверки **смены** выбрать обычный доступный сервер другой известной страны, если исходный режим — VPN с автовыбором и доступно короткое окно переключения. Записать исходный режим. Подтвердить «На 10 минут», дождаться нового активного выхода по данным панели и смены маркера. Вернуть «Автовыбор XGW» и проверить ответ панели и рабочий VPN. Если исходный pin или отсутствие пригодного сервера мешают воспроизводимому возврату, выставить NOT_RUN только смене. Отмена в диалоге и успешный HTTP-ответ сами по себе смену выхода не подтверждают.

### 3. Откат и отчёт

При открытом Proton запустить `"$app" gui --builtin`, убедиться, что открывается встроенное окно и прежний процесс завершается. Закрыть окно. Выполнить `"$app" gui --set-default builtin`, дважды открыть через тестовый значок, проверить встроенное окно и единственный PID. Выполнить `"$app" gui --set-default proton`, снова открыть из трея и подтвердить возврат к Proton с той же сессией. Закрыть тестовое окно, завершить тестовый значок и сверить исходный режим шлюза. После сохранения результатов удалить созданный временный каталог с копией сеанса.

Оформить один обезличенный `docs/reports/<UTC>_proton-ui-manifest.md` при любом исходе. Включить полный SHA, версию Ubuntu и Qt, результаты чистой установки и обновления, запуска через трей, повторного открытия, выбора/карты и обоих способов отката. Отдельно отметить исходный и конечный режим, ошибки и пропуски. При необходимости приложить обрезанные кадры интерфейса без адресов, токенов и названий подписок. Передать отчёт владельцу вместе с результатами. Для этой локальной ветки публикацию на GitHub определяет владелец. Критерии закрытия также доступны в комплекте по команде `git show e65c658:docs/plans/ROADMAP.md`.
