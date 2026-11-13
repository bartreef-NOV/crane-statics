"""Rewrite authored crane documents in place from schema v12 to v13.

Usage: python scripts/migrate_authored_v13.py FILE [FILE ...]
"""

from __future__ import annotations

import sys

from crane_statics.data.migrate_v13 import migrate_file


def main(paths: list[str]) -> None:
    for path in paths:
        migrate_file(path)
        print(f"migrated {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
