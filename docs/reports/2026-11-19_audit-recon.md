# ThinkCentre — рекон спорных выводов аудита XGW — 2026-11-19

- RESULT: **A1 PASS (панель: daemon_owns=true; status-listener отсутствует), A2 PASS
  (sysctl acct=0, be_liberal=0; FIB 4 строки согласованы), A3 PASS (13 шагов/180 с,
  max=p95=0.678 с, пропусков нет, wake_latency=NOT_MEASURED; TUN-события/ошибки
  восстановления в журнале только «xgwtun0 поднят» — service_race=INCONCLUSIVE),
  A4 PASS (все 6 FIB-строк expected=actual; контроли bypass_control=0,
  unmarked_other_uid=1), A5 PARTIAL→NOT_REPRODUCED_IN_THIS_CASE (close_control
  12/12 echo/FIN/final_ack, ошибок 0; close_xgw 12/12 echo/FIN но final_ack=0 —
  повторяемая потеря поздних ACK при здоровом контроле = дефект лабораторного пути;
  пакеты без UID: output all−uid = 72−60 / 132−60), A6 PASS (tun_absent
  created/usable/routes=true за 85 мс; tun_down created=false, usable/routes=true
  за 97 мс), ct-контроль PASS (acct=1: first_one=4 — отсечение ct packets>4 работает;
  acct=0: first_zero=8 — без учёта не отсекает; all_zero=all_one=8), A7 PASS
  (nfqws2 v1.0.7 038c97e — pin совпал; AUDIT_POS 2 3 2 2 true — ожидания сходятся;
  AUDIT_TLS nil string 677 — N=677>4; CUTOFF 45 EXCLUDED_COVERAGE / 0 INCLUDED;
  HTTP_IP_ID пуст — применимых строк нет), A8 PASS (13/13 контрактов: токены,
  одноразовый вход, откат ядер, чужие правила, возврат TUN, singbox-обход,
  Flowseal pin/separation)**. Машина не менялась: конфиги CONFIG_IDENTICAL,
  поколения и службы active, слушатели прежние; удалены только доверенные приборы
  из /run. Спорные выводы аудита: владение HTTP — у демона (не чужой процесс);
  ct packets — валидно и зависит от sysctl; «потеря ACK» — лабораторный артефакт;
  claims о смене guard-логики не воспроизводятся — все строки expected=actual.
- ОС: Ubuntu 24.04.5 LTS, ядро 7.0.0-43-generic, amd64. Приборы: `754d2e4…`
  (audit_host_observe.py + audit_kernel_lab.py, установлены 0500 root в /run,
  сверены с git, удалены после). Установленные модули XGW: zapret2.py и
  watch/panel.py = `3630b44`; net/nft.py, net/iprule.py, net/capture.py,
  watch/status_page.py = байты обеих ревизий (3630b44 == 46c69fd) — установленная
  база `3630b44`, `OTHER` не встречался. Время: UTC 13:18–13:38, 2026-11-19.
- Ограничение: A4/A5/A6 — изолированные veth/namespaces на том же ядре; синтетика
  не доказывает поведение процесса в интернете (синтетическая метка ≠ пакет из сети).
  A5 «отсутствие final_ack» по счётчикам не позволяет присвоить skb->sk конкретному
  владельцу.

## A1 — владельцы HTTP и полномочия (рабочая машина)

| Объект | Наблюдение |
| --- | --- |
| panel 8781 | listening=true, **daemon_owns=true** (сокет принадлежит MainPID XGW) |
| status page | listening=false, daemon_owns=null → **NOT_ACTIVE** |
| xgw.service | EUID=0, active, CapEff `0x30c0` (bounded net_admin+net_raw: true) |
| xgw-xray.service | EUID=997 (xray), active, CapEff `0x1400` |
| xgw-zapret2.service | EUID=0, active (в текущем off — не обрабатывает; LoadState loaded), CapEff `0x3000` |

## A2 — маршрутизация и ранние правила (рабочая машина)

- sysctl: nf_conntrack_acct=0, nf_conntrack_tcp_be_liberal=0.
- FIB: bypass→main/other, proxy→local/lo/100, proxy_extra→main/other,
  selected→main/other — все четыре согласованы; в `before_100_including_own`
  один pref 95 с селекторами fwmark/priority/src/table (свой, правил шлюза).
- ПравилаPrivate сохранены в $D; в отчёте только принадлежность/приоритет.

## A3 — шаги watchdog и контекст TUN (рабочая машина, 180 с)

- distinct_completed_steps=13, max=p95=0.678 с, missing=0, max_record_age_s=16.7.
- p95 на 13 шагах — описательная статистика окна (не СКО population).
- wake_latency=NOT_MEASURED (нет пар начало-событие/обработка на одном поколении).
- Журнал за 24 ч: 109 строк; все совпадения — «интерфейс xgwtun0 поднят, маршруты
  в него на месте» (восстановления TUN, пары старт/подтверждение); ошибок
  «правила не загружены»/«Control process exited» — 0. service_race=INCONCLUSIVE
  (нет отказов post-start в окне).

## A4 — метки и guard (изолированное ядро)

