# T01/T02. Дробление ClientHello на отдельном канале загрузки XHTTP

На машине по отчёту 98ba130 установлен 59353da (C05, первая часть). Новый код 87942c2266ffe49f87d7575b51c46f87fbbb01e9:

- T01: у XHTTP канал загрузки бывает отдельным (downloadSettings — свой адрес, TLS и sockopt).
  Раньше профиль дробления (fragment или fragment-split) ставился только на основной канал, и
  ClientHello канала загрузки уходил целым. Теперь профиль ложится и на канал загрузки, если тот
  идёт по TCP с TLS/REALITY, не мост к 127.0.0.1 и без чужой цепочки.
- T02: XHTTP считается QUIC только при TLS с alpn ровно ["h3"] — так выбирает Xray. Раньше
  ["h2","h3"] ошибочно считался UDP (дробление и прямая TCP-проверка ему не давались), а
  `splithttp` с ["h3"] — TCP.
- Журнал сканов C05 в панели и `xgw status` теперь в КБ/МБ, а не в байтах.

Критерии: установка и health rc0; по применённому конфигу ни одного канала загрузки, который
должен идти через профиль своего сервера и не идёт (`legs_mismatch` 0), у внешних каналов есть
метка шлюза; копия конфига со всеми XHTTP-каналами загрузки на профиле проходит `xray run -test`;
если на машине есть XHTTP с внешним каналом загрузки — загрузка через временный Xray с
дроблением даёт HTTP 2xx/3xx и ненулевое тело. Нет таких серверов — живая часть
NOT_APPLICABLE, это не дефект.

Разрешены терминал, браузер, зрение, чтение status/diag/logs. Пути, sudo и ожидание
адаптировать по месту. WAN, LAN, Tailscale, подписки, пул, pin, профили и настройки не менять.
Временный Xray помощника слушает только 127.0.0.1 и завершается сам. В отчёте — числа и
обезличенные признаки, без имён, тегов, адресов, доменов, конфигов и скриншотов.

## 1. Код, предыдущая копия и помощник

```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=87942c2266ffe49f87d7575b51c46f87fbbb01e9
BASE=59353daad93acc24fc757ea9cc595c51fa8bf5ac
TARGET="$HOME/xgw-t01-$CODE"
PREV="$HOME/xgw-c05-$BASE"
git worktree add --detach "$TARGET" "$CODE"
HELPER="$PWD/docs/helpers/xhttp_fragment_check.py"
printf '%s  %s\n' '3560e94fdf8f36de5c6ab4d49883db2137fd977a72f85f78d853204bdcf7619f' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$PREV" rev-parse HEAD
sudo python3 -I "$HELPER" health
```

Ожидаются чистый клон, сумма OK, точные CODE/BASE, {"health": true} и rc0. Если PREV нет —
`git worktree add --detach "$PREV" "$BASE"`. Существующие worktree не удалять. Сверить, что
установлен BASE (функция из ТЗ c05-scan-bytes):

```sh
match_package() {
  sudo sh -s -- "$1" <<'SH'
set -e
files=$(git -c safe.directory="$1" -C "$1" ls-files src/xgw packaging)
test -n "$files"
for file in $files; do
    case "$file" in src/*) to="/opt/xgw/lib/${file#src/}";; *) to="/opt/xgw/$file";; esac
    cmp -s "$1/$file" "$to"
done
printf '%s\n' 'Пакет совпадает'
SH
}
match_package "$PREV"
```

Установлена другая версия, нет рабочего on или сумма/код расходятся — только чтение и
сообщить владельцу. Приватно записать: on/HTTPS, режим пула, ручной выбор, итог
`sudo xgw diag --no-net` (только числа OK/WARN/FAIL).

## 2. До установки — подсчёт по рабочему конфигу

```sh
sudo python3 -I "$HELPER" count; printf 'count rc=%s\n' "$?"
```

Одна строка JSON с числами: `xhttp` — XHTTP-серверов в конфиге (участники и запасные),
`with_download_legs` — из них с отдельным каналом загрузки, `legs_fit` — каналов, которым
дробление подходит, `xhttp_on_profile` — XHTTP на профиле дробления, `legs_should` /
`legs_fragmented` / `legs_mismatch`, `xhttp_h3_exact`, `xhttp_h3_among_several`. На старом коде
rc 3 с `legs_mismatch` > 0 — это и есть дефект T01 (записать), rc0 — на машине нет XHTTP с
каналом загрузки на профиле дробления. Записать строку целиком.

