# Единое ТЗ исполнителю: возврат исходного on, REC-A–E


## Актуально после AC — единый AD130 source-hook пакет (03.11.2026)

[ACreport](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ac-2026-11-03.md) проверен:
51/51,A28/B16/D7; fakepositiverestorations2/expectedfailure1/refusals2/unused2;
measuredtimings5, WORKLOAD8directchildren+7driverlaunchobservations. HEALTHY/on/pool/
версии/связьсохранны. [Разбор AC](REVIEW-REAL-MACHINE-0.2.0-wave3ac.md) уточняет
Acounts:10COMPLETED/2REFUSED/14UNKNOWN/2terminalcases, ане11/15. Общий51PASSверен.
AC51/AB32/AA22/Z19/Y6/X26/W25неповторять. Runtimeгейтыfalse.

[Единое ТЗ AD](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ad.md) объединяет130НОВЫХcases:
38вариантовреальныхметодов×LEGACY/OWNED/FENCED +16context/error/readerchecks.
[ADR AD](ADR-REC-C-OPT-IN-SOURCE-HOOKS.md). Одинstart/автопереходы/partialreadout/одинreport,
максимальныйготовыйsafeобъём. РеальнаяAD NOT_RUN; локально8узкихtests/RuffPASS.

Source diffпротивpin351 теперь4A+7M: ownership*.pyдобавлены; 7модулейCapture/Backend/
Applier/SingboxCore/Job/ApiClient/managedполучилиopt-inhooks. 31instancewrapper+managed
_update. СохраняемостьстарыхbodyпроверяетсяAST. Вsourceстарые7модулейтеперьимпортируют
hooks; раннее«нетimports»нижеисторическое. Ноexistingruntimeactors coordinatorНЕпередают,
NoneсохраняетlegacyиНЕобеспечиваетfence. Installedruntimeне меняется/неустанавливается.
Mandatorybinding/realverifier/repair/recovery/bootstrapNOT_IMPLEMENTED.

ADfreezehelper+publicSHAmanifest+114sourcefilesвusernotes, импортprivatefrozen_ad, не
installedXGW. Runner/API/service/TUNподставные, dummycorefilesтольковfixture. Auditguard
отказываетprocess/socket/out-of-noteswriteдоэффекта; этонеhostilecode securitysandbox.
Никакихworkloadprocesses/ACfakeDповторов/служб/сети. FENCEDchecksпроверяютfixturecontent/
modes/entriesиtrace0; OWNEDreturnclass+одинreceipt. CallerassertionsнеactualKERNEL/APIproof.

Coordinatorсохраняетbusinessresult/exception, nestedrolesделятticket, nestedfailuretaints
outer. Deferredresultsотвергаютсявключаявложенные, thread/PIDcontextпроверяется. Новая
регрессиязакрываетescapeвложенногогенератора; генераторbodyнеисполняется. DefaultNone
неразрешаетзаявлятьglobalfence/ставитьlivefault. LiveCinstallationBLOCKED_BOOTSTRAP.
Nooff/install/G1/WAN/LAN/TS/pin/pool/config/service/ruleschanges. OnlyThinkCentre,
workingLAN/HEALTHY/on. Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты,
неwave4/DAE. Далееистория; прежнийACNOT_RUNзаменёнфактическимотчётом,неliveготовностью.



## Актуально после AB — единый максимальный пакет AC (03.11.2026)

[ABотчёт](TEST-REPORT-REAL-MACHINE-0.2.0-wave3ab-2026-11-03.md) проверен:32/32,
3processcases/4children, command0/shapevalid; HEALTHY/on/pool/versions/связьсохранны.
[Разбор AB](REVIEW-REAL-MACHINE-0.2.0-wave3ab.md). Scopefoundationonly; AB32/AA22/Z19/Y6/
X26/W25 не повторять. Driver/fence/repair/activegatesреальнойсети по-прежнемуfalse.

