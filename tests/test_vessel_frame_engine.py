"""The engine drives crane loads from the vessel-frame motion (accelerations, tilt, slew).

The golden files were recorded on the commit before this change (e4eae55):

- ``gt283_mh_45deg.json``: wind 10 m/s +X, zero accelerations, level vessel, slew 0.
- ``gt283_mh_45deg_accel_no_idle.json``: as above plus accel_x 0.5, accel_z 0.3, pitch accel
  0.01, with the idle hook masses (AH, trolley) zeroed. Idle hook blocks used to feel gravity
  only; they now also feel the vessel accelerations, so a run that keeps them cannot reproduce
  the old numbers.
"""

import json
import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.solver import crane_solver
from crane_statics.core import load_document

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_GT283.yaml"
G = 9.81
SPLIT_SUFFIXES = ("_left", "_right")
OUT_OF_PLANE_PLATFORM = {"Fy", "Mx"}
NO_IDLE_HOOKS = {"AH": {"hook_mass_t": 0.0}, "trolley": {"hook_mass_t": 0.0}}


@pytest.fixture(scope="module")
def calc():
    return CraneCalculator(load_document(EXAMPLE))


def _point(calc, **kwargs):
    p = calc.compute_analysis_point(boom_angle_deg=45.0, hook_load_kN=0.0, hoist_id="MH", **kwargs)
    assert p is not None
    return p


def _flat(reactions):
    return {(e, k): v for e, comps in reactions.items() for k, v in comps.items()}


def _in_plane(reactions):
    """Reactions of the X-Z solve only (no left/right split, no platform Fy/Mx)."""
    return {
        (e, k): v
        for (e, k), v in _flat(reactions).items()
        if not e.endswith(SPLIT_SUFFIXES)
        and not (e == "platform_base" and k in OUT_OF_PLANE_PLATFORM)
    }


def _split_pair_sums(reactions):
    sums = {}
    for (e, k), v in _flat(reactions).items():
        for suffix in SPLIT_SUFFIXES:
            if e.endswith(suffix):
                key = (e[: -len(suffix)], k)
                sums[key] = sums.get(key, 0.0) + v
    return sums


def _golden(name):
    return json.loads((ROOT / "tests" / "golden" / name).read_text())


def test_level_vessel_inputs_reproduce_golden(calc):
    p = _point(
        calc,
        wind_speed_m_s=10.0,
        wind_direction="+X",
        accel_x_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_accel_rad_s2=0.0,
        vessel_roll_deg=0.0,
        vessel_pitch_deg=0.0,
        crane_slewing_angle_deg=0.0,
    )
    golden = _golden("gt283_mh_45deg.json")
    assert _flat(p.baseline_reactions) == pytest.approx(_flat(golden["baseline"]))
    assert _flat(p.sensitivity_reactions) == pytest.approx(_flat(golden["sensitivity"]))


def test_level_accelerations_reproduce_in_plane_golden_without_idle_hooks(calc):
    """Vessel-frame accelerations at slew 0 / level are the legacy crane-frame ones.

    The in-plane solve is unchanged. The left/right split now also feels accel_x and
    accel_z (it used to apply gravity only), so only the left+right sums are compared.
    """
    p = _point(
        calc,
        wind_speed_m_s=10.0,
        wind_direction="+X",
        accel_x_m_s2=0.5,
        accel_z_m_s2=0.3,
        pitch_accel_rad_s2=0.01,
        vessel_roll_deg=0.0,
        vessel_pitch_deg=0.0,
        crane_slewing_angle_deg=0.0,
        hoist_runtime_overrides=NO_IDLE_HOOKS,
    )
    golden = _golden("gt283_mh_45deg_accel_no_idle.json")
    assert _in_plane(p.baseline_reactions) == pytest.approx(_in_plane(golden["baseline"]))
    assert _in_plane(p.sensitivity_reactions) == pytest.approx(_in_plane(golden["sensitivity"]))
    assert _split_pair_sums(p.baseline_reactions) == pytest.approx(
        _split_pair_sums(golden["baseline"])
    )


