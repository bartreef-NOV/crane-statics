"""Authored v13 documents for the tests: examples and inline v12 dicts on the current format.

The shipped ``examples/*.yaml`` may still be on schema v12. ``example_path`` hands out a
v13 copy of an example (the file itself once it is already v13), and ``v13`` converts an
inline authored dict. Both go through ``crane_statics.data.migrate_v13.migrate_document``
and are idempotent: a document already on schema 13 is returned untouched.
"""

from __future__ import annotations

import functools
from copy import deepcopy
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from crane_statics.core.io import _StrictIntSafeLoader, load_document
from crane_statics.core.load_condition import condition_document, scene_case
from crane_statics.data.authored_models import AUTHORED_SCHEMA_MAJOR_VERSION, authored_schema_major
from crane_statics.data.migrate_v13 import migrate_document, migrate_file
from crane_statics.data.models import ConditionHoist, CraneDocument

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def v13(doc: dict[str, Any]) -> dict[str, Any]:
    """``doc`` as a v13 authored dict: migrated from v12, or ``doc`` itself when already v13."""
    schema = doc.get("schema")
    version = schema.get("version") if isinstance(schema, dict) else None
    if authored_schema_major(version) == AUTHORED_SCHEMA_MAJOR_VERSION:
        return doc
    return migrate_document(doc)


def copy_hoist(model_definition: dict[str, Any], source: str, target: str) -> dict[str, Any]:
    """Add hoist ``target`` to an authored v13 ``model_definition`` as a copy of ``source``,
    usable in every condition ``source`` is usable in with the same settings; returns it."""
    hoist: dict[str, Any] = deepcopy(model_definition["hoists"][source])
    model_definition["hoists"][target] = hoist
    for condition in model_definition.get("conditions", {}).values():
        entries = condition.get("hoists", {})
        if source in entries:
            entries[target] = deepcopy(entries[source])
    return hoist


def read_yaml(path: Union[str, Path]) -> dict[str, Any]:
    """The raw authored dict in the YAML file at ``path``."""
    with open(path, "r", encoding="utf-8-sig") as f:
        data: dict[str, Any] = yaml.load(f, Loader=_StrictIntSafeLoader)
    return data


def _is_v13(path: Path) -> bool:
    return authored_schema_major(read_yaml(path)["schema"]["version"]) == 13


@functools.lru_cache(maxsize=None)
def _examples_dir() -> Path:
    """``examples/`` itself once every example is v13; otherwise a per-process temporary
    copy of it with the v12 files migrated (all files, so siblings resolve too)."""
    sources = sorted(EXAMPLES.glob("*.yaml"))
    if all(_is_v13(p) for p in sources):
        return EXAMPLES
    target = Path(tempfile.mkdtemp(prefix="crane_statics_v13_examples_"))
    for source in sources:
        copy = target / source.name
        shutil.copyfile(source, copy)
        if not _is_v13(copy):
            migrate_file(copy)
    return target


def example_path(example: Union[str, Path]) -> Path:
    """A v13 file of ``example`` (a file name under ``examples/`` or a path to one).

    While ``examples/`` holds v12 files this is the example's migrated copy in a
    per-process temporary directory (same file name, next to the other examples); once
    they are v13 it is the example itself. Treat the result as read-only.
    """
    path = Path(example)
    if not path.is_absolute() and path.parent == Path("."):
        path = EXAMPLES / path
    path = path.resolve()
    if path.parent != EXAMPLES:
        return path  # already a migrated copy, or a file outside examples/
    return _examples_dir() / path.name


def example_dict(example: Union[str, Path]) -> dict[str, Any]:
    """The v13 authored dict of ``example`` (a fresh copy on every call)."""
    return read_yaml(example_path(example))


def load_example(example: Union[str, Path]) -> CraneDocument:
    """``example`` loaded through ``load_document`` on its v13 file."""
    return load_document(example_path(example))


def case_document(doc: CraneDocument, condition_name: Optional[str] = None) -> CraneDocument:
    """``doc`` with the environment of the Scene's case of ``condition_name`` (None: the
    first condition), the document a ``CraneCalculator`` for that case is built from.

    v13 keeps the wind speed and vessel motion on the conditions; the runtime environment
    only holds placeholders, so a calculator built straight from ``doc`` would not see them.
    """
    return condition_document(doc, scene_case(doc, condition_name))


def load_example_case(example: Union[str, Path]) -> CraneDocument:
    """``case_document`` of ``load_example(example)``."""
    return case_document(load_example(example))


def hoist_settings(
    doc: CraneDocument, hoist_id: str, condition_name: Optional[str] = None
) -> ConditionHoist:
    """``hoist_id``'s entry (leads, DAF, chart) in ``condition_name`` (None: the first one)."""
    return scene_case(doc, condition_name).hoist_settings(hoist_id)


def authored_daf(doc: CraneDocument, hoist_id: str, condition_name: Optional[str] = None) -> float:
    """The constant hook DAF of ``hoist_id`` in a rules-less condition (1.0 when omitted)."""
    daf = hoist_settings(doc, hoist_id, condition_name).daf
    return 1.0 if daf is None else float(daf)
