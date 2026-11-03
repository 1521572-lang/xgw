# ADR: opt-in schema2 code identity и readonly build preflight

Обновление04.11.2026: [AK435/437](REVIEW-REAL-MACHINE-0.2.0-wave3ak.md), две ошибки
в тестовых fixtures, fullqualificationHOLD. [AL756](TEST-PLAN-REAL-MACHINE-0.2.0-wave3al.md)
исправляетtargets без productpatch. Ниже исходное решение доactualAK; runtimegatesfalse.


Статус04.11.2026: source candidate готов, реальный AK437 NOT_RUN.
[AJ принят328/328](REVIEW-REAL-MACHINE-0.2.0-wave3aj.md).
[Единое ТЗ AK437](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ak.md).

## Проблема

Одна bootidentity и generation не отличают старый процесс от нового с изменённым
writer contract. Нельзя разрешать реальный recovery на основании generation без
согласованной версии кода, unit contract, writer boundaries и domain verification.
До этого изменения Registry был исключительно schema1 и не имел code namespace.

## Принятое решение

CodeIdentity — exact dataclass protocol2+source/unit/surface canonical SHA. No I/O.
Registry получает code_identity=None по умолчанию: старый schema1/state/token/summary
сохраняются. Explicit CodeIdentity создаёт ТОЛЬКО новый schema2registry. Code record
лежит в том же state.json/state.next атомарном commit, writer/recovery tokens содержат
code digest. Каждая операция проверяет schema/code/boot/context до mutation. Совпадение
идентичности нужно также для receipt lookup и recovery begin/retire. Wrongcode не может
«дозавершить» retainedtoken. Диагностика readonly, stage не promote/delete/repair.
Нет implicit migration/downgrade/reuse; старый exact public Registry reference отказывает
schema2. Legacy читатели взаимно читают schema1 в same-process fixtures.

CodeSeal — explicitroot/UID/exact paths+SHA+modes, bounded anchored NOFOLLOW reads,
regular/nlink1/owner/mode/2MiB/file16MiBtotal, directory/inventory/preposthash checks.
Expected1–256files, depth≤16/root≤64parts. Root/descendantdirs700/750/755, ancestors
NOFOLLOW без полного ancestorDAC/mountpolicy. File checked — actual verified prefix.
Ничего не устанавливает/исполняет/исправляет. Sequential evidence не atomic snapshot.
Futureproductionstartup должен отдельно защитить fixedroots/pathalias/mount/permissions.

SurfaceCatalog — declared50actor methods+15lifecyclefunctions. Без actorconstruction/body
закрепляет wrappers/code/defaults/defaultfunctioncode/closure refs/signature, роли и
declareddependencies/bindingtables. Manifest hashes defaultvalues, rawdefaults в отчёт
не идут. Moduleprefix normalized, frozen/source catalog одинаков. Не arbitraryglobals/
fullcallgraph/bytecode hostile-sandbox. Failure checked0 не attestedprefix.

CodePreflight — constructor без I/O, exactproviders/identity/methodrefs/PID/thread.
Каждый observe заново проверяет source/unit/surface; ordinarymismatch сохраняет все
independent results, exception/contextdrift сохраняет только уже собранный prefix.
Ничего не кэшируется как разрешение записи. Return не Verification/lease/activation.
Seal manifest digest включает paths/modes/SHA, отличается от SHA manifest.jsonfile.
Canonical surface.jsonfileSHA используется как surface digest без newline.

## Границы доверия и незакрытые gates

Сейчас это cooperative opt-in code namespace и explicit preflight, НЕ mandatory handshake.
Caller может объявить неверные digests/пропустить preflight; runtime composition не wired.
Нет утверждения, что loaded/installed code совпадает с наблюдаемыми bytes. Same-process
старые/newpeer fixtures не IPC/mixed-versionrollingupgrade/realboot proof. Private UID
fixtures не rootDAC. None callers остаются legacy/unfenced. Schema2 code_bound в частной
summary не runtime_writer_fence_verified. Все7runtimeflagsfalse всегда.

Globalmandatory writer graph, protectedpathaliases, boot/root lifetime, actualKERNEL/API/
routes/processdomainverifiers, startup repair/bootstrap и independentoriginalon/code/unit
rescue ещё открыты. Нет daemon/CLI/servicehook/installer activation/registryautocreate/env
default или newunit. LiveC BLOCKED_BOOTSTRAP, E требует C+D+rescue. Полныйwave3/45s/D1-on/
scopedfault/LANUDP/IPv6/DNS/E4/performance/allTS не закрыты; wave4/DAE не начинать.
NFT10c1/backup2739/freshinstalllegacyWANIPv6 debts остаются.

## Атомарный пакет и проверка

1. Source:3новых pure/readonlyмодуля +optional Registry binding+diagnostic reasons;
   остальные116source/packaging/config/pyproject/старыеhelpers unchanged.
2. Deliver6artifacts+121source+8publicpackagingcopies. Никакого install.sh/unit execution.
3. Flash437newcases:225protocol/50CodeSeal/146surface/16integration, one start/report.
   Ordinaryfail не прерывает independent ветви; scope/source/privacy/baseline/audit STOP.
4. По actualreport принять scoped result или исправить конкретное evidencefailure.
   Sourcecandidate не устанавливать. Не повторять AJ/AI/AG/AF/AE/AD/oldbatches.

19narrowtests/RuffPASS; syntax/hash/inventory/record-size checks архитектурные, НЕ full437.
ПолныйAK/ThinkCentre/network/kernel/servicesNOT_RUN. Publication GitFForigin/freepool.
Следующий готовый пакет после actualAK: доказуемая runtime composition/real resource
observations и bootstrap dry protocol. Не ослаблять rescue/активационные gates ради объёма.
