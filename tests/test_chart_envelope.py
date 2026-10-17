"""Load-chart envelope: probe solves superpose to any vessel-motion / slew / wind case."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.engine import AnalysisPoint, CraneCalculator
from crane_statics.calculation.vessel_frame import VesselInputs
from crane_statics.core import load_document
from crane_statics.core.chart_envelope import build_probes, motion_channels, superpose
from crane_statics.data.models import CraneDocument

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
BOOM_ANGLE_DEG = 45.0
HOIST = "MH"
# Model vessel-motion limits, all nonzero (engine keyword -> limit).
LIMITS = {
    "accel_x_m_s2": 0.8,
    "accel_y_m_s2": 0.6,
    "accel_z_m_s2": 1.1,
    "roll_accel_rad_s2": 0.05,
    "pitch_accel_rad_s2": 0.03,
    "vessel_roll_deg": 4.0,
    "vessel_pitch_deg": 2.5,
}
CASES = 20


def _document(*, offset_boom_mass: bool) -> CraneDocument:
    doc = load_document(EXAMPLE)
    vm = doc.environment.vessel_motion
    vm.accel_x_m_s2 = LIMITS["accel_x_m_s2"]
    vm.accel_y_m_s2 = LIMITS["accel_y_m_s2"]
    vm.accel_z_m_s2 = LIMITS["accel_z_m_s2"]
    vm.roll_angular_accel_rad_s2 = LIMITS["roll_accel_rad_s2"]
    vm.pitch_angular_accel_rad_s2 = LIMITS["pitch_accel_rad_s2"]
    vm.roll_deg = LIMITS["vessel_roll_deg"]
    vm.pitch_deg = LIMITS["vessel_pitch_deg"]
    vm.reference_x_m = 3.0
    vm.reference_z_m = -2.0
    if offset_boom_mass:
        boom = next(b for b in doc.bodies if b.id == "boom")
        mp = boom.mass_points[0]
        mp.y_m = 1.7
        if mp.local_x_m is not None:
            mp.local_y_m = 1.7
    return doc


def _cases(seed: int) -> list[tuple[dict[str, Any], float, float]]:
    rng = random.Random(seed)
    cases = []
    for _ in range(CASES):
        motion = {k: rng.choice((-1.0, 1.0)) * v for k, v in LIMITS.items()}
        cases.append((motion, rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0)))
    return cases


def _flat(point: AnalysisPoint) -> dict[tuple[str, str], float]:
    flat = {("rope", r): float(v) for r, v in point.baseline_rope_tensions.items()}
    for entity, comps in point.baseline_reactions.items():
        for comp, value in comps.items():
            flat[(entity, comp)] = float(value)
    return flat


def _vessel_inputs(motion: dict[str, float], slew_deg: float) -> VesselInputs:
    return VesselInputs(
        accel_x_m_s2=motion["accel_x_m_s2"],
        accel_y_m_s2=motion["accel_y_m_s2"],
        accel_z_m_s2=motion["accel_z_m_s2"],
        roll_deg=motion["vessel_roll_deg"],
        pitch_deg=motion["vessel_pitch_deg"],
        slew_deg=slew_deg,
        roll_accel_rad_s2=motion["roll_accel_rad_s2"],
        pitch_accel_rad_s2=motion["pitch_accel_rad_s2"],
    )


def _wind_scales(angle_deg: float) -> tuple[float, float]:
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return c * abs(c), s * abs(s)


@pytest.mark.parametrize("offset_boom_mass", [False, True], ids=["example", "boom_mass_y"])
@pytest.mark.parametrize("wind_speed", [None, 20.0], ids=["document_wind", "wind_20"])
def test_superposition_matches_direct_solve(
    offset_boom_mass: bool, wind_speed: float | None
) -> None:
    doc = _document(offset_boom_mass=offset_boom_mass)
    calc = CraneCalculator(doc)
    speed = float(doc.environment.max_wind_speed_m_s if wind_speed is None else wind_speed)
    gravity = abs(float(doc.environment.gravity_m_s2))
    overrides: dict[str, dict[str, Any]] | None = None
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, speed, overrides)
    assert probes is not None

    for motion, slew, wind_angle in _cases(seed=5):
        direct = calc.compute_analysis_point(
            BOOM_ANGLE_DEG,
            0.0,
            HOIST,
            wind_speed_m_s=speed,
            wind_angle_deg=wind_angle,
            crane_slewing_angle_deg=slew,
            hoist_runtime_overrides=overrides,
            **motion,
        )
        assert direct is not None
        wx, wy = _wind_scales(wind_angle)
        got = superpose(probes, motion_channels(gravity, _vessel_inputs(motion, slew)), wx, wy)

        expected_flat, got_flat = _flat(direct), _flat(got)
        assert set(got_flat) == set(expected_flat)
        for key, value in expected_flat.items():
            assert got_flat[key] == pytest.approx(value, rel=1e-9, abs=1e-9), (key, motion, slew)
        assert got.sensitivity_rope_tensions == probes.zero.sensitivity_rope_tensions
        assert got.sensitivity_reactions == probes.zero.sensitivity_reactions


def test_motion_channels_are_zero_for_zero_inputs() -> None:
    assert motion_channels(9.81, VesselInputs()).tolist() == [0.0] * 5


def test_motion_channels_on_a_level_vessel_are_the_inputs() -> None:
    inputs = VesselInputs(
        accel_x_m_s2=0.1,
        accel_y_m_s2=0.2,
        accel_z_m_s2=0.3,
        pitch_accel_rad_s2=0.4,
        roll_accel_rad_s2=0.5,
    )
    assert motion_channels(9.81, inputs).tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])


def test_zero_wind_probes_reuse_the_zero_point() -> None:
    calc = CraneCalculator(_document(offset_boom_mass=False))
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, 0.0, None)
    assert probes is not None
    assert probes.wind_x is probes.zero
    assert probes.wind_y is probes.zero


def test_unknown_hoist_gives_no_probes() -> None:
    calc = CraneCalculator(_document(offset_boom_mass=False))
    assert build_probes(calc, "nope", BOOM_ANGLE_DEG, 10.0, None) is None
