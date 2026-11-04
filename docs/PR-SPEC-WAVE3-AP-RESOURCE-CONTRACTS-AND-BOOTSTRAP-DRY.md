# ТЗ разработчику AP: контракты ресурсов и dry-run подготовки запуска

Статус 04.11.2026: задание на реализацию, НЕ готовый тестовый пакет Flash.
База: f75fdc8803f3a2e24f1ee90b3f8d27c1aaa7d1af, ветка freepool.
Приёмка AO66 завершена. Код продукта на этой базе —122 Python-файла, pin351:
12A11M. Installed runtime не обновлялся. AM startup failure, AN850/852 и AO66
не переписывать в один вымышленный полный повторный852PASS.

## Цель следующего большого пакета

Перейти от частного FILES-контракта к точному описанию всех ресурсов, нужных операции,
и проверяемому плану подготовки запуска. Сделать одним заходом независимые компоненты,
их интеграцию без активации и один готовый пакет квалификации Flash. Не наращивать
число прежних fault/metadata cases ради количества. Закрыть перечисленные ниже
требования либо оставить конкретные NOT_IMPLEMENTED/UNKNOWN с объяснением.

Это ТЗ не разрешает установку, live collector, изменение WAN/LAN/Tailscale/пула/ядра,
вызовы nft/ip/systemctl/API, новый SSH inventory, services/units/timers/guardian,
off/on/fault/replay. На ThinkCentre рабочая раздача HEALTHY/on. LAN-клиента нет.
Сквозные LAN/UDP/IPv6/DNS/performance проверки с host не выдавать за выполненные.
Независимый original-on/code/unit rescue обязателен ДО любого будущего install/fault.
Входящий обрыв>1мин модель следующей командой не исправит. All7runtimegates=false.
Live C остаётся BLOCKED_BOOTSTRAP; AP не разрешает C/D/E.

## AP-1. Явный контракт ресурсов

Добавить изолированный модуль с неизменяемыми типами, не подключая его к daemon/CLI.
Публичный интерфейс: ResourceContract, ResourceRequirement, ContractDecision.
Constructor/validate/compile не выполняют I/O и не создают actors/registry.

ResourceRequirement описывает domain, стабильный логический resource_id,
expected-state identifier и required/optional. Уникальность по(domain,resource_id),
строгие типы, предельное число требований, отсутствие пустых/неизвестных domains,
отсутствие дубликатов. Не хранить credentials/URI/ключи в публичном результате.
expected-state identifier не доказательство наблюдаемого состояния.
Domain names совместимы с ownership_adapters.CHECKS: FILES/KERNEL/API/PROCESSES/
MODE/ROUTES/MARKERS; отсутствие реализации любого required domain запрещает COMPLETED.
Не вводить неявный FILES-only fallback для lifecycle/network/core операций.

Определить таблицу требований для объявленных9actors/50hooks и15lifecycle functions.
Для каждого перечислить требуемые domains и открытые неучтённые зависимости.
Опирайся на реальные тела функций и вложенные вызовы: не выводи domain только из
названия метода. Если нельзя доказать полноту, completeness=UNKNOWN, не READY.
Таблица declared subset не глобальный граф. Отдельно отметить installer/uninstaller,
legacy None callers, callbacks, фоновые задачи и ссылки, не охваченные контрактом.
Не менять сохранённую семантику этих путей и не считать их автоматически fenced.

## AP-2. Сравнение ограниченных наблюдений

Добавить чистые функции compare_observation(contract, observation) и aggregate(...).
Observation передаётся явно; никаких команд, сетевых запросов, чтения /proc или
системных путей в этом пакете. Не придумывать неподтверждённые Linux wire schemas.
Для будущего source-адаптера задать версионируемый внутренний envelope:
domain, schema_version, collection_status, code/boot/context binding, bounded payload.
Реальные wire-format декодеры потребуют отдельного источника и подтверждённых fixtures.

Результаты MATCH/MISMATCH/UNKNOWN/UNSUPPORTED различаются. Missing input, truncated
input, wrong type, contradictory observations, unknown schema, identity mismatch,
absence of provenance, unsupported clauses, timeout/status unknown → UNKNOWN или
UNSUPPORTED; не пустой набор, не MATCH, не нулевые счётчики по умолчанию.
Несовпадение доказанного expected-state → MISMATCH. Explicit absence может быть MATCH
только если конкретный source умеет доказать полноту нужного scope.

Поддержать independent partial results: одна недоступная domain не стирает результаты
остальных, но блокирует итоговое completion. checked — фактически проверенный prefix,
не доказательство полноты. Ограничить глубину, размер входов, число элементов и время
чистого сравнения; duplicate JSON keys/NaN/Infinity и неоднозначные типы отвергать,
если JSON decoder входит в реализацию. Не сравнивать команды по строке и не исполнять
ожидаемые значения.

Synthetic fixtures обязаны иметь simulation_only=true. Их результаты НЕЛЬЗЯ преобразовать
в accepted Verification для реального writer. Новый Decision не является автоматически
ownership_adapters.Verification. Caller-provided boolean trusted/provenance_verified
не превращает произвольный snapshot в kernel/API/process evidence.
Actual collectors и trusted provenance boundary пока NOT_IMPLEMENTED.

