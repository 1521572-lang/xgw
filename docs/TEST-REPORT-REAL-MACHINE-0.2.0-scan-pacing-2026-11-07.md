# ThinkCentre: волна 1 — плановые проверки запасных с паузами — 2026-11-07

- Дата; CODE/BASE; сумма OK; состав пакета: 2026-11-07; CODE 83d5b37, BASE fe1c2ba; SHA помощника 40974cd65e280dd3bd3a3a88f26c60423e33655166b353613b4508697e378161 (OK); diff src/packaging — ровно одна строка `src/xgw/daemon.py` (да).
- Подготовка: helper_rc 0; installed_is_base OK (config_sha 89bf2a67f0c34268… записан приватно); on/HTTPS до — OK on, OK https; diag до (OK/WARN/FAIL): 33/0/0; состояние HEALTHY; режим пула и ручной выбор — есть (не менялись).
- Тесты на машине: 5 passed / 0 failed (паузы в бюджете, срочные/ручные/DEGRADED без пауз, очередь, аварийная перестановка, перемешивание при равном рейтинге).
- Согласие: получено по точной формулировке ТЗ (время сохранено приватно). deploy: `OK baseline`, `install_rc=0 at=13:05:18`, `OK on`, `OK https`, `OK installed`, `helper_rc=0`; возврат — не нужен.
- Наблюдение 10 мин: helper_rc 0; state=HEALTHY весь цикл, scan_minutes=60, next_planned_in_s=4054; planned_pauses=59, min=0,226, max=1,457, outside=0 (допуск 0,19–1,6); idle_max_s=1,548 (справочно); urgent_probes=0, urgent_waited=0; scan_lines=0; error_lines=0; status_writes=61, median_s=9,1, max_s=23,9, over25=0, slow_step_lines=0 (OK status_every_25s); config_unchanged OK; on/HTTPS после — OK.
- Конечное: on/HTTPS OK (helper health rc 0), diag после 33/0/0 — новых FAIL нет; пул и ручной выбор без изменений (да).
- Границы: устройства за роутером не проверялись; отказы не имитировались; невидимость для ТСПУ не проверялась (вне объёма волны 1). Всё запланированное выполнено — NOT_RUN нет.
- Итог: PASS. Первый непройденный шаг — отсутствует. Оставлено на машине: CODE 83d5b37 установлен; каталог /run/xgw-pacing-install остаётся до перезагрузки (блок второй установки); путь D записан приватно.
