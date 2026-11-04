# Отчёт: XGW wave3p — один запрос SB-1 с сохранённой идентичностью

Дата/время MSK: 2026-11-02, 20:13:49–20:17+03. Модель GLM-5.3-Flash (ZCode), терминал
владельца; OS Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc Yak #3) (S1.3,
записано буквально; не обновлялся). Tested HEAD f9ed31f966d2e2dc337096e450c537702d4cb489
/ tree 4e3e39d077d613b92bd9ea35a336d13f12cf5ac6. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; изменён только тестовый пакет (новый wave3_single_bridge.py);
продукт не устанавливался и не менялся.
Installed4 equality (install/sysctl/diag/nft): True ×4 (INSTALLED_SOURCE_OK).
4 frozen SHA/modes (SINGLE_PROBE_FROZEN; /run/xgw-w3p 0700, файлы root600):
wave3_single_bridge.py 66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93
(единственный запускаемый CLI);
wave3_bridge_diagnostic.py e77d441e1e5b2c97f3dff5d65ac7483b015574fba0e8fe830c765b22cd87b068,
wave3_bridge_probe.py 2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef,
wave3_on_observer.py 0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46 —
только библиотеки, их CLI не запускались.
Начальный: HEALTHY с 02.11 19:56 (таймштамп демона обновился относительно прежних
прогонов — факт записан; вероятно, владелец перезапускал VPN между прогонами 16:12→20:13;
режим on); перехват ВКЛЮЧЁН; pool «выключен»; Xray 26.10.31 / sing-box 1.14.4; Tailscale
route=vpn не менялся. Конечные: те же HEALTHY/on/pool; связь владельца и модели живая.

## Исполнение

Первый STOP: D1.1 — **STOP_SINGLE_PROBE (command rc 3)** — сбор не подтвердился ДО
запроса; отклонений/действий владельца в прогоне не было. Run command rc: 3.
Collector marker: STOP_SINGLE_PROBE. Show rc: 0 (файл прочитан; «код 0» = чтение, не
успех теста). INTERRUPTED_UNKNOWN — нет (started/summary согласованы; завершение
управляемое). UNKNOWN: точное место ValueError внутри сборщика (raw не вскрывался —
запрещено ТЗ; печатался только collection_error_class).
request_count = **0** — запрос НЕ начинался (не «started без attempt»: запуск запроса
не достигнут). private_plan_persisted_before_request: UNKNOWN/NOT_RUN — план либо не
создан, либо создание не подтверждено; каталог/файлы не проверялись вручную и не
пересоздавались (запрещено).
historical_mapping_basis N→O: FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN (без изменения —
прошлое временное основание не превращено в доказательство).
current_config_matches_O_digest (точный O→P): UNKNOWN — сверка не завершилась (сбор
остановился на ValueError до выдачи результата). Цель: планировалась первая допустимая
из ТЕКУЩЕГО config.probe; старая цель N остаётся неизвестной.
listener_owned_before/after: NOT_RUN (до запроса не дошло). current config безопасные
attrs: NOT_RUN в этом прогоне (в wave3o — vless/443/TLS+reality+uTLS/vision, без
mux/detour/bind; идентичны SB-2; повтор не выполнялся).

## Единственный новый запрос

Не выполнялся: outcome/attempt отсутствуют, curl_rc/http_status/bytes/seconds/
tls_verify_result/content_encoding_identity/body_ok — NOT_RUN; error fields — NOT_RUN.
Нет fallback/повторов/других узлов/сканов. **N остаётся partial (1/2 BODY_OK)**;
этот прогон не является ни отрицательным результатом SB-1, ни его реабилитацией —
измерение не состоялось. Если бы request_count был 1 без attempt — исход UNKNOWN;
этот случай иной: request_count=0.

## Journal

request_window: не формировался (запрос не выполнялся). Journal нового окна не
запрашивался: query_ok/rows/categories/literal counts/message levels — NOT_RUN.
Различия «общие слова vs литералы vs приоритет vs текстовый уровень» не измерялись.

## Сохранение контекста

before и after (оба сняты): capture true до/после; guard query=ok,
postrouting/10/forward/drop=5/reject=0 в обоих; службы active ×6; sing-box
nonprivileged/uid-gid match/forbidden groups absent/caps 0×5/NoNewPrivs; DAC expected ×4;
pool_mode=off, router ap, tailscale_route=vpn, derp=true; interfaces distinct, carrier 1/1.
on_context_preserved=true; settings_unchanged=true ×3; bridge_config_unchanged=true;
same_singbox_process=true; same_boot=true; service_pid_same=true ×6;
pin_record_readable_before_after=true/true; pin_record_unchanged=true;
all_context_checks_ok=true. collection_error_class=ValueError;
after_read_error_class — отсутствует. Recovery: сетевых/служебных изменений не было;
off-rollback не запускался (не нужен — сетевое состояние не менялось).

## Вывод

Наблюдение: сборщик P остановился с ValueError до выполнения единственного запроса
(request_count=0); контекст полностью сохранён. Гипотеза о месте сбоя НЕ выдвигается
вслепую: без вскрытия raw известен только класс ошибки; допустимые кандидаты — валидация
исторических материалов (mapping-private из O, старые N summary/helper) или plan-этап;
проверка требует отдельного узкого шага с диагностированием, что этому ТЗ запрещено
(«не чинить», «не повторять run», «не пересоздавать mapping»). Недостающий факт для
следующего шага: точная точка ValueError (например, через локальный read-only разбор
форм файлов теста отдельным решением разработчика — повтор run в этом прогоне запрещён).
Никакой автоматической причины SB-1 из этого прогона не следует: отказ SB-1 в N остаётся
с неизвестной причиной; положительный результат SB-2 (N) и наблюдения O остаются в силе
и не пересматриваются.
SB2 positive / M 6/6 / L 608 с / J short-host+loaded — приняты и не повторялись.
N partial / full wave3 / D1-on / E4 / scoped faults / LAN UDP / IPv6 / DNS / all
Tailscale paths — остаются открытыми. Это не указание на неисправность рабочей LAN.

Публикация: только этот Markdown; private план/root файлы/raw logs вне Git. Реальный
путь docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3p-2026-11-02.md, коммит «Отчёт: XGW 0.2.0,
wave3p — один запрос SB-1 с сохранённой идентичностью», push в freepool
(REPORT_PUBLISHED в финальном сообщении). Рабочий режим в конце: HEALTHY/on — сохранён.
