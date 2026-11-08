"""The dynamic factor of each chart point: rules profile per outreach, legacy constant."""

from __future__ import annotations

import math

import pytest

from crane_statics.calculation.dynamic_factor import ConstantDynamicFactor
from crane_statics.calculation.engine import get_calculator
from crane_statics.calculation.rope_mass import hook_support_node_id
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core import load_document
from crane_statics.core.analysis_cases import analysis_mode_by_name
from crane_statics.core.analysis_services import HoistStateService
from crane_statics.core.governing_case import governing_case
from crane_statics.core.lift_factor import LiftFactors, factor_for_point
from crane_statics.core.limit_auto_set import _evaluate_contractual_points
from crane_statics.core.load_condition import condition_cases
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.data.models import ConditionSpec, CraneDocument, VesselMotion
from crane_statics.rules import RulesValidationError, validate_rules_document
from crane_statics.rules.stiffness import payload_hoist_stiffness_terms
from tests import rules_reference as ref
from tests.rules_docs import (
    without_live_lateral,
    GT283,
    legacy_equivalent,
    rules_doc,
    without_suspended_rope,
)

HOIST = "MH"
HOOK_T = 50.0  # GT283 MH hook block
G = 9.81
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}
STEP = 10.0
OUTREACH = 20.0  # MH reaches 16 to 25 m
EA_KN = {"MH__rope": 90000.0, "BH__rope": 150000.0, "AH__rope": 60000.0, "trolley__rope": 20000.0}
V_H, V_IN, V_T = 0.5, 0.8, 0.6
MOTION = VesselMotion(accel_z_m_s2=0.5, roll_deg=2.0, pitch_deg=1.0)


def _sea(**kw) -> ConditionSpec:
    """An offboard condition without wind (Hs 2 m, v_in 0.8 m/s, v_t 0.6 m/s)."""
    return ConditionSpec(
        name="sea",
        lift="offboard",
        wind_speed_m_s=0.0,
        vessel_motion=MOTION,
        significant_wave_height_m=2.0,
        v_in_m_s=V_IN,
        v_t_m_s=V_T,
        **kw,
    )


def _rules(doc: CraneDocument, daf: float) -> CraneDocument:
    ropes = [r.model_copy(update={"ea_kN": EA_KN.get(r.id, r.ea_kN)}) for r in doc.ropes]
    hoists = [
        (
            h.model_copy(update={"hook_daf": daf, "max_hoisting_speed_m_s": V_H})
            if h.id == HOIST
            else h.model_copy(update={"max_hoisting_speed_m_s": V_H})
        )
        for h in doc.hoists
    ]
    out = doc.model_copy(update={"ropes": ropes, "hoists": hoists})
    validate_rules_document(out)
    return out


def _abs_doc(daf: float = 1.0, **cond) -> CraneDocument:
    return _rules(rules_doc("ABS", _sea(**cond)), daf)


def _curve(doc: CraneDocument) -> dict[float, float]:
    payload = run_mode_sweep(doc, HOIST, "normal", LIMITS, STEP, {})
    assert payload is not None and payload["curve_data"]
    return dict(payload["curve_data"])


def _angle(doc: CraneDocument, outreach: float = OUTREACH) -> float:
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach, HOIST)
    assert angle is not None
    return float(angle)


def _point(doc: CraneDocument, angle: float):
    point = get_calculator(doc).compute_analysis_point(
        angle, 0.0, HOIST, offlead_deg=0.0, sidelead_deg=0.0
    )
    assert point is not None
    return point


def _setup(doc: CraneDocument, angle: float, case_index: int = 0):
    mode = analysis_mode_by_name(next(h for h in doc.hoists if h.id == HOIST), "normal")
    condition = condition_cases(doc, None)[case_index]
    return factor_for_point(doc, condition, HOIST, mode, _point(doc, angle), angle)


def _oracle_k(doc: CraneDocument, angle: float, tackle_m: float | None) -> float:
    terms = payload_hoist_stiffness_terms(doc, _point(doc, angle), HOIST, tackle_m)
    return ref.hook_stiffness([(t.tension_per_hook_kN, t.reeved_length_m, t.ea_kN) for t in terms])


def _computed_k(setup) -> float:
    record = next(
        r for r in setup.records if r.quantity == "dynamic_factor" and r.source == "computed"
    )
    return float(record.inputs["K_kN_m"])


