# ThinkCentre. Причины отказов selective и срок видеоссылки

CODE `78cd0a45a8a4f385c3149b460493714036a507e3`, BASE `29201b155ef8817a53ef5b2831786506102aafb9`.
Исполнитель GLM-5.3-Flash. Основание — дополнение отчёта gui-zapret2. Версия 0.2.0.
Обновляются три файла. Порог 16 КиБ, сетевые запросы, стратегия и маршруты не меняются.
На машине по отчёту selective/fallback. Сначала получить согласие владельца штатно выключить
zapret2 кнопкой окна. Владелец нажимает её сам. Дождаться off, затем снимать baseline.
Не запускать сравнение, selective, замеры, обновления подписок и не менять остальные настройки.
Не менять WAN/LAN, Tailscale, pin, пул. Не трогать службы ядер. Приватные URL не копировать в отчёт.
Машинное зрение по живому окну не кликает. Сетевые отказы проверяются изолированными тестами.

## 1. Подготовка

Блоки выполнять в одной bash-сессии. Любой неожиданный ненулевой rc — STOP с отчётом.

```bash
set -euo pipefail
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=78cd0a45a8a4f385c3149b460493714036a507e3
BASE=29201b155ef8817a53ef5b2831786506102aafb9
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-probes.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/zapret2_probes_check.py"
printf '%s  %s\n' 1f543ba6c78f273267b9009b5cbb4bbf9d8f22b01c7ed3ac7f8f0a0cf4db0add "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json" --base "$D/base"
sudo xgw diag --no-net >"$D/diag-before"
(cd "$D/new" && PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m pytest \
 -p no:cacheprovider -o addopts= -q tests/test_zapret2.py tests/test_zapret2_panel.py \
 tests/test_gui_qt.py -k zapret2)
```

Нужны `OK baseline`, capture on, zapret2 off, активные демон и Xray, 50 passed, 0 skipped.
sing-box может быть inactive. Его состояние сохраняется. Нет Qt — NOT_RUN tools, не ставить пакеты.
Сверить diag приватно, записать только количества. Новый FAIL или другая база файлов — STOP.
Тесты проверяют 204, малое тело, редирект, HTTP-ошибку, таймаут, CONNECT, ранний отказ,
обновление результатов после успеха, expire, отсутствие секретов в API и отображение Qt.

## 2. Установка

Получить согласие владельца закрыть окно и кратко перезапустить только демон XGW.
Владелец закрывает GUI. Выполнить фиксированный блок, без дополнительных перезапусков.

```bash
sudo bash -s -- "$D" <<'SH'
set -euo pipefail
D=$1
G=/opt/xgw/lib/xgw
N="$D/new/src/xgw"
files=(zapret2.py watch/zapret2_control.py gui/zapret2.py)
for dir in "$G" "$G/watch" "$G/gui"; do test -d "$dir"; test ! -L "$dir"; done
mkdir -p "$D/saved/watch" "$D/saved/gui"
for f in "${files[@]}"; do
    test ! -L "$G/$f"
    cmp -s "$G/$f" "$D/base/src/xgw/$f"
    cp -a -- "$G/$f" "$D/saved/$f"
done
python3 - "$N" "${files[@]}" <<'PY'
import ast, pathlib, sys
for name in sys.argv[2:]:
    ast.parse((pathlib.Path(sys.argv[1]) / name).read_text(encoding='utf-8'))
print('OK syntax')
PY
rollback() {
    trap - ERR
    set +e
    systemctl stop xgw.service
    for f in "${files[@]}"; do cp -a -- "$D/saved/$f" "$G/$f"; done
    systemctl start xgw.service
    echo 'STOP install_rollback_attempted'
    exit 2
}
trap rollback ERR
systemctl stop xgw.service
for f in "${files[@]}"; do
    ref="$D/saved/$f"
    install -o "$(stat -c %u "$ref")" -g "$(stat -c %g "$ref")" -m "$(stat -c %a "$ref")" "$N/$f" "$G/$f"
done
for f in "${files[@]}"; do cmp -s "$G/$f" "$N/$f"; done
systemctl start xgw.service
trap - ERR
echo 'OK installed files=3'
SH
```

Дождаться свежего статуса до 90 секунд. При ошибке возврат разделом 4, без подбора команд.

## 3. Просмотр и результат

Запустить `xgw gui` от пользователя в графическом сеансе. Владелец проверяет при 1024×720.

1. В разделе zapret2 виден off и блок «Последние проверки».
2. В настройках показаны минимум 16 КиБ, требование HTTP 2xx и отсутствие переходов selective.
3. Для каждого сохранённого адреса виден срок expire UTC либо «срок по адресу неизвестен».
4. Для истёкшей даты виден текст «срок expire истёк». Если такой ссылки нет, пункт NOT_RUN.
5. Открыть «Настроить», проверить подсказки и скрытые поля, закрыть «Отмена».
6. Просмотр не меняет настройки и не запускает пробы. Живые ошибки в этом прогоне NOT_RUN.

```bash
sudo python3 -I "$H" after --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны `RESULT zapret2_probes_ok`, прежние настройки от baseline, capture on, zapret2 off,
прежние ядра и отсутствие новых FAIL. Рестарт демона ожидаем. Смена PID ядра — STOP,
причину выяснить приватно, не приписывать обновлению без доказательств. Успешный код оставить.

## 4. Возврат при ошибке

После закрытия окна владельцем выполнить блок. Настройки от baseline не менялись.

```bash
sudo bash -s -- "$D" <<'SH'
set -euo pipefail
D=$1
G=/opt/xgw/lib/xgw
systemctl stop xgw.service
for f in zapret2.py watch/zapret2_control.py gui/zapret2.py; do
    cp -a -- "$D/saved/$f" "$G/$f"
done
systemctl start xgw.service
SH
sudo xgw diag --no-net >"$D/diag-rollback"
```

Сверить прежние файлы, capture on, off, здоровье шлюза и ядра. Не включать selective автоматически.
При проблеме возврата остановиться и сообщить владельцу. Приватные копии сохранить до приёмки.

## 5. Отчёт

Одна страница `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-probes-ДАТА.md`, включая STOP/NOT_RUN.
CODE, BASE, SHA, согласия, 50 тестов, установка 3/3, пункты просмотра, helper, diag до/после,
смена PID по ролям без самих PID, конечный режим и возврат при необходимости.
Без URL, доменов, подписей, имён серверов, снимков реального окна и сырых журналов.
