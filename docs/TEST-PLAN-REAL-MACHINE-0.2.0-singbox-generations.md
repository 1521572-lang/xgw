# PR-G1: поколения sing-box без обрыва текущей загрузки

До запуска фиксируются критерии: обычная установка rc0, рабочий on/HTTPS, полный установленный
пакет совпадает с 77067b49d9aa52a34d3622f8cd833694c769e44b. Две загрузки по 2 МиБ через один probe-inbound Xray завершены
без повтора соединения, каждая не короче 60 с; первая начата до переключения, вторая после.
Во время второй видны установленные TCP-соединения к старому и новому мостам; CLI rotate rc0.
Одновременно максимум два обслуживающих процесса sing-box, оба от xgw-singbox с CapEff=0;
счёт по службам поколений, краткий sing-box check отдельно. После drain=300 с
старый процесс исчез. Настройки/пул/ручной выбор сохранены, кроме естественного истечения TTL.
Запись status.json остаётся не реже раза в 25 с; возраст проверок справочный. Новых FAIL diag нет.
DEGRADED и отдельные плохие серверы допустимы; нужен хотя бы один рабочий маршрут через sing-box.
Критерии после прогона меняет только владелец. На пункт один прогон и максимум два повтора
с новой конкретной гипотезой и изменённым кодом/помощником; затем решение владельца.

Разрешены все инструменты: терминал, панель, браузер, машинное зрение, API для чтения.
Можно повторять чтение, ждать дольше, адаптировать пути/кавычки/sudo, записав отклонения.
Для диагностики читать status/diag/logs, journalctl, nft list, ip rule/route; сырьё приватно.
Не менять вручную WAN/LAN/Tailscale, подписки, пул, pin, настройки; не выполнять off/uninstall,
--force и сетевые faults. STOP только при угрозе рабочему on или выходе за согласованные действия.
Публиковать только новый отчёт: без секретов, внешних адресов/доменов, имён, полных MAC и PID.

## 1. Подготовить источники и единственный помощник — без установки
```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
CODE=77067b49d9aa52a34d3622f8cd833694c769e44b
PREVIOUS=50d51f76c80cd289df8db33ad4a42d3b98d2e222
TARGET="$HOME/xgw-g1-$CODE"
ROLLBACK="$HOME/xgw-before-g1"
git worktree add --detach "$TARGET" "$CODE"
git worktree add --detach "$ROLLBACK" "$PREVIOUS"
HELPER="$TARGET/docs/helpers/singbox_generation_check.py"
printf '%s  %s\n' '1c8d0ec0ff708c89ba9c2118caa187d8a149642ce7a9ee3268e8929a1e74eedc' "$HELPER" | sha256sum -c -
```
Ожидается чистый freepool, точные SHA worktree, сумма OK. Существующие worktree проверить
`git -C "$TARGET" rev-parse HEAD` и аналогично ROLLBACK; не удалять и не reset чужую работу.
Пути можно адаптировать. Версия 0.2.0, main не менять. Предыдущая база по рабочему коду
совпадает с установленной и принятой main 57756aa; повторять прежнее ТЗ align-main не нужно.

## 2. Исходное состояние и согласие
```sh
sudo -v
sudo python3 "$HELPER" health
sudo sh -c 'umask 077; xgw status --json > /run/xgw-g1/before-status.json; xgw diag --json > /run/xgw-g1/before-diag.json; xgw pool > /run/xgw-g1/before-pool.txt; sha256sum /etc/xgw/config.toml > /run/xgw-g1/before-config.sha'
```
Ожидается «Рабочий on и HTTPS подтверждены», rc0. Разобрать приватно исходные WARN/FAIL,
пул и pin. Если проверка отказала — читать независимые данные, уточнить доступность HTTPS;
до подтверждённого рабочего on установку не начинать. Не чинить отдельные плохие серверы.
Спросить владельца: «Разрешаете обычную установку 77067b49d9aa52a34d3622f8cd833694c769e44b, процессы поколений
xgw-singbox-blue/green, один singbox rotate и проверки загрузками (обычно менее 8 МиБ сверх
фонового трафика), а при сбое — остановку демона, singbox legacy и штатную установку 50d51f7?»
Объяснить: install.sh переприменяет прежний LAN и правила, сохраняет WAN, перезапускает демон
и при необходимости ядра; новый ExecCondition старого unit тоже требует установки.
Возврат legacy прерывает соединения sing-box; при неизвестном API перезапускает Xray.
Без согласия только чтение, INSTALL_NOT_RUN. Старое согласие на main не является согласием здесь.