Прямоеуказаниевладельца: последующиеТЗ — весьмаксимальныйготовыйsafeобъём заодинзаход,
безпотерикачества: независимыеветви/автопереходы/partialresults/одинreport. Не дробить на
микрозадания. Globalidentity/baseline/privacySTOP и prerequisitegatesнеослаблять.

[ТЗ AC](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ac.md) объединяет51 новыйcase:28adapter +
16readonlydiagnostic +7fake-onlyprocess. [ADR](ADR-REC-C-ADAPTERS-AND-FAKE-D.md).
Один detachedusercollector/EXCLstart/checkpoints/summary/Markdown. Casefailнеблокирует
другиеветви. Реальная AC NOT_RUN. Локально8узкихtests/RuffPASS, fullbatchнеисполнялся.

Source diffпротивpin351 теперьровно3новыхмодуля:ownership.py(ABbytesunchanged),
ownership_adapters.py,ownership_diagnostics.py. Прежнийruntime/entrypoints/unit/config
не менялись и не импортируютновыемодули; installedruntimeнеобновлялся. Неinstall/restart.
Adapterverification — callerassertions, diagnosticsneverrepair/promote/prune. FakeD
возвращаеттолькоusercasefileпослеexit/crashсвоегоcontroller; это неслужба/таймер/
networkguardian/реальныйrescue. Положительныхfakerestorations2, expectedfailure1,
refusals2,unused2, не7restored. D01–D05 timingmeasured; D06/D07 timeNOT_MEASURED.

C-ENTRY/verifier/fence/repair/recovery/bootstrapNOT_IMPLEMENTED. Liveустановкапо-прежнему
BLOCKED_BOOTSTRAP; realEтребуетC+D+независимоговозвратаисходногоon. Nooff/install/G1/
WAN/LAN/Tailscale/pin/pool/service/ruleschanges. OnlyThinkCentre/workingLAN/HEALTHY/on.
Fullwave3/D1-on/faults/LANUDP/IPv6/DNS/E4/performance/allTSоткрыты,неwave4/DAE.

Ниже история; прежнийAB NOT_RUN отменён фактическим отчётомвыше, livegatesнеподменять.



## Актуально после AA — dormant registry AB (03.11.2026)

[AAотчёт](TEST-REPORT-REAL-MACHINE-0.2.0-wave3aa-2026-11-03.md) принят:
22/22, триprocesscases/3children, command0/shapevalid, HEALTHY/on/pool/versions/связь
сохранны. [Разбор AA](REVIEW-REAL-MACHINE-0.2.0-wave3aa.md). Это sandboxscope;
реальные fence/recovery/activeflagsfalse. AA22/Z19/Y6/X26/W25 не повторять.

Следующий [ADRfoundation](ADR-REC-C-REGISTRY-FOUNDATION.md) и
[единое ТЗ AB](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ab.md):32 новых проверок sourceRegistry,
включая bootidentity/metadata/receipts/pre-postrename и3processcases/4children.
Реальный AB NOT_RUN. Новый src/xgw/ownership.py — **единственное source-добавление**,
без import-timeI/O и без импорта из существующего runtime/entrypoints. Все старые src,
packaging/config/CLI неизменны, на ThinkCentre не устанавливается. Поэтому source diff
не пуст, а установленный рабочий runtime остаётся прежним.

Unifiedrecord сохраняет generation+writerremoval+receipt одной заменой. Это заменяет
двухфайловый COMMITTINGgap AA, но не даёт kernel/APIatomicity. state.next → failclosed,
без autorepair/prune; COMMIT_UNCERTAIN не разрешает повтор. Receipts — assertions caller,
не networkproof. FoundationC-REG1 не закрывает C-REG2repair/C-ENTRY/C-VERIFY/bootstrap.

Далее fixes поAB либо dormantadapters/repair/receipts; fake-only независимыйD может
разрабатываться до Cinstallation. Установка C-ENTRY остаётся BLOCKED_BOOTSTRAP:
независимый возврат исходных code/unit/on ещё не реализован. Nooff/install/G1/WAN/LAN/
Tailscale/pin/pool/service/ruleschanges. ТолькоThinkCentre, workingLAN; hostнеLANclientproof.
Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.

