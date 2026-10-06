"""Compose analysis points from their per-unit lateral channels without re-solving.

An ``AnalysisPoint`` is linear in every lateral input, and carries the response
to one unit of each:

- hook lateral loads -- ``offlead_lateral_unit_*`` (+X at the sheave) and
  ``sidelead_lateral_unit_reactions`` (+Y at the sheave), per kN of lateral
  force per kN of hook load;
- lateral gravity -- ``gravity_lateral_x_unit_*`` and
  ``gravity_lateral_y_unit_reactions``, per unit of the crane-frame gravity
  fraction (see ``vessel_attitude``).

So a lead case or a different slew is a weighted sum of maps. Composition
always returns new maps; the source point is never modified.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from .vessel_attitude import CraneFrameGravity, normalize_slew_deg

if TYPE_CHECKING:
    from .engine import AnalysisPoint

FlatMap = Mapping[str, float]
NestedMap = Mapping[str, Mapping[str, float]]


def _sum_flat(base: FlatMap, terms: Sequence[tuple[float, Optional[FlatMap]]]) -> dict[str, float]:
    out = {key: float(value) for key, value in base.items()}
    for scale, channel in terms:
        if scale == 0.0 or not channel:
            continue
        for key, value in channel.items():
            out[key] = out.get(key, 0.0) + scale * float(value)
    return out


def _sum_nested(
    base: NestedMap, terms: Sequence[tuple[float, Optional[NestedMap]]]
) -> dict[str, dict[str, float]]:
    out = {entity: dict(components) for entity, components in base.items()}
    for scale, channel in terms:
        if scale == 0.0 or not channel:
            continue
        for entity, components in channel.items():
            target = out.setdefault(entity, {})
            for component, value in components.items():
                target[component] = target.get(component, 0.0) + scale * float(value)
    return out


def compose_lateral_channels(
    point: "AnalysisPoint",
    *,
    hook_x: float = 0.0,
    hook_y: float = 0.0,
    gravity_x: float = 0.0,
    gravity_y: float = 0.0,
) -> "AnalysisPoint":
    """Add lateral unit channels to a point at the given scales.

    ``hook_x``/``hook_y`` add lateral hook force per kN of hook load to the
    sensitivities; ``gravity_x``/``gravity_y`` add lateral gravity fractions to
    the baselines.
    """
    return replace(
        point,
        baseline_rope_tensions=_sum_flat(
            point.baseline_rope_tensions,
            [(gravity_x, point.gravity_lateral_x_unit_rope_tensions)],
        ),
        baseline_reactions=_sum_nested(
            point.baseline_reactions,
            [
                (gravity_x, point.gravity_lateral_x_unit_reactions),
                (gravity_y, point.gravity_lateral_y_unit_reactions),
            ],
        ),
        sensitivity_rope_tensions=_sum_flat(
            point.sensitivity_rope_tensions,
            [(hook_x, point.offlead_lateral_unit_rope_tensions)],
        ),
        sensitivity_reactions=_sum_nested(
            point.sensitivity_reactions,
            [
                (hook_x, point.offlead_lateral_unit_reactions),
                (hook_y, point.sidelead_lateral_unit_reactions),
            ],
        ),
    )


def with_crane_gravity(
    point: "AnalysisPoint", gravity: CraneFrameGravity, *, slew_deg: float
) -> "AnalysisPoint":
    """Move a point to another gravity direction (another slew on the same vessel).

    The hook hangs plumb, so its load tilts with gravity: the lateral gravity
    fractions are also lateral hook-force fractions. The vertical fraction is
    fixed by heel and trim and already solved into the point.
    """
    d_x = gravity.lateral_x - point.crane_gravity.lateral_x
    d_y = gravity.lateral_y - point.crane_gravity.lateral_y
    moved = point
    if d_x != 0.0 or d_y != 0.0:
        moved = compose_lateral_channels(
            point, hook_x=d_x, hook_y=d_y, gravity_x=d_x, gravity_y=d_y
        )
    return replace(moved, crane_gravity=gravity, slew_deg=normalize_slew_deg(slew_deg))
