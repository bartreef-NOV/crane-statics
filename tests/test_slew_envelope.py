"""Load charts on a heeled/trimmed vessel: the worst case over every slew angle.

A chart point is the smallest capacity over the wind directions and over the
slew samples of ``vessel_attitude.envelope_slew_angles``; contractual verdicts
and rope/connection auto-set use the same envelope.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator, candidate_wind_directions
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.calculation.vessel_attitude import (
    VesselAttitude,
    crane_frame_gravity,
    envelope_slew_angles,
)
from crane_statics.core.io import load_document
from crane_statics.core.limit_auto_set import (
    compute_required_connection_capacity_kN,
    compute_required_rope_capacity_kN,
)
from crane_statics.core.sweep import run_capacity_sweep

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
LIMITS = {
    "BH__rope_T": {"T": 1100.0},
    "MH__rope_T": {"T": 1400.0},
    "heel_point_resultant": {"resultant": 30000.0},
    "heel_left_resultant": {"resultant": 16000.0},
    "platform_base_mradial": {"mradial": 1.0e6},
    "platform_base_fradial": {"fradial": 2000.0},
}
OUTREACH_STEP_M = 30.0


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


def _tilted(doc, heel_deg: float = 3.0, trim_deg: float = 1.0):
    tilted = doc.model_copy(deep=True)
    tilted.environment.vessel_motion.heel_deg = heel_deg
    tilted.environment.vessel_motion.trim_deg = trim_deg
    return tilted


def _curve(doc) -> list[tuple[float, float]]:
    return list(
        run_capacity_sweep(doc, "MH", LIMITS, OUTREACH_STEP_M, {})["modes"]["normal"]["curve_data"]
    )


def _capacity_t_at_slew(doc, outreach_m: float, slew_deg: float) -> float:
    """Chart capacity at one outreach for a crane held at one slew."""
    hoist = next(h for h in doc.hoists if h.id == "MH")
    calc = CraneCalculator(doc)
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach_m, "MH")
    assert angle is not None
    wind = float(doc.environment.max_wind_speed_m_s)
    capacities = []
    for direction in candidate_wind_directions(wind):
        point = calc.compute_analysis_point(
            angle, 0.0, "MH", wind_speed_m_s=wind, wind_direction=direction, slew_deg=slew_deg
        )
        assert point is not None
        cap = calc.compute_allowable_load(
            point, LIMITS, hook_daf=hoist.hook_daf, hook_mass_t=hoist.hook_mass_t
        )
        capacities.append(cap.max_allowable_load_t)
    return min(capacities)


class TestEnvelopePoints:
    def test_a_level_vessel_needs_one_point(self, document):
        calc = CraneCalculator(document)
        point = calc.compute_analysis_point(45.0, 0.0, "MH")

        assert calc.slew_envelope_points(point) == [point]

    def test_a_tilted_vessel_is_sampled_round_the_slew_ring(self, document):
        tilted = _tilted(document)
        calc = CraneCalculator(tilted)
        attitude = VesselAttitude(3.0, 1.0)

        points = calc.slew_envelope_points(calc.compute_analysis_point(45.0, 0.0, "MH"))

        assert [p.slew_deg for p in points] == pytest.approx(list(envelope_slew_angles(attitude)))
        for p in points:
            assert p.crane_gravity == crane_frame_gravity(attitude, p.slew_deg)


class TestChartEnvelope:
    def test_each_chart_point_is_the_worst_sampled_slew(self, document):
        tilted = _tilted(document)
        samples = envelope_slew_angles(VesselAttitude(3.0, 1.0))

        for outreach, capacity_t in _curve(tilted)[:4]:
            worst = min(_capacity_t_at_slew(tilted, outreach, slew) for slew in samples)
            assert capacity_t == pytest.approx(worst, rel=1e-9, abs=1e-9)

    def test_no_slew_between_samples_is_materially_worse(self, document):
        tilted = _tilted(document)

        for outreach, capacity_t in _curve(tilted)[:3]:
            for slew in (7.0, 101.0, 233.5, 318.0):
                assert capacity_t <= _capacity_t_at_slew(tilted, outreach, slew) * (1 + 2e-3) + 1e-6

    def test_the_envelope_depends_only_on_total_tilt(self, document):
        heel_only = _curve(_tilted(document, heel_deg=3.0, trim_deg=0.0))
        trim_only = _curve(_tilted(document, heel_deg=0.0, trim_deg=3.0))

        assert len(heel_only) == len(trim_only)
        for (x_h, y_h), (x_t, y_t) in zip(heel_only, trim_only):
            assert x_h == pytest.approx(x_t)
            assert y_h == pytest.approx(y_t, rel=1e-9, abs=1e-9)

    def test_tilt_changes_the_chart(self, document):
        level = _curve(document)
        tilted = _curve(_tilted(document))

        assert any(not math.isclose(a[1], b[1], rel_tol=1e-6) for a, b in zip(level, tilted))

    def test_contractual_verdicts_use_the_envelope(self, document):
        tilted = _tilted(document)
        mode = run_capacity_sweep(tilted, "MH", LIMITS, OUTREACH_STEP_M, {})["modes"]["normal"]
        samples = envelope_slew_angles(VesselAttitude(3.0, 1.0))

        cp, allowable_t, _passes = mode["contractual_results"][0]
        worst = min(_capacity_t_at_slew(tilted, float(cp.outreach_m), s) for s in samples)
        assert allowable_t == pytest.approx(worst, rel=1e-9, abs=1e-9)


class TestAutoSetEnvelope:
    def test_level_auto_set_reports_no_governing_slew(self, document):
        result = compute_required_rope_capacity_kN(document, "BH__rope")

        assert result.required_kN is not None
        assert result.governing_slew_deg is None

    def test_tilted_auto_set_sizes_the_boom_hoist_for_the_worst_slew(self, document):
        level = compute_required_rope_capacity_kN(document, "BH__rope")
        tilted = compute_required_rope_capacity_kN(_tilted(document), "BH__rope")

        assert tilted.required_kN is not None and level.required_kN is not None
        assert tilted.required_kN > level.required_kN
        assert tilted.governing_slew_deg in envelope_slew_angles(VesselAttitude(3.0, 1.0))

    def test_connection_auto_set_records_the_governing_slew(self, document):
        result = compute_required_connection_capacity_kN(_tilted(document), "heel_left", "Fz")

        assert result.required_kN is not None
        assert result.governing_slew_deg in envelope_slew_angles(VesselAttitude(3.0, 1.0))


class TestAllowableCapacityReportsTheSlew:
    def test_governing_slew_is_reported_on_a_tilted_vessel(self, document):
        tilted = _tilted(document)
        calc = CraneCalculator(tilted)
        point = calc.compute_analysis_point(45.0, 0.0, "MH", slew_deg=120.0)

        cap = calc.compute_allowable_load(point, LIMITS)

        assert cap.governing_slew_deg == pytest.approx(120.0)

    def test_no_slew_is_reported_on_a_level_vessel(self, document):
        calc = CraneCalculator(document)
        point = calc.compute_analysis_point(45.0, 0.0, "MH", slew_deg=120.0)

        assert calc.compute_allowable_load(point, LIMITS).governing_slew_deg is None
