# Разбор wave3p: STOP до запроса, рабочий контекст сохранён

[Фактический отчёт Flash](https://github.com/1521572-lang/xgw/blob/08cdf113dd0a020321199dda86166a9bde6dae5a/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3p-2026-11-02.md),
commit **08cdf113dd0a020321199dda86166a9bde6dae5a**, FF merged.
TestedHEADf9ed31f966d2e2dc337096e450c537702d4cb489 /
tree4e3e39d077d613b92bd9ea35a336d13f12cf5ac6. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок, runtime diff пуст,
installed4 равны, четыре frozenSHA совпали. Продукт не устанавливался.

## Решение по результату

| Результат | Принятое значение |
|---|---|
| STOP_SINGLE_PROBE/commandrc3 | Проверка остановилась до запроса; P не принят как сетевой опыт |
| request_count0/нетattempt | Никакого нового отрицательного или положительного результата SB-1 |
| showrc0 | Файл прочитан, не успешный тест |
| ValueError/contexttrue | Условие сборщика не прошло, рабочее состояние сохранилось; точная ветвь не записана |
| on/settings3/SBconfig/process/boot/PID6/pinreadable+unchangedtrue | Рабочие состояние и контекст в bookends сохранены |
| Нового journal/запроса/действий владельца нет | Не назначаем причины SB-1 по этому прогону, не повторяем запрос |

N остаётся partial1/2. SB-2positive/M6/6/L608с/Jshort-host+loaded приняты и не повторяются.
Это не свидетельство поломки работающей LAN. Fullwave3/D1-on/E4/scopedfaults/LANUDP/
IPv6/DNS/allTailscale остаются открытыми, wave4/DAE не начинаем.

## Недоработка тестового сборщика и вывод из исходников

P скрывал текст исключения ради приватности, но оставлял только error_class.
Это дефект наблюдаемости теста: безопасный stage/code нужен отдельно от raw сообщения.
Он не является доказательством дефекта runtime XGW или сервера.

[Порядок P до запроса](https://github.com/1521572-lang/xgw/blob/f9ed31f966d2e2dc337096e450c537702d4cb489/tests/stand/wave3_single_bridge.py#L317-L334):
configdigest вычисляется до selected_from_mapping/marks/targets/tool/version;
curl_version эмитируется до подтверждающих mapping/attrs/plan флагов.
[План создаётся позже](https://github.com/1521572-lang/xgw/blob/f9ed31f966d2e2dc337096e450c537702d4cb489/tests/stand/wave3_single_bridge.py#L339-L358).
[bridge_config_unchanged](https://github.com/1521572-lang/xgw/blob/f9ed31f966d2e2dc337096e450c537702d4cb489/tests/stand/wave3_single_bridge.py#L153-L154)
требует исходный digest неNone. Поэтому reportedbridge_config_unchangedtrue доказывает,
что до чтения текущего конфига P дошёл: более ранние проверки source/Nsummary прошли
в тот момент. Гипотезу отчёта о любом раннем историческом входе нужно сузить.

Если rootPsummary действительно не содержит curl_version, область исходного ValueError
лежит после вычисленияconfigdigest до эмиссииcurl_version. Она включает mapping/route/
marks/configload/targets/tool/version. Plan располагается позже; его не назначать
причиной при отсутствующем curl_version. Точный site из одного класса не восстанавливается.
Q проверяет поля фактического rootJSON; недостающие данные текстового отчёта не додумывает.

Изменённый HEALTHYtimestamp с12:42на19:56 не доказывает, что владелец перезапускалVPN.
Действия между опытами не наблюдались; предположение отчёта «вероятно владелец…» не принимаем
как установленный факт. Внутри P по отчёту действий владельца и сетевых изменений не было.

## Следующий пакет: только статические чтения

[ТЗ wave3q](TEST-PLAN-REAL-MACHINE-0.2.0-wave3q.md) и
[шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3q-TEMPLATE.md): новый readonly helper с
фиксированными stage/code для входов, safechecks для mapping/route/currentconfig,
полями наличия старых эмиссий/plan и временным основанием currentconfig→P.
Psource66128…/старые N/O файлы не меняются. Нет запуска curl даже--version, GET,
journal, сканов, APIwrites, сменыузла/pin/служб/правил/WAN/LAN/Tailscale/VPN.
Никакого автоматического повтора P после Q. Сначала фактический отчёт.

current_first_unmet_gate — современный факт Q, не сохранённая старая ветвь исключенияP.
Если filemtime+ctime предшествуютP и clocksсовместимы, это только
FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN, не digestproof P. Даже currentOconfigmismatch
не является основанием откатывать конфиг или обвинять обновление/владельца/тест.
Если все текущие staticgatestrue, точкаP всё равно UNRECORDED; старые входы могли отличаться.
Нет сохранённого входа→BLOCKED, не подмена старых данных текущими и не повторрадиPASS.

Локально13узких fixture/mockedпроверок нового readonlyсборщика и RuffPASS; только
статическая проверка ТЗ, без broadVM/netns/живыхлогов/запросов/шлюза. Runtime и старые
helpers неизменны. Реальная **wave3q NOT_RUN**. Ожидается
TEST-REPORT-REAL-MACHINE-0.2.0-wave3q-ДАТА.md. Рабочий on сохраняется, offrollback запрещён.
