"""Live-load lateral loads on the hook (ABS 2-2/5.17, 5.19.3, 5.21, 9.3.1; DNV 4.2.3).

``HookLateral`` puts ``fraction * H + constant`` horizontally at the hoist's support node,
the fraction part floored at ``min_fraction * H`` (spec section 9). The expected values are
built from the solver's own off-lead / side-lead unit responses (an independent path through
``compute_analysis_point``) and from ``tests/rules_reference``.
"""

from __future__ import annotations

import json
import math
import dataclasses
from pathlib import Path
from typing import Any, Literal

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.hook_lateral import add_hook_lateral
from crane_statics.calculation.results import AnalysisPoint, HookLateral
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.calculation.vessel_frame import VesselInputs, crane_frame_motion
from crane_statics.core import lift_factor, load_document
from crane_statics.core import sweep as sweep_module
from crane_statics.core.analysis_cases import analysis_mode_by_name
from crane_statics.core.chart_envelope import (
    build_probes,
    envelope_capacity,
    envelope_capacity_case,
)
from crane_statics.core.lead_channels import compose_lead_channel_point
from crane_statics.core.lift_factor import LiftFactors
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.core.load_condition import condition_cases, condition_document
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.data.models import ConditionSpec, VesselMotion
from crane_statics.rules import validate_rules_document
from crane_statics.rules.abs_profile import AbsProfile
from tests import rules_reference as ref
from tests.rules_docs import GT283, rules_doc, without_live_lateral, without_suspended_rope

ROOT = Path(__file__).parent.parent
HOIST = "MH"
G = 9.81
ANGLE = 45.0
H_KN = 1000.0
INCLINE_DEG = math.hypot(5.0, 2.0)  # 5.385 deg
SIN_INCLINE = math.sin(math.radians(INCLINE_DEG))


@pytest.fixture(scope="module")
def calc() -> CraneCalculator:
    return CraneCalculator(load_document(GT283))


def _point(calc: CraneCalculator, **kwargs) -> AnalysisPoint:
    kwargs.setdefault("wind_speed_m_s", 0.0)
    pt = calc.compute_analysis_point(ANGLE, 0.0, HOIST, **kwargs)
    assert pt is not None
    return pt


def _flat(reactions: dict) -> dict:
    return {(e, k): float(v) for e, comps in reactions.items() for k, v in comps.items()}


def _at(pt: AnalysisPoint, hook_kN: float) -> dict:
    """Every reaction component and rope tension at hook force ``hook_kN``."""
    base, sens = _flat(pt.baseline_reactions), _flat(pt.sensitivity_reactions)
    out = {key: base.get(key, 0.0) + sens.get(key, 0.0) * hook_kN for key in set(base) | set(sens)}
    for rope, value in pt.baseline_rope_tensions.items():
        out[("rope", rope)] = value + pt.sensitivity_rope_tensions.get(rope, 0.0) * hook_kN
    return out


def _diff(a: dict, b: dict) -> dict:
    return {key: a.get(key, 0.0) - b.get(key, 0.0) for key in set(a) | set(b)}


def _unit_x(calc: CraneCalculator, **kwargs) -> dict:
    """Response to 1 kN along +x at the support node, through the solver's off-lead path."""
    lead = _at(_point(calc, offlead_deg=90.0, sidelead_deg=0.0, **kwargs), 1.0)
    plain = _at(_point(calc, offlead_deg=0.0, sidelead_deg=0.0, **kwargs), 1.0)
    return _diff(lead, plain)


def _unit_y(calc: CraneCalculator, **kwargs) -> dict:
    """Response to 1 kN along +y at the support node, through the solver's side-lead path."""
    lead = _at(_point(calc, offlead_deg=0.0, sidelead_deg=90.0, **kwargs), 1.0)
    plain = _at(_point(calc, offlead_deg=0.0, sidelead_deg=0.0, **kwargs), 1.0)
    return _diff(lead, plain)


def _assert_scaled(actual: dict, unit: dict, scale: float) -> None:
    for key in set(actual) | set(unit):
        assert actual.get(key, 0.0) == pytest.approx(scale * unit.get(key, 0.0), abs=1e-6), key


# --- the solver ---------------------------------------------------------------------------


def test_no_hook_lateral_leaves_the_gt283_golden_unchanged(calc: CraneCalculator) -> None:
    kwargs = dict(
        wind_speed_m_s=10.0,
        wind_direction="+X",
        accel_x_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_accel_rad_s2=0.0,
        vessel_roll_deg=0.0,
        vessel_pitch_deg=0.0,
        crane_slewing_angle_deg=0.0,
    )
    plain = _point(calc, **kwargs)
    with_none = _point(calc, hook_lateral=None, **kwargs)
    golden = json.loads((ROOT / "tests" / "golden" / "gt283_mh_45deg.json").read_text())
    assert _flat(with_none.baseline_reactions) == pytest.approx(_flat(golden["baseline"]))
    assert _flat(with_none.sensitivity_reactions) == pytest.approx(_flat(golden["sensitivity"]))
    # Bit for bit the call without the keyword.
    assert with_none.baseline_reactions == plain.baseline_reactions
    assert with_none.sensitivity_reactions == plain.sensitivity_reactions
    assert with_none.baseline_rope_tensions == plain.baseline_rope_tensions
    assert with_none.sensitivity_rope_tensions == plain.sensitivity_rope_tensions