def _support_z(doc: CraneDocument, angle: float) -> float:
    doc_dict = doc.model_dump()
    positions = KinematicsAdapter(doc_dict).compute_all_node_positions(angle)
    return float(positions[hook_support_node_id(doc_dict, HOIST)]["z"])


# --- legacy ------------------------------------------------------------------------------


def test_legacy_document_gets_the_constant_authored_factor() -> None:
    doc = load_document(GT283)
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    angle = _angle(doc)
    setup = _setup(doc, angle)
    assert setup.factor == ConstantDynamicFactor(hoist.hook_daf)
    assert setup.records == () and setup.warnings == ()
    assert setup.retaining_live_factor == 1.0
    assert setup.foundation.live_factor(1234.0) == 1.0 and setup.foundation.dead_factor == 1.0
    assert setup.lateral.min_fraction == 0.0 and setup.lateral.wind_area_m2 == 0.0


def test_legacy_governing_case_names_no_condition() -> None:
    case = governing_case(load_document(GT283), HOIST, "normal", LIMITS, OUTREACH, None)
    assert case is not None
    assert case.condition_name is None and case.case_name is None


# --- ABS offboard against the oracle -----------------------------------------------------


def _oracle_payload_t(hook_force_kN: float, k_kN_m: float, a_v_g: float) -> float:
    """Payload whose LL * VAF(LL) equals the hook force, by bisection on the oracle VAF."""
    v_r = ref.abs_v_r(V_H, V_IN, V_T)
    lo, hi = 1e-6, hook_force_kN
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid * ref.abs_vaf_offboard(mid, k_kN_m, v_r, a_v_g) < hook_force_kN:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi) / G - HOOK_T


def test_abs_offboard_sweep_capacity_matches_the_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    # Without payload-rope mass the daf-1 legacy chart has the rules run's dead load, so its
    # limiting hook force is the rules one exactly (the rope: tests/test_rules_suspended.py).
    doc = without_suspended_rope(_abs_doc())
    assert abs(doc.environment.gravity_m_s2) == G
    swept = _curve(doc)
    # The limiting hook force does not depend on the factor: read it from a daf-1 chart.
    unit = _curve(legacy_equivalent(doc, 0.0, MOTION))
    hook_force_kN = (unit[OUTREACH] + HOOK_T) * G
    angle = _angle(doc)
    k = _oracle_k(doc, angle, 0.0)  # worst case: hook at its sheave
    a_v_g = MOTION.accel_z_m_s2 / G
    expected = _oracle_payload_t(hook_force_kN, k, a_v_g)
    assert swept[OUTREACH] == pytest.approx(expected, rel=1e-3)
    # The relative-velocity branch governs here, and it is well below the daf-1 chart.
    ll = (expected + HOOK_T) * G
    v_r = ref.abs_v_r(V_H, V_IN, V_T)
    assert 1.0 + v_r * math.sqrt(k / (G * ll)) > ref.abs_vaf_onboard(ll, a_v_g)
    assert swept[OUTREACH] < unit[OUTREACH] / 1.1


def test_abs_offboard_factor_varies_with_outreach() -> None:
    doc = _abs_doc()
    near, far = _setup(doc, _angle(doc, 16.0)), _setup(doc, _angle(doc, 25.0))
    assert _computed_k(near) != _computed_k(far)
    assert near.factor != far.factor


# --- manual daf --------------------------------------------------------------------------


def test_manual_daf_gives_the_legacy_capacity_and_both_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    # Without payload-rope mass; the amplified suspended rope: tests/test_rules_suspended.py.
    doc = without_suspended_rope(_abs_doc(daf=1.25))
    swept = _curve(doc)
    legacy = _curve(legacy_equivalent(doc, 0.0, MOTION))
    assert swept.keys() == legacy.keys()
    for outreach, load_t in legacy.items():
        assert swept[outreach] == pytest.approx(load_t, rel=1e-12)
    setup = _setup(doc, _angle(doc))
    sources = [r.source for r in setup.records if r.quantity == "dynamic_factor"]
    assert sources == ["computed", "override"]


# --- hook height override ----------------------------------------------------------------

OVERRIDE_M = -20.0


