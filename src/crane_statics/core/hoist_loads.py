"""Hoist and rope helpers shared by the drawn-loads builder and the scene."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def _positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _nonnegative_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except Exception:
        return None
    return parsed if parsed >= 0.0 else None


def effective_segment_mult(
    hoist: Mapping[str, Any],
    segment: Mapping[str, Any],
    authored_mult: int,
    rope_id: str,
    *,
    split_mode_active: bool,
) -> int:
    """Falls carried by one rope segment, honouring the hoist's split-block mode.

    Only the segment the active hoist manages (support node <-> load node) is
    overridden; every other segment keeps its authored multiplier.
    """
    hoist_rope_id = str(hoist.get("rope_id", "")).strip()
    if not hoist_rope_id or str(rope_id).strip() != hoist_rope_id:
        return authored_mult

    support_node_id = str(hoist.get("support_node_id", "")).strip()
    load_node_id = str(hoist.get("load_node_id", "")).strip()
    if not support_node_id or not load_node_id:
        return authored_mult

    from_node = str(segment.get("from_node_id", "")).strip()
    to_node = str(segment.get("to_node_id", "")).strip()
    is_managed_hook_segment = (from_node == support_node_id and to_node == load_node_id) or (
        from_node == load_node_id and to_node == support_node_id
    )
    if not is_managed_hook_segment:
        return authored_mult

    falls = _positive_int(hoist.get("falls"))
    split_falls = _positive_int(hoist.get("split_falls"))
    if split_mode_active and split_falls is not None:
        return split_falls
    if falls is not None:
        return falls
    return authored_mult


def split_support_mass_t(hoist: Mapping[str, Any], *, split_mode_active: bool) -> Optional[float]:
    """Mass left at the support node when a splitable block is split, in tonnes."""
    if not split_mode_active:
        return None
    if not bool(hoist.get("splitable_block", False)):
        return None
    hook_mass_t = _nonnegative_float(hoist.get("hook_mass_t"))
    split_hook_mass_t = _nonnegative_float(hoist.get("split_hook_mass_t"))
    if hook_mass_t is None or split_hook_mass_t is None:
        return None
    support_mass_t = max(0.0, hook_mass_t - split_hook_mass_t)
    if support_mass_t <= 1e-9:
        return None
    return support_mass_t


def active_hoist_dict(document_dict: Mapping[str, Any], hoist_id: str) -> dict[str, Any]:
    """The authored hoist a load set is built for, or ``{}`` when unresolved."""
    return next(
        (h for h in document_dict.get("hoists", []) if h.get("id") == hoist_id),
        {},
    )


def rope_tension_channel(rope: Mapping[str, Any], rope_id: str) -> str:
    """Which analysis-point channel carries this rope's tension."""
    mode = str(rope.get("tension_mode", "") or "").strip().lower()
    return "boom_hoist" if mode == "solve" else rope_id


def resolve_rope_tension_kN(
    rope: Mapping[str, Any],
    rope_id: str,
    *,
    analysis_point: Any,
    hook_load_kN: float,
) -> Optional[float]:
    """Rope tension at the given hook load, linearised about the analysis point."""
    if analysis_point is None:
        return None
    baseline = getattr(analysis_point, "baseline_rope_tensions", {}) or {}
    sensitivity = getattr(analysis_point, "sensitivity_rope_tensions", {}) or {}
    channel = rope_tension_channel(rope, rope_id)
    base = float(baseline.get(channel, baseline.get(rope_id, 0.0)))
    sens = float(sensitivity.get(channel, sensitivity.get(rope_id, 0.0)))
    return base + sens * float(hook_load_kN)


def mass_point_label(mass_point: Mapping[str, Any]) -> str:
    mass_point_id = str(mass_point.get("id", "")).strip()
    return mass_point_id if mass_point_id else "Unnamed mass point"
