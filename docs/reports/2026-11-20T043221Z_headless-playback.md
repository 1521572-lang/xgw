# ThinkCentre · CDN-проба Range и headless-воспроизведение — 2026-11-20

- RESULT: **§1 PASS (213 tests на кандидате `3788dd2`, база 11/11 = `08d31ee`,
  off/off fresh), §2 PASS (оверлей zapret2/jobs/client prepare+apply, cmp×3,
  таймер 180м), §3 ЧАСТИЧНО: новый headless-инструментарий и Стандарт-контроль
  отработали, обе матрицы (signed и persistent) complete 4/4, restore=pass —
  но two_https_pass=[] в обеих → pin отказ, Selective и §4 NOT_RUN, §5
  rollback выполнен (3 файла = базе `08d31ee`, конфиги sha256 OK)**. Ключевой
  диагноз нового прибора: **CDN-проба стабильно падает на TLS-фазе**
  (page probe при этом HTTP 200 с телом в каждом круге) — при том что
  внешний curl с той же машины через VPN получает 206 от того же узла
  googlevideo (64К 0.37с / burst 10 МиБ 1.48с). Воспроизводимый блокер
  CDN-пробы локализован: не подпись, не канал, а путь/обработка пробы.
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; mpv 0.37.0; yt-dlp 2026.10.26;
  curl 8.5.0; кандидат `3788dd2…`; база `08d31ee…`.

## §1 Контроль VPN (VIDEO: 10h, формат 398 mp4 720p)

| Замер | Результат |
| --- | --- |
| probe 64 КиБ | 206, TLS 0.24с, TTFB 0.32с, всего 0.40с, узел `173.194.x.x`, ok |
| probe 10 МиБ | 206, TLS 0.17с, 1.48с, ~7.1 МБ/с, тот же узел, ok |
| player 120с --peers | ok=true: eligible 134.1с, progress 99.5%, 720p 100%, stall 1.0с, cache_min 0.48с, медиана чтения 200 КБ/с, bitrate 0.81 Мбит/с, THROTTLED (по буферу), outcome=elapsed |

- mpv с прямым URL снова доиграл 134 с без ошибок извлечения; «THROTTLED» у
  обеих линий определяется только минимальным буфером (<5с) — sustain-скорость
  googlevideo ~200 КБ/с одинакова через VPN и напрямую, bursts по 7–11 МБ/с.
- solve/resolve: подпись fresh; узел rr5 (`…-5t`).

## §2 Установка трёх файлов

prepare → apply: complete; cmp `$PAYLOAD/code` vs `/opt/xgw/lib/xgw` —
zapret2.py, desync/jobs.py, desync/client.py — 3/3 совпали с кандидатом;
config.toml+panel.json sha256 OK; rollback-таймер 180м active.

## §3 Контроль и матрицы

**Standalone** (multisplit + 4 домена YouTube, проба off): fresh/active.
probe по исходной подписи — оба таймаута (rc=28, узел `173.194.x.x`);
отдельное извлечение на прямом пути: подпись сменила узел **rr5→rr8
(`…-c35d`, `77.37.x.x`)**; повтор: 206×2 (64К 0.32с; burst 10 МиБ за 0.97с —
10.8 МБ/с). player 120с: ok=true (134.1с, 720p 100%, THROTTLED по буферу
0.46с). Прямой маршрут подтверждён. Возврат off/off settled.

**Матрица signed** (`c718c3e7…`, fake_md5+multidisorder ×2, job complete,
restore=pass, ok=true 4/4):

| Строка | state | reason | page | cdn |
| --- | --- | --- | --- | --- |
| fake_md5 r1 | fallback | youtube_cdn_probe_failed | 200/body 57247 Б, 501мс | **TLS timeout 20231мс (first 10153мс)** |
| multidisorder r1 | timeout | trial_timeout | — | — |
| multidisorder r2 | timeout | trial_timeout | — | — |
| fake_md5 r2 | timeout | trial_timeout | — | — |

- Повтор того же задания пропущен по ТЗ (все строки TLS/таймаут).
- **probe-persistent** (off/off): saved; **матрица persistent** (`34b645e7…`,
  complete, restore=pass): та же картина — обе строки r2 с пробами:
  page 200/body 543–568мс, **cdn TLS timeout 20232–20412мс** на
  persistent-URL того же хоста; r1 — trial_timeout. **two_https_pass=[]**.
- Итог допуска: НЕ ПРОЙДЕН; «исправление подтверждено на CDN» — нет (проба
  не записала ни одного HTTP 206 с телом ни на подписанном, ни на
  persistent-URL). PROFILE не выбран, pin не выполнялся.

## §4 — NOT_RUN

Selective не включался (нет пина) — long/seek/pairs/socket-match/SIGKILL/сутки
не выполнялись. Причина: пустой two_https_pass в обоих job.

## §5 Возврат

- rollback: restore-completed; 3 файла = базе `08d31ee` (cmp 3/3);
  config.toml+panel.json sha256 OK; xgw.service active, воркеры inactive;
  off/off fresh/matched, job complete; таймер остановлен.
- vpn-final: probe 64К — 206 (0.37с, тот же узел `173.194.x.x` — подпись
  format.json жива через VPN-выход); player 120с — ok=true (134.1с, 720p
  100%, THROTTLED по буферу 0.40с) — контроль после возврата воспроизводит §1.
- Диск 38 ГБ; сырые URL/подписи/JSONL — на машине в каталоге опыта 0700.

## Наблюдения для Codex

1. **CDN-проба: TLS timeout — устойчивый воспроизводимый исход** (3 job
   подряд, обе редакции URL: подписанный /videoplayback и persistent того же
   хоста; ~20с full timeout, первый TLS-таймаут ~10с), при этом page-проба
   www.youtube.com — 200 с телом каждый раз, и параллельный внешний curl до
   того же узла googlevideo получает 206. То есть подпись и хост доступны,
   TCP/TLS до googlevideo с этой машины работает — отказ возникает именно на
   пути пробы воркера (маркировка/обработка первого ответа от CDN-хоста).
   Это согласуется с прежней диагностикой «прямые пути теряют TLS-ответы от
   googlevideo (acked, recv=0)». Точка для следующего шага: сравнить
   сокет-статистику и nfqws-решения на пакеты пробы vs внешнего curl.
2. Прибор `3788dd2` (64 КиБ Range, reason/phase/kind/http/bytes в матрице)
   работает как задуман: причина каждой строки видна — это и позволило
   точно зафиксировать TLS-фазу отказа без повторов задания.
3. trial_timeout ×3: круги multidisorder r1/fake_md5 r2 не завершились в
   бюджет — при TLS-блокировке CDN-пробы это ожидаемое следствие, отдельного
   поиска не требует.
4. mpv-плеер: обе линии (VPN и прямой) дают одинаковую кривую — burst 7–11
   МБ/с, sustain ~200 КБ/с, буфер 0.4–0.5с минимум. Для 900-секундной фазы
   понадобится профиль с большим запасом sustain или долгий предбуфер
   (сейчас кеш не превышает ~45с и падает до нуля при колебаниях).
- Publication commit: `добавляется после push`.
