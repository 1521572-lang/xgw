# ThinkCentre · медиамаршрут Selective и возврат на VPN, редакция 2 — 2026-11-20

- RESULT: **INITIAL_PLAY PASS · SEEK_PLAY PASS · MEDIA_PATH SUPPORTED (seek) /
  PARTIAL (initial) · NFQUEUE OBSERVED (оба окна) · VPN_OTHER_SITE PASS ·
  AUTO_FALLBACK PASS · MANUAL_VPN PASS · RESTORE VERIFIED**. Новые сборщики
  `1e0c290` (--marked-sockets) и анализатор `selective_media_evidence`
  отработали штатно: в seek-окне 44/54 сопоставимых окон дали одновременный
  рост на сокетах одного CDN, очереди NFQUEUE и downlink аутбаунда zapret2
  сверх фона (full_matches=1, outbound_matches=1); initial — 42 socket и
  42 queue совпадения, но без роста аутбаунда → PARTIAL по media_path.
  Fallback: SIGKILL MainPID → fallback на t+12.1с той же ревизии `ba632f09`,
  клиентское правило снято (`client_zapret2_rule: false`), новый CDN-запрос
  **206/65536** через VPN-выход (`173.194.x.x`), xray downlink +85.8 КБ в
  сопоставимых снимках. Восстановление: guard accept, 8/8 проверок, таймер
  остановлен. Среда: sudo без терминала отклоняет `sudo -v` — работает
  `sudo -n` (NoNewPrivs=0, CapEff=0); все блоки выполнены с `sudo -n true`
  вместо `sudo -v` (отклонений прав не было).
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; база: 5 файлов `3a00777` + 6 файлов
  `08d31ee` — cmp 11/11; инструменты `1e0c290`; VIDEO 10h (без замены);
  off/off fresh на старте, воркеры inactive.

## §1 Доступ и исходное состояние

ACCESS_OK (после адаптации sudo); source-tree `1e0c290` — ок; база 11 файлов
(`zapret2/jobs/client/zapret2_control/daemon` = `3a00777`, `panel/
zapret2_management/profiles/nft/sysctl/nfqws2` = `08d31ee`) — 0 расхождений;
off/off fresh; воркеры MainPID=0; tools `/opt/xgw/handoff/media-route-r2-tools.LRZW3SqP`
с `route_evidence` импортируется; **socket-check `state: read`** (2 с);
QUEUE=200; `nf_conntrack_acct=0`.

Замечание к протоколу: два исполнительских сбоя при переносе состояния между
shell-вызовами (функции/переменные) — initial-off и restore-arm выполнены
повторно после исправления; на результат проверок не повлияли (все итоговые rc=0).
VPN-снапшоты первого vpn_site писались с umask 022 → `private_path_required`
в delta; после chmod 600 delta отработала (снапшоты переснимались заново
тем же окном — дельта относится к своему интервалу 1.1с).

## §2 VPN-контроль, предохранитель, политика

- VPN baseline: resolve ок; **probe 206/65536** (TLS 0.24с, `173.194.x.x`);
  api.ipify ок; delta сопоставимых снапшотов: xray downlink **+69 753** за
  1.1с, правило false — **VPN_BASELINE_CAPTURED**.
- Guard: unit `xgw-selective-media-r2-1795170214-18217`, 90м, accept-restore,
  marker создан, hash-файл 0600, lock взят.
- Standalone: fresh/matched/active/without_vpn; прямой контроль — resolve
  с первого раза упал (SSL handshake timeout при извлечении), **один повтор —
  ок: 206/65536 за 0.16с (`77.37.252.211` — узел, проверенный в прошлом
  проходе)** → DIRECT_OK.
- off/off settled; settings POST (fake_md5 + пара t/terms + прямой URL,
  512 МиБ, 180/120) → **SELECTIVE_SETTINGS_READY** на ревизии `ba632f09…`,
  blockers.selective=[].
- Selective включён: pending → active → **active/https_reachable** (~60с,
  fresh, matched, transport=https_reachable).

## §3 Два коротких окна

| Окно | Плеер | Сборщики | Анализатор |
| --- | --- | --- | --- |
| initial | **ok=true**: 135.05с eligible, прогресс 99.5%, 720p 100%, stall 0, gaps 0 | gateway 180с (rc 0), marked 180с (rc 0) | 46 comparable; **socket 42, queue 42**; outbound 0; probe_overlap 1 → **media_path=PARTIAL, NFQUEUE=OBSERVED** |
| seek (+480) | **ok=true**: 135.06с, прогресс 99.95%, 720p 100%, stall 0, gaps 0, **seek_observed** (цель 485.42) | gateway 180с (rc 0), marked 180с (rc 0) | 54 comparable; **socket 44, queue 44, outbound 1, full 1** → **media_path=SUPPORTED, NFQUEUE=OBSERVED** |

