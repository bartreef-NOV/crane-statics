"""App-consistency fixes: reaction sign convention.

Reactions are the force the support exerts on the crane; +Y points to port.
"""

import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core import load_document
from crane_statics.core.demand_extraction import extract_connection_component_response
from crane_statics.data.models import MassPoint
from tests.test_vessel_frame_engine import _all_point_masses

ROOT = Path(__file__).parent.parent
EXAMPLE_22689 = ROOT / "examples" / "crane_input_22689.yaml"
G = 9.81
LEVEL = {
    "wind_speed_m_s": 0.0,
    "wind_direction": "+X",
    "accel_x_m_s2": 0.0,
    "accel_y_m_s2": 0.0,
    "accel_z_m_s2": 0.0,
    "pitch_accel_rad_s2": 0.0,
    "roll_accel_rad_s2": 0.0,
    "vessel_roll_deg": 0.0,
    "vessel_pitch_deg": 0.0,
    "crane_slewing_angle_deg": 0.0,
    "offlead_deg": 0.0,
    "sidelead_deg": 0.0,
}


def _calc() -> CraneCalculator:
    return CraneCalculator(load_document(EXAMPLE_22689))


def _platform(calc, **overrides):
    point = calc.compute_analysis_point(45.0, 0.0, "MH", **{**LEVEL, **overrides})
    assert point is not None
    return point


def test_platform_base_fy_balances_y_loads():
    calc = _calc()
    point = _platform(calc, accel_y_m_s2=1.0)
    total_t = sum(m for m, _z in _all_point_masses(calc))
    # The support pushes +Y to accelerate the crane +Y.
    fy = point.baseline_reactions["platform_base"]["Fy"]
    assert fy > 0.0
    assert fy == pytest.approx(1.0 * total_t, abs=1e-6)


def test_platform_base_fy_positive_for_wind_toward_minus_y():
    calc = _calc()
    # Wind direction "-Y" pushes the crane toward -Y; the support reacts +Y.
    toward_minus_y = _platform(calc, wind_speed_m_s=20.0, wind_direction="-Y")
    toward_plus_y = _platform(calc, wind_speed_m_s=20.0, wind_direction="+Y")
    fy_minus = toward_minus_y.baseline_reactions["platform_base"]["Fy"]
    fy_plus = toward_plus_y.baseline_reactions["platform_base"]["Fy"]
    assert fy_minus > 0.0
    assert fy_plus == pytest.approx(-fy_minus)


def test_platform_base_mx_is_moment_balance():
    base_calc = _calc()
    doc = load_document(EXAMPLE_22689)
    mass_t, x, y, z = 10.0, 5.0, 3.0, 10.0
    platform_body = next(b for b in doc.bodies if b.id == "platform")
    platform_body.mass_points.append(MassPoint(id="probe", mass_t=mass_t, x_m=x, y_m=y, z_m=z))
    probe_calc = CraneCalculator(doc)

    accel_y = 1.0
    heel_z = float(probe_calc._kinematics.compute_all_node_positions(45.0)["platform_heel"]["z"])
    rel_z = z - heel_z
    fz_applied = -mass_t * G
    fy_applied = -mass_t * accel_y
    expected = -(y * fz_applied - rel_z * fy_applied)

    with_probe = _platform(probe_calc, accel_y_m_s2=accel_y)
    without = _platform(base_calc, accel_y_m_s2=accel_y)
    delta_mx = (
        with_probe.baseline_reactions["platform_base"]["Mx"]
        - without.baseline_reactions["platform_base"]["Mx"]
    )
    assert delta_mx == pytest.approx(expected, abs=1e-6)
    assert delta_mx > 0.0  # support pushes back against a mass sitting at +Y


def test_platform_base_sign_applies_to_hook_and_sidelead():
    calc = _calc()
    sidelead_deg, hook_kN = 4.5, 1000.0
    no_lead = _platform(calc)
    with_lead = _platform(calc, sidelead_deg=sidelead_deg)

    def fy_at(point, hook):
        pb = point.baseline_reactions["platform_base"]["Fy"]
        return pb + point.sensitivity_reactions["platform_base"]["Fy"] * hook

    assert fy_at(no_lead, hook_kN) == pytest.approx(0.0, abs=1e-6)
    side_force = hook_kN * math.sin(math.radians(sidelead_deg))
    # Sidelead pushes the crane toward +Y (the side-force unit response is +1 kN applied
    # at the sheave); the support reacts the other way.
    assert fy_at(with_lead, hook_kN) == pytest.approx(-side_force, rel=1e-6)
    unit = with_lead.sidelead_lateral_unit_reactions["platform_base"]["Fy"]
    assert unit == pytest.approx(-1.0)


def test_sign_agnostic_consumers_unchanged():
    """Values captured from the code before the sign change (case 3: Y wind, roll, sidelead)."""
    calc = _calc()
    point = _platform(
        calc, wind_speed_m_s=15.0, wind_direction="+Y", vessel_roll_deg=3.0, sidelead_deg=4.5
    )
    expected = {
        "resultant": 25813.675823060286,
        "fradial": 1106.7070878225763,
        "mradial": 754757.7929947668,
        "max_bearing_line_load": 969204.2169511968,
        "min_bearing_line_load": 952770.7205247495,
    }
    for component, value in expected.items():
        got = extract_connection_component_response(point, 1000.0, "platform_base", component)
        assert got == pytest.approx(value, rel=1e-9), component
