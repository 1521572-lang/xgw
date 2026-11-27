# ThinkCentre · матрица регрессий Xray и sing-box

| Поле | Значение |
| --- | --- |
| Задание | commit `1bd3931a64556b48c6ea2169b37e168c5c6345a5` (`docs/handoff/DUALCORE-REGRESSION-MATRIX-2026-11-27.md`, blob `a9423f5f9ad64e13ef9af4ecf25c6dd5a6460344`, sha256 `3dd9612c3a994f479936acd8d42e48b986b182d21ffbc750aa53d585ddf781c8`) |
| Кандидат | `20069a0f1d08df7a0a01d57d0e5c69a276693f06` |
| Контроль | `a1513402062653683eb097d6f3c710d90afc9524` (кандидат — потомок контроля, проверено) |
| Бандл | sha256 `24bc95c7813acd75777e013077ebfc78c8f90032c08cf908c87475b138416508`, проверен; `FETCH_HEAD` совпал с кандидатом |
| ОС / ядро | Ubuntu 24.04.5 LTS, amd64 / 7.0.0-43-generic |
| Python / pytest | 3.12.3 / 7.4.4 (одним интерпретатором для обеих ревизий) |
| UTC | 18:28:23Z–18:31:44Z |
| Помощь / повторы | 0 / 0; технических сбоев среды не было, повтор фаз не требовался |

Публикуются только агрегаты, имена сценариев и категории различий: адреса, PID, конфиги, полные логи, XML и локальные пути остаются на ThinkCentre.

## `CONTROL` (контроль `a151340`, семь прежних сценариев)

`CONTROL=1`: **7 failed, 0 passed, 35 deselected, 0 skipped, 0 errors** (22,55 с) — ровно ожидаемые семь assertion/fixture-падений, сбор полный (ошибок среды и неполного сбора нет).

Фактический первый сбой (порядок выполнения): `tests/test_dualcore.py::test_a_server_only_singbox_can_run_is_dropped_when_pinned_to_xray`.

Все семь: `test_a_server_only_singbox_can_run_is_dropped_when_pinned_to_xray`, `test_a_restart_in_the_middle_of_a_trial_continues_the_ladder`, `test_a_restart_during_the_daily_recheck_returns_the_learned_profile`, `test_new_sing_box_config_waits_while_a_member_goes_through_it`, `test_deferred_sing_box_config_is_applied_in_the_restart_window`, `test_when_nothing_answers_other_cores_and_transports_are_scanned_first`, `test_a_profile_trial_is_decided_by_the_whole_probe_file`.

## `CANDIDATE` (полная матрица семи файлов)

`CANDIDATE=0`: **212 passed, 0 failed, 0 skipped** (144,95 с) — прежде в этой же матрице было 205 passed и те же 7 падений. Между контролем и кандидатом исходники (`src`) не менялись: изменён только `tests/test_dualcore.py` (+76/−66), остальное — документация. То есть семь падений были дефектами самих тестов, а не кода, и обновлённые тесты их закрывают.

Отдельно сверенные сценарии (все PASS):

| Проверка | Сценарий | Итог |
| --- | --- | --- |
| Исключение sing-box-only узла при закреплении за Xray | `test_a_server_only_singbox_can_run_is_dropped_when_pinned_to_xray` | PASS (на контроле FAIL) |
| Восстановление профиля и проб после перезапуска/пересборки | `test_a_restart_during_the_daily_recheck_returns_the_learned_profile`, `test_a_learned_profile_survives_a_rebuild_and_a_restart` | PASS |
| Порядок очереди сканирования | `test_when_nothing_answers_other_cores_and_transports_are_scanned_first`, `test_ladder_orders_and_filters_the_steps` | PASS (первый на контроле FAIL) |
| Выбор по полному файлу пробы | `test_a_profile_trial_is_decided_by_the_whole_probe_file` | PASS (на контроле FAIL) |
| Смена состава: положительный и отрицательный сценарии | `test_singbox_composition_waits_for_bridge_validation[True]`, `[False]` | PASS |

Смена состава проверена по коду сценария и результату: до проверки моста снимок обоих конфигов (Xray и sing-box) обязан совпадать с исходным; положительный сценарий (`True`) применяет состав только после готовности моста и записывает новый состав, отрицательный (`False`) не применяет ничего и сохраняет оба исходных файла. Оба варианта прошли.

## `WATCHDOG`

`WATCHDOG=0`: **12 passed, 0 failed, 0 skipped** (28,45 с, 164 deselected) — фоновая сборка, устаревшие входы и штатный возврат через отдельное поколение.

## `HOST_FIELDS`

`HOST_FIELDS=MATCH`: `LoadState`, `ActiveState`, `MainPID` пяти штатных юнитов (`xgw.service`, `xgw-xray.service`, `xgw-singbox.service`, `xgw-singbox-blue.service`, `xgw-singbox-green.service`) до и после прогона совпали; категорий различий нет.

## Остаток

Рабочее переключение поколений, прямой CDN и сутки — `NOT_RUN`: проход матрицы их не предусматривает, тесты работали в двух приватных деревьях, штатные службы только читались.

## Итог

| Этап | Результат |
| --- | --- |
| `CONTROL` | 7 failed (ожидаемые, первый — `...::test_a_server_only_singbox_can_run_is_dropped_when_pinned_to_xray`), 0 errors |
| `CANDIDATE` | 212 passed, 0 failed, 0 skipped — матрица чистая, включая все отдельно сверенные сценарии |
| `WATCHDOG` | 12 passed, 0 failed |
| `HOST_FIELDS` | MATCH |
| Рабочее переключение / прямой CDN / сутки | `NOT_RUN` |

Обновлённые тесты двух ядер закрывают прежние семь падений: кандидат проходит полную матрицу 212/212, тогда как на контроле воспроизводятся ровно те же семь отказов; исходники при этом не менялись.