## AP-3. Dry-run план подготовки запуска

Добавить BootstrapInventory, BootstrapPlan, plan_bootstrap(inventory, contract).
Вход — explicit, ограниченный набор фактов, полученный caller; планировщик pure.
Каждый факт имеет origin/status, code binding и возможность UNKNOWN. Не считывать
реальные units/config/registry/kernel ради заполнения пропусков.

План выводит фиксированный ordered список необходимых действий и блокировок:
IDENTITY_UNKNOWN, ACTOR_GRAPH_INCOMPLETE, DOMAIN_UNSUPPORTED, WRITERS_LIVE,
WRITERS_UNKNOWN, STAGE_UNPROVEN, RESCUE_NOT_QUALIFIED, ORIGINAL_ON_UNPROVEN,
READY_FOR_REVIEW. Конкретные enums можно уточнить без ослабления требований.
READY_FOR_REVIEW означает полноту описания dry-плана, НЕ permission/install/runtimeREADY.
На базе AP live_activation_authorized=false всегда.

Учитывать writer_total отдельно от unknown_writers. writer1/unknown0 означает LIVE,
не idle. Stage_VALID_UNPROVEN не разрешает promotion/repair. Registry schema mismatch/
wrong boot/code/uncertain completion acknowledgement не разрешают миграцию или retry.
Нет автоматического release/prune/retire/rollback/replay/repair. Не создавать store.

План должен явно содержать НЕВЫПОЛНЕННЫЕ prerequisites будущего original-on/code/unit
rescue. Не генерировать самовыполняющийся shell, service unit или сетевые команды.
Не выбирать always_off как способ восстановления. Ни один результат planner не
должен вызывать Composition.run/Registry.initialize/команды установки.

## AP-4. Дремлющая интеграция и конечные артефакты

Создать явный integration facade: контракт + источник observations + dry inventory.
Constructor не I/O. Facade возвращает bounded diagnostics, dry plan и unsupported/
unknown причины. Он не активирует existing runtime и не меняет defaults ownership=None.
Не обходить существующие FileCompletion/BuildCompletion требования и не расширять
accepted CHECKS на основании synthetic MATCH.

Документировать путь от текущей частной композиции к будущему live C:
1. Полная таблица требуемых ресурсов и неохваченных writers.
2. Реальный readonly source collector и provenance/identity binding — отдельная
   реализация, разрешения и реальный отчёт; в AP их нет.
3. Whole startup/entrypoint composition и независимый original-on/code/unit rescue.
4. Лишь затем отдельное review и квалификация live C/D/E с прежними STOP.
Не считать пункты2–4 завершёнными из успеха pure fixtures.

## Приёмка и один пакет для Flash

Локально минимум: синтаксис/согласованность патча и узкие tests новой логики. Старые
AO66/AN850/AL/AK/... и широкие VM/WSL suites не повторять. Нужны representative проверки
unknown propagation, conflicting/provenance-less data, partialaggregation, synthetic
decision rejected by runtime adapter, LIVE1UNKNOWN0 и dry-only отсутствие side effects.
Факты PASS не подменять запланированными cases. Не переиспользовать диагноз по exception
class без наблюдения конкретного пути.

Перед передачей Flash написать подробное единое ТЗ по существующему образцу:
- уникальные номера, одна команда на шаг, exact HEAD/tree/SHA/source inventory;
- реальный freeze/bootstrap/source loader проходит отдельную узкую regression;
- один READY/start, автоматические independent ветви, частичные результаты, один report;
- started/claim/emptycheckpoint/firstcase/finalsummary различаются; fail доcases
  оставляет honest emptycheckpoint или fixedfailure в чат без обхода F3;
- expected operation exceptions принимаются только явно; прочие исключения FAIL;
- start/monitor/show/shape/report rc раздельно, workerexit NOT_COLLECTED если не наблюдался;
- bounded readonly публичный отчёт, полный review без truncation, strict prefix/footer/F3;
- нет even-readonly host/kernel/units/API collector без отдельного разрешённого scope;
- all runtime gatesfalse, simulation-only results ясно отделены от actual observations;
- свежие HEALTHY/on/pool/link bookends как наблюдения, не continuous/LAN proof.

Включить весь готовый независимый объём AP-1…4 за один заход. Число сценариев определяется
реализованными ветвями и проверяемыми инвариантами, не требованием превысить852.
Если часть не готова, не включать опасную/неработающую ветвь ради объёма. Перед
публикацией проверить Git LF bytes/SHA, форматы partial reports, отсутствие credentials
и соответствие всего ТЗ фактическому runner. Remote delivery обычным FF origin/freepool.

Обязательные deliverables: код, schema/API contract, resource table с exact file:line
ссылками, ADR с trust boundary, атомарные commits и один готовый TEST-PLAN/TEMPLATE/
runner/manifest. Доставка этого PR-spec сама по себе не реализация AP и не реальный прогон.