def test_hook_height_override_lowers_the_stiffness_and_the_factor() -> None:
    worst_doc = _abs_doc()
    override_doc = _abs_doc(hook_height_override_m=OVERRIDE_M)
    angle = _angle(worst_doc)
    worst, low = _setup(worst_doc, angle), _setup(override_doc, angle)

    # Hook height h maps to the tackle length below the sheave: max(0, z_support - h).
    tackle_m = _support_z(worst_doc, angle) - OVERRIDE_M
    assert tackle_m > 0.0
    assert _computed_k(low) == pytest.approx(_oracle_k(override_doc, angle, tackle_m), rel=1e-12)
    assert _computed_k(worst) == pytest.approx(_oracle_k(worst_doc, angle, 0.0), rel=1e-12)
    assert _computed_k(low) < _computed_k(worst)
    for payload_t in (100.0, 500.0, 1000.0):
        assert low.factor.hook_force_kN(payload_t, HOOK_T, G) < worst.factor.hook_force_kN(
            payload_t, HOOK_T, G
        )
    assert _curve(override_doc)[OUTREACH] > _curve(worst_doc)[OUTREACH]


def test_hook_height_override_at_the_lowest_hook_height_is_the_design_position() -> None:
    lowest = next(h for h in load_document(GT283).hoists if h.id == HOIST).lowest_hook_height_m
    assert lowest is not None
    doc = _abs_doc(hook_height_override_m=lowest)
    angle = _angle(doc)
    # tackle None puts the hook at lowest_hook_height_m (rope_mass.active_hook_positions).
    assert _computed_k(_setup(doc, angle)) == pytest.approx(_oracle_k(doc, angle, None), rel=1e-12)


# --- DNV: one setup per case --------------------------------------------------------------


def test_dnv_case_ii_lift_setup_lateral_spec_has_its_own_incline() -> None:
    # The LiftSetup lateral spec only; the solver does not use it yet (Task 11).
    doc = _rules(rules_doc("DNV", _sea()), 1.0)
    angle = _angle(doc)
    case_i, case_ii = _setup(doc, angle, 0), _setup(doc, angle, 1)
    assert case_ii.lateral.incline_deg == pytest.approx(1.5 * case_i.lateral.incline_deg)
    assert case_i.factor == case_ii.factor


# --- every consumer uses the same factor -------------------------------------------------


def test_governing_case_hook_load_is_the_chart_value_through_the_factor() -> None:
    doc = _abs_doc()
    case = governing_case(doc, HOIST, "normal", LIMITS, OUTREACH, None)
    assert case is not None
    assert case.condition_name == "sea" and case.case_name == "In-service"
    factor = _setup(doc, _angle(doc)).factor
    payload_t = factor.payload_t(case.scene_fields["hook_load_kN"], HOOK_T, G)
    assert payload_t == pytest.approx(_curve(doc)[OUTREACH], rel=1e-9)


def test_auto_set_hook_force_uses_the_factor_at_each_contractual_point() -> None:
    doc = _abs_doc()
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    results = _evaluate_contractual_points(
        [hoist],
        doc,
        get_calculator(doc),
        KinematicsAdapter(doc.model_dump()),
        G,
        lambda _pt, hook_kN, _case: hook_kN,
    )
    assert len(results) == len(hoist.contractual_points)
    for result in results:
        cp = hoist.contractual_points[result.cp_index]
        factor = _setup(doc, result.angle_deg).factor
        assert result.best_demand == pytest.approx(factor.hook_force_kN(cp.load_t, HOOK_T, G))
        assert result.best_demand > ConstantDynamicFactor(1.1).hook_force_kN(cp.load_t, HOOK_T, G)
        assert result.condition_name == "sea" and result.case_name == "In-service"


def test_scene_conversions_use_the_scene_condition_factor() -> None:
    doc = _abs_doc()
    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist(HOIST)
    service = HoistStateService(session)
    scene = session.hoist_states[HOIST].scene_state
    scene.tackle_length_m = 40.0  # the suspended rope hangs at the Scene's hook
    angle = float(scene.boom_angle_deg)
    mode = analysis_mode_by_name(next(h for h in doc.hoists if h.id == HOIST), "normal")
    expected = factor_for_point(
        doc, session.scene_condition(), HOIST, mode, _point(doc, angle), angle, tackle_length_m=40.0
    ).factor
    at_sheave = factor_for_point(
        doc, session.scene_condition(), HOIST, mode, _point(doc, angle), angle, tackle_length_m=0.0
    ).factor
    assert expected != at_sheave  # the 40 m of falls (7.3 t) are in the live load
    assert service.payload_t_to_hook_force_kN(300.0, HOIST) == pytest.approx(
        expected.hook_force_kN(300.0, HOOK_T, G), rel=1e-12
    )
    force = expected.hook_force_kN(300.0, HOOK_T, G)
    assert service.hook_force_kN_to_payload_t(force) == pytest.approx(300.0, rel=1e-9)


