"""Rope reeving length and winch spooled-mass calculations.

Winch nodes for a hoist are the nodes referenced by that hoist's own rope
segments whose id contains "winch" (case-insensitive). When a hoist doesn't
specify rope_length_m, the total rope length is assumed to equal the reeved
length at max hook travel and 0 deg boom angle.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

from .solver.kinematics import KinematicsAdapter

EffectiveMultFn = Callable[[str, dict[str, Any], int], int]


def _find_hoist(doc_dict: dict[str, Any], hoist_id: str) -> Optional[dict[str, Any]]:
    return next((h for h in doc_dict.get("hoists", []) if h.get("id") == hoist_id), None)


def _find_rope(doc_dict: dict[str, Any], rope_id: str) -> Optional[dict[str, Any]]:
    return next((r for r in doc_dict.get("ropes", []) if r.get("id") == rope_id), None)


def find_winch_node_ids(doc_dict: dict[str, Any], hoist_id: str) -> list[str]:
    """Nodes on this hoist's own rope segments whose id contains "winch" (case-insensitive)."""
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return []
    rope = _find_rope(doc_dict, str(hoist.get("rope_id", "")))
    if rope is None:
        return []
    node_ids: list[str] = []
    seen: set[str] = set()
    for seg in rope.get("segments", []):
        for node_id in (str(seg.get("from_node_id", "")), str(seg.get("to_node_id", ""))):
            if node_id and "winch" in node_id.lower() and node_id not in seen:
                seen.add(node_id)
                node_ids.append(node_id)
    return node_ids


def _segment_length_m(
    positions: dict[str, dict[str, float]], from_id: str, to_id: str
) -> Optional[float]:
    a = positions.get(from_id)
    b = positions.get(to_id)
    if a is None or b is None:
        return None
    return math.hypot(float(b["x"]) - float(a["x"]), float(b["z"]) - float(a["z"]))


def compute_reeved_length_m(
    doc_dict: dict[str, Any],
    hoist_id: str,
    positions: dict[str, dict[str, float]],
    effective_mult: Optional[EffectiveMultFn] = None,
) -> Optional[float]:
    """Sum of this hoist's rope segment lengths x effective mult, at the supplied node positions.

    effective_mult(rope_id, segment, authored_mult) overrides a segment's mult, e.g. to
    substitute a hoist's split_falls for its normal falls on the managed hook segment.
    """
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return None
    rope_id = str(hoist.get("rope_id", ""))
    rope = _find_rope(doc_dict, rope_id)
    if rope is None:
        return None
    total = 0.0
    for seg in rope.get("segments", []):
        length = _segment_length_m(
            positions, str(seg.get("from_node_id", "")), str(seg.get("to_node_id", ""))
        )
        if length is None:
            return None
        authored_mult = max(1, int(seg.get("mult", 1)))
        mult = (
            authored_mult
            if effective_mult is None
            else max(1, int(effective_mult(rope_id, seg, authored_mult)))
        )
        total += length * mult
    return total


def compute_reference_reeved_length_m(doc_dict: dict[str, Any], hoist_id: str) -> Optional[float]:
    """Reeved length at boom angle 0 deg with the hook lowered to max_hook_travel_m."""
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return None
    kin = KinematicsAdapter(doc_dict)
    positions = kin.compute_all_node_positions(0.0)

    load_node_id = str(hoist.get("load_node_id") or "")
    max_travel = hoist.get("max_hook_travel_m")
    if load_node_id in positions and max_travel is not None:
        nodes_defs = {n.get("id"): n for n in doc_dict.get("nodes", [])}
        below_id = str((nodes_defs.get(load_node_id, {}) or {}).get("below_node_id") or "")
        reference = positions.get(below_id)
        if reference is not None:
            positions = dict(positions)
            positions[load_node_id] = {
                "x": float(positions[load_node_id]["x"]),
                "z": float(reference["z"]) - float(max_travel),
            }
    return compute_reeved_length_m(doc_dict, hoist_id, positions)


def resolve_total_rope_length_m(doc_dict: dict[str, Any], hoist_id: str) -> Optional[float]:
    """The hoist's authored rope_length_m, or the reference reeved length when unspecified."""
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return None
    specified = hoist.get("rope_length_m")
    if specified is not None:
        return float(specified)
    return compute_reference_reeved_length_m(doc_dict, hoist_id)


def compute_rope_on_winch(
    doc_dict: dict[str, Any],
    hoist_id: str,
    positions: dict[str, dict[str, float]],
    effective_mult: Optional[EffectiveMultFn] = None,
) -> tuple[float, float]:
    """(length_on_winch_m, mass_on_winch_kg) for this hoist at the supplied
    (live) node positions."""
    total = resolve_total_rope_length_m(doc_dict, hoist_id)
    reeved = compute_reeved_length_m(doc_dict, hoist_id, positions, effective_mult)
    if total is None or reeved is None:
        return 0.0, 0.0
    hoist = _find_hoist(doc_dict, hoist_id)
    linear_mass_kg_m = float((hoist or {}).get("linear_mass_kg_m", 0.0))
    length_on_winch_m = max(0.0, total - reeved)
    return length_on_winch_m, length_on_winch_m * linear_mass_kg_m
