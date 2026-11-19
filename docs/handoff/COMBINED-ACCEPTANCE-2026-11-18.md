# Одна расширенная приёмка открытых блоков XGW

**История. Продолжение после принятого слоя 3630b44 —
[единое ТЗ бюджета/матрицы/измеренного видео](COMBINED-ADMISSION-2026-11-19.md).**
Не устанавливать код этого архивного задания поверх нового. Запущенный по нему
суточный монитор завершается и учитывается по §1 нового ТЗ.

Редакция от **19 ноября** после [отчёта BLOCKED_TEST](../reports/2026-11-18_combined-open-blocks.md).
Исправлен вход в Flowseal через обычные настройки. Установка прошлого пакета
не выполнялась: продолжать нужно с §1 этого документа на новом SHA, а не
с CLI старого пакета. Это то же единое задание; сетевые фазы и суточная часть
сохранены, отдельной короткой приёмки только хотфикса нет.

Машина: ThinkCentre, **Ubuntu 24.04 LTS, amd64**. WAN IPv6 отсутствует по
подтверждению владельца: живая IPv6-фаза **NOT_APPLICABLE_ON_THIS_HOST**.
Не настраивать IPv6-туннель и не ждать провайдера ради этой приёмки.
Структурные тесты IPv6 и защита маршрутов остаются.

**Код: 3630b44502b872ca3788e0824c6a9d0d8363b561.** База установленного слоя:
3d117b1cc9cdd9e7b0184892a36604cd4ebec316 (принятый код бюджета 553de56,
код 2b78617 на машине не устанавливался). Действующее задание заменяет разрозненные
повторы бюджета/CDN/UI. Сначала прочитай [последний отчёт](../reports/2026-11-18_combined-open-blocks.md)
и [общий план](DESYNC-ROADMAP.md).

Цель — за одну приёмку проверить пакет T07–T12, а также собрать недостающие
данные M3. Активная часть ориентировочно 3–4 часа, затем одно суточное наблюдение.
Таймеры и сборщики ограничены. При раннем отказе CDN продолжай независимые
UI/API/отмена/восстановление/Standalone/VPN-проверки; не заканчивай весь проход
после первого TLS-таймаута. Одну и ту же неудачную строку не повторять бесконечно.

## Роль исполнителя и границы вывода

Ты, Flash, **сама** запускаешь команды, устанавливаешь код, открываешь Chrome,
смотришь интерфейс через vision, собираешь данные, выполняешь возврат и
автоматически публикуешь один отчёт. При отсутствии терминала, sudo или GUI
сама запроси доступ. Не передавай запуск владельцу. Не пиши и не исправляй код,
тесты, Lua, установщик или системные конфиги по собственной догадке. При дефекте
выполни опубликованный возврат и запиши воспроизводимые шаги.

Все команды и помощники уже написаны Codex. Выполнение опубликованных блоков
не является поручением разрабатывать код. Вводить параметры, пользоваться
штатными настройками и писать обезличенный отчёт разрешено.

Три независимых результата:
1. Исправность кода и управления.
2. Прохождение HTTPS к странице и CDN.
3. Настоящее воспроизведение с доказательством маршрута и качества.

Нельзя объявлять пункт 3 по пункту 2. Успех /generate_204 не доказывает работу
/videoplayback, SABR или другого IP. Сохранение профиля задания — явное изменение
настройки, а не автоматический перенос кэша между IP. Полученные эффекты
относятся к этой линии, времени и клиенту.

## 1. Подготовка и одно окно работы