Ниже история. Прежние AA/Z NOT_RUN — статус до полученных выше фактических отчётов.



## Актуально после Z — lifetime admission AA (03.11.2026)

[Отчёт Z](TEST-REPORT-REAL-MACHINE-0.2.0-wave3z-2026-11-03.md) проверен:
19/19, три realprocesscases/4children, command0, HEALTHY/on/pool/versions/связь сохранны.
Принят только cooperative sandboxscope, реальный fence/driver/activeflagsfalse.
Y/REC-B snapshot/check-only принят ранее; Y6/X26/W25/Z19 не повторять.

[Разбор Z](REVIEW-REAL-MACHINE-0.2.0-wave3z.md),
[аудит entrypoints и bootstrap](REC-C-CALLSITES-AND-BOOTSTRAP.md),
[ADR lifetime admission](ADR-REC-C-ADMISSION-LIFETIME.md),
[единое ТЗ AA](TEST-PLAN-REAL-MACHINE-0.2.0-wave3aa.md).
AA22 новых cases/3child — только user-sandbox; реальный AA NOT_RUN до отчёта.

Уточнение прежнего долгого ownershiplock: вокруг systemctlrestart он создаёт риск
parent→ExecStartPost→xgwnettun→тотжеlock. Новый кандидат использует короткий registrylock
и durabletickets на lifetime writers. При непустом registry lease сразу отказывается,
без PENDING, orphanpruning и остановки служб. COMMITTING/UNKNOWN запрещают silentretirement.
Это не productintegration и не доказательство общего lockgraph.

Далее productregistry/entrypointadapters/outcomereceipts. Fake-only независимый REC-D
можно разрабатывать до Cinstallation, потому что он не меняет сеть; это уточняет старое
строго последовательное описание C→D. Реальный E требует принятия и C, и D, и bootstrap.
Установка C-ENTRY пока BLOCKED_BOOTSTRAP: нет независимого возврата исходных code/unit/on.
Nooff/install/G1/WAN/LAN/Tailscale/pin/pool/service/ruleschanges. ThinkCentreonly, workingLAN.
Fullwave3/D1-on/fault/LANUDP/IPv6/DNS/E4/performance/allTS открыты, неwave4/DAE.

Ниже история предыдущих кандидатов; прежние NOT_RUN не отменяют принятые выше отчёты.


Обновление Y1440d51: REC-B snapshot/check-only qualification принята, Xguardtestbug закрыт.
Ymanifest остаётся PLANNED_NOT_ARMED. Следующий REC-C test candidate реализован в
tests/stand/wave3_writer_fence_dry.py; Zпередаёт19cases/3processcases без product integration.
ADR-REC-C-OWNERSHIP задаёт epoch/token/lease/retirement; runtime fence/driver не установлен,
реальная Z NOT_RUN. Старые блокировки/живые writers и root snapshot в Z не затрагиваются.


Обновление после X283bb12: REC-B partial/guard contract bug. Исторический collector
ошибочно ожидал forward priority5 вместо source10. Новый Y v2 исправляет тест и
публикует safe guard observations; старый X/run неизменён, живые правила не менять.
Y объединяет6 новых guard cases и snapshot/check/after; реальная Y NOT_RUN. REC-B пока
не закрыт, переход к REC-C/D/E не выполнен. Подробно REVIEW-REAL-MACHINE-0.2.0-wave3x.md.


Роль: исполнитель кода уровня Principal Linux/Netfilter engineer. Минимум VM-прогонов,
проверки реального systemd/nft/network — через подробное ТЗ Flash на ThinkCentre.
Исходное решение: [ADR](ADR-RECOVERY-ORIGINAL-ON.md).
Это план реализации по атомарным изменениям, а не разрешение выполнить будущие сетевые
операции из текущего W. Не добавлять скрытый enable/restart/guardian в проверку модели.

