# Ubuntu 24.04 — T12 r2: очистка адресов при off и повтор TLS-пробы CDN (a382971) — 2026-11-18

- RESULT: **CLEAR_OFF=PASS — весь §2 формы (off-контракт адресов) принят; реальный клик
  Selective принят; сетевая фаза завершена по ветвлению «ошибка страницы»: page-проба
  `/t/terms` упала в TLS-таймаут 10 137 мс → `fallback/youtube_page_probe_failed`,
  CDN-проба не начиналась → RETRY_LIVE=NOT_RUN, MEDIA_PATH=NOT_RUN (видео и rechecks —
  NOT_RUN)**. Исправление `a382971` подтверждено: целевой тест из BLOCKED_TEST
  `test_probes_are_write_only_preserved_when_omitted_and_explicitly_cleared` — **PASS**,
  полный набор **162 passed** (zapret2, panel, management, management_linux, schema,
  route_evidence) + `node --check` + `bash -n`. Установка 6/6 манифест, cmp checks.py
  OK (BLOCKED_BASE не было), таймер armed до apply, конфиги byte-identical.
  §2: кнопка «Заменить список на домены YouTube» скрыта до включения HTTPS-опции и
  видима после; клик меняет только черновик (POST нет); сохранение с лишним
  `domain:example.org` → `invalid` с подсказкой о доменах, `config_key` не изменился,
  sha-проверка OK/OK; подстановка доменов == 6 строк `youtube_domains` API; сохранение
  комплекта (multisplit, retry 120, HTTPS, страница `/t/terms` + фикстура CDN) →
  `saved`, новая ревизия, off/off, probe_count=2, page_kind=terms, probes={},
  воркеры не стартовали, подпись фикстуры не отражена в GET/ответах. CLEAR_OFF:
  «Удалить сохранённые адреса» → `saved`, probe_count=0, transport=true, page_kind
  сброшен, подсказка в `blockers.selective`, кнопка Selective недоступна, воркеры
  inactive; фикстура удалена из хранилища (байтовая проверка panel.json); повторная
  очистка → `unchanged`, та же ревизия. Свежий CDN из DevTools тестового Chrome
  (GET 200 до сетевой фазы) + `/t/terms` → `saved`, probe_count=2, off/off,
  `blockers.selective` пуст. Клик: первый — на устаревшем disabled-рендере карточки;
  после перезагрузки вкладки карточка «Загрузка…» из-за occlusion окна Chrome
  (фронтенд останавливает poll при document.hidden и не перепланирует его);
  после возврата видимости — свежий рендер, кнопка доступна, **реальный клик** →
  POST принят → `mode=selective`. Попытка: preparing/nfqueue (multisplit, очередь 200)
  → fallback/youtube_page_probe_failed: page {phase:tls, kind:timeout, http:0,
  bytes:0, elapsed_ms:10137, page_kind:terms} ≈ TLS-бюджет 10 c; автоповтора нет
  (контракт «ошибка страницы» соблюдён), CDN не тестировалась, воркеры остановлены,
  прямых правил нет, VPN жив (ipify 200). Диагностика при fallback: direct GET
  той же страницы — 200/0.69 c/57 247 Б; direct GET того же CDN — 200/1.03 c/31 Б —
  расхождение probe-путь/direct (как в r4/r5, теперь на page-пробе). По ТЗ «при
  другом отказе заверши сетевую фазу»: новый сеанс со свежим CDN не проводился
  (разрешён только при CDN-отказе). Off кнопкой → off/off; **новый сеанс YouTube
  через VPN — дельта ACCEPTED: client_rule=false, xray +14.7 МБ downlink** (окно
  224 c). Возврат **accept**: конфиги OK/OK, манифест new 6/6 на диске, xgw active,
  воркеры inactive, VPN/panel 200, таймер остановлен до срабатывания (за 49 мин),
  тестовый Chrome закрыт. Решение accept: форма/CLEAR_OFF/клик/возврат исправны,
  слой отработал штатно (честный fallback, автоповтор не запускался), регрессии
  установки нет; TLS-отказ страницы — «отрицательный результат по устойчивости»,
  не регрессия слоя.
- CODE: `a382971f162db53a8bd7435f124d591b6a5287fa`; база для установки: INFO
  `601238e`, MGMT `f3de005`, TLS `01379af` (cmp checks.py == принятая TLS-версия).
  Манифест new (6): zapret2.py `7f353891…`, zapret2_control.py `e80d9be8…`,
  zapret2.html `183d5f55…`, zapret2.js `0a35c635…`, schema.py `0e1fe97e…`,
  zapret2_management.py `a4d22612…`. Установка: apply complete; таймер 90 м armed до
  apply (NEXT 02:09:06 МСК), остановлен после сверки.
- §1 тесты: **162 passed**, включая прежний упавший целевой тест — PASS; node/bash OK.
  Место 45 ГБ свободно; tcpdump отсутствует.
- Адреса до/после: до раунда transport=false, probe_count=0; в §2 сохранена пара
  (2 адреса) → очистка (0, транспорт остался включён) → повторная очистка
  `unchanged` → снова пара (2) для сетевой фазы → после off кнопкой probes очищены
  ({}), настройка пары сохранена в off (probe_count=2, transport=true) — всё по
  write-only контракту, подписи не отражались в API-ответах.
- Финал: off/off, воркеры inactive, VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`
  byte-identical, слой `a382971` оставлен (accept). Диск 45 ГБ.

## Таблица проб (попытка 1, UTC 01:08:05–01:09:46 МСК)

| Проба | Результат |
| --- | --- |
| page (`/t/terms`) | `{ok:false, phase:tls, kind:timeout, http:0, connect_http:0, bytes:0, elapsed_ms:10137, page_kind:terms}` — TLS-бюджет 10 c исчерпан |
| CDN | не начиналась (страница отказала первой) |
| `first_tls_timeout_ms` | отсутствует (повтора не было) |
| Состояние | preparing/nfqueue → fallback/youtube_page_probe_failed, policy_matched=true, ревизия `86fc608c…` |
| Прямые правила/воркеры после fallback | 0 правил, оба воркера inactive |

- RETRY_LIVE=**NOT_RUN** (CDN-повтор не достижим — отказ страницы). MEDIA_PATH=**NOT_RUN**
  (active-фазы не было). Пригодного 720p в Selective: 0 с (NOT_RUN).

## Наблюдения для Codex

1. **TLS-таймаут пробы расширился с CDN на страницу**: в r4/r5 page `/t/terms`
   проходила за 380–1066 мс, отказывал только CDN; сейчас страница упала в 10,1 с
   при живом direct (200/0.69 c). Проба через probe-путь флапает независимо от цели
   — указывает на состояние очереди/пути пробы в момент запуска, а не на конкретный
   хост.
2. Occlusion-артефакт фронтенда: при скрытом окне Chrome карточка остаётся
   «Загрузка…» навсегда (refresh() выходит при document.hidden и не перепланирует
   poll-цепочку). После возврата видимости карточка не оживает сама — требуется
   перезагрузка вкладки/событие. В реальном использовании окно видно, но отдельная
   вкладка zapret2 в фоновом окне — штатный сценарий.
3. CLEAR_OFF-контракт (awaiting_urls) и write-only хранение работают как задумано,
   включая запрет активации Selective до ввода адресов и `unchanged` на повторную
   очистку.
- Publication commit: `1916103078d2436a8ee8289e9a172ef0180fe512` (f4a6668 → 1916103, remote verified byte-identical to local HEAD).
