"""Compose a horizontal hook load from an analysis point's lateral unit responses.

The point carries the response to 1 kN at the hoist's support node along crane-frame +x
(``lateral_x_unit_reactions`` with ``offlead_lateral_unit_rope_tensions``) and +y
(``sidelead_lateral_unit_reactions``; an out-of-plane force leaves the ropes alone). A
lateral of ``fraction * H + force`` therefore adds ``fraction * unit`` to the sensitivity
and ``force * unit`` to the baseline. Off-lead, side-lead and ``HookLateral`` all use these
same units.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .results import AnalysisPoint, HookLateral

_WIND_ZERO = 1e-12


def wind_axis_weights(wind_x_m_s: float, wind_y_m_s: float) -> tuple[float, float]:
    """``(V_x|V_x|, V_y|V_y|) / V^2``: how much of an axis wind force a solve's wind gives.

    The structural wind scales the same way (force ~ signed squared speed per axis), so an
    axis wind gives +-1 on its axis and no wind gives nothing.
    """
    vx, vy = float(wind_x_m_s), float(wind_y_m_s)
    speed_sq = vx * vx + vy * vy
    if speed_sq <= _WIND_ZERO**2:
        return 0.0, 0.0
    return vx * abs(vx) / speed_sq, vy * abs(vy) / speed_sq


def _add(
    values: dict[str, float],
    unit_x: dict[str, float],
    unit_y: dict[str, float],
    sx: float,
    sy: float,
) -> dict[str, float]:
    out = dict(values)
    for key in set(unit_x) | set(unit_y):
        out[key] = (
            float(values.get(key, 0.0))
            + sx * float(unit_x.get(key, 0.0))
            + sy * float(unit_y.get(key, 0.0))
        )
    return out


def add_hook_lateral(
    point: AnalysisPoint,
    fraction_x: float,
    fraction_y: float,
    force_x_kN: float = 0.0,
    force_y_kN: float = 0.0,
) -> AnalysisPoint:
    """``point`` with a support-node lateral of ``fraction * H + force`` (crane frame).

    Returns ``point`` itself when every term is zero. The units are read from ``point``
    (``compute_analysis_point`` fills them for every point).
    """
    fx, fy = float(fraction_x), float(fraction_y)
    cx, cy = float(force_x_kN), float(force_y_kN)
    if fx == 0.0 and fy == 0.0 and cx == 0.0 and cy == 0.0:
        return point
    unit_x = point.lateral_x_unit_reactions or {}
    unit_y = point.sidelead_lateral_unit_reactions or {}
    unit_x_ropes = point.offlead_lateral_unit_rope_tensions or {}

    def _reactions(
        values: dict[str, dict[str, float]], sx: float, sy: float
    ) -> dict[str, dict[str, float]]:
        if sx == 0.0 and sy == 0.0:
            return values
        out = {entity: dict(comps) for entity, comps in values.items()}
        for entity in set(unit_x) | set(unit_y):
            out[entity] = _add(
                values.get(entity, {}), unit_x.get(entity, {}), unit_y.get(entity, {}), sx, sy
            )
        return out

    def _ropes(values: dict[str, float], sx: float) -> dict[str, float]:
        if sx == 0.0:
            return values
        return _add(values, unit_x_ropes, {}, sx, 0.0)

    return replace(
        point,
        baseline_reactions=_reactions(point.baseline_reactions, cx, cy),
        sensitivity_reactions=_reactions(point.sensitivity_reactions, fx, fy),
        baseline_rope_tensions=_ropes(point.baseline_rope_tensions, cx),
        sensitivity_rope_tensions=_ropes(point.sensitivity_rope_tensions, fx),
    )


def apply_hook_lateral(
    point: AnalysisPoint, lateral: HookLateral, wind_x_m_s: float, wind_y_m_s: float
) -> AnalysisPoint:
    """``point`` with ``lateral`` applied: floored fractions, wind-borne constants."""
    fx, fy = lateral.floored_fractions()
    wx, wy = wind_axis_weights(wind_x_m_s, wind_y_m_s)
    return add_hook_lateral(
        point, fx, fy, float(lateral.constant_x_kN) * wx, float(lateral.constant_y_kN) * wy
    )


def circumscribed_directions(radius: float, sides: int = 16) -> list[tuple[float, float]]:
    """Vertices of a regular ``sides``-gon circumscribing the circle of ``radius``.

    A demand convex in the lateral vector that holds at every vertex holds on the whole
    circle, so the worst vertex is never below the worst direction (and at most
    ``1/cos(pi/sides) - 1`` above it: 1.96 % for 16 sides).
    """
    if radius <= 0.0:
        return []
    outer = float(radius) / math.cos(math.pi / sides)
    return [
        (outer * math.cos(2.0 * math.pi * k / sides), outer * math.sin(2.0 * math.pi * k / sides))
        for k in range(sides)
    ]
