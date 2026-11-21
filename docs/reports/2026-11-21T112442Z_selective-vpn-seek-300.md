# ThinkCentre · 300 секунд 720p после перемотки через штатный VPN, r2 — 2026-11-21

- RESULT: **все 20 этапов rc=0. PLAY_SEEK = PASS — acceptance.ok=true,
  outcome=elapsed, seek_observed=true: перемотка с 5.18с за край буфера
  (cached_until 6.28с) на цель 485.18с, посадка 485.9с (правее края
  буфера), далее полное окно 300с: прогресс 99.77%, 720p 100%,
  остановки 0.0с (макс 0.0с), пропуски 0.0с. FLOW_SEEK = VPN_CONFIRMED —
  state=observed, 1 сопоставленный поток, группа xray (только),
  unmatched пуст, client_zapret2_rule=false. CONTROL: off/off fresh до и
  после, HTTPS 200 дважды, SHA настроек идентичен, временный
  диагностический каталог удалён (cleanup rc=0)**. Read-only: политика
  и службы не менялись.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; mpv 0.37.0; yt-dlp 2026.10.26;
  curl 8.5.0; инструментальный коммит `f141e88…` (SHA инструмента);
  база `08d31ee…`+`3a00777…`.

## §1 Прогон (все этапы)

| Этап | rc | | Этап | rc |
| --- | --- | --- | --- | --- |
| play-unit | 0 | | route-after | 0 |
| sudo / vpn-lock | 0 / 0 | | play-seek | 0 |
| vpn-before / http-port / https-before | 0 / 0 / 0 | | flow-seek | 0 |
| settings-before | 0 | | vpn-after / https-after | 0 / 0 |
| route-tools / route-tools-check | 0 / 0 | | settings-after / -unchanged | 0 / 0 |
| resolve | 0 | | route-tools-cleanup | 0 |
| route-before / route-off | 0 / 0 | | | |

- Инструменты снапшотов распакованы из закреплённого коммита в
  root-каталог 0700 (/tmp), модуль проверен в изолированном Python
  (`env -i`) перед resolve, после опыта каталог удалён. Снимок снят ДО
  запуска mpv — стартовое окно зафиксировано (пара ~150с, одна epoch).

## §2 PLAY_SEEK = PASS

| Поле | Значение |
| --- | --- |
| seek.from / cached_until | 5.18с / 6.28с |
| seek.target / landed | 485.18с / **485.9с** (правее края буфера) |
| acceptance.required / observed | 300с / 300с |
| acceptance.progress_ratio | 0.99765 (≥0.98 ✓) |
| acceptance.target_height_ratio | 1.0 (≥0.99 ✓) |
| acceptance.sampling_gap_seconds | 0.0 (≤5 ✓) |
| acceptance.stall_seconds / longest | 0.0 / 0.0 (≤3 / ≤5 ✓) |
| outcome / seek_observed | elapsed / true |

- Дополнительно: cache_min_seconds 2.02с, cache_read_median_Bps 152 058
  (~152 КБ/с), cache_read_to_bitrate_ratio 1.499, bitrate_bps 811 576.
- **THROTTLED** (старая оценка): сработало единственное условие —
  буфер <5с (cache_min 2.02с); остановок нет; медиана чтения 152 КБ/с
  выше битрейта (~101 КБ/с) — условие «медиана ниже битрейта» не
  сработало. После перемотки окно отыграло 300с без единой остановки.
- Перемотка «за край буфера» (с 6с на 485с) подтверждена полями seek:
  посадка правее cached_until, прогресс окна 99.77%.

## §3 FLOW_SEEK = VPN_CONFIRMED

- `flow-seek.out`: state=observed, qualified_flows=1, groups={xray: 1},
  unmatched={}, client_zapret2_rule=false — полное совпадение с
  положительными критериями ТЗ: минимум один поток, только группа xray,
  пустой unmatched, клиентское правило отсутствует.
- Сопоставленный поток — сокет плеера, на котором объём принятых байтов
  вырос после перемотки в пределах пары снимков (окно ~150с; соединение
  могло быть открыто до перемотки — по ТЗ это допустимо).

## §4 CONTROL

vpn-before/vpn-after — off/off fresh/matched; https-before/after — 200;
settings-before/after — SHA идентичен (сравнение без публикации хэшей);
route-tools-cleanup rc=0. Машина в финале: off/off fresh/matched,
политика и службы не менялись, установок не было.

## Наблюдения для Codex

1. **Маршрут плеера подтверждён на VPN-пути новым инструментом** —
   закрывает вопрос прошлого прохода (FLOW_START inconclusive из-за
   поздних снимков) и общий вопрос подтверждения маршрута сокетов на
   off/off. Пара «снимок до mpv + снимок на ~150с» работает.
2. **Перемотка через VPN без остановок**: после прыжка на +480с окно
   дало 300с при 720p 100% и нулевых stall — буфер после перемотки
   восстанавливается быстрее реального времени (медиана чтения 1.5×
   битрейта сразу после прыжка).
3. THROTTLED-оценка по-прежнему сводится к одному буферному условию;
   предложение из отчёта 900с остаётся в силе (отделять буферный
   критерий от критериев остановок).
4. Инструментальная цепочка r2 (pinned-коммит → root tmp 0700 →
   isolated python → cleanup) прошла без замечаний — пригодна как
   шаблон для read-only ТЗ.
- Publication commit: `f7266fc3f485aec0b5b3b56cabac1facea836882` (1d7ae23 → f7266fc, ancestor verified).
