"""ThinkCentre-only check: independent processes contend on the actual flock."""

import multiprocessing

from xgw import config, managed
from xgw.desync import schema
from xgw.watch.zapret2_management import command


def _writer(cfg, expected, value, start, connection):
    try:
        assert start.wait(timeout=10)
        result = command(cfg, "settings", {"expected": expected,
                         "settings": {"retry_seconds": value}},
                         ready=True, capture={"mode": "on"})
        connection.send(result["code"])
    finally:
        connection.close()


def test_processes_compare_revision_inside_file_lock(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("", encoding="utf-8")
    expected = schema.fingerprint(config.load(cfg)[0].desync)
    context = multiprocessing.get_context("fork")
    start = context.Event()
    readers, workers = [], []
    try:
        for value in (120, 180):
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(target=_writer, args=(cfg, expected, value, start, writer))
            process.start()
            writer.close()
            readers.append(reader)
            workers.append(process)
        start.set()
        results = []
        for reader in readers:
            assert reader.poll(15), "writer timed out"
            results.append(reader.recv())
        for process in workers:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert sorted(results) == ["conflict", "saved"]
        assert config.load(cfg)[0].zapret2.retry_seconds in (120, 180)
        assert managed.path_for(cfg).stat().st_mode & 0o777 == 0o600
    finally:
        for reader in readers:
            reader.close()
        for process in workers:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
