# TEST-REPORT-REAL-MACHINE-0.2.0-desync-nfqws2-r3-2026-11-14

Дата: 2026-11-14; прогон 09:12–10:00 UTC. CODE a99cd41ae606be0d6907151885779b911cfd9e01,
BASE 9b58725354799a6b91c7341c41a311371bdfa4d8 (= установленный код по отчёту b6421a5), план
62ec6da, ветка gui-light. Исполнитель GLM-5.3-Flash; Ubuntu 26.04 amd64; Python 3.12.3; Xray
26.10.21; sing-box 0.1.13; nfqws2 v1.0.7. Root — один systemd-run --system юнит с FIFO-очередью,
остановлен после восстановления. Согласия r2 действовали (движок, профили/offload, установка
исправления); новых опасных действий не было.

## Итог: **PARTIAL** — START и hostfakesplit PASS; disorder-badseq FAIL (новый дефект offload)

Первый FAIL: §5, смена на disorder-badseq — `Offload.disable()` падает IndexError на строке
ethtool `Features for <dev>:` (пустое значение) → исключение выходит из `start()` (IndexError
не входит в except шага) → шаг watchdog крашится целиком, disorder не может стартовать никогда.
Зависимые этапы остановлены по плану. Деградации трафика нет: VPN/HTTPS работали во всех фазах.

## §2–3: контроль — PASS

Baseline: HEALTHY, capture on, selective off, engine-ключа нет, очередей нет, acct=0, diag
«OK — 33, WARN — 0, FAIL — 0»; установленные cli.py/daemon.py/nfqws2.py побайтово равны BASE
(SHA-256 сверены), права root 0644. Тесты §3: **23 passed** (11,8 с), включая stop-during-poll
[auto]/[off] ~1,2–1,5 с и новые тесты reload/failed_reload/run_once.

## §4: установка трёх модулей и старт — PASS

cli.py/daemon.py/nfqws2.py из CODE установлены root:root 0644 (SHA-256 сверены с CODE:
bd2378ef…, 4911fdef…, 31a09bdf…). Перезапуск только xgw.service: rc0, **0,41 с**, PID Xray
262461 сохранён, HEALTHY, HTTPS 200, nfqws2 не запущен. Секция zapret2 создана
(mode=off, engine=auto, seqovl, queue=200), acct=1 временно. Старт движка: **ACTIVE через 4 с**
(норма ≤90) — одновременно active unit, queue 200 занята, профиль seqovl, правила цепи
nfq_output корректны (bypass, ct packets ≤8/≤4, анти-петля, skuid 992, reserved-исключения,
policy accept), аргументы worker-а точные (`multisplit:pos=2,sniext+1:seqovl=679`, fwmark,
оба lua-init, UDP fake).

## §5: профили — PASS на seqovl/hostfakesplit, **FAIL на disorder-badseq**

- seqovl → hostfakesplit: перечитывание заняло ~25 с, затем **один** рестарт unit с точными
  аргументами hostfakesplit (`fake:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=…:tcp_ts=+100`,
  `hostfakesplit:host=www.google.com:altorder=1:tcp_ts=+100`) — worker проработал 57 с до
  следующей смены без перезапусков; HTTPS 200; PID Xray не менялся. Живая правка исполнителя
  (замер P1 до рестарта) дала ложный «PID изменился» — по журналу рестарт ровно один.
- disorder-badseq: демоном рабочий остановлен, но новый не запущен — краш шага watchdog:
  `_enabled()` → IndexError на строке `Features for enp3s0f0:` (пустое значение; строка есть в
  каждом выводе ethtool -k). IndexError не перехватывается в step (ловятся OSError/ValueError/
  CommandError), run loop перезапускается и падает снова — worker при disorder не живёт никогда,
  offload не отключается. Вне шага трогаемого трафика нет; fail-open подтвердился.
- touch mtime при неработающем worker-е: «настройки перечитаны» зафиксированы, но содержательный
  тест RELOAD_SAME (PID сохраняется, offload остаётся отключённым) неинтерпретируем — NOT_RUN.
- Возврат к seqovl не выполнялся осмысленно (worker не поднимался при disorder) — зависимая
  сверка offload NOT_RUN.

## §6: восстановление и недоступные пути

- WORKER_RECOVERY (остановка unit при устойчивом active): NOT_RUN — устойчивого active на
  disorder нет из-за FAIL выше; на seqovl/hostfakesplit остановку не делали, чтобы не рисковать
  сценарием до окончания приёмки.
- PATH_ACCESS: **PASS**. binary-копия в /var/lib/xgw/r3test (0755 root, без Lua) + lua_dir в
  0700-каталоге исполнителя (недоступность подтверждена stat'ом) → перечитывание →
  `{'state': 'off', 'reason': 'not_found'}` — **без traceback и без сбоя шага watchdog** (дефект
  r2 с PermissionError исправлен `_is_file()`); HEALTHY по факту шага. Возврат путей, затем off.

## §7: VIDEO_DIRECT NOT_RUN (согласованного direct-пути YouTube нет, маршруты без поручения не
добавляются). Восстановление: binary/lua_dir удалены, конфиг **байтово идентичен** исходному,
acct=0, таблицы nft — тот же состав (xgw_acct пересоздан демоном, отличен только порядок строк в
list tables), по плану при FAIL **три модуля возвращены к BASE 9b58725** и перезапущен только
демон (nfqws2.py SHA e4ed4feb… = BASE), diag «OK — 33, WARN — 0, FAIL — 0», HEALTHY, capture on,
selective off, PID Xray 262461, HTTPS 200, тестовые файлы удалены. Наблюдение вне прогона:
DEGRADED «часть серверов недоступна — замена на запасные» в середине фазы — штатная ротация
линии дня (engine off, worker не жил), к прогону отношения не имеет; к концу HEALTHY.

## Сводка вердиктов

TESTS 23 PASS; INSTALL PASS; START PASS (4 с); PROFILE_SWITCH **FAIL** (disorder: IndexError в
offload.disable → краш шага watchdog; seqovl/hostfakesplit PASS); RELOAD_SAME NOT_RUN; OFFLOAD
NOT_RUN (worker при disorder не жил); WORKER_RECOVERY NOT_RUN; PATH_ACCESS PASS; VIDEO_DIRECT
NOT_RUN; RESTORE PASS. Оставшийся код на машине: BASE 9b58725 (модули откатаны), конфиг исходный.

## Передать разработчику

1. Точный дефект: `Offload._enabled()` делает `value.split(":",1)[-1].strip().split()[0]` на
   каждой строке ethtool -k с двоеточием; заголовок `Features for <dev>:` имеет пустое значение
   → IndexError; `start()` вызывает `offload.disable()` только для disorder-badseq (этим
   объясняется, почему seqovl/hostfakesplit стартуют, а disorder — нет); IndexError не входит в
   набор исключений, перехватываемых в `step` → падает весь шаг watchdog. Предложение: пропускать
   строки без значения, а `disable()`/`restore()` оборачивать, чтобы сбой offload не мешал
   старту worker-а.
2. Исправление a99cd41 работает по своему назначению: рестарт run loop больше не глушит worker
   заново (в r2 flap был бесконечным, в r3 hostfakesplit стартовал одним рестартом и жил), а
   недоступные пути дают чистый not_found.

Отчёт без снимков, IP/доменов, имён серверов/устройств и URL; приватные журналы — в каталоге
прогона (mode 0700), worktree CODE сохранён до разбора отчёта.