def test_list_trim_incline_adds_its_hand_value_at_the_support_node(calc: CraneCalculator) -> None:
    expected = ref.abs_list_trim_load(H_KN, 5.0, 2.0)
    assert expected == pytest.approx(93.85, abs=0.01)
    plain = _point(calc, offlead_deg=0.0, sidelead_deg=0.0)
    tilted = _point(
        calc, offlead_deg=0.0, sidelead_deg=0.0, hook_lateral=HookLateral(SIN_INCLINE, 0.0)
    )
    added = _diff(_at(tilted, H_KN), _at(plain, H_KN))
    _assert_scaled(added, _unit_x(calc), expected)
    # The platform takes the whole horizontal force: 93.85 kN.
    assert -added[("platform_base", "Fx")] == pytest.approx(expected, abs=0.01)
    # The left/right supports share it (the hook lateral uses the complete x unit).
    assert added[("heel_left", "Fx")] + added[("heel_right", "Fx")] == pytest.approx(
        added[("heel_point", "Fx")], abs=1e-6
    )
    assert added[("heel_left", "Fx")] != 0.0


def test_lateral_y_fraction_uses_the_side_lead_unit(calc: CraneCalculator) -> None:
    plain = _point(calc, offlead_deg=0.0, sidelead_deg=0.0)
    side = _point(
        calc, offlead_deg=0.0, sidelead_deg=0.0, hook_lateral=HookLateral(0.0, SIN_INCLINE)
    )
    _assert_scaled(_diff(_at(side, H_KN), _at(plain, H_KN)), _unit_y(calc), H_KN * SIN_INCLINE)


@pytest.mark.parametrize("wind", [("+X", 15.0), ("+Y", 15.0), ("-X", 0.0)])
@pytest.mark.parametrize("force", [(7.0, 0.0), (0.0, -5.0), (3.0, 4.0)])
def test_constant_force_is_applied_as_given_whatever_h_and_the_wind(
    calc: CraneCalculator, wind: tuple[str, float], force: tuple[float, float]
) -> None:
    direction, speed = wind
    kwargs = dict(wind_speed_m_s=speed, wind_direction=direction, offlead_deg=0.0, sidelead_deg=0.0)
    plain = _point(calc, **kwargs)
    loaded = _point(calc, hook_lateral=HookLateral(0.0, 0.0, *force), **kwargs)
    assert loaded.sensitivity_reactions == plain.sensitivity_reactions
    assert loaded.sensitivity_rope_tensions == plain.sensitivity_rope_tensions
    unit_x, unit_y = _unit_x(calc), _unit_y(calc)
    expected = {
        key: force[0] * unit_x.get(key, 0.0) + force[1] * unit_y.get(key, 0.0)
        for key in set(unit_x) | set(unit_y)
    }
    for hook in (0.0, 500.0, 2000.0):
        _assert_scaled(_diff(_at(loaded, hook), _at(plain, hook)), expected, 1.0)


def test_floor_without_fractions_gives_min_fraction_times_h_linearly(
    calc: CraneCalculator,
) -> None:
    plain = _point(calc, offlead_deg=0.0, sidelead_deg=0.0)
    floored = _point(
        calc,
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hook_lateral=HookLateral(0.0, 0.0, min_fraction=0.02),
    )
    unit = _unit_x(calc)
    for hook in (250.0, 1000.0, 4000.0):
        added = _diff(_at(floored, hook), _at(plain, hook))
        _assert_scaled(added, unit, 0.02 * hook)
        assert -added[("platform_base", "Fx")] == pytest.approx(0.02 * hook, rel=1e-9)
    # Linear in H: the floor sits in the sensitivity, the baseline is untouched.
    assert floored.baseline_reactions == plain.baseline_reactions


def test_floor_scales_a_small_lateral_to_the_minimum_in_its_direction() -> None:
    small = HookLateral(0.003, -0.004, min_fraction=0.02)
    fx, fy = small.floored_fractions()
    assert math.hypot(fx, fy) == pytest.approx(0.02)
    assert (fx, fy) == pytest.approx((0.012, -0.016))
    big = HookLateral(0.03, 0.04, min_fraction=0.02)
    assert big.floored_fractions() == (0.03, 0.04)


# --- the envelope: the lateral direction of largest demand --------------------------------


def _probes(calc: CraneCalculator):
    probes = build_probes(calc, HOIST, ANGLE, 0.0, None, vessel=VesselMotion())
    assert probes is not None
    return probes


