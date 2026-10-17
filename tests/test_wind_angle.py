"""Wind from an arbitrary angle (degrees from +X toward +Y) in the engine."""

from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
WIND = 20.0


@pytest.fixture(scope="module")
def calc():
    return CraneCalculator(load_document(EXAMPLE))


def _point(calc, **kwargs):
    p = calc.compute_analysis_point(boom_angle_deg=45.0, hook_load_kN=0.0, hoist_id="MH", **kwargs)
    assert p is not None
    return p


def _flat(reactions):
    return {(e, k): v for e, comps in reactions.items() for k, v in comps.items()}


@pytest.mark.parametrize("angle,direction", [(0, "+X"), (90, "+Y"), (180, "-X"), (270, "-Y")])
def test_axis_wind_angles_match_direction_strings(calc, angle, direction):
    by_angle = _point(calc, wind_speed_m_s=WIND, wind_angle_deg=float(angle))
    by_dir = _point(calc, wind_speed_m_s=WIND, wind_direction=direction)
    a, b = _flat(by_angle.baseline_reactions), _flat(by_dir.baseline_reactions)
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == pytest.approx(b[key], rel=1e-12, abs=1e-12)
    ta, tb = by_angle.baseline_rope_tensions, by_dir.baseline_rope_tensions
    assert ta.keys() == tb.keys()
    for key in ta:
        assert ta[key] == pytest.approx(tb[key], rel=1e-12, abs=1e-12)


def test_oblique_wind_is_the_sum_of_half_axis_effects(calc):
    zero = _flat(_point(calc, wind_speed_m_s=0.0).baseline_reactions)
    p0 = _flat(_point(calc, wind_speed_m_s=WIND, wind_angle_deg=0.0).baseline_reactions)
    p90 = _flat(_point(calc, wind_speed_m_s=WIND, wind_angle_deg=90.0).baseline_reactions)
    p45 = _flat(_point(calc, wind_speed_m_s=WIND, wind_angle_deg=45.0).baseline_reactions)
    assert any(abs(p0[k] - zero[k]) > 1e-6 for k in zero)
    assert any(abs(p90[k] - zero[k]) > 1e-6 for k in zero)
    for key, z in zero.items():
        expected = z + 0.5 * (p0[key] - z) + 0.5 * (p90[key] - z)
        assert p45[key] == pytest.approx(expected, rel=1e-9, abs=1e-9)
