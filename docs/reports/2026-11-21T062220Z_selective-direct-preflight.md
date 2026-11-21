# ThinkCentre · проверка прямого CDN до установки кандидата (preflight) — 2026-11-21

- RESULT: **§1 PASS, §2 BASE_DIRECT=UNSTABLE — приёмка кандидата
  корректно заблокирована префлайтом, установка не выполнялась, §3
  NOT_RUN (переход закрыт), §4 RESTORE VERIFIED**. Помощник допуска
  `4c9379e` (src/xgw побайтово = кандидату `39421a6`) отработал как
  задумано: unit 7/7, receipt создан до POST, две отдельные прямые
  пробы не набрались — на установленной базе Selective ушёл в
  **fallback / youtube_cdn_probe_failed (tls/timeout)** через ~2 минуты
  после здорового VPN-контроля (206/65536); VPN-контроль базы в этом же
  окне — **pass** (URL через VPN доступен). Возврат off по receipt,
  guard accept, SHA настроек OK, файлы 6/6 = базе, off/off settled,
  таймер остановлен, VPN жив.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; mpv 0.37.0; yt-dlp 2026.10.26;
  curl 8.5.0; инструментальный коммит `4c9379e`; кандидат `39421a6…`
  (не устанавливался); установленная база `08d31ee…` + 5 файлов
  `3a00777…` + applier/singbox_generation `1e27384…` — сверены 13/13.

## §1 База, тест помощника, guard

| Шаг | Итог |
| --- | --- |
| trial-source | worktree `4c9379e`; `git diff --quiet CANDIDATE HEAD -- src/xgw` — src/xgw совпадает с кандидатом |
| trial-helper-unit | 7/7 passed (`tests/test_selective_admission.py`) |
| база | off/off fresh, воркеры off, xgw.service active, таймеров нет; 13 файлов (11 базы + applier/singbox) = базе (cmp) |
| VPN-контроль | resolve 720p mp4 10.2ч; **probe 206/65536 через VPN** (06:17:34Z); vpn_site снимки сопоставимы (client_zapret2_rule=false, конфиг не менялся) → **VPN_BASELINE_CAPTURED** |
| trial-stage/guard | payload+backup под handoff, prepare OK, sha256 config+panel OK, guard 90м active, network-test-started → **TRIAL_GUARDED** (overlay-apply-started ещё нет — guard в режиме accept) |

## §2 Две прямые пробы на базе

- `admit --format … --checks 2 --timeout 180`: настройки сохранены
  помощником (fake_md5, 10 доменов, check_seconds=60, retry 120,
  бюджет 512 МБ, probe_urls [terms, CDN URL]); POST mode принят
  (receipt `c38b1fbe…`).
- Исход: **fallback, youtube_cdn_probe_failed, cdn_phase=tls,
  cdn_kind=timeout** — две успешные прямые пробы с разными штампами не
  набрались → rc=2. **BASE_DIRECT=UNSTABLE** (причина: TLS-таймаут
  прямого пути в окне допуска).
- Одновременно `control=pass` (VPN-контроль базы) при
  `target=null/attempts=[]` — базовый демон зафиксировал доступность
  URL через VPN в тот же момент; новые поля attempts/target — только
  у кандидата, помощник читает их через .get без ошибок.
- **write-install не запускался** (ветка прервана на base-admission) —
  оверлей кандидата не применялся, overlay-apply-started не создавался.
- Возврат: `off` по receipt — rc=0, режим off подтверждён
  (fresh/matched/off) ещё до guard.

## §3 — NOT_RUN

Переход закрыт до CANDIDATE_INSTALLED. STATUS=NOT_EXERCISED,
LIVE_PLAY=NOT_RUN, FLOW=NOT_RUN.

## §4 Восстановление

- guard (mode=accept — оверлей не применялся) rc=0 → restore-completed;
  sha256 config.toml+panel.json OK (состояние до опыта); файлы 6/6 =
  базе; xgw.service active; воркеры inactive; off/off: штатный settling
  (pending/stopping → off на 2-й проверке, ~20с — как и в r4);
  ipify 200 (тот же выход, что в r2–r4); таймер остановлен
  (inactive/dead).
- Машина в финале: off/off fresh/matched, файлы = базе, VPN работает.

## Наблюдения для Codex

1. **Префлайт работает как замысел**: кандидат с проверенным
   redirect-механизмом не устанавливался на нестабильный прямой путь —
   окно опыта потрачено на контроль базы, а не на установку с
   последующим fallback (в r3/r4 допуск падал уже ПОСЛЕ установки).
2. **Флап продолжается (3-е ТЗ подряд без активного допуска)**:
   06:17:34Z — 206/65536 через VPN; ~06:19:5xZ — прямой TLS-таймаут;
   в том же окне VPN-контроль базы — pass. Окна «здоровья» короткие;
   помощник с check_seconds=60 в окне 180с не успевает собрать два
   штампа, если первая проба попала в фазу флапа.
3. Идея для следующего шага: помощник/ТЗ может позволить «прогрев» —
   клиентский контрольный GET на прямой путь до POST mode (как
   контроль в CDN-PEER r0), чтобы начинать допуск только в здоровой
   фазе; либо допускать больший timeout при checks=2.
4. Механика помощника чистая: receipt до POST, разные штампы по
   206/65536, возврат off по receipt, работу с базовой схемой evidence
   (без attempts/target) — без ошибок.
- Publication commit: `6d81e35a31c5c2d56e77232c7f3d3a95f9d81d4c` (ebb14ca → 6d81e35, ancestor verified).
