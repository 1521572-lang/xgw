# ThinkCentre: карта и карточки серверов в светлом GUI

Цель: установить только пять файлов окна, проверить компоновку и открытие сведений по клику.
CODE `8b02d4c9178643e8740db55612bd7690e90bee34`, версия 0.2.0. Установщик не запускать.
Нельзя останавливать/перезапускать демон, Xray, sing-box, менять сеть, VPN, pin, пул или подписки.
Терминал, зрение, браузер и другие инструменты разрешены для этих шагов. Просмотр может делать Flash.
Локальные четыре Qt-теста уже прошли; полный набор здесь не повторять. Главная приёмка — живое окно.
DEGRADED допустим при рабочем on. Отчёт сохраняется и при STOP; невыполненные пункты — NOT_RUN.
Снимки реального окна, имена, адреса, токены и содержимое конфигов в Git не отправлять.

## 1. Подготовить источник и определить установленную версию окна

Все блоки — в одной bash-сессии. При ненулевом rc остановиться и записать шаг; не чинить службы.

```bash
set -euo pipefail
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=8b02d4c9178643e8740db55612bd7690e90bee34
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-gui-layout.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
G=/opt/xgw/lib/xgw/gui
N="$D/new/src/xgw/gui"
H="$D/new/docs/helpers/gui_layout_check.py"
printf '%s  %s\n' f665de3e488e33b7a1dbbcd7c17e34cce6e3f60b4372173fb665c5d8fc9581f3 "$H" | sha256sum -c -
sudo test -d "$G"
sudo test ! -L "$G"
BASE=
for ref in 97af08130321318241be3afc5c54bc8e85b7e273 92bda2bbec92a3b330757668d964b79765b97f37 5942365f536788673335ca93177a663f52660e04; do
    git worktree add --detach "$D/$ref" "$ref"
    B="$D/$ref/src/xgw/gui"
    same=1
    diff -q <(find "$B" -maxdepth 1 -name '*.py' -printf '%f\n' | sort) <(sudo find "$G" -maxdepth 1 -name '*.py' -printf '%f\n' | sort) >/dev/null || same=0
    for source in "$B"/*.py; do
        f=${source##*/}
        sudo test ! -L "$G/$f" && sudo cmp -s "$source" "$G/$f" || same=0
    done
    if test "$same" = 1; then BASE=$ref; break; fi
done
test -n "$BASE" || { echo 'STOP unknown_gui_base'; exit 2; }
printf 'OK gui_base=%s\n' "$BASE"
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Ожидается: сумма OK; один из известных BASE; `OK baseline: capture_on=1 services_active=1`.
Хелпер ничего не меняет; stdout отказа содержит `stage=...`. Проверить diag локально, записать только OK/WARN/FAIL.
Новый FAIL, неизвестная версия GUI или отсутствие PyQt6 — STOP; не устанавливать пакеты ради обхода ворот.
Если GUI неизвестного состава, достаточно сообщить этот факт; не перезаписывать его «на пробу».

## 2. Согласие и замена пяти файлов

Получить согласие владельца: заменить `pages.py`, `theme.py`, `widgets.py`, `window.py`, добавить `mapdata.py`.
Объяснить: меняется окно, службы и сетевые правила не затрагиваются; возврат — из копии ниже.
Нет согласия — NOT_RUN install, отчёт с причиной. Согласие старой волны не использовать.
Закрыть только окно XGW обычной кнопкой закрытия. Трей и службы не останавливать.
Дождаться выхода именно процесса GUI; если он не выходит, STOP, не использовать массовые pkill/killall.

```bash
sudo bash -s -- "$G" "$N" "$D" "$B" <<'SH'
set -Eeuo pipefail
G=$1 N=$2 D=$3 B=$4
files=(pages.py theme.py widgets.py window.py mapdata.py)
# Повторно сверить базу непосредственно перед заменой.
for source in "$B"/*.py; do
    f=${source##*/}
    test ! -L "$G/$f"
    cmp -s "$source" "$G/$f"
done
test ! -e "$G/mapdata.py" && test ! -L "$G/mapdata.py"
python3 - "$N" <<'PY'
import pathlib, sys
for name in ('pages.py', 'theme.py', 'widgets.py', 'window.py', 'mapdata.py'):
    p = pathlib.Path(sys.argv[1]) / name
    compile(p.read_bytes(), str(p), 'exec')
print('OK syntax')
PY
mkdir -m 700 "$D/saved"
for f in "${files[@]}"; do
    if test -f "$G/$f"; then cp -a -- "$G/$f" "$D/saved/$f"; fi
done
restore() {
    for f in "${files[@]}"; do
        if test -f "$D/saved/$f"; then cp -a -- "$D/saved/$f" "$G/$f";
        else rm -f -- "$G/$f"; fi
    done
    echo 'RESULT gui_files_restored'
}
trap 'restore; exit 2' ERR
for f in "${files[@]}"; do
    ref="$D/saved/$f"
    test -f "$ref" || ref="$D/saved/theme.py"
    install -o "$(stat -c %u "$ref")" -g "$(stat -c %g "$ref")" -m "$(stat -c %a "$ref")" "$N/$f" "$G/.xgw-gui-new"
    mv -f -- "$G/.xgw-gui-new" "$G/$f"
