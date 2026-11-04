# AP API contract v1

Обновление04.11.2026: [AP211 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ap.md).
211/211/summary/byteexactprefix;C91/P20/A14/B17/T65/I4. Данныесимуляции не создают
runtimeквитанции: I3verificationfalse/receipt0/UNKNOWNwriter1. Каталог65требуетвсе7domains/
completenessUNKNOWN. HEALTHY_ON/poolOFF/linkALIVE/versionssame/bookendsсохранны.
Actualcollectors/provenanceНЕреализованы;all7gatesfalse/LiveCBLOCKED_BOOTSTRAP.
СтарыеAPcasesнеповторять. Ниже описаниедоactualAP;егоNOT_RUNустарелпослеэтойприёмки.


Modules: ownership_resources.py и ownership_resource_catalog.py. Internal typed Python
API only. JSON ingestion/Linux wire decoder/actual collector не реализованы. В runner
JSON — только schema-checked output отчёта; входы создаются typed constructors.

| Type / function | Поля / правила |
|---|---|
| Binding | code/boot/context: exactstr, 1–128 ASCIIidentifier chars; opaque namespace tokens, не trustedprovenance/проверкаactualboot |
| ResourceRequirement | domain∈CHECKS; resource_id/expected_state_id boundedtokens; required/expected_absent exactbool |
| ResourceContract | exactBinding, tuple1–128 exactrequirements, unique(domain,id), ≥1required, completeness UNKNOWN/DECLARED_COMPLETE |
| ResourceState | bounded id/state tokens, absent exactbool |
| Observation | domain, Binding, tuple≤128 states; schema_version exactint0…65535; status COMPLETE/NOT_COLLECTED/TRUNCATED/TIMEOUT/ERROR; simulation_only/scope_complete exactbool; origin SIMULATION/UNBOUND/CALLER |
| compare_observation | strictcontract + explicit domain if input missing/wrongtype; decision MATCH/MISMATCH/UNKNOWN/UNSUPPORTED |
| ContractDecision | fixeddomain/status/reason; actual checked prefix, knownrequired/optionalcount; simulation_only=true; runtime_completion_authorized=false/init=False |
| aggregate | tuple≤14 supplied observations; retains independent per-domain decisions; ambiguity→UNKNOWN; required mismatch/unsupported/unknown blocksMATCH; incompleteness blocksMATCH |
| AggregateDecision | status/tupledecisions/missing_required; simulation_only=true/runtime_completion_authorized=false |
| BootstrapFact | fixedname IDENTITY/ACTOR_GRAPH/DOMAINS/ORIGINAL_ON/RESCUE; CONFIRMED/REFUSED/UNKNOWN; binding; SIMULATION/CALLER/UNBOUND |
| BootstrapInventory | explicitbinding, tuple≤5unique facts, nullablewriter_total/unknown0…32, unknown≤total if known; stageNONE/VALID_UNPROVEN/REFUSED/UNKNOWN; ackCONFIRMED/UNCERTAIN/UNKNOWN; simulation bool |
| plan_bootstrap | pure ordered blockers/actions; no executable commands/paths, no mutation; simulation confirmedfacts can yield READY_FOR_REVIEW only |
| BootstrapPlan | blockers/actions/simulation; live_activation_authorized=false/repair_authorized=false, init=False |
| ObservationSet | explicit tuple≤14exactObservation; no callable/providerexecution |
| ResourceFacade.inspect | returns aggregate and dryplan; constructor/inspect noI/O |
| ResourceFacade.runtime_verification | always exact Verification(outcome=UNKNOWN,checks=()); never accepted |
| contract_for_surface | one of65declared IDs; explicitexpected_state dict for ALL7domains; completenessUNKNOWN; noFILES-onlyfallback |

Принципы сравнения:

- Missing/type/binding/collection/conflictingstates→UNKNOWN; unsupportedversion и
  actual/caller/unbound provenance→UNSUPPORTED. Ничего из этого не MATCH/пустойуспех.
- Only explicit SIMULATION/COMPLETE/schema1/samebinding сравнивается поtypedid/state.
  Проверка id/state не анализирует реальный kernel/API/process content.
- Explicit absence требует scope_complete, иначе UNKNOWN. Scopecomplete вsimulation
  не даёт actualabsenceproof; actualobservations всёравноUNSUPPORTED.
- Optionalfailure виден вdomain decision/count, не блокирует requiredMATCH.
- checked — непрерывный MATCH-prefix, не количество обработанных элементов.
- Нет deep JSON payload, arbitrary callbacks, eval/exec/subprocess/socket/FS/clock вAPI.
  Максимум128requirements/128states/14observations, bounded128chars, fixed loops.
  Boolнеint, float/NaN/Infinity не допустимы там, где требуетсяint/bool/string.
- Unknowncounts остаются None; известныйunknownwriter1 сохраняет blocker даже при
  неизвестномtotal. LIVE1UNKNOWN0 имеет WRITERS_LIVE.
- READY_FOR_REVIEW только completeness dry-плана, никогда permission/registryrepair.
- Типы не hostile-code sandbox: maliciousroot может менять Pythonobjects. Нет
  утверждения independent provenance по переданным caller значениям.

Встроенный каталог содержит exact publicsourceanchors/calls и консервативные domain
кандидаты по реализации; полнота каждогоsurface UNKNOWN. Эффективный контракт
требуетвсе7domains. Вне declared65: installer/uninstaller/daemon/CLI/servicehooks/
legacyNone/backgroundcallbacks/factorydependencies. Полная таблица:
[RESOURCE-TABLE-WAVE3AP.md](RESOURCE-TABLE-WAVE3AP.md).
