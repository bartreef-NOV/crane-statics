"""Rewrite authored crane documents in place from schema v13 to v14.

Usage: python scripts/migrate_authored_v14.py FILE [FILE ...]
"""

from __future__ import annotations

import sys

from crane_statics.data.migrate_v14 import migrate_file


def main(paths: list[str]) -> None:
    failed = False
    for path in paths:
        try:
            migrate_file(path)
        except Exception as e:  # report and continue with the remaining files
            print(f"error: {path}: {e}", file=sys.stderr)
            failed = True
        else:
            print(f"migrated {path}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
