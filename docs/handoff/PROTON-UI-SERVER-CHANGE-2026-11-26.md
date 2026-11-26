# ThinkCentre · смена VPN-сервера и маркера Proton

**Flash выполняет одну проверку на Ubuntu 24.04 LTS. Кандидат — `179d63a3a0c42682349b3d03b333e1734c609427`.** Закрытие обеих рамок, сессия, трей и отказ установки при неполной поставке подтверждены на `c9a8534`. Для смены сервера остался открытый результат `NOT_RUN`: исходный выход был закреплён вручную. [Отчёт повторной приёмки](https://github.com/1521572-lang/xgw/blob/2cd896e242170b7743be5daf077d2ffa375a1bfb/docs/reports/2026-11-26T070351Z_proton-ui-followup.md)

## 1. Подготовка без смены выхода

В графическом сеансе обычного пользователя выполнить команды в Bash из клона XGW. При отсутствии доступа запросить его. [Git bundle](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-proton-p1-server-change.bundle)

```bash
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(id -u)" != 0
/usr/bin/python3 -I -c 'from PyQt6 import QtWidgets, QtSvg'
repo=$(git rev-parse --show-toplevel)
candidate=179d63a3a0c42682349b3d03b333e1734c609427
umask 077
d=$(mktemp -d)
bundle="$d/server-change.bundle"
git -C "$repo" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$repo" show FETCH_HEAD:docs/handoff/artifacts/xgw-proton-p1-server-change.bundle >"$bundle"
printf '%s  %s\n' 'eec362866a968c04f8cd9eb045e56965456b8fae046c3e26ee0241c402b83c68' "$bundle" | sha256sum --check -
git -C "$repo" bundle verify "$bundle"
git -C "$repo" fetch "$bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$repo" rev-parse FETCH_HEAD)" = "$candidate"
mkdir "$d/src" "$d/root" "$d/prefs"
git -C "$repo" archive "$candidate" | tar -x -C "$d/src"
export XGW_ROOT="$d/root" XDG_CONFIG_HOME="$d/prefs"
export XGW_GUI_INSTANCE="xgw-proton-server-change-$(id -u)-$(basename "$d")"
export XGW_GUI_SESSION="$d/session.json"
if [ -r "$HOME/.config/xgw/gui.json" ]; then
    install -m 600 "$HOME/.config/xgw/gui.json" "$XGW_GUI_SESSION"
fi
cd "$d"
PYTHONPATH="$d/src/src" /usr/bin/python3 -P -c \
    'from xgw.config import Config; from xgw.install import Installer; from xgw.paths import Paths; Installer(Config(), Paths.from_env())._code()'
app="$XGW_ROOT/usr/local/bin/xgw"
"$app" gui >"$d/window.log" 2>&1 &
```

Открыть диалог другого сервера и нажать «Отмена». При существующем ручном закреплении ожидается предупреждение о замене и о возврате в автовыбор после истечения временного выбора. Сверить сохранение исходного маркера. Открытие и отмену можно проверить до согласования окна.

## 2. Согласованное окно и возврат

1. Запросить у владельца разрешение на **одно переключение и возврат**. Снять исходное состояние рабочего шлюза через авторизованную панель и обычный контрольный HTTPS через его VPN. Зафиксировать страну активного выхода, маркер, настройки перехвата, `pin.tag`, `pin.until` и `pin.down`. Полные теги и снимки сохранить локально.
2. Выбрать способ возврата по фактическому состоянию. При пустом `pin` возврат — «Автовыбор XGW». При здоровом бессрочном `pin` (`until: null`, `down: null`) сохранить тег исходного доступного сервера. Возврат — выбор именно этого сервера кнопкой «Бессрочно». Если понадобится резервная команда, заранее убедиться в наличии прав на штатный CLI. При временном или не отвечающем закреплении, отсутствии прав на возврат либо разрешённого окна оставить «смена выхода» как `NOT_RUN`.
3. В согласованное окно выбрать доступный сервер обычной подписки в другой стране с известным GeoIP. Подтвердить «На 10 минут». Дать до **90 секунд** на появление нового активного сервера по данным панели, контроль через VPN и перенос маркера. Отдельно отметить страну и видимое движение маркера. При несовпадении или истечении 90 секунд сразу перейти к возврату.
4. Вернуть исходный выбор сразу после наблюдения. При исходном бессрочном pin и отказе тестового окна использовать `sudo env -u XGW_ROOT /usr/local/bin/xgw pin "$original_tag" --ttl forever`, где `original_tag` — проверенный локальный тег исходного сервера. При исходном автовыборе резервная команда — `sudo env -u XGW_ROOT /usr/local/bin/xgw unpin`. При появлении стороннего ручного изменения во время окна согласовать возврат с владельцем перед записью. Сверить исходный режим и выбор, успешный HTTPS через VPN и маркер после возврата. При проблеме с возвратом сообщить владельцу фактическое состояние.

## 3. Отчёт

Закрыть тестовое окно, удалить временную копию сессии после фиксации результатов. При любом исходе опубликовать один обезличенный `docs/reports/<UTC>_proton-ui-server-change.md` в ветке `docs/flash-proton-ui-manifest`. Записать полный SHA, исходный тип выбора, наблюдаемые страны и время смены, результат контрольного HTTPS и способ возврата. Отдельно указать исход диалога с отменой. Полный системный install и обновление служб в это ТЗ не входят.
