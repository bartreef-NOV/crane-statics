"""Rope reeving length, rope self-weight, and the hook-height derivation.

Winch nodes for a hoist are the nodes referenced by that hoist's own rope
segments whose id contains "winch" (case-insensitive).

Rope self-weight is a *lumped-mass* idealisation: see :func:`rope_mass_at_nodes`,
the one definition both the solver and ``core.drawn_loads`` build their rope
weight from.

A payload hoist's rope length and hook travel are not authored: they follow from
the hoist's ``lowest_hook_height_m``, the absolute Z the hook must
reach at that hoist's minimum outreach. That state is the governing one --
reeved length falls monotonically as the boom lowers -- so the rope needed there
is the rope needed anywhere, and ``derive_hook_geometry`` computes both from it.
The boom hoist keeps an authored ``rope_length_m``; it has no hook to position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .solver.kinematics import KinematicsAdapter

EffectiveMultFn = Callable[[str, dict[str, Any], int], int]

#: A linear mass at or below this is no rope worth accounting for, in kg/m.
_MASS_TOLERANCE_KG_M = 1e-9


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
    positions: Mapping[str, Mapping[str, float]], from_id: str, to_id: str
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


def falls_override_effective_mult(
    doc_dict: dict[str, Any], falls_by_hoist_id: Mapping[str, int]
) -> EffectiveMultFn:
    """An ``effective_mult`` that swaps runtime falls onto managed hook segments.

    Splitting a block changes how many parts of rope reach the hook, and so how
    much rope is reeved rather than spooled. Only the segment between a hoist's
    support node and its hook is affected; every other segment keeps its
    authored multiplier.
    """
    managed: dict[str, tuple[frozenset[str], int]] = {}
    for hoist_id, falls in falls_by_hoist_id.items():
        hoist = _find_hoist(doc_dict, str(hoist_id))
        if hoist is None:
            continue
        support_id = str(hoist.get("support_node_id") or "")
        load_node_id = str(hoist.get("load_node_id") or "")
        rope_id = str(hoist.get("rope_id") or "")
        if not (support_id and load_node_id and rope_id):
            continue
        managed[rope_id] = (frozenset((support_id, load_node_id)), max(1, int(falls)))

    def effective_mult(rope_id: str, segment: dict[str, Any], authored_mult: int) -> int:
        entry = managed.get(str(rope_id))
        if entry is None:
            return authored_mult
        endpoints, falls = entry
        segment_endpoints = {
            str(segment.get("from_node_id", "")),
            str(segment.get("to_node_id", "")),
        }
        return falls if segment_endpoints == endpoints else authored_mult

    return effective_mult


@dataclass(frozen=True)
class RopeNodeMass:
    """Rope self-weight lumped at one node, in tonnes."""

    node_id: str
    reeved_t: float = 0.0
    spooled_t: float = 0.0
    hoist_ids: tuple[str, ...] = ()

    @property
    def mass_t(self) -> float:
        return self.reeved_t + self.spooled_t


def rope_mass_at_nodes(
    doc_dict: dict[str, Any],
    positions: Mapping[str, Mapping[str, float]],
    effective_mult: Optional[EffectiveMultFn] = None,
) -> dict[str, RopeNodeMass]:
    """Every hoist rope's self-weight, lumped at the nodes that carry it.

    A reeved segment is idealised as a straight bar between its end nodes: half
    its weight hangs on each end, on that node's own body. Whatever length is
    not reeved at these positions is still on the drum, so it sits entirely at
    the hoist's winch node. The total is therefore fixed by the hoist's
    ``rope_length_m`` -- lowering the boom only moves mass from the falls back
    onto the winch, it does not create or destroy it.

    A hoist with no winch node loses its spooled share: there is no node to hang
    it from, and inventing one would be a guess.
    """
    reeved: dict[str, float] = {}
    spooled: dict[str, float] = {}
    hoists_by_node: dict[str, list[str]] = {}

    def _credit(bucket: dict[str, float], node_id: str, mass_t: float, hoist_id: str) -> None:
        bucket[node_id] = bucket.get(node_id, 0.0) + mass_t
        owners = hoists_by_node.setdefault(node_id, [])
        if hoist_id not in owners:
            owners.append(hoist_id)

    for hoist in doc_dict.get("hoists", []):
        hoist_id = str(hoist.get("id", "") or "")
        linear_mass_kg_m = float(hoist.get("linear_mass_kg_m", 0.0) or 0.0)
        if not hoist_id or linear_mass_kg_m <= _MASS_TOLERANCE_KG_M:
            continue
        rope = _find_rope(doc_dict, str(hoist.get("rope_id", "")))
        if rope is None:
            continue
        rope_id = str(rope.get("id", ""))

        reeved_length_m = 0.0
        for seg in rope.get("segments", []):
            from_id = str(seg.get("from_node_id", ""))
            to_id = str(seg.get("to_node_id", ""))
            length = _segment_length_m(positions, from_id, to_id)
            if length is None:
                continue
            authored_mult = max(1, int(seg.get("mult", 1)))
            mult = (
                authored_mult
                if effective_mult is None
                else max(1, int(effective_mult(rope_id, seg, authored_mult)))
            )
            segment_length_m = length * mult
            reeved_length_m += segment_length_m
            half_t = segment_length_m * linear_mass_kg_m / 2000.0
            _credit(reeved, from_id, half_t, hoist_id)
            _credit(reeved, to_id, half_t, hoist_id)

        total_length_m = resolve_total_rope_length_m(doc_dict, hoist_id)
        winch_node_ids = find_winch_node_ids(doc_dict, hoist_id)
        if total_length_m is None or not winch_node_ids:
            continue
        spooled_length_m = max(0.0, float(total_length_m) - reeved_length_m)
        _credit(spooled, winch_node_ids[0], spooled_length_m * linear_mass_kg_m / 1000.0, hoist_id)

    return {
        node_id: RopeNodeMass(
            node_id=node_id,
            reeved_t=reeved.get(node_id, 0.0),
            spooled_t=spooled.get(node_id, 0.0),
            hoist_ids=tuple(hoists_by_node.get(node_id, ())),
        )
        for node_id in sorted(set(reeved) | set(spooled))
    }


def hook_support_node_id(doc_dict: dict[str, Any], hoist_id: str) -> str:
    """The node the hook hangs from: the load node's ``below_node_id``, else ``support_node_id``."""
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return ""
    load_node_id = str(hoist.get("load_node_id") or "")
    nodes_defs = {n.get("id"): n for n in doc_dict.get("nodes", [])}
    below_id = str((nodes_defs.get(load_node_id, {}) or {}).get("below_node_id") or "")
    return below_id or str(hoist.get("support_node_id") or "")