def test_pitch_equals_equivalent_level_acceleration(calc):
    beta = math.radians(10.0)
    tilted = _point(calc, wind_speed_m_s=0.0, vessel_pitch_deg=10.0)
    equiv = _point(
        calc,
        wind_speed_m_s=0.0,
        accel_x_m_s2=-G * math.sin(beta),
        accel_z_m_s2=-G * (1.0 - math.cos(beta)),
    )
    assert _flat(tilted.baseline_reactions) == pytest.approx(_flat(equiv.baseline_reactions))


def test_pitch_changes_in_plane_reactions(calc):
    level = _point(calc, wind_speed_m_s=0.0)
    tilted = _point(calc, wind_speed_m_s=0.0, vessel_pitch_deg=10.0)
    assert _in_plane(tilted.baseline_reactions) != pytest.approx(
        _in_plane(level.baseline_reactions)
    )


@pytest.mark.parametrize(
    "extras",
    [
        pytest.param({}, id="mass-points-and-idle-hooks"),
        pytest.param(
            {
                "hoist_runtime_overrides": {"MH": {"support_comp_mass_t": 5.0}},
                "rope_mass_t_by_node": {"mh_boom_sheave_3": 2.0},
            },
            id="plus-support-comp-and-rope-mass",
        ),
    ],
)
def test_tilt_loads_every_mass_including_idle_hook(calc, extras):
    """Sum of body Fx under pitch beta == |sum of body Fz| at level * sin(beta).

    Holds only if every mass (mass points, idle hook mass, support-comp mass, rope mass) feels
    the tilt; a mass left on the scalar-gravity path breaks the identity. The active hook
    carries no mass here (hook load 0), and rope tensions are internal (every rope end sits on
    a body), so they cancel in the sums.
    """
    d = calc._doc_dict
    positions = calc._kinematics.compute_all_node_positions(45.0)
    node_pos = {n: (float(v["x"]), float(v["z"])) for n, v in positions.items()}
    body_map = {n["id"]: n.get("body", "") for n in d["nodes"]}
    beta = math.radians(10.0)
    level, _ = crane_solver._accumulate_loads(
        d, node_pos, body_map, "MH", 0.0, 0.0, 0.0, 0.0, boom_angle_deg=45.0, **extras
    )
    tilted, _ = crane_solver._accumulate_loads(
        d,
        node_pos,
        body_map,
        "MH",
        0.0,
        0.0,
        -G * math.sin(beta),
        -G * (1.0 - math.cos(beta)),
        boom_angle_deg=45.0,
        **extras,
    )
    total_fz_level = sum(b["Fz"] for b in level.values())
    total_fx_tilted = sum(b["Fx"] for b in tilted.values())
    total_fz_tilted = sum(b["Fz"] for b in tilted.values())
    assert total_fx_tilted == pytest.approx(abs(total_fz_level) * math.sin(beta))
    assert total_fz_tilted == pytest.approx(total_fz_level * math.cos(beta))


def test_slew_90_moves_vessel_ax_out_of_the_xz_solve(calc):
    level = _point(calc, wind_speed_m_s=0.0)
    at0 = _point(calc, wind_speed_m_s=0.0, accel_x_m_s2=1.0)
    at90 = _point(calc, wind_speed_m_s=0.0, accel_x_m_s2=1.0, crane_slewing_angle_deg=90.0)
    assert _in_plane(at90.baseline_reactions) == pytest.approx(_in_plane(level.baseline_reactions))
    assert _in_plane(at0.baseline_reactions) != pytest.approx(_in_plane(level.baseline_reactions))


def test_slew_90_vessel_ax_loads_the_left_right_supports(calc):
    level = _point(calc, wind_speed_m_s=0.0)
    at90 = _point(calc, wind_speed_m_s=0.0, accel_x_m_s2=1.0, crane_slewing_angle_deg=90.0)
    equiv = _point(calc, wind_speed_m_s=0.0, accel_y_m_s2=-1.0)
    for entity in ("heel_left", "heel_right", "front_leg_left", "rear_leg_right"):
        assert at90.baseline_reactions[entity]["Fx"] != pytest.approx(
            level.baseline_reactions[entity]["Fx"]
        )
    # Vessel +x at slew 90 is crane -y: every crane mass is pushed toward +y.
    assert at90.baseline_reactions["platform_base"]["Fy"] > 0.0
    assert _flat(at90.baseline_reactions) == pytest.approx(_flat(equiv.baseline_reactions))