## 1. Зафиксированный исходный код и evidence

- Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7.
- Фактический V report: be1fc1bf8b5bcc9a6e0f9b1b68eeaa8680ad1acf.
- Working HEALTHY/on; ThinkCentre→роутер→устройства; Tailscale иногда через VPN.
- Отдельного управляемого LAN-клиента нет. Не повторять вопрос об инвентаризации.
- [net.lock](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L240-L241)
  и [enable/disable](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/src/xgw/net/capture.py#L749-L768)
  не являются готовой независимой страховкой.
- Старый [always_off launch](https://github.com/1521572-lang/xgw/blob/351fb54e074f4a7b497a8a4244fc74c6088788d7/tests/stand/wave3_safety.py#L192-L216)
  запрещён на рабочем on; исторические helpers не менять.
- U/V не доказали runtime mismatch. Не чинить серверы/ключи/пулы ради прохождения теста.

## 2. Общие требования к реализации

Каждый атомарный PR/commit должен иметь trigger, конечное поведение, точный scope,
ограничение времени и примеры отрицательного результата. Не смешивать реальную проверку
независимости, логическую модель и проверку пользовательского трафика.

Ни один неизвестный gate не становится true по умолчанию. Не сериализовать приватные
данные в stdout/отчёт. Root material:0700/0600, no symlink, EXCL start/manifest, bounded
reads, byte digest. Public: bool/count/fixed enum/Git/source SHA, без значений правил/config.

Не использовать общий restore scripts с произвольными shell-командами из manifest.
Операции типизированы и соответствуют allowlist, argv собирает доверенный driver;
path/family/table проверяются на принадлежность scope, а не только regex.
Противоречивые или дублированные поля JSON, неизвестный version/scope, wrong boot,
неверный digest, поздний start и чужой run → отказ до fault.

Общий бюджет задаётся заранее, не увеличивается heartbeat/pulse/перезапуском модели.
Прогресс записывается атомарно; partial не выдавать за финальный результат. Команда,
driver, восстановление и связь имеют отдельные результаты. Exit0 контроллера не PASS сети.

## 3. REC-A — чистая модель, текущий кандидат

Файл tests/stand/wave3_on_recovery_model.py. Никаких runtime imports XGW, чтения живых
config/DB/proc, subprocess/socket/nft/systemctl, служб, timer или сетевых действий.
Исполняемый интерфейс только `simulate`; запуск с оптимизацией Python запрещён.
Виртуальное время вводится явно. Внутри25 сценариев нет sleep и ожиданий реального времени.

Свойства:

1. Неизвестные предусловия по умолчанию false, требуется именно bool True.
2. Scope CAPTURE_TABLE_ONLY; D1_INSTALL и расширение scope отвергаются.
3. Фиксированные сроки:15с fault,20с restore,5с verify, hard≤45с от вооружения.
4. Fault не начинается после дедлайна/при неподтверждённом driver/старом поколении.
5. Исчезновение virtual controller не продлевает срок. Early job finish тоже ведёт к restore.
6. Повреждённый snapshot не replay; failed transaction/verify/timeout не RESTORED_ON.
7. Никакого RESTORED_OFF, fallbackdirect и автоматического обхода guard.

Доставка: текущий code+ADR+это ТЗ+ТЗ W+единый шаблон. Локально только AST/static safety/Ruff;
W e670ceb подтвердил25/25 на ThinkCentre; REC-A принят как синтетическая модель.
Model PASS не разрешает REC-E. Реальный driver/fence/snapshot остаются не реализованными.

## 4. REC-B — snapshot и построение плана без применения

Новый отдельный stdlib-компонент планирования с driver protocol. Не импортировать старую
страховку с побочными эффектами. Не включать автоматически в install/service lifecycle.

Входы: read-only факты текущего on, точное поколение SB/Xray/config settings, boot и
process identities, scoped nft structure и RPDB, текущая принадлежность таблиц, ожидаемый
guard. Секреты и raw rules только в закрытом material, не в public manifest.
Unknown/несогласованные входы → BLOCKED_BASELINE, без подготовки исполняемого fault.

Выходы: versioned private snapshot + public qualification с перечнем проверенных bool,
readcounts/limits, status=PLANNED_NOT_ARMED. Подготовка плана не вооружает механизм.
Снимок создаётся эксклюзивно; изменившееся во время чтения поколение → STALE_SNAPSHOT,
не повтор через новый каталог радиPASS. Сам факт доступного last-good не выбирает его
как baseline: исходник — текущий реально подтверждённый on.

Транзакция ограничена XGW capture table, поддерживает исходное наличие/отсутствие
затронутой таблицы. Guard и чужие таблицы не входят в удаляемые объекты. No flush ruleset.
Не переносить handles/counters как доказательство семантической идентичности.
RPDB читается для verification; его изменение не часть первого fault/recovery scope.

Узкие отрицательные fixtures: symlink, неправильный владелец/права, limit, duplicateJSON,
wrongfamily/table, чужая таблица, oldboot, неполный guard, отсутствующий snapshotpiece,
конфликт generation, malformed transaction. Применять nft даже с -c только по реальному
подробному ТЗ после конкретного review; nft-c не имитирует kernel-acceptance удалённо.

Один реальный пакет Flash: source identity → readonly collection → plan qualification →
все отрицательные синтетические fixtures → один отчёт. Никаких live fault/arm/replay.

Кандидат REC-B теперь реализован в tests/stand/wave3_on_snapshot.py. ТЗ X собирает private
material и scoped JSON-проект, выполняет один nft -c -j -f - без применения и after.
26 validation cases объединены в тот же worker. Реальная X NOT_RUN, absent-table replay
не проверен, manifest PLANNED_NOT_ARMED и все active/fence/driver gates=false.
Текущий collector сознательно stdlib: raw TOML capturedefaults100/1, raw panel opaque,
без productparser/старогоguardian. Для REC-C использовать отдельную инвентаризацию
REC-C-WRITER-INVENTORY.md; её наличие не реализация fence.

## 5. REC-C — writer fence и владение поколением

Перед driver определить всех writers затронутых capture/guard/config-dependent путей:
Capture._load/enable/disable/open/close/tailscale_*; install/migration; apply paths;
демон, CLI, панель и связанные job. Каждый путь имеет точную ссылку на текущий код и
явный ответ: participates, read-only или outside proved scope. Не пропускать API/фоновые
обновления только потому, что UI не используется. Список из текущего анализа не полон.

Разработать единую модель владения поколением. Net.lock сам по себе не доказывает
достаточность fence: он не охватывает все config writers и не должен блокировать
автономное восстановление на30с. Digest check без исключения гонки не fence.
Fence должен иметь владельца и deadline; crash/старый lease не освобождает его так,
чтобы поздний job начал новый fault. Драйверу нужна проверяемая связь с тем же run.

Не удалять чужие lock-файлы, не похищать flock и не останавливать произвольные службы.
При невозможности доказать writer quiescence вернуть BLOCKED_WRITER_FENCE и закончить
разрешённые независимые этапы. Не подставлять fixture True в реальный qualification.
Изменение product writers — отдельный атомарный кандидат с узкой регрессией. До установки
на ThinkCentre нужен подробный пакет с независимым возвратом исходного on, поэтому
первую итерацию делать только с test drivers/планом. Если возникает циклическая зависимость
«установка fence требует уже работающего восстановления», решить bootstrap отдельно
в проекте до установки; не обходить её незастрахованной установкой.

## 6. REC-D — независимый driver, сначала без сетевых действий

Driver получает замороженные root material, fixed deadline и именованный scope. Никакого
импорта меняемого runtime, обращения к подпискам/сети/модели, ожидания UI/SSH.
Вызовы bounded с единым общим бюджетом; timeouts не суммируются за hard deadline.
После подтверждённого истечения срока нельзя продлить/cancel обещанный возврат on.

Архитектуру запуска на реальном systemd255 выбрать и описать в следующем ADR/patch:
кто запускает до job, какие зависимости гарантируют переживание controller exit,
как отличить действительно armed от успешного Popen/systemctl return, кто пишет status,
что происходит при ошибке запуска/несоответствии boot/записи половины manifest.
До этой реализации системные unit/timer templates не публиковать как готовые команды.

Первый реальный driver опыт только с безопасным test adapter: никаких nft/ip/service/
config операций; имитируемый job отдельного контура и закрытый result artifact.
Проверить потерю controller process, поздний start, отсутствие pulse, kill только
собственного тестового job, deadline и конечный результат. Это потребует отдельного
конкретного scope: текущий W не запускает служб/таймеров и не разрешает такой опыт.

Итог driver dry-run: AUTONOMY_DRY_RECORDED с measured end-to-end timings и source identity.
Это не NETWORK_RESTORED_ON. При ошибке независимости — FAIL и active gate остаётся false.

## 7. REC-E — первый ограниченный реальный fault, ещё не готов

Составлять ТЗ только после отчётов B–D и review точного кода. Один canonical protocol:
исходный HEALTHY/on → freeze/validate → реальное подтверждение armed/fence → один
scope-limited job → автономный возврат → verification → один обезличенный отчёт.
Никаких вариантов «если не работает, попробуй другой firewall/profile».

До первой мутации должны быть готовы: частный baseline, понятная цель fault, current
generation, проверенный guard, независимый driver, общий бюджет≤45с и полный список
разрешённых argv. Отсутствие любого пункта — NOFAULT/NOT_RUN, без сдвига сроков.
Не принимать только heartbeat модели или Tailscale за доказательство сохранности Flash.

Verification разделяет: table transaction rc, semantic guard/capture/RPDB, actual
capture.on, generation, процессы, WAN invariants и реальную связь. Не объявлять
RESTORED_ON по одному nft rc0 или службе active. Host HTTPS не заменяет LAN client proof.
Если возврат не подтверждён — FAILED/UNKNOWN, не off как «успешный rescue».
Сбои kernel/power/WAN link и глобальный nft flush не в scope.

Реальный scope не расширять на D1-on только потому, что узкий capture fault прошёл.
Для D1-on нужен отдельный snapshot кода/unit/DAC/config dependencies, порядок запуска
и устранённая зависимость от меняемых executables. Для core faults — отдельный план
восстановления процессов. Для LAN UDP/IPv6/DNS/E4 — подходящий клиентский путь; только
ThinkCentre не выдавать за управляемое устройство за роутером.

## 8. Общая доставка, остановки и отчёт

Обычный FF push в freepool, без ZIP/patch/force. Каждый готовый реальный пакет содержит
точные SHA/HEAD/tree/product diff, уникальные шаги, одну команду на шаг, маркеры/rc,
общие STOP и автопереходы при optional отсутствиях. Весь независимый разрешённый объём
одного этапа — в одном запуске и одном отчёте. Не присылать новое ТЗ после каждой строки.

При local mismatch не менять сеть ради PASS. При baseline/identity/privacy STOP
сохранить partial/NOT_RUN. При обрыве>1мин восстановление уже должно выполняться локально;
задание следующей команды модели не считается планом. До доказательств активные шаги
остаются не выполненными. Задания REC-B–E не обозначать завершёнными из наличия этого ТЗ.

Принятые M/J/L/Npartial/Pblocked/Q/Rnegative/S/T/U/V сохранить. Missing_identity и writer
остаются отдельными недоказанными вопросами; не подменять ими recovery gate.
Сохранять существующую рабочую эксплуатацию. Полная wave3, WAN IPv6 migration debt,
performance/all Tailscale открыты. Wave4/DAE до acceptance не начинать.