@pytest.mark.parametrize(
    "limits",
    [
        {"heel_left": {"Fx": 4000.0}},  # linear, responds to x and y
        {"front_leg_right": {"Fz": 15000.0}},  # linear
        {"platform_base": {"fradial": 300.0}},  # magnitude
        {"platform_base": {"mradial": 300000.0}},  # magnitude
    ],
)
def test_envelope_takes_the_lateral_direction_of_largest_demand(
    calc: CraneCalculator, limits: dict
) -> None:
    probes = _probes(calc)
    lateral = HookLateral(0.06, 0.0, min_fraction=0.02)
    cap, case = envelope_capacity_case(
        calc,
        probes,
        limits,
        vessel=VesselMotion(),
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hook_daf=1.0,
        lower_block_mass_t=50.0,
        hook_lateral=lateral,
    )
    plain, _ = envelope_capacity_case(
        calc,
        probes,
        limits,
        vessel=VesselMotion(),
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hook_daf=1.0,
        lower_block_mass_t=50.0,
    )
    assert case is not None
    assert cap.max_allowable_load_kN < plain.max_allowable_load_kN
    # Brute force over directions on the circle |l| = 0.06 H.
    worst = math.inf
    for step in range(720):
        phi = math.radians(step * 0.5)
        pt = compose_lead_channel_point(
            probes.zero, 0.0, 0.0, lateral=(0.06 * math.cos(phi), 0.06 * math.sin(phi))
        )
        worst = min(worst, calc.compute_allowable_load(pt, limits, 1.0, 50.0).max_allowable_load_kN)
    # Never above the true worst; a magnitude limit may be up to the 16-gon overshoot below.
    assert cap.max_allowable_load_kN <= worst * (1.0 + 1e-9)
    magnitude = "fradial" in str(limits) or "mradial" in str(limits)
    assert cap.max_allowable_load_kN >= worst * (0.97 if magnitude else 1.0 - 1e-6)
    chosen = (case.lateral_x_fraction, case.lateral_y_fraction)
    radius = math.hypot(*chosen)
    if magnitude:
        assert radius == pytest.approx(0.06 / math.cos(math.pi / 16))
    else:
        assert radius == pytest.approx(0.06)
    # The recorded direction reproduces the capacity.
    pt = compose_lead_channel_point(probes.zero, 0.0, 0.0, lateral=chosen)
    again = calc.compute_allowable_load(pt, limits, 1.0, 50.0).max_allowable_load_kN
    assert again == pytest.approx(cap.max_allowable_load_kN, rel=1e-9)


def test_envelope_without_hook_lateral_is_unchanged(calc: CraneCalculator) -> None:
    probes = _probes(calc)
    limits = {"heel_left": {"Fx": 3000.0}, "boom_hoist": {"T": 5000.0}}
    kwargs: dict[str, Any] = dict(
        vessel=VesselMotion(),
        offlead_deg=1.0,
        sidelead_deg=2.5,
        hook_daf=1.0,
        lower_block_mass_t=50.0,
    )
    a = envelope_capacity_case(calc, probes, limits, **kwargs)
    b = envelope_capacity_case(calc, probes, limits, hook_lateral=None, **kwargs)
    assert a == b
    assert a[1] is not None and a[1].lateral_x_fraction == 0.0 == a[1].lateral_y_fraction


# --- the rules profiles fill the lateral --------------------------------------------------


def test_abs_default_load_area_is_applied_at_the_chart_maximum_live_load() -> None:
    doc = rules_doc("ABS", ConditionSpec(name="c", wind_speed_m_s=10.3))
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    rope_t, chart_t = 4.0, 300.0
    setup = AbsProfile().lift_setup(
        doc, doc.conditions["c"], HOIST, mode, 0.0, rope_t, chart_t, support_x_m=0.0
    )
    ll_kN = (chart_t + mode.lower_block_mass_t + rope_t) * G
    area = ref.abs_live_load_wind_area(ll_kN)
    assert setup.lateral.wind_area_m2 == pytest.approx(area, rel=1e-12)
    pressure = ref.abs_wind_pressure(10.3, 1.0)
    assert setup.lateral.wind_force_per_speed_sq * 10.3**2 == pytest.approx(
        pressure * area, rel=1e-12
    )
    assert any("5.19.3" in w and "applied" in w and "not applied" not in w for w in setup.warnings)
    record = next(r for r in setup.records if r.quantity == "load_wind_force")
    assert record.value == pytest.approx(pressure * area, rel=1e-12)


def test_abs_entered_load_area_is_used_as_entered() -> None:
    cond = ConditionSpec(
        name="c", wind_speed_m_s=10.3, load_wind_area_m2=12.0, load_drag_coefficient=1.2
    )
    doc = rules_doc("ABS", cond)
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    setup = AbsProfile().lift_setup(doc, cond, HOIST, mode, 0.0, 4.0, 300.0, support_x_m=0.0)
    assert setup.lateral.wind_area_m2 == 12.0
    assert setup.lateral.wind_force_per_speed_sq * 10.3**2 == pytest.approx(
        ref.abs_wind_pressure(10.3, 1.2) * 12.0, rel=1e-12
    )
    assert not any("5.19.3" in w for w in setup.warnings)


def test_rules_hook_lateral_from_the_lift_setup() -> None:
    motion = VesselMotion(accel_x_m_s2=0.6, accel_y_m_s2=0.8, roll_deg=5.0, pitch_deg=2.0)
    cond = ConditionSpec(name="c", wind_speed_m_s=10.0, vessel_motion=motion)
    doc = rules_doc("ABS", cond)
    condition = condition_cases(doc, "c")[0]
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    lift = LiftFactors(doc, CraneCalculator(doc))
    setup = lift.setup(condition, HOIST, mode, ANGLE)
    support_z = lift.support_z_m(HOIST, ANGLE)
    lateral = lift_factor.hook_lateral(setup, condition.wind_speed_m_s, support_z_m=support_z)
    assert lateral is not None
    # a_h = hypot(0.6, 0.8)/g = 1/g (no angular acceleration, so the same at every height),
    # added to the list/trim term in the worst direction.
    assert lateral.fraction_x == pytest.approx(1.0 / G + SIN_INCLINE, rel=1e-12)
    assert lateral.fraction_y == 0.0
    assert lateral.min_fraction == 0.02
    force = setup.lateral.wind_force_per_speed_sq * 100.0
    assert lateral.constant_x_kN == pytest.approx(force) and lateral.constant_y_kN == 0.0
    assert lateral.constant_magnitude() == pytest.approx(force)
    legacy = lift_factor.legacy_lift_setup(hoist)
    assert lift_factor.hook_lateral(legacy, 10.0, support_z_m=support_z) is None


