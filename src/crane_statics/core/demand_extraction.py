"""Shared demand-extraction helpers for connection components and rope tensions."""

from __future__ import annotations

from typing import Optional, Any
import math

from ..calculation.engine import (
    compute_platform_base_fradial_kN,
    compute_platform_base_mradial_kNm,
    compute_platform_base_max_bearing_line_load_kN_per_m,
    resolve_connection_component_linear_response,
)


def extract_connection_component_response(
    pt: Any,
    hook_kN: float,
    connection_id: str,
    component: str,
    support_widths_diameter_m: float = 1.0,
) -> Optional[float]:
    """Extract a single connection component demand from analysis point.

    Handles standard components (resultant, fradial, mradial, max_bearing_line_load)
    and linear-response generic components.

    Args:
        pt: AnalysisPoint with baseline_reactions and sensitivity_reactions
        hook_kN: Hook load sensitivity multiplier (kN)
        connection_id: Connection entity ID (e.g. "platform_base", "boom_base")
        component: Component name (e.g. "resultant", "fradial", "T")
        support_widths_diameter_m: Slewing bearing diameter for max_bearing_line_load

    Returns:
        Component response or None if the component is not available.
    """
    base_map = pt.baseline_reactions.get(connection_id, {})
    sens_map = pt.sensitivity_reactions.get(connection_id, {})

    if component == "resultant":
        fx = float(base_map.get("Fx", 0.0)) + float(sens_map.get("Fx", 0.0)) * hook_kN
        fz = float(base_map.get("Fz", 0.0)) + float(sens_map.get("Fz", 0.0)) * hook_kN
        return math.hypot(fx, fz)

    elif component == "fradial" and connection_id == "platform_base":
        fx = float(base_map.get("Fx", 0.0)) + float(sens_map.get("Fx", 0.0)) * hook_kN
        fy = float(base_map.get("Fy", 0.0)) + float(sens_map.get("Fy", 0.0)) * hook_kN
        return compute_platform_base_fradial_kN(fx_kN=fx, fy_kN=fy)

    elif component == "mradial" and connection_id == "platform_base":
        mx = float(base_map.get("Mx", 0.0)) + float(sens_map.get("Mx", 0.0)) * hook_kN
        my = (
            float(base_map.get("My", base_map.get("M", 0.0)))
            + float(sens_map.get("My", sens_map.get("M", 0.0))) * hook_kN
        )
        return compute_platform_base_mradial_kNm(mx_kNm=mx, my_kNm=my)

    elif component == "max_bearing_line_load" and connection_id == "platform_base":
        fz = float(base_map.get("Fz", 0.0)) + float(sens_map.get("Fz", 0.0)) * hook_kN
        mx = float(base_map.get("Mx", 0.0)) + float(sens_map.get("Mx", 0.0)) * hook_kN
        my = (
            float(base_map.get("My", base_map.get("M", 0.0)))
            + float(sens_map.get("My", sens_map.get("M", 0.0))) * hook_kN
        )
        return compute_platform_base_max_bearing_line_load_kN_per_m(
            fz_kN=fz,
            mx_kNm=mx,
            my_kNm=my,
            slewing_bearing_diameter_m=support_widths_diameter_m,
        )

    else:
        # Generic linear-response component. Preserve its sign for result rows;
        # capacity checks can apply magnitude semantics at their boundary.
        linear = resolve_connection_component_linear_response(pt, connection_id, component)
        if linear is None:
            return None
        base, sens = linear
        return base + sens * hook_kN


def extract_connection_component_demand(
    pt: Any,
    hook_kN: float,
    connection_id: str,
    component: str,
    support_widths_diameter_m: float = 1.0,
) -> Optional[float]:
    """Extract a non-negative connection demand from an analysis point."""
    response = extract_connection_component_response(
        pt,
        hook_kN,
        connection_id,
        component,
        support_widths_diameter_m=support_widths_diameter_m,
    )
    if response is None:
        return None
    if component in {"resultant", "fradial", "mradial", "max_bearing_line_load"}:
        return response
    return abs(response)


def connection_component_responds_to_hook_load(
    pt: Any,
    connection_id: str,
    component: str,
    support_widths_diameter_m: float = 1.0,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether a connection component changes with hook load."""
    baseline = extract_connection_component_response(
        pt,
        0.0,
        connection_id,
        component,
        support_widths_diameter_m=support_widths_diameter_m,
    )
    unit_load = extract_connection_component_response(
        pt,
        1.0,
        connection_id,
        component,
        support_widths_diameter_m=support_widths_diameter_m,
    )
    if baseline is None or unit_load is None:
        return False
    return abs(float(unit_load) - float(baseline)) > tolerance


def rope_tension_responds_to_hook_load(
    pt: Any,
    rope_id: str,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether a rope tension has non-zero hook-load sensitivity."""
    sensitivity = float(pt.sensitivity_rope_tensions.get(rope_id, 0.0))
    return abs(sensitivity) > tolerance


def extract_rope_tension_demand(
    pt: Any,
    hook_kN: float,
    rope_id: str,
) -> float:
    """Extract rope tension demand from analysis point.

    Args:
        pt: AnalysisPoint with baseline_rope_tensions and sensitivity_rope_tensions
        hook_kN: Hook load sensitivity multiplier (kN)
        rope_id: Rope entity ID

    Returns:
        Rope tension (kN).
    """
    sens = float(pt.sensitivity_rope_tensions.get(rope_id, 0.0))
    base = float(pt.baseline_rope_tensions.get(rope_id, 0.0))
    return base + sens * hook_kN