def test_roll_tilts_gravity_into_the_left_right_supports(calc):
    gamma = math.radians(5.0)
    rolled = _point(calc, wind_speed_m_s=0.0, vessel_roll_deg=5.0)
    equiv = _point(
        calc,
        wind_speed_m_s=0.0,
        accel_y_m_s2=G * math.sin(gamma),
        accel_z_m_s2=-G * (1.0 - math.cos(gamma)),
    )
    assert _flat(rolled.baseline_reactions) == pytest.approx(_flat(equiv.baseline_reactions))
    # Roll to starboard pulls every mass toward starboard (crane -y at slew 0).
    assert rolled.baseline_reactions["platform_base"]["Fy"] < 0.0


def test_split_support_comp_mass_feels_the_acceleration(calc):
    overrides = {"MH": {"support_comp_mass_t": 10.0}}
    base = _point(calc, wind_speed_m_s=0.0, accel_y_m_s2=1.0)
    comp = _point(calc, wind_speed_m_s=0.0, accel_y_m_s2=1.0, hoist_runtime_overrides=overrides)
    # The comp mass sits on the support node (y = 0) and gets fy = -m * ay.
    assert comp.baseline_reactions["platform_base"]["Fy"] == pytest.approx(
        base.baseline_reactions["platform_base"]["Fy"] - 10.0 * 1.0
    )


def test_document_defaults_are_applied_as_signed_values():
    """With no kwargs the document vessel_motion is used as exact signed values (no envelope)."""
    doc = load_document(EXAMPLE)
    vm = doc.environment.vessel_motion
    vm.accel_x_m_s2 = -0.5
    vm.accel_z_m_s2 = 0.3
    vm.pitch_deg = 4.0
    vm.roll_deg = -3.0
    defaults_calc = CraneCalculator(doc)
    implicit = _point(defaults_calc)
    explicit = _point(
        CraneCalculator(load_document(EXAMPLE)),
        wind_speed_m_s=float(doc.environment.max_wind_speed_m_s),
        wind_direction="+X",
        accel_x_m_s2=-0.5,
        accel_z_m_s2=0.3,
        vessel_pitch_deg=4.0,
        vessel_roll_deg=-3.0,
    )
    assert _flat(implicit.baseline_reactions) == pytest.approx(_flat(explicit.baseline_reactions))
    assert implicit.governing_signs is not None
    assert implicit.governing_signs["accel_x"] != 0.0


def test_omnidirectional_capacity_forwards_vessel_kwargs(calc):
    limits = {"boom_hoist": {"T": 5000.0}, "heel_point": {"Fx": 50000.0}}
    slewed = calc.compute_omnidirectional_allowable_load(
        45.0, "MH", limits, wind_speed_m_s=0.0, accel_x_m_s2=-1.0, crane_slewing_angle_deg=180.0
    )
    equiv = calc.compute_omnidirectional_allowable_load(
        45.0, "MH", limits, wind_speed_m_s=0.0, accel_x_m_s2=1.0
    )
    plain = calc.compute_omnidirectional_allowable_load(
        45.0, "MH", limits, wind_speed_m_s=0.0, accel_x_m_s2=-1.0
    )
    assert slewed is not None and equiv is not None and plain is not None
    assert slewed.max_allowable_load_kN == pytest.approx(equiv.max_allowable_load_kN)
    assert slewed.max_allowable_load_kN != pytest.approx(plain.max_allowable_load_kN)