def test_abs_horizontal_acceleration_is_taken_at_the_boom_tip() -> None:
    """5.17: a_h at the support node = linear + angular acceleration x lever arm (per axis)."""
    motion = VesselMotion(
        accel_x_m_s2=0.6,
        accel_y_m_s2=0.3,
        roll_deg=5.0,
        pitch_deg=2.0,
        pitch_angular_accel_rad_s2=0.04,
        roll_angular_accel_rad_s2=0.06,
        reference_x_m=12.0,
        reference_z_m=-6.0,
    )
    cond = ConditionSpec(name="c", wind_speed_m_s=0.0, vessel_motion=motion)
    doc = rules_doc("ABS", cond)
    condition = condition_cases(doc, "c")[0]
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    lift = LiftFactors(doc, CraneCalculator(doc))
    setup = lift.setup(condition, HOIST, mode, ANGLE)
    # The support node's height, read independently of the factor code.
    doc_dict = doc.model_dump()
    positions = KinematicsAdapter(doc_dict).compute_all_node_positions(ANGLE)
    support = next(h for h in doc_dict["hoists"] if h["id"] == HOIST)["support_node_id"]
    lever = positions[support]["z"] - (-6.0)
    assert lever > 10.0  # the boom tip is high above the reference point
    a_x = 0.6 + 0.04 * lever  # the solver's a_x + pitch_accel * (z - z_ref)
    a_y = 0.3 + 0.06 * lever  # |a_y - roll_accel * (z - z_ref)|, magnitudes added
    lateral = lift_factor.hook_lateral(setup, 0.0, support_z_m=lift.support_z_m(HOIST, ANGLE))
    assert lateral is not None
    assert lateral.fraction_x == pytest.approx(math.hypot(a_x, a_y) / G + SIN_INCLINE, rel=1e-12)
    # Without angular acceleration the old value.
    still = motion.model_copy(
        update={"pitch_angular_accel_rad_s2": 0.0, "roll_angular_accel_rad_s2": 0.0}
    )
    doc_still = rules_doc("ABS", cond.model_copy(update={"vessel_motion": still}))
    lift_still = LiftFactors(doc_still, CraneCalculator(doc_still))
    setup_still = lift_still.setup(condition_cases(doc_still, "c")[0], HOIST, mode, ANGLE)
    plain = lift_factor.hook_lateral(
        setup_still, 0.0, support_z_m=lift_still.support_z_m(HOIST, ANGLE)
    )
    assert plain is not None
    assert plain.fraction_x == pytest.approx(math.hypot(0.6, 0.3) / G + SIN_INCLINE, rel=1e-12)


def test_load_wind_takes_the_worst_direction_at_full_force(calc: CraneCalculator) -> None:
    """A linear limit gains F*|R| (the resultant of its x and y responses), not max(|R|)*F."""
    probes = _probes(calc)
    limits = {"heel_left": {"Fx": 4000.0}}
    kwargs: dict[str, Any] = dict(
        vessel=VesselMotion(),
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hook_daf=1.0,
        lower_block_mass_t=50.0,
    )
    force = 40.0
    plain, _ = envelope_capacity_case(calc, probes, limits, **kwargs)
    windy, case = envelope_capacity_case(
        calc, probes, limits, hook_lateral=HookLateral(0.0, 0.0, 0.0, force), **kwargs
    )
    zero = probes.zero
    assert zero.lateral_x_unit_reactions is not None
    assert zero.sidelead_lateral_unit_reactions is not None
    r_x = zero.lateral_x_unit_reactions["heel_left"]["Fx"]
    r_y = zero.sidelead_lateral_unit_reactions["heel_left"]["Fx"]
    assert r_x != 0.0 and r_y != 0.0
    s = zero.sensitivity_reactions["heel_left"]["Fx"]
    # H = (L - B - F|R|)/s and H0 = (L - B)/s.
    expected = plain.max_allowable_load_kN - force * math.hypot(r_x, r_y) / s
    assert windy.max_allowable_load_kN == pytest.approx(expected, rel=1e-9)
    axis_only = plain.max_allowable_load_kN - force * max(abs(r_x), abs(r_y)) / s
    assert windy.max_allowable_load_kN < axis_only
    assert case is not None
    assert math.hypot(case.lateral_x_kN, case.lateral_y_kN) == pytest.approx(force)


