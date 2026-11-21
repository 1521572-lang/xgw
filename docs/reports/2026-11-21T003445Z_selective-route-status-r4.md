# ThinkCentre · контроль CDN через VPN с переходом и статус Selective после ротации (r4) — 2026-11-21

- RESULT: **§1 PASS (тесты кандидата `39421a6` из ветки: writer-unit 109/109,
  route-unit 134/134 — включая новые `test_zapret2_redirect.py`, route-rebuild
  1/1; daemon-gate ok=true: 158/158 у обеих сторон, matching=12 бит-в-бит,
  changed=0, new=0, added=0, missing=0), §2 УСТАНОВКА PASS (6/6 файлов =
  кандидату, cmp, таймер 90м, off/off после рестарта) и ДОПУСК = FALLBACK
  при полностью работающем новом механизме перехода**: прямой путь снова
  TLS-таймаут (20.3с, первый 10.2с) — `youtube_cdn_probe_failed`; контроль
  того же CDN URL через VPN получил **HTTP 302 и единственный разрешённый
  переход совершил: следование на другой хост (host_changed=true), второй
  адрес тоже ответил 3xx → state=hop_limit**, вердикт `fail`,
  причина `cdn_redirect_unconfirmed` (новая, из кандидата), повтор
  не назначался (retry_pending=false). VPN обычный жив на всём окне
  (ipify совпал с прежними проходами; через минуту тот же URL через VPN —
  206/65536). §3 NOT_RUN по ТЗ (fallback): STATUS=NOT_EXERCISED,
  LIVE_PLAY/FLOW NOT_RUN. §4 RESTORE VERIFIED (6/6 = базе, SHA OK,
  off/off settled, таймер остановлен inactive/dead).
- ОС: Ubuntu 24.04.5 LTS; ядро 7.0.0-43; mpv 0.37.0; yt-dlp 2026.10.26;
  curl 8.5.0; кандидат `39421a6…` (поверх базы `3a00777…` = `08d31ee…`
  + 5 файлов); наблюдение ротации на установленном кандидате в этом
  проходе не выполнялось — это окно только про допуска/переход.

## §1 Тесты и установка

| Набор | Итог |
| --- | --- |
| writer-unit (applier, sing-box generations, route_evidence, probe_watch, gate) | 109/109, rc=0 |
| route-unit (zapret2_panel, zapret2, **zapret2_redirect**) | 134/134, rc=0 |
| route-rebuild (daemon tick restores VPN after worker death) | 1/1, rc=0 |
| daemon NEW vs OLD | rc=1/rc=1 (158 cases обе стороны), matching_baseline_failures=12, changed_failures=[], new_failures=[], added_tests=[], missing_tests=[], new_skips=[], ok=true |

- Обе копии worktree из ОДНОГО коммита `39421a6`; baseline = тот же коммит
  с 6 файлами, восстановленными из базы. Один интерпретатор, обычный
  пользователь. VPN-контроль до таймера: свежий формат (видео 10.2ч,
  720p mp4, формат 398) — **проба 206/65536 через VPN** (окно здоровья
  линии, 00:15Z).
- Установка: payload/backup под `/opt/xgw/handoff` и `/var/lib/xgw/handoff`,
  cmp 6/6 (`applier.py`, `singbox_generation.py`, `daemon.py`,
  `zapret2_control.py`, `zapret2_management.py`, `zapret2.py`) = кандидату;
  наблюдатель `selective_route_status_watch.py` в payload — побайтовое
  совпадение с деревом кандидата; sha256 config.toml+panel.json OK;
  таймер 90м active; после рестарта демона off/off fresh.

## §2 Один допуск Selective

- before-settings: SELECTIVE_SETTINGS_READY (fake_md5, 10 доменов,
  youtube_transport_probe, check 180с, retry 120с, бюджет 512 МБ/сут,
  probe_urls [terms, CDN URL формата]).
- Допуск (окно ~00:29–00:31Z): POST mode selective принят; итог —
  **fallback / youtube_cdn_probe_failed**; транспорт CDN: phase=tls,
  kind=timeout, elapsed 20295мс, first_tls_timeout 10217мс — та же
  подпись, что в r3.

**CDN_VPN_CONTROL** (target=cdn, `VPN_CONTROL_SECONDS=8`):

| Попытка | t (rel) | verdict | reason | phase/kind | http | bytes | redirect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #1 | +21с после старта CDN-пробы | fail | **cdn_redirect_unconfirmed** | headers/http | 302 | 0 | {http:302, state:**hop_limit**, host_changed:**true} |