def _all_point_masses(calc):
    """Every mass the solve applies, as (mass_t, z): body mass points, idle hook blocks and
    rope self-weight (the latter two lumped at nodes, the same list the X-Z solve uses)."""
    from crane_statics.calculation.solver.crane_solver import (
        build_directional_response_basis,
        rotate_boom_local_point,
    )

    positions = calc._kinematics.compute_all_node_positions(45.0)
    node_pos = {n: (float(v["x"]), float(v["z"])) for n, v in positions.items()}
    masses = []
    for body in calc.doc.bodies:
        for mp in body.mass_points:
            if body.id == "boom" and mp.local_x_m is not None:
                _x, z = rotate_boom_local_point(
                    float(mp.local_x_m), float(mp.local_z_m or 0.0), node_pos, 45.0
                )
            else:
                z = float(mp.z_m)
            masses.append((float(mp.mass_t), z))
    basis = build_directional_response_basis(
        calc._doc_dict, calc._kinematics, "MH", 45.0, solver_ctx=calc._solver_ctx
    )
    assert basis is not None
    masses.extend((m, z) for m, _x, z in basis.lumped_point_masses)
    return masses


def _expected_roll_fy(calc, roll_rad_s2):
    """Hand sum of the lateral inertia force of every mass under a roll accel.

    Roll is right-handed about +x: omega x r = (0, -omega*z, 0) for a point at height z
    above the reference, so the point accelerates toward -y and its inertia force
    -m*a_y = +m*omega*z points toward +y.
    """
    ref_z = float(calc.doc.environment.vessel_motion.reference_z_m)
    return sum(m * roll_rad_s2 * (z - ref_z) for m, z in _all_point_masses(calc))


IDLE_HOOKS = (("AH", 7.0), ("trolley", 7.7))


def _idle_hook_heights_above_platform(calc):
    positions = calc._kinematics.compute_all_node_positions(45.0)
    z_platform = float(positions["platform_heel"]["z"])
    return [(m, float(positions[f"__hook__{h}"]["z"]) - z_platform) for h, m in IDLE_HOOKS]


def test_roll_tilt_loads_idle_hooks_and_rope_masses_out_of_plane(calc):
    """Roll 5 deg: crane-frame accel_y = g*sin(5 deg), so each mass gets Fy = -m*g*sin(5 deg).

    Idle hooks: 7.0 + 7.7 = 14.7 t -> dFy = -14.7 * 9.81 * 0.0871557 = -12.568 kN, and
    dMx = sum(-(z - z_platform) * fy) = sum((z - z_platform) * m) * 9.81 * 0.0871557.
    """
    s = math.sin(math.radians(5.0))
    with_hooks = _point(calc, wind_speed_m_s=0.0, vessel_roll_deg=5.0)
    no_hooks = _point(
        calc, wind_speed_m_s=0.0, vessel_roll_deg=5.0, hoist_runtime_overrides=NO_IDLE_HOOKS
    )
    pb, pb0 = (
        with_hooks.baseline_reactions["platform_base"],
        no_hooks.baseline_reactions["platform_base"],
    )
    assert pb["Fy"] - pb0["Fy"] == pytest.approx(-14.7 * G * s)
    assert pb["Fy"] - pb0["Fy"] == pytest.approx(-12.568, abs=1e-3)
    arm_mass = sum(m * dz for m, dz in _idle_hook_heights_above_platform(calc))
    assert pb["Mx"] - pb0["Mx"] == pytest.approx(arm_mass * G * s)
    # Every mass (points, idle hooks, rope self-weight) is pushed to starboard.
    total_t = sum(m for m, _z in _all_point_masses(calc))
    assert pb["Fy"] == pytest.approx(-total_t * G * s)


def test_slew_90_vessel_ax_loads_idle_hooks_out_of_plane(calc):
    """Vessel ax = 1 at slew 90 is crane accel_y = -1: each mass gets Fy = +m * 1.

    Idle hooks: dFy = +14.7 kN, dMx = -sum((z - z_platform) * m).
    """
    with_hooks = _point(calc, wind_speed_m_s=0.0, accel_x_m_s2=1.0, crane_slewing_angle_deg=90.0)
    no_hooks = _point(
        calc,
        wind_speed_m_s=0.0,
        accel_x_m_s2=1.0,
        crane_slewing_angle_deg=90.0,
        hoist_runtime_overrides=NO_IDLE_HOOKS,
    )
    pb, pb0 = (
        with_hooks.baseline_reactions["platform_base"],
        no_hooks.baseline_reactions["platform_base"],
    )
    assert pb["Fy"] - pb0["Fy"] == pytest.approx(14.7)
    arm_mass = sum(m * dz for m, dz in _idle_hook_heights_above_platform(calc))
    assert pb["Mx"] - pb0["Mx"] == pytest.approx(-arm_mass)
    total_t = sum(m for m, _z in _all_point_masses(calc))
    assert pb["Fy"] == pytest.approx(total_t)


