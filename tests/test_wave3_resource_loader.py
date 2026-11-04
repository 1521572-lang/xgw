import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["fixed", "startup_failure"])
def test_real_frozen_loader_without_cases(tmp_path, mode):
    repo = Path(__file__).parents[1]
    stand = repo / "tests/stand"
    notes = tmp_path / "notes"
    notes.mkdir(mode=0o700)
    files = {
        "ak.py": "wave3_code_handshake.py",
        "support.py": "wave3_source_hooks.py",
        "manifest.json": "wave3_resources_manifest.json",
        "units.json": "wave3_units_manifest.json",
        "surface.json": "wave3_surface_catalog.json",
        "legacy.py": "wave3_schema1_reference.py",
    }
    for name, src in files.items():
        shutil.copyfile(stand / src, notes / name)
        (notes / name).chmod(0o600)
    for manifest, folder in (("manifest.json", "source"), ("units.json", "units")):
        for name, digest in json.loads((notes / manifest).read_bytes()).items():
            target = notes / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, target)
            target.chmod(0o600)
            assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    for parent, _, _ in os.walk(notes):
        Path(parent).chmod(0o700)
    helper = stand / "wave3_resource_batch.py"
    if mode == "old":
        helper = notes / "old.py"
        raw = (stand / "wave3_resource_batch.py").read_text()
        raw = raw.replace(
            '    M["ownership_binding"] = importlib.import_module("frozen_ad.ownership_binding")\n',
            "",
        )
        helper.write_text(raw)
        helper.chmod(0o600)
    script = """
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('loader_probe',sys.argv[1])
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.NOTES=Path(sys.argv[2]);count=h.bootstrap()
mode=sys.argv[3]
if mode=='startup_failure':
    def stop():raise ValueError('injected before source')
    h.source=stop
    try:h.batch()
    except ValueError:pass
    expected={'final':False,'completed':0,'cases':[]}
    assert json.loads((h.NOTES/'progress.json').read_bytes())==expected
    assert not (h.NOTES/'cases').exists() and not (h.NOTES/'summary.json').exists()
    h.SUPPORT.create(h.NOTES/'source-current.json',{'head':'a'*40,'tree':'b'*40})
    h.report()
    assert (h.NOTES/'report-record.json').exists() and (h.NOTES/'report-data.md').exists()
    print('EMPTY_CHECKPOINT_REPORT_CONFIRMED')
else:
    try:h.source()
    except KeyError as exc:
        assert mode=='old' and exc.args==('ownership_binding',)
        print('ORIGINAL_KEYERROR_CONFIRMED')
    else:
        assert mode=='fixed' and count==124 and len(h.M['ownership_resource_catalog'].ROWS)==65
        assert h.SUPPORT.AUDIT['ready'] and h.SUPPORT.AUDIT['violations']==0
        assert not (h.NOTES/'cases').exists()
        print('REAL_SOURCE_LOADER_CONFIRMED')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(helper), str(notes), mode],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    marker = {
        "old": "ORIGINAL_KEYERROR_CONFIRMED",
        "fixed": "REAL_SOURCE_LOADER_CONFIRMED",
        "startup_failure": "EMPTY_CHECKPOINT_REPORT_CONFIRMED",
    }[mode]
    assert marker in result.stdout
