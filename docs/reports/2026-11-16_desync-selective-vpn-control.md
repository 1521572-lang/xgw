# Ubuntu 24.04 — Selective: сохранение vpn_control в окне повтора — 2026-11-16

- RESULT: **PASS** — новый слой `e2b11ad` (2 файла) проверен живым циклом Selective: после
  SIGKILL рабочего PID контроллер выдал `fallback / worker_down` с
  **`vpn_control=pass, vpn_control_reason=ok`** и штампом `vpn_control_at`; результат
  **сохранялся неизменным во всех 41 снимках статуса (~323 с окна повтора, ≥3 разных
  `updated` — с запасом)**, свежий клиентский запрос браузера прошёл через VPN-участника
  (дельта счётчиков proxy-outbound), панельный `zapret2.evidence` совпал с сырым статусом,
  при переходе в off и при новой попытке поля корректно сбрасываются. Слой оставлен
  установленным (restore `accept`), конфиги владельца byte-identical, off/off.
- CODE: `e2b11ad13543aa4af4c4688ab62482f87c025d14`; BASE `7fa7ffb` (мой отчёт телеметрии/
  Compare — предок CODE, ветка не переезжала); установленная база на старте — T04-слой
  `ad81542`+hotfix (applier `ecac82aa…`), заменяемые файлы (`zapret2.py`,
  `watch/zapret2_control.py`) совпали с BASE побайтово (`prepare: complete`, `old_sha`
  манифеста `d563c4f2…`/`a8cecc3a…` = BASE).
- Ubuntu 24.04.5 / kernel 7.0.0-43; демон PID 1863797 (python3.12), ExecStart
  `/usr/local/bin/xgw`, пакет `/opt/xgw/lib/xgw` — как в командах ТЗ.
- pytest `--portable` (test_zapret2, test_zapret2_panel, test_desync_standalone,
  test_desync_schema) в существующем dev-venv: **111 passed, 2.50s**, падений нет.
- Предпосылки PASS проверены до установки: прикладной конфиг содержит `burstObservatory`
  (1 observer) и 75 probe-inbound (base 20001); все 5 proxy-участников `alive=true` по
  observatory; `probe_enabled` — производное от mode (selective включит сам).
- Слой: манифест 2/2 (`new_sha` `5f604e2b…`/`1c1bdaa1…` = CODE, сверено на диске), конфиги
  после apply byte-identical (`89bf2a67…`/`33916cb5…` OK), restore.sh + таймер 25 м заряжены
  ДО сетевых шагов (`network-test-started`), очередь пуста, обе worker-службы inactive.

## Пре-чек и подготовка

- URL из ТЗ (`ru.wikipedia.org/wiki/Россия`, ASCII-процентное кодирование) через штатный
  VPN: **200 / 3,270,734 байт / 0 редиректов / 1.0 с** (≥16 KiB, без авторизации).
- Очередь 201 свободна (proc-таблица пуста), `nf_conntrack_acct=0`, TSO/GSO/GRO on,
  VPN-выход жив (ipify 200), карточка off/fresh/schema=1.
- Collector `status.jsonl` запущен отдельным процессом **до** переключения политики
  (10 мин, шаг 1 с, stamp `updated` + state/reason/gate_closed/vpn_control*).

## Цикл Selective (21:40:52–21:53Z UTC)

Замечание честно: первая попытка `set_desync` в моём скрипте положила `queue_num` в группу
`selected` — схема отвергла (`PolicyError: invalid selected`), политика не применилась
невалидной; исправлено на `runtime.queue_num=201` и применено чисто (21:40:52Z).

Политика: `mode=selective, strategy=multisplit, queue=201, retry=300,
domains=[full:ru.wikipedia.org], probe_urls=[URL из ТЗ], engine=off`. Дальнейшая
state-машина по collector (штампы `updated`, UTC):

| UTC | state / reason | Свидетельство |
|---|---|---|
| 21:41:20 | preparing / probe_inbound | контроллер поднял probe-канал |
| 21:41:33 | preparing / nfqueue | worker стартует, сборка конфига в фоне |
| 21:41:45 | **active / probes_ok** | прямая проба прошла: worker PID 1895671, очередь `201 peer=1895671`, резервация `{generation:1, unit:xgw-zapret2.service, queue:201}`, valid_until |
| 21:42:44 | — (SIGKILL main) | `systemctl kill --kill-whom=main --signal=SIGKILL xgw-zapret2.service` — только экспериментальный юнит |
| t+2 c | очередь освобождена | proc-таблица пуста при первом опросе, юнит inactive; статус ещё показывал активный снимок (тик watchdog не наступил) — честно зафиксировано |
| 21:43:01.7 | **fallback / worker_down** | `gate_closed=true`, **`vpn_control=pass`, `vpn_control_reason=ok`, `vpn_control_at=1794778981.6987934`** — служебная проба через VPN-участника прошла с первого тика |

