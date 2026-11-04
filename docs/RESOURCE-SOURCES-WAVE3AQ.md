# AQ resource sources: exact implementation anchors and coverage

04.11.2026. Source commit `ee1cc2ec814f473b476b8c5cb3a01e684e60b389`. Offline qualification READY / real AQ NOT_RUN.
Host BLOCKED_SCOPE_REVIEW/HOST_NOT_RUN; all7gatesfalse/C BLOCKED_BOOTSTRAP.
Installed runtime не обновлялся. Здесь implementation anchors, не реальные измерения.

|Участок|Exact source anchor|Предел доказательства|
|---|---|---|
|Policy/types|[CapturePolicy](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observations.py#L96)|Pure positive bounded limits; not capabilities setup|
|Wire JSON|[strict_json](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observations.py#L229)|cap/nesting/container/duplicate/nonfinite/UTF8 failures|
|UNIT|[decode_unit](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L37)|fixed5properties; MainPID0 not process absence|
|PROCESS stat|[decode_stat](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L70)|comm grammar/starttime; private subset only|
|PROCESS envelope|[decode_process](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L96)|unit_scope/net/mnt strict fields|
|CONTEXT|[decode_context](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L84)|boot/net/mnt canonical fixture, not reboot proof|
|NFT_TABLE|[decode_nft](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L148)|schema1/table/chain/rule restricted subset|
|NFT semantics|[expression](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L115)|unknown refuses; counter normalization only|
|Decoder refusals|[decode](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L228)|INVALID/UNSUPPORTED separated from collection|
|Fixture provider|[FixtureBackend.capture](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L264)|exact immutable entries, no I/O|
|Host boundary|[LinuxReadonlyBackend.capture](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L278)|always BLOCKED_SCOPE_REVIEW, no I/O|
|Candidate argv|[proposed_argv](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L284)|pure literal paths/targets, no shell|
|Candidate byte/time/cleanup|[ProposedTransport.query](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L319)|unwired streaming cap/deadline/private stderr/owned child cleanup|
|Proc stream|[ProposedTransport._proc_stream](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L419)|bounded stream incl st_size0; fixed paths; candidate only|
|Namespace identity|[ProposedTransport._namespace](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L445)|targeted readlink only; no arbitrary link target follow|
|Collector context assembly|[ProposedTransport.proc_context](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L456)|boot/self net/mnt; private data; unwired|
|Process assembly|[ProposedTransport.proc_process](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L477)|PID from UNIT; zero/missing/permission/drift do not repair|
|Full proposed sequence|[proposed_profile](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_sources.py#L517)|ordered9children/24proc-context reads, cleanup STOP; unwired|
|Session constructor|[ReadonlyObservationSession.__init__](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L62)|expected/policy/provider/method pins, no filesystem/clock I/O|
|Code/reference boundary|[ReadonlyObservationSession._validate](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L118)|cooperative PID/thread/method/default/flat-data pin, not hostile sandbox|
|Clock check|[ReadonlyObservationSession._now](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L150)|finite/monotonic/pinned provider|
|Evidence issuance|[ReadonlyObservationSession.collect_once](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L162)|session ownership/terminal/budget/latest scope; no host authority|
|Bookends/PROCESS↔UNIT|[ReadonlyObservationSession.finalize](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L230)|full chosen bookends; partial/drift invalidates; not atomic snapshot|
|Scoped compare|[ReadonlyObservationSession.compare_scoped](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L267)|FIXTURE-only expected identity/freshness/context; never runtime permission|
|JSON import|[imported_evidence](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L339)|untrusted; no handles reconstructed|
|Aggregation|[aggregate_scoped](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L380)|always UNKNOWN/COVERAGE_INCOMPLETE; partial rows retained|
|Runtime facade|[ReadonlyObservationSession.runtime_verification](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observation_compare.py#L332)|Verification UNKNOWN, acceptedfalse|
|Public projection|[project_public](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_observations.py#L283)|12whitelisted fields, no raw/private values|
|Worker/empty checkpoint|[batch](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/tests/stand/wave3_observation_batch.py#L806)|claim→emptyprogress→imports→independent cases/baseline→summary|
|Worker baseline|[baseline](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/tests/stand/wave3_observation_batch.py#L256)|new method/code/default state restoration; trusted regression guard|
|Immutable public snapshot|[report](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/tests/stand/wave3_observation_batch.py#L915)|strict enums/nullable/known sources and canonical bytes, no source rerun|

LinuxReadonlyBackend не вызывает ProposedTransport. Новые stand cases проверяют proc/
profile assembly только через подменённые private functions, без host I/O. Streaming/
timeout/rc1/cleanup branches проверены локально fake process/selectors, не настоящим child.
Transport current lstat не полная executable identity policy; proc assembly/full sequence реализованы как unwired candidate;
host scope/permissions/executable/installed wire qualification пока НЕ выполнены.
При будущем host review source table расширяется exact read/metadata/kill/budget ledger,
а не путём вызова предложенного helper вручную. В этом пакете collectors фактически0.

## Семь domains

|Domain|Новое в AQ|Что остаётся открытым|
|---|---|---|
|KERNEL|NFT structural wire parser и scoped fixture comparison|Actual capture; sets/maps/tproxy/other expressions; full kernel semantics/consistency|
|PROCESSES|Unit/stat/context decoders; session PID/unit bookends|Actual proc reads; executable/cgroup/descendants/installed loaded identity|
|FILES|Ничего к AP runtime qualification|Actual installed files/config/unit identity, DAC/mount/aliases|
|ROUTES|UNSUPPORTED|Actual RPDB/routes and their complete expected contract|
|API|UNSUPPORTED|Readonly protocol/method allowlist, actual endpoints and identity|
|MODE|UNSUPPORTED|Authoritative actual mode semantics and cross-source proof|
|MARKERS|UNSUPPORTED|Actual marker provenance/consistency and expected ownership|

## Все65 прежних declared surfaces

Для каждого неизменённого surface появился только внешний AQ diagnostic candidate;
runtime wiring отсутствует. Caller/body source bytes unchanged относительно AP.
AP contract_for_surface по-прежнему7required/completenessUNKNOWN. Новые scoped fixtures
не подставляются в AP simulation path. Наличие table/PID не доказывает все эффекты вызова.
Эта таблица declared subset, не global graph. Installed calls/actual observers NOT_RUN.

|Surface|Exact original body|AQ runtime binding / AP aggregate|
|---|---|---|
|`actions.apply_network`|[src/xgw/actions.py:154](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L154)|NOT_WIRED / UNKNOWN (7required)|
|`actions.disable`|[src/xgw/actions.py:135](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L135)|NOT_WIRED / UNKNOWN (7required)|
|`actions.enable`|[src/xgw/actions.py:74](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L74)|NOT_WIRED / UNKNOWN (7required)|
|`actions.enable_checked`|[src/xgw/actions.py:120](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L120)|NOT_WIRED / UNKNOWN (7required)|
|`actions.house_after_boot`|[src/xgw/actions.py:344](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L344)|NOT_WIRED / UNKNOWN (7required)|
|`actions.pin`|[src/xgw/actions.py:188](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L188)|NOT_WIRED / UNKNOWN (7required)|
|`actions.set_core`|[src/xgw/actions.py:438](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L438)|NOT_WIRED / UNKNOWN (7required)|
|`actions.set_pool_mode`|[src/xgw/actions.py:292](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L292)|NOT_WIRED / UNKNOWN (7required)|
|`actions.set_pool_pin`|[src/xgw/actions.py:364](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L364)|NOT_WIRED / UNKNOWN (7required)|
|`actions.unpin`|[src/xgw/actions.py:250](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/actions.py#L250)|NOT_WIRED / UNKNOWN (7required)|
|`api.add_inbounds`|[src/xgw/xraycore/api.py:218](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L218)|NOT_WIRED / UNKNOWN (7required)|
|`api.add_outbounds`|[src/xgw/xraycore/api.py:208](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L208)|NOT_WIRED / UNKNOWN (7required)|
|`api.pin`|[src/xgw/xraycore/api.py:249](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L249)|NOT_WIRED / UNKNOWN (7required)|
|`api.remove_inbound`|[src/xgw/xraycore/api.py:222](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L222)|NOT_WIRED / UNKNOWN (7required)|
|`api.remove_outbound`|[src/xgw/xraycore/api.py:212](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L212)|NOT_WIRED / UNKNOWN (7required)|
|`api.replace_routing`|[src/xgw/xraycore/api.py:228](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L228)|NOT_WIRED / UNKNOWN (7required)|
|`api.unpin`|[src/xgw/xraycore/api.py:254](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/xraycore/api.py#L254)|NOT_WIRED / UNKNOWN (7required)|
|`capture._load`|[src/xgw/net/capture.py:452](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L452)|NOT_WIRED / UNKNOWN (7required)|
|`capture._save`|[src/xgw/net/capture.py:189](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L189)|NOT_WIRED / UNKNOWN (7required)|
|`capture.close`|[src/xgw/net/capture.py:791](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L791)|NOT_WIRED / UNKNOWN (7required)|
|`capture.disable`|[src/xgw/net/capture.py:773](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L773)|NOT_WIRED / UNKNOWN (7required)|
|`capture.down`|[src/xgw/net/capture.py:798](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L798)|NOT_WIRED / UNKNOWN (7required)|
|`capture.enable`|[src/xgw/net/capture.py:764](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L764)|NOT_WIRED / UNKNOWN (7required)|
|`capture.open`|[src/xgw/net/capture.py:783](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L783)|NOT_WIRED / UNKNOWN (7required)|
|`capture.restore_tun`|[src/xgw/net/capture.py:663](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L663)|NOT_WIRED / UNKNOWN (7required)|
|`capture.tailscale_direct`|[src/xgw/net/capture.py:690](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L690)|NOT_WIRED / UNKNOWN (7required)|
|`capture.tailscale_fallback`|[src/xgw/net/capture.py:725](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L725)|NOT_WIRED / UNKNOWN (7required)|
|`capture.tidy`|[src/xgw/net/capture.py:641](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L641)|NOT_WIRED / UNKNOWN (7required)|
|`capture.up`|[src/xgw/net/capture.py:758](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/net/capture.py#L758)|NOT_WIRED / UNKNOWN (7required)|
|`cores._event`|[src/xgw/cores.py:881](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L881)|NOT_WIRED / UNKNOWN (7required)|
|`cores._reject`|[src/xgw/cores.py:854](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L854)|NOT_WIRED / UNKNOWN (7required)|
|`cores._save`|[src/xgw/cores.py:874](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L874)|NOT_WIRED / UNKNOWN (7required)|
|`cores._stage`|[src/xgw/cores.py:865](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L865)|NOT_WIRED / UNKNOWN (7required)|
|`cores.rollback`|[src/xgw/cores.py:804](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L804)|NOT_WIRED / UNKNOWN (7required)|
|`cores.run`|[src/xgw/cores.py:671](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L671)|NOT_WIRED / UNKNOWN (7required)|
|`cores.update`|[src/xgw/cores.py:709](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/cores.py#L709)|NOT_WIRED / UNKNOWN (7required)|
|`engine._save_fingerprints`|[src/xgw/engine.py:192](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/engine.py#L192)|NOT_WIRED / UNKNOWN (7required)|
|`engine.apply_all`|[src/xgw/engine.py:1011](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/engine.py#L1011)|NOT_WIRED / UNKNOWN (7required)|
|`engine.collect`|[src/xgw/engine.py:214](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/engine.py#L214)|NOT_WIRED / UNKNOWN (7required)|
|`engine.persist`|[src/xgw/engine.py:900](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/engine.py#L900)|NOT_WIRED / UNKNOWN (7required)|
|`engine.save_inventory`|[src/xgw/engine.py:133](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/engine.py#L133)|NOT_WIRED / UNKNOWN (7required)|
|`panel.update`|[src/xgw/ownership_binding.py:34](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/ownership_binding.py#L34)|NOT_WIRED / UNKNOWN (7required)|
|`peers._nft_element`|[src/xgw/freepool/backend.py:163](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/backend.py#L163)|NOT_WIRED / UNKNOWN (7required)|
|`peers._save_peers`|[src/xgw/freepool/backend.py:157](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/backend.py#L157)|NOT_WIRED / UNKNOWN (7required)|
|`peers.prepare`|[src/xgw/freepool/backend.py:177](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/backend.py#L177)|NOT_WIRED / UNKNOWN (7required)|
|`peers.reconcile`|[src/xgw/freepool/backend.py:308](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/backend.py#L308)|NOT_WIRED / UNKNOWN (7required)|
|`peers.stop`|[src/xgw/freepool/backend.py:287](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/backend.py#L287)|NOT_WIRED / UNKNOWN (7required)|
|`pool._check_proxy`|[src/xgw/freepool/pool.py:417](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L417)|NOT_WIRED / UNKNOWN (7required)|
|`pool._note_handshake`|[src/xgw/freepool/pool.py:333](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L333)|NOT_WIRED / UNKNOWN (7required)|
|`pool._prune_candidates`|[src/xgw/freepool/pool.py:241](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L241)|NOT_WIRED / UNKNOWN (7required)|
|`pool._prune_retired`|[src/xgw/freepool/pool.py:109](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L109)|NOT_WIRED / UNKNOWN (7required)|
|`pool._record`|[src/xgw/freepool/pool.py:438](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L438)|NOT_WIRED / UNKNOWN (7required)|
|`pool.check_some`|[src/xgw/freepool/pool.py:345](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L345)|NOT_WIRED / UNKNOWN (7required)|
|`pool.refresh_backend`|[src/xgw/freepool/pool.py:305](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L305)|NOT_WIRED / UNKNOWN (7required)|
|`pool.refresh_due`|[src/xgw/freepool/pool.py:209](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/pool.py#L209)|NOT_WIRED / UNKNOWN (7required)|
|`pool_store._ensure`|[src/xgw/freepool/store.py:78](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/store.py#L78)|NOT_WIRED / UNKNOWN (7required)|
|`pool_store.commit`|[src/xgw/freepool/store.py:89](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/store.py#L89)|NOT_WIRED / UNKNOWN (7required)|
|`pool_store.prune`|[src/xgw/freepool/store.py:127](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/store.py#L127)|NOT_WIRED / UNKNOWN (7required)|
|`pool_store.retire_openvpn`|[src/xgw/freepool/store.py:138](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/store.py#L138)|NOT_WIRED / UNKNOWN (7required)|
|`pool_store.save_candidates`|[src/xgw/freepool/store.py:166](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/freepool/store.py#L166)|NOT_WIRED / UNKNOWN (7required)|
|`singbox.apply`|[src/xgw/apply/singbox.py:116](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/apply/singbox.py#L116)|NOT_WIRED / UNKNOWN (7required)|
|`singbox.restart`|[src/xgw/apply/singbox.py:240](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/apply/singbox.py#L240)|NOT_WIRED / UNKNOWN (7required)|
|`singbox.rollback`|[src/xgw/apply/singbox.py:250](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/apply/singbox.py#L250)|NOT_WIRED / UNKNOWN (7required)|
|`xray.apply`|[src/xgw/apply/applier.py:101](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/apply/applier.py#L101)|NOT_WIRED / UNKNOWN (7required)|
|`xray.rollback`|[src/xgw/apply/applier.py:113](https://github.com/1521572-lang/xgw/blob/ee1cc2ec814f473b476b8c5cb3a01e684e60b389/src/xgw/apply/applier.py#L113)|NOT_WIRED / UNKNOWN (7required)|

Реальные source completeness/global aliases/boot/repair/rescue/C+D до E/LAN/performance
остаются открыты. Host bookends не LAN proof и не continuous monitoring. DAE/wave4 не этап AQ.
