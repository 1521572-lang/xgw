# Ubuntu 24.04 — T12: источник проб и перепроверки Selective (601238e) — 2026-11-17

- RESULT: **PASS по форме/подстановке/диагностике rechecks; стабильность Selective не
  подтверждена — после успешного recheck №1 следующий цикл ушёл в fallback
  youtube_cdn_probe_failed (elapsed 10106 мс ≈ TLS-бюджет 10 c исчерпан)**; разрешённый
  повтор со свежей CDN и той же страницей условий — тоже youtube_cdn_probe_failed
  (tls timeout 10133 мс) → сетевая фаза завершена, accept (4/4 new_sha). Диагностика
  r5 подтвердила механизм: recheck №1 при той же ревизии 7417acd8 и page_kind=terms
  показал новые started_at и время 1066/344 мс — успешная перепроверка работает;
  отказ №2 — tls timeout при CDN (page прошёл за 743 мс), как и в T12. Точная
  первопричина циклических CDN-TLS таймаутов остаётся у Codex (r3: CDN 360 мс
  стабильно; r4/r5: таймауты непредсказуемо — проба по probe-пути при том же direct
  200/0.39 c).
- Дополнительно найден и задокументирован **дефект сценария off→selective при
  transport_probe=true** (локализован точно): panel сохраняет transport_probe=true и
  10 доменов при off (это валидно), но mode-endpoint → selective отклоняется
  (`youtube_transport_probe requires Selective and two YouTube URLs`), потому что
  panel.domains (10 доменов r1-наследие) не являются подмножеством YOUTUBE_DOMAINS.
  Чинится сохранением настроек с 6 доменами r3 через settings-endpoint (задокументи-
  ровано и выполнено). Рекомендация Codex: либо приводить domains к 6 при сохранении
  transport_probe=true в off, либо сообщение об этом в форме.
- CODE: `601238ef053447e1287be918864f8c839e1a3cf4`; база: zapret2.py — TLS `01379af`
  (сверка cmp OK), zapret2_control/html/js — r3 `a8b177f`. Установка 4/4 манифест ==
  new_sha: zapret2.py `08fb3c0b…`, zapret2_control.py `6d94d417…`, zapret2.html
  `901d2573…`, zapret2.js `326b8ec1…`. Таймер 90 м armed до apply; конфиги
  byte-identical.
- §1 тесты: **89 passed** (zapret2, panel, management, route_evidence) + `node --check`
  + `bash -n`. Место 45 ГБ.
- Финал: off/off, воркеры inactive, очередь пуста, VPN/panel 200, конфиги
  byte-identical. Слой `601238e` оставлен (accept). Tcpdump отсутствует; место 45 ГБ.

## §1 Подготовка — PASS

- Манифест TLS 2/2 на машине (не сверялся здесь — задействован в §2 cmp); 89 тестов;
  off/off; панель/VPN 200. Свежая CDN-пара — из DevTools того же Chrome.

## §2 Установка — PASS

- checks.py == принятая TLS-версия (cmp OK — BLOCKED_BASE не было). Таймер armed
  13:32 МСК + 90 мин; apply; конфиги OK; manifest new 4/4.

## §3 Форма, подстановка и запуск — PASS (с оговоркой)

- Кнопка «Подставить страницу условий YouTube» появляется **только с включённой
  HTTPS-опцией** и скрыта при выключении/удалении адресов; подставляет
  `https://www.youtube.com/t/terms` в поле страницы, фокус в поле CDN (по коду;
  через CDP фокус на BODY — отмечено как артефакт программного клика, мышью не
  пере-проверено).
- Комплект: multisplit + 6 доменов r3 + интервал 120 + transport + пара URL →
  `saved`. Форма показывает «Страница условий»; API `probe_page_kind=terms`;
  `transport_probes={}` до запуска. 390 px читаем; подпись отсутствует в GET/POST.
- Честная оговорка: первый клик кнопки Selective — в устаревшем рендере вкладки
  (disabled); включение выполнено через mode-endpoint (тот же контракт, что кнопка).
  Это легитимный путь панели (кнопка шлёт тот же POST).

## §4 Rechecks — PASS частично / стабильность НЕ подтверждена

- Активация 18:19:43Z, ревизия 7417acd8: **probe 1**: page ok/200/57247 Б/848 мс/
  page_kind=terms/started_at …566; CDN ok/200/31 Б/360 мс/started_at …567.
- **Recheck 1 (успешный, ~135 c)**: та же ревизия и page_kind, новые started_at
  …701/…702, page 1066 мс, CDN 344 мс — «Повторная успешная проба должна показать
  новое время при той же ревизии и том же типе страницы» — **подтверждено**.
- **Recheck 2 (fallback, ~285 c)**: `fallback / youtube_cdn_probe_failed`, page
  ok/743 мс, **cdn {phase:tls, kind:timeout, bytes:0, elapsed_ms:10106}** — TLS-бюджет
  10 c исчерпан. При том же direct GET (200/0.39 c). State при неизменных настройках —
  задокументирован.
- **Разрешённый повтор (по ветвлению CDN)**: off кнопкой (policy_matched/off,
  probes очищен), свежая CDN из DevTools, та же страница условий, settings `saved`,
  mode selective `unchanged` (mode уже selective — корректно), включение →
  **fallback / youtube_cdn_probe_failed, cdn {phase:tls, kind:timeout,
  elapsed_ms:10133}** при page ok/507 мс. Стабильность Selective **не подтверждена**:
  CDN-проба через probe-путь флапает между 274–360 мс (r3/успех) и 5–10 с таймаутом.

## §4 Видео и дельты — NOT_RUN

- Активная фаза была (60+135 c active в наблюдении), но устойчивого окна для
  ≥150 c видео при стабильных пробах не получилось: recheck 2 ушёл в fallback.
- Дельты: пары через смену конфигурации отвергаются прибором (field=applied_config,
  проверено в T12); в активном окне recheck-пары не снимались — интервал наблюдения
  был потрачен на слежение за probes. MEDIA_PATH: PARTIAL (прошлые данные r3
  подтверждали путь, текущий раунд не добавил пары).

## §5 Выключение и возврат — PASS

- Off кнопкой → policy_matched/off, probes очищен; **новый сеанс YouTube через VPN** —
  дельта xray **+647 КБ / 33.6 c**, client_rule=false.
- Restore **accept**: panel byte-identical (OK/OK), verify_manifest new 4/4 на диске,
  off/off подтверждён (mode=off, engine=off), Proton работает, panel/VPN 200.
- Таймер остановлен после сверки; бэкап сохранён. Тестовые Chrome закрыты.

## Наблюдения для Codex

1. **Дефект off→selective при transport_probe=true и доменах ≠ 6**: panel допускает
   сохранение transport=true при off с любыми доменами, но mode-endpoint затем
   отклоняется. Рекомендация: предупреждение в форме (при transport=true требовать
   ровно 6 доменов r3) либо авто-нормализация доменов.
2. **CDN-TLS таймауты**: циклическое поведение (r3 — стабильно быстро; r4/r5 —
   флап). Данные r5: page-проба проходит стабильно (666/848/743/507 мс), CDN —
   360/344 мс в успехе и 5147/10106/10133 мс таймауты. Указание на зависимость от
   состояния очереди/меток в момент probe (zapret2_live/рейт-лимит) сохраняется.
3. Recheck-диагностика (started_at/page_kind/elapsed) — работает как задумано.
4. Длинный опыт — переносится после стабилизации CDN-пробы.
- Publication commit: добавить после push.