- **REDIRECT=OBSERVED**: CDN ответил через VPN 302 уже в фазе заголовков;
  кандидат совершил единственный разрешённый переход: цель — https,
  путь `/videoplayback`, домен в белом списке, не literal-IP,
  **хост сменился** (host_changed=true — подпись перебалансировки GGC,
  как в r2/r3). Второй адрес **тоже ответил 3xx** → state=hop_limit —
  контроль по классификации ТЗ **незавершённый** (не `followed`+206,
  не `followed`+403): диапазон видео через VPN подтверждён не был.
- Повтор: **retry_pending=false** — полученный HTTP-ответ завершает цикл
  пробы (согласуется с r3), переход списал попытку (повторная запись
  watchdog не назначалась). Вторая запись watchdog в окне не видна.
- Прямой маршрут закрыт и остался закрыт: `client_zapret2_rule=false`
  на обеих границах снапшотов; оба воркера inactive после снятия.
- Обычный VPN: ipify 200 (тот же выход, что в r2/r3), через ~60с после
  вердикта контрольная проба того же URL через VPN — **206/65536**:
  URL доступен через VPN в это время; цепочка 302→3xx — свойство
  CDN-балансировки, а не недоступность.
- Снапшоты допуска: changed_sections=[routing,inbounds,outbounds]
  (несопоставимы, как в r2/r3 — штатная перезапись при смене режима),
  xray_epoch на границах совпал. Статус панели: «Прямой путь отключён»,
  деталь отрендерила новые строки («CDN перенаправил запрос через VPN.
  Диапазон видео не подтверждён.») — новая ветка detail работает.
- Плеер и ротация: NOT_RUN (fallback по ТЗ). Одно отклонение от блока ТЗ
  в исполнении: первый запуск блока допуска был прерван локальной
  ошибкой окружения (имя функции перекрылось системной утилитой) до POST
  mode — режим оставался off/off, блок повторён один раз; POST на
  ревизию — один.

## §3 Наблюдение статуса — NOT_RUN

STATUS=NOT_EXERCISED (окно наблюдения требует успешного прямого допуска),
LIVE_PLAY=NOT_RUN, FLOW=NOT_RUN, счётчики `active_with_rule` /
`route_reconcile` / `active_without_rule` не набирались.

## §4 Откат

- guard rollback rc=0 → restore-completed; sha256 config.toml+panel.json OK;
  **файлы 6/6 = базе** (`3a00777`/`08d31ee`, cmp); xgw.service active;
  воркеры inactive; off/off: после отката штатно settling ~20с
  (pending/stopping → off — как и при старте сессии), подтверждено
  fresh/matched/off; ipify 200 (тот же выход); таймер остановлен,
  ActiveState=inactive, SubState=dead.
- Машина в финале: off/off fresh/matched, 6 файлов = базе, VPN работает.

## Наблюдения для Codex

1. **Механизм перехода работает end-to-end**: поля
   `attempts[].redirect{http,state,host_changed}` появились в evidence
   ровно как задумано, новая причина `cdn_redirect_unconfirmed`
   отрендерилась в статусе панели. Это первая живая демонстрация
   перехода: 302 → follow → снова 3xx.
2. **Число и байты финального (после перехода) ответа не попадают в
   attempt-row**: при state=hop_limit в evidence остаётся http=302 первой
   ноги, а вторая нога видна только качественно. Предлагаю при
   state=hop_limit/blocked/expired записывать `redirect.final_http` и
   `redirect.final_bytes` — это различит «второй 3xx» (текущий случай,
   балансы GGC) и «403 на втором адресе» из классификации ТЗ.
3. **Цепочка редиректов**: первый ответ и цель перехода оба 3xx
   (перебалансировка GGC продолжается). Возможно, для CDN-цели имеет
   смысл допуск второго перехода (hop_limit → follow #2) в том же
   8с-окне: в r2/r3 третий запрос обычно уже отвечал 206/200.
4. **Линия продолжает флапать**: 00:15Z проба через VPN 206/65536 →
   00:30Z прямой TLS-таймаут + 302-цепочка через VPN → 00:31Z та же
   проба через VPN снова 206. Окна допуска по-прежнему попадают в фазу
   флапа; admission остаётся заблокированным третье ТЗ подряд — живая
   проверка `pending→active` при ротации не выполнялась ни в r3, ни в r4.
5. Мелочь исполнения: имя `snapshot` в bash-функции исполнителя
   перекрылось с системной утилитой окружения рабочего стола — внутренняя
   ошибка подготовки, к кандидату отношения не имеет (POST не ушёл,
   повтор блока единственный).
- Publication commit: `90212a670e6e5fe50db06ae574e2fba444e2e74e` (d8b4a6e → 90212a6, ancestor verified).
