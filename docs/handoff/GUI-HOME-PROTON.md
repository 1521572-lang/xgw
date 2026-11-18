# Приёмка главного окна XGW на Ubuntu 24.04 LTS

Проверь и установи новый главный экран на работающем ThinkCentre. Код GUI закреплён за `3c4ae6b8446cd36e94dad1b3a9f74ac75dca23b5`. Слева поиск, подписки, фильтры и серверы. В центре карта, состояние и действие. Справа разделы XGW, внизу сведения шлюза. [Образец из Qt на демонстрационном каталоге, тёмная тема, 125%](images/gui-home-dark.png). На машине имена, статус, флаги, оттенок карты и показатели зависят от API.

Flash сама запускает команды, смотрит окно и сохраняет отчёт. При отсутствии терминала, sudo или рабочего стола запроси доступ. Системный код и тесты поставлены в GitHub. Задание ограничено GUI. Переключение рабочего маршрута и просмотр YouTube относятся к [сетевому этапу T12](../reports/2026-11-18_desync-t12-selective-media-pairs.md). Продолжительность этого прохода около 25 минут.

## 1. Подготовка

Выполняй блоки в Bash от пользователя графической сессии. Если проверка остановилась, запиши шаг и ошибку, затем перейди к возврату и публикации.

```bash
set -euo pipefail
umask 077
. /etc/os-release
printf '%s\n' "$PRETTY_NAME"
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
BR=integration/zapret2-batch1
CODE=3c4ae6b8446cd36e94dad1b3a9f74ac75dca23b5
OLD=ba62c75d5bb05354cb1860c22696b57240e84299
BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git cat-file -e "$BASE^{commit}" || git fetch origin "$BASE"
D=$(mktemp -d "$HOME/xgw-gui-home.XXXXXXXX")
GUI=/opt/xgw/gui/releases/$BASE
P=/var/lib/xgw/handoff/gui-home-$CODE
F=(vpn_ui/main_xgw.py vpn_ui/views/map_canvas_view.py vpn_ui/xgw/panels.py
   vpn_ui/xgw/sidebar.py vpn_ui/xgw/window.py)
test -f "$GUI/vpn_ui/main_xgw.py"
grep -Fq "$GUI/vpn_ui/main_xgw.py" /opt/xgw/lib/xgw/gui/app.py
for f in "${F[@]}"; do
  rev=$OLD
  case "$f" in vpn_ui/main_xgw.py|vpn_ui/xgw/panels.py) rev=$BASE ;; esac
  mkdir -p "$D/before/$(dirname "$f")" "$D/after/$(dirname "$f")"
  git show "$rev:$f" > "$D/before/$f"
  git show "$CODE:$f" > "$D/after/$f"
done
for h in gui_home_install.py gui_catalog_install.py; do
  git show "$CODE:docs/helpers/$h" > "$D/$h"
done
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service > "$D/services.before"
sudo sha256sum /etc/xgw/config.toml > "$D/config.before"
```

## 2. Проверка композиции до установки

Используй копию фактически установленного GUI. Так тест включает ранее принятые накладки каталога и zapret2. Переключения состояний выполняет фиктивный клиент. Для pytest выбери существующий интерпретатор с pytest и системным PyQt6. Если `/usr/bin/python3` не содержит pytest, используй имеющийся dev-venv или создай `python3 -m venv --system-site-packages "$D/venv"` и установи в него pytest. GUI в этом разделе работает без сетевых запросов.

```bash
mkdir -p "$D/scene/tests/fixtures/gui"
cp -R "$GUI/vpn_ui" "$GUI/src" "$D/scene/"
cp -R "$D/after/vpn_ui/." "$D/scene/vpn_ui/"
git show "$BASE:tests/test_vpn_ui_xgw.py" > "$D/scene/tests/test_vpn_ui_xgw.py"
git show "$CODE:tests/test_vpn_ui_sidebar.py" > "$D/scene/tests/test_vpn_ui_sidebar.py"
git show "$BASE:tests/fixtures/gui/state-work.json" > "$D/scene/tests/fixtures/gui/state-work.json"
PY=${XGW_GUI_TEST_PYTHON:-/usr/bin/python3}
"$PY" -c 'import pytest, PyQt6.QtSvg, PyQt6.QtWidgets'
(cd "$D/scene" && QT_QPA_PLATFORM=offscreen PYTHONPATH="$D/scene:$D/scene/src" \
 "$PY" -m pytest -q tests/test_vpn_ui_sidebar.py tests/test_vpn_ui_xgw.py)
```

Ожидается 10 passed, 0 skipped. Если Qt или тест падает, зафиксируй ошибку и оставь действующий GUI.

## 3. Установка в действующее приложение

Закрой только окно XGW обычной кнопкой. Рабочие службы остаются запущенными. Помощник сверяет все пять модулей и установленный dispatcher с прежней поставкой, сохраняет права и меняет файлы атомарно. Dispatcher берётся из резервной копии принятой установки. Он передаст выбор темы новому окну. При прерванной операции тот же помощник поддерживает повтор и возврат.

