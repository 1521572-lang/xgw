# Ubuntu 24.04 — T06: контроль комплекта nfqws2 и загрузки Lua — 2026-11-16

- RESULT: **PASS с подтверждённым хотфиксом** — изолированный повтор AutoTTL-лаборатории на
  новом коде захватов чист (6/6 фаз byte-exact, ни одного остатка процессов/namespace/Lua),
  контроль `warm_off` впервые дан чисто: Lua на общем воркере выдал кэш-значение
  `track_ttl=62` при реальном входящем TTL 58 — происхождение TTL из IP-кэша подтверждено
  независимо. Preflight проверен на все три уровня: разбор аргументов, инициализация Lua и
  обе положительные ветви (bundle.json / version-string), три негатива дали точные коды.
  **Найдена и исправлена интеграционная несовместимость**: на этом стенде `/opt/xgw/zapret2/1.0.7`
  — symlink; лексическое сравнение путей в preflight отвергало штатный комплект
  (`bundle_mismatch`) и **не давало воркерам стартовать** — воспроизведено живым включением
  Standalone, исправлено точечным resolve-aware хотфиксом (2 строки), воркеры обоих режимов
  после него запускаются и обрабатывают трафик (YouTube 135 c 720p без пауз; Engine auto —
  второй воркер на очереди 200). Слой оставлен установленным (accept) с хотфиксом в
  манифесте.
- CODE: `32645a75633a6d5e3f15dad99579328b4d53f7e2`; BASE `6de8375` (мой отчёт T05-replies —
  предок). pytest `--portable` (zapret2, schema, panel, standalone, worker): **122 passed,
  2.37s**; nfqws2+bundle: **35/36** — единственный FAIL
  `test_nfqws2.py::EngineTests::test_failed_preflight_does_not_stop_service`
  **воспроизведён на чистой BASE `6de8375`** (pre-existing, триаж T03/T04; assert не
  ослаблялся).
- Установка: `--preflight-t06`, манифест 4/4 (`desync/preflight.py 4a0c5de3…hotfix`,
  `nfqws2.py 980120be…`, `zapret2.py 277cb937…`, `watch/zapret2_control.py 063ae4d4…`),
  конфиги владельца byte-identical до/после (`89bf2a67…`/`33916cb5…`), таймер 45 м
  (остановлен после сверки, не сработал), restore accept.

## 1. Изолированный повтор T05-лаборатории

- Новый механизм захватов (`desync_lab_capture.py`, AF_PACKET, неблокирующий select,
  ready/stop-файлы, лимит 20 c) — **ни одного остатка**: процессов захвата 0, namespaces
  `xgwttl-*` 0, временный Lua в `/run` удалён скриптом. Прежние pcaps не тронуты.
  Три RTNETLINK-строки — прежняя диагностика `ss` в server-namespace, нефатальна.
- Все 6 фаз — **HTTPS body matched (byte-exact)**. Прибор Lua от того же worker'а:

| Фаза | SYN/ACK TTL (pcap, чистые захваты) | Lua `track_ttl`/`predicted` | Вывод |
|---|---|---|---|
| md5 | 62 | 62 / 1 | baseline MD5 |
| cold_off | 62 | **0 / 0** | SYN/ACK мимо очереди, TTL в Lua нет |
| cold_on | 62 | 62 / 1 | свежий worker, fake TTL 1 |
| warm_off | **58** (сервер 60) | **62 / 1** (hello=2, общий лог worker'а) | **IP-кэш подтверждён**: Lua 62 при реальном 58 |
| changed_ttl | 58 | 58 / **5** | пересчёт новым worker'ом |
| early_reply8 | 58 | 58 / 5 | окно: правило `ct reply packets 2-9` — **8 пакетов / 10,988 B**, передача целая |

- `warm_off` — впервые чисто: пустая входная цепочка подтверждена снимком `nft -j` (нет
  правил), отдельные client/server pcaps одной фазы, реальный TTL SYN/ACK 58, Lua-запись от
  того же worker'а (файл общего воркера `cold_on.worker.log`, hello=2; второй CH-полёт в
  pcaps самой cold_on отсутствует — все клиентские полёты в пределах 2.6 мс, значит hello=2
  — это соединение warm_off). Сравнение с прогоном T05-ч2 (Lua 62/1 при реальном 58) —
  вывод одинаковый; расхождение в именовании артефакта того прогона отмечено, на вывод не
  влияет.
- Доставка fake: cold_on — fake TTL 1 не дошёл (0 MD5-строк от порта на сервере);
  changed_ttl — fake TTL 5 **дошёл** (2 сегмента TTL 3 с MD5-опцией) — граница эвристики
  подтверждена повторно на чистых захватах.
- tcpdump предыдущего SYNACK-раунда (PID 1935908, enp3s0f0): жив, состояние S (poll),
  **SIGTERM и SIGKILL от root → EPERM** (ядро/LSM `lockdown`; CapEff=0, Uid 109); файл
  растёт ~34 КБ/с (за 10 c +339 968 B). По ТЗ зафиксировано; нового tcpdump на WAN не
  запускалось (лабораторные захваты — AF_PACKET в namespace).

## 2. Preflight без запуска очереди