def _with_fixed_lateral(probes, fx: float, fy: float, cx: float, cy: float):
    """Every probe with the same lateral: the envelope over everything else, one direction."""
    return dataclasses.replace(
        probes,
        zero=add_hook_lateral(probes.zero, fx, fy, cx, cy),
        motion=tuple(add_hook_lateral(m, fx, fy, cx, cy) for m in probes.motion),
        wind_x=add_hook_lateral(probes.wind_x, fx, fy, cx, cy),
        wind_y=add_hook_lateral(probes.wind_y, fx, fy, cx, cy),
    )


BRUTE_STEPS = 720
MOVING = VesselMotion(
    accel_x_m_s2=0.6,
    accel_y_m_s2=0.3,
    accel_z_m_s2=0.4,
    roll_deg=2.0,
    pitch_deg=1.0,
    pitch_angular_accel_rad_s2=0.02,
    roll_angular_accel_rad_s2=0.03,
)


@pytest.mark.parametrize(
    "limits",
    [
        {"heel_left": {"Fx": 15000.0}},
        {"boom_hoist": {"T": 5000.0}},
        {"platform_base": {"fradial": 3000.0}},
    ],
)
def test_envelope_lateral_matches_brute_force_with_leads_wind_and_motion(limits: dict) -> None:
    calc = CraneCalculator(load_document(GT283))
    probes = build_probes(calc, HOIST, ANGLE, 15.0, None, vessel=MOVING)
    assert probes is not None
    r, force = 0.05, 30.0
    kwargs: dict[str, Any] = dict(
        vessel=MOVING, offlead_deg=1.0, sidelead_deg=2.5, hook_daf=1.0, lower_block_mass_t=50.0
    )
    cap, _ = envelope_capacity_case(
        calc, probes, limits, hook_lateral=HookLateral(r, 0.0, force, 0.0, 0.02), **kwargs
    )
    worst = math.inf
    for step in range(BRUTE_STEPS):
        phi = 2.0 * math.pi * step / BRUTE_STEPS
        ux, uy = math.cos(phi), math.sin(phi)
        fixed = _with_fixed_lateral(probes, r * ux, r * uy, force * ux, force * uy)
        worst = min(
            worst, envelope_capacity_case(calc, fixed, limits, **kwargs)[0].max_allowable_load_kN
        )
    assert math.isfinite(worst)
    magnitude = "fradial" in str(limits)
    assert cap.max_allowable_load_kN <= worst * (1.0 + 1e-6)
    # The grid's own coarseness (0.5 deg) bounds the linear gap.
    assert cap.max_allowable_load_kN >= worst * (0.97 if magnitude else 1.0 - 1e-4)


# --- sweeps -------------------------------------------------------------------------------

LIMIT_T = {"boom_hoist": {"T": 5000.0}}
ABS_MOTION = VesselMotion(accel_x_m_s2=0.5, roll_deg=5.0, pitch_deg=2.0)
DAF = 1.3


def _abs_sweep_doc(motion: VesselMotion = ABS_MOTION):
    cond = ConditionSpec(name="sea", wind_speed_m_s=0.0, vessel_motion=motion)
    doc = without_suspended_rope(rules_doc("ABS", cond))
    hoists = [h.model_copy(update={"hook_daf": DAF}) if h.id == HOIST else h for h in doc.hoists]
    doc = doc.model_copy(update={"hoists": hoists})
    validate_rules_document(doc)
    return doc


def _curve(doc, limits=LIMIT_T, condition_name=None) -> dict[float, float]:
    payload = run_mode_sweep(doc, HOIST, "normal", limits, 5.0, {}, condition_name=condition_name)
    assert payload is not None and payload["curve_data"]
    return dict(payload["curve_data"])


@pytest.mark.parametrize(
    ("motion", "r"),
    [
        (ABS_MOTION, 0.5 / G + SIN_INCLINE),  # above the floor
        # a_x/g + sin(0.5 deg) = 0.0138 < 0.02: the 0.02 VDL floor governs.
        (VesselMotion(accel_x_m_s2=0.05, roll_deg=0.5), 0.02),
    ],
)
def test_abs_sweep_capacity_drops_by_the_hand_derived_lateral(
    monkeypatch, motion: VesselMotion, r: float
) -> None:
    """boom_hoist T: s = s_hook + (sin(offlead) + r)|R_x|, r = max(a_x/g + sin(theta), 0.02)."""
    if r == 0.02:
        assert 0.05 / G + math.sin(math.radians(0.5)) < 0.02
    doc = _abs_sweep_doc(motion)
    with_lateral = _curve(doc)
    monkeypatch.setattr(sweep_module, "hook_lateral", lambda *_a, **_k: None)
    without = _curve(doc)
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    kin = KinematicsAdapter(doc.model_dump())
    calc = CraneCalculator(doc)
    checked = 0
    for outreach, payload_t in without.items():
        angle = kin.outreach_to_angle(outreach, HOIST)
        assert angle is not None
        pt = calc.compute_analysis_point(
            angle,
            0.0,
            HOIST,
            wind_speed_m_s=0.0,
            offlead_deg=0.0,
            sidelead_deg=0.0,
            amplified_rope_hoist_id=HOIST,
        )
        assert pt is not None and pt.offlead_lateral_unit_rope_tensions is not None
        s_hook = pt.sensitivity_rope_tensions["boom_hoist"]
        r_x = abs(pt.offlead_lateral_unit_rope_tensions["boom_hoist"])
        s_lead = s_hook + math.sin(math.radians(hoist.offlead_deg)) * r_x
        h0 = DAF * (payload_t + hoist.lower_block_mass_t) * G
        expected_h = h0 * s_lead / (s_lead + r * r_x)
        expected_t = expected_h / (DAF * G) - hoist.lower_block_mass_t
        assert with_lateral[outreach] == pytest.approx(expected_t, rel=1e-9)
        assert with_lateral[outreach] < payload_t
        checked += 1
    assert checked >= 2