```bash
sudo install -d -m 0700 "$P"
for h in gui_home_install.py gui_catalog_install.py; do
  sudo install -o root -g root -m 0600 "$D/$h" "$P/$h"
done
for kind in before after; do
  for f in "${F[@]}"; do
    sudo install -D -o root -g root -m 0600 "$D/$kind/$f" "$P/$kind/$f"
  done
done
home_install() { sudo /usr/bin/python3 -I "$P/gui_home_install.py" "$1"; }
home_install check
home_install apply
home_install check
```

Нужны `INSTALLED` и `READY changed files: 0` после применения. При неизвестных байтах остановись и сообщи имя файла. Запусти **`xgw gui`** от пользователя рабочего стола через доступный графический терминал или `systemd-run --user --collect xgw gui` в его графическом сеансе.

## 4. Что посмотреть в установленном окне

1. При ширине около 1002×650 логических пикселей сравни композицию с образцом. Сохранённая тема имеет приоритет, первое открытие с чистыми настройками использует тёмную. Выбранную ранее тему запиши и верни перед завершением. Проверь заголовок, перемещение, изменение размера, сворачивание, повторный вызов `xgw gui` и закрытие.
2. В левой панели проверь Ctrl+F, выбор подписки, три вкладки фильтра и каждую сортировку в обоих направлениях. Жди два обновления API. В строках должны читаться имя, страна **по IP**, скорость и рейтинг. При длинном имени наведи на строку и прочитай его целиком в карточке справа. Сверь источник и сортировку после обновления. Наведение и фильтрация сохраняют рабочий сервер.
3. В центре сверь название, флаг и страну с применённым сервером. При свежем VPN-соединении с известной страной проверь пульс по двум кадрам с интервалом около секунды. При другой исходной конфигурации опиши её, а переход между странами, stale и standalone оцени по Qt-тестам. Основную кнопку и подтверждение выбора на живом шлюзе не нажимай. Проверь подпись действия и нижний статус в фактическом режиме.
4. Справа открой zapret2, устройства, трафик, диагностику, «Ещё» и настройки. Сверь видимый статус zapret2 с текущим режимом панели. Для проверки перехода в раздел достаточно открыть и закрыть его. Не запускай диагностику сети, смену стратегии или изменение маршрута.
5. Переключи тему. Проверь контраст заголовков, флагов и значений; закрой и снова открой `xgw gui`, проверь сохранение темы. Проверь 720×660 и минимальное окно. Раскрой ☰, нажми Esc, открой настройки и вернись на карту. Проверь, что наложенная панель читаема и можно добраться до строк и кнопок. Сохрани скриншоты приватно.
6. После PASS оставь новый GUI. При сбое запуска, неверных состояниях, пропаже навигации или неудобочитаемом окне закрой GUI и выполни `home_install rollback` (ожидается `RESTORED`), затем снова запусти `xgw gui`. Запиши, какая версия осталась. Сверь итог с исходным состоянием:

```bash
systemctl show -p MainPID -p ActiveState xgw.service xgw-xray.service > "$D/services.after"
cmp "$D/services.before" "$D/services.after"
sudo sha256sum -c "$D/config.before"
```

## 5. Отчёт и публикация

Включи CODE, PRETTY_NAME, версии Qt/Python, размер окна и масштаб, результаты fixture и отдельные результаты **установленного** окна. Для установки, тем, каталогов, карты, статуса, переходов, размеров, сохранения темы и состояния служб укажи PASS / FAIL / NOT_RUN с наблюдением. При блокере опубликуй BLOCKED и укажи запрошенный доступ. Скриншоты с реальными подписками, именами серверов, IP или токенами остаются на машине.

Самостоятельно опубликуй только Markdown-отчёт по завершении, также после FAIL или блокера. В отдельном checkout от актуальной ветки создай файл по пути `$REPORT` и заполни фактическими результатами перед `git add`.

```bash
cd "$REPO"
git fetch origin "$BR"
git worktree add --detach "$D/report" FETCH_HEAD
cd "$D/report"
REPORT="docs/reports/$(date +%F)_gui-home-proton.md"
# Здесь напиши отчёт о выполненных проверках в "$REPORT".
git add -- "$REPORT"
git diff --cached --check
git diff --cached --stat
git commit -m "docs: report Ubuntu 24.04 XGW home screen acceptance"
git push origin "HEAD:refs/heads/$BR"
git ls-remote origin "refs/heads/$BR"
```

Если подготовка остановилась до создания `$D`, для публикации укажи `REPO=$(git rev-parse --show-toplevel)`, `BR=integration/zapret2-batch1` и создай временный каталог командой `D=$(mktemp -d)`. Если ветка успела уйти вперёд, выполни `git fetch origin "$BR"`, `git rebase FETCH_HEAD` и обычный push. При конфликте с одноимённым чужим отчётом сохрани свой под уникальным именем и оставь опубликованный файл.
