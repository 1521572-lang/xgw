# ThinkCentre · отдельный HTTP-процесс для статуса zapret2 (P2.2) — 2026-11-21

- RESULT: **ПОЛНЫЙ УСПЕХ, шлюз не тронут (GATEWAY_UNCHANGED)**.
  Контрактные тесты: **95 passed / 0 failed / 0 skipped**. Живой прогон
  отдельного HTTP-процесса под непривилегированным UID: сокет IPC root
  0660; токен установленной панели этому UID **недоступен**
  (http_panel_token_denied); профиль изоляции: все пять масок
  capabilities нулевые, NoNewPrivs=1; читаемость файлов — config=false,
  snapshot=true. Единственный маршрут GET/HEAD `/api/zapret2/status`:
  401 без ключа/неверный/повторённый, 403 чужой Origin и повторённый
  Host, 405 POST, 404 `/api/state` — отклонённые запросы до бэкенда не
  доходят; авторизованный GET — 200 и пять полей, **совпавших со
  штатной панелью** (ISOLATED_HTTP_STATUS_MATCH); HEAD — пустое тело;
  при отказе IPC — 503, после восстановления — 200. Очистка и финал:
  порт/процесс/сокет/каталог удалены, обе службы active, PID и три
  контрольных файла совпали, off/off fresh/matched, HTTPS 200.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; кандидат `b686169…`
  (SHA инструмента); только временные файлы, сокет и loopback-порт,
  установки не было.

## §1 База и контракты

- PINNED `b68616921658ccbac377de5bae96dcfbd26a4d90`; baseline:
  off/off fresh/matched, HTTPS 200, контрольные SHA зафиксированы.
- **CONTRACT_TESTS_RC 0** — 95 passed / 0 failed / 0 skipped за 66с.

## §2 Изоляция HTTP-процесса

| Проверка | Итог |
| --- | --- |
| socket_permissions (IPC root 0660) | OK |
| http_privileges (caps 5×0, NoNewPrivs=1) | OK |
| http_panel_token_denied (токен панели недоступен UID) | OK |
| http_file_readability | **config=false, snapshot=true** — профиль изоляции: конфиг не читается, рабочий снимок читается |

- HTTP обслуживается UID **без дополнительных групп**; ключ прогона
  передаётся через stdin (в отчёт и чат не включён).

## §3 Маршрут GET/HEAD /api/zapret2/status

| Запрос | Итог |
| --- | --- |
| без ключа / неверный ключ / повторённый заголовок | 401 ×3 (http_anonymous, http_wrong_key, http_duplicate_authorization) |
| чужой Origin / повторённый Host | 403 ×2 (http_other_origin, http_duplicate_host) |
| POST | 405 (http_post) |
| `/api/state` | 404 (http_only_read_route — единственный маршрут) |
| **авторизованный GET** | **200 + пять полей** (mode/engine_mode/state/fresh/policy_matched) |
| **ISOLATED_HTTP_STATUS_MATCH** | поля совпали со штатной панелью байт-в-байт |
| http_head | 200, пустое тело |
| Отклонённые запросы | до бэкенда не доходят |

## §4 Отказоустойчивость и очистка

- **http_unavailable** — 503 при недоступном IPC; **http_recovered** —
  200 с прежней карточкой после восстановления.
- http_cleanup / socket_cleanup / TOOLS_REMOVED — порт закрыт, процесс,
  сокет и root-каталог удалены.
- **GATEWAY_UNCHANGED** — обе службы active, PID и три контрольных файла
  до/после совпали, off/off fresh/matched, HTTPS 200.

## Наблюдения для Codex

1. **P2.2 принят целиком с первого прогона**: изоляция (caps=0,
   NoNewPrivs, токен недоступен, конфиг нечитаем) подтверждена живым
   процессом; протокол ключа/Origin/Host и одиночный маршрут работают;
   восстановление после отказа IPC — 503→200.
2. Пара P2.1→P2.2 образует завершённый read-only путь «IPC-сокет →
   отдельный HTTP-UID → пять полей» с проверенным профилем изоляции
   (config=false, snapshot=true) — профиль готов к переносу в
   постоянную службу, когда будет принято решение.
3. Мелочь: 95 тестов против 94 в P2.1 — добавлен тест нового маршрута,
   конфликтов нет.
- Publication commit: _заполняется при публикации_.