### Окно сохранения (ключевая проверка ТЗ)

- **41 снимок** с разными `updated` в диапазоне 1794778982→1794779305 (**~323 с**, до
  следующей попытки) — во **всех** поля идентичны: `state=fallback, reason=worker_down,
  gate_closed=true, vpn_control=pass, vpn_control_reason=ok, vpn_control_at=…981.6987934`.
  Требование «минимум три разных `updated`» перекрыто на порядок.
- Параллельно проверено состояние: воркер inactive, очередь пуста, резервация None; в
  прикладном Xray осталось ровно одно zapret2-правило — **probe-канал**
  (`inboundTag [xgw-zapret2-probe] → outboundTag xgw-zapret2`, домен wikipedia) —
  клиентское правило снято. nft: элементы marks/захвата исчезли из дифа, queue-правил нет.
- **Новый клиентский запрос** (обычный Chrome 157, свежий профиль, CDP-навигация на URL,
  QUIC off, без обхода системной маршрутизации): `loadEventFired` за 8.6 с, title 18
  символов («Россия — Википедия»), readyState complete, `transferSize=498,262`.
  Дельта счётчиков Xray по тегам: **proxy-np-8e27 down +238,504 / up +499,524** — поток
  через VPN-участника; **xgw-zapret2 без дельты** (249,029 — const) — через обход не ходил.
- **Панельный API `/api/state`**: `evidence = {transport: unknown, playback: not_tested,
  vpn_control: "pass", vpn_control_reason: "ok", vpn_control_at: 1794778981.6987934}` —
  **побайтово совпадает с сырым статусом** (все три новых поля отдаются карточкой).
- Новая попытка (retry 300 c): 21:48:33 `preparing/nfqueue` → 21:49:12 `active/probes_ok`
  — при старте новой попытки поля сброшены (результат принадлежит окну — semantics из
  комментария кода подтверждена живьём).

## Исчезновение доказательств при off

- 21:52:36Z `mode=off` через `managed.set_desync`: raw-статус `off/off`, все три поля
  `null`; воркер inactive, очередь 0. Карточка: `state=off, mode=off, evidence
  {vpn_control: "not_run", reason: null, at: null}` — поля исчезли и из API.

## Возврат

- 21:53:23Z `restore.sh … accept`: panel восстановлен, apply — «изменений нет»;
  `sha256sum -c` — конфиги **byte-identical** (`89bf2a67…`/`33916cb5…` OK), cmp с
  `panel.before` — идентичен; карточка off/off fresh=True matched=True.
- Сеть/машина: обе worker-службы inactive, очередь пуста, acct=0, offload on/on/on,
  VPN-выход жив (ipify 200), panel API 200, окно владельца GUI открыто (тот же PID
  1243747). Диф nft до/после раунда: только счётчики трафика и динамические элементы
  захвата (структура и число правил не менялись, queue-правил 0).
- Таймер `xgw-desync-vpn-control-rollback` остановлен после подтверждения (до
  срабатывания; дедлайн был 22:05:11 UTC).
- **Слой оставлен установленным** (accept): `zapret2.py`/`zapret2_control.py` —
  `new_sha` манифеста на диске; поверх T04-слоя (12/12 с хотфиксом applier).
- Приватное на стенде: статус-ряды (`status.jsonl`), счётчики, снимки nft, панель.before
  в `/var/lib/xgw/handoff/desync-vpn-control-…` (0700). URL — из самого ТЗ; токенов,
  подписок, адресов серверов в отчёте нет.
- Итоговый режим шлюза: **off/off** (VPN-маршрут владелеца), слои T04 + vpn-control
  установлены.

## Вывод

Критерий PASS ТЗ выполнен: `vpn_control=pass` при свежем `fallback` после SIGKILL рабочего
PID, с сохранением `vpn_control/vpn_control_reason/vpn_control_at` на протяжении всего окна
повтора и точным зеркалом в панельном `zapret2.evidence`. Причины-коды пропуска из
`_fallback_vpn_control` в этом окружении не понадобились (все условия были живы:
observatory-alive участник, probe-порт, credentials, бюджет); механизм reason-кодов
гарантирован unit-тестами набора (111 passed).
- Publication commit: добавить после push.