def test_reported_idle_rope_tension_carries_heave(calc):
    # AH: 7.0 t on 6 falls.
    still = _point(calc, wind_speed_m_s=0.0)
    heave = _point(calc, wind_speed_m_s=0.0, accel_z_m_s2=1.5)
    assert still.baseline_rope_tensions["AH__rope"] == pytest.approx(7.0 * G / 6)
    assert heave.baseline_rope_tensions["AH__rope"] == pytest.approx(7.0 * (G + 1.5) / 6)


def test_roll_acceleration_is_right_handed_about_x(calc):
    level = _point(calc, wind_speed_m_s=0.0)
    rolled = _point(calc, wind_speed_m_s=0.0, roll_accel_rad_s2=0.1)
    expected = _expected_roll_fy(calc, 0.1)
    assert expected > 0.0  # the GT283 masses sit above the reference point
    fy = rolled.baseline_reactions["platform_base"]["Fy"]
    assert fy - level.baseline_reactions["platform_base"]["Fy"] == pytest.approx(expected)


def test_slew_90_swaps_roll_and_pitch_accelerations(calc):
    # Vessel pitch accel 0.1 at slew 90 -> crane roll 0.1, crane pitch 0.
    v_pitch = _point(calc, wind_speed_m_s=0.0, pitch_accel_rad_s2=0.1, crane_slewing_angle_deg=90.0)
    c_roll = _point(calc, wind_speed_m_s=0.0, roll_accel_rad_s2=0.1)
    assert _flat(v_pitch.baseline_reactions) == pytest.approx(_flat(c_roll.baseline_reactions))
    assert v_pitch.baseline_reactions["platform_base"]["Fy"] == pytest.approx(
        _expected_roll_fy(calc, 0.1)
    )
    # Vessel roll accel 0.1 at slew 90 -> crane roll 0, crane pitch -0.1.
    v_roll = _point(calc, wind_speed_m_s=0.0, roll_accel_rad_s2=0.1, crane_slewing_angle_deg=90.0)
    c_pitch = _point(calc, wind_speed_m_s=0.0, pitch_accel_rad_s2=-0.1)
    assert _flat(v_roll.baseline_reactions) == pytest.approx(
        _flat(c_pitch.baseline_reactions), abs=1e-9
    )


def _rear_leg_rope_load(calc, accel_x, accel_z):
    """Load on the rear leg: it carries no mass, so only rope tensions land on it.

    Only the AH idle hook keeps its mass (trolley zeroed, MH active at hook load 0), so the
    rear-leg load is the AH rope tension times a fixed geometry factor.
    """
    d = calc._doc_dict
    positions = calc._kinematics.compute_all_node_positions(45.0)
    node_pos = {n: (float(v["x"]), float(v["z"])) for n, v in positions.items()}
    body_map = {n["id"]: n.get("body", "") for n in d["nodes"]}
    ld, _ = crane_solver._accumulate_loads(
        d,
        node_pos,
        body_map,
        "MH",
        0.0,
        0.0,
        accel_x,
        accel_z,
        boom_angle_deg=45.0,
        hoist_runtime_overrides={"trolley": {"hook_mass_t": 0.0}},
    )
    return ld["rear_leg"]


def test_idle_rope_tension_carries_the_vertical_load_component(calc):
    still = _rear_leg_rope_load(calc, 0.0, 0.0)
    heave = _rear_leg_rope_load(calc, 0.0, 1.5)
    surge = _rear_leg_rope_load(calc, 1.0, 0.0)
    assert abs(still["Fx"]) + abs(still["Fz"]) > 1.0
    ratio = (G + 1.5) / G
    for k in ("Fx", "Fz", "M"):
        assert heave[k] == pytest.approx(still[k] * ratio)
        # accel_z = 0: the tension is the zero-motion value.
        assert surge[k] == pytest.approx(still[k])


