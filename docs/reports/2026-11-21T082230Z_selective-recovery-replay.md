# ThinkCentre · разбор сохранённых потоков и один повтор CDN на базе — 2026-11-21

- RESULT: **§1 PASS (инструменты `f79eec8`: src/xgw = кандидату `39421a6`,
  helper-тесты 49/49), REPLAY выполнен для обоих сохранённых окон,
  VPN_BASELINE_CAPTURED, TRIAL_GUARDED; §2 BASE_DIRECT=UNSTABLE — первая
  прямая проба TLS-таймаут на +64.6с, помощник открыл окно штатного
  повтора (waiting_for_cdn_retry), повтор watchdog через ~60с — снова
  TLS-таймаут → fallback, две успешные прямые пробы не набрались;
  write-install не запускался; §3 NOT_RUN; §4 RESTORE VERIFIED** (receipt
  off + guard accept, SHA OK, файлы 6/6 = базе, off/off, таймер dead,
  VPN жив).
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; mpv 0.37.0; yt-dlp 2026.10.26;
  curl 8.5.0; инструментальный коммит `f79eec8`; кандидат `39421a6…`
  (не устанавливался); база `08d31ee…`+5 файлов `3a00777…`+applier/
  singbox `1e27384…` — 13/13 сверены до опыта.

## REPLAY сохранённых окон (политика не менялась)

Разбор выполнен новым инструментом (`selective_flow_evidence
--observe-applied-change`) по сохранённым парам снимков + JSONL плеера;
журнал Xray извлечён по boot/PID/окну из epoch снимков (доступ через
группу adm). По одной паре на имя, неоднозначности не было.

| Окно | Источник | state | changed_sections | logged_zapret2 |
| --- | --- | --- | --- | --- |
| writer-media | опыт xray-config-writes r3 | inconclusive | [routing, inbounds, outbounds] | {accepted 0, qualified 1, unconfirmed 1} |
| flow-r2b | опыт cdn-update r2 | inconclusive | [routing, inbounds, outbounds] | {accepted 0, qualified 1, unconfirmed 0} |

- Оба окна — «изменившиеся» (несопоставимые снимки): общая оценка
  остаётся inconclusive, но новое поле даёт частичный ответ вместо
  немого отказа: в каждом окне один qualified поток плеера и **ноль
  точных совпадений с accept-записями выделенного outbound zapret2**
  в журнале того же процесса Xray.
- Это согласуется с прежней находкой «нулевой счётчик zapret2» в этих
  окнах (42/42 no_growth при росте xray-группы). Артефакты и журнал
  были доступны; сырые данные остаются в приватных каталогах.

## §1 Инструменты, VPN, guard

| Шаг | Итог |
| --- | --- |
| trial-source | worktree `f79eec8`; `diff --quiet CANDIDATE HEAD -- src/xgw` чисто |
| trial-helper-unit | 49/49 (admission + новые тесты probe_watch) → TRIAL_TOOLS_READY |
| база | off/off fresh, воркеры off, таймеров нет, 13 файлов = базе |
| VPN-контроль | resolve 720p mp4 10.2ч; **206/65536 через VPN** (08:15:29Z); снимки сопоставимы (rule=false) → **VPN_BASELINE_CAPTURED** |
| trial-stage/guard | prepare OK, sha256 config+panel OK, guard 90м, network-test-started → **TRIAL_GUARDED** |

## §2 Прямые пробы на базе с одним повтором

- Настройки помощником (fake_md5, 10 доменов, check_seconds=60,
  retry 120, бюджет 512 МБ, probe_urls [terms, CDN URL]); POST mode
  принят, receipt создан до POST.
- **+64.6с**: CDN-проба — TLS-таймаут → помощник зафиксировал
  `waiting_for_cdn_retry` (новая логика: счётчик успешных проб сброшен,
  окно продолжено) и ждал штатный повтор watchdog.
- **~+245с** (повтор через 60с после первого): **повторный TLS-таймаут**
  → окончательный fallback / youtube_cdn_probe_failed (tls/timeout) —
  по ТЗ это завершает проверку, rc=2. **BASE_DIRECT=UNSTABLE**.
- `control=pass` в обоих событиях относится к первому адресу пары
  (страница YouTube через VPN); CDN-проба базы на прямом пути оба раза
  TLS-таймаут. Попыток vpn_control на CDN у базы нет (attempts=[] —
  поле кандидата).
- **write-install не запускался** (ветка прервана на base-admission);
  оверлей не применялся, overlay-apply-started не создавался.
- Возврат: `off` по receipt rc=0, режим off подтверждён.

## §3 — NOT_RUN

Переход закрыт до CANDIDATE_INSTALLED. STATUS=NOT_EXERCISED,
LIVE_PLAY=NOT_RUN, FLOW=NOT_RUN.

## §4 Восстановление

- guard (mode=accept) rc=0 → restore-completed; sha256 config+panel OK;
  файлы 6/6 = базе; xgw.service active; воркеры inactive; off/off
  подтверждён сразу (fresh/matched/off); ipify 200 (тот же выход);
  таймер остановлен (inactive/dead).
- Машина в финале: off/off fresh/matched, файлы = базе, VPN работает.

## Наблюдения для Codex

1. **Механика `--recover-cdn-once` работает как задумано**: первый
   TLS-таймаут не завершает окно, логируется waiting_for_cdn_retry
   с elapsed, счётчик сбрасывается; повторный таймаут завершает
   проверку. Впервые окно допуска прождало штатный повтор watchdog
   end-to-end.
2. **Флап устойчив в масштабе минут**: 08:15:29Z — 206/65536 через VPN;
   +64.6с — прямой TLS-таймаут; +125с — повторный прямой TLS-таймаут.
   Два подряд прямых таймаута в одном окне — новый тип исхода (раньше
   окно прерывалось после первого). Прямой путь к googlevideo остаётся
   недоступным в фазе флапа, при этом служебные HTTPS (terms) через VPN
   живы.
3. **REPLAY: accepted=0 в обоих старых окнах** — точных совпадений
   сокетов плеера с accept-записями outbound zapret2 нет, хотя
   qualified поток есть. Вопрос для разбора: логирует ли Xray accept
   на reserved outbound в тех версиях/окнах, либо медиасокеты в этих
   окнах действительно шли мимо zapret2 (тогда ранее доказанный
   FLOW=ZAPRET2 в свежих окнах контрастирует со старыми).
4. Сбой среды исполнения (не стенда): во время этого прохода приложение
   агента перезапустилось и ~30 минут не имело доступа к sudo
   (NoNewPrivs=1 на scope приложения); разбор сохранённых окон успели
   выполнить до сбоя (он не требует root), живая часть продолжена тем
   же окружением после восстановления доступа. Политика в паузе не
   менялась (машина off/off, таймеров не было).
- Publication commit: _заполняется при публикации_.
