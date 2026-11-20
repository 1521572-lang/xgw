# ThinkCentre · открытие формы, замена CDN и сопоставимость снимков — 2026-11-20

- RESULT: **INSTALL PASS · WEB_FIRST_OPEN PASS · WEB_VALIDATION PASS ·
  ATOMIC_CDN PASS · QT PASS (offscreen-фикстура с флажком) · SNAPSHOT_DIFF
  PASS-механизм (секции видны; в живом окне отказ атрибутирован:
  `changed_sections=["routing","inbounds","outbounds"]`) · LIVE_PLAY PASS
  (135.1с, 720p 100%, stall 0) · FLOW PARTIAL (атрибуция несравнимости
  подтверждена, владелец перезаписи конфига не установлен; принятый
  FLOW=ZAPRET2 из отчёта 11:14Z остаётся в силе) · LIVE_ACTIVE_UPDATE
  NOT_RUN · LIVE_EXPIRY NOT_RUN · RESTORE VERIFIED**.
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee` — сверена с
  исходным пакетом, не с временным `187653f`); кандидат `946a869`
  (management, control, ui html/js, gui; GUI-релиз совпал — `--gui`
  применён); тесты кандидата: **170 passed** (management/panel/schema/
  route_evidence/probe_watch) + `node --check` ок + негативный контроль
  `test_live_snapshots_compare_reformatted_config_and_reject_routing_order_changes`
  — PASS (field=applied_config, changed_sections=["routing"]). sudo -n.

## §1 Установка

prepare/apply complete; guard rollback 90м; VPN baseline 206/65536 + delta
xray +71КБ (окно 1.1с); off/off fresh после apply. `install-location`
записан. cdn-off: off/off fresh.

## §2 Веб и Qt

- **Исходная пара**: t/terms + истёкшая r1-фикстура при **выключенной**
  HTTPS-проверке → overview: `probe_count=2`, `can_replace_cdn_probe=true`,
  `youtube_transport_probe=false`.
- **WEB_FIRST_OPEN=PASS**: два клика «Настроить» на свежеперезагруженной
  странице (второй — во время очередного GET overview): форма появляется
  уже заполненной из overview — check=180, retry=300, budget=256,
  `formValid=true`, адресные поля пусты, «Перечитать настройки» не
  использовалась.
- **WEB_VALIDATION=PASS**: интервал 0 → видимое сообщение «Заполните
  обязательные поля. Проверьте интервалы и бюджет.», POST отсутствует,
  черновик сохранён (значение 0 осталось в форме); сохранение только
  страницы → «Для замены заполните оба адреса.», POST отсутствует.
- **ATOMIC_CDN=PASS**: в форме флажок HTTPS-проверки + пустая страница +
  только второй адрес-фикстура → **один POST** с `youtube_transport_probe:
  true`, `cdn_probe_url` и текущим `expected` (тела запроса: поля strategy/
  domains/интервалы присутствуют как есть); «Настройки сохранены»; одна
  новая ревизия (`d3d9e47a`→`1089391d`), `page_kind=terms`, новый срок CDN
  (2000000003), off/off. Конфликт по старой ревизии — `conflict` с
  возвратом текущей. **POST только с новым адресом CDN при выключенной
  опции** (без `youtube_transport_probe=true`) — отклонён (`blocked`).
- **QT=PASS (offscreen-фикстура)**: диалог кандидата содержит флажок
  «HTTPS-проверка YouTube и CDN»; флажок + только CDN → `values()`
  содержат `youtube_transport_probe=true` и `cdn_probe_url` (без
  `probe_urls`). Реальное окно владельца не открывалось (панель на прежнем
  релизе) — как допускает ТЗ, указана фикстура.
- **Старые действия подтверждены**: оба адреса → полная пара (count=2);
  очистка → count=0, can_replace=false, ревизия сменилась; атомарное
  включение после очистки требует полной пары (иначе `blocked`); смена
  ревизии в другом окне: форма синхронизирует expected при submit —
  сохранение с устаревшим черновиком не выполнило POST и не изменило
  ревизию; конфликт на уровне API подтверждён (`conflict` + текущая
  ревизия в ответе).

## §3 Снимки Xray и живой контроль

- **SNAPSHOT_DIFF**: снимки кандидата содержат `config_sections_sha256`
  (11 секций Xray: routing, outbounds, inbounds, api, dns, log, metrics,
  policy, stats, burstObservatory, other). Положительный контроль:
  оф-окно (site между снимками) — сравнение допускается, дельта xray
  +74 389 (1.14с), правило false. Негативный контроль — тест пройден
  (см. §1). **Живое окно**: inconclusive теперь атрибутирован —
  `field=applied_config`, **`changed_sections=["routing","inbounds",
  "outbounds"]`**: конфиг Xray перегенерировался посреди окна воспроизведения
  (правило zapret2 true в обеих границах, epoch не менялся). Кто выполнял
  перезапись — не установлено (в объём ТЗ не входит).
- **Живой цикл одним POST**: Standalone-извлечение действительного адреса
  (206/65536, 0.11с, узел из принятой пары); один POST
  `strategy=fake_md5 + youtube_transport_probe=true + cdn_probe_url` →
  Selective **fresh/matched/active/https_reachable** (~80с). Примечание: до
  этого с сохранённой стратегией hostfakesplit_md5 тот же адрес дал
  fallback — фаза отказа записана; к замене CDN отношения не имеет.
- **LIVE_PLAY=PASS**: mpv 135.1с eligible, прогресс 99.4%, 720p 100%,
  stall 0, gaps 0 (второе окно: 134.1с, stall 1.0с).
- **FLOW=PARTIAL**: сопоставление потока в обоих свежих окнах —
  inconclusive из-за подтверждённой перезаписи конфига (см. выше); группа
  выхода в этих окнах не засчитана. Принятый `FLOW=ZAPRET2` из
  [отчёта потока](2026-11-20T111437Z_selective-flow-evidence.md) остаётся
  сведением; новый инструмент корректно называет changed_sections вместо
  немого отказа.
- **LIVE_ACTIVE_UPDATE=NOT_RUN** — второго действующего адреса в окне нет.
  **LIVE_EXPIRY=NOT_RUN** — естественного истечения не наступало
  (фикстуры в живых запросах не участвовали).

## §4 Откат

off/off через панель; guard rollback rc 0; marker; sha256 config+panel OK;
manifest: **5 файлов вернулись к исходным хэшам**; xgw.service active;
воркеры inactive; off/off fresh (после ~6 опросов); ipify ок; таймер
остановлен (ActiveState=inactive) → **RESTORE VERIFIED**.

## Наблюдения для Codex

1. **Атрибуция changed_sections работает** и сразу дала результат:
   перегенерация routing/inbounds/outbounds посреди живого окна — вероятный
   источник прежних `snapshots_incomparable`. Следующий шаг — найти писателя
   (кандидаты: демон при персистентности бюджета/состояния проб, tray,
   отложенный apply) и либо устранить перезапись без изменения политики,
   либо исключить эти секции из semantic-сравнения, когда правило и epoch
   неизменны.
2. Первое открытие формы и валидация без POST работают как задумано;
   автозагрузка устранила молчаливый блок HTML5-валидации из прошлого
   прохода.
3. Атомарная запись «флажок + CDN» одним POST подтверждена и в веб-форме,
   и в Qt-диалоге, и в API; попытка заменить CDN при выключенной опции
   отклоняется — контракт цельный.
4. Стратегия hostfakesplit_md5 не проходит HTTPS-допуск на этой линии
   (fallback на действующем адресе) — согласуется с матрицей CDN-PEER, где
   два pass дали только fake_md5/multidisorder.
- Publication commit: `839e624188b468b5784ca87a5397423d0ac3e870` (a6971e9 → 839e624, ancestor verified).
