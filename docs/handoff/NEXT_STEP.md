# Ubuntu 24.04 — стрелки сортировки в установленном GUI

- Ветка integration/zapret2-batch1.
- Отчёт предыдущей приёмки и база ветки ffbf9017587ef05276b6d2edcca5b8fcb542437d.
- Исходный установленный sidebar.py из 4b711b7e304fe457ae9f2e5b25dd7d0b64e7c374.
- Полный GUI для тестов из 7c20f59023ec39e5c5ce4606767ea915c3b91f64.
- Опубликуй отчёт в docs/reports/YYYY-MM-DD_gui-sort-indicators.md.

Прочитай предыдущий отчёт docs/reports/2026-11-15_gui-catalog-map.md. Список, страны по IP и
анимация прошли приёмку. Нужно проверить соответствие стрелки фактическому порядку строк.
Прошлое ТЗ доступно в коммите 4b711b7. Используй терминал и vision сама. Если отсутствует доступ
к терминалу, sudo или рабочему столу, запроси его. Владелец не запускает команды за исполнителя.
После завершения автоматически опубликуй отчёт, в том числе при блокере.

## Подготовка

Выполняй блоки в одной сессии Bash. В исходном checkout проверь чистоту рабочего дерева.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
git fetch origin integration/zapret2-batch1
TIP=$(git rev-parse FETCH_HEAD)
CODE=$(git log -1 --format=%H "$TIP" -- docs/handoff/NEXT_STEP.md)
OLD=4b711b7e304fe457ae9f2e5b25dd7d0b64e7c374
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
git merge-base --is-ancestor ffbf9017587ef05276b6d2edcca5b8fcb542437d "$CODE"
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-gui-sort.XXXXXXXX")
F=vpn_ui/xgw/sidebar.py
git show "$OLD:$F" > "$D/sidebar.before"
git show "$CODE:$F" > "$D/sidebar.after"
git show "$CODE:tests/test_vpn_ui_sidebar.py" > "$D/test_vpn_ui_sidebar.py"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r
python3 --version
```

Прочитай dispatcher и подтверди путь по запущенному окну. Сохрани приватно хэши настроек и
PID служб для сравнения. Для этой графической правки достаточно следующего теста в полном GUI.
Используй имеющееся dev-venv с PyQt6 и pytest или отдельное, как в предыдущем проходе.

```bash
git worktree add --detach "$D/gui" "$GUI_BASE"
cp "$D/sidebar.after" "$D/gui/$F"
python3 -m venv --system-site-packages "$D/venv"
"$D/venv/bin/python" -m pip install pytest
"$D/venv/bin/python" -c 'import PyQt6.QtWidgets, PyQt6.QtSvg'
PYTHONPATH="$D/gui:$D/gui/src" "$D/venv/bin/python" -m pytest -q \
  "$D/test_vpn_ui_sidebar.py" -k header_clicks_sort_without_selecting_server
```

Тест должен пройти без skip. Он сверяет порядок и подпись заголовка после каждого щелчка
и после обновления списка. Проверь в GUI обе темы и узкое окно уже после установки.

## Замена одного файла GUI

Закрой окно штатно. Введи путь релиза, который подтвердил dispatcher. Если байты sidebar.py
отличаются от 4b711b7, опиши расхождение и остановись перед заменой. Если уже установлен
точный новый файл, переходи к проверкам. Для замены и отката используй одну и ту же функцию
с проверкой ожидаемых байтов. Она копирует файл во временный файл в том же каталоге и
атомарно переименовывает, сохраняя исходные права и владельца. Backend и системные службы
в эту операцию не входят. Для отката достаточно закрыть GUI, восстановить файл и открыть окно.

```bash
GUI=$(readlink -f /opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64)
TARGET="$GUI/$F"
sudo test -f "$TARGET"
sudo test ! -L "$TARGET"

replace_sidebar() {
  sudo bash -s -- "$TARGET" "$1" "$2" <<'BASH'
set -euo pipefail
target=$1
expected=$2
replacement=$3
test -f "$target"
test ! -L "$target"
cmp --silent -- "$expected" "$target"
next=$(mktemp -- "$(dirname -- "$target")/.sidebar.XXXXXXXX")
trap 'rm -f -- "$next"' EXIT
cat -- "$replacement" > "$next"
chown --reference="$target" "$next"
chmod --reference="$target" "$next"
cmp --silent -- "$expected" "$target"
mv -T -- "$next" "$target"
BASH
}

if ! sudo cmp --silent -- "$D/sidebar.after" "$TARGET"; then
  replace_sidebar "$D/sidebar.before" "$D/sidebar.after"
fi
sudo cmp --silent -- "$D/sidebar.after" "$TARGET"
```

Открой установленный XGW командой `xgw gui` от пользователя графической сессии. Запиши
результаты по каждому пункту.

- «Серверы» отсортированы по возрастанию при открытии и показывают ▲. Щелчок даёт ▼ и
  обратный алфавитный порядок. Второй щелчок возвращает исходный порядок.
- Первый щелчок по «Мбит/с» сортирует от большего к меньшему с ▼. Второй сортирует от
  меньшего к большему с ▲. Повтори для «Рейтинг». Пропуски визуально остаются внизу.
- Стрелка только в активном столбце, читается в обеих темах и при раскрытии узкого списка.
  Проверь, что заголовки и данные помещаются. Стрелка и порядок переживают обновление API.
- У строк видны имя и страна по IP. Проверь пульс на карте при действующем соединении и
  что сортировка не выбирает сервер. Сравни PID демона и Xray, хэши конфигов и SHA файла.
  Закрепи доказательства скриншотами локально. В отчёт внеси результат без имён серверов,
  IP, токена, подписок или полного API.

Если правка мешает нормальной работе GUI, закрой окно и выполни
`replace_sidebar "$D/sidebar.after" "$D/sidebar.before"`, затем сверь прежние байты и открой GUI.
При неожиданной версии установленного файла остановись до перезаписи и запиши результат.
Допускается отдельный хотфикс читаемости стрелки с повторным тестом и визуальной проверкой.

## Отчёт

Укажи CODE, ОС и Qt, установленный путь, PASS/FAIL/NOT_RUN по трём заголовкам и шести
направлениям, темам и узкому окну, автообновлению, списку, карте и SHA. Укажи, какая версия
оставлена на машине. Отдельно запиши блокер или откат, если они произошли.

Вернись в исходный checkout и опубликуй результат сразу после проверки.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c glm/gui-sort-indicators-report FETCH_HEAD
# Создай отчёт с фактической датой в имени.
git add docs/reports/YYYY-MM-DD_gui-sort-indicators.md
git diff --cached --check
git diff --cached
git commit -m "docs: report installed GUI sort indicators"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```