- **Положительные ветви** (на доверенной копии комплекта, root-owned, в версионном макете
  `ROOT/1.0.7/{nfqws2,bundle.json,lua/}`; реальный argv из builder'а с подменой путей):
  - manifest branch (bundle.json с SHA): **parse=ok lua_init=ok**;
  - version-string branch (bundle.json убран): строка `v1.0.7 (038c97e5…) lua_compat_ver 6`
    совпала с pin — **parse=ok lua_init=ok**.
- **Негативы** — точные коды: изменённый Lua → **`bundle_mismatch`**; неизвестный флаг →
  **`bad_worker_options`**; `--lua-init=error('xgw_t06_control')` → **`lua_init_failed`**
  (классификация pinned nfqws2 соответствует ожиданиям кода). Очередь и PID демона
  до/после не изменились (0 / тот же MainPID).
- **Две находки окружения**:
  1. **F1 (интеграционный дефект, см. хотфикс ниже)**: `/opt/xgw/zapret2/1.0.7` на стенде —
     symlink на `/opt/zapret2/1.0.7` (раскладка администратора с r1). `trusted_file`
     возвращает **resolved** реальный путь, а проверки `_verify_managed_binary` и Lua-ветви
     сравнивают его с лексическим `MANAGED_ROOT/VERSION/…` — неравенство всегда →
     `bundle_mismatch` на штатном комплекте; version-string ветвь для managed-путей
     недостижима. На stdout-тестах разработчика (реальные каталоги, без symlink) не
     воспроизводится.
  2. `/run` смонтирован **noexec** — бинарник из /run исполнить нельзя (эксперимент дал
     `bad_worker_options` именно по этой причине); Lua в /run допустим, но managed-макет
     требует единый корень → доверенная копия размещена в `/opt/xgw/handoff/xgw-t06-copy`
     (root-owned, 0755), удалена по завершении.

## 3. Живые проверки двух воркеров

- **Воспроизведение F1 до хотфикса**: установка слоя → Standalone (YouTube-список,
  hostfakesplit_md5) → `blocked / bundle_mismatch` на t+45 c, воркер не стартовал — живое
  подтверждение интеграционного дефекта (не регрессия трафика, а отказ preflight).
- **Хотфикс** (точечный, `src/xgw/desync/preflight.py`, 2 строки, обе стороны сравнения
  через `.resolve()`; все digest-проверки и trust-проверки сохранены без ослабления):
  `new_sha` preflight.py в манифесте обновлён, ряд помечен `hotfix`. После правки и рестарта
  демона — **Standalone активен сразу** (`active/worker_ready`), воркер 2049062.
- **Standalone (контроль запуска и трафика)**: PID 2049062, очередь `201 peer=2049062`,
  netlink Eth=12 owner ✓; обычный Chrome 157 — **135 c YouTube 720p без пауз** (10 сэмплов,
  медиа-время = стене, readyState=4), **`xgw-zapret2` +45.4 МБ** свежей передачи (0→45.4 МБ),
  очередь 15 502 пакетов, drops 0/0.
- **Engine auto seqovl (короткое окно)**: после off и штатного восстановления VPN (мосты
  ~72 c, ipify 200) — **второй воркер `xgw-nfqws2` стартовал на t+5 c** (PID 2053313),
  очередь **200 peer=2053313**, netlink Eth=12 owner ✓; новое соединение обработано
  (ya.ru 302 / gnu 200; счётчик очереди 346→372). Очереди 200/201 не пересекались.
- **Три уровня исходов**: разбор аргументов — ok на обеих ветвях и обоих воркерах;
  инициализация Lua — ok (этап `--intercept=0`; негатив дал точный `lua_init_failed`);
  реальный трафик — обработан обоими воркерами (standalone-медиа и engine-соединения).
  Различия режимов: standalone — очередь 201, selected-путь; engine — очередь 200
  (engine_queue), профиль seqovl. `zapret-auto.lua` в комплект не добавлялся (по ТЗ).
- Возврат: engine off → воркеры inactive, очередь пуста → restore **accept** 00:13:12Z —
  panel byte-identical, apply «изменений нет», конфиги OK.
- Финальная сверка: off/off, обе worker-службы inactive, очередь пуста, offload on/on/on,
  VPN-выход 200, panel 200, окно владельца открыто (PID 1243747). **acct вернул 0** —
  лабораторный `sysctl nf_conntrack_acct` оказался глобальным на этом ядре (не
  netns-local), замечено по снимку до/после и возвращён вручную; для следующих лабораторий
  стоит вернуть значение в скрипте. Таймер остановлен. Временные объекты раунда (копии
  комплекта, argv-файлы) удалены.
- **Слой T06 (4 файла) оставлен установленным с хотфиксом preflight** поверх
  T04+vpn-control+synack+replies; политика off.

## Хотфикс (точный путь)

`src/xgw/desync/preflight.py`: строки сравнения `path != MANAGED_ROOT / VERSION / …` в
`_verify_managed_binary` и Lua-ветви `prepare` заменены на сравнение с
`(MANAGED_ROOT / VERSION / …).resolve()` — корректно для symlink-раскладки managed-корня
(этот стенд), все trust/digest-проверки без изменений. Включён в отчётный коммит точным
путём и в манифест слоя (`hotfix`).
- Publication commit: добавить после push.
