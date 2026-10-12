"""Consistency checks for the authored-document contract.

The JSON Schema is generated from crane_statics.data.authored_models, not
hand-authored, so the main risk is a checked-in file drifting from what the
models would currently generate. See .claude/agents/schema-contract-reviewer.md.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import tomllib

from crane_statics.data.authored_models import AUTHORED_SCHEMA_MAJOR_VERSION
from crane_statics.schemas.generate_schema import SCHEMA_FILENAME, generate_schema, render

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "src" / "crane_statics" / "schemas"


def test_generated_schema_is_up_to_date():
    checked_in = (SCHEMAS_DIR / SCHEMA_FILENAME).read_text(encoding="utf-8")
    regenerated = render(generate_schema())
    assert checked_in == regenerated, (
        f"{SCHEMA_FILENAME} is out of date with authored_models.py; run "
        "`python -m crane_statics.schemas.generate_schema` and commit the result"
    )


def test_schema_filename_matches_major_version():
    assert SCHEMA_FILENAME == f"crane-statics-v{AUTHORED_SCHEMA_MAJOR_VERSION}.schema.json"


def test_package_data_glob_still_matches_schema_filename():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"]["crane_statics"]
    relative_path = f"schemas/{SCHEMA_FILENAME}"
    assert any(
        fnmatch.fnmatch(relative_path, pattern) for pattern in patterns
    ), f"{relative_path!r} is not matched by any package-data glob {patterns!r} in pyproject.toml"
