"""Allowable hook load: invert each design limit's response and keep the most restrictive.

For a limit on a linear response Q(H) = Q0 + s*H the hook-force capacity is
H_max = (Q_max - Q0) / s. Magnitude limits (resultant, radial, bearing line load) are
not linear in H and are solved with ``capacity``.

A ``DemandScale`` factors an entity's demand, ``dead * Q0 + live(LL) * s * H`` (LL the
unamplified live load), and is solved by bisection. An entity id ``<entity>_retaining``
names a factored copy of ``<entity>``: it reads that entity's reactions under its own scale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from ..data.models import CraneDocument
from .capacity import solve_capacity_limit_kN, solve_radial_capacity_kN
from .demand_formulas import (
    compute_platform_base_max_bearing_line_load_kN_per_m,
    compute_platform_base_min_bearing_line_load_kN_per_m,
    resolve_connection_component_linear_response,
)
from .dynamic_factor import DynamicFactorLike, as_dynamic_factor
from .results import AllowableCapacity, AnalysisPoint

_PLATFORM_BASE = "platform_base"
# Radial magnitude limits: component -> the two reaction quantities as (key, fallback key).
# ``resultant`` applies to any reaction entity, the others to the platform base only.
_RADIAL_QUANTITIES: dict[str, tuple[tuple[str, Optional[str]], tuple[str, Optional[str]]]] = {
    "resultant": (("Fx", None), ("Fz", None)),
    "fradial": (("Fx", None), ("Fy", None)),
    "mradial": (("Mx", None), ("My", "M")),
}
_BEARING_COMPONENTS = ("max_bearing_line_load", "min_bearing_line_load")
#: Entity-id suffix of a factored copy of an entity (``platform_base_retaining``).
RETAINING_SUFFIX = "_retaining"


def base_entity_id(entity_id: str) -> str:
    """The entity whose reactions ``entity_id`` reads: ``<entity>_retaining`` -> ``<entity>``."""
    if entity_id.endswith(RETAINING_SUFFIX) and len(entity_id) > len(RETAINING_SUFFIX):
        return entity_id[: -len(RETAINING_SUFFIX)]
    return entity_id


@dataclass(frozen=True)
class DemandScale:
    """Factors on an entity's demand: ``dead * baseline + live(LL) * sensitivity * H``.

    ``live`` takes the unamplified live load LL in kN (payload, hook block and suspended
    rope). ``live_load_kN`` turns the hook force H into LL; None takes the payload the
    hook factor's inverse gives plus the hook mass (no suspended rope).
    """

    live: Callable[[float], float]
    dead: float = 1.0
    live_load_kN: Optional[Callable[[float], float]] = None


def find_demand_scale(
    demand_scale: Optional[Mapping[str, DemandScale]], limit_key: str, component: str
) -> Optional[DemandScale]:
    """The scale of a limit: by limit key, then by the key without its ``_<component>``
    suffix (the entity, e.g. ``"platform_base"``). None without one.

    A factored copy (``<entity>_retaining``) has no unfactored meaning, so it never falls
    back to its base entity's scale or to none: without its own entry this raises
    ``ValueError`` (a caller forgot ``lift_factor.demand_scales``).
    """
    suffix = f"_{component}"
    entity = limit_key[: -len(suffix)] if limit_key.endswith(suffix) else limit_key
    for key in (limit_key, entity):
        scale = None if not demand_scale else demand_scale.get(key)
        if scale is not None:
            return scale
    if base_entity_id(entity) != entity:
        raise ValueError(f"design limit {limit_key!r}: no demand scale for {entity!r}")
    return None


def scaled_live_factor(
    scale: DemandScale,
    hook_daf: DynamicFactorLike,
    lower_block_mass_t: float,
    gravity_m_s2: float,
) -> Callable[[float], float]:
    """``H -> scale.live(LL(H))``, LL as ``DemandScale.live_load_kN`` describes."""
    if scale.live_load_kN is not None:
        to_ll = scale.live_load_kN
    else:
        factor = as_dynamic_factor(hook_daf)

        def to_ll(hook_kN: float) -> float:
            payload = max(0.0, factor.payload_t(hook_kN, lower_block_mass_t, gravity_m_s2))
            return (payload + lower_block_mass_t) * gravity_m_s2

    return lambda hook_kN: float(scale.live(to_ll(hook_kN)))


def _read(values: dict[str, float], key: str, fallback: Optional[str]) -> float:
    if fallback is None:
        return float(values.get(key, 0.0))
    return float(values.get(key, values.get(fallback, 0.0)))


def _magnitude_candidate(
    doc: CraneDocument,
    point: AnalysisPoint,
    entity_id: str,
    component: str,
    limit_kN: float,
    tolerance: float,
) -> Optional[float]:
    """Hook-force capacity for a magnitude limit, or None if ``component`` is not one."""
    if component != "resultant" and entity_id != _PLATFORM_BASE:
        return None
    base_map = point.baseline_reactions.get(entity_id, {})
    sens_map = point.sensitivity_reactions.get(entity_id, {})

    if component in _RADIAL_QUANTITIES:
        (ku, fu), (kv, fv) = _RADIAL_QUANTITIES[component]
        return solve_radial_capacity_kN(
            limit_kN,
            _read(base_map, ku, fu),
            _read(base_map, kv, fv),
            _read(sens_map, ku, fu),
            _read(sens_map, kv, fv),
        )

    if component in _BEARING_COMPONENTS:
        diameter = float(getattr(doc.support_widths, "slewing_bearing_diameter_m", 1.0))
        uplift = component == "min_bearing_line_load"
        line_load = (
            compute_platform_base_min_bearing_line_load_kN_per_m
            if uplift
            else compute_platform_base_max_bearing_line_load_kN_per_m
        )

        def demand(hook_kN: float) -> float:
            value = line_load(
                fz_kN=_read(base_map, "Fz", None) + _read(sens_map, "Fz", None) * hook_kN,
                mx_kNm=_read(base_map, "Mx", None) + _read(sens_map, "Mx", None) * hook_kN,
                my_kNm=_read(base_map, "My", "M") + _read(sens_map, "My", "M") * hook_kN,
                slewing_bearing_diameter_m=diameter,
            )
            # Uplift -q_min(H) must stay within the (positive) limit.
            return -value if uplift else value

        return solve_capacity_limit_kN(limit_kN, demand, tolerance=tolerance)

    return None


def _scaled_candidate(
    doc: CraneDocument,
    point: AnalysisPoint,
    entity_id: str,
    component: str,
    limit_kN: float,
    tolerance: float,
    dead: float,
    live: Callable[[float], float],
) -> Optional[float]:
    """Hook-force capacity of a limit under ``dead * Q0 + live(H) * s * H`` (bisection).

    The same components as the unscaled path, each quantity factored before the magnitude
    is taken. None when the component has no response on ``entity_id``.
    """
    base_map = point.baseline_reactions.get(entity_id, {})
    sens_map = point.sensitivity_reactions.get(entity_id, {})

    def value(key: str, fallback: Optional[str], hook_kN: float) -> float:
        base = _read(base_map, key, fallback)
        return dead * base + live(hook_kN) * _read(sens_map, key, fallback) * hook_kN

    demand: Callable[[float], float]
    magnitude = component == "resultant" or entity_id == _PLATFORM_BASE
    if magnitude and component in _RADIAL_QUANTITIES:
        (ku, fu), (kv, fv) = _RADIAL_QUANTITIES[component]

        def demand(hook_kN: float) -> float:
            return math.hypot(value(ku, fu, hook_kN), value(kv, fv, hook_kN))

    elif magnitude and component in _BEARING_COMPONENTS:
        diameter = float(getattr(doc.support_widths, "slewing_bearing_diameter_m", 1.0))
        uplift = component == "min_bearing_line_load"
        line_load = (
            compute_platform_base_min_bearing_line_load_kN_per_m
            if uplift
            else compute_platform_base_max_bearing_line_load_kN_per_m
        )

        def demand(hook_kN: float) -> float:
            q = line_load(
                fz_kN=value("Fz", None, hook_kN),
                mx_kNm=value("Mx", None, hook_kN),
                my_kNm=value("My", "M", hook_kN),
                slewing_bearing_diameter_m=diameter,
            )
            return -q if uplift else q

    else:
        linear = resolve_connection_component_linear_response(point, entity_id, component)
        if linear is None:
            return None
        baseline, sens = linear

        def demand(hook_kN: float) -> float:
            return dead * baseline + live(hook_kN) * sens * hook_kN

    return solve_capacity_limit_kN(limit_kN, demand, tolerance=tolerance)


def allowable_hook_load(
    doc: CraneDocument,
    point: AnalysisPoint,
    design_limits: dict[str, dict],  # entity_id -> {component -> max_kN}
    *,
    resolve_limit_target: Callable[[str, str], tuple[str, str]],
    tolerance: float,
    hook_daf: DynamicFactorLike = 1.0,
    lower_block_mass_t: float = 0.0,
    demand_scale: Optional[Mapping[str, DemandScale]] = None,
) -> AllowableCapacity:
    """Invert Q(H) = Q0 + s*H <= Q_max  →  H_max = (Q_max - Q0) / s.
    Returns the most restrictive limit.

    design_limits keys may be either entity_id ('boom_hoist') or
    limit_id ('boom_hoist_T'/'rear_hinge_Fx'); ``resolve_limit_target`` resolves
    the entity by stripping the component suffix when needed.

    ``demand_scale`` (keyed by connection id, e.g. ``"platform_base"``, or as
    ``find_demand_scale`` looks it up) factors a connection limit's demand to
    ``dead * Q0 + live(LL) * s * H``; such a limit is solved by bisection
    (``solve_capacity_limit_kN``; the demand is monotone in H for the pedestal factors).
    None or empty: today's inversion, bit for bit.
    """
    gravity = abs(doc.environment.gravity_m_s2)

    h_max_kN = float("inf")
    governing_limit_id = None

    for limit_key, components in design_limits.items():
        for component, limit_kN in components.items():
            if not limit_kN:
                continue

            entity_id, rope_channel = resolve_limit_target(limit_key, component)

            scale = find_demand_scale(demand_scale, limit_key, component)
            if scale is not None and entity_id in point.sensitivity_reactions:
                scaled_h = _scaled_candidate(
                    doc,
                    point,
                    entity_id,
                    component,
                    float(limit_kN),
                    tolerance,
                    float(scale.dead),
                    scaled_live_factor(scale, hook_daf, lower_block_mass_t, gravity),
                )
                if scaled_h is not None and 0.0 <= scaled_h < h_max_kN:
                    h_max_kN = scaled_h
                    governing_limit_id = limit_key
                continue
            if entity_id in point.sensitivity_reactions:
                magnitude_h = _magnitude_candidate(
                    doc, point, entity_id, component, float(limit_kN), tolerance
                )
                if magnitude_h is not None:
                    if 0.0 <= magnitude_h < h_max_kN:
                        h_max_kN = magnitude_h
                        governing_limit_id = limit_key
                    continue
                linear = resolve_connection_component_linear_response(point, entity_id, component)
                if linear is None:
                    continue
                baseline, sens = linear
            elif rope_channel in point.sensitivity_rope_tensions:
                sens = point.sensitivity_rope_tensions.get(rope_channel, 0.0)
                baseline = point.baseline_rope_tensions.get(rope_channel, 0.0)
            else:
                continue

            if baseline > limit_kN:
                h_candidate = 0.0  # already exceeded with no hook load
            elif abs(sens) > tolerance:
                h_candidate = (limit_kN - baseline) / sens
            else:
                continue
            if 0.0 <= h_candidate < h_max_kN:
                h_max_kN = h_candidate
                governing_limit_id = limit_key

    # No limit yields a candidate: the hook load is unlimited (inf), not 1000 kN.

    # Convert hook force to payload with the dynamic factor (removes the factor, converts
    # force to mass and subtracts the hook mass).
    h_max_kN = max(0.0, h_max_kN)
    h_net_payload_t = as_dynamic_factor(hook_daf).payload_t(h_max_kN, lower_block_mass_t, gravity)
    h_net_payload_t = max(0.0, h_net_payload_t)
    # Metric domain semantics:
    #   h_max_kN = hook-force domain (includes DAF & hook mass effects)
    #   h_net_payload_t = payload domain (net mass after subtracting hook mass)

    return AllowableCapacity(
        max_allowable_load_kN=h_max_kN,
        max_allowable_load_t=h_net_payload_t,
        governing_limit_id=governing_limit_id,
        governing_wind_direction=point.governing_wind_direction,
        margin_kN=max(0.0, h_max_kN),
    )
