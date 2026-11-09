# ThinkCentre: дополнительные проверки кандидатов в видео-выход — 2026-11-09

- Дата; CODE 390b38f; сумма помощника OK (777c9983…); число файлов совпало — **да** (4).
- До: helper_rc=0; on/HTTPS OK; diag (OK/WARN/FAIL): 33/0/0; режим пула observe.
- Тесты (5 файлов): new rc=1 (**19 failed, 266 passed**); base rc=1 (19 failed, 260 passed);
  **«новые падения:» — пусто** ✓; упавших на прежнем коде — 19 (тот же список).
- Согласие: в сообщении с ТЗ слова «разрешаю» не было — спрошено отдельно (время приватно):
  «Разрешаю». deploy helper_rc=0; install_rc=0 at=16:51:21; строки ATTEMPT как есть:
  `ATTEMPT 1 at=16:51:36 status=ok status_s=14.4 on=1 https=ok:301`; возврат не нужен.
- Включение: enable helper_rc=0; `INFO pin_active=True`; `INFO media_state=applying`; `OK
  enabled`; on/HTTPS OK.
- Наблюдение 40 мин: helper_rc=0. Строки INFO как есть:
  `INFO window_min=40.1 states=[('applying', 1), ('best', 88)] exit_changes=0`;
  `INFO extra_checks=1 all_checks=5 min_gap_s=- probe_mb=8.0 probe_limit_mb=256 errors=0`.
  Итоговые проверки: `OK xray_not_restarted`, `OK not_degraded`, `OK config_unchanged`, `OK
  budget`, `OK on`, `OK https`, **`OK best_applied`**, **`OK extra_checks`**, **`OK gap`** —
  режим в best с первого замера до конца окна, дополнительная проверка прошла, расход 8,0 МБ из
  суточного лимита 256 МБ, ошибок нет. min_gap_s не вычислялся — проверка была одна.
- Возврат настроек: `OK backup_found`, `OK config_restored`, `INFO media_state=off`, `OK
  disabled`, `INFO pin_active=True` (совпал с шагом 6 — да), `OK on`, `OK https`, helper_rc=0.
- Конечное: on/HTTPS OK; diag после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет; режим пула без
  изменений (да: observe); [media] в config.toml нет.
- Границы: смена выхода при плохом сервере и поведение при исчерпании суточного лимита не
  проверялись (по ТЗ); `pin_active=True` в обоих замерах — работа при ручном выборе проверена.
- Итог: **PASS** — `OK best_applied`, `OK extra_checks`, `OK gap`, `OK budget`, новые падения
  пусты; первый непройденный шаг — отсутствует. На машине: код шлюза **390b38f**, режим best
  выключен (config возвращён байт в байт), состояние HEALTHY, VPN включён.