## 3. Обычная установка и заранее записанный условный возврат
Одна локальная команда ThinkCentre: терминал или устойчивая сессия, не менее 30 минут,
при работе ждать дольше. При потере связи возврат выполняет уже запущенный shell.
```sh
sudo sh -s -- "$TARGET" "$ROLLBACK" "$HELPER" <<'SH'
umask 077
dir=/run/xgw-g1
sh "$1/packaging/install.sh" --yes >"$dir/install-private.log" 2>&1
installed=$?
printf '%s\n' "$installed" >"$dir/install.rc"
python3 "$3" health >"$dir/after-install-health.log" 2>&1
healthy=$?
printf '%s\n' "$healthy" >"$dir/after-install-health.rc"
if [ "$installed" -ne 0 ] || [ "$healthy" -ne 0 ]; then
    systemctl stop xgw.service >>"$dir/rollback-private.log" 2>&1
    restored=0
    if PYTHONPATH=/opt/xgw/lib python3 -c 'import xgw.apply.singbox_generation'; then
        restored=1
        for attempt in $(seq 1 60); do
            if xgw singbox legacy --yes >>"$dir/rollback-private.log" 2>&1; then restored=0; break; fi
            sleep 2
        done
    fi
    if [ "$restored" -eq 0 ]; then
        sh "$2/packaging/install.sh" --yes >>"$dir/rollback-private.log" 2>&1
        printf '%s\n' "$?" >"$dir/rollback.rc"
    else printf '%s\n' 3 >"$dir/rollback.rc"; fi
    python3 "$3" health >"$dir/rollback-health.log" 2>&1
    printf '%s\n' "$?" >"$dir/rollback-health.rc"
fi
printf '%s\n' 'Установка завершена: прочитайте сохранённые rc и health'
SH
```
Ожидается install.rc=0, after-install-health.rc=0, rollback.rc отсутствует. Если связь пропала,
после возврата сначала проверить терминал и rc, дождаться идущей команды; не устанавливать заново.
Продолжить шаг 4. Установочные логи содержат токен панели, их нельзя публиковать.
Возврат на 50d51f7 — частичный результат G1, даже при исправном on; тест не запускать.
Если возврат не восстановил on — не делать новых изменений, сообщить владельцу и разобрать логи.

## 4. Проверить установленную копию и дождаться готовности
```sh
sudo sh -s -- "$TARGET" <<'SH'
set -e
files=$(git -c safe.directory="$1" -C "$1" ls-files src/xgw packaging)
test -n "$files"
for file in $files; do
    case "$file" in src/*) to="/opt/xgw/lib/${file#src/}";; *) to="/opt/xgw/$file";; esac
    cmp -s "$1/$file" "$to"
done
cmp -s "$1/packaging/xgw-singbox.service" /etc/systemd/system/xgw-singbox.service
printf '%s\n' 'Пакет и упаковка совпадают'
SH
sudo xgw singbox status
```
Ожидается строка совпадения; pending=null, draining=null. Если установка уже сменила состав,
может идти подготовка или drain: это не причина повторять установку. Читать status, ждать
не менее 900 с и дольше по факту работы; переходить к шагу 5 только после завершения.
При uncertain читать приватный журнал и состояние API; не запускать новую смену вслепую.
Несовпадение копии — сообщить разработчику; файлы вручную не заменять.

