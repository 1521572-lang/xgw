# G1: последний повтор, без повторной установки

Отчёты CPU и fix1 приняты: установка f82fbca исправна, on/HTTPS сохранены. CPU повторять
не нужно. Непрерывность G1 пока не доказана: помощник отверг заголовки HTTP 206 до тела,
rotate не выполнялся. Это повтор 2 из максимум 2, независимо от двух чтений готовности fix1.
Новая гипотеза: ответ выбранного измерительного адреса не соответствует запрошенному Range
либо прежний парсер его не распознал. Заголовков в отчёте нет, точная причина неизвестна.
Теперь помощник различает статус, диапазон, длину, кодирование и сохраняет только числа/enum.

Критерии прежние: две полные загрузки по 2 МиБ через один probe-inbound Xray, каждая ≥60 с,
без переподключения/докачивания; первая начата до rotate, вторая после. Видны старый/новый
TCP-мосты одновременно; rotate rc0; максимум два обслуживающих процесса, UID xgw-singbox,
CapEff=0 по /proc; старый процесс исчез после drain=300 с. Запись статуса ≤25 с, настройки,
пул и pin сохранены, кроме естественного истечения TTL. On/HTTPS исправны, новых FAIL diag нет.
DEGRADED/отдельные неработающие серверы допустимы. Критерии после прогона меняет владелец.
Смена поколений при прошлой установке и process_limit=2 не заменяют эти доказательства.

Разрешены любые инструменты: терминал, браузер, машинное зрение, API для чтения. Повторять
чтение, ждать дольше, адаптировать пути/кавычки/sudo можно, записав отклонения. Диагностика:
status/diag/logs, journalctl, nft list, ip rule/route; сырьё приватно. Не менять WAN/LAN/TS,
подписки, пул, pin, настройки; не выполнять off/uninstall, faults, ручные правила/подмену файлов.
STOP при угрозе on или выходе за разрешённые действия. В Git только один новый отчёт без
секретов, адресов/доменов, имён серверов/устройств/подписок, полных MAC, PID, argv и скриншотов.

## 1. Подготовить помощник, не устанавливая пакет
```sh
cd ~/xgw
git status --short
git switch freepool
git fetch origin
git merge --ff-only origin/freepool
RUNTIME=f82fbca998ca673d947f48d33c1bddfdc7912983
HELPER_CODE=7c00d5927884318ee4460f1b590113b9ae6e9d1e
PREVIOUS=50d51f76c80cd289df8db33ad4a42d3b98d2e222
TARGET="$HOME/xgw-g1-$RUNTIME"
CHECK="$HOME/xgw-g1-check-$HELPER_CODE"
ROLLBACK="$HOME/xgw-before-g1"
git worktree add --detach "$CHECK" "$HELPER_CODE"
HELPER="$CHECK/docs/helpers/singbox_generation_check.py"
printf '%s  %s\n' '1b8d310beb9909a2f3e34d3529465fbc34062a11e3d1836edbfeeb47dceeacdd' "$HELPER" | sha256sum -c -
git -C "$TARGET" rev-parse HEAD
git -C "$ROLLBACK" rev-parse HEAD
```
Ожидается чистый freepool, сумма OK, TARGET=RUNTIME, ROLLBACK=PREVIOUS. Уже существующие
worktree проверить по SHA, не удалять/reset. Если TARGET/ROLLBACK отсутствуют — создать
`git worktree add --detach "$TARGET" "$RUNTIME"` и аналогично ROLLBACK/PREVIOUS.
Код продукта и упаковка HELPER_CODE совпадают с RUNTIME, новый только помощник/тесты.
Старые /run/xgw-g1 и /run/xgw-g1-fix1 не трогать. Новый каталог — /run/xgw-g1-fix2.

## 2. Подтвердить установленную копию и готовность
```sh
sudo -v
sudo python3 "$HELPER" health
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
sudo sh -c 'umask 077; xgw status --json > /run/xgw-g1-fix2/before-status.json; xgw diag --json > /run/xgw-g1-fix2/before-diag.json; xgw pool > /run/xgw-g1-fix2/before-pool.txt; sha256sum /etc/xgw/config.toml > /run/xgw-g1-fix2/before-config.sha'
```
Ожидается health rc0 «Рабочий on и HTTPS подтверждены», совпадение rc0, pending=null,
draining=null. Если штатная смена идёт — читать, ждать ≥900 с и дольше по живой операции.
При uncertain/несовпадении пакета новый rotate не делать, разобрать чтением и записать PARTIAL.
Не переустанавливать f82fbca для совпадения. Старые WARN/FAIL записать, серверы не чинить.

## 3. Один связанный прогон и условный штатный возврат одной командой
Ранее разрешённый rotate ещё не выполнялся. Если прежнее согласие охватывает этот повтор
и возврат — использовать его. Иначе получить согласие на один rotate, загрузки через имеющиеся
адреса замера, а при потере on — stop демона, legacy и прежний штатный install.sh 50d51f7.
Без согласия только чтение, ROTATE_NOT_RUN. Новая установка G1 не требуется.

Помощник до rotate рассматривает speed.url_fallback → speed.url → speed.youtube_speed_url,
каждый не более одного раза; это уже настроенные адреса самого XGW, конфиг не меняется.
speed.cloudflare.com/не-HTTPS/пустые адреса пропускает; новые домены/произвольные URL не добавляет.
Запрашивает Range 2 МиБ с no-cache; полный 200 нужной длины или точный 206. Короткий диапазон,
сжатое тело, неверная длина не принимаются. Переход к следующему адресу только до rotate,
когда предыдущий поток уже завершился без прочитанных байтов. Начавшееся тело не перезапускает.
Выбранный адрес для второй загрузки тот же. На тело вводит backpressure около 192 с;
это не замер пропускной способности. Ранее полученные 0 Б не объявлять отказом VPN/ТСПУ.

