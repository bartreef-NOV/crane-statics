"""Migrate authored documents from schema v13 to v14.

v14 moves the vessel-motion reference point from each condition's ``vessel_motion``
(``reference_x_m`` / ``reference_z_m``) to the crane's ``structure.motion_reference``
(``x_m`` / ``z_m``): it is a property of the crane, not of a condition.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

_TARGET_VERSION = "14.0.0"
_FIELDS = (("reference_x_m", "x_m"), ("reference_z_m", "z_m"))


def _pop_references(conditions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Remove the reference point of every condition; its values keyed by condition name."""
    found: dict[str, dict[str, Any]] = {}
    for name, condition in conditions.items():
        motion = condition.get("vessel_motion") if isinstance(condition, dict) else None
        if not isinstance(motion, dict):
            continue
        values = {new: motion.pop(old, 0.0) for old, new in _FIELDS}
        if not motion:
            del condition["vessel_motion"]
        found[str(name)] = values
    return found


def migrate_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a v14 copy of the v13 authored document ``doc`` (the input is not mutated).

    Raises ``ValueError`` when the conditions disagree on the reference point: it is now
    one value for the crane, so the file must say which.
    """
    schema = doc.get("schema") if isinstance(doc, dict) else None
    if not isinstance(schema, dict) or "version" not in schema:
        raise ValueError("Document has no schema.version; expected a v13 authored document")
    version = str(schema["version"])
    if not version.startswith("13."):
        raise ValueError(f"Cannot migrate schema version {version!r}; expected 13.x")
    md = doc.get("model_definition")
    if not isinstance(md, dict):
        raise ValueError("Document has no model_definition mapping")
    out = deepcopy(doc)
    md = out["model_definition"]
    found = _pop_references(md.get("conditions") or {})
    distinct = {tuple(values.items()) for values in found.values()}
    if len(distinct) > 1:
        detail = "; ".join(
            f"{name}: x {values['x_m']:g}, z {values['z_m']:g}" for name, values in found.items()
        )
        raise ValueError(
            "the conditions disagree on the vessel-motion reference point, which v14 keeps "
            f"once per crane ({detail}); make them equal in the v13 file, then migrate"
        )
    reference = dict(next(iter(found.values()))) if found else {}
    structure = md.get("structure")
    if reference and any(reference.values()) and isinstance(structure, dict):
        # Keep ``motion_reference`` ahead of the node positions for a readable key order.
        reordered: dict[str, Any] = {}
        for key, value in structure.items():
            if key == "boom_heel":
                reordered["motion_reference"] = reference
            reordered[key] = value
        if "motion_reference" not in reordered:
            reordered["motion_reference"] = reference
        structure.clear()
        structure.update(reordered)
    out["schema"]["version"] = _TARGET_VERSION
    return out


def migrate_file(path: str | Path) -> None:
    """Rewrite the YAML file at ``path`` in place as a v14 document."""
    import yaml

    # Deferred: core.io imports this package, so a top-level import would be circular.
    from ..core.io import _CompactSafeDumper, _StrictIntSafeLoader

    path = Path(path)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = yaml.load(f, Loader=_StrictIntSafeLoader)
    try:
        migrated = migrate_document(data)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e
    # Serialize fully before touching the file so a failure never leaves it half written.
    text = yaml.dump(
        migrated,
        Dumper=_CompactSafeDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    path.write_text(text, encoding="utf-8")
