# ThinkCentre: дополнительный выход zapret2 — первая приёмка — 2026-11-10

- Дата; CODE e3c8068; сумма помощника OK (ad537491…); база разработки 059258a, установленная до
  ТЗ 49f0440 (все 7 существующих файлов совпали с PREV, zapret2.py отсутствовал — норма).
- До: CHECK state=unknown route=0 queue=0 lease=0 capture_on=1 warnings=0 zapret_bytes=0; `OK
  baseline`; on/HTTPS OK; diag (OK/WARN/FAIL): 32/1/0; режим пула observe.
- Тесты: первый набор — 5 failed / 196 passed / 15 skipped; все 5 падений в test_nft.py
  **BASELINE_FAIL** (идентичный список на PREV, «новые FAIL» — пусто); второй набор (zapret2/media/
  youtube по daemon) — **20 passed**. Полный набор не запускался; пакеты не ставились.
- Согласия (времена приватно): замена 8 файлов кода — «Разрешаю»; скачивание nfqws2 v1.0.7
  (bol-van/zapret2, 05.11.2026, x86_64, /opt/zapret2) — «Разрешаю v1.0.7»; прямой выход ~20 мин —
  «Разрешаю прямой выход»; адрес страницы YouTube прислал владелец, адрес файла видеосети — «открой
  самостоятельно, разрешаю» (извлечён через отдельный исполняемый yt-dlp из приватного каталога,
  без установки в систему).
- Установка кода: 7 файлов сверены cmp с PREV; копии /opt/xgw/lib/xgw и config.toml (0600) сняты и
  сверены; синтаксис 8 файлов через compile OK; остановлен и запущен только xgw.service; Xray и
  sing-box не перезапускались. Приёмка: `CHECK state=off route=0 … xray_same=1 protected_same=1`;
  после 5 минут — HEALTHY; diag после установки 32/1/0.
- Подготовка zapret2: архив v1.0.7 сверён по sha256sum.txt выпуска (60 файлов OK); nfqws2 и два
  Lua (zapret-lib, zapret-antidpi) в /opt/zapret2, root, без записи группе/остальным; `--version`
  = v1.0.7 (038c97e5); сумма nfqws2 совпала с выпуском (приватно); install_easy/firewall/sysctl не
  трогались; очередь 200 и порт 19999 свободны; block_quic=true (эффективно), proxy_domains пуст.
- Включение: раздел [zapret2] mode=selective, strategy=multisplit, probe_urls=2 (приватно),
  config читается без предупреждений. Watch 180 с: `preparing → fallback`; причина кодом —
  **`probe_failed`** (тест доступности не пройден;(route=0, queue снята, zapret_bytes=517,
  xray_same=1, protected_same=1 — обычный VPN продолжал работать). Причина не интерпретировалась.
- Видео: не проводилось — активного режима не было (**NOT_RUN video**, NOT_RUN route_bytes);
  проверка отказа обработчика — не применима (без active).
- Выключение и откат: config.toml возвращён байт в байт ([zapret2] отсутствует); **`RESULT
  rollback_ok`** — state=off, route=0, lease=0, xray_same=1, protected_same=1; worker_pid=0
  (приватно: PID нет); diag после (OK/WARN/FAIL): **32/1/0** — новых FAIL нет; режим пула без
  изменений (да: observe); состояние HEALTHY.
- Оставлено на машине (по согласиям): 8 файлов кода XGW с zapret2.py — установлены, режим off;
  nfqws2 v1.0.7 и Lua в /opt/zapret2 — не удаляются и постоянно не включаются; пробы владельца —
  только в приватном конфиге, в отчёт и git не попали.
- Примечание: probe_failed согласуется с измерением youtube-wan-r2 (страница и видеосеть прямого
  пути не отвечали, файл замера отвечал) — интерпретация и повторные стратегии — за разработчиком.
- Итог: **PARTIAL** (не PASS: активного режима не было — fallback probe_failed; при этом чистые
  установка, отказ-поведение и откат). Первый непройденный шаг — 6 (active не получен). На
  машине: код XGW e3c8068 (zapret2 неактивен), nfqws2 v1.0.7 в /opt/zapret2, состояние HEALTHY,
  VPN включён.