## 3. Обычная установка с локальным возвратом

Нужно согласие владельца на обычную установку CODE, две небольшие загрузки (по 45–70 КБ)
через временный Xray помощника и условный возврат штатным установщиком BASE, если установка
или on/HTTPS откажут. Нет согласия — INSTALL_NOT_RUN, отчёт по шагам 1–2.

Одной командой в устойчивой локальной сессии ThinkCentre. При потере интернета следующая
команда модели для возврата не нужна:

```sh
sudo sh -s -- "$TARGET" "$PREV" "$HELPER" <<'SH'
umask 077
d=/run/xgw-t01
mkdir -m 700 "$d" || exit 3
sh "$1/packaging/install.sh" --yes >"$d/install.log" 2>&1
i=$?; echo "$i" >"$d/install.rc"
python3 -I "$3" health >"$d/health.json" 2>&1
h=$?; echo "$h" >"$d/health.rc"
if [ "$i" -ne 0 ] || [ "$h" -ne 0 ]; then
    sh "$2/packaging/install.sh" --yes >"$d/return.log" 2>&1
    echo "$?" >"$d/return.rc"
    python3 -I "$3" health >"$d/return-health.json" 2>&1
    echo "$?" >"$d/return-health.rc"
fi
printf '%s\n' 'Проверьте сохранённые rc'
SH
sudo cat /run/xgw-t01/install.rc /run/xgw-t01/health.rc
```

Ожидается 0 и 0. После потери связи — проверить сохранённые rc, установку заново не начинать.
При откате снять health и закончить с PARTIAL. Логи установки приватны.

## 4. После установки

```sh
match_package "$TARGET"
sudo python3 -I "$HELPER" health
sleep 60; sudo python3 -I "$HELPER" count; printf 'count rc=%s\n' "$?"
sudo python3 -I "$HELPER" xtest; printf 'xtest rc=%s\n' "$?"
sudo python3 -I "$HELPER" live; printf 'live rc=%s\n' "$?"
```

Ожидаются «Пакет совпадает» и {"health": true}. `count` — rc0, `legs_mismatch` 0,
`legs_external_without_mark` 0; `legs_fragmented` равно `legs_should`. Остальные числа как
в шаге 2 (состав мог штатно смениться — тогда отметить). `xtest` — rc0, `forced` — сколько
XHTTP с каналом загрузки было переведено на профиль в копии (0 — таких нет). `live`: при
`candidates` 0 — `NO_XHTTP_WITH_DOWNLOAD_LEG`, rc0 (NOT_APPLICABLE); иначе `legs_on_profile` ≥ 1,
у `fragment` http 2xx/3xx и `bytes` > 0. `plain` — та же загрузка без дробления, для сравнения:
её неудача при удачной `fragment` — наблюдение, не дефект. Неудача `fragment` при удачной
`plain` — дефект T01. Неудачны обе — сервер недоступен сейчас; `live` не повторять больше
одного раза.

Затем без команд: `sudo xgw diag --no-net` — числа OK/WARN/FAIL сравнить с шагом 1; в панели
на карточке «Трафик» строка журнала сканов показана в КБ или МБ. Режим пула, ручной выбор и
связь — как до установки.

## 5. Один отчёт, максимум страница

```text
Дата, CODE/BASE, сумма помощника, согласие, исходный и конечный on/HTTPS:
Установка / health / совпадение пакета / возврат rc либо NOT_RUN:
count до: <JSON>; count после: <JSON>; rc обоих:
xtest: forced, xray_test_rc; live: candidates, legs_on_profile, plain и fragment (http/bytes/seconds):
diag до/после (OK/WARN/FAIL); журнал сканов в панели — единицы:
Пул/pin/настройки/связь; что осталось непроверенным; PASS/PARTIAL/INSTALL_NOT_RUN:
```

Файл docs/TEST-REPORT-REAL-MACHINE-0.2.0-t01-xhttp-ДАТА.md. В freepool добавить, проверить
git diff --cached --name-only и --check, закоммитить и отправить только этот отчёт.
