# Ubuntu 24.04 — T12: форма Selective и повтор TLS-пробы CDN (3d3e0f5) — 2026-11-18

- RESULT: **BLOCKED_TEST — целевой тест опубликованного комплекта падает, установка
  остановлена до apply** (по ТЗ: «Падение целевого теста останавливает установку»).
  `tests/test_zapret2_management.py::test_probes_are_write_only_preserved_when_omitted_
  and_explicitly_cleared` — **FAIL**: последовательность `{probe_urls: пара, transport:
  true}` → `{retry_seconds: 120}` → `{probe_urls: []}` — третий send возвращает
  `invalid` («Сохраните HTTPS-адрес страницы YouTube и HTTPS-адрес CDN googlevideo.com
  с путём /videoplayback или отключите HTTPS-проверку YouTube и CDN»), тест ожидает
  `ok`. **Точная причина (воспроизведена локально и локализована)**: в `candidate`
  (3d3e0f5) появился флаг `editing=action == "settings"` — любой settings-запрос
  считается редактированием, и валидация `valid_youtube_transport("selective",
  domains, probe_urls)` выполняется даже при `mode=off`: очистка probe_urls даёт
  `len(urls) != 2` → False → PolicyError. Тест закрепляет противоположное поведение
  (write-only проба, очистка разрешена при off). Машина не менялась: установка не
  начиналась, конфиги byte-identical, off/off, VPN/panel 200, воркеры inactive.
  Остальные наборы — 143 passed (zapret2, panel, management_linux, schema,
  route_evidence), node/bash — OK. Шаги ТЗ: тесты FAIL → установка/форма/Selective/
  медиа — NOT_RUN. Ждёт исправления Codex (одно из: пропускать transport-валидацию
  при очистке/опустошении probe_urls при off; либо запретить очистку только при
  активном transport-маршруте; либо обновить тест под новое правило).
- CODE: `3d3e0f551a805c7f8ecfd63e276bdf19f1c005ef`; база слоёв для установки: INFO
  `601238e`, MGMT `f3de005`, TLS `01379af` (cmp checks.py не выполнялся — остановка
  до prepare). Установка: **NOT_RUN**; таймер: NOT_RUN; машина в исходном состоянии.
- Финал: off/off, воркеры inactive, очередь пуста, VPN/panel 200, конфиги
  `89bf2a67…`/`33916cb5…`. Диск 45 ГБ свободно. Tcpdump отсутствует.
- Publication commit: `77cb8ad57008bf3059aa2d3e8a284fcc7d1c2ae6` (rebase поверх 56d6ade «Prioritize verified playback…», remote verified byte-identical to local HEAD).
