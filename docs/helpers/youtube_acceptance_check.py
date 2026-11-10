#!/usr/bin/env python3
"""Читает сводку прогона, выводит только счётчики и фиксированные метки."""

import argparse
import contextlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def main():
    from xgw.config import load
    from xgw.generator.builder import applied_media, applied_nodes
    from xgw.paths import Paths
    from xgw.watch import youtube

    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=int, default=0)
    args = parser.parse_args()
    paths = Paths.from_env()
    cfg, warnings = load(paths.config_file)
    status = json.loads(paths.status_file.read_text())
    applied = json.loads(paths.xray_config_file.read_text())
    tags = applied_media(applied)
    healthy = int(status.get("state") == "HEALTHY")
    capture = int((status.get("capture") or {}).get("mode") == "on")
    mode = int(cfg.media.youtube_mode == "best")
    key = youtube.sign_key(cfg.media.youtube_sign_url)
    print(f"CHECK healthy={healthy} capture_on={capture} best={mode} "
          f"sign_enabled={int(bool(key))} route={int(bool(tags))} warnings={len(warnings)}")
    if not args.since or not key:
        return
    uri = paths.db_file.as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        row = db.execute("SELECT value FROM meta WHERE key=?", ("youtube",)).fetchone()
    records = json.loads(row[0]) if row else {}
    now = time.time()
    counts = dict.fromkeys((youtube.ACCEPT, youtube.REFUSE, youtube.UNKNOWN), 0)
    refused = set()
    for fp, record in records.items():
        sign = youtube.sign_sample(record, key, now)
        if sign is None or record["sign"]["ts"] < args.since:
            continue
        counts[sign] += 1
        if sign == youtube.REFUSE:
            refused.add(fp)
    refused_active = 0
    for info in applied_nodes(applied):
        if info.tag not in tags:
            continue
        matches = [fp for fp in records if fp.startswith(info.fingerprint)]
        if len(matches) == 1 and matches[0] in refused:
            refused_active += 1
    media = status.get("media") or {}
    print(f"SIGN accept={counts[youtube.ACCEPT]} refuse={counts[youtube.REFUSE]} "
          f"unknown={counts[youtube.UNKNOWN]} refused_active={refused_active} "
          f"all_refused={int(media.get('state') == 'waiting_for_acceptance')}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print("STOP summary_unavailable")
        sys.exit(2)
