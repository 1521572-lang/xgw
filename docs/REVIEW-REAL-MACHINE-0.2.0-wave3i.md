# Разбор wave3i: принят короткий host-кейс, остаётся loaded

Дата02.11.2026. Прочитан
[отчёт b32669a](https://github.com/1521572-lang/xgw/blob/b32669a84555d29c457abe2d69d32a98b7b7e1f8/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3i-2026-11-02.md).

## Факты

| Проверка | Полученный результат |
|---|---|
| Installed source | 4/4, NFT2739e81c, без повторной установки |
| Actualguard приon | JSONok0.064с, postrouting10/forward/drop5/reject0 |
| On state | capturebefore/aftertrue, frames capture/guardtrue |
| Plain HTTPS | 200/32769/0.428с, третий успех подряд |
| Marked HTTPS | 200/32769/0.436с |
| Enable | rc0/8.524с |
| Автономный возврат | total25.126с, restore0.126с, nft0 |
| WAN comparison | 6/6True; carrier1 в точках |
| Full loaded | null/child8сdeadline, последний active method__desired_problem |

Строка матрицы ТЗ «короткий host-кейс» выполнена: actuallayout+две HTTPS+offrollback.
Принимается именно этот ограниченный случай. Он не доказывает весь VPN-egress, TPROXY
конкретного flow (plain может идти direct по исключению), полное тело, устойчивость,
непрерывную связь модели/Tailscale, LAN/UDP/IPv6/DNS-on/E4. Полная wave3 не принята.

## Что показал trace

Первая сборка inbound/rules завершилась за3.625с (nested rules3.616с). Затем завершились
guard-generation/listing, чтение IPv4table0.692с, отдельныеset-чтения (одно1.071с), IPv6guard.
У child осталась одна активная граница method__desired_problem сtracebegin5.626.
Это не длительность метода и не доказанный зависший syscall:8с — весьchild, началоtrace
находится после созданияCapture. Получен конкретный следующий участок для профилирования.

Утверждение отчёта «прежняя причина была в конкуренции, не в nft» не установлено этими
данными. Раньше deadline_or_error объединял несколько ошибок; теперь изменены схема запуска,
лимит, numericflags и условия. Один успешный
[guard_query](https://github.com/1521572-lang/xgw/blob/f78c2f1432ae56cdec8e229b59f33b9ee4723760/tests/stand/wave3_enable_probe.py#L304)
не восстанавливает прошлую причину. Nativefallback не понадобился; его реальная совместимость
в этом прогоне NOT_RUN. Сам факт нынешнего layout достаточен для узкой матрицы, не дляE4.

## Профиль и новый кандидат

Выполнено только purePython профилирование
[Capture._desired_problem](https://github.com/1521572-lang/xgw/blob/f78c2f1432ae56cdec8e229b59f33b9ee4723760/src/xgw/net/capture.py#L556)
с синтетическими непересекающимися IPv4, CIDR вexpected иhost spelling вactual. Runner
запрещал kernel/packet команды. Cache интервалов очищался перед coldpass; рендеры сохранены.

| Размер | До | После candidate |
|---|---|---|
| 4096 адресов,73 753байта render | 0.1555с | 0.0837с |
| 20 000 адресов,360 368байт render | 0.8168с | 0.3869с |

Это разовый cProfile на WSL, не статистический benchmark и не время ThinkCentre. Основные
затраты фикстуры — intervals/ipaddress.Network. Не доказано, что каждый внутренний шаг
реального незавершённого метода имеет те же доли. Реальный loaded может снова не уложиться.

Кандидат [351fb54](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/nft.py#L1332)
изменяет только parsing helpers: canonicalIPv4host/prefix использует строгую IPv4Address
и целочисленные границы; остальные формы/IPv6 проходят stdlib. Invalid→None, merge/cache8,
полное сравнениеpolicysets сохранены; expected-elements извлекаются один раз. Никакие
наборы/правила не пропускаются и неизвестность не подменяетсяуспехом. Другой moduleAST,
включая всеrender/guard функции, совпал сbaseline.17 узких parser/manifest проверок PASS,
в том числе132 сочетания адреса иprefix0..32, необычные маски, IPv6/invalid/equivalent/changed.

## Реальная проверка

Каноническое ТЗ — TEST-PLAN-REAL-MACHINE-0.2.0-wave3j.md. Послеoff-preflight один новый
atomicparser update толькоnft.py при остановленных писателях (old2739→new10c1), backup/SHA/
4installed/dry nft-c, стартoff и один guarded enable25с. Это не повторG1старойwave3g и не
полныйinstaller. Safety25с/fullchild8с/guard3+3/HTTPS4 прежние. Не повышать бюджеты радиPASS.
Отчёт должен показать actuallayout, полныйread_trace и фактическийloadedTrue/False/Unknown.
Realwave3j первоначально NOT_RUN; WAN/sysctl/config/core/Tailscale не меняются.
