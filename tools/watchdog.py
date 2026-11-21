#!/usr/bin/env python3
"""Exit 2 when 허브상태.txt is more than 3 minutes old, so the start script can restart the hub.

A missing file is not stale: the hub may still be starting. A file with no heartbeat line is stale.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

STALE_SECONDS = 180
BEAT_RE = re.compile(r"허브 정상 (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")


def should_restart(text, now, limit=STALE_SECONDS):
    """True only when the heartbeat file exists and its clock is older than `limit` seconds."""
    if text is None:
        return False
    found = BEAT_RE.search(text)
    if not found:
        return True
    then = datetime.strptime(found[1], "%Y-%m-%d %H:%M")
    return (now - then).total_seconds() > limit


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--drive", required=True)
    p.add_argument("--stale", type=int, default=STALE_SECONDS)
    args = p.parse_args(argv)
    path = Path(args.drive) / "허브상태.txt"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        text = None
    return 2 if should_restart(text, datetime.now(), args.stale) else 0


if __name__ == "__main__":
    sys.exit(main())
