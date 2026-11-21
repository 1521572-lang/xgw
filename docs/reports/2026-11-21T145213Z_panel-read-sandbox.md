# ThinkCentre · изоляция файлов HTTP-процесса панели (P2.3) — 2026-11-21

- RESULT: **ПОЛНЫЙ УСПЕХ, шлюз не тронут (GATEWAY_UNCHANGED), первый
  прогон без повторов**. HTTP-процесс под непривилегированным UID
  запущен в одноразовом transient systemd unit с профилем
  `packaging/panel-read-hardening.conf`; сокет IPC размещён вне
  закрытых каталогов. Перед открытием HTTP-порта тот же процесс
  попытался открыть четыре рабочих файла (конфигурация, рабочий
  снимок, токен, база) — **все четыре отказа** (содержимое не
  читалось). Контрактные тесты: **95 passed / 0 failed / 0 skipped**.
  Все HTTP-контракты P2.2 воспроизведены; GET/HEAD — 200 с пятью
  полями, **совпавшими со штатной панелью**; при отказе IPC — 503,
  после восстановления — 200. Unit, порт, сокет, root-каталог
  удалены; обе службы active, PID и три контрольных файла совпали,
  off/off fresh/matched, HTTPS 200.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43-generic; systemd 255
  (255.4-1ubuntu8.19); кандидат `95aeaa4…` (SHA инструмента);
  только временные unit/каталог/сокет и loopback-порт, установки
  пакета, правок конфигурации и перезапусков XGW/Xray не было.

## §1 База и контракты

- PINNED `95aeaa496e080a6374168909f1fbd606c7462a88`; baseline:
  обе службы active, off/off fresh/matched, HTTPS 200, контрольные
  SHA трёх файлов зафиксированы.
- **CONTRACT_TESTS_RC 0** — 95 passed / 0 failed / 0 skipped за 66с
  (панель IPC, HTTP-чтение, event-сокет, панель, T11 login check).

## §2 Песочница filesystem

| Проверка | Итог |
| --- | --- |
| socket_permissions (IPC root 0660, вне закрытых каталогов) | OK |
| http_unsandboxed_snapshot (контрольный замер тем же UID вне unit) | true — снимок читаем вне unit, оба булевых значения допустимы |
| **http_sandbox_files_denied** (конфигурация, снимок, токен, база) | **OK — все 4 открытия отклонены внутри unit** |
| http_privileges (UID непривилегированный, только своя группа, 5 масок capabilities = 0, NoNewPrivs=1) | OK |
| **http_mount_namespace** (пространство монтирования воркера отдельно от root-чекера) | **OK** |

- Профиль unit: `NoNewPrivileges`, пустые
  `CapabilityBoundingSet`/`AmbientCapabilities`, `ProtectSystem=strict`,
  `ProtectHome`, `PrivateTmp`, `PrivateDevices`, `ProtectProc=invisible`,
  `ProtectKernelTunables/Modules/Logs`, `InaccessiblePaths` на каталоги
  gateway, `RestrictAddressFamilies`, `RestrictNamespaces`,
  `RestrictSUIDSGID`, `LockPersonality`, `SystemCallArchitectures`,
  `UMask=0077`; страховки `RuntimeMaxSec=40s`, `TimeoutStopSec=3s`.
- Сочетание с P2.2: вне unit тот же UID видит снимок
  (http_unsandboxed_snapshot=true), внутри unit снимок недоступен —
  отказ обусловлен именно песочницей unit, а не UID.

## §3 HTTP-контракты (в песочнице, как в P2.2)

| Запрос | Итог |
| --- | --- |
| без ключа / неверный ключ / повторённый заголовок | 401 ×3 |
| чужой Origin / повторённый Host | 403 ×2 |
| POST | 405 |
| `/api/state` | 404 — единственный маршрут GET/HEAD `/api/zapret2/status` |
| Отклонённые запросы | **до IPC не доходят** (http_only_read_route) |
| **авторизованный GET** | **200 + пять полей** (mode/engine_mode/state/fresh/policy_matched = off/off/off/true/true) |
| **ISOLATED_HTTP_STATUS_MATCH** | поля совпали с baseline штатной панели |
| http_head | 200, пустое тело |

## §4 Отказоустойчивость и очистка

- **http_unavailable** — 503 при недоступном IPC внутри песочницы;
  **http_recovered** — 200 с прежней карточкой после восстановления.
- http_unit_stopped (transient unit завершён), http_cleanup (порт
  закрыт), socket_cleanup (IPC-сокет удалён), TOOLS_REMOVED
  (root-каталог инструментов удалён).
- **GATEWAY_UNCHANGED** — обе службы active, PID и три контрольных
  файла до/после совпали, off/off fresh/matched, HTTPS 200.

## Наблюдения для Codex

1. **P2.3 принят целиком с первого прогона**: профиль
   `panel-read-hardening.conf` даёт полный набор (caps=0, NoNewPrivs,
   отдельный mount namespace, InaccessiblePaths на все четыре рабочих
   файла и /run/xgw*); все контракты P2.2 воспроизводятся без
   изменений внутри песочницы, включая 503→200.
2. Контрольная пара замеров снята корректно: тот же UID вне unit
   читает снимок (true), внутри unit — отказ; значит, недоступность
   рабочих файлов обеспечивается systemd-песочницей, что и требовалось
   доказать в P2.3.
3. Цепочка P2.1 (IPC) → P2.2 (HTTP-UID) → P2.3 (filesystem sandbox)
   замкнута: read-only путь «IPC-сокет → отдельный HTTP-UID → пять
   полей» устойчив под жёстким unit с RuntimeMaxSec; профиль готов к
   переносу в постоянную службу при принятии решения.
4. Число контрактных тестов без изменений против P2.2 (95).
- Publication commit: `053d3d9f74552357e344fc34a7056f61436a9c12` (2026-11-21T145213Z_panel-read-sandbox.md).
