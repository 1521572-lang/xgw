# ADR AQ: scoped wire evidence с отдельной закрытой host границей

04.11.2026. Принят для source candidate/offline qualification. Real AQ NOT_RUN;
host BLOCKED_SCOPE_REVIEW/HOST_NOT_RUN. C BLOCKED_BOOTSTRAP, все7gates false.

Проблема: AP сравнивал caller-supplied simulation identifiers. Переключение origin или
simulation_only у actual-looking JSON не доказывает источник, контекст, свежесть и полноту.
Нужны явные wire decoders и session ownership, без скрытого расширения прав исполнителя.

Решение:

1. Декодеры трёх форматов UNIT/PROCESS/NFT плюс collector context изолированы от I/O;
   strict size/type/schema/unknown rejection, точная граница supported subset.
2. Evidence выдаётся только сессией с exact typed backend и immutable fixture entries.
   Handles/expected/context/policy/методы привязаны внутри текущего owner process/thread.
   JSON импорт не переносит authority, session-local replay не durable fence.
3. MATCH относится только FIXTURE expected и named scope; aggregate/runtime всегда
   UNKNOWN. Complete domain/global graph/installed loaded identity не заявляются.
4. Host adapter намеренно всегда закрыт. Наличие предложенного argv/bounded transport
   не разрешает host запуск. Proc assembly/full sequence существуют только как unwired candidate.
   Для host нужны review конкретных capabilities, executable path policy, proc magic
   links/permissions/budgets/full profile и отдельное wire qualification по actual версии.
5. Offline worker сохраняет accepted AD audit guard. No subprocess/socket/liveops в
   workload; start/monitor/report wrappers учитываются отдельно. Guard не sandbox.

Альтернативы отклонены: доверять trusted=true/boot digest/caller origin; менять AP
simulation guard; list ruleset/весь proc/полный systemctl inventory; отключить audit guard;
обучать expected по тому же observed snapshot; переводить partial в runtime acceptance.

Ограничения: метод/flat-reference pinning не защищает от враждебного Python/root или
произвольной подмены globals/private internals. Fixtures synthetic, не измерения машины.
Не atomic snapshot; PID/starttime/netns checks не устраняют ABA/TOCTOU и не доказывают
всех descendants. Неподдержанные NFT objects никогда не исключаются ради зелёного MATCH.
Предложенный transport не доказывает свой executable после lstat; это отдельный host gate.

Последствия: можно квалифицировать parsing/provenance/partial lifecycle одним безопасным
offline batch. Нельзя активировать C/D/E, repair/guardian/install/fault или делать вывод
о LAN/performance/ТСПУ. Independent original-on/code/unit rescue остаётся prerequisite
до install/fault. Ни WAN, ни выходящий LAN адаптер не изменяются.

Документы: [API](API-CONTRACT-WAVE3AQ.md), [исходное ТЗ](PR-SPEC-WAVE3AQ-READONLY-OBSERVATION-SOURCES.md).
Полнота resource source table добавляется с exact source commit anchors до передачи Flash.
