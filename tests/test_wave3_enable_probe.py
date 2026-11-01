"""Только новые границы диагностики enable: без служб и сетевых запросов."""
import importlib.util
from pathlib import Path

import pytest


def sampler():
    path = Path(__file__).parent / "stand/wave3_enable_probe.py"
    spec = importlib.util.spec_from_file_location("enable_sampler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("error", [TimeoutError, ConnectionResetError])
def test_failed_body_keeps_bytes_from_previous_reads(error):
    tool = sampler()
    result = {"bytes": 0}

    class Stream:
        def settimeout(self, value):
            pass

    class Response:
        reads = 0

        def read1(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"x" * 8192
            raise error()

    with pytest.raises(error):
        tool.consume(Response(), Stream(), tool.time.monotonic() + 3, result)
    assert result == {"bytes": 8192, "phase": "body"}


@pytest.mark.parametrize("failure", ["not_ready", "stale", "changed_sampler"])
def test_invalid_baseline_cannot_reach_enable(tmp_path, monkeypatch, failure):
    tool = sampler()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    tool.guard.save(tmp_path / "snapshot.json", {"boot": boot})
    tool.guard.save(tmp_path / "baseline.json", {
        "ready": failure != "not_ready",
        "monotonic": tool.time.monotonic() - (301 if failure == "stale" else 0),
        "sampler_sha256": ("bad" if failure == "changed_sampler"
                           else tool.hashlib.sha256(tool.HERE.read_bytes()).hexdigest()),
    })
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("must not enable"))
    with pytest.raises(SystemExit, match="off-базы"):
        tool.run(tmp_path)


def test_manual_sampler_run_outside_tracked_job_cannot_enable(tmp_path, monkeypatch):
    tool = sampler()
    monkeypatch.setattr(tool, "permit", lambda directory: {"target": 0})
    monkeypatch.setattr(tool, "in_job", lambda: False)
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("must not enable"))
    with pytest.raises(SystemExit, match="job-unit"):
        tool.run(tmp_path)