def hook_positions_at_height(
    doc_dict: dict[str, Any],
    hoist_id: str,
    positions: dict[str, dict[str, float]],
    hook_height_m: float,
) -> dict[str, dict[str, float]]:
    """``positions`` with this hoist's hook moved to absolute ``hook_height_m``.

    The hook cannot be hoisted past its own sheave, so the height is clamped to
    the support elevation -- a boom low enough puts the sheave below the design
    height, and the honest answer there is zero payout, not negative rope.
    """
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return positions
    load_node_id = str(hoist.get("load_node_id") or "")
    support_id = hook_support_node_id(doc_dict, hoist_id)
    hook = positions.get(load_node_id)
    support = positions.get(support_id)
    if hook is None or support is None:
        return positions
    moved = dict(positions)
    moved[load_node_id] = {
        "x": float(hook["x"]),
        "z": min(float(support["z"]), float(hook_height_m)),
    }
    return moved


def active_hook_positions(
    doc_dict: dict[str, Any],
    hoist_id: str,
    positions: dict[str, dict[str, float]],
    tackle_length_m: Optional[float] = None,
) -> dict[str, dict[str, float]]:
    """``positions`` with the active hoist's hook where the operator has hoisted it.

    Kinematics parks every managed hook a nominal drop below its sheave, which is
    a placeholder, not a position. ``tackle_length_m`` is the rope paid out below
    the sheave -- what the scene draws and drags. Passing ``None`` asks for the
    designed operating position instead: the hook at the hoist's
    ``lowest_hook_height_m``, which is the state the derived rope length
    was sized for and so the state a sweep or a contractual check evaluates.
    """
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return positions
    if tackle_length_m is None:
        hook_height_m = hoist.get("lowest_hook_height_m")
        if hook_height_m is None:
            return positions
        return hook_positions_at_height(doc_dict, hoist_id, positions, float(hook_height_m))

    support = positions.get(hook_support_node_id(doc_dict, hoist_id))
    if support is None:
        return positions
    return hook_positions_at_height(
        doc_dict,
        hoist_id,
        positions,
        float(support["z"]) - max(0.0, float(tackle_length_m)),
    )


