# Ubuntu 24.04 — desync batch 1 r2 — 2026-11-15

- RESULT: **PASS** — батч 1 установлен и оставлен: backend (5 изменённых + 3 новых файла) и
  две GUI-накладки на принятый freepool-релиз; демон перезапущен штатно helper-ом, карточка
  `/api/state.zapret2` в LIVE_OFF соответствует контракту, «Нет данных» в реальном GUI
  пропало. Контрольный таймер отката отработал холостую (отменён до срабатывания), манифест
  из 10 строк сверен — установленные файлы на месте.
- BASE: 48f7ebae15096c40aaa4b82b7f3b19488ab24dd3
- CODE / PLAN / HOTFIX commits: CODE = `4f5349537e2e4d087cb88cfd8642d62dfde8e0c5` (r2,
  «Fix dormant zapret2 strategy loading and refresh batch 1 acceptance»; единственный коммит
  с NEXT_STEP.md). Кодовых хотфиксов исполнителя **не потребовалось**. Прошлый раунд:
  отчёт 48040ea и fixture-хотфикс 0a4b664 (уже в ветке).
- Executor: GLM 5.3 Flash; команды и vision на шлюзе выполнены исполнителем; root — один
  systemd-run --system юнит с FIFO (диалоги подтверждены владельцем); GUI — от пользователя
  через `systemd-run --user`.
- OS ID / VERSION_ID / kernel: `ubuntu` / `24.04` (24.04.5 LTS noble) / `7.0.0-43-generic`.
- Python 3.12.3 (демон /usr/bin/python3.12) / nft 1.0.9 / nfqws2 v1.0.7 (038c97e5…) — только
  `--version` / curl 8.5.0 **без HTTP3** (QUIC-пробы не запускались, вне скоупа).
- Installed backend path: `/opt/xgw/lib/xgw` (без symlink); GUI source: установленный релиз
  `/opt/xgw/gui/releases/7c20f59…` (dispatcher из vpn-ui-install, ACTIVE) — накладки батча
  применены helper-ом в его файлы с резервной копией.
- GUI mode: **INSTALLED** (обе накладки в установленном релизе; PREVIEW-прогоны дополнительно
  на checkout для fixture-состояний).

## Checks

| Check | PASS / FAIL / NOT_RUN | Evidence / reason |
|---|---|---|
| Ubuntu 24.04 confirmed | **PASS** | os-release: ID=ubuntu, VERSION_ID=24.04 (24.04.5/noble); kernel/nft/curl/nfqws2 записаны приватно |
| Baseline hashes | **PASS** | config.toml `89bf2a67…`, panel.json `33916cb5…` (не менялись ни в r1, ни в r2); workers off; приватные снимки nft/ip-rule/ip-route — в каталоге прогона |
| Portable unit tests | **PASS** | `pytest --portable tests/test_desync_schema.py tests/test_zapret2_panel.py` — **72 passed** (r2 расширил набор с 51) |
| Targeted Linux regression tests | **PASS** | **196 passed, 0 failed** (было 194+1: пред-существующий провал free_pool/pin исправлен разработчиком в 4f53495). Отдельно: `test_off_is_original_config_without_starting_anything` — **passed**: сохранённая hostfakesplit_md5 при off не создаёт маршрут, вход для проб и не запускает обработчик |
| Ruff | **PASS** | All checks passed (0.17.5, полный список файлов из §3 r2, включая новый src/xgw/zapret2.py) |
| Rollback timer armed before apply | **PASS** | `systemd-run --unit=xgw-desync-b1-rollback --on-active=20m` → timer active до apply; после приёмки остановлен, service никогда не был active |
| Daemon / API LIVE_OFF | **PASS** | helper apply: RC=0; xgw.service active, новый MainPID 581316 (штатный stop→start); журнал за 15 минут: **0 traceback/error**; panel 200; `/api/state.zapret2` присутствует |
| policy_matched / fresh | **PASS** | schema_version=1, fresh=true (observed_at в пределах 90 с), policy_matched=true, state=off, mode=off, engine_mode=off, source=engine; бесконечных pending/legacy_snapshot нет; конфигурация при off с исходной сохранённой стратегией (без замены) |
| Стратегия/счётчики/доказательства | **PASS** | strategy=null (активный не подтверждён), configured_strategy=seqovl (дефолт engine_profile схемы — «настроено, но не запущено»; в config.toml ключей engine нет), counters все null, evidence transport=unknown / playback=not_tested — выдуманного успеха видео нет |
| can_off / can_edit / blockers | **PASS** | can_off=false, can_edit=false, capabilities status-only; blockers для всех режимов: «Управление режимами пока недоступно в этой версии панели.» — причина видна |
| GUI «Нет данных» пропало | **PASS (LIVE)** | Установленный GUI с накладками: виджет zapret2 показывает **«Выключен»** (LIVE), tooltip «Обработка выключена.» без None; главный экран и карточка согласованы с API (AUTO-сервер, плитки, «Защищено») |
| Темы / узкое окно | **PASS (LIVE)** | Светлая и тёмная, 1002×650 и 680×650 (☰-сворачивание, виджет-колонка и карта на месте), текст без обрезок и без None в подписи стратегии |
| FIXTURE_ACTIVE / ERROR / ABSENT / STALE | **PASS (PREVIEW)** | Отдельный видимый процесс на checkout GUI_BASE + накладки r2 (сеть/сервисы не тронуты): 16 состояний — подписи точны (missing→«Нет данных», off→«Выключен», off+selective→«Не используется», active→«Обработчик готов» + оговорка про YouTube, error→«Ошибка обработчика», absent→«Не установлен», fresh=false→«Не подтверждён», pending/preparing/blocked/fallback→«Прямой путь отключён»/compared/unknown, legacy без policy_key→«Выключен»); `Client.sent`=0 |
| DORMANT_LOAD | **PASS** | managed.load копии реального panel.json: strategy=hostfakesplit_md5, mode=off, 10 доменов; migrate(source=gui-light) сохраняет стратегию без подстановки, идемпотентно; project при off проходит и сохраняет strategy в проекции |
| DORMANT_PERSIST | **PASS** | set_desync на временном файле в D: 0600, flock без конфликтов, повторное сохранение той же политики не переписывает файл (mtime неизменен); reload читает selected.strategy=hostfakesplit_md5/off; канонический документ сохраняет **домены 10/10 точно**; легаси-секция очищается явно (по контракту: единственная власть канонического документа) |
| probe_urls | **PASS (N/A)** | В исходной легаси-секции probe_urls пуст (mode=off — пробы не нужны по контракту); migrate сохраняет «точно» (0→0); после explicit replacement — в каноническом документе |
| UNSUPPORTED_ACTIVATION_REJECTED | **PASS** | Попытка перевода копии в selective с hostfakesplit_md5: PolicyError «selected strategy requires batch T04» **до записи**, файл не изменился; standalone: PolicyError «standalone requires batch T04» |
| Configuration unchanged | **PASS** | SHA config.toml/panel.json идентичны до/после apply |
| Xray PID / other services / network structure | **PASS** | Главный Xray PID 255025 не менялся (при stop демона штатно убит его transient-потомок free-pool, демон поднял свои процессы заново — обычное управление детьми, маршрутов не касался); xgw-net/xgw-xray active, workers off; nft-снимок после — только сравнение структуры, изменений нет |
| Installed hashes after timer cancellation | **PASS** | После остановки таймера (rollback не выполнялся): все 10 целевых файлов совпадают с manifest `new_sha` — батч оставлен установленным |
| Restore | **N/A** | не требовался |

