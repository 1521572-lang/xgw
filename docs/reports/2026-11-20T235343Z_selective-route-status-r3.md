# ThinkCentre · отложенный CDN VPN-контроль (r3) — 2026-11-21

- RESULT: **UNIT_TESTS PASS · DAEMON_BASELINE ok=true (matching=12, changed=0,
  new=0) · INSTALL PASS (6 файлов) · ADMISSION: одна попытка → fallback
  (cdn tls/timeout) · CDN_VPN_CONTROL: target=cdn, result=**fail**,
  reason=request_failed; **попытка задокументирована детально: phase=headers,
  kind=http, HTTP 302, bytes=0** — retry_pending=false, вторая попытка не
  назначалась (HTTP-отказ завершает контроль одной попыткой по контракту) ·
  STATUS/LIVE_PLAY/FLOW NOT_RUN (ветка fallback) · RESTORE VERIFIED (6/6)**.
- ОС: Ubuntu 24.04.5 LTS; база 11/11; кандидат `25b4b94` — те же 6 файлов
  (applier, singbox_generation, daemon, control, management, zapret2.py);
  VPN_FORMAT fresh (23:37, 206/65536 через `173.194.x.x`); sudo -n; тесты
  обычным пользователем.

## §1 Гейт

Обе копии из `25b4b94`; baseline = кандидат с 6 файлами от `3a00777`
(diff-only 6 имён). writer-unit rc=0; daemon rc=1/1; **gate ok=true:
matching=12, changed=0, new=0** — пятый стабильный прогон.

## §2 Одна попытка допуска (расширенное окно 105+75с)

- Пара (domains=YOUTUBE_DOMAINS + probe on + t/terms + CDN из VPN_FORMAT)
  сохранена штатно; **SELECTIVE_SETTINGS_READY** (ревизия `3b260751…`);
  snapshot before снят.
- Admission-скрипт r3: mode POST принят → **fallback**
  (youtube_cdn_probe_failed, cdn tls/timeout) с **новыми полями
  retry_pending=false и attempts=[...]** — прямой TLS-таймаут повторился
  (линия всё ещё деградировала в окне 23:50–23:51).
- **Попытка vpn_control #1 (единственная)**: верdict=fail,
  reason=request_failed, at=1795218686.65 (≈95с после mode POST),
  **phase=headers, kind=http, http=302, connect_http=0, bytes=0**.
  CDN-URL через VPN ответил **редиректом 302** — кандидат корректно
  классифицировал не-206 как отказ и зафиксировал фазу/код/байты.
  Вторая попытка не назначалась: HTTP-отказ завершает контроль одной
  попыткой (контракт кандидата), retry_pending=false.
- Ветка fallback по ТЗ: `route-admission-after` — **client_zapret2_rule=
  false** (правило снято); обычный VPN (ipify) — работает.

## Бонус-диагностика линии (приватно, агрегаты в отчёт)

- Через ~2 мин после допуска: прямой recheck того же CDN-URL — **HTTP 200**
  (curl без Range; прямой путь снова отвечает!). Последовательность за
  5 минут: TLS-таймаут (проба панели) → 302 через VPN (контроль) → 200
  напрямую (recheck). Линия продолжает резкие флапы между состояниями
  «TLS не отвечает» / «отвечает редиректом» / «отвечает полностью».
- Гипотеза о природе 302 через VPN: перебалансировка GGC (redirect на
  другой кеш) при несовпадении фактического IP с подписью в момент запроса
  через VPN-выход — совпадает с нестабильностью маршрутизации на линии.

## Статусы

| Статус | Значение |
| --- | --- |
| UNIT_TESTS | PASS |
| DAEMON_BASELINE | ok=true — matching=12, changed=0, new=0 |
| INSTALL | PASS (6 файлов, off/off fresh) |
| ADMISSION | fallback: tls/timeout (одна попытка) |
| CDN_VPN_CONTROL | target=cdn; попытка #1: fail/request_failed, http=302, bytes=0; попытки #2 не было (HTTP-отказ завершает) |
| STATUS | NOT_RUN (ветка fallback) |
| LIVE_PLAY | NOT_RUN |
| FLOW | NOT_RUN |
| RESTORE | **VERIFIED** — rollback rc 0, **6/6 cmp = базе `3a00777`**, sha256 OK, воркеры inactive, off/off fresh (2-й опрос), ipify ок, таймер остановлен |

## Наблюдения для Codex

1. **Новый класс отказа vpn_control: HTTP 302 через VPN**. Текущий контракт
   классифицирует любой не-206 как fail — корректно для строгости, но
   диагностически полезно различать: 302 (перебалансировка GGC) vs
   request_failed (сеть) vs 403 (подпись). Рекомендация: сохранять
   Location-хост редиректа как отдельное поле (privatно), чтобы видеть,
   куда перенаправляет кеш.
2. Линия в режиме сильного флапа три состояния за 5 минут (timeout / 302 /
   200). Измерения допуска в такое окно дают лотерейный исход — любая
   будущая проверка route_reconcile должна сначала зафиксировать
   «стабильность линии» (например, 3 прямых probe с интервалом 30с подряд
   до постановки допуска).
3. Механика r3 (retry_pending/attempts в overview) работает: попытка
   видна с полными деталями, контракт «HTTP-отказ завершает одной
   попыткой» соблюдён.
- Publication commit: `добавляется после push`.