def _session_services():
    from crane_statics.core.analysis_presenter import AnalysisPresenter
    from crane_statics.core.analysis_services import (
        AnalysisCalculator,
        HoistStateService,
        KinematicsService,
    )
    from crane_statics.core.session_model import SessionModel

    session = SessionModel()
    session.set_document(load_document(EXAMPLE))
    hoist_svc = HoistStateService(session)
    analysis = AnalysisCalculator(session, KinematicsService(session), hoist_svc)
    presenter = AnalysisPresenter(session, analysis, hoist_svc)
    return session, analysis, hoist_svc, presenter


def test_scene_state_tilt_and_slew_reach_the_engine():
    session, analysis, hoist_svc, _presenter = _session_services()
    state = session.get_active_hoist_state()
    assert state is not None
    sc = state.scene_state
    sc.boom_angle_deg = 45.0
    sc.wind_speed_m_s = 0.0
    sc.accel_x_m_s2 = 1.0
    sc.vessel_roll_deg = 2.0
    sc.vessel_pitch_deg = 10.0
    sc.crane_slewing_angle_deg = 30.0
    pt = analysis.compute_analysis_point()
    assert pt is not None
    expected = CraneCalculator(session.document).compute_analysis_point(
        sc.boom_angle_deg,
        0.0,
        session.selected_hoist_id,
        wind_speed_m_s=0.0,
        wind_direction=sc.wind_direction,
        accel_x_m_s2=1.0,
        accel_y_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_accel_rad_s2=0.0,
        roll_accel_rad_s2=0.0,
        offlead_deg=sc.offlead_deg,
        sidelead_deg=sc.sidelead_deg,
        hoist_runtime_overrides=hoist_svc.active_hoist_runtime_overrides(),
        tackle_length_m=sc.tackle_length_m,
        vessel_roll_deg=2.0,
        vessel_pitch_deg=10.0,
        crane_slewing_angle_deg=30.0,
    )
    assert expected is not None
    assert _flat(pt.baseline_reactions) == pytest.approx(_flat(expected.baseline_reactions))


def test_load_breakdown_puts_tilt_and_slew_in_the_vessel_motion_step(monkeypatch):
    session, _analysis, _hoist_svc, presenter = _session_services()
    state = session.get_active_hoist_state()
    assert state is not None
    sc = state.scene_state
    sc.vessel_roll_deg = 2.0
    sc.vessel_pitch_deg = 10.0
    sc.crane_slewing_angle_deg = 30.0
    calls = []

    def _record(row_meta, hoist_id, hook_load_kN, **kwargs):
        calls.append(kwargs)
        return 1.0

    monkeypatch.setattr(presenter, "_overview_point_demand", _record)
    assert presenter.build_load_contribution_overview({"demand_kN": 1.0}) is not None
    tilt = [
        (c["vessel_roll_deg"], c["vessel_pitch_deg"], c["crane_slewing_angle_deg"]) for c in calls
    ]
    # dead, hook, wind: level and unslewed; inertia, offlead, sidelead: the scene values.
    assert tilt == [(0.0, 0.0, 0.0)] * 3 + [(2.0, 10.0, 30.0)] * 3


def test_sidelead_force_acts_at_the_support_node(calc):
    """The rope delivers the lateral load at the sheave, not the placeholder hook node."""
    point = _point(calc)

    def platform(force_kN):
        _, mx, fy = calc._build_out_of_plane_reactions(
            point, "MH", 45.0, 0.0, 0.0, 0.0, 0.0, side_lateral_force_kN=force_kN
        )
        return mx, fy

    mx0, fy0 = platform(0.0)
    mx1, fy1 = platform(100.0)
    nodes = calc._kinematics.compute_all_node_positions(45.0)
    z_support = float(nodes[calc.hoists["MH"].support_node_id]["z"])
    z_heel = float(nodes["platform_heel"]["z"])
    assert fy1 - fy0 == pytest.approx(100.0)
    assert mx1 - mx0 == pytest.approx(-(z_support - z_heel) * 100.0)
