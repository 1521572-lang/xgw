# GLM — установить исправления списка серверов, GeoIP и анимации карты

- target_os: **Ubuntu 24.04 LTS**.
- delivery_branch: `integration/zapret2-batch1`.
- base_commit: **f2317886e1aa90f67a69d49b6ee59f102b5e5b8d** — отчёт PASS r2.
- installed_backend_commit: **4f5349537e2e4d087cb88cfd8642d62dfde8e0c5**.
- gui_base_commit: **7c20f59023ec39e5c5ce4606767ea915c3b91f64** с двумя накладками r2.
- code_commit: последний коммит NEXT_STEP в delivery_branch; закрепить командой ниже.
- report: `docs/reports/YYYY-MM-DD_gui-catalog-map.md`.
- scope: имена и страны IP, сортировка заголовками, живая карта. T03–T07 не выполнять.

Сама запускай команды, читай журналы/API, работай с GUI через vision. Не проси владельца
запускать скрипты/присылать скриншоты. Нет терминала/sudo/GUI — запроси доступ. По завершении
автоматически commit/push отчёта и разрешённых хотфиксов без нового подтверждения.
Не публикуй подписки, токены, IP серверов, исходные конфиги и приватные снимки экрана.

## 1. Закрепи исходное и новое состояние

Прочитай `docs/reports/2026-11-15_desync-batch1-r2.md`: backend и GUI оставлены установленными.
Прежнее ТЗ сохранено в `ARCHIVE-DESYNC-BATCH1-r2.md`. Карточка zapret2 сохраняется.
Integration содержит GUI-накладки, не весь frontend; полный GUI для проверки собирается ниже.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
git fetch origin refs/heads/integration/zapret2-batch1:refs/remotes/origin/integration/zapret2-batch1
BASE=f2317886e1aa90f67a69d49b6ee59f102b5e5b8d
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
CODE=$(git log -1 --format=%H origin/integration/zapret2-batch1 -- docs/handoff/NEXT_STEP.md)
git merge-base --is-ancestor "$BASE" "$CODE"
D=$(mktemp -d "$HOME/xgw-gui-catalog.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
printf '%s\n' "$BASE" "$GUI_BASE" "$CODE" > "$D/revisions.txt"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r > "$D/kernel.txt"
nft --version > "$D/nft.txt"
curl --version > "$D/curl.txt"
sudo systemctl cat xgw.service > "$D/unit.txt"
sudo cat /usr/local/bin/xgw > "$D/launcher.txt"
PID=$(systemctl show xgw.service -p MainPID --value)
test "$PID" -gt 0
PY=$(sudo readlink -f "/proc/$PID/exe")
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
GUI=$(readlink -f /opt/xgw/gui/releases/7c20f59023ec39e5c5ce4606767ea915c3b91f64)
```

Подтверди PACKAGE/PY по launcher/ExecStart/cmdline, GUI — по dispatcher и процессу окна.
Другие пути найди сама; неизвестный layout — BLOCKED. Выполни только `--version`
действующего nfqws2. Приватно сохрани SHA config.toml/panel.json, PID главного xgw-xray,
состояния служб, nft/ip-rule/ip-route. В отчёт — сравнение, не содержимое.
Запрещены flush ruleset, очистка conntrack, смена маршрутов/VPN-сервера/режима zapret2.
Если workers уже включены — не отключай ради установки, остановись до apply.

## 2. Тесты до установки

Используй отдельное dev-venv с системным PyQt6. Рабочее окружение XGW не меняй.
При отсутствии python3-venv/PyQt6 запроси недостающий доступ. GUI запускай от пользователя.

```bash
python3 -m venv --system-site-packages "$D/test-env"
T="$D/test-env/bin/python"
"$T" -m pip install pytest ruff
"$T" -m pytest --portable tests/test_gui_server_data.py tests/test_geodat.py \
  tests/test_zapret2_panel.py tests/test_desync_schema.py
"$T" -m pytest -q tests/test_panel.py tests/test_engine.py tests/test_geodat.py \
  tests/test_config.py tests/test_managed.py tests/test_zapret2.py tests/test_nfqws2.py
"$T" -m ruff check src/xgw/geodat.py src/xgw/engine.py src/xgw/watch/panel.py \
  src/xgw/watch/server_geo.py vpn_ui/xgw/catalog.py vpn_ui/xgw/sidebar.py \
  vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py tests/test_gui_server_data.py tests/test_geodat.py \
  tests/test_panel.py tests/test_vpn_ui_sidebar.py docs/helpers/gui_catalog_install.py
git worktree add --detach "$D/gui" "$GUI_BASE"
for f in vpn_ui/xgw/overview.py src/xgw/gui/zapret2.py vpn_ui/xgw/catalog.py \
         vpn_ui/xgw/sidebar.py vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py; do
  cp "$D/source/$f" "$D/gui/$f"
done
PYTHONPATH="$D/gui:$D/gui/src" "$T" -m pytest -q tests/test_vpn_ui_sidebar.py
PYTHONPATH="$D/gui:$D/gui/src" "$T" -m pytest -q "$D/gui/tests/test_vpn_ui_xgw.py" \
  -k map_animates_to_active_endpoint_and_ignores_preview
```

Qt-тесты не должны быть skipped. Они проверяют щелчки, числовой порядок, неизвестные
значения внизу, выбор/прокрутку, отсутствие команд выбора, пульсацию и остановку таймера.
test_panel проверяет страну применённого адреса Xray/sing-box и отсутствие секретов в API.
При провале не ослабляй assert и не ставь PASS. Новое ТЗ не разрешает смену рабочего сервера.

## 3. Подготовь payload и мировую GeoIP-базу

Закрой установленное окно штатно, сохрани канал управления.

```bash
PAYLOAD="/opt/xgw/handoff/gui-catalog-$CODE"
BACKUP="/var/lib/xgw/handoff/gui-catalog-$CODE"
test ! -e "$PAYLOAD" && test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base" "$PAYLOAD/gui_base"
git archive "$CODE" src/xgw vpn_ui docs/helpers/gui_catalog_install.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$BASE" src/xgw/geodat.py src/xgw/engine.py src/xgw/watch/panel.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$GUI_BASE" src/xgw/watch/server_geo.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$GUI_BASE" vpn_ui/xgw/catalog.py vpn_ui/xgw/sidebar.py vpn_ui/views/map_canvas_view.py vpn_ui/xgw/window.py |
  sudo tar --no-same-owner -x -C "$PAYLOAD/gui_base"
sudo chmod -R go-w -- "$PAYLOAD"
HELPER="$PAYLOAD/code/docs/helpers/gui_catalog_install.py"
GEOIP=/opt/xgw/xray/geoip-ui.dat  # уточни по действующему Paths.xray_dir
GEO_ARGS=()
```

Основную geoip.dat ядра не заменяй. Отдельную существующую geoip-ui.dat оставь, если она
читается новым geodat и содержит более 100 стран; запиши SHA и число стран. Для инспекции
используй root Python с `sys.path.insert(0, "$PAYLOAD/code/src")`, geodat.countries(path),
посчитай уникальные непустые коды в `_index` (это диагностическая проверка, не API).
Если UI-базы нет/она повреждена/неполная, выполни следующий блок. Пин из ранее принятого ТЗ
vpn-ui-map; файл применяется **только для отображения**:

```bash
curl --fail --location --max-time 180 -o "$D/geoip-ui.dat" \
  https://github.com/v2fly/geoip/releases/download/202610050438/geoip.dat
printf '%s  %s\n' 4ff4b2ec242a9e87b296ba27ddb85f8311e8d3e071eaebac5be9231c60e408dd \
  "$D/geoip-ui.dat" | sha256sum -c -
sudo install -m 0644 "$D/geoip-ui.dat" "$PAYLOAD/geoip-ui.dat"
if sudo test -e "$GEOIP"; then
  sudo install -m 0644 "$GEOIP" "$PAYLOAD/base/geoip-ui.dat"
fi
GEO_ARGS=(--geoip "$GEOIP")
```

При ошибке скачивания/хэша — BLOCKED_GEO, не подставляй непроверенную базу. Новый файл базы
устанавливается и откатывается helper вместе с кодом. server_geo.py допускается отсутствующий
или точно из GUI_BASE; остальные три backend-файла должны совпасть с BASE. Неизвестное
расхождение — остановка. Старые резервные комплекты не переиспользуй и не удаляй.

## 4. Установи с независимым откатом

Прочитай helper до sudo. Он заменяет только файлы, перезапускает xgw.service, не меняет
сетевые настройки. Manifest: 8 файлов либо 9 с UI-базой. Права файлов/родителей проверяются.

```bash
sudo "$PY" "$HELPER" prepare --payload "$PAYLOAD" --backup "$BACKUP" \
  --package "$PACKAGE" --gui "$GUI" "${GEO_ARGS[@]}"
sudo systemd-run --unit=xgw-gui-catalog-rollback --on-active=20m \
  "$PY" "$HELPER" rollback --backup "$BACKUP"
sudo systemctl is-active xgw-gui-catalog-rollback.timer
sudo "$PY" "$HELPER" apply --backup "$BACKUP"
sudo systemctl is-active xgw.service
sudo journalctl -u xgw.service --since '-3 minutes' --no-pager > "$D/journal-after.txt"
```

Проверь главный Xray PID, config/panel, маршруты и структуру nft. Ошибка старта, другой
маршрут или перезапуск главного Xray → rollback, не сетевые эксперименты. При потере доступа
сработает timer. Немедленный откат выполняй сама:
`sudo "$PY" "$HELPER" rollback --backup "$BACKUP"`.

## 5. Обязательная живая приёмка

Запусти **установленный `xgw gui`** от пользователя графической сессии, не root; если launcher
другой, используй найденный dispatcher. API читай существующим авторизованным клиентом;
не печатай token/cookie/полный JSON. Не ограничивайся preview или тестовыми данными.

1. **LIVE_NAME_COUNTRY:** подписки сверху, у реальных строк видны имя и страна по IP,
   отдельные Мбит/с и Рейтинг. Сопоставь минимум 3 строки с API name/endpoint_country,
   приватно сверь страну применённого IP Xray/sing-box с GeoIP. Для DNS используй
   dns.hosts/predefined. В публичном отчёте обозначь строки A/B/C, без имён и IP.
   Неизвестные/неоднозначные данные — «Страна неизвестна». Если это рабочий сервер,
   разберись в адресе/базе до PASS, не заполняй страну вручную или по флагу подписки.
2. **LIVE_HEADERS:** сама нажми каждый заголовок дважды. Имя — алфавит, скорость/рейтинг —
   числовой порядок; первый щелчок новой числовой колонки по убыванию, повтор меняет
   направление, стрелка видна. Пропуски внизу. После нескольких API-опросов порядок сохраняется.
   Сортировка и просмотр не отправляют POST выбора и не переключают VPN.
3. **LIVE_MAP:** страна текущего main/pin или единственного selected совпадает с фокусом;
   точка пульсирует при уже установленном соединении. Через vision наблюдай несколько секунд
   или сравни два приватных кадра с интервалом: одного скриншота недостаточно. Подписка и
   сортировка не меняют фокус/сервер. При нескольких selected без основного нельзя выдумывать
   один активный сервер: опиши такой режим и проверь смену фокуса отдельно в preview.
4. **FIXTURE_MAP_TRANSITION:** отдельный полный checkout с фикстурами — имя NL, IP-страна JP,
   затем основной сервер DE; фокус плавно JP→DE. Stale/off/standalone снимают подтверждённый
   фокус. Для этого можно использовать Client/scene из GUI_BASE `tests/test_vpn_ui_xgw.py`
   (в том числе `test_map...`); рабочий API/status.json не подменяй, настоящий сервер не меняй.
5. **LIVE_LAYOUT:** обе темы, обычное/узкое окно с раскрытым списком. Имя и страна — две
   строки, цифры отдельны; длинное имя полностью доступно в правой карточке при наведении.
   Проверь hover, клавиатуру, выбор и прокрутку. Недостаточную ширину поправь как UI-хотфикс.
6. **ZAPRET_REGRESSION:** r2-карточка остаётся off/fresh/policy_matched. YouTube NOT_RUN:
   этот проход исправляет отображение и не расширяет сетевые режимы.

Preview не заменяет INSTALLED_PASS. Блокирующий дефект → откат и отчёт. Разрешены мелкие
исправления пути запуска/кодировки, ширины колонок/отступов и fixture. Изменения маршрутов,
выбора сервера, смысла GeoIP или ослабление проверки — остановка для разработчика.

## 6. Заверши и автоматически опубликуй

После PASS отмени timer, проверь, что rollback не выполняется, затем каждый установленный SHA:

```bash
sudo systemctl stop xgw-gui-catalog-rollback.timer
if sudo systemctl is-active --quiet xgw-gui-catalog-rollback.service; then exit 1; fi
sudo "$PY" -I - "$BACKUP" <<'PY'
import hashlib, json, pathlib, sys
for row in json.loads((pathlib.Path(sys.argv[1]) / 'manifest.json').read_text()):
    assert hashlib.sha256(pathlib.Path(row['target']).read_bytes()).hexdigest() == row['new_sha']
print('installed hashes: PASS')
PY
```

При PASS оставь новый backend/GUI. При FAIL восстанови прежние файлы, подтверди восстановление,
потом отмени timer. Backup/payload оставь. Отчёт по `TEMPLATE_gui-catalog-map.md`: BASE/CODE,
ОС, результаты всех групп, установка/preview, причины неизвестных стран и итоговое состояние.
В исходном репозитории, от свежего delivery tip:

```bash
git fetch origin integration/zapret2-batch1
git switch -c glm/gui-catalog-map-report FETCH_HEAD
git add docs/reports/YYYY-MM-DD_gui-catalog-map.md
git diff --cached --check
git diff --cached  # проверь отсутствие приватных данных
git commit -m 'docs: report installed server list and live map acceptance'
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Хотфиксы — отдельными коммитами с причиной/проверкой. Не используй git add . или force.
При новом remote tip прочитай изменения и перенеси только свой отчёт/хотфикс на него.
Если доступа GitHub нет — запроси доступ, не заявляй публикацию до успешного push.
