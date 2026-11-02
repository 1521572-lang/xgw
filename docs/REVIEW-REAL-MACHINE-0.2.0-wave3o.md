# Разбор wave3o: данные собраны, причина SB-1 ещё не установлена

[Отчёт Flash](https://github.com/1521572-lang/xgw/blob/4fbde2e4469ec2bda92956d3715ab0e5a3f80728/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-2026-11-02.md),
commit **4fbde2e4469ec2bda92956d3715ab0e5a3f80728**, FF merged.
Tested HEAD ce1f1ed8365c43158a72ebd7c4546af8f2a868f2 /
tree bdf174926fa628e3692a30a3fa5ffc188b2a5765. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7, runtime diff пуст, installed4 равны,
три frozen SHA совпали. Продукт не устанавливался, новых сетевых запросов не было.

## Что принято

READ_DIAGNOSTIC_RECORDED/exit0, show согласован. Сохранены рабочий HEALTHY/on,
guard postrouting10/forward/drop5/reject0, 6 active служб и PID, SB process/boot,
settings3/SB-config, pin readable/unchanged. Сеть и режимы владельца не переключались.
Это успешный сбор диагностических данных, **не PASS SB-1 и не исправление**.

[Основание сопоставления](https://github.com/1521572-lang/xgw/blob/4fbde2e4469ec2bda92956d3715ab0e5a3f80728/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-2026-11-02.md#L22-L42):
Nsummary валиден, реальное окно2.919с, clock basis совместим, 71 кандидат,
mtime/ctime config до N. FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN сохраняется буквально:
исходный N не сохранил configdigest/selectedfingerprints/PID в privateplan.
Поэтому соответствие N→O поддержано временами файлов, не старым сохранённым digest.
O сохранил локальный root600 mapping для следующего точного сравнения с O.

## Разделение фактов и гипотез

| Факт | Вывод и ограничение |
|---|---|
| SB-1 latest scan OK/305байт/.77с, beforeN/age1464.083с | Был ранний короткий положительный scan; он мог устареть. Это не32769body и не свежий health в N |
| SB-2 scan OK/305байт/.43с, afterN/age−1719.36с | Поздний scan не является фактом о прошлом. Положительный N HTTPS SB-2 принят независимо |
| Безопасные attrs SB1/SB2 одинаковы: vless/reality/uTLS/vision/TCP/443 и т.д. | Совпадают классы признаков. Приватные значения параметров/их корректность этим не проверены |
| 2 journal rows, queryok/nottruncated/parseerrors0, обе условно relatedSB1, TLS-auth-handshake2 | Есть две строки с широкими словамиTLS/reality/handshake и тегом в окне, а не два доказанных сбоя TLS |
| error_priority_rows0 | У journaltransport нет priority≤3. Уровень ERROR может находиться внутри MESSAGE; O его не разбирал |
| Остальные keywordcounts0 | По заданным шаблонам совпадений нет; это не исключение прав/DNS/маршрута/другой причины |

Следовательно, слова отчёта «изоляция/конфигурация причиной не выглядят» допустимы как
осторожная гипотеза, не основание исключить endpoint-specific дефект. SB-2 исключает
глобальную неспособность того же worker передать HTTPS, но не проблему конкретного SB-1.
Не установлен ни ТСПУ, ни падение сервера, ни дефект XGW, ни успешный TLS SB-1.
N остаётся partial1/2. TLSverify0 при HTTP0/bytes0 не является положительным TLS.

## Следующий атомарный шаг

[ТЗ wave3p](TEST-PLAN-REAL-MACHINE-0.2.0-wave3p.md) и
[шаблон отчёта](TEST-REPORT-REAL-MACHINE-0.2.0-wave3p-TEMPLATE.md):
один НОВЫЙ запрос через ровно SB-1 из закрытого O mapping, только при точном совпадении
текущего SB-configdigest с O. Сохранить privateplan ДО запроса, запретить повтор через
startedmarker. Собирать безопасные признаки curlstderr/SOCKSreply и journal нового окна,
отделять literal failure-фразы и текстовый loglevel от широких keywordcategories/priority.
Цель из текущего configprobe; старый N targetdigest не сохранён, совпадение не утверждается.
Нет смены pin/узла/правил/процесса/WAN/LAN/Tailscale/VPN. SB-2/M/L/J не повторяются.

Это проверка текущего состояния с улучшенным сохранением свидетельств, не поиск PASS
на случайном другом узле. Положительный новый ответ не доказывает причину старого отказа,
отрицательный сам по себе также не назначает виновника. При отсутствующем/изменённом
mapping/config — BLOCKED без запросов и без реконструкции старых данных.

[Официальные коды libcurl](https://curl.se/libcurl/c/libcurl-errors.html):97 означает
ошибку proxy handshake. [curl8.5.0](https://github.com/curl/curl/blob/curl-8_5_0/lib/socks.c#L924-L944)
печатает числовой SOCKSreply в распознаваемом сообщении; общий reply1 не объясняет upstream.
Не публиковать строки/адреса/ключи, только enum/count/bool/числовойreply.

Локально только15узких mocked/fixture проверок нового сборщика, Ruff и статическая
проверка ТЗ. Нет широких VM/netns/реальных запросов. Runtimepatch пока не обоснован.
Реальная **wave3p NOT_RUN**; ожидается TEST-REPORT-REAL-MACHINE-0.2.0-wave3p-ДАТА.md.
Fullwave3/D1-on/E4/scopedfaults/LANUDP/IPv6/DNS/allTS открыты, wave4/DAE не начинаем.
Рабочая LAN считается работающей; gateway on сохраняется, always_off guardian запрещён.
