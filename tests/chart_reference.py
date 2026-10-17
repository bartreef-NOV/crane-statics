"""Brute-force load-chart reference (test only, slow by design).

Minimises ``compute_allowable_load`` over every vessel-motion sign case, slew angle, wind
angle and lead sign case, so the fast envelope can be checked against it.
"""

from __future__ import annotations

import itertools
from typing import Any

from crane_statics.calculation.engine import AllowableCapacity, CraneCalculator
from crane_statics.core.analysis_cases import _signed_candidates
from crane_statics.core.lead_channels import compose_lead_channel_point
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
    hook_mass_t: float,
    overrides: dict[str, dict[str, Any]] | None,
    slew_step_deg: float = 15.0,
    wind_step_deg: float = 15.0,
) -> AllowableCapacity:
    """Worst-case allowable capacity found by exhaustive enumeration."""
    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    offlead = float(getattr(hoist, "offlead_deg", 0.0))
    sidelead = float(getattr(hoist, "sidelead_deg", offlead))
    wind_speed = float(doc.environment.max_wind_speed_m_s)
    wind_angles = [0.0] if abs(wind_speed) < _WIND_ZERO else _angles(wind_step_deg)
    lead_cases = list(itertools.product(_signed_candidates(offlead), _signed_candidates(sidelead)))

    best: AllowableCapacity | None = None
    for motion in vessel_motion_cases(doc.environment.vessel_motion):
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
                    **motion,
                )
                if pt is None:
                    continue
                for off, side in lead_cases:
                    cap = calc.compute_allowable_load(
                        compose_lead_channel_point(pt, off, side),
                        limits,
                        hook_daf=hook_daf,
                        hook_mass_t=hook_mass_t,
                    )
                    if best is None or cap.max_allowable_load_kN < best.max_allowable_load_kN:
                        best = cap
    if best is None:
        raise ValueError("no analysis point could be computed")
    return best
