# Разбор wave3q: старая база O отличается от текущего конфига

[Фактический отчёт Flash](https://github.com/1521572-lang/xgw/blob/e768971594d20ca6ac0b424bc114cadf2c33f179/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3q-2026-11-02.md),
commit **e768971594d20ca6ac0b424bc114cadf2c33f179**, FF merged.
TestedHEAD58841d2a86d9d9475952561d83af45d024b5d06f /
treeee76159096f98fa74d02a4a959719d52c04e3001. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7 — предок, runtime diff пуст,
installed4 и4frozenSHA совпали. Продукт не устанавливался.

## Что принято

GATE_DIAGNOSTIC_RECORDED/rc0, stageCURRENT_STATIC_READS_COMPLETE, showrc0.
Все предусмотренные чтения состоялись. Q_network_requests0, новых GET/journal/сканов
или переключений не было. HEALTHY/on, settings3/SBconfig/6PID/process/boot/pin,
capless/NNP/DAC/guard сохранены. Q принята как диагностический сбор, не сетевойPASS.

| Свидетельство | Решение |
|---|---|
| current_config_digest_matches_Ofalse; остальные10staticchecks true | Текущий SBconfig отличается от записанного в O; referencekey сейчас соответствует одному vless/d входу |
| Prequest0, версияcurl/Omappingflag/planflag отсутствуют, planfileabsentnow | В P не состоялся новый запрос; отсутствие текущего планфайла не самостоятельное прошлое доказательство |
| Pstage_rangeAFTER_CONFIG_DIGEST_BEFORE_CURL_VERSION_EMISSION | Сужен диапазон исходников; точная ветвь P_exception_siteUNRECORDED |
| clockcompatible+configmtime/ctimebeforeP | Только FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN, не сохранённый исторический digest P |
| warningsfalse/2HTTPSцели/curlpathtrue/versionnotrechecked | Текущая статическая информация; не старый toolresult и не разрешение повторить P |

Q согласуется с блокировкой P на межпрогонном сравнении digest, но не доказывает её
как точную старую ветвь ValueError. Более сильную фразу отчёта «файл точно не менялся
с P и содержимое совпадает с baseline P» не принимаем: условия filetime — поддержка,
а не записанный Pdigest. Не установлены причина и время изменения конфигурации.
Новый HEALTHYtimestamp не доказывает действий владельца/перезапуска VPN.
Нельзя восстанавливать старое содержимое O ради зелёного отчёта или обвинять пользователя.

## Решение о тестовой базе

Закрыть Q в scope чтений. P оставить BLOCKED/NOT_RUN(request0), не пытаться задним
числом восстановить точный exception site. N сохраняется partial1/2: два отрицательных
запроса SB-1 и принятый положительный SB-2. Причина старого SB-1 остаётся неизвестной.
Нового доказанного дефекта runtime XGW нет, продуктовый patch не обоснован.

Новый [пакет R](TEST-PLAN-REAL-MACHINE-0.2.0-wave3r.md) /
[шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3r-TEMPLATE.md) вводит отдельную текущую
baseline. Проверяется только один нынешний vless/d вход по ключу SB-1 из O, без
поиска здоровой альтернативы. Внутри R неизменность полного configdigest/процесса/
настроек/boot/6PID/pin обязательна до и после; privateplan сохраняется ДО запроса.
Межпрогонное отличие от O отображается отдельным bool, не требует отката продукта.
Это явное изменение политики теста, не ослабление проверок внутри опыта.

Старая историческая идентичность НЕ доказана: [ключ подписки32бит](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/model.py#L50-L54)
и не сохранённые N/O значения endpoint не обеспечивают неизменность всех параметров.
R маркируется R-CURRENT-1 / CURRENT_UNIQUE_VLESS_AT_O_CASE_KEY /
historical_endpoint_identityUNPROVEN. Не называть его доказанно тем же endpoint N,
не переписывать N/P новым результатом. Новый полный текущий digest остаётся root600.

R делает один ограниченный HTTPS и ограниченное чтение журнала нового окна. Нет
смены pin/узла/цели/сканов/служб/режимов/правил/WAN/LAN/Tailscale. Старые helpers
используются только как неизменённые библиотеки; новый wrapper выдаёт stage+safe code,
не rawисключение. Started блокирует повтор даже при краше. На любой исход — отчёт,
без retry/fallback/следующего кандидата. M/L/J/SB2 уже приняты и не повторяются.

10новых узких fixture/mocked проверок wrapperPASS, RuffPASS, статическая проверка
команд ТЗ; старые helpers/runtime не менялись. Нет broadVM/netns/живых запросов/логов/
шлюза. Обновление02.11: Rbd512410a5515692a3870c8aba153535c742a0d2 получена, отрицательнаяпопытка.
[РазборR](REVIEW-REAL-MACHINE-0.2.0-wave3r.md), следующийSreadonly NOT_RUN.
Fullwave3/D1-on/E4/scopedfaults/LANUDP/IPv6/DNS/allTS открыты, wave4/DAE не начинаем.
Рабочая LAN считается работающей; on сохранён, старый always_off запрещён.
