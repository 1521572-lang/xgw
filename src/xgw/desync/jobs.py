"""Bounded policy trials through the existing controller, with durable CAS rollback."""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from pathlib import Path

from .. import config, managed
from ..paths import LockTimeout, atomic_write_json, file_lock
from . import schema

ACTIVE = ("queued", "running", "restoring")
MAX_SECONDS = 3600
TRIAL_SECONDS = 95
MAX_AGE = 6 * 3600
CANDIDATES = ("multisplit", "multidisorder", "fake_md5_split", "fake_seq",
              "fake_seq_split", "fake_md5", "hostfakesplit_md5",
              "fake_static_md5", "fake_clone_md5")
WAIT_STAGES = ("status_stale", "policy_pending", "probe_inbound", "nfqueue",
               "worker_handoff_pending", "matched_other", "no_sample")


class Conflict(ValueError):
    pass


class Cancelled(ValueError):
    pass


class AdmissionBlocked(ValueError):
    pass


class TrialTimeout(TimeoutError):
    def __init__(self, stage):
        super().__init__("trial_timeout")
        self.stage = stage


class Jobs:
    def __init__(self, directory: Path, config_path: Path, observe, wake, *, budget_reader=None):
        self.directory = directory
        self.path = directory / "job.json"
        self.cancel_path = directory / "cancel"
        self.config_path = config_path
        self.observe, self.wake = observe, wake
        self.budget_reader = budget_reader
        self.thread = None
        self.stopping = threading.Event()
        self.mutex = threading.Lock()

    def _read(self):
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        if len(raw) > 65536:
            raise ValueError("job_size")
        row = json.loads(raw)
        if (not isinstance(row, dict) or row.get("version") != 1
                or not isinstance(row.get("id"), str) or len(row["id"]) != 32
                or row.get("state") not in (*ACTIVE, "complete", "cancelled", "interrupted",
                                             "conflict", "failed", "restore_failed")
                or not isinstance(row.get("original"), dict)
                or not isinstance(row.get("expected"), str)
                or not isinstance(row.get("candidates"), list)
                or any(p not in CANDIDATES for p in row["candidates"])
                or type(row.get("rounds")) is not int or not 1 <= row["rounds"] <= 2
                or type(row.get("budget_seconds")) is not int
                or not 120 <= row["budget_seconds"] <= MAX_SECONDS
                or not isinstance(row.get("results"), list) or len(row["results"]) > 18
                or row.get("restore") not in ("pending", "pass", "unconfirmed")):
            raise ValueError("job_schema")
        schema.validate_policy(row["original"])
        return row

    def _write(self, row):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_json(self.path, row, mode=0o600)

    def public(self):
        try:
            row = self._read()
        except (OSError, ValueError):
            return {"state": "unavailable"}
        if row is None:
            return {"state": "idle"}
        return {key: row[key] for key in (
            "id", "state", "started", "finished", "candidates", "rounds", "results",
            "restore", "error", "budget_seconds",
        ) if key in row}

    def _policy(self):
        cfg, _warnings = config.load(self.config_path)
        return cfg, cfg.desync or schema.migrate(vars(cfg.zapret2))

    def _replace(self, expected, policy):
        path = managed.path_for(self.config_path)
        with managed.file_lock(managed.lock_path(path), timeout=3, mode=0o600):
            _cfg, current = self._policy()
            if schema.fingerprint(current) != expected:
                raise Conflict("policy_changed")
            raw = json.loads(path.read_text()) if path.exists() else {}
            raw["desync"], raw["zapret2"] = policy, {}
            managed.save(path, raw)
        self.wake()
        return schema.fingerprint(policy)

    def _transition(self, row, patch):
        from ..watch.zapret2_management import admission, candidate

        cfg, current = self._policy()
        if schema.fingerprint(current) != row["expected"]:
            raise Conflict("policy_changed")
        policy, proposed = candidate(cfg, patch)
        problem = admission(proposed, self.budget_reader)
        if problem:
            raise AdmissionBlocked(problem)
        row["pending"] = schema.fingerprint(policy)
        self._write(row)
        row["expected"] = self._replace(row["expected"], policy)
        self._write(row)

    def _wait(self, row, states, deadline, *, restoring=False):
        stage = "no_sample"
        while time.monotonic() < deadline:
            if not restoring and (self.stopping.is_set() or self.cancel_path.exists()):
                raise Cancelled("cancelled")
            _cfg, policy = self._policy()
            if schema.fingerprint(policy) != row["expected"]:
                raise Conflict("policy_changed")
            view = self.observe()
            if not view.get("fresh"):
                stage = "status_stale"
            elif not view.get("policy_matched") or view.get("config_key") != row["expected"]:
                stage = "policy_pending"
            else:
                if view.get("state") in states:
                    return view
                reason = view.get("reason")
                stage = reason if reason in ("probe_inbound", "nfqueue",
                                             "worker_handoff_pending") else "matched_other"
            self.stopping.wait(0.5) if not restoring else time.sleep(0.5)
        raise TrialTimeout(stage)

    def _restore(self, row):
        row["state"] = "restoring"
        self._write(row)
        _cfg, current = self._policy()
        key = schema.fingerprint(current)
        if key not in (row["expected"], row.get("pending")):
            raise Conflict("restore_conflict")
        row["pending"] = schema.fingerprint(row["original"])
        self._write(row)
        row["expected"] = self._replace(key, row["original"])
        self._write(row)
        self._wait(row, ("off",), time.monotonic() + 90, restoring=True)
        row["restore"] = "pass"

    def _run(self, recovery=False):
        with file_lock(self.directory / "runner.lock", timeout=0, mode=0o600):
            row = self._read()
            outcome = "interrupted" if recovery else "complete"
            deadline = time.monotonic() + row["budget_seconds"]
            try:
                if not recovery:
                    row["state"] = "running"
                    self._write(row)
                    for round_id in range(row["rounds"]):
                        sequence = row["candidates"][::1 if round_id % 2 == 0 else -1]
                        for profile in sequence:
                            if self.stopping.is_set() or self.cancel_path.exists():
                                raise Cancelled("cancelled")
                            if time.monotonic() + TRIAL_SECONDS > deadline:
                                raise TimeoutError("time_budget")
                            started = time.monotonic()
                            self._transition(row, {"mode": "selective", "strategy": profile})
                            try:
                                view = self._wait(
                                    row, ("active", "fallback", "blocked", "error"),
                                    min(deadline, time.monotonic() + TRIAL_SECONDS),
                                )
                            except TimeoutError as exc:
                                # A candidate timeout is a measurement, not a reason to
                                # abandon untried candidates. Off must still be confirmed.
                                view = {"state": "timeout", "reason": "trial_timeout",
                                        "wait_stage": getattr(exc, "stage", "no_sample")}
                            evidence = view.get("evidence", {})
                            row["results"].append({
                                "round": round_id + 1, "candidate": profile,
                                "state": view["state"], "reason": view["reason"],
                                "transport": evidence.get("transport", "unknown"),
                                "probes": {target: {key: value for key, value in probe.items()
                                                    if key in ("ok", "phase", "kind", "http",
                                                               "elapsed_ms", "bytes",
                                                               "started_at", "connect_http",
                                                               "first_tls_timeout_ms")}
                                           for target, probe in
                                           evidence.get("transport_probes", {}).items()
                                           if target in ("page", "cdn")},
                                "elapsed_ms": round((time.monotonic() - started) * 1000),
                                "at": time.time(),
                            })
                            if view.get("wait_stage") in WAIT_STAGES:
                                row["results"][-1]["wait_stage"] = view["wait_stage"]
                            self._write(row)
                            self._transition(row, {"mode": "off"})
                            self._wait(row, ("off",), min(deadline, time.monotonic() + 90))
            except Cancelled:
                outcome = "cancelled"
            except Conflict:
                outcome = "conflict"
                row["error"] = "policy_changed"
            except AdmissionBlocked as exc:
                outcome = "failed"
                row["error"] = str(exc)
            except (OSError, ValueError, TimeoutError, LockTimeout, config.ConfigError):
                outcome = "failed"
                row["error"] = "trial_failed"
            finally:
                try:
                    self._restore(row)
                except (OSError, ValueError, TimeoutError, LockTimeout, config.ConfigError):
                    row["restore"] = "unconfirmed"
                    row["error"] = "restore_unconfirmed"
                    outcome = "restore_failed"
                row.update(state=outcome, finished=time.time())
                self._write(row)

    def _launch(self, recovery=False):
        def run():
            with contextlib.suppress(OSError, ValueError, LockTimeout, config.ConfigError):
                self._run(recovery)

        self.thread = threading.Thread(target=run, name="xgw-desync-job", daemon=True)
        self.thread.start()

    def recover(self):
        with self.mutex:
            try:
                row = self._read()
            except (OSError, ValueError):
                return  # Corrupt job metadata must not prevent the gateway from starting.
            if row and row["state"] in ACTIVE:
                self._launch(recovery=True)

    def command(self, action, body):
        from ..watch.zapret2_management import reply

        if not isinstance(body, dict):
            return reply(False, "invalid", "Ожидается объект параметров.")
        try:
            return self._command(action, body)
        except (OSError, ValueError, LockTimeout, config.ConfigError, managed.ManagedError):
            return reply(False, "unavailable",
                         "Не удалось изменить задание. Перечитайте состояние.")

    def _command(self, action, body):
        from ..watch.zapret2_management import admission, candidate, reply

        with self.mutex:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            with file_lock(self.directory / "command.lock", timeout=1, mode=0o600):
                row = self._read()
                if action == "cancel":
                    if (set(body) != {"id"} or not row or body["id"] != row["id"]
                            or row["state"] not in ACTIVE):
                        return reply(False, "conflict", "Задание уже изменилось.")
                    atomic_write_json(self.cancel_path, {"id": row["id"]}, mode=0o600)
                    return reply(True, "cancelling",
                                 "Отмена запрошена. Ожидается возврат настроек.")
                cfg, policy = self._policy()
                key = schema.fingerprint(policy)
                if body.get("expected") != key:
                    return reply(False, "conflict", "Перечитайте текущие настройки.")
                if row and row["state"] in ACTIVE:
                    return reply(False, "busy", "Дождитесь возврата текущего задания.")
                if cfg.zapret2.mode != "off" or cfg.zapret2.engine != "off":
                    return reply(False, "blocked", "Выключите оба режима zapret2 перед заданием.")
                if action in ("pin", "reset"):
                    allowed = {"expected", "id"} | ({"candidate"} if action == "pin" else set())
                    if (set(body) != allowed or not row or row["id"] != body["id"]
                            or row["restore"] != "pass"
                            or not 0 <= time.time() - row["finished"] <= MAX_AGE):
                        return reply(False, "invalid", "Нет свежего завершённого задания.")
                    flat, original = schema.flatten(policy), schema.flatten(row["original"])
                    if any(flat[field] != original[field] for field in (
                        "probe_urls", "domains", "youtube_transport_probe", "queue_num",
                        "probe_port", "binary", "lua_dir",
                    )):
                        return reply(False, "conflict",
                                     "Изменился контекст проверки. Запустите её заново.")
                    profile = schema.flatten(row["original"])["strategy"]
                    if action == "pin":
                        profile = body["candidate"]
                        hits = [r for r in row["results"] if r["candidate"] == profile]
                        if (len(hits) != row["rounds"] or row["rounds"] < 2
                                or any(r["transport"] != "https_reachable" for r in hits)):
                            return reply(False, "blocked", "Нужны два успешных круга HTTPS.")
                    selected, _cfg = candidate(cfg, {"strategy": profile})
                    self._replace(key, selected)
                    return reply(True, "saved", "Профиль сохранён. Режим остаётся выключенным.")
                if (action != "start" or set(body) != {"expected", "candidates", "rounds",
                                                      "budget_seconds"}):
                    return reply(False, "invalid", "Недопустимые параметры задания.")
                profiles = body["candidates"]
                if (not isinstance(profiles, list) or not 1 <= len(profiles) <= len(CANDIDATES)
                        or any(not isinstance(p, str) or p not in CANDIDATES
                               for p in profiles)
                        or len(set(profiles)) != len(profiles)
                        or type(body["rounds"]) is not int or not 1 <= body["rounds"] <= 2
                        or type(body["budget_seconds"]) is not int
                        or not 120 <= body["budget_seconds"] <= MAX_SECONDS):
                    return reply(False, "invalid",
                                 "Ожидаются до девяти профилей, 1–2 круга и 120–3600 с.")
                view = self.observe()
                if (not cfg.zapret2.youtube_transport_probe or not view.get("fresh")
                        or not view.get("policy_matched") or view.get("config_key") != key
                        or view.get("blockers", {}).get("selective", ["unknown"])):
                    return reply(False, "blocked", "Проверьте готовность Selective и бюджет.")
                _policy, proposed = candidate(cfg, {"mode": "selective",
                                                    "strategy": profiles[0]})
                problem = admission(proposed, self.budget_reader)
                if problem:
                    return reply(False, problem, "Для задания не хватает бюджета проб "
                                 "и резерва VPN либо учёт бюджета недоступен.")
                row = {
                    "version": 1, "id": uuid.uuid4().hex, "state": "queued",
                    "started": time.time(), "original": policy, "expected": key,
                    "candidates": profiles, "rounds": body["rounds"],
                    "budget_seconds": body["budget_seconds"], "results": [], "restore": "pending",
                }
                self.cancel_path.unlink(missing_ok=True)
                self._write(row)
                self._launch()
                return reply(True, "queued", "Проверка поставлена в очередь.", id=row["id"])

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=10)