Работай в Bash от пользователя рабочего стола, не от root. В исходном checkout
должны отсутствовать чужие правки. Сохрани приватно исходный VPN-выход контрольного
сайта вне YouTube, обычный сайт и новый сеанс YouTube через VPN. Не публикуй адреса,
cookie, подписки, полные конфиги, CDN URL и сырые записи.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
printf '%s\n' "$PRETTY_NAME"
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=3630b44502b872ca3788e0824c6a9d0d8363b561
OLD=3d117b1cc9cdd9e7b0184892a36604cd4ebec316
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git cat-file -e "$GUI_BASE^{commit}" || git fetch origin "$GUI_BASE"
D=$(mktemp -d "$HOME/xgw-combined.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
TELEMETRY_PY=${XGW_TELEMETRY_PYTHON:-$TEST_PY}
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo -v
df -h "$D" /var/lib/xgw
systemctl show xgw.service xgw-xray.service xgw-zapret2.service xgw-nfqws2.service \
  -p ActiveState -p MainPID
```

Проверь фактические ExecStart, launcher и Python демона. Если штатный Python
другой, присвой PY точный установленный путь. Не устанавливай зависимости в venv
демона. Недостающий инструмент ставь штатно в существующее dev-окружение после
проверки доступных путей; отсутствие доступа фиксируй как блокер среды.

Исходно обязательны mode=off, engine=off, рабочие VPN и панель, неактивные оба
nfqws2-юнита. Сними права/хэши config.toml и panel.json, acct, offload, nft,
очередь и конфигурацию Xray приватно. Если воркер уже обрабатывает рабочий трафик,
не выключай его вслепую — запроси окно доступа.

Старый T05 tcpdump: только проверка PID/дескриптора, занятого места и фактического
роста. Удалённый открытый файл способен продолжать занимать диск. Не считать
unlink решением и не повторять прежние неограниченные захваты. Для этого ТЗ
новый WAN pcap не требуется: CDP, журналы и счётчики достаточны.

## 2. Максимальный целевой набор на настоящем Ubuntu

Сначала короткий обязательный набор: любой FAIL/ERROR блокирует установку.
Здесь есть проверки обеих веток наличия ассетов, поэтому отсутствие Flowseal
на машине не скрывает дефект ручного выбора. Старый patch4 должен пройти.
Сохрани вывод и JUnit приватно в D. Исправлять тесты/код самой запрещено.

```bash
"$TEST_PY" -m pytest -o addopts='' -q \
  tests/test_desync_jobs.py tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_zapret2_management.py tests/test_zapret2_management_linux.py \
  tests/test_desync_schema.py tests/test_acceptance_gate.py \
  --junitxml="$D/core.xml" >"$D/core-tests.log" 2>&1
"$TEST_PY" -m pytest -o addopts='' -q tests/test_panel.py -k zapret2 >"$D/api-tests.log" 2>&1
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
```

Затем один расширенный набор. В прошлом отчёте 14 отказов воспроизведены на OLD;
без полных ошибок нельзя считать доказанным, что все вызваны только версией nft.
Их не исключают по имени файла и не помечают PASS. Если они повторятся, помощник
сопоставит каждый testcase, тип failure/error и **полное сообщение assertion** с
OLD; нормализуется только путь checkout. Временные файлы pytest размещаются
в одинаковом подкаталоге двух новых изолированных worktree, чтобы разный номер
системного pytest-tmp не создавал искусственное отличие. Новая/другая ошибка, новая skipped-строка,
исчезновение/добавление testcase либо неполный JUnit блокируют установку.

Расширенный список одинаков для NEW и OLD. Новые тесты управления и заданий
в него не включены: они уже прошли обязательный набор и не могут быть оправданы
отказом старой версии. При полном PASS расширенного NEW старую версию не гонять.

```bash
BROAD=(tests/test_desync_worker.py tests/test_desync_standalone.py
       tests/test_desync_cache.py tests/test_desync_shadow.py tests/test_desync_event_socket.py
       tests/test_desync_tournament.py tests/test_desync_flowseal.py tests/test_desync_route_evidence.py
       tests/test_selective_probe_watch.py tests/test_youtube_telemetry.py
       tests/test_nfqws2.py tests/test_nft.py tests/test_applier.py tests/test_generator.py
       tests/test_freepool.py tests/test_freepool_backend.py tests/test_freepool_stats.py
       tests/test_freepool_traffic.py)
run_broad() {
  local tree=$1 report=$2 log=$3
  (
    cd "$tree" || exit 2
    env PYTHONPATH="$tree/src:$tree" "$TEST_PY" -m pytest -o addopts='' -q \
      "${BROAD[@]}" --basetemp="$tree/.acceptance-pytest-tmp" --junitxml="$report"
  ) >"$log" 2>&1
}
if run_broad "$D/source" "$D/broad-new.xml" "$D/broad-new.log"; then
  BROAD_RESULT=PASS
else
  NEW_RC=$?
  test "$NEW_RC" -eq 1
  git worktree add --detach "$D/baseline" "$OLD"
  if run_broad "$D/baseline" "$D/broad-old.xml" "$D/broad-old.log"; then
    OLD_RC=0
  else
    OLD_RC=$?
  fi
  test "$OLD_RC" -le 1
  "$PY" docs/helpers/acceptance_test_gate.py \
    --current "$D/broad-new.xml" --baseline "$D/broad-old.xml" \
    --current-source "$D/source" --baseline-source "$D/baseline" \
    >"$D/baseline-comparison.json"
  BROAD_RESULT=BASELINE_MATCH
fi
```

BASELINE_MATCH разрешает продолжить установку при PASS обязательного набора.
Это означает «старые отказы с теми же сообщениями», а не принятие этих тестов.
Запиши их количество/идентификаторы и остальной результат. Если сообщения
различаются только неизвестными помощнику временными данными, не расширяй
нормализацию и не обходи его код выхода: сохрани обе ошибки для Codex, установка
BLOCKED_TEST. После тестового блокера выполнить независимые Qt/синтаксис и
опубликовать отчёт; сетевые фазы без установки не запускать.


Для проверки Qt составь копию **реально установленного** GUI с принятыми накладками:

```bash
GUI="/opt/xgw/gui/releases/$GUI_BASE"
GUI_FILE=src/xgw/gui/zapret2.py
mkdir -p "$D/gui/src" "$D/gui/vpn_ui" "$D/gui/tests/fixtures/gui"
cp -R "$GUI/vpn_ui/." "$D/gui/vpn_ui/"
cp -R "$GUI/src/." "$D/gui/src/"
cp "$GUI_FILE" "$D/gui/$GUI_FILE"
cp tests/test_vpn_ui_sidebar.py "$D/gui/tests/"
git show "$GUI_BASE:tests/test_vpn_ui_xgw.py" >"$D/gui/tests/test_vpn_ui_xgw.py"
git show "$GUI_BASE:tests/fixtures/gui/state-work.json" >"$D/gui/tests/fixtures/gui/state-work.json"
(
  cd "$D/gui"
  QT_QPA_PLATFORM=offscreen PYTHONPATH="$D/gui:$D/gui/src" "$TEST_PY" \
    -m pytest -o addopts='' -q tests/test_vpn_ui_sidebar.py tests/test_vpn_ui_xgw.py
) >"$D/qt-tests.log" 2>&1
```

Отдельно укажи результаты recovery before/after commit, cancel, conflict,
матрицы 18 попыток, pin/reset, сохранения посторонних полей, удаления подписи и
ограничений импорта; это фикстуры, не сетевой эффект. Старый тест UTC-границы
также остаётся фикстурой. В локальной Windows-проверке исправления Codex были
74 PASS управления/карточки/заданий и 5 PASS сравнения JUnit. Qt 11 PASS подтверждён
предыдущим отчётом, а выше повторяется на новой копии GUI.
Linux/flock/API/маршруты принимаются здесь.

## 3. Доставка 7 файлов службы и 1 файла GUI

Установщик сверяет каждый прежний файл с OLD. Новые jobs.py/client.py должны
отсутствовать в старой установке. Если база не совпала, останови установку,
запиши путь и исходный коммит отличающегося файла; не подменяй baseline текущими
байтами, не делай принудительный apply. Проверь также совпадение неизменённых
zapret2.py, desync/flowseal.py и watch/zapret2_control.py с OLD.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PAYLOAD="/opt/xgw/handoff/combined-$CODE"
BACKUP="/var/lib/xgw/handoff/combined-$CODE"
UNIT=xgw-selective-jobs-rollback
OVERLAY=--selective-jobs
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
CORE=(src/xgw/desync/schema.py src/xgw/desync/jobs.py src/xgw/desync/client.py
      src/xgw/watch/panel.py src/xgw/watch/zapret2_management.py
      src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js)
PREVIOUS=(src/xgw/desync/schema.py src/xgw/watch/panel.py
          src/xgw/watch/zapret2_management.py src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js)
sudo cmp src/xgw/zapret2.py "$PACKAGE/zapret2.py"
sudo cmp src/xgw/desync/flowseal.py "$PACKAGE/desync/flowseal.py"
sudo cmp src/xgw/watch/zapret2_control.py "$PACKAGE/watch/zapret2_control.py"
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base"
git archive "$OLD" "${PREVIOUS[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$OLD" "$GUI_FILE" | sudo tar --no-same-owner -x -C "$PAYLOAD/gui_base"
git archive "$CODE" "${CORE[@]}" "$GUI_FILE" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" --package "$PACKAGE" \
  --gui "$GUI" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$PANEL" "$UNIT" "$OVERLAY" "$HELPER" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=240m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
```

Закрой настольное окно штатно. Затем:

```bash
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
check_installed() {
  for file in "${CORE[@]}"; do sudo cmp "$file" "$PACKAGE/${file#src/xgw/}"; done
  sudo cmp "$GUI_FILE" "$GUI/$GUI_FILE"
}
check_installed
systemctl is-active xgw.service
sudo touch "$BACKUP/network-test-started"
```

Ожидается 8/8 совпадений. Снова открой xgw gui штатным launcher от пользователя
рабочего стола. Войди в панель штатным способом. Новый локальный CLI использует
тот же сохранённый сеанс и **не запускается через sudo**:

```bash
"$PY" -m xgw.desync.client status >"$D/status-initial.json"
```

При ошибке авторизации сама открой вход XGW, повтори только status. Не печатай
файл ~/.config/xgw/gui.json и cookie.

## 4. Оба интерфейса, безопасность API, каталог и карта

| ID | Действие исполнителя | PASS |
|---|---|---|
| UI01 | /zapret2 в двух окнах, светлая/тёмная тема, 390 px; desktop страница zapret2 | Есть CDN-проба без подписи, Flowseal, задание, отмена, результат; кнопки не вылезают за экран, клавиатура и подтверждения работают |
| UI02 | Сверь /api/state, /api/zapret2/overview, веб и desktop | Одинаковые mode/профиль/config_key, бюджет/UTC, job.id/state/results; устаревшее состояние не названо успехом |
| UI03 | Отредактируй настройки A; в B сохрани retry=120 или 180; затем сохрани A | A получает conflict, не перезаписывает B. Пустые URL сохраняют прежние; очистка действительно удаляет их |
| UI04 | Скрыть веб на 30 с, вернуть; свернуть/вернуть desktop; Offline → Online | Форма не теряется, периодический веб-опрос скрытой вкладки остановлен, после возврата свежие данные, POST сам не повторяется |
| UI05 | В подписке и пуле сортируй «Серверы → Мбит/с → рейтинг», скролл и hover | Ширина/вид строк стабильны, имя и реальная страна по IP видны; карточка справа; сортировка и выделение не сбрасываются после обновления |
| UI06 | Сравни карту до/после **реального** выбранного VPN-сервера и в Standalone | Анимация зависит от применённого активного сервера и GeoIP, hover её не переключает; без VPN нет ложного VPN-маркера; hide/show возобновляет анимацию |
| UI07 | Выполни новые API-тесты из §2, проверь журналы ошибок UI | 401 без сеанса, 403 без origin/header, неправильное тело не меняет политику; нет signed URL, cookie и полного IP в публичном результате |
| UI08 | Настройка ALT9 при Selective / задание при engine=auto, повторный запуск задания | Не происходит обхода ограничений; выводится отказ, текущая политика сохранена. Для engine=auto используй только уже опубликованный тест-фиксچر; живую конфигурацию ради этого не изменяй |

GUI05/06 — регрессия уже принятого кода, не новый редизайн. Если GeoIP недоступен,
покажи неизвестную страну; название из подписки не доказательство географии.

## 5. Задание: отмена, перезапуск, конфликт и возврат

Подготовь через штатную форму **off/off**, 6 доменов YouTube, HTTPS-проверку,
страницу https://www.youtube.com/t/terms и свежий приватный CDN /videoplayback из
DevTools обычного Chrome. Установи check=180, retry=120, budget=512 МиБ на опыт.
Не отключай проверки сертификата или маршрута, не выставляй active вручную.
Из текущего отчёта CDN TLS часто не проходит — это допустимый сетевой исход.

Для следующих строк достаточно одного кандидата. Запуск производится опубликованной
командой, Flash не пишет скрипт. После каждой строки дождись off/off и job.restore=pass,
проверь новый VPN-сеанс. При unconfirmed переходи к §11.

```bash
"$PY" -m xgw.desync.client start --candidates multisplit --rounds 1 --seconds 180
"$PY" -m xgw.desync.client status
# Во время queued/running:
"$PY" -m xgw.desync.client cancel
```

| ID | Действие | PASS |
|---|---|---|
| JOB01 | Отмени первый короткий запуск немедленно; потом ещё один после preparing | cancelled, restore=pass; новых попыток после отмены нет, off/off, очередь свободна и свежий VPN работает |
| JOB02 | Во время короткого запуска закрой веб и desktop на 30 с, затем верни | Задание продолжает работу независимо от UI; в обоих UI тот же id и накопленные результаты |
| JOB03 | Во время короткого запуска сама выполни sudo systemctl restart xgw.service | Старое задание не продолжается; состояние interrupted и restore=pass; исходная политика вернулась, воркеры остановлены |
| JOB04 | Пока задание running, во второй вкладке попробуй повторный старт/изменение | UI блокирует обычную правку, API второго старта busy; нет второго runner. Конфликт внешнего CAS проверен тестом, не подделывай root job.json |
| JOB05 | После окончания открой job.json под sudo только для stat и сверки прав | Каталог 0700, job.json/cancel/lock 0600, приватный original не попадает в GET, UI, логи или Git |

JOB02/03 делай отдельными короткими запусками с готовой командой выше. Для JOB02
если он завершился до 30 с, это нормальный быстрый результат; повтори один раз с
двумя кандидатами, а затем запиши фактическое время. Не растягивай фазу ради UI.

Полный набор полей исходной политики восстанавливается, посторонние поля panel.json
сохраняются. Побайтовый возврат **всего** panel.json обеспечивает §11; эти два
критерия не подменяют друг друга.

## 6. CDN без подписи: проверка гипотезы и полная матрица

### A/B/B/A на одном CDN authority

A — исходный свежий /videoplayback, B — /generate_204 того же hostname.
Не меняй профиль между A и B: используй hostfakesplit_md5 как принятый контроль
либо текущий multisplit, записав выбор. Адрес страницы, домены, клиент и WAN те же.
Перед каждым сохранением и преобразованием — off. Для B нажми «CDN-проба без подписи»
в вебе либо desktop; второй вариант проверь обратным повтором. Либо:

```bash
"$PY" -m xgw.desync.client probe-persistent
```

Команда удаляет подпись и query, сохраняет HTTPS hostname, не скачивает URL и не
включает маршрут. Старый полный URL сохрани только в приватном месте через DevTools,
не выводи в терминал. Для возврата A введи прежнюю пару в штатную форму.

Сделай A/B/B/A, каждый раз один запуск:
```bash
"$PY" -m xgw.desync.client start --candidates hostfakesplit_md5 --rounds 1 --seconds 180
```

Жди завершения не дольше 180 с + 90 с возврата. Для каждой строки запиши профиль,
порядок, фазу connect/TLS/request/headers/body, HTTP, elapsed_ms страницы/CDN,
transport, причину, bytes, spent delta, fresh/policy_matched. Смена DNS/IP
разделяет контексты; не усредняй разные окна как один опыт.

- A=403/expired, B=HTTPS pass: B устраняет зависимость служебной проверки от
  подписи, **но ещё не доказано**, что клиентское медиа проходит.
- A и B истекают в TLS на том же IP: замена пути не помогла этому отказу.
- B даёт HTTP не-2xx: B непригодна на этом CDN, верни свежую A.
- B проходит, видео не играет: транспортная проба недостаточна; это отдельный
  дефект критерия, не «YouTube работает».
- Нет подходящего CDN/доступа DevTools: блокер этой ветки, остальные § продолжай.

### Девять профилей, два круга

На пригодной паре проб выполни **одну** полную матрицу 18 попыток. Первый круг
прямой, второй обратный. В неё входят шесть T09 и принятые контроли
hostfakesplit_md5/static/clone. ALT9 сюда не входит: он только Standalone.

```bash
"$PY" -m xgw.desync.client start --seconds 3600
"$PY" -m xgw.desync.client monitor --output "$D/matrix.jsonl" --seconds 3600 --interval 15
"$PY" -m xgw.desync.client status >"$D/matrix-result.json"
```

Само задание прекращается по бюджету времени, отмене, ошибке или чужой правке,
возвращая исходную политику через контроллер. После конца его допустимы дополнительные
90 с на подтверждение off. Если оно завершилось раньше, монитор можно прервать Ctrl+C,
дождавшись job.restore=pass, и анализировать неполную по времени запись.

PASS механики: complete, 18 строк с 9×2, правильный обратный порядок, бюджет не
превышен, restore=pass. Сетевые FAIL остаются результатами строк, не поломкой
самого перебора. failed/time_budget означает неполную матрицу — не дорисовывай строки.

Если у профиля два HTTPS pass, попробуй «Сохранить профиль» в одном UI, reset в
другом. Команды эквивалентны:
```bash
# Подставь имя только из фактически успешных строк; пример не означает успех.
"$PY" -m xgw.desync.client pin hostfakesplit_md5
"$PY" -m xgw.desync.client reset
```
Должны меняться только стратегия, mode остаётся off. Профиль с FAIL, старое id,
возраст >6 ч или смена URL/доменных/runtime-настроек отклоняются. Возраст/future
и несовпадения контекста проверяй опубликованными тестами, системные часы не меняй.

## 7. Flowseal из UI и Standalone без VPN

Сначала запусти локальную проверку уже установленных каталогов/ассетов:

```bash
"$PY" -c 'from xgw.desync import flowseal; flowseal.live_arguments(); print("PINNED_ASSETS_OK")'
"$PY" -m xgw.desync.client import-flowseal
```

Ожидается сверка закреплённых каталогов и хэшей. При отсутствии ассетов нет
скачивания произвольного кода, режим не меняется. Подготовку известного снимка
выполни готовыми командами [T10 §1](T10-FLOWSEAL-LIVE.md#1-подготовка), только
часть получения/проверки/установки ассетов; **не применяй старый overlay T10**.
Это техническое выполнение готового установщика, не изменение реализации.

В off нажми импорт в вебе, потом desktop. Стратегия flowseal_alt9 и 6 доменов
сохранены, HTTPS-gate выключен, режим остаётся off. Попытка Selective отклонена.

| ID | Проверка контракта ALT9 | PASS |
|---|---|---|
| FLOW01 | До импорта профиль обычный. Открой обе формы, сравни strategies API | ALT9 не предлагается как обычный новый выбор; исходный patch4 и новый тест с доступными ассетами проходят |
| FLOW02 | Нажми импорт в вебе; затем импорт в desktop с актуальной ревизией | Только проверенный локальный импорт выбирает ALT9; второй вызов unchanged, mode остаётся off, чужие поля не потеряны |
| FLOW03 | С ALT9 в вебе измени retry; в desktop открой и сохрани форму с прежним профилем | Оба запроса приняты, ALT9 не теряется; сохранение без изменений unchanged, не требуется повторный импорт |
| FLOW04 | В off выбери multisplit, снова открой форму | ALT9 больше не предлагается в обычном выборе; возвращается только отдельной кнопкой импорта |
| FLOW05 | Опубликованные тесты отсутствия/повреждения ассетов и повторной проверки перед Standalone | Import/activation blocked, off разрешён; ошибки не содержат приватных строк. Реальные ассеты ради имитации не удалять и не переименовывать |
| FLOW06 | Повтори stale expected и запрет Selective на импортированном ALT9 | Конфликт до записи, неподходящий режим не активируется; все старые ограничения сохранены |

Отсутствие ассетов не мешает сохранять уже выбранный выключенный профиль при
правке других полей и выключать запущенный режим. При новом включении Standalone
хэши проверяются заново. Эти ветки покрыты обязательными тестами; live-ассеты
остаются нетронутыми. Сохранённый ALT9 виден в форме как текущий профиль, это не
предложение выбрать его из обычного списка после переключения на другой.

Standalone включи штатной кнопкой. Проверь worker, nft, очередь и применённый Xray:
выбранный HTTPS-трафик через zapret2, VPN bridges/балансировщики приостановлены,
остальной трафик напрямую; это не Selective.

Проведи пары multisplit / ALT9 / ALT9 / multisplit по 180 с пригодного 720p,
один ролик, Chrome TCP, новый сеанс в каждой строке. Между строками off и смена
профиля в форме; для multisplit выключи HTTPS-gate и не меняй остальные параметры.
Для лучшего кандидата дополнительно 15+5 минут с перемоткой, если с §8 такой
опыт ещё не покрыт. Не утверждай преимущество по одному pass.
После каждой Standalone-фазы верни off/off и проверь обычный VPN.

## 8. Главное: YouTube через zapret2, другой трафик через VPN

Возьми кандидата с двумя pass и пригодную пару проб из §6. Настрой off, профиль,
6 доменов, HTTPS-gate=true, check=180, retry=120. Включи Selective кнопкой.
Не подменяй пробу, IP или состояния ради получения active. Дождись настоящего
active и двух перепроверок на одной ревизии либо зафиксируй fallback и продолжай
ветку восстановления. Для signed URL убедись, что срока хватает на весь опыт.

Для контроля медиа используй готовые сборщики. QUEUE возьми из конфигурации,
обычно 200. Ролик сама выбери из уже известного доступного публичного видео,
длительностью >30 минут, с 720p и перемоткой; не проси владельца открыть ролик.

```bash
QUEUE=200
collect() {
  sudo -v
  sudo -n env PYTHONPATH="$PYTHONPATH" "$PY" docs/helpers/selective_probe_watch.py \
    --queue "$QUEUE" --seconds 180 --media-pairs --socket-stats >"$D/$1.jsonl" &
  WATCH_PID=$!
}
# VIDEO присвой выбранный публичный YouTube ID из 11 символов.
test "${#VIDEO}" -eq 11
"$TELEMETRY_PY" docs/helpers/youtube_telemetry.py --video "$VIDEO" \
  --label combined-selective --out "$D/player-selective" --seconds 1560 \
  --height 720 --channel chrome --disable-quic >"$D/player-selective.log" 2>&1 &
PLAYER_PID=$!
collect media-open
```

Самостоятельно проверь согласие/автовоспроизведение и качество в открывшемся Chrome
через vision. Основное измерение — JSONL плеера + CDP сетевые события,
статистика с экрана служит проверкой корректности. Не ограничивайся скриншотом.
Не считай буфер и пользовательскую паузу успешным прогрессом передачи.

1. В пределах одного active и одной ревизии сними фон без передачи, затем
   media-open с новым сеансом. Не принимай пару через смену nft handle, worker,
   policy_key или служебную пробу. При rejected пересними одно короткое окно.
2. Одновременно в новом отдельном сеансе открой обычный сайт вне YouTube. Его
   выход должен совпасть с исходным VPN, а медиапоток должен идти по zapret2.
3. Наблюдай 15 минут пригодного 720p, сделай media-mid. Перед перемоткой за
   текущий буфер выполни collect media-seek, перемотай через GUI, ещё 5 минут.
4. При наличии уже рабочего сервера подписки через sing-box повтори короткий
   контроль ordinary-site + 180 с видео на нём. Выбирать только известный рабочий
   сервер, не импортировать новый. Нет такого сервера — BLOCKED_DEPENDENCY для
   этого ядра; это не PASS обоих ядер.
5. Для естественной смены CDN-IP запиши новые CDP peer/IP локально. Если адресов
   несколько, применяй существующий H02-анализ к раздельным контекстам. При одном
   IP перенос остаётся INCONCLUSIVE.

MEDIA_PATH=CONFIRMED требует общей accepted-пары Xray/NFQUEUE, прироста очереди
и downlink zapret2 сверх фона, свежих CDN-байтов плеера и помеченного сокета к тому
же IP, неизменных policy/worker/rule и параллельного VPN-контроля. Только
положительные дельты без этой связи дают PARTIAL.
[Полные критерии пары](T12-SELECTIVE-MEDIA-PAIRS.md#2-короткое-окно-живой-передачи).

Для качества: ≥95% пригодного времени в 720p, прогресс ≥98% пригодного времени,
остановки/буфер/пропуски/восстановление после seek — из анализатора
[YOUTUBE-TELEMETRY](YOUTUBE-TELEMETRY.md). Не меняй пороги после результата.

Если active не получен ни в одной строке, MEDIA_PATH/длинный Selective = NOT_RUN.
Standalone и VPN-контроль всё равно выполняются. Это означает отсутствие принятого
Selective в данном окне, не доказательство бесполезности всех стратегий.

## 9. Отказ worker, малый бюджет и восстановление

Отказ проверяй только после фактического active; иначе эту строку отметь NOT_RUN.
Сохрани текущие Unit/InvocationID/MainPID. Один раз:

```bash
sudo systemctl kill --kill-whom=main --signal=SIGKILL xgw-zapret2.service
```

Дождись снятия selective-правила. Открой **новый** Chrome-сеанс YouTube и обычный
сайт через VPN, сохрани свежие CDN-байты и Xray delta. Запиши время от первого
отказа до принятого нового VPN-сеанса. Старый TCP-сеанс не обязан мигрировать.

Малый бюджет уже принят в последнем отчёте; здесь достаточно одной регрессии:
в off установи допустимый лимит по текущему spent так, чтобы осталось меньше
резерва одной попытки (целые МиБ, без редактирования БД). Попробуй старт из UI и
job/start. Должен быть отказ по бюджету, без запуска worker/роста spent. Если
spent сегодня <1 МиБ и целым лимитом нельзя получить такой остаток, используй
принятый тест exhausted_budget; не трать трафик искусственно. Верни 512 МиБ
для суточной фазы, **не обнуляй** расход дня.

Standalone fail-closed: при успешном Standalone один SIGKILL соответствующего
воркера должен закрыть выбранный путь; VPN сам не включается. Далее off/off,
штатный VPN, свежий контроль. Не смешивай этот ожидаемый исход с Selective fallback.

## 10. Сутки, UTC и M3 в том же задании

Проводить после успешного возврата предыдущих фаз и при исправном VPN. Если
код/возврат регрессировал, сутки не нужны — rollback и публикация. Режим для суток:
Selective с проверенным кандидатом и пригодной пробой без подписи, если он прошёл
§8; иначе off/off и обычный VPN. Во втором случае проверяются монитор, UTC и M3,
а стабильность Selective остаётся NOT_RUN.

Верни check=180, retry=300, временный budget=512. Измерения бюджета ограничены
резервами контроллера; достижение лимита — ожидаемый fallback, не повод его обойти.
Не включай free_pool=on для всего дома специально ради этого опыта. Если пул уже
используется по исходной настройке, наблюдай его; иначе собери только диагностику.
Не останавливай WAN и не подделывай истёкшие учётки на рабочем шлюзе.

Перед сутками заверши старый таймер и **сразу** поставь новый 26-часовой
предохранитель с тем же restore. Делай это только при off/off и рабочем VPN;
затем активируй выбранный проверенный Selective, если он принят.

```bash
sudo systemctl stop "$UNIT.timer"
sudo systemctl reset-failed "$UNIT.service" || true
sudo systemd-run --unit=xgw-combined-day-rollback --on-active=26h \
  --timer-property=AccuracySec=1s /bin/bash "$BACKUP/restore.sh" \
  "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active xgw-combined-day-rollback.timer
DAY_UNIT="xgw-combined-monitor-$(date +%s)"
systemd-run --user --unit="$DAY_UNIT" --collect \
  --property=RuntimeMaxSec=25h --property=UMask=0077 \
  /usr/bin/env PYTHONPATH="$PYTHONPATH" "$PY" -m xgw.desync.client monitor \
  --output "$D/day.jsonl" --seconds 86400 --interval 60
sudo xgw pool stats >"$D/pool-before.txt"
sudo xgw diag >"$D/diag-before.txt"
```

Сборщик только читает API: не создаёт сетевые пробы и маршруты. Файл создаётся
эксклюзивно с 0600, максимум 16 МиБ/90 000 с. В нём whitelist агрегатов, без
подписок, серверов, устройств, cookie и URL. UI можно закрыть. Flash сама
наблюдает за unit и после завершения продолжает задание; не поручает это владельцу.
Один отчёт публикуется по завершении либо раньше при аварийном останове.

В течение суток два раза проверь обычный сайт и короткое новое видео (в начале
и после UTC-границы), снимай полноценную телеметрию только на эти ограниченные окна.
Проверку перехода UTC проводи по действительному времени, часы не переставляй.
Сравни budget перед/после 00:00 UTC, первый реальный резерв нового дня и worker:
чтение API само по себе не доказывает возобновление проб.

По окончании:

```bash
"$PY" -m xgw.desync.client analyze "$D/day.jsonl" >"$D/day-summary.json"
sudo xgw pool stats >"$D/pool-after.txt"
sudo xgw diag >"$D/diag-after.txt"
```

Для DAY_PASS требуются ≥24 часов фактического elapsed, отсутствие крупных
необъяснённых дыр и исправность VPN. Analyze считает только интервалы со свежими,
совпавшими policy и состоянием; это не число секунд просмотра видео.
Для SELECTIVE_DAY отдельно нужны активные интервалы, естественные перепроверки,
доступность видео в контрольных окнах и отсутствие циклических переключений.

По M3 запиши: фактический режим пула, длительность, пригодные серверы, время
closed, смены и причины, среднюю скорость из штатного дневника. При отсутствии
реального трафика пула M3_TRAFFIC=NOT_RUN, даже если API доступен. Не объявляй
R32/R35 полезными без сравнимых данных. R39/полный R50 не закрываются монитором.

По H01/H04/H07/H11/H12:
- Поздний reset/EOF и смену CDN сопоставь с CDP и метриками плеера при наличии
  естественного события; по одному зависанию не делай вывода о ТСПУ.
- AutoTTL и shared memory не включать в домовой трафик ради неподтверждённого
  ускорения. Сними CPU/RSS/потери очереди штатными ограниченными наблюдениями
  в 60-секундном видео и фоне; нет bottleneck — нет основания для fanout.
- QUIC Initial/ECH и remote obfs не считать реализованными этой матрицей.
  Без собственного совместимого H3 endpoint / удалённого узла — соответствующий
  BLOCKED_DEPENDENCY. WAN IPv6 здесь NOT_APPLICABLE, а не вечный блокер.
- По H02 сравнивать перенос только при ≥2 реальных адресах в сопоставимых
  контекстах, исходные exact-IP записи сохранять; hostname не означает один IP.

## 11. Единый возврат и обязательная проверка финала

При полном PASS кода оставь новый код, но восстанови исходные конфиги. При
регрессии GUI/системы/маршрута используй rollback. Даже при частичном сетевом FAIL
код можно принять лишь если управление, границы и возврат прошли; отдельно запиши
непринятый сетевой результат.

Сначала отмени активный job и дождись off/off/restore=pass. Если отмена недоступна,
используй независимый restore напрямую. Он останавливает демон, возвращает исходный
panel.json, при необходимости файлы, запускает демон и штатный apply. При штатной
остановке job имеет время завершить возврат; при прерывании журнал обеспечивает
повторный CAS-возврат при запуске. При чужом изменении его нельзя затереть.

```bash
# Выбери ровно одно: accept для принятого кода либо rollback при регрессии.
RESULT_MODE=accept
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" \
  "$RESULT_MODE" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
sudo cat /proc/net/netfilter/nfnetlink_queue
sudo test -f "$BACKUP/restore-completed"
if [ "$RESULT_MODE" = accept ]; then check_installed; fi
sudo systemctl stop "$UNIT.timer"
sudo systemctl stop xgw-combined-day-rollback.timer 2>/dev/null || true
```

Открой новый YouTube-сеанс через VPN и обычный сайт. Подтверди CDN-байты,
отсутствие selective client-rule, отсутствие нового worker. Сверь acct/offload/
правила с исходными; расход бюджета сохраняется, его обнуление не является
возвратом. Закрой только тестовые браузеры/сборщики. Суточный user-unit при досрочном
конце останови по его точному DAY_UNIT, а не по маске. Проверь диск и фоновые
процессы; не оставляй бесконтрольную запись.

Если restore не удался: не продолжай эксперименты, сохрани точную ошибку, запроси
необходимый доступ, не называй VPN восстановленным без нового сеанса.
Публикация отчёта обязательна и в этом случае.

## 12. Один автоматически опубликованный отчёт

Файл docs/reports/YYYY-MM-DD_combined-open-blocks.md. В отчёте:
- SHA кода, SHA базы/GUI, Ubuntu, время, доступы, кто реально запускал команды;
- CORE_TESTS / BROAD_RESULT / BASELINE_MATCH (если был) / API / Qt;
- INSTALL 8/8 / UI01–UI08 / JOB01–JOB05 / FLOW01–FLOW06;
- A/B/B/A, таблица всех 18 строк, pin/reset, Flowseal, качества плеера и пути;
- START/RECHECK, MEDIA_PATH, ordinary VPN, Xray/sing-box по отдельности,
  SIGKILL_SELECTIVE, SIGKILL_STANDALONE, budget, UTC_LIVE, DAY, M3 и H01–H12;
- для каждого PASS/FAIL/NOT_RUN/INCONCLUSIVE/NOT_APPLICABLE/BLOCKED — причина и
  обезличенная метрика; code correctness отдельно от network benefit;
- финальные режимы, конфиги побайтово, версии/файлы, PID, диск, таймеры,
  сохранившиеся процессы и результат свежего VPN-сеанса.

Исходники, тесты и планы не меняй. Перед публикацией сама проверь отчёт на секреты.
В чистом исходном checkout (не detached source) fetch и fast-forward ветку,
добавь **только** файл отчёта, commit и push origin integration/zapret2-batch1.
При concurrent push fetch/rebase только своего отчётного коммита, без force.
Проверь SHA удалённой ветки. Не проси отдельное подтверждение публикации.
Не обещай коммит собственного SHA внутри себя: SHA публикации укажи в сообщении
либо отдельным метаданным-коммитом, если это принято в текущем окружении.