def derive_hook_geometry(
    doc_dict: dict[str, Any],
    hoist_id: str,
    hook_height_m: float,
) -> Optional[tuple[float, float]]:
    """``(max_hook_travel_m, rope_length_m)`` implied by the lowest hook height.

    Both follow from one state: the hook at ``hook_height_m`` with the boom at
    this hoist's minimum outreach. Returns ``None`` when the geometry cannot be
    resolved (an unreachable minimum outreach, a missing support node), leaving
    the caller to report it rather than substitute a number.

    Raises ``ValueError`` when the lowest hook height sits above the support node at
    minimum outreach, which asks for negative rope payout.
    """
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return None
    support_id = hook_support_node_id(doc_dict, hoist_id)
    if not support_id:
        return None

    outreach_min = hoist.get("outreach_min_m")
    if outreach_min is None:
        return None
    kin = KinematicsAdapter(doc_dict)
    try:
        angle = kin.outreach_to_angle(float(outreach_min), hoist_id)
    except (TypeError, ValueError, RuntimeError, ZeroDivisionError):
        return None
    if angle is None:
        return None

    positions = kin.compute_all_node_positions(float(angle))
    support = positions.get(support_id)
    if support is None:
        return None
    travel_m = float(support["z"]) - float(hook_height_m)
    if travel_m < 0.0:
        raise ValueError(
            f"hoist[{hoist_id}]: lowest_hook_height_m {hook_height_m:g} m is above the "
            f"support node {support_id!r} at {float(support['z']):g} m, so the required hook "
            f"travel is negative ({travel_m:g} m)"
        )

    reeved = compute_reeved_length_m(
        doc_dict,
        hoist_id,
        hook_positions_at_height(doc_dict, hoist_id, positions, hook_height_m),
    )
    if reeved is None:
        return None
    return travel_m, reeved


def reeved_length_at_angle_m(
    doc_dict: dict[str, Any], hoist_id: str, angle_deg: float
) -> Optional[float]:
    """Reeved length with the boom at ``angle_deg`` and every node where kinematics puts it.

    For the boom hoist that is the whole story -- its rope has no hook to pay out
    -- so this is how much rope it must own to stand at that angle at all.
    """
    kin = KinematicsAdapter(doc_dict)
    positions = kin.compute_all_node_positions(float(angle_deg))
    return compute_reeved_length_m(doc_dict, hoist_id, positions)


def resolve_total_rope_length_m(doc_dict: dict[str, Any], hoist_id: str) -> Optional[float]:
    """The hoist's ``rope_length_m``: authored for the boom hoist, derived for payload hoists."""
    hoist = _find_hoist(doc_dict, hoist_id)
    if hoist is None:
        return None
    specified = hoist.get("rope_length_m")
    return None if specified is None else float(specified)


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