Выполнить в устойчивом локальном терминале ThinkCentre, окно ≥30 минут. Возврат при плохом
on делает тот же уже работающий shell, следующая команда модели после обрыва не является rescue.
```sh
sudo sh -s -- "$HELPER" "$ROLLBACK" <<'SH'
umask 077
dir=/run/xgw-g1-fix2
python3 "$1" >"$dir/run-private.log" 2>&1
printf '%s\n' "$?" >"$dir/run.rc"
python3 "$1" health >"$dir/after-health.log" 2>&1
healthy=$?
printf '%s\n' "$healthy" >"$dir/after-health.rc"
if [ "$healthy" -ne 0 ]; then
    systemctl stop xgw.service >"$dir/rollback-private.log" 2>&1
    xgw singbox legacy --yes >>"$dir/rollback-private.log" 2>&1
    printf '%s\n' "$?" >"$dir/legacy-rollback.rc"
    sh "$2/packaging/install.sh" --yes >>"$dir/rollback-private.log" 2>&1
    printf '%s\n' "$?" >"$dir/rollback.rc"
    python3 "$1" health >"$dir/rollback-health.log" 2>&1
    printf '%s\n' "$?" >"$dir/rollback-health.rc"
fi
printf '%s\n' 'Прогон завершён: прочитайте сохранённые rc и report'
SH
```
Ожидается run.rc=0, after-health.rc=0, rollback.rc отсутствует. Не обрывать живую операцию
из-за таймаута инструмента. После потери связи сначала проверить терминал/rc/report/status,
дождаться идущей команды; start/rotate повторно не запускать. Отказ helper не запрещает чтение.
Существующий summary запрещает новый start, даже если rotate не начался. Не удалять его.
Если все адреса не подошли — PARTIAL с точными числовыми причинами; третьего повтора нет.
Ненулевой legacy не блокирует прежний установщик. При исправном on и неполной приёмке
сохранить f82fbca. Если возврат не восстановил on — STOP и сообщение владельцу, без новых правок.

## 4. Прочитать результат и независимые проверки
```sh
sudo python3 "$HELPER" report
sudo python3 "$HELPER" health
sudo xgw singbox status
sudo sh -c 'umask 077; xgw status --json > /run/xgw-g1-fix2/after-status.json; xgw diag --json > /run/xgw-g1-fix2/after-diag.json; xgw pool > /run/xgw-g1-fix2/after-pool.txt; sha256sum /etc/xgw/config.toml > /run/xgw-g1-fix2/after-config.sha'
```
Для PASS: rotate_rc=0, first/second ok=true, bytes=2097152 и seconds≥60 каждый;
old_endpoint/new_endpoint/overlap/old_retired/permissions/settings_unchanged/status_within_25=true,
max_processes=2; pin_unchanged=true либо доказанное естественное истечение TTL. CapEff/UID
помощник читает из /proc обоих работающих процессов; свойства unit не заменяют эту проверку.
Процесс считается ушедшим по MainPID=0/inactive/failed либо исчезновению unit, не process_limit.
Из attempts выписать source и http/error/length/range/identity; URL/сырые заголовки не публиковать.
Нулевые байты при RANGE_MISMATCH/LENGTH_MISMATCH означают отказ до чтения, не доказанный обрыв тела.
Если rotate не начался, исходный status_within_25=true не считать наблюдением интервалов: NOT_RUN.
Сравнить diag/настройки/пул/pin с исходными. Неизвестное оставить NOT_RUN/не проверено.

## 5. Один отчёт — максимум страница
```text
# Поколения sing-box — ДАТА, повтор 2 из 2
- Runtime f82fbca, helper 7c00d59 / SHA; source match rc ...; согласие ...; переустановка NOT_RUN.
- До/после: on/HTTPS/daemon/Xray ..., diag OK/WARN/FAIL ..., новые FAIL ...; связь ...
- Источники fallback/primary/youtube: http/error/length/range/identity ... (только числа/enum).
- run/health/rotate rc ...; первая ... Б / ... с / ok ...; вторая ... Б / ... с / ok ...
- Старый/новый мост ..., overlap ...; фактический max процессов ..., UID/CapEff ..., old_retired ...
- Интервал статуса ... с / within_25 ...; настройки/пул/pin ..., истечение TTL ...
- legacy/rollback/health после возврата rc ... либо NOT_RUN; итог PASS/PARTIAL/ROTATE_NOT_RUN.
- Неизвестное/отклонения ...; LAN/UDP/IPv6/faults и живой импорт нового состава NOT_RUN.
```
Создать `docs/TEST-REPORT-REAL-MACHINE-0.2.0-singbox-generations-fix2-ДАТА.md` в исходном freepool.
```sh
git add -- docs/TEST-REPORT-REAL-MACHINE-0.2.0-singbox-generations-fix2-ДАТА.md
git diff --cached --name-only
git diff --cached --check
git commit -m "Отчёт последнего повтора поколений sing-box"
git fetch origin
git rebase origin/freepool
git push origin HEAD:freepool
```
В staged только новый отчёт; конфликт не обходить изменением кода или прежних отчётов.
После PASS разработчик предложит main и перейдёт к C05/C06. После PARTIAL — короткий выбор
владельца: принять частично / изменить критерий / отложить. Новая диагностическая серия запрещена.
