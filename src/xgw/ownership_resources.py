"""Pure, dormant resource contracts. No collector, runtime wiring or authorization.

MATCH can describe only supplied simulation data. Actual provenance adapters do not
exist here. Decisions deliberately are not ownership_adapters.Verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ownership_adapters import CHECKS, Verification

DOMAINS = tuple(sorted(CHECKS))
MAX_REQUIREMENTS = 128


class ResourceRefused(ValueError):
    pass


def require(value):
    if not value:
        raise ResourceRefused("RESOURCE_ARGUMENT")


def identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value)


@dataclass(frozen=True)
class Binding:
    code: str
    boot: str
    context: str

    def __post_init__(self):
        require(
            type(self) is Binding
            and all(identifier(v) for v in (self.code, self.boot, self.context))
        )


@dataclass(frozen=True)
class ResourceRequirement:
    domain: str
    resource_id: str
    expected_state_id: str
    required: bool = True
    expected_absent: bool = False

    def __post_init__(self):
        require(
            type(self) is ResourceRequirement
            and type(self.domain) is str
            and self.domain in CHECKS
            and identifier(self.resource_id)
            and identifier(self.expected_state_id)
            and type(self.required) is type(self.expected_absent) is bool
        )


@dataclass(frozen=True)
class ResourceContract:
    binding: Binding
    requirements: tuple
    completeness: str = "UNKNOWN"

    def __post_init__(self):
        require(type(self) is ResourceContract and type(self.binding) is Binding)
        require(
            type(self.requirements) is tuple and 1 <= len(self.requirements) <= MAX_REQUIREMENTS
        )
        require(
            type(self.completeness) is str and self.completeness in ("UNKNOWN", "DECLARED_COMPLETE")
        )
        require(all(type(r) is ResourceRequirement for r in self.requirements))
        require(
            len({(r.domain, r.resource_id) for r in self.requirements}) == len(self.requirements)
        )
        require(any(r.required for r in self.requirements))


@dataclass(frozen=True)
class ResourceState:
    resource_id: str
    state_id: str
    absent: bool = False

    def __post_init__(self):
        require(
            type(self) is ResourceState
            and identifier(self.resource_id)
            and identifier(self.state_id)
            and type(self.absent) is bool
        )


@dataclass(frozen=True)
class Observation:
    domain: str
    binding: Binding
    states: tuple = ()
    schema_version: int = 1
    collection_status: str = "NOT_COLLECTED"
    simulation_only: bool = True
    origin: str = "UNBOUND"
    scope_complete: bool = False

    def __post_init__(self):
        require(type(self) is Observation and type(self.domain) is str and self.domain in CHECKS)
        require(
            type(self.binding) is Binding
            and type(self.schema_version) is int
            and 0 <= self.schema_version <= 65535
        )
        require(type(self.states) is tuple and len(self.states) <= MAX_REQUIREMENTS)
        require(all(type(s) is ResourceState for s in self.states))
        require(
            type(self.collection_status) is str
            and self.collection_status
            in ("COMPLETE", "NOT_COLLECTED", "TRUNCATED", "TIMEOUT", "ERROR")
        )
        require(type(self.simulation_only) is type(self.scope_complete) is bool)
        require(type(self.origin) is str and self.origin in ("SIMULATION", "UNBOUND", "CALLER"))
        # Contradictory/duplicate states are retained as input, refused by comparison.


@dataclass(frozen=True)
class ContractDecision:
    domain: str
    status: str
    checked: int = 0
    required: int = 0
    optional_unmatched: int = 0
    reason: str = "NOT_OBSERVED"
    simulation_only: bool = True
    runtime_completion_authorized: bool = field(default=False, init=False)


def compare_observation(contract, observation, *, domain=None):
    require(type(contract) is ResourceContract)
    if domain is None and type(observation) is Observation:
        domain = observation.domain
    require(type(domain) is str and domain in CHECKS)
    rows = tuple(r for r in contract.requirements if r.domain == domain)
    required = sum(r.required for r in rows)

    def decision(status, reason, checked=0, optional=0):
        return ContractDecision(domain, status, checked, required, optional, reason)

    if not rows:
        return decision("UNSUPPORTED", "DOMAIN_NOT_REQUIRED")
    if type(observation) is not Observation:
        return decision("UNKNOWN", "OBSERVATION_MISSING_OR_TYPE")
    if observation.domain != domain or observation.binding != contract.binding:
        return decision("UNKNOWN", "IDENTITY_MISMATCH")
    if observation.schema_version != 1:
        return decision("UNSUPPORTED", "SCHEMA_UNSUPPORTED")
    if observation.collection_status != "COMPLETE":
        return decision("UNKNOWN", "COLLECTION_INCOMPLETE")
    if not observation.simulation_only or observation.origin != "SIMULATION":
        return decision("UNSUPPORTED", "ACTUAL_PROVENANCE_NOT_IMPLEMENTED")
    ids = [s.resource_id for s in observation.states]
    if len(ids) != len(set(ids)):
        return decision("UNKNOWN", "CONTRADICTORY_STATES")
    states = {s.resource_id: s for s in observation.states}
    checked = optional = 0
    failures = []
    for row in rows:
        state = states.get(row.resource_id)
        if state is None:
            status, reason = "UNKNOWN", "RESOURCE_NOT_OBSERVED"
        elif state.absent and not observation.scope_complete:
            status, reason = "UNKNOWN", "ABSENCE_UNPROVEN"
        elif state.absent != row.expected_absent or state.state_id != row.expected_state_id:
            status, reason = "MISMATCH", "STATE_MISMATCH"
        else:
            status, reason = "MATCH", "SIMULATION_MATCH"
        # checked is a verified contiguous prefix, never total processed.
        if not failures and status == "MATCH":
            checked += 1
        if status != "MATCH":
            failures.append((row.required, status, reason))
            if not row.required:
                optional += 1
    for target in ("MISMATCH", "UNKNOWN"):
        found = next((reason for req, status, reason in failures if req and status == target), None)
        if found:
            return decision(target, found, checked, optional)
    return decision("MATCH", "SIMULATION_MATCH", checked, optional)


@dataclass(frozen=True)
class AggregateDecision:
    status: str
    decisions: tuple
    missing_required: int
    simulation_only: bool = field(default=True, init=False)
    runtime_completion_authorized: bool = field(default=False, init=False)


def aggregate(contract, observations):
    require(type(contract) is ResourceContract)
    require(type(observations) is tuple and len(observations) <= len(CHECKS) * 2)
    domains = tuple(d for d in DOMAINS if any(r.domain == d for r in contract.requirements))
    results = []
    for domain in domains:
        matches = tuple(o for o in observations if type(o) is Observation and o.domain == domain)
        if len(matches) > 1 or any(type(o) is not Observation for o in observations):
            n = sum(r.required for r in contract.requirements if r.domain == domain)
            result = ContractDecision(
                domain, "UNKNOWN", required=n, reason="OBSERVATIONS_AMBIGUOUS"
            )
        else:
            result = compare_observation(contract, matches[0] if matches else None, domain=domain)
        results.append(result)
    bad = tuple(r for r in results if r.required and r.status != "MATCH")
    status = "MATCH"
    for candidate in ("MISMATCH", "UNSUPPORTED", "UNKNOWN"):
        if any(r.status == candidate for r in bad):
            status = candidate
            break
    if status == "MATCH" and contract.completeness != "DECLARED_COMPLETE":
        status = "UNKNOWN"
    return AggregateDecision(status, tuple(results), sum(r.required for r in bad))


@dataclass(frozen=True)
class BootstrapFact:
    name: str
    status: str
    binding: Binding
    origin: str = "UNBOUND"

    def __post_init__(self):
        require(type(self) is BootstrapFact and type(self.name) is str and self.name in FACT_NAMES)
        require(type(self.status) is str and self.status in ("CONFIRMED", "REFUSED", "UNKNOWN"))
        require(
            type(self.binding) is Binding
            and type(self.origin) is str
            and self.origin in ("SIMULATION", "CALLER", "UNBOUND")
        )


FACT_NAMES = ("IDENTITY", "ACTOR_GRAPH", "DOMAINS", "ORIGINAL_ON", "RESCUE")


@dataclass(frozen=True)
class BootstrapInventory:
    binding: Binding
    facts: tuple = ()
    writer_total: int | None = None
    unknown_writers: int | None = None
    stage: str = "UNKNOWN"
    acknowledgement: str = "UNKNOWN"
    simulation_only: bool = True

    def __post_init__(self):
        require(type(self) is BootstrapInventory and type(self.binding) is Binding)
        require(
            type(self.facts) is tuple
            and len(self.facts) <= len(FACT_NAMES)
            and all(type(f) is BootstrapFact for f in self.facts)
        )
        require(len({f.name for f in self.facts}) == len(self.facts))
        require(
            all(
                v is None or (type(v) is int and 0 <= v <= 32)
                for v in (self.writer_total, self.unknown_writers)
            )
        )
        require(
            self.writer_total is None
            or self.unknown_writers is None
            or self.unknown_writers <= self.writer_total
        )
        require(
            type(self.stage) is str
            and self.stage in ("NONE", "VALID_UNPROVEN", "REFUSED", "UNKNOWN")
        )
        require(
            type(self.acknowledgement) is str
            and self.acknowledgement in ("CONFIRMED", "UNCERTAIN", "UNKNOWN")
        )
        require(type(self.simulation_only) is bool)


@dataclass(frozen=True)
class BootstrapPlan:
    blockers: tuple
    actions: tuple
    simulation_only: bool
    live_activation_authorized: bool = field(default=False, init=False)
    repair_authorized: bool = field(default=False, init=False)


BLOCKER_ORDER = (
    "IDENTITY_UNKNOWN",
    "ACTOR_GRAPH_INCOMPLETE",
    "DOMAIN_UNSUPPORTED",
    "WRITERS_UNOBSERVED",
    "WRITERS_LIVE",
    "WRITERS_UNKNOWN",
    "STAGE_UNPROVEN",
    "ACKNOWLEDGEMENT_UNPROVEN",
    "ORIGINAL_ON_UNPROVEN",
    "RESCUE_NOT_QUALIFIED",
    "ACTUAL_PROVENANCE_NOT_IMPLEMENTED",
)


def ordered_plan(blockers, simulation_only):
    ordered = tuple(reason for reason in BLOCKER_ORDER if reason in blockers)
    actions = tuple("REVIEW_" + name for name in ordered) or ("READY_FOR_REVIEW",)
    return BootstrapPlan(ordered, actions, simulation_only)


def plan_bootstrap(inventory, contract):
    require(type(inventory) is BootstrapInventory and type(contract) is ResourceContract)
    blockers = []
    facts = {f.name: f for f in inventory.facts}
    reasons = (
        ("IDENTITY", "IDENTITY_UNKNOWN"),
        ("ACTOR_GRAPH", "ACTOR_GRAPH_INCOMPLETE"),
        ("DOMAINS", "DOMAIN_UNSUPPORTED"),
        ("ORIGINAL_ON", "ORIGINAL_ON_UNPROVEN"),
        ("RESCUE", "RESCUE_NOT_QUALIFIED"),
    )
    for name, reason in reasons:
        f = facts.get(name)
        confirmed = (
            f is not None
            and f.status == "CONFIRMED"
            and f.binding == contract.binding
            and inventory.binding == contract.binding
            and inventory.simulation_only
            and f.origin == "SIMULATION"
        )
        if not confirmed:
            blockers.append(reason)
    if contract.completeness != "DECLARED_COMPLETE" and "ACTOR_GRAPH_INCOMPLETE" not in blockers:
        blockers.append("ACTOR_GRAPH_INCOMPLETE")
    if inventory.writer_total is None or inventory.unknown_writers is None:
        blockers.append("WRITERS_UNOBSERVED")
    if (
        inventory.writer_total is not None
        and inventory.unknown_writers is not None
        and inventory.writer_total > inventory.unknown_writers
    ):
        blockers.append("WRITERS_LIVE")
    if inventory.unknown_writers:
        blockers.append("WRITERS_UNKNOWN")
    if inventory.stage != "NONE":
        blockers.append("STAGE_UNPROVEN")
    if inventory.acknowledgement != "CONFIRMED":
        blockers.append("ACKNOWLEDGEMENT_UNPROVEN")
    if not inventory.simulation_only:
        blockers.append("ACTUAL_PROVENANCE_NOT_IMPLEMENTED")
    return ordered_plan(blockers, inventory.simulation_only)


@dataclass(frozen=True)
class ObservationSet:
    observations: tuple

    def __post_init__(self):
        require(
            type(self) is ObservationSet
            and type(self.observations) is tuple
            and len(self.observations) <= len(CHECKS) * 2
            and all(type(o) is Observation for o in self.observations)
        )


@dataclass(frozen=True)
class ResourceFacade:
    contract: ResourceContract
    source: ObservationSet
    inventory: BootstrapInventory

    def __post_init__(self):
        require(
            type(self) is ResourceFacade
            and type(self.contract) is ResourceContract
            and type(self.source) is ObservationSet
            and type(self.inventory) is BootstrapInventory
        )

    def inspect(self):
        decision = aggregate(self.contract, self.source.observations)
        plan = plan_bootstrap(self.inventory, self.contract)
        if any(d.required and d.status != "MATCH" for d in decision.decisions):
            plan = ordered_plan((*plan.blockers, "DOMAIN_UNSUPPORTED"), plan.simulation_only)
        return decision, plan

    def runtime_verification(self):
        # No conversion of supplied/simulation data to accepted runtime evidence.
        return Verification()
