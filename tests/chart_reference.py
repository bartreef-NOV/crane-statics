"""Brute-force load-chart reference (test only, slow by design).

Minimises ``compute_allowable_load`` over every vessel-motion sign case, slew angle, wind
angle and lead sign case, so the fast envelope can be checked against it.
"""

from __future__ import annotations

import itertools
from typing import Any, Sequence

from crane_statics.calculation.engine import AllowableCapacity, CraneCalculator
from crane_statics.core.analysis_cases import _signed_candidates
from crane_statics.core.lead_channels import compose_lead_channel_point
from crane_statics.core.load_condition import scene_case
from crane_statics.core.vessel_envelope import vessel_motion_cases
from crane_statics.data.models import CraneDocument

_WIND_ZERO = 1e-9


def _angles(step_deg: float) -> list[float]:
    count = int(round(360.0 / step_deg))
    return [i * step_deg for i in range(count)]


def reference_capacity(
    calc: CraneCalculator,
    doc: CraneDocument,
    hoist_id: str,
    angle_deg: float,
    limits: dict[str, dict],
    *,
    hook_daf: float,
    lower_block_mass_t: float,
    overrides: dict[str, dict[str, Any]] | None,
    slew_step_deg: float = 15.0,
    wind_step_deg: float = 15.0,
    condition_name: str | None = None,
) -> AllowableCapacity:
    """Worst-case allowable capacity found by exhaustive enumeration."""
    return reference_capacities(
        calc,
        doc,
        hoist_id,
        angle_deg,
        [limits],
        hook_daf=hook_daf,
        lower_block_mass_t=lower_block_mass_t,
        overrides=overrides,
        slew_step_deg=slew_step_deg,
        wind_step_deg=wind_step_deg,
        condition_name=condition_name,
    )[0]


def reference_capacities(
    calc: CraneCalculator,
    doc: CraneDocument,
    hoist_id: str,
    angle_deg: float,
    limit_sets: Sequence[dict[str, dict]],
    *,
    hook_daf: float,
    lower_block_mass_t: float,
    overrides: dict[str, dict[str, Any]] | None,
    slew_step_deg: float = 15.0,
    wind_step_deg: float = 15.0,
    condition_name: str | None = None,
) -> list[AllowableCapacity]:
    """``reference_capacity`` for several limit sets, sharing one enumeration of solves.

    The wind speed, vessel motion and lead limits are those of ``doc``'s condition
    ``condition_name`` (None: the first); ``calc`` should be built for that case.
    """
    # The wind, vessel motion and lead limits of the Scene's case of ``condition_name``.
    case = scene_case(doc, condition_name)
    settings = case.hoist_settings(hoist_id)
    offlead = float(settings.offlead_deg)
    sidelead = float(settings.sidelead_deg)
    wind_speed = float(case.wind_speed_m_s)
    wind_angles = [0.0] if abs(wind_speed) < _WIND_ZERO else _angles(wind_step_deg)
    lead_cases = list(itertools.product(_signed_candidates(offlead), _signed_candidates(sidelead)))

    best: list[AllowableCapacity | None] = [None] * len(limit_sets)
    for motion in vessel_motion_cases(case.vessel_motion):
        for slew in _angles(slew_step_deg):
            for wind_angle in wind_angles:
                pt = calc.compute_analysis_point(
                    angle_deg,
                    0.0,
                    hoist_id,
                    wind_speed_m_s=wind_speed,
                    wind_angle_deg=wind_angle,
                    crane_slewing_angle_deg=slew,
                    hoist_runtime_overrides=overrides,
                    # Zero-lead point: the signed leads are composed below.
                    offlead_deg=0.0,
                    sidelead_deg=0.0,
                    **motion,
                )
                if pt is None:
                    continue
                for off, side in lead_cases:
                    lead_pt = compose_lead_channel_point(pt, off, side)
                    for index, limits in enumerate(limit_sets):
                        cap = calc.compute_allowable_load(
                            lead_pt,
                            limits,
                            hook_daf=hook_daf,
                            lower_block_mass_t=lower_block_mass_t,
                        )
                        current = best[index]
                        if (
                            current is None
                            or cap.max_allowable_load_kN < current.max_allowable_load_kN
                        ):
                            best[index] = cap
    results = [cap for cap in best if cap is not None]
    if len(results) != len(limit_sets):
        raise ValueError("no analysis point could be computed")
    return results
