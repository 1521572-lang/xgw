# ThinkCentre · обновление CDN-пробы без повторного ввода страницы — 2026-11-20

- RESULT: **INSTALL PASS · API PASS · WEB PASS · QT PASS (offscreen-фикстура) ·
  LIVE_PLAY PASS (134.1с, 720p 100%) · FLOW=ZAPRET2 (qualified=1, unmatched=0)
  · LIVE_ACTIVE_UPDATE NOT_RUN · LIVE_EXPIRY NOT_RUN · RESTORE VERIFIED**.
  Кандидат `187653f` позволяет заменить только сохранённый CDN-адрес
  (`cdn_probe_url`): ревизия и срок CDN обновляются, вид пробы страницы
  остаётся `terms`, стратегия/бюджет не трогаются; конфликт по старой
  ревизии возвращает ту же новую; одинаковый адрес — `unchanged`; комбинация
  с `probe_urls` и адрес вне Googlevideo отклоняются. Веб-форма в реальной
  панели сохранила замену с пустым полем страницы; POST содержит ключ
  `cdn_probe_url`. Восстановление: rollback по manifest (хэши всех файлов =
  исходным), off/off fresh, таймер остановлен.
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee`); оверлей
  кандидата `187653f` (management, control, ui html/js, gui zapret2.py;
  GUI-релиз совпал с базой — `--gui` применён к `7c20f590…`); тесты
  кандидата: 58 passed (management/panel/schema) + `node --check` ок;
  sudo -n (NOPASSWD), NoNewPrivs=0.

## §1 Установка

prepare/apply complete; guard rollback 90м (`xgw-selective-cdn-update-rollback`);
VPN baseline: 206/65536 + delta xray +71КБ; off/off fresh подтверждён после
apply. Файл `install-location` записан (BACKUP/HELPER/PANEL/OVERLAY/UNIT).

## §2 API, веб-форма, Qt

- **Фикстура**: пара t/terms + истёкший r1-CDN сохранена → Selective
  заблокирован («Истёк срок адреса CDN»), `can_replace_cdn_probe=true` при
  истёкшем адресе, probe_count=2.
- **Замена только CDN** (страница пуста): ревизия сменилась
  (`2cba69dd`→`083dc2a1`), срок CDN 1→2000000000, вид страницы остался
  `terms`, режим off/off.
- **conflict** (старая ревизия): ok=false `conflict`, возвращён та же новая
  ревизия. **unchanged** (та же ревизия + тот же адрес): ok=true,
  changed=false. **Комбинация** `cdn_probe_url`+`probe_urls`: отклонена
  (`invalid`). **Не-Googlevideo CDN**: отклонён (`invalid`).
- **Пустые поля сохраняют пару** (unchanged). **Явная очистка**: probe_count=0,
  `can_replace_cdn_probe=false`, Selective заблокирован; попытка одного
  адреса после очистки — `blocked` (ревизия не изменилась — контент настроек
  оставался прежним до восстановления пары). Тестовая пара восстановлена
  (probe_count=2, page terms).
- **WEB (реальная форма в панели 8781, CDP-Chromium, cookie)**: оба поля
  пустые при открытии; страница оставлена пустой, введён только второй
  адрес — «Настройки сохранены»; перехваченный POST `/api/zapret2/settings`
  содержит `"cdn_probe_url"` и не содержит `probe_urls`; после сохранения
  ревизия сменилась, page kind `terms`, expiry обновлён (2000000001).
  Примечание: форма корректно работает только после «Перечитать настройки» —
  до загрузки числовые поля пусты и HTML5-валидация молча блокирует submit.
- **QT (offscreen `SettingsDialog.values()`, PyQt6, фикстура view)**: при
  открытии поля пусты; только второй адрес → `cdn_probe_url`; оба адреса →
  `probe_urls` (2); чекбокс очистки → `probe_urls=[]`. Реальная Qt-форма
  владельца не открывалась (панель работает на прежнем релизе) — проверка
  выполнена фикстурой из checkout, как допускает ТЗ.

## §3 Живой цикл

- Свежий 720p-формат из VPN (`rr5-…-5t`); замена только CDN (страница
  сохранена) — ревизия `c3583a51`. Selective на этом адресе — **fallback**
  (адрес подписан под VPN-выход; TLS к нему на пути воркера не проходит —
  согласуется с CDN-PEER). По допустимому повтору: Standalone-извлечение
  нового адреса того же ролика (206/65536 за 0.31с, узел `77.37.252.211`),
  возврат off, включение пробы и замена только CDN (два POST — комбинация
  «включить пробу + `cdn_probe_url`» отклоняется как `blocked`), ревизия
  `066b4241`→e5787a64.
- **Selective: fresh/matched/active/https_reachable** на прямом адресе.
- **trace_playback**: первая попытка — inconclusive (`snapshots_incomparable`:
  конфиг изменился посреди окна — семантический sha снапшотов разный при
  неизменном правиле true); вторая (повтор тех же команд на active):
  **`{"client_zapret2_rule": true, "groups": {"zapret2": 1},
  "qualified_flows": 1, "unmatched": {}}`** — медиасоединение плеера
  атрибутировано outbound zapret2. Плеер: **ok=true, 134.1с eligible,
  прогресс 99.7%, 720p 100%, stall 1.0с, gaps 0**. После фазы selective
  оставался active/https_reachable.
- **LIVE_ACTIVE_UPDATE=NOT_RUN**: второго действующего адреса того же ролика
  в том же окне нет — адрес, действующий на пути воркера, даёт только
  Standalone-извлечение, а оно требует покинуть Selective.
- **LIVE_EXPIRY=NOT_RUN**: естественного истечения за время опыта не
  наступало; fallback на VPN-подписанном адресе учтён как фаза отказа, не
  как истечение.

## §4 Откат и восстановление

off/off через панель до guard; guard rollback rc 0; marker; sha256
config+panel OK; **manifest-проверка: все заменённые файлы вернулись к
исходным хэшам (4–5 файлов, каждый сверён)**; xgw.service active; воркеры
MainPID=0; off/off fresh (после ~5 опросов — панель применяла ревизию);
ipify ок; таймер остановлен (ActiveState=inactive) → **RESTORE VERIFIED**.

## Наблюдения для Codex

1. **Стартовый барьер формы**: до «Перечитать настройки» числовые поля пусты
   и HTML5-валидация молча блокирует отправку (никакого сообщения) — стоит
   либо автозагрузку при открытии редактирования, либо сообщение валидации.
2. **Многошаговый цикл замены**: «включить HTTPS-пробу + `cdn_probe_url`»
   одним POST отклоняется (`blocked`), а включение Standalone требует
   предварительного выключения пробы. Замена CDN в живом цикле заняла
   4 шага режима (selective→off→standalone→off→selective). Возможно
   упростить: разрешить включение пробы вместе с `cdn_probe_url`, когда
   сохранённая страница остаётся `terms`.
3. **Снапшоты route_evidence несравнимы при Accounting-записях конфига**:
   семантический sha панели меняется посреди окна (бюджет/состояние пробы),
   что ломает сопоставимость без реального изменения политики — фоновая
   причина inconclusive первой попытки. Стоит исключить летучие поля из
   semantic sha.
4. Запись кнопки «Сохранить CDN-пробу без подпис» видна в форме — путь
   persistent-пробы не проверялся в этом проходе (по ТЗ).
- Publication commit: `840dd03d14771bb6f4cdaf000ffadd1af3c21d28` (9323c38 → 840dd03, ancestor verified).
