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
    """Sign-agnostic values (case 3: Y wind, roll, sidelead).

    Captured before the sign change; fradial, mradial and the bearing line loads were
    re-baselined in the wind-scaling task because the example's boom-local area_v_m2 is no
    longer multiplied by |sin(boom angle)| for Y wind. The resultant is unchanged.
    """
    calc = _calc()
    point = _platform(
        calc, wind_speed_m_s=15.0, wind_direction="+Y", vessel_roll_deg=3.0, sidelead_deg=4.5
    )
    expected = {
        "resultant": 25813.675823060286,
        "fradial": 1080.0615734455357,
        "mradial": 754713.2826163806,
        "max_bearing_line_load": 969147.5445772843,
        "min_bearing_line_load": 952714.048150837,
    }
    for component, value in expected.items():
        got = extract_connection_component_response(point, 1000.0, "platform_base", component)
        assert got == pytest.approx(value, rel=1e-9), component


GROUPS = (
    ("heel_left", "heel_right", "heel_point"),
    ("front_leg_left", "front_leg_right", "front_hinge"),
    ("rear_leg_left", "rear_leg_right", "rear_hinge"),
)


def _calc_with_mass_at_y(y: float) -> CraneCalculator:
    doc = load_document(EXAMPLE_22689)
    platform_body = next(b for b in doc.bodies if b.id == "platform")
    platform_body.mass_points.append(MassPoint(id="probe", mass_t=50.0, x_m=5.0, y_m=y, z_m=10.0))
    return CraneCalculator(doc)


@pytest.mark.parametrize("y", [5.0, -5.0])
def test_heel_left_carries_more_when_mass_is_to_port(y):
    # Compare against the same crane with the mass on the centreline so only the lateral
    # offset is being measured.
    centred = _platform(_calc_with_mass_at_y(0.0))
    offset = _platform(_calc_with_mass_at_y(y))
    for left, right, _total in GROUPS:
        d_left = offset.baseline_reactions[left]["Fz"] - centred.baseline_reactions[left]["Fz"]
        d_right = offset.baseline_reactions[right]["Fz"] - centred.baseline_reactions[right]["Fz"]
        if y > 0.0:  # port
            assert d_left > d_right, left
        else:
            assert d_right > d_left, right


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"accel_y_m_s2": 1.0},
        {"accel_x_m_s2": 1.0, "crane_slewing_angle_deg": 90.0},
        {"vessel_roll_deg": 5.0},
        {"wind_speed_m_s": 20.0, "wind_direction": "+Y"},
        {"wind_speed_m_s": 20.0, "wind_direction": "+X", "sidelead_deg": 4.5},
    ],
)
def test_left_right_sum_to_total(overrides):
    point = _platform(_calc(), **overrides)
    for left, right, total in GROUPS:
        for comp in ("Fx", "Fz"):
            pair = point.baseline_reactions[left][comp] + point.baseline_reactions[right][comp]
            assert pair == pytest.approx(point.baseline_reactions[total][comp], abs=1e-6)
            sens = point.sensitivity_reactions
            pair_s = sens[left].get(comp, 0.0) + sens[right].get(comp, 0.0)
            assert pair_s == pytest.approx(sens[total].get(comp, 0.0), abs=1e-6)


def test_reaction_arrows_sit_on_the_matching_side():
    """Arrows are drawn from the XZ group totals (no y position); only the table labels
    carry a side, and they must pair the entity with the name it is called."""
    from crane_statics.core.drawn_loads import REACTION_SPECS
    from crane_statics.presentation.formatters import ConnectionFormatter

    assert not [e for e in REACTION_SPECS if e.endswith(("_left", "_right"))]
    assert ConnectionFormatter.child_display_name("heel_left") == "Left"
    assert ConnectionFormatter.child_display_name("heel_right") == "Right"
    assert ConnectionFormatter.display_name("heel_left") == "Heel Left"
    assert ConnectionFormatter.display_name("heel_right") == "Heel Right"


# --- Wind scaling parity -------------------------------------------------------------------

RHO = 1.225


def _doc_with_single_wind_area(body_id: str, **area_kwargs):
    from crane_statics.data.models import WindArea

    doc = load_document(EXAMPLE_22689).model_copy(deep=True)
    for body in doc.bodies:
        body.wind_areas = []
    body = next(b for b in doc.bodies if b.id == body_id)
    body.wind_areas.append(WindArea(id="probe", cd=1.3, **area_kwargs))
    doc.environment.air_density_kg_m3 = RHO
    return doc


@pytest.mark.parametrize("angle", [30.0, 75.0])
def test_y_wind_on_boom_does_not_scale_with_boom_angle(angle):
    doc = _doc_with_single_wind_area(
        "boom", area_w_m2=40.0, area_v_m2=25.0, x_m=0.0, z_m=0.0, local_x_m=20.0, local_z_m=0.0
    )
    calc = CraneCalculator(doc)
    geometry = calc._out_of_plane_geometry(angle, ())
    speed = 15.0
    total_kN = float(geometry.wind_coef.sum()) * speed**2
    assert total_kN == pytest.approx(0.5 * RHO * 1.3 * 25.0 * speed**2 / 1000.0, rel=1e-12)


