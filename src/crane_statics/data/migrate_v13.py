"""Migrate authored documents from schema v12 to v13.

v13 moves ``daf`` / ``offlead_deg`` / ``sidelead_deg`` from the payload hoists into the
conditions and tags every load chart point with the conditions it applies to.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

_TARGET_VERSION = "13.0.0"
_LEAD_FIELDS = ("daf", "offlead_deg", "sidelead_deg")
_DEFAULT_CONDITION = "default"


def _condition_hoists(hoists: dict[str, Any]) -> dict[str, Any]:
    """Per-condition hoist settings taken from the v12 payload hoists (everything but BH)."""
    result: dict[str, Any] = {}
    for hoist_id, hoist in hoists.items():
        if hoist_id == "BH":
            continue
        entry: dict[str, Any] = {}
        if "offlead_deg" in hoist:
            entry["offlead_deg"] = hoist["offlead_deg"]
        if hoist.get("sidelead_deg", 0.0) != 0.0:
            entry["sidelead_deg"] = hoist["sidelead_deg"]
        if hoist.get("daf", 1.0) != 1.0:
            entry["daf"] = hoist["daf"]
        result[hoist_id] = entry
    return result


def _tag_chart(chart: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "outreach_m": point["outreach_m"],
            "load_t": point["load_t"],
            "conditions": list(names),
            **{k: v for k, v in point.items() if k not in ("outreach_m", "load_t", "conditions")},
        }
        for point in chart
    ]


def migrate_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a v13 copy of the v12 authored document ``doc`` (the input is not mutated)."""
    out = deepcopy(doc)
    md: dict[str, Any] = out["model_definition"]
    hoists: dict[str, Any] = md.get("hoists", {})
    payload = _condition_hoists(hoists)

    if md.get("rules") is None:
        environment = md.get("environment", {})
        condition: dict[str, Any] = {}
        if "max_wind_speed_m_s" in environment:
            condition["wind_speed_m_s"] = environment.pop("max_wind_speed_m_s")
        motion = md.pop("vessel_motion", None)
        if motion is not None:
            condition["vessel_motion"] = motion
        conditions: dict[str, Any] = {_DEFAULT_CONDITION: condition}
        # Insert ``conditions`` right after ``environment`` to keep a readable key order.
        reordered: dict[str, Any] = {}
        for key, value in md.items():
            reordered[key] = value
            if key == "environment":
                reordered["conditions"] = conditions
        if "conditions" not in reordered:
            reordered["conditions"] = conditions
        md.clear()
        md.update(reordered)
    else:
        conditions = md["conditions"]

    for condition in conditions.values():
        condition["hoists"] = deepcopy(payload)
    names = list(conditions)

    for hoist in hoists.values():
        for field in _LEAD_FIELDS:
            hoist.pop(field, None)
        if "load_chart" in hoist:
            hoist["load_chart"] = _tag_chart(hoist["load_chart"], names)
        split = hoist.get("split")
        if split is not None and "load_chart" in split:
            split["load_chart"] = _tag_chart(split["load_chart"], names)

    out["schema"]["version"] = _TARGET_VERSION
    return out


def migrate_file(path: str | Path) -> None:
    """Rewrite the YAML file at ``path`` in place as a v13 document."""
    import yaml

    # Deferred: core.io imports this package, so a top-level import would be circular.
    from ..core.io import _CompactSafeDumper, _StrictIntSafeLoader

    path = Path(path)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = yaml.load(f, Loader=_StrictIntSafeLoader)
    migrated = migrate_document(data)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            migrated,
            f,
            Dumper=_CompactSafeDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