done
for f in "${files[@]}"; do cmp -s "$G/$f" "$N/$f"; done
trap - ERR
echo 'OK gui_files=5'
SH
```

Ожидается `OK syntax`, `OK gui_files=5`, rc0. При ошибке блок пытается вернуть файлы; записать фактический rc и результат возврата.
Это не установка всего CODE: остальные компоненты сохраняют прежние версии. Карта не загружает тайлы/геолокацию.

## 3. Проверить окно за один заход

Запустить `xgw gui` в графическом сеансе владельца, от обычного пользователя. Разрешён запуск средствами рабочего стола.
Входить штатно; пароли и коды в отчёт не копировать. Не нажимать «Выключить VPN», «Выбрать», замеры, обновления и переключатели.

1. Проверить обзор при 1024×720 и развёрнутом окне: светлая тема, карта фоном, состояние сверху, замеры снизу.
2. Нет наложения и обрезания кнопок; названия с многоточием доступны полностью в карточке. Прокрутка списка работает.
3. Нет дублирующей панели справа. Все семь разделов доступны значками с подсказкой и Ctrl+1…7.
4. Нажать имя и свободное место строки текущего, запасного и недоступного сервера: открываются соответствующие сведения.
5. Проверить полное имя, состояние, скорость/задержку, доступные протокол, ядро и профиль по данным панели, без новых сетевых проб.
6. Повторный клик по тому же серверу не плодит его окна. Escape и «Закрыть» работают; Tab → Enter/Space открывает карточку.
7. В «Серверах» проверить карточку подписки и, если список уже есть, бесплатного пула. Не включать пул ради проверки.
8. Навести на кнопки выбора/замера/меню: они остались отдельными действиями. В этой живой приёмке не нажимать их.
9. Открыть «Устройства», «Трафик», «Диагностику», «Ещё» и вернуться. Только просмотр, без сохранения или запуска проверок.
10. Оставить карточку открытой на два опроса: данные помечены как снимок, окно не исчезает и не теряет выбранный сервер.
11. Закрыть/открыть GUI один раз; нет второго опросника. Просмотр не сменил сервер, pin, пул или настройки.
12. Карта показывает приблизительную страну из подписки; совпадение с IP-геолокацией не заявлять.

Если пункта нечем проверить, указать NOT_RUN. Если окно не открывается/критично обрезано — закрыть его и вернуть файлы шагом 5.
При штатной смене серверов демоном не запрещать ему работать и не приписывать событие GUI без доказательств.

## 4. Финальная сверка и отчёт

```bash
sudo python3 -I "$H" after --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
# Другие модули GUI также остались прежними.
for source in "$B"/*.py; do
    f=${source##*/}
    case "$f" in pages.py|theme.py|widgets.py|window.py) continue;; esac
    sudo cmp -s "$source" "$G/$f"
done
```

Ожидается `OK gui_layout: capture_on=1 services_active=1 settings_same=1 files=5`, rc0, без новых FAIL.
`OBS processes_changed=N` — наблюдение. Если N>0, только чтением журнала выяснить причину; не перезапускать службы.
Штатное обновление состава не делает GUI автоматически FAIL. Если причину установить нельзя — PARTIAL и коротко владельцу.
PASS: установка и доступные пункты просмотра прошли, финальная сверка успешна. Непроверенные ветви перечислить отдельно.
PARTIAL: просмотр неполон/результат неоднозначен. FAIL: воспроизводимый дефект окна. STOP: ворота/установка не прошли.
Создать один `docs/TEST-REPORT-REAL-MACHINE-0.2.0-gui-layout-ДАТА.md`, до одной страницы:

```text
Дата; CODE; обнаруженный BASE GUI; согласие; SHA помощника:
Исходный on; службы; diag OK/WARN/FAIL; rc before/install/after:
Пункты 1–12: PASS/FAIL/NOT_RUN; первое расхождение:
Клик/Enter/Space; Escape; окно сведений; отсутствующие данные:
Итоговая сверка файлов/настроек; processes_changed и объяснение; diag после:
Откат (да/нет, rc); что оставлено на машине; итог PASS/PARTIAL/FAIL/STOP:
```

Публиковать только этот обезличенный отчёт в freepool по действующему поручению владельца, без force; не менять main.

## 5. Возврат только окна при неудачном запуске/просмотре

Закрыть GUI. Резервная копия из шага 2 обязательна. Службы и сеть не трогать.

```bash
sudo bash -s -- "$G" "$D/saved" <<'SH'
set -euo pipefail
G=$1 S=$2
for f in pages.py theme.py widgets.py window.py; do test -f "$S/$f"; done
for f in pages.py theme.py widgets.py window.py; do
    cp -a -- "$S/$f" "$G/$f"
    cmp -s "$S/$f" "$G/$f"
done
rm -f -- "$G/mapdata.py"
echo 'OK previous_gui_restored'
SH
```

Ожидается rc0 и `OK previous_gui_restored`. Открыть прежний GUI от пользователя, записать итог и STOP этой установки.