def test_dnv_case_ii_incline_and_load_wind_reach_the_sweep(monkeypatch) -> None:
    """Case I: sin(theta); Case II: sin(1.5 theta) plus the 4.2.3.3 wind on the load.

    platform_base Fx (a reaction) sees only horizontal loads: a unit +x lateral gives -1,
    the vertical hook load 0, the 1 deg off-lead sin(1 deg). Per case the worst baseline
    B follows from the capacity without the lateral, H0 = (L - B) / sin(1 deg), and with
    it H = (L - B - W) / (sin(1 deg) + r), W the load wind (it blows with the worst
    structural wind). The chart is the lowest case, through the case's psi (onboard: the
    8.2.2.1 floor of the chart's maximum working load).
    """
    motion = VesselMotion(roll_deg=3.0, pitch_deg=2.0)
    cond = ConditionSpec(
        name="sea",
        wind_speed_m_s=15.0,
        vessel_motion=motion,
        load_wind_area_m2=20.0,
        load_drag_coefficient=1.2,
    )
    doc = without_suspended_rope(rules_doc("DNV", cond))
    limit = 1500.0
    limits = {"platform_base": {"Fx": limit}}
    seen: dict[str, set[HookLateral]] = {}
    real = sweep_module.envelope_capacity

    def spy(calc, probes, limits, **kwargs):
        wind = calc.doc.environment.max_wind_speed_m_s
        seen.setdefault("Case II" if wind else "Case I", set()).add(kwargs["hook_lateral"])
        return real(calc, probes, limits, **kwargs)

    monkeypatch.setattr(sweep_module, "envelope_capacity", spy)
    with_lateral = _curve(doc, limits)
    monkeypatch.setattr(sweep_module, "envelope_capacity", real)

    theta_i = math.hypot(3.0, 2.0)
    rho = doc.environment.air_density_kg_m3
    wind_kN = 0.5 * rho * 1.2 * 15.0**2 * 20.0 / 1000.0
    expected_lateral = {
        "Case I": HookLateral(math.sin(math.radians(theta_i)), 0.0, 0.0, 0.0, 0.0),
        "Case II": HookLateral(math.sin(math.radians(1.5 * theta_i)), 0.0, wind_kN, 0.0, 0.0),
    }
    for name, expected in expected_lateral.items():
        (got,) = seen[name]
        assert got.fraction_x == pytest.approx(expected.fraction_x, rel=1e-12)
        assert got.fraction_y == 0.0
        assert got.constant_x_kN == pytest.approx(expected.constant_x_kN, rel=1e-12)
        assert got.constant_y_kN == pytest.approx(expected.constant_y_kN, rel=1e-12)
        assert got.min_fraction == 0.0

    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    s_lead = math.sin(math.radians(hoist.offlead_deg))
    kin = KinematicsAdapter(doc.model_dump())
    lift = LiftFactors(doc, CraneCalculator(doc))
    for outreach, payload_t in with_lateral.items():
        angle = kin.outreach_to_angle(outreach, HOIST)
        assert angle is not None
        by_case = {}
        payload_by_case = {}
        for condition in condition_cases(doc, "sea"):
            factor = lift.setup(condition, HOIST, mode, angle).factor
            calc = CraneCalculator(condition_document(doc, condition))
            probes = build_probes(
                calc,
                HOIST,
                angle,
                condition.wind_speed_m_s,
                {},
                vessel=condition.vessel_motion,
                amplified_rope_hoist_id=HOIST,
            )
            assert probes is not None and condition.case is not None
            h0 = envelope_capacity(
                calc,
                probes,
                limits,
                vessel=condition.vessel_motion,
                offlead_deg=hoist.offlead_deg,
                sidelead_deg=hoist.sidelead_deg,
                hook_daf=factor,
                lower_block_mass_t=hoist.lower_block_mass_t,
            ).max_allowable_load_kN
            baseline = limit - h0 * s_lead
            lateral = expected_lateral[condition.case.name]
            name = condition.case.name
            by_case[name] = (limit - baseline - lateral.constant_x_kN) / (
                s_lead + lateral.fraction_x
            )
            payload_by_case[name] = factor.payload_t(by_case[name], hoist.lower_block_mass_t, G)
        # Case II's 1.5x incline and wind govern.
        assert by_case["Case II"] < by_case["Case I"]
        assert payload_t == pytest.approx(min(payload_by_case.values()), rel=1e-9)


# --- Auto-Set and the Scene ---------------------------------------------------------------


def test_auto_set_counts_the_lateral(monkeypatch) -> None:
    doc = _abs_sweep_doc()
    rope_id = next(h for h in doc.hoists if h.id == "BH").rope_id
    with_lateral = compute_required_rope_capacity_kN(doc, rope_id)
    without_live_lateral(monkeypatch)
    without = compute_required_rope_capacity_kN(doc, rope_id)
    assert with_lateral.required_kN is not None and without.required_kN is not None
    assert with_lateral.required_kN > without.required_kN


