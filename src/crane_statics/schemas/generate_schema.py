"""Generates the published authored-document JSON Schema from AuthoredDocument.

The pydantic models in crane_statics.data.authored_models are the source of
truth for the authored-document contract; this script derives the JSON
Schema file from them rather than it being hand-authored.

Usage:
    python -m crane_statics.schemas.generate_schema          # write the file
    python -m crane_statics.schemas.generate_schema --check  # verify, don't write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crane_statics.data.authored_models import AuthoredDocument, AUTHORED_SCHEMA_MAJOR_VERSION

SCHEMAS_DIR = Path(__file__).parent
SCHEMA_FILENAME = f"crane-statics-v{AUTHORED_SCHEMA_MAJOR_VERSION}.schema.json"


def generate_schema() -> dict:
    """Build the published JSON Schema document from AuthoredDocument."""
    schema = AuthoredDocument.model_json_schema()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.com/schemas/{SCHEMA_FILENAME}",
        "title": f"Crane Statics Authored Input v{AUTHORED_SCHEMA_MAJOR_VERSION}",
        **schema,
    }
    return schema


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the checked-in schema file matches generated output; don't write",
    )
    args = parser.parse_args()

    rendered = render(generate_schema())
    target = SCHEMAS_DIR / SCHEMA_FILENAME

    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != rendered:
            print(f"{target} is out of date with authored_models.py.", file=sys.stderr)
            print("Run: python -m crane_statics.schemas.generate_schema", file=sys.stderr)
            return 1
        print(f"{target} is up to date.")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