# --- review fixes --------------------------------------------------------------------------


def _dnv_onboard_doc() -> CraneDocument:
    cond = ConditionSpec(name="deck", lift="onboard", wind_speed_m_s=0.0, vessel_motion=MOTION)
    return rules_doc("DNV", cond)


def test_scene_factor_follows_in_place_document_edits() -> None:
    doc = _dnv_onboard_doc()
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    hoist.hook_daf = 1.0  # computed, not the GT283 manual 1.1
    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist(HOIST)
    service = HoistStateService(session)

    def factor() -> float:
        return float(service.payload_t_to_hook_force_kN(100.0, HOIST) / ((100.0 + HOOK_T) * G))

    # Rated 1000 t: W = 1050 t * g > 5000 kN, so the DNV psi floor is 1.1.
    assert factor() == pytest.approx(ref.dnv_psi_floor((1000.0 + HOOK_T) * G))
    for cp in hoist.contractual_points:
        cp.load_t = 100.0  # edited in place, as the chart's contractual-point editor does
    assert factor() == pytest.approx(ref.dnv_psi_floor((100.0 + HOOK_T) * G)) == 1.3
    hoist.hook_daf = 1.45  # in place: a manual daf now overrides
    assert factor() == pytest.approx(1.45)


def _no_ea_offboard_doc() -> CraneDocument:
    doc = rules_doc("ABS", _sea())  # not validated: no rope EA
    hoists = [
        h.model_copy(update={"max_hoisting_speed_m_s": V_H, "contractual_points": []})
        for h in doc.hoists
    ]
    return doc.model_copy(update={"hoists": hoists})


def test_sweep_raises_on_an_inconsistent_rules_document_instead_of_dropping_points() -> None:
    doc = _no_ea_offboard_doc()  # no contractual points: stage 2 meets the error first
    with pytest.raises(RulesValidationError, match="ea_kN"):
        run_mode_sweep(doc, HOIST, "normal", LIMITS, STEP, {})


def test_mode_without_contractual_points_warns_of_the_rated_load_fallback() -> None:
    doc = _no_ea_offboard_doc()
    doc = doc.model_copy(update={"conditions": {"deck": _dnv_onboard_doc().conditions["deck"]}})
    setup = _setup(doc, _angle(doc))
    assert any("no contractual points" in w for w in setup.warnings)
    assert not any("no contractual points" in w for w in _setup(_abs_doc(), _angle(doc)).warnings)


def test_split_mode_warns_that_the_stiffness_ignores_the_split_block() -> None:
    doc = _abs_doc()
    hoists = [
        (
            h.model_copy(
                update={
                    "splitable_block": True,
                    "split_falls": 10,
                    "split_hook_mass_t": 30.0,
                    "split_contractual_points": h.contractual_points,
                }
            )
            if h.id == HOIST
            else h
        )
        for h in doc.hoists
    ]
    doc = doc.model_copy(update={"hoists": hoists})
    angle = _angle(doc)
    split = analysis_mode_by_name(next(h for h in doc.hoists if h.id == HOIST), "split")
    assert split.name == "split"
    condition = condition_cases(doc, None)[0]
    setup = factor_for_point(doc, condition, HOIST, split, _point(doc, angle), angle)
    assert any("authored reeving" in w for w in setup.warnings)
    assert not any("authored reeving" in w for w in _setup(doc, angle).warnings)


def test_bounded_lift_factors_keep_at_most_max_entries() -> None:
    doc = _abs_doc()
    lift = LiftFactors(doc, get_calculator(doc), max_entries=2)
    mode = analysis_mode_by_name(next(h for h in doc.hoists if h.id == HOIST), "normal")
    condition = condition_cases(doc, None)[0]
    angles = [_angle(doc, x) for x in (16.0, 20.0, 25.0)]
    setups = [lift.setup(condition, HOIST, mode, a) for a in angles]
    assert len(lift._setups) == 2 and len(lift._points) == 2
    assert lift.setup(condition, HOIST, mode, angles[0]).factor == setups[0].factor