def _scene_vm(doc):
    from crane_statics.qml_app.session import SessionState
    from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
    from tests.test_scene_view_model import MockCanvas

    session = SessionState()
    vm = SceneViewModel(session)
    vm.bindCanvas(MockCanvas())
    session.model.set_document(doc)
    vm.selectHoist(HOIST)
    return vm


def test_scene_applies_the_lateral_along_its_inertia_and_its_equilibrium_closes() -> None:
    doc = _abs_sweep_doc()
    vm = _scene_vm(doc)
    vm.setHookLoadTonnes(300.0)
    vm.setAccelX(0.8)
    state = vm._model.get_active_hoist_state()
    assert state is not None
    sc = state.scene_state
    lateral = vm._hoist_state.hook_lateral(HOIST)
    assert lateral is not None
    # The Scene condition's magnitude (not the Scene sliders'), along the Scene's inertia:
    # -(a_x, a_y) of its crane-frame motion, the tilt of its heel/trim folded in.
    magnitude = 0.5 / G + SIN_INCLINE
    motion = crane_frame_motion(
        G,
        VesselInputs(
            accel_x_m_s2=sc.accel_x_m_s2,
            accel_y_m_s2=sc.accel_y_m_s2,
            accel_z_m_s2=sc.accel_z_m_s2,
            roll_deg=sc.vessel_roll_deg,
            pitch_deg=sc.vessel_pitch_deg,
            slew_deg=sc.crane_slewing_angle_deg,
        ),
    )
    ux, uy = -motion.accel_x_m_s2, -motion.accel_y_m_s2
    size = math.hypot(ux, uy)
    assert ux < 0.0  # accel_x 0.8 dominates: the payload swings toward -x
    assert lateral.fraction_x == pytest.approx(magnitude * ux / size, rel=1e-9)
    assert lateral.fraction_y == pytest.approx(magnitude * uy / size, rel=1e-9)
    # The Scene solve carries it: the hook-load sensitivity gains magnitude * (-X).
    point = vm._calculator.compute_analysis_point()
    assert point is not None and point.lateral_x_unit_reactions is not None
    plain = CraneCalculator(doc).compute_analysis_point(
        sc.boom_angle_deg,
        0.0,
        HOIST,
        wind_speed_m_s=sc.wind_speed_m_s,
        wind_direction=sc.wind_direction,
        accel_x_m_s2=sc.accel_x_m_s2,
        accel_y_m_s2=sc.accel_y_m_s2,
        accel_z_m_s2=sc.accel_z_m_s2,
        pitch_accel_rad_s2=sc.pitch_accel_rad_s2,
        roll_accel_rad_s2=sc.roll_accel_rad_s2,
        offlead_deg=sc.offlead_deg,
        sidelead_deg=sc.sidelead_deg,
        tackle_length_m=sc.tackle_length_m,
        vessel_roll_deg=sc.vessel_roll_deg,
        vessel_pitch_deg=sc.vessel_pitch_deg,
        crane_slewing_angle_deg=sc.crane_slewing_angle_deg,
        amplified_rope_hoist_id=HOIST,
    )
    assert plain is not None
    unit_fx = point.lateral_x_unit_reactions["platform_base"]["Fx"]
    assert point.sensitivity_reactions["platform_base"]["Fx"] == pytest.approx(
        plain.sensitivity_reactions["platform_base"]["Fx"] + lateral.fraction_x * unit_fx,
        rel=1e-9,
    )
    # The drawn hook lateral closes the in-plane equilibrium check.
    conditions = vm._calculator.drawn_load_conditions()
    assert conditions.hook_lateral_x_kN == pytest.approx(
        lateral.fraction_x * sc.hook_load_kN, rel=1e-9
    )
    inputs = vm._scene_inputs()
    assert inputs.document_dict is not None
    report = vm._presenter.build_drawn_load_sections(
        document_dict=inputs.document_dict,
        analysis_point=inputs.analysis_point,
        node_positions=inputs.node_positions(),
        conditions=inputs.conditions,
    )
    failing = [s for s in report["sections"] if not s["passed"]]
    assert not failing, [(s.get("title"), s.get("force_residual")) for s in failing]


def test_legacy_scene_has_no_lateral() -> None:
    vm = _scene_vm(load_document(GT283))
    vm.setHookLoadTonnes(300.0)
    assert vm._hoist_state.hook_lateral(HOIST) is None
    assert vm._calculator.drawn_load_conditions().hook_lateral_x_kN == 0.0


def test_scene_load_overview_shows_the_hook_lateral_step() -> None:
    vm = _scene_vm(_abs_sweep_doc())
    vm.setHookLoadTonnes(300.0)
    point = vm._calculator.compute_analysis_point()
    assert point is not None
    state = vm._model.get_active_hoist_state()
    assert state is not None
    meta = {"kind": "connection", "entity_id": "platform_base", "component": "Fx"}
    demand = vm._calculator.resolve_row_demand(point, state.scene_state.hook_load_kN, meta)
    assert demand is not None
    overview = vm._presenter.build_load_contribution_overview({**meta, "demand_kN": demand})
    assert overview is not None
    names = [t["name"] for t in overview["terms"]]
    assert names[-1] == "Hook lateral"
    assert overview["terms"][-1]["value_kN"] != 0.0
    assert overview["reconstructed_kN"] == pytest.approx(demand, abs=1e-6)


