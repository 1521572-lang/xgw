# Разбор wave3r: отрицательный запрос и конкретный признак отказа REALITY

[Отчёт Flash](https://github.com/1521572-lang/xgw/blob/bd512410a5515692a3870c8aba153535c742a0d2/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3r-2026-11-02.md),
commit **bd512410a5515692a3870c8aba153535c742a0d2**, FF merged.
TestedHEAD3ec17cf6dba4cce9b85ecd1c5fa3e6c72db98829 /
tree5b52cd788d20b64fb60b5017ac6ec9757c2201f3. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7, ancestor/runtime diffempty,
installed4/5frozenSHA совпали. Продукт не устанавливался.

## Принятый результат

CURRENT_BRIDGE_RECORDED/rc0 — корректно собранная попытка, не BODY_PASS.
R-CURRENT-1: один запрос, curl97/HTTP0/bytes0/.977с/bodyfalse, SOCKSreply1;
listenerownedbefore/aftertrue. План с полным currentconfigdigest/targetdigest/identity
сохранён до запроса. CurrentconfigequalsOfalse; внутри R конфиг не менялся.
Historical_endpoint_identityUNPROVEN сохраняется: referencekey8hex не доказывает старыйendpoint.

Новый journalqueryok/1row/nottruncated/parse0: related1, broadTLS1,
literalreality_verification_failed1, leadingmessageERROR1, transportpriorityerrors0.
Это сильнее прежней широкой категории O: в новом окне зафиксирована конкретная фраза,
но tag+time всё ещё не идентификатор точного curl-сеанса. N не содержал сохранённого
этого литерала: нельзя задним числом назначить N тот же REALITYсбой.

Рабочий on/guard/capsNNPDAC/settings3/SBconfig/process/boot/6PID/pinreadable+unchanged
сохранены. Нет отключений/изменений/действий владельца/повторных попыток. Принять R как
отрицательное измерение текущего входа и диагностику, сохранить bodyfalse.
Npartial1/2/Pblocked0/Qreadonly/M6/6/L608с/Jshort-host+loaded/SB2positive не пересматриваются.

## Коррекция интерпретации

В [официальном исходнике sing-box1.14.4](https://github.com/SagerNet/sing-box/blob/v1.14.4/common/tls/reality_client.go#L214-L225)
такой отказ возвращается после TLS-handshake, когда специальная проверка REALITY
не установила verified. Это проверка upstream-протокола между worker и сервером,
не TLS HTTPS-цели curl. Источник версии помогает интерпретировать строку, но не является
аттестацией сборки установленного бинарника/пакетной трассой.

Отсюда не установлен виновник: неправильные/устаревшие параметры, сервер, промежуточный
путь и совместимость остаются кандидатами. Не назначаем ТСПУ/падение сервера/дефектXGW.
socks_auth_failure_textfalse означает лишь отсутствие распознанной фразы локальнойSOCKSauth,
не отсутствие всех проблем авторизации; REALITY сама проверяет подлинность upstream.
Контекст изоляции сохранён, но фразу отчёта «изоляция подтверждена» нельзя расширять до
исключения всех endpoint-specific прав/маршрута/совместимости. SB2positive исключает
глобальную неспособность worker, не все специфические проблемы R.

Важный предел бюджета: [та же ветвь запускает фоновый fallback](https://github.com/SagerNet/sing-box/blob/v1.14.4/common/tls/reality_client.go#L223-L259)
на уже открытом upstream-соединении. Поэтому один инициированный curl не гарантирует
ровно один HTTP-запрос внутри ядра; curlbodymax/child8с не ограничивают всю такую фоновую
работу постоянного процесса. Наличие этой ветви в исходнике не доказывает конкретный
фоновый трафик в R. Повторять опыт для его поиска не нужно; новый S соединений не создаёт.

## Следующая проверка без сетевых запросов

Проверен код: [REALITYполя переносятся явно](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/parsers/convert.py#L217-L230),
[базовый профиль копирует spec](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/generator/singbox.py#L119-L147).
Очевидного дефекта этого участка по одному отчёту нет. Не отключать verification,
не править ключ/shortID/SNI по догадке и не переключать узел ради PASS.

[ТЗ S](TEST-PLAN-REAL-MACHINE-0.2.0-wave3s.md) /
[шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3s-TEMPLATE.md): только rootRартефакты,
currentconfig, доступные локальные cachedbody/manuallinks и чистый штатный parser.
Новый helper выдаёт только bools формы и сравнения полей/coveragecounts. Если currentdigest
не совпал с Rplan, вывод только CURRENT_ONLY, без приписывания современного контракта R.
Сверка источника ПОСЛЕ parser не независимая проверка самого parser/оригинальной подписки.
Современныйcache мог смениться, lineage не доказана; mismatch не автоматический runtimebug,
equality не правильность серверных ожиданий. Ambiguity/недоступные источники не подменятьPASS.

Никаких curl/journal/scan/APIwrites/пиннинга/служб/правил/адаптеров/VPN. Старые helpers
не менялись; sourceidentity всего установленногоPythonдерева проверяется перед parser.
14узких fixtures/mocked проверокPASS/RuffPASS, синтаксисТЗпроверен. BroadVM/netns/живые
прогоны нами не делались. Обновление02.11: Sa7482377b5cb0d85a015d8a7fcc747743b8e7e94 получена, scopedconsistencyпринята.
[РазборS](REVIEW-REAL-MACHINE-0.2.0-wave3s.md); новый укрупнённый TNOT_RUN. Fullwave3/D1-on/E4/faults/LANUDP/IPv6/DNS/
allTS открыты, неwave4/DAE. РабочаяLANработает; baselineon и запретalways_off сохраняются.
