"""Pure recovery contract model. No live recovery driver, services, files or network I/O.

All scenarios use synthetic observations and an injected clock. A successful simulation
does not establish autonomous recovery or authorize a fault on the working gateway.
"""

import dataclasses
import json
import math
import sys


@dataclasses.dataclass(frozen=True)
class Preconditions:
    baseline_on: bool = False
    snapshot_verified: bool = False
    same_boot: bool = False
    writer_fence_verified: bool = False
    independent_driver_verified: bool = False
    guard_preserved: bool = False
    owned_capture_table_only: bool = False
    wan_untouched: bool = False
    scope: str = "CAPTURE_TABLE_ONLY"
    fault_seconds: float = 15
    restore_seconds: float = 20
    verify_seconds: float = 5
    hard_seconds: float = 45

    def validate(self):
        for item in dataclasses.fields(self):
            if item.name.endswith("seconds"):
                value = getattr(self, item.name)
                if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                    raise ValueError("INVALID_BUDGET")
            elif item.name != "scope" and getattr(self, item.name) is not True:
                raise ValueError("PRECONDITION_UNVERIFIED")
        if self.scope != "CAPTURE_TABLE_ONLY":
            raise ValueError("UNSUPPORTED_SCOPE")
        if (
            self.hard_seconds > 45
            or self.fault_seconds + self.restore_seconds + self.verify_seconds > self.hard_seconds
        ):
            raise ValueError("UNBOUNDED_RECOVERY")


@dataclasses.dataclass
class Model:
    plan: Preconditions
    state: str = "ARMED"
    now: float = 0
    fault_started: bool = False
    restore_deadline: float | None = None
    verify_deadline: float | None = None

    def __post_init__(self):
        self.plan.validate()
        # This is a virtual clock origin, not a realtime timestamp or a running timer.
        if self.now != 0 or self.state != "ARMED" or self.fault_started:
            raise ValueError("INVALID_INITIAL_STATE")

    def tick(self, now):
        if type(now) not in (int, float) or not math.isfinite(now) or now < self.now:
            raise ValueError("INVALID_MONOTONIC_CLOCK")
        self.now = now
        if self.state in ("RESTORED_ON", "FAILED", "REFUSED", "EXPIRED_UNUSED"):
            return
        if now >= self.plan.hard_seconds:
            self.state = "FAILED" if self.fault_started else "EXPIRED_UNUSED"
        elif self.state == "ARMED" and now >= self.plan.fault_seconds:
            self.state = "EXPIRED_UNUSED"
        elif self.state == "FAULT_RUNNING" and now >= self.plan.fault_seconds:
            self.state = "RECOVERY_DUE"
        elif (self.state == "RESTORING" and now >= self.restore_deadline) or (
            self.state == "VERIFYING" and now >= self.verify_deadline
        ):
            self.state = "FAILED"

    def begin_fault(self, now, *, same_generation=False, driver_armed=False):
        self.tick(now)
        if self.state != "ARMED":
            raise ValueError("FAULT_NOT_ARMED")
        if same_generation is not True or driver_armed is not True:
            self.state = "REFUSED"
            return
        self.fault_started, self.state = True, "FAULT_RUNNING"

    def job_finished(self, now):
        self.tick(now)
        if self.state == "FAULT_RUNNING":
            self.state = "RECOVERY_DUE"

    def begin_restore(self, now, *, snapshot_still_verified=False, same_boot=False):
        self.tick(now)
        if self.state != "RECOVERY_DUE":
            raise ValueError("RESTORE_NOT_DUE")
        if snapshot_still_verified is not True or same_boot is not True:
            self.state = "FAILED"
            return
        self.state = "RESTORING"
        self.restore_deadline = min(now + self.plan.restore_seconds, self.plan.hard_seconds)

    def restore_result(self, now, *, transaction_ok):
        self.tick(now)
        if self.state != "RESTORING":
            raise ValueError("RESTORE_NOT_RUNNING")
        if transaction_ok is not True:
            self.state = "FAILED"
            return
        self.state = "VERIFYING"
        self.verify_deadline = min(now + self.plan.verify_seconds, self.plan.hard_seconds)

    def verify_result(self, now, *, capture_on, guard_matches, routes_match, generation_matches):
        self.tick(now)
        if self.state != "VERIFYING":
            raise ValueError("VERIFY_NOT_RUNNING")
        self.state = (
            "RESTORED_ON"
            if all(v is True for v in (capture_on, guard_matches, routes_match, generation_matches))
            else "FAILED"
        )


def verified_fixture():
    # Synthetic proof flags only, never an observation of the real gateway.
    return Preconditions(
        baseline_on=True,
        snapshot_verified=True,
        same_boot=True,
        writer_fence_verified=True,
        independent_driver_verified=True,
        guard_preserved=True,
        owned_capture_table_only=True,
        wan_untouched=True,
    )


