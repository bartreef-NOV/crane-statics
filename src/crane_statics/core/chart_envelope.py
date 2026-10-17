"""Load-chart envelope by superposition of probe solves (pure, Qt-free).

An analysis point's baseline (rope tensions and reactions at zero hook load) is affine in
the crane-frame load channels: accel x, y, z, pitch accel, roll accel, and the squared-speed
wind components along crane X and Y. Eight probe solves per boom angle therefore let any
vessel-motion / slew / wind case be assembled arithmetically. The hook sensitivities and the
lead channels do not depend on motion or wind and are taken from the zero probe.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence

import numpy as np

from ..calculation.engine import AnalysisPoint, CraneCalculator
from ..calculation.vessel_frame import CraneFrameMotion, VesselInputs, crane_frame_motion

# Probe order for ``ProbeSet.motion`` and ``motion_channels``.
_PROBE_KWARGS = (
    "accel_x_m_s2",
    "accel_y_m_s2",
    "accel_z_m_s2",
    "pitch_accel_rad_s2",
    "roll_accel_rad_s2",
)
_PROBE_VALUE = 1.0
_WIND_ZERO = 1e-12


@dataclass(frozen=True)
class ProbeSet:
    """Probe solves at one boom angle; ``motion``: accel x, y, z, pitch accel, roll accel."""

    zero: AnalysisPoint
    motion: tuple[AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint]
    wind_x: AnalysisPoint
    wind_y: AnalysisPoint


def build_probes(
    calc: CraneCalculator,
    hoist_id: str,
    boom_angle_deg: float,
    wind_speed_m_s: float,
    overrides: Optional[dict[str, dict[str, Any]]],
) -> Optional[ProbeSet]:
    """Solve the zero, unit-motion and wind probes on a level vessel at slew 0.

    On a level vessel at slew 0 the vessel-frame inputs equal the crane-frame channels, so
    each motion probe sets one input to +1 (m/s² or rad/s²). Returns ``None`` if any probe
    fails; with zero wind speed the wind probes are the zero probe.
    """

    def _solve(
        wind_speed: float = 0.0, wind_angle: float = 0.0, **motion: float
    ) -> Optional[AnalysisPoint]:
        kwargs: dict[str, Any] = dict.fromkeys(_PROBE_KWARGS, 0.0)
        kwargs.update(motion)
        return calc.compute_analysis_point(
            boom_angle_deg,
            0.0,
            hoist_id,
            wind_speed_m_s=wind_speed,
            wind_angle_deg=wind_angle,
            hoist_runtime_overrides=overrides,
            crane_slewing_angle_deg=0.0,
            vessel_roll_deg=0.0,
            vessel_pitch_deg=0.0,
            **kwargs,
        )

    zero = _solve()
    if zero is None:
        return None
    motion = [_solve(**{name: _PROBE_VALUE}) for name in _PROBE_KWARGS]
    if abs(float(wind_speed_m_s)) <= _WIND_ZERO:
        wind_x: Optional[AnalysisPoint] = zero
        wind_y: Optional[AnalysisPoint] = zero
    else:
        wind_x = _solve(wind_speed=float(wind_speed_m_s), wind_angle=0.0)
        wind_y = _solve(wind_speed=float(wind_speed_m_s), wind_angle=90.0)
    m0, m1, m2, m3, m4 = motion
    if m0 is None or m1 is None or m2 is None or m3 is None or m4 is None:
        return None
    if wind_x is None or wind_y is None:
        return None
    return ProbeSet(zero=zero, motion=(m0, m1, m2, m3, m4), wind_x=wind_x, wind_y=wind_y)


def _channel_vector(motion: CraneFrameMotion) -> np.ndarray:
    return np.array(
        [
            motion.accel_x_m_s2,
            motion.accel_y_m_s2,
            motion.accel_z_m_s2,
            motion.pitch_accel_rad_s2,
            motion.roll_accel_rad_s2,
        ],
        dtype=float,
    )


def motion_channels(gravity: float, inputs: VesselInputs) -> np.ndarray:
    """Crane-frame channel deltas of ``inputs`` relative to all-zero inputs, shape (5,).

    Gravity tilt is folded in: a tilted vessel shows up as crane-frame acceleration.
    """
    return _channel_vector(crane_frame_motion(gravity, inputs)) - _channel_vector(
        crane_frame_motion(gravity, VesselInputs())
    )


def superpose(
    probes: ProbeSet,
    channels: Sequence[float],
    wind_x_scale: float,
    wind_y_scale: float,
) -> AnalysisPoint:
    """Assemble one case's baseline from the probes; sensitivities stay the zero point's."""
    zero = probes.zero
    terms = [(float(c), p) for c, p in zip(channels, probes.motion)]
    terms.append((float(wind_x_scale), probes.wind_x))
    terms.append((float(wind_y_scale), probes.wind_y))

    rope_ids = set(zero.baseline_rope_tensions)
    for _, p in terms:
        rope_ids |= set(p.baseline_rope_tensions)
    ropes: dict[str, float] = {}
    for rope_id in rope_ids:
        base = float(zero.baseline_rope_tensions.get(rope_id, 0.0))
        value = base
        for scale, p in terms:
            value += scale * (float(p.baseline_rope_tensions.get(rope_id, 0.0)) - base)
        ropes[rope_id] = value

    entity_ids = set(zero.baseline_reactions)
    for _, p in terms:
        entity_ids |= set(p.baseline_reactions)
    reactions: dict[str, dict[str, float]] = {}
    for entity_id in entity_ids:
        zero_comps = zero.baseline_reactions.get(entity_id, {})
        probe_comps = [(scale, p.baseline_reactions.get(entity_id, {})) for scale, p in terms]
        component_ids = set(zero_comps)
        for _, comps in probe_comps:
            component_ids |= set(comps)
        out: dict[str, float] = {}
        for component in component_ids:
            base = float(zero_comps.get(component, 0.0))
            value = base
            for scale, comps in probe_comps:
                value += scale * (float(comps.get(component, 0.0)) - base)
            out[component] = value
        reactions[entity_id] = out

    return replace(zero, baseline_rope_tensions=ropes, baseline_reactions=reactions)