- Между окнами (вне окна анализа mpv): api.ipify через VPN + дельта
  сопоставимых снапшотов — xray uplink **+1 090 508** / downlink +4 189 за
  1.0с, правило true → **VPN_OTHER_SITE PASS** (обычный сайт идёт через
  VPN-аутбаунд при активном Selective).
- initial PARTIAL: одновременного роста аутбаунда zapret2 в сопоставимых
  окнах анализатор не увидел (outbound_matches=0 при 42 socket/queue
  совпадениях); по ТЗ поддержка маршрута относится к своему окну —
  поддержана именно seek-фаза. `NFQUEUE=OBSERVED` подтверждён в обоих окнах
  собственными положительными дельтами очереди сверх фона — на этом хосте с
  acct=0 счётчики пар `--media-pairs` оставались нулевыми, новый сборщик
  `--marked-sockets` + очередь из диагностического пути дали положительные
  дельты (расхождение источников отмечено).
- Смена CDN-адреса/владельца сокета между окнами: initial — медиасокет к
  одному peer, seek — к `77.37.252.211`; окна анализатор не сливал.

## §4 Новый CDN-сеанс внутри fallback

- Пред-проверки: active (та же ревизия), VPN-подпись читается, **владелец
  очереди 200 верифицирован** (`worker.verify_owner` rc 0).
- Хронология (от SIGKILL): kill rc 0 @0.07с → active×23 опроса → **fallback
  fresh/matched на t+12.1с, ревизия `ba632f09` неизменна** → снапшот маршрута
  (`client_zapret2_rule: false`) → GET: **206/65536** (TLS 0.23с,
  `173.194.x.x` — VPN-выход, время 13.1→15.0с окна) → после GET состояние
  fallback сохраняется (fresh) → delta сопоставимых снапшотов: xray downlink
  **+85 832** / uplink +6 775 за 1.9с, правило false → **AUTO_FALLBACK PASS**.
- Повторный active после fallback не ожидался в окне скрипта (45с лимит не
  исчерпан — окно завершилось успехом на 15.5с); отдельная пометка: возврат
  active наблюдался в прошлом проходе и здесь не проверялся.

## §5 Восстановление

- Первый вызов guard — rc 1: в мой вызов не подставился путь PANEL
  (исполнительская ошибка состояния shell; restore.sh получил пустой аргумент);
  второй вызов — rc 0, «изменений нет» (панель уже приведена к panel.before),
  marker создан.
- **verify_restore 8/8**: marker, sha256 config+panel OK, xgw.service active,
  воркеры MainPID=0 inactive, off/off fresh/matched (final.json), снапшот
  restored с `client_zapret2_rule: false`, ipify ок → **RESTORE_VERIFIED**;
  таймер остановлен (ActiveState=inactive).
- **MANUAL_VPN**: свежий resolve + **206/65536** (`173.194.x.x`) + delta
  сопоставимых снапшотов xray downlink **+183 244** за 2.1с, правило false →
  PASS. Lock освобождён.
- Хронология шагов — 88 записей в steps.tsv (каталог опыта 0700); сырые
  журналы, URL, IP, конфиги — на стенде.

## Наблюдения для Codex

1. **Новый канал доказательства работает**: `--marked-sockets` + корреляция
   анализатором дала `media_path=SUPPORTED` с одновременными дельтами очереди
   (NFQUEUE=OBSERVED), socket-ростом на одном CDN-peer и downlink аутбаунда —
   впервые без pcap и без acct.
2. **initial без outbound-дельты** при 42 socket/queue совпадениях: медиа
   шло (плеер 0 stall, 720p), но аутбаунд zapret2 за окна не вырос. Кандидаты
   причин: короткие перерывы отдачи в фоне (буфер 25с), фоновые окна съели
   порог «сверх фона», либо вниз сходил другой outbound в эти секунды. Стоит
   логировать в анализаторе top-дельты соседних outbound для окон с
   socket_matches и без outbound_matches.
3. **`sudo -v` в ТЗ** непригоден для исполнителя без tty (NoNewPrivs=0,
   sudo NOPASSWD по -n): заменять в следующих ТЗ на `sudo -n true`, иначе
   ACCESS_OK ложный BLOCKED_ENV.
4. Сбои переноса shell-состояния (мой инструментальный пункт): повтор не
   повлиял на исходы, но в скриптах ТЗ функции `live/capture/workers_off`
   используются в нескольких блоках — объединить их в один env-файл или
   один скрипт, чтобы исключить человеческий фактор.
- Publication commit: `добавляется после push`.
