# Разбор wave3t: большой пакет завершён, найден пробел независимого покрытия

[Фактический отчёт](https://github.com/1521572-lang/xgw/blob/8d208e9d25be2c0fee9dff2a6fa348db038150ae/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3t-2026-11-02.md),
commit **8d208e9d25be2c0fee9dff2a6fa348db038150ae**, FF merged.
TestedHEAD1e02778c3779d81b5fd0dd3bc82ef3c30472d5f2 /
treee2aeefb513d5650dae41afe7ea806ae8e26a1068. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7, runtimeempty/installed4equal/110.py==110.py/
6frozenSHAcorrect. Продукт не устанавливался.

## Принимаемые результаты

EXTENDED_BATCH_RECORDED, finalsummary,364.31с, семь collectionsRECORDED, requests0.
Все before/aftercontextflags/settings3/SBconfig/Xrayconfig/process/boot/6PID/pin/cache
сохранны. Tailscaleroutevpn/pooloff/HEALTHY/on/связь прежние. Это scopedreadonlyсбор,
не общийPASSработыкаждого узла/профиля/сетевого пути.

| Этап | Принятый факт |
|---|---|
| T1 | CurrentSBdigest не совпал с Rplan, только современныйreferencekey/неисторическийendpoint |
| T2–T3 | 8supportedrecords,6/67уникальныхVLESSсверокравны,0mismatch,61NOT_RUN; reference0matched |
| T4 |141SBbridge(d71/f67/m3),135REALITYформ,3Xrayreference; badcounts0/finalrejecttrue/marks0 |
| T5 |90savedscans,все>300с,38короткихOKbody; неfreshhealth/неcoreidentity |
| T6 | Ограниченные10минутныеkeywordqueries: xgw8rows,SB0rows,ошибокпарсинга/обрезкинет; не глобальноеотсутствиеошибок |
| T7 |12пассивныхsamples,carrier1/одинаковаяLANidentity/context/settings/process вточках; счётчики двигались |

Не превращать stability в точках в непрерывную пакетную трассу. Дельты в helper
[накоплены от начала наблюдения](https://github.com/1521572-lang/xgw/blob/1e02778c3779d81b5fd0dd3bc82ef3c30472d5f2/tests/stand/wave3_extended_batch.py#L515-L551).
Их нельзя складывать как трафик интервала. Формулировку таблицы «суммарно RX35774669/
TX924284684» до сверки с rootTJSON не принимаем как однозначный итог: U сопоставит
её с последним cumulative и с суммой cumulative. Старое наблюдение не повторять.
Ни один вариант этой цифры не является скоростью VPN/пакетной атрибуцией клиента.

## Дефект тестового покрытия, не runtime XGW

[Tsource_records](https://github.com/1521572-lang/xgw/blob/1e02778c3779d81b5fd0dd3bc82ef3c30472d5f2/tests/stand/wave3_extended_batch.py#L125-L159)
считает каждый элемент корневого JSON-массива конечной записью. Но элемент может быть
полным конфигом с outbounds. [independent_record](https://github.com/1521572-lang/xgw/blob/1e02778c3779d81b5fd0dd3bc82ef3c30472d5f2/tests/stand/wave3_extended_batch.py#L41-L96)
его не раскрывает и молча возвращаетNone при отсутствии leafprotocol/type.
Локальная fixture воспроизводит0supported на массиве корректных полных конфигов.
Это установленная недоработка коллектора. Фактическая структура двух PLAIN_JSON из T
не раскрыта отчётом; связь конкретного coveragegap с этой формой установит U на realcache.
T6/67 сохраняется исторически, новые числа не переписывают старый отчёт.

Уточнения других выводов:
- Смена SBdigest не доказывает, что всякая регенерация меняет файл. [При равномJSONapply
  прекращается без записиSBconfig](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/singbox.py#L125-L134).
  [Установка/перечитывание](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/singbox.py#L150-L176)
  и [rollback](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/apply/singbox.py#L202-L216)
  — известные пути записи; одни stat/digest не устанавливают, кто и почему писал реально.
- В схеме есть nodesfingerprint/tag и scansprobe_tag. Нет КОНКРЕТНОГОCORE в savedscan,
  а не всей идентичности узла. U свяжет строки readonly без приписывания scanядруSB.
- NoNewPrivs1 в процессе ZCode заблокировалsudo; это свойство канала исполнителя,
  не дефект шлюза. После действия владельца канал сталNNP0, пакет завершён.
  [Флаг наследуется и не снимается в этом дереве процессов](https://docs.kernel.org/userspace-api/no_new_privs.html).
  Не менятьNNP ожидаемоизолированногоSBworker, не обходить sudoers/паролем/prctl.
- Строки backlogT «нужно согласие на любую активнуюпроверку» не заменяют существующую
  авторизацию чата. Открытые тесты здесь ограничены запретами/подготовкой и отсутствием
  отдельного LANисполнителя, а не автоматически новым формальным согласием на каждыйшаг.

## Укрупнённый следующий пакет и реальная возможность исполнителя

Владелец03.11подтвердил: доступен только ThinkCentre с XGW. Нет управляемого устройства
за роутером. Не требовать новую SSHинвентаризацию/не выдавать hostзапросы за LANклиентские.
[ТЗ U](TEST-PLAN-REAL-MACHINE-0.2.0-wave3u.md) и
[единый шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3u-TEMPLATE.md) содержат восемь этапов:
history+аудитcumulativeT; исправленный независимый JSONcontainerwalk; всеdefaultVLESS;
текущийграф; diffcurrent/last-good/pending; keyedpersistedhealth; effectiveunitproperties;
boundedwriterjournal24h. Одинbackgroundworker, автопереходы при optionalUNAVAILABLE,
один полныйотчёт/приоритетныйbacklog. Не новый6минT7 и не очередной активныйREALITYrequest.

Fullwave3/D1-on/E4/faults/LANUDP/IPv6/DNS/allTS/performance остаются открытыми. Runtimepatch
не обоснован нулевыми staticbadcounts и пробелом тестов. Шлюз работает, on/WAN/LAN/
службы/правила/pin/Tailscale не меняются. Ни новыхсоединений, ни packetcapture, ни netns.
14узкихfixtures/mockedchecksPASS/RuffPASS; syntaxТЗпроверен. BroadVM/netns/liveнами NOT_RUN.
Реальная **wave3u NOT_RUN**, ожидается один TEST-REPORT-REAL-MACHINE-0.2.0-wave3u-ДАТА.md.

## После реального U

[Review U](REVIEW-REAL-MACHINE-0.2.0-wave3u.md): 101 supported, 66/67 equal,
reference12/12; текущий legacy-T на тех же U bytes даёт0/0/8 против46/47/8.
Исторический Tcache изменился; старые6/67 не переписаны, форма старойreference не доказана.
U подтвердил суммирование cumulative в таблице T; последние дельты —
RX5 517 331/TX139 736 077 байт. Не скорость VPN/пакетная атрибуция.
U8 превысил3с; writer не установлен. Следующий единый пакет V классифицирует
gap и объекты/один bounded journal; повтор T7/M/L/J/графа/units не нужен.