def simulate():
    results = []

    def check(name, fn):
        try:
            fn()
            results.append({"case": name, "passed": True})
        except Exception:
            # Never print arbitrary exception strings or caller-supplied values.
            results.append({"case": name, "passed": False})

    def expect_rejected(plan):
        try:
            Model(plan)
        except ValueError:
            return
        raise AssertionError

    check("REJECT_UNVERIFIED_DEFAULT", lambda: expect_rejected(Preconditions()))

    for field in (
        "baseline_on",
        "snapshot_verified",
        "same_boot",
        "writer_fence_verified",
        "independent_driver_verified",
        "guard_preserved",
        "wan_untouched",
        "owned_capture_table_only",
    ):
        check(
            "REJECT_" + field.upper(),
            lambda field=field: expect_rejected(
                dataclasses.replace(verified_fixture(), **{field: False})
            ),
        )
    check(
        "REJECT_INSTALL_SCOPE",
        lambda: expect_rejected(dataclasses.replace(verified_fixture(), scope="D1_INSTALL")),
    )
    check(
        "REJECT_OVERBUDGET",
        lambda: expect_rejected(dataclasses.replace(verified_fixture(), hard_seconds=60)),
    )
    check(
        "REJECT_NAN_BUDGET",
        lambda: expect_rejected(
            dataclasses.replace(verified_fixture(), fault_seconds=float("nan"))
        ),
    )
    check(
        "REJECT_STRING_BOOL",
        lambda: expect_rejected(dataclasses.replace(verified_fixture(), baseline_on="true")),
    )

    def unused():
        model = Model(verified_fixture())
        model.tick(15)
        assert model.state == "EXPIRED_UNUSED" and not model.fault_started
        try:
            model.begin_fault(16)
        except ValueError:
            return
        raise AssertionError

    check("EXPIRED_TIMER_NEVER_STARTS_LATE_FAULT", unused)

    def stale():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=False, driver_armed=True)
        assert model.state == "REFUSED" and not model.fault_started

    check("STALE_GENERATION_REFUSES_JOB", stale)

    def driver_absent():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=False)
        assert model.state == "REFUSED" and not model.fault_started

    check("UNARMED_DRIVER_REFUSES_JOB", driver_absent)

    def complete(early=False):
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        if early:
            model.job_finished(2)
            now = 2
        else:
            # Advancing the injected clock models a controller disappearing; no pulse exists.
            model.tick(15)
            now = 15
        assert model.state == "RECOVERY_DUE"
        model.begin_restore(now, snapshot_still_verified=True, same_boot=True)
        model.restore_result(now + 1, transaction_ok=True)
        model.verify_result(
            now + 2, capture_on=True, guard_matches=True, routes_match=True, generation_matches=True
        )
        assert model.state == "RESTORED_ON"

    check("VIRTUAL_CONTROLLER_LOSS_REACHES_ON", complete)
    check("EARLY_JOB_END_STILL_RESTORES_ON", lambda: complete(True))

    def bad_snapshot():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.tick(15)
        model.begin_restore(15, snapshot_still_verified=False, same_boot=True)
        assert model.state == "FAILED"

    check("CORRUPT_SNAPSHOT_NEVER_REPLAYED", bad_snapshot)

    def rejected_transaction():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.tick(15)
        model.begin_restore(15, snapshot_still_verified=True, same_boot=True)
        model.restore_result(16, transaction_ok=False)
        assert model.state == "FAILED"

    check("TRANSACTION_FAILURE_NOT_RESTORED_ON", rejected_transaction)

    def false_verdict():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.job_finished(2)
        model.begin_restore(2, snapshot_still_verified=True, same_boot=True)
        model.restore_result(3, transaction_ok=True)
        model.verify_result(
            4, capture_on=True, guard_matches=True, routes_match=False, generation_matches=True
        )
        assert model.state == "FAILED"

    check("VERIFY_FAILURE_NOT_RESTORED_ON", false_verdict)

    def stuck_restore():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.tick(15)
        model.begin_restore(15, snapshot_still_verified=True, same_boot=True)
        model.tick(35)
        assert model.state == "FAILED"

    check("RESTORE_TIMEOUT_NOT_SUCCESS", stuck_restore)

    def stuck_verify():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.tick(15)
        model.begin_restore(15, snapshot_still_verified=True, same_boot=True)
        model.restore_result(16, transaction_ok=True)
        model.tick(21)
        assert model.state == "FAILED"

    check("VERIFY_TIMEOUT_NOT_SUCCESS", stuck_verify)

    def late_driver():
        model = Model(verified_fixture())
        model.begin_fault(1, same_generation=True, driver_armed=True)
        model.tick(45)
        assert model.state == "FAILED"

    check("HARD_DEADLINE_NOT_SUCCESS", late_driver)

    def backwards():
        model = Model(verified_fixture())
        model.tick(1)
        try:
            model.tick(0)
        except ValueError:
            return
        raise AssertionError

    check("BACKWARDS_CLOCK_REJECTED", backwards)
    passed = sum(row["passed"] for row in results)
    return {
        "marker": "ON_RECOVERY_MODEL_RECORDED"
        if passed == len(results)
        else "ON_RECOVERY_MODEL_FAILED",
        "cases": results,
        "passed": passed,
        "total": len(results),
        "scope": "SYNTHETIC_STATE_MACHINE_ONLY",
        "network_requests": 0,
        "live_operations": 0,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
    }


if __name__ == "__main__":
    if sys.argv[1:] != ["simulate"] or sys.flags.optimize != 0:
        print("STOP_MODEL_MODE")
        raise SystemExit(3)
    result = simulate()
    print(json.dumps(result))
    raise SystemExit(0 if result["marker"] == "ON_RECOVERY_MODEL_RECORDED" else 3)