@pytest.mark.parametrize("angle", [30.0, 60.0])
def test_x_wind_boom_areas_scale_in_arrow_and_solver_alike(angle):
    from crane_statics.core import drawn_loads as dl
    from tests.test_acceptance import scene_inputs_at_drawn_tackle

    # Boom-body wind area given in global coordinates (not boom-local).
    doc = _doc_with_single_wind_area("boom", area_w_m2=40.0, area_v_m2=25.0, x_m=10.0, z_m=15.0)
    speed = 20.0
    inputs = scene_inputs_at_drawn_tackle(
        doc, doc.hoists[0].id, angle=angle, wind_speed_m_s=speed, wind_direction="+X"
    )
    loads = inputs.body_loads(inputs.node_positions(), "boom")
    arrows = loads.category(dl.WIND)
    assert len(arrows) == 1
    expected = 0.5 * RHO * 1.3 * 40.0 * abs(math.sin(math.radians(angle))) * speed**2 / 1000.0
    assert arrows[0].fx_kN == pytest.approx(expected, rel=1e-12)

    # Solver: the only wind load is this area, so the change in the platform-base reaction
    # (a reaction is minus the applied load) is the solver wind Fx.
    calc = CraneCalculator(doc)
    windy = _platform_at(calc, angle, wind_speed_m_s=speed)
    calm = _platform_at(calc, angle, wind_speed_m_s=0.0)
    solver_fx = -(
        windy.baseline_reactions["platform_base"]["Fx"]
        - calm.baseline_reactions["platform_base"]["Fx"]
    )
    assert solver_fx == pytest.approx(arrows[0].fx_kN, rel=1e-9)


def _platform_at(calc, angle, **overrides):
    point = calc.compute_analysis_point(angle, 0.0, "MH", **{**LEVEL, **overrides})
    assert point is not None
    return point


@pytest.mark.parametrize("angle", [0.0, 90.0])
@pytest.mark.parametrize("direction", ["+X", "+Y"])
def test_wind_speed_zero_gives_zero_and_no_error(angle, direction):
    doc = _doc_with_single_wind_area(
        "boom", area_w_m2=40.0, area_v_m2=25.0, x_m=0.0, z_m=0.0, local_x_m=20.0, local_z_m=0.0
    )
    calc = CraneCalculator(doc)
    still = _platform_at(calc, angle, wind_speed_m_s=0.0, wind_direction=direction)
    base = _platform_at(calc, angle, wind_speed_m_s=0.0, wind_direction="+X")
    assert still.baseline_reactions["platform_base"]["Fy"] == pytest.approx(0.0, abs=1e-9)
    assert still.baseline_reactions["platform_base"]["Mx"] == pytest.approx(
        base.baseline_reactions["platform_base"]["Mx"], abs=1e-9
    )
    windy = _platform_at(calc, angle, wind_speed_m_s=10.0, wind_direction=direction)
    assert windy is not None


# --- Task 4: near-singular statics fail clearly, with a reason -----------------------------

EXAMPLES = sorted((ROOT / "examples").glob("*.yaml"))


def test_is_ill_conditioned_flags_singular_and_near_singular():
    import numpy as np

    from crane_statics.calculation.solver.crane_solver import is_ill_conditioned

    assert not is_ill_conditioned(np.eye(3))
    assert is_ill_conditioned(np.array([[1.0, 2.0], [1.0, 2.0]]))
    assert is_ill_conditioned(np.array([[1.0, 2.0], [1.0, 2.0 + 1e-15]]))
    assert is_ill_conditioned(np.array([[1.0, 0.0], [0.0, 0.0]]))


def _angle_span(calc, hoist):
    kin = calc._kinematics
    angles = [
        kin.outreach_to_angle(hoist.outreach_min_m or 0.0, hoist.id),
        kin.outreach_to_angle(hoist.outreach_max_m or 200.0, hoist.id),
    ]
    lo, hi = (0.0, 90.0) if None in angles else (min(angles), max(angles))
    return [lo + (hi - lo) * i / 9 for i in range(10)]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_all_examples_still_solve(path):
    calc = CraneCalculator(load_document(path))
    for hoist in calc.doc.hoists:
        for angle in [0.0, *_angle_span(calc, hoist)]:
            point = calc.compute_analysis_point(angle, 0.0, hoist.id)
            assert point is not None, (hoist.id, angle)
            assert calc.unavailable_reason is None


def _collapsed_calc() -> CraneCalculator:
    doc = load_document(EXAMPLE_22689)
    nodes = {n.id: n for n in doc.nodes}
    for name in ("x_m", "z_m"):
        setattr(nodes["front_base"], name, getattr(nodes["rear_base"], name))
        setattr(nodes["front_top"], name, getattr(nodes["rear_top"], name))
    return CraneCalculator(doc)


def test_collapsed_geometry_reports_reason():
    calc = _collapsed_calc()
    assert calc.compute_analysis_point(45.0, 0.0, "MH") is None
    reason = calc.unavailable_reason
    assert reason is not None and "singular" in reason
    assert "boom" in reason or "leg frame" in reason


def test_unavailable_reason_resets_on_next_call():
    calc = _collapsed_calc()
    assert calc.compute_analysis_point(45.0, 0.0, "MH") is None
    assert calc.unavailable_reason is not None
    good = _calc()
    good.unavailable_reason = "stale"
    assert good.compute_analysis_point(45.0, 0.0, "MH") is not None
    assert good.unavailable_reason is None


def test_chart_sweep_skips_unsolvable_points(monkeypatch):
    from crane_statics.calculation.solver import crane_solver
    from crane_statics.core.chart_envelope import build_probes

    real = crane_solver.is_ill_conditioned
    state = {"bad": False}
    monkeypatch.setattr(crane_solver, "is_ill_conditioned", lambda m: state["bad"] or real(m))
    calc = _calc()
    results = []
    for angle in (20.0, 30.0, 40.0, 50.0):
        state["bad"] = angle == 40.0
        results.append(build_probes(calc, "MH", angle, 0.0, None))
    assert [r is None for r in results] == [False, False, True, False]
    assert _collapsed_calc().compute_analysis_point(45.0, 0.0, "MH") is None
    assert build_probes(_collapsed_calc(), "MH", 45.0, 0.0, None) is None
