"""Pure demand formulas: connection component responses and platform-base magnitudes."""

import math
from typing import Optional

from .results import AnalysisPoint


def resolve_connection_component_linear_response(
    point: AnalysisPoint,
    connection_id: str,
    component: str,
) -> Optional[tuple[float, float]]:
    """Resolve baseline/sensitivity for linear connection components.

    Returns (baseline, sensitivity) for components representable as
    baseline + sensitivity * hook_load_kN. Returns None when the
    component is unsupported or required local-axis data is unavailable.
    """
    base_map = point.baseline_reactions.get(connection_id, {})
    sens_map = point.sensitivity_reactions.get(connection_id, {})

    if component in {"Fx", "Fy", "Fz", "M", "Mx", "My"}:
        return float(base_map.get(component, 0.0)), float(sens_map.get(component, 0.0))

    axis_kind = None
    if component == "boom_axial":
        axis_kind = "axial"
    elif component == "boom_normal":
        axis_kind = "normal"
    elif component == "leg_axial":
        axis_kind = "axial"
    elif component == "leg_normal":
        axis_kind = "normal"
    else:
        return None

    axis_map = point.connection_local_axes or {}
    axis = axis_map.get(connection_id)
    if not axis:
        return None

    if isinstance(axis, dict):
        ux = float(axis.get("ux", 0.0))
        uz = float(axis.get("uz", 0.0))
    elif isinstance(axis, (tuple, list)) and len(axis) >= 2:
        ux = float(axis[0])
        uz = float(axis[1])
    else:
        return None

    if abs(ux) + abs(uz) <= 1e-12:
        return None

    fx0 = float(base_map.get("Fx", 0.0))
    fz0 = float(base_map.get("Fz", 0.0))
    sfx = float(sens_map.get("Fx", 0.0))
    sfz = float(sens_map.get("Fz", 0.0))

    if axis_kind == "axial":
        return fx0 * ux + fz0 * uz, sfx * ux + sfz * uz
    # Right-handed in-plane normal from axial (ux, uz).
    return fx0 * (-uz) + fz0 * ux, sfx * (-uz) + sfz * ux


def compute_platform_base_max_bearing_line_load_kN_per_m(
    *,
    fz_kN: float,
    mx_kNm: float,
    my_kNm: float,
    slewing_bearing_diameter_m: float,
) -> float:
    """Compute bearing line load demand from vertical force and resultant moment."""
    diameter = float(slewing_bearing_diameter_m)
    if diameter <= 0.0:
        raise ValueError("slewing_bearing_diameter_m must be > 0")
    m_res = math.hypot(float(mx_kNm), float(my_kNm))
    return float(fz_kN) / (math.pi * diameter) + 4.0 * m_res / (math.pi * diameter * diameter)


def compute_platform_base_min_bearing_line_load_kN_per_m(
    *,
    fz_kN: float,
    mx_kNm: float,
    my_kNm: float,
    slewing_bearing_diameter_m: float,
) -> float:
    """Compute the minimum (signed) bearing line load; negative means uplift."""
    diameter = float(slewing_bearing_diameter_m)
    if diameter <= 0.0:
        raise ValueError("slewing_bearing_diameter_m must be > 0")
    m_res = math.hypot(float(mx_kNm), float(my_kNm))
    return float(fz_kN) / (math.pi * diameter) - 4.0 * m_res / (math.pi * diameter * diameter)


def compute_platform_base_fradial_kN(
    *,
    fx_kN: float,
    fy_kN: float,
) -> float:
    """Compute platform-base radial force magnitude from Fx/Fy."""
    return math.hypot(float(fx_kN), float(fy_kN))


def compute_platform_base_mradial_kNm(
    *,
    mx_kNm: float,
    my_kNm: float,
) -> float:
    """Compute platform-base radial moment magnitude from Mx/My."""
    return math.hypot(float(mx_kNm), float(my_kNm))
