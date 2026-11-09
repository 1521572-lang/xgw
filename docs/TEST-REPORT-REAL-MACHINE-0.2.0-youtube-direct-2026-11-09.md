# ThinkCentre: правило видео через API, маршрут и мосты — 2026-11-09

- Дата; CODE d7c672b; сумма помощника OK (e0c961eb…); число файлов совпало — **да** (3).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 33/0/0; режим пула observe.
- Тесты (9 файлов): new rc=1 (**19 failed, 366 passed**); base rc=1 (19 failed, 357 passed);
  **«новые падения:» — пусто** ✓; упавших на прежнем коде — 19 (тот же список).
- Согласие: в сообщении с ТЗ слова «разрешаю» не было — спрошено отдельно (время приватно):
  «Разрешаю». deploy: первый запуск — `STOP baseline` (установка не начиналась, машина не менялась;
  по согласию владельца выполнен один повтор — тот же транзитный вид отказа, что и прежде);
  повтор: `OK baseline`, install_rc=0 at=12:47:53, `OK on`, `OK https`, `OK installed`,
  helper_rc=0; возврат не нужен.
- Включение: helper_rc=0; `INFO pin_active=True`; `INFO media_state=applying`; `OK enabled`;
  on/HTTPS OK.
- Наблюдение 30 мин: helper_rc=0 — `INFO window_min=30.4 states=[('applying', 1), ('best', 71)]
  exit_changes=0 sample_age_max_s=5010`, `INFO exit_mbps=47.4`, `INFO diag_youtube_lines=1
  diag_warn=0`, `OK diag_youtube`, `OK xray_not_restarted`, `OK not_degraded`, `OK
  config_unchanged`, `OK on`, `OK https`, **`OK best_applied`** — режим вошёл в best с первого
  замера и держался до конца окна (degraded не было; в прошлый раз окно завершилось в degraded).
- Маршрут (1 попытка): helper_rc=0 — `OK xray_not_restarted`; `INFO route_video=[46623, 47452,
  47276] route_control=[0, 0, 80798] need=12000` (байты); `OK route_video_seen`, **`OK
  route_video`** — рост байтов только на видео-выходе, на обычном от видео-запросов нули.
- Мосты: helper_rc=0 — `INFO bridges total=5 members=0 curl_rc=[97, 97, 97, 97, 97]`; по ТЗ любые
  коды — не FAIL, причина не интерпретируется (разбор за разработчиком).
- Возврат настроек: helper_rc=0 — `OK backup_found`, `OK config_restored`, `INFO media_state=off`,
  `OK disabled`, `INFO pin_active=True` (совпал с шагом 6 — да), `OK on`, `OK https`.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; режим пула без
  изменений (да: observe); [media] в config.toml нет.
- Границы: `pin_active=True` в обоих замерах — работа при ручном выборе проверена этим прогоном;
  само видео, его качество и скорость не проверялись; коды мостов не анализировались.
- Итог: **PASS** — `OK best_applied` и `OK route_video` достигнуты; правило видео ставится в
  работающий Xray без перезапуска, застарелая связка со сборкой мостов устранена. Отклонение одно:
  первый deploy упал в STOP baseline (до изменений), повтор по согласию владельца прошёл чисто.
  Первый непройденный шаг — отсутствует. На машине: код шлюза d7c672b, режим best выключен (config
  возвращён байт в байт), состояние HEALTHY, VPN включён.
