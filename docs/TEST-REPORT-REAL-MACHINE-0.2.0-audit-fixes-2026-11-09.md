# ThinkCentre: правки внешнего аудита — 2026-11-09

- Дата; CODE 4e43764; сумма помощника OK (ea4edf10…); файлов 15 — **да**.
- Подготовка: первый прогон — `STOP TimeoutExpired` (транзитный таймаут чтения, только для чтения,
  ничего не менялось); повтор — helper_rc=0: `OK tools`, `OK install_scripts_parse`, `OK on`, `OK
  https`; absent_table: family=4 rc=2 known_text=True, family=6 rc=2 known_text=True, `OK
  absent_table`; `OK installed_is_base`; state=DEGRADED, members=5, spares=86, subscriptions=3.
- Диагностика до (OK/WARN/FAIL): 32/1/0 (прежний некритичный WARN); режим пула observe.
- Тесты: прогоны по 10 файлам, new и base. Первый прогон прерван на середине (обрыв моей сессии,
  не машины) — перезапущен с нуля. new rc=1 (28 failed, **629 passed**, 1 skipped); base rc=1
  (28 failed, **527 passed**, 1 skipped); **«новые падения:» — пусто** ✓; упавших на прежнем коде — 28
  (тот же список, среда без root/сети, как в прежних отчётах).
- Согласие (время приватно): «Разрешаю установку». deploy helper_rc=0; install_rc=0 at=00:32:34;
  возврат не нужен.
- Наблюдение 20 мин: helper_rc=3 — после `OK config_unchanged` финальный health упал по таймауту
  чтения (`STOP TimeoutExpired`, тот же транзитный вид, что и в подготовке); из-за этого не
  напечатаны финальные `OK on`/`OK https`/`OK subscriptions_reported`. Все содержательные проверки —
  OK: `INFO from=install`; состояния за окно: DEGRADED и HEALTHY (число замеров помощник не выдаёт);
  status_age_max_s=20; 3 × `INFO sub state=fresh reason=none` (1189/1188/1187 с); `OK
  age_consistent`; `OK subscription_path`; via_xray_errors=0, target_refused=0, unconfirmed=0,
  tracebacks=0, `OK no_tracebacks`; unknown_lines=0, `OK state_known`; urls_checked=2, `OK
  no_urls_in_status`; `OK config_unchanged`. DEGRADED в окне — записан как факт, причина не
  интерпретируется.
- Конечное: `OK on`, `OK https` (health rc=0 — закрывает не напечатанный хвост наблюдения); diag
  после (OK/WARN/FAIL): **33/0/0** — новых FAIL нет, прежний WARN исчез; режим пула без изменений
  (да: observe). Каталог /run/xgw-auditfix-install остаётся до перезагрузки.
- Границы: отказы на машине не вызывались (проверены тестами шага 3); живьём — что обычный путь не
  сломан (подписки fresh, target_refused=0, через Xray ошибок нет).
- Итог: **PASS** — все шаги по существу пройдены; отклонение одно: финальный health наблюдения не
  напечатался из-за транзитного таймаута чтения, подтверждён шагом 7. Первый непройденный шаг —
  отсутствует. На машине: CODE 4e43764, состояние после наблюдения HEALTHY (финальный health OK),
  VPN включён.