## Blocker r1 → разрешение в r2

`project()` в r1 отклонял любую не-multisplit/multidisorder стратегию даже при mode=off —
легаси `hostfakesplit_md5` в panel.json ронял `config.load()` (отчёт 48040ea). В 4f53495
исправлено: при `mode=off` известные схеме selected-стратегии сохраняются «спящими» без
подстановки (и в документе, и в Config.zapret2); включение их в selective/compare и
standalone по-прежнему отклоняется до записи. Проверка §4 «new config reader» теперь:
`PASS; policy off; warnings: 0; dormant strategy kept: hostfakesplit_md5` и
`schema.migrate(asdict(cfg.zapret2)) == cfg.desync` — подстановки нет.

## Observations and hotfixes

1. Кодовых хотфиксов не потребовалось. Механика payload: `git archive` снова давал каталоги
   0775 — в r2-инструкции уже есть явный `sudo chmod -R go-w` (выполнен, prepare прошёл сразу).
2. `configured_strategy=seqovl` в карточке при off — дефолт engine_profile схемы (в TOML
   движок-ключей нет); strategy=null честно показывает «ничего не подтверждено».
3. В журнале остановки демона при apply виден SIGKILL child-процессу xray (потомок free-pool
   наблюдения) и строка «remains running after unit stopped» — это штатное управление
   детьми демона при рестарте, маршруты/правила не менялись; главный Xray PID не менялся.
4. `test_off_is_original_config_without_starting_anything` (новый в r2) — passed, зафиксирован
   отдельно по требованию ТЗ.
5. Прошлые payload/backup от 557e515 (`/opt/xgw/handoff|/var/lib/xgw/handoff/desync-batch1-557e…`)
   не удалялись и не переиспользовались — оставлены до закрытия приёмки по ТЗ.

## Final machine state

- Backend: **batch 1 установлен** (`4f53495`: config.py, managed.py, daemon.py, watch/panel.py,
  zapret2.py — заменены; watch/zapret2_control.py, desync/__init__.py, desync/schema.py —
  новые), SHA сверены с манифестом после отмены таймера.
- GUI: **installed overlay** — в установленном релизе 7c20f59 заменены vpn_ui/xgw/overview.py
  и src/xgw/gui/zapret2.py (тоже в манифесте, SHA сверены); реальное окно показывает LIVE-карточку.
- Worker / selected mode / engine: off/off, workers inactive — как до раунда; ни одного
  сетевого действия батч не выполнял.
- Config files: unchanged (SHA).
- Rollback timer/service: остановлены до срабатывания; service никогда не был active; backup
  (`/var/lib/xgw/handoff/desync-batch1-4f53…`, manifest 10 строк) и payload — оставлены для
  будущего отката.
- Publication commit: отчёт публикуется следующим коммитом ветки integration/zapret2-batch1.