## 5. Один связанный прогон
```sh
sudo python3 "$HELPER"
```
Дать не менее 15 минут и больше при живой операции. Помощник сам выбирает рабочий sing-box
через его probe-inbound Xray, начинает загрузку, вызывает обычный `xgw singbox rotate`, затем
начинает вторую загрузку через тот же inbound. Замедляет чтение, ограничивает TCP-окно,
проверяет старый/новый TCP-мост и ждёт исчезновения старого процесса после drain.
Пул и pin не переключает. Проверочный адрес взят из настроенного speed.url; в запросе меняется
только bytes на 2097152, настройки не записываются. Нужны HTTPS и параметр bytes.
Ожидается rc0: rotate_rc=0, обе загрузки ok, old_endpoint/new_endpoint/overlap=true,
old_retired=true, max_processes=2, permissions=true, settings_unchanged=true,
status_within_25=true. pin_unchanged=true либо отдельно подтверждено истечение прежнего TTL.
При rc3 сначала report и независимые status/diag/logs, сохранить факты и продолжить шаг 6.
Предварительный отказ до rotate не занимает каталог навсегда: после исправления окружения
повтор чтения готовности допустим, прошлый результат сохранится. После стадии rotate новый
прогон только с новой гипотезой/правкой разработчика. Не удалять summary ради повторного start.
При разрыве связи прочитать report и `xgw singbox status`, проверить живые процессы/CLI,
дождаться идущей операции. Незаконченный поток не объявлять успешной загрузкой.

## 6. Конечные проверки; возврат при необходимости
```sh
sudo python3 "$HELPER" report
sudo python3 "$HELPER" health
sudo sh -c 'umask 077; xgw status --json > /run/xgw-g1/after-status.json; xgw diag --json > /run/xgw-g1/after-diag.json; xgw pool > /run/xgw-g1/after-pool.txt; sha256sum /etc/xgw/config.toml > /run/xgw-g1/after-config.sha'
```
Сравнить настройки/пул/pin и diag с исходными приватно; отличие checksum разобрать по эффективным
настройкам, не исправлять вручную. Проверить on/HTTPS, CapEff/UID, отсутствие третьего процесса.
Если G1 нарушил on и есть данное в шаге 2 согласие на возврат — повторить ТОЛЬКО ветвь возврата
из шага 3, без новой установки G1: stop xgw.service → singbox legacy --yes → PREVIOUS/install.sh.
Это дополнительный штатный CLI-шаг: прежний код не умеет завершать transient поколения.
Никакой подмены файлов, новых rescue-процессов или ручных сетевых правил. При исправном on
и неполной приёмке сохранить установленное состояние и PARTIAL, не откатывать ради цифры.

## 7. Один отчёт — максимум страница, включая partial/failure
```text
# Поколения sing-box — ДАТА
- Код 77067b49d9aa52a34d3622f8cd833694c769e44b, helper SHA; согласие владельца: ...; установка/health rc ...; source match ...
- До/после: on, HTTPS, daemon, Xray ...; состояние ...; diag OK/WARN/FAIL ..., новые замечания ...
- rotate rc ...; первая загрузка ... Б / ... с / ok ...; вторая ... Б / ... с / ok ...
- Старый/новый TCP-мосты ..., одновременное присутствие ...; старый процесс после drain ...
- Максимум обслуживающих процессов ...; UID/capabilities ...; статус: интервал ... с, within_25 ...
- Настройки/пул/pin ...; исходный TTL истёк: да/нет/не проверено; откат NOT_RUN/rc ...
- Отклонения, связь, неизвестное ...; итог PASS/PARTIAL/INSTALL_NOT_RUN.
- Живой импорт нового состава подписки, LAN/UDP/IPv6 и faults NOT_RUN. Новый состав покрыт кодом/узкими тестами.
```
Не копировать сырьё/скриншоты/PID/адреса/имена/хеши приватных настроек в Git.
Создать `docs/TEST-REPORT-REAL-MACHINE-0.2.0-singbox-generations-ДАТА.md` в исходном freepool.
```sh
git add -- docs/TEST-REPORT-REAL-MACHINE-0.2.0-singbox-generations-ДАТА.md
git diff --cached --name-only
git diff --cached --check
git commit -m "Отчёт поколений sing-box на шлюзе"
git fetch origin
git rebase origin/freepool
git push origin HEAD:freepool
```
В staged только новый отчёт. Конфликт — не переписывать код/старые отчёты ради push, сообщить.
После приёмки разработчик предложит main. C05/C06, XHTTP/UDP и DAE этим заданием не закрываются.
