# ThinkCentre · маршрут конкретного медиасоединения T12 — 2026-11-20

- RESULT: **FLOW=ZAPRET2** — TCP-соединение медиаплеера в окне Selective
  сопоставлено анализатором `c9d39fb` с записью журнала `xgw-xray.service`:
  выбранный outbound — **zapret2**, `qualified_flows=1`, неидентифицированных
  0 (`unmatched={}`), обе границы окна в одной ревизии Selective active
  (`client_zapret2_rule=true`, конфиг `62ce93c6…`, epoch Xray не менялся).
  Положительный контроль VPN: в off/off то же соединение атрибутировано
  **xray** (`groups={"xray": 1}`, `qualified_flows=1`, правило false).
  Плеер в обеих фазах ok=true (134.1с, 720p 100%, stall 1с, gaps 0).
  **RESTORE VERIFIED** (guard accept, 8/8, таймер остановлен).
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 файлов `3a00777` + 6 `08d31ee`);
  инструменты: клиент `1e0c290`, трассировка `c9d39fb`; VIDEO 10h; sudo -n
  (NOPASSWD), NoNewPrivs=0. Журнал Xray читался только по PID из снимка в
  коротком интервале (≤5000 строк, JSON, только MESSAGE/_PID/_BOOT_ID/UNIT).

## §1 Подготовка и VPN-контроль

- ACCESS_OK; source `1e0c290`; база cmp 11/11 без расхождений; off/off fresh;
  воркеры inactive; tools с `route_evidence`; socket-check `state: read`;
  QUEUE=200; `nf_conntrack_acct=0`.
- VPN baseline: resolve ок; probe **206/65536** (`173.194.x.x`); ipify ок;
  delta сопоставимых снапшотов xray downlink +71 619 (1.1с).

## §2 Положительный контроль (off/off → flow-vpn)

- `flow-vpn.out`: `{"client_zapret2_rule": false, "groups": {"xray": 1},
  "qualified_flows": 1, "state": "observed", "unmatched": {}}`.
- Плеер: ok=true — 134.11с eligible, прогресс 99.3%, 720p 100%, stall 1.0с,
  gaps 0. Контроль пройден: журнал годится для сопоставления, соединение
  получило маршрут VPN-группы.

## §3 Один старт в Selective (flow-selective)

- Готовность: fresh/matched/active/**https_reachable** (~45с), настройки
  fake_md5 + пара t/terms + прямой URL проверенного узла (probe206
  0.17с, `77.37.252.211` — узел из прошлого прохода).
- `flow-selective.out`: `{"client_zapret2_rule": true, "groups":
  {"zapret2": 1}, "qualified_flows": 1, "state": "observed", "unmatched": {}}`.
- Границы окна: обе в одной ревизии (config semantic sha `62ce93c6…`
  идентичен, Xray epoch `5186260` не менялся), состояние selective active.
- Плеер: ok=true — 134.11с, прогресс 99.6%, 720p 100%, stall 1.0с, gaps 0.
- **Вердикт: FLOW=ZAPRET2** — все пригодные соединения (1 из 1) получили
  один вид маршрута (zapret2); других групп и `other` не найдено.
- После фазы: selective оставался active/https_reachable до restore.

## §4 Связь с initial-PARTIAL (пересчёт от 10:51Z)

Повтор стартовал на том же проверенном узле, что и seek в r2, и получил
zapret2-маршрут на уровне потока. Это согласуется с гипотезой пересчёта
(в initial непоподтверждённые окна имели рост группы xray при ровно нуле
zapret2): выбор CDN-peer влияет на исходящий обработчик. Прямую привязку
«старый initial» здесь не переоткрыть — исторические JSONL не содержат
локальных портов; **вывод по старому initial остаётся PARTIAL/открытым**,
что соответствует ТЗ. Совпадение на повторе относится к этому интервалу;
VPN fallback и окно seek учитываются по принятому отчёту r2.

## §5 Восстановление

guard accept: первый вызов rc 0; verify 8/8 (marker, sha256 конфигов OK,
xgw.service active, воркеры MainPID=0, off/off fresh после ~4 попыток
опроса — панель применяла ревизию, снапшот с `client_zapret2_rule: false`,
ipify ок) → **RESTORE_VERIFIED**; таймер остановлен; 90 записей steps.tsv.
Сырые журналы/URL/IP/PID — на машине в каталоге опыта 0700.

## Наблюдения для Codex

1. Потоковая атрибуция через журнал Xray работает в обоих режимах и даёт
   недостающее звено «peer → outbound»: r2-загадка initial (xray растёт,
   zapret2=0 при живой очереди) теперь объяснима проверяемым способом —
   по локальному порту соединения плеера в journal.
2. Следующий шаг для закрытия initial: повтор r2-окон с этой же трассировкой
   (локальный порт в сэмплах уже пишется новым headless_playback), тогда
   PARTIAL можно будет переклассифицировать по факту, а не по гипотезе.
3. `sudo -v` заменён на `sudo -n true` (как согласовано в r2-отчёте).
- Publication commit: `добавляется после push`.
