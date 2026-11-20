# ThinkCentre · контроль CDN через VPN и статус Selective после ротации — 2026-11-21

- RESULT: **UNIT_TESTS PASS · DAEMON_BASELINE ok=true (matching=12, changed=0,
  new=0) · INSTALL PASS (6 файлов) · ADMISSION: одна штатная попытка →
  fallback (reason=youtube_cdn_probe_failed, cdn_phase=tls, cdn_kind=timeout;
  client_zapret2_rule=false подтверждено снимком; правило снято) ·
  CDN_VPN_CONTROL: target=cdn, result=**fail**, reason=request_failed —
  в окне попытки (23:09:36–23:11:21 UTC) не прошёл и контрольный запрос
  кандидата через VPN · STATUS/LIVE_PLAY/FLOW NOT_RUN (ветка fallback по ТЗ) ·
  RESTORE VERIFIED (6/6 = базе)**.
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee`); кандидат
  `d4b9a7b` — 6 файлов (+ `zapret2.py` к пяти прошлого прохода); VPN_FORMAT
  fresh (22:57, 206/65536 через `173.194.x.x`); sudo -n; тесты обычным
  пользователем.

## §1 Гейт (6 файлов)

Обе копии из `d4b9a7b`; baseline = кандидат с 6 файлами от `3a00777`
(diff-only ровно 6 имён). writer-unit rc=0; daemon rc=1/1; **gate ok=true:
matching=12 бит-в-бит, changed=0, new=0** — четвёртый стабильный прогон гейта.

## §2 Одна попытка допуска

- Пара сохранена штатно (domains=YOUTUBE_DOMAINS + probe on + пара
  t/terms + CDN из VPN_FORMAT — URL, проверенный через VPN в 22:57).
- **SELECTIVE_SETTINGS_READY** на ревизии `821a5404…`; snapshot before снят
  до включения; admission-скрипт ТЗ (105с): mode POST принят → через ~95с
  **fallback** с телом: `{"state": "fallback",
  "reason": "youtube_cdn_probe_failed", "cdn_phase": "tls",
  "cdn_kind": "timeout", "vpn_control": "fail", "vpn_control_target": "cdn",
  "vpn_control_reason": "request_failed"}`.
- Ветка fallback выполнена по ТЗ: `snapshot route-admission-after` —
  **client_zapret2_rule=false** (правило снято, секций 11); обычный VPN
  (ipify) — работает; панель удерживает selective/fallback до ручного
  возврата.
- **Контекст флапа линии** (важно для интерпретации fail): в 22:26 и 22:57
  vpn-media 206; в 23:09–23:11 не прошёл и прямой TLS, и контроль кандидата
  через VPN; в 23:12 прямой probe того же URL снова **206 за 0.45с**
  (тот же узел `173.194.x.x`), ipify ок. Линия флапает с периодами отказа
  ~минуты — vp_control=fail попал в такой провал. Это отдельный факт о
  канале, не вердикт о коде кандидата: механизм контроля сработал
  (target=cdn корректен, причина зафиксирована), но результат «pass/fail»
  на флапающей линии неустойчив.

## Статусы

| Статус | Значение |
| --- | --- |
| UNIT_TESTS | PASS |
| DAEMON_BASELINE | ok=true — matching=12, changed=0, new=0 |
| INSTALL | PASS (6 файлов, off/off fresh) |
| ADMISSION | fallback: tls/timeout (одна штатная попытка) |
| CDN_VPN_CONTROL | target=cdn, **result=fail**, reason=request_failed |
| STATUS | NOT_RUN (ветка fallback) |
| LIVE_PLAY | NOT_RUN (ветка fallback) |
| FLOW | NOT_RUN |
| RESTORE | **VERIFIED** — rollback rc 0, **6/6 файлов cmp = базе `3a00777`**, sha256 OK, воркеры inactive, off/off fresh (6-й опрос), ipify ок, таймер остановлен |

## Наблюдения для Codex

1. **vpn_control на флапающей линии даёт неустойчивый результат**: тот же
   URL — 206 через VPN в 22:57, fail в 23:11, прямой 206 в 23:12. Стоит
   добавить в vpn_control повтор (2–3 попытки с интервалом) или окна
   ретраи, иначе «pass/fail» будет зависеть от точки замера на деградирующей
   линии.
2. Механика кандидата отработала штатно: fallback → правило снято
   (snapshot rule=false) → vpn_control выполнен с target=cdn → причина
   и фаза проб опубликованы в overview. Это ровно тот «измеримый результат
   при отказе», который запрашивало ТЗ.
3. Флап линии продолжается с вечера (DEGRADED×2 за 180с в пассивном окне,
   tls-таймауты в двух прогонах, минуты отказа). Гипотеза для проверки
   владельцем/провайдером: нестабильность аплинка в эти интервалы
   (прямые TLS-запросы к GGC и контрольные HTTPS отваливаются синхронно).
- Publication commit: `добавляется после push`.
