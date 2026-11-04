# AM: стартовый отказ, результатов 852 scenarios нет

Источник: failure-сообщение Flash, переданное владельцем в чате04.11.2026. Git-report
отсутствует по правильной ветке ТЗ: workerclaim без summary/progress/cases; monitor3/
shape1/report3, prefix не создан. F3/ручнойcommit запрещены. Исполнитель соблюл протокол.
Не записывать fictitious852FAIL/PASS, не менять original reports.

В коде воспроизведён KeyError ownership_binding при source(): модуль транзитивно
импортирован, но не записан в словарь M. Узкие тесты AM вручную заполняли M, пропуская
настоящий bootstrap. Исправлен tests/stand/wave3_bound_composition.py. Новый regression
в отдельном Python процессе проверяет настоящий freeze/bootstrap/source/audit.
Это не полученный traceback ThinkCentre: причина реальной остановки сопоставлена
с местом воспроизведённого дефекта, иных startup причин сообщение не исключает.

Дополнительно progress0 создаётся сразу послеclaim до imports. При повторномstartup
failure можно сохранить честный emptycheckpoint, без ожидаемыхданных/852строк. Нет
дажеcheckpoint→стараяSTOPветка. Никаких runtime source/units/network изменений.
Три targeted tests/RuffPASS. Full852/ThinkCentreNOT_RUN.
[Новый AN852](TEST-PLAN-REAL-MACHINE-0.2.0-wave3an.md), новый private notesAN/one start.
Старый AM не повторять и заметки AM не чистить. All7gatesfalse/Cblocked.