# --- ABS a_v at the boom tip (review fix round 2) ----------------------------------------

TIP_MOTION = VesselMotion(
    accel_z_m_s2=0.5,
    pitch_angular_accel_rad_s2=0.05,
    roll_angular_accel_rad_s2=-0.03,
    reference_x_m=-3.0,
)


def _abs_setup(
    lift: Literal["onboard", "offboard"], motion: VesselMotion, support_x_m: float, **kw: Any
):
    cond = ConditionSpec(name="c", lift=lift, wind_speed_m_s=0.0, vessel_motion=motion, **kw)
    doc = rules_doc("ABS", cond)
    hoists = [h.model_copy(update={"max_hoisting_speed_m_s": 0.5}) for h in doc.hoists]
    doc = doc.model_copy(update={"hoists": hoists})
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    hoist = hoist.model_copy(update={"hook_daf": 1.0})
    doc = doc.model_copy(update={"hoists": [hoist if h.id == HOIST else h for h in doc.hoists]})
    mode = analysis_mode_by_name(hoist, "normal")
    setup = AbsProfile().lift_setup(
        doc, cond, HOIST, mode, 5000.0, 0.0, 300.0, support_x_m=support_x_m
    )
    return setup, mode


def _vaf(setup, mode, ll_kN: float) -> float:
    payload = ll_kN / G - mode.lower_block_mass_t
    return float(setup.factor.hook_force_kN(payload, mode.lower_block_mass_t, G) / ll_kN)


def test_abs_a_v_is_taken_at_the_boom_tip() -> None:
    # a_v = (|a_z| + (|alpha_pitch| + |alpha_roll|) * (|x_ref| + |x_tip|)) / g
    a_v = (0.5 + (0.05 + 0.03) * (3.0 + 40.0)) / G
    assert a_v > 0.3  # ~0.4 g at a 40 m tip, against 0.05 g from a_z alone
    setup, mode = _abs_setup("onboard", TIP_MOTION, 40.0)
    for ll in (1000.0, 3000.0):
        assert _vaf(setup, mode, ll) == pytest.approx(ref.abs_vaf_onboard(ll, a_v), rel=1e-12)
    record = next(r for r in setup.records if r.quantity == "dynamic_factor")
    assert record.inputs["a_v_g"] == pytest.approx(a_v, rel=1e-12)
    assert record.inputs["a_v_lever_m"] == 43.0
    # The lever bound is the same on either side of the slew axis.
    mirrored, _ = _abs_setup("onboard", TIP_MOTION, -40.0)
    assert _vaf(mirrored, mode, 1000.0) == pytest.approx(_vaf(setup, mode, 1000.0), rel=1e-15)


def test_abs_a_v_without_angular_acceleration_is_the_linear_one() -> None:
    still = TIP_MOTION.model_copy(
        update={"pitch_angular_accel_rad_s2": 0.0, "roll_angular_accel_rad_s2": 0.0}
    )
    setup, mode = _abs_setup("onboard", still, 40.0)
    assert _vaf(setup, mode, 1000.0) == pytest.approx(
        ref.abs_vaf_onboard(1000.0, 0.5 / G), rel=1e-12
    )


def test_abs_offboard_factor_uses_the_tip_a_v() -> None:
    a_v = (0.5 + 0.08 * 43.0) / G
    setup, mode = _abs_setup(
        "offboard",
        TIP_MOTION,
        40.0,
        significant_wave_height_m=2.0,
        v_in_m_s=0.8,
        v_t_m_s=0.6,
    )
    v_r = ref.abs_v_r(0.5, 0.8, 0.6)
    for ll in (1000.0, 3000.0, 8000.0):
        assert _vaf(setup, mode, ll) == pytest.approx(
            ref.abs_vaf_offboard(ll, 5000.0, v_r, a_v), rel=1e-12
        )
    # The onboard floor (with the tip a_v) governs at a large live load.
    assert _vaf(setup, mode, 8000.0) == pytest.approx(ref.abs_vaf_onboard(8000.0, a_v), rel=1e-12)


def test_lift_setup_passes_the_support_node_x_at_each_angle() -> None:
    cond = ConditionSpec(name="c", wind_speed_m_s=0.0, vessel_motion=TIP_MOTION)
    doc = rules_doc("ABS", cond)
    condition = condition_cases(doc, "c")[0]
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    lift = LiftFactors(doc, CraneCalculator(doc))
    doc_dict = doc.model_dump()
    support = next(h for h in doc_dict["hoists"] if h["id"] == HOIST)["support_node_id"]
    kin = KinematicsAdapter(doc_dict)
    levers = []
    for angle in (40.0, 70.0):
        setup = lift.setup(condition, HOIST, mode, angle)
        record = next(r for r in setup.records if r.quantity == "dynamic_factor")
        x_tip = kin.compute_all_node_positions(angle)[support]["x"]
        assert record.inputs["a_v_lever_m"] == pytest.approx(3.0 + abs(x_tip), rel=1e-12)
        levers.append(record.inputs["a_v_lever_m"])
    assert levers[0] != levers[1]  # cached per angle: the tip moves