| Строка | expected | actual | Вывод |
| --- | --- | --- | --- |
| bypass_control | 0 | 0 | PASS |
| unmarked_other_uid | 1 | 1 | PASS (дельта ip.output.15=2 — только по чужому UID) |
| off_selected_copy | 1 | 1 | PASS |
| closed_selected_copy (допуск закрыт) | 1 | 1 | PASS (копия остановлена) |
| open_selected_copy (допуск открыт) | 0 | 0 | PASS (эхо проходит, inet.output.25=6) |
| open_selected_no_listener | 1 | 1 | PASS (без слушателя очереди — закрыто) |
| engine_copy | 0 | 0 | PASS |
| engine_no_listener | 0 | 0 | PASS (bypass с пустой очередью проходит) |
| engine_other_uid | 1 | 1 | PASS (ip.output.16=6) |

FIB: mark 0x1→audit-tun; 0x2, 0x20000001, 0x20000012, 0x10000000, 0x50000000→audit0 —
все expected=actual.

## A5 — закрытие сокета по UID (изолированное ядро)

| Окно | client_ok | echo | client_fin | final_ack | errors | all−uid |
| --- | --- | --- | --- | --- | --- | --- |
| close_control | 12/12 | 12 | 12 | **12** | 0 | 72−60 |
| close_xgw | 12/12 | 12 | 12 | **0** | 0 | 132−60 |

- Строгий контроль здоров: 12/12 эхо/FIN/final_ack, 0 ошибок.
- close_xgw: обмен полностью прошёл (echo 12/12), но финальные ACK не наблюдались
  в правилах с UID-совпадением — повторяемая потеря поздних ACK при исправном
  контроле = **дефект лабораторного пути**, не доказательство поведения XGW.
  NOT_REPRODUCED_IN_THIS_CASE; реальные RST/ретрансляции — вне этого опыта.
  Пакеты без UID-совпадения наблюдались (72−60=12 и 132−60=72), но по счётчикам
  невозможно присвоить skb->sk конкретному сокету.

## A6 — TUN (изолированное ядро, настоящие ensure-функции)

- tun_absent: created=true, usable=true, routes=true (85 мс).
- tun_down: created=false, usable=true, routes=true (97 мс) — устройство
  возвращается при наличии.
- service_race=INCONCLUSIVE (A3 — отказов не было).

## ct packets контроль (изолированное ядро, loopback UDP 8×2)

| Счётчик | acct=0 | acct=1 |
| --- | --- | --- |
| all_zero / all_one | 8 | 8 |
| first_zero (≤4) | **8** | **4** |

- all_zero=all_one=8 — контроль валиден. Отсечение ct packets>4 при acct=1
  подтверждено (first_one=4); при acct=0 выражение не отсекает (first_zero=8).
  Зависимость от sysctl подтверждена; рабочий шлюз: acct=0 (см. A2) — Engine-счётчики
  на этой машине без per-flow учёта.

## A7 — семантика установленного zapret2 и охват Flowseal

- Бинарник: v1.0.7 (038c97e…) — pin совпал, сравнение с другой сборкой не требуется.
- `AUDIT_POS 2 3 2 2 true` — resolve_pos: позиция 1→2, «2»→3, с zstr→2, sub-длина 2,
  «99»→nil — все ожидания сходятся.
- `AUDIT_TLS nil string 677` — TLSMod на 4 нулевых байтах → nil (некорректная
  структура — ожидаемо), на fake_default_tls → строка 677 байт (N>4 ✓). Сообщение
  о некорректной структуре при работающем положительном контроле — ожидаемо.
- CUTOFF: **45 EXCLUDED_COVERAGE, 0 INCLUDED** — ни одна применённая конфигурация
  не использует dpi-desync-cutoff; HTTP_IP_ID: [] — применимых HTTP-строк с
  ip-id=zero нет.
- Число стадий/инициализация не измеряют эффективность на YouTube.

## A8 — действующие контракты (фикстуры, 13/13 passed)

test_notify_page ×2 (токен/только чтение), test_panel ×2 (cookie-перенос,
одноразовый код), test_cores ×4 (откат/подмена/диагностика версий), test_net ×3
(чужие правила, возврат TUN), test_nft singbox-bypass, test_desync_flowseal
(pin/separation) — **все passed**, skip/fail/error нет; расхождений нет.
Проверка постоянной ссылки подтверждает наличие механизма; степень риска — вне
факта приёма запроса.

## Завершение

- before/after: службы xgw/xgw-xray active, слушатели прежние (panel daemon_owns,
  status не активен), конфиги CONFIG_IDENTICAL; таймеры: xgw-combined-day-rollback
  (до 20.11 17:35 МСК) и user-монитор xgw-combined-monitor-1795041850 — **на месте,
  работают** (естественное течение суток основной приёмки), новых/исчезнувших нет.
- Установленные файлы приложения не менялись; удалены только доверенные копии
  приборов из /run; смена поколения — не зафиксирована.
- Приватные артефакты (rules, journal, kernel.err, contracts.log) остаются в
  локальном каталоге опыта (0700), вне Git.
- Publication commit: `добавляется после push`.
