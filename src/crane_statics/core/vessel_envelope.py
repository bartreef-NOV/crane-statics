"""Vessel-motion limits as a ± envelope.

The Model's vessel motion values are limits: each input may take either sign up to its
magnitude. The load chart evaluates every sign combination and keeps the worst case; the
Scene clamps its inputs to the same ± range.
"""

from __future__ import annotations

import itertools
from typing import Any

from ..data.models import VesselMotion

# Surge, sway, heave, roll, pitch, roll angle, pitch angle:
# (VesselMotion field, SceneState field, compute_analysis_point keyword).
VESSEL_LIMIT_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("accel_x_m_s2", "accel_x_m_s2", "accel_x_m_s2"),
    ("accel_y_m_s2", "accel_y_m_s2", "accel_y_m_s2"),
    ("accel_z_m_s2", "accel_z_m_s2", "accel_z_m_s2"),
    ("roll_angular_accel_rad_s2", "roll_accel_rad_s2", "roll_accel_rad_s2"),
    ("pitch_angular_accel_rad_s2", "pitch_accel_rad_s2", "pitch_accel_rad_s2"),
    ("roll_deg", "vessel_roll_deg", "vessel_roll_deg"),
    ("pitch_deg", "vessel_pitch_deg", "vessel_pitch_deg"),
)

# SceneState field -> VesselMotion field holding its limit.
SCENE_FIELD_LIMITS: dict[str, str] = {scene: model for model, scene, _ in VESSEL_LIMIT_INPUTS}

_ZERO = 1e-12


def vessel_limit(motion: VesselMotion, field: str) -> float:
    """Magnitude of one vessel motion limit (the sign in the document is ignored)."""
    return abs(float(getattr(motion, field, 0.0) or 0.0))


def clamp_to_limit(value: float, limit: float) -> float:
    """Clamp ``value`` to ``[-limit, +limit]``."""
    return max(-limit, min(limit, float(value)))


def vessel_motion_cases(motion: VesselMotion) -> list[dict[str, Any]]:
    """Every ± combination of the vessel limits as ``compute_analysis_point`` keywords.

    A zero limit has one sign, so a document without vessel motion yields a single case.
    """
    options: list[tuple[str, tuple[float, ...]]] = []
    for field, _, keyword in VESSEL_LIMIT_INPUTS:
        limit = vessel_limit(motion, field)
        options.append((keyword, (limit,) if limit < _ZERO else (limit, -limit)))
    return [
        {keyword: value for (keyword, _), value in zip(options, combo)}
        for combo in itertools.product(*(values for _, values in options))
    ]
