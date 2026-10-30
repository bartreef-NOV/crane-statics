"""Rope facts read from the static context and per-hoist runtime overrides."""

from __future__ import annotations

from typing import Any, Dict, Tuple

Overrides = Dict[str, Dict[str, Any]]


def effective_parts(base: int, override: Dict[str, Any]) -> int:
    """Falls on a hook: the runtime ``falls`` override when it parses, else ``base``."""
    falls = override.get("falls")
    if falls is not None:
        try:
            return max(1, int(falls))
        except (TypeError, ValueError):
            pass
    return max(1, int(base))


def hook_mass_t(hoist: Dict[str, Any], override: Dict[str, Any]) -> float:
    """Hook block mass (t) of ``hoist``, with the runtime override applied."""
    return float(override.get("hook_mass_t", hoist.get("hook_mass_t", 0.0)) or 0.0)


def _active_rope_metadata(
    doc_dict: Dict[str, Any],
    hoist_id: str,
    solver_ctx: Dict[str, Any],
    hoist_runtime_overrides: Overrides | None = None,
) -> Tuple[Tuple[str, ...], str, int]:
    rope_ids = tuple(str(r["id"]) for r in doc_dict.get("ropes", []) if r.get("id"))
    hoist = solver_ctx["hoist_by_id"].get(hoist_id)
    if hoist is None:
        return rope_ids, "", 1
    active_rope_id = str(hoist.get("rope_id", ""))
    load_node_id = str(hoist.get("load_node_id", ""))
    n = solver_ctx["parts_count_map"].get((active_rope_id, load_node_id), 1)
    override = (hoist_runtime_overrides or {}).get(hoist_id, {})
    return rope_ids, active_rope_id, effective_parts(n, override)


def _inactive_rope_mass_per_part(
    active_hoist_id: str,
    solver_ctx: Dict[str, Any],
    hoist_runtime_overrides: Overrides | None = None,
) -> Dict[str, float]:
    """Idle hook mass per fall (t) by rope; the idle tension is this times (g + accel_z)."""
    baseline_by_rope: Dict[str, float] = {}
    for hoist in solver_ctx.get("hoists", []):
        hoist_runtime_id = str(hoist.get("id", "") or "")
        rope_id = str(hoist.get("rope_id", "") or "")
        if not rope_id or rope_id == "boom_hoist" or hoist_runtime_id == active_hoist_id:
            continue
        override = (hoist_runtime_overrides or {}).get(hoist_runtime_id, {})
        load_node_id = str(hoist.get("load_node_id", "") or "")
        parts = solver_ctx.get("parts_count_map", {}).get((rope_id, load_node_id), 1)
        baseline_by_rope[rope_id] = hook_mass_t(hoist, override) / effective_parts(parts, override)
    return baseline_by_rope
