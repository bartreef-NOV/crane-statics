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


def test_slew_90_vessel_ax_loads_the_split_supports(calc):
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


def test_roll_tilts_gravity_into_the_split_supports(calc):
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
    vm.crane_slewing_angle_deg = 30.0
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
        crane_slewing_angle_deg=30.0,
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
