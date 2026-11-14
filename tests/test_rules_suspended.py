"""The suspended rope (support node to hook) counted in the amplified live load on rules runs."""

from __future__ import annotations

from typing import Any

import pytest

from crane_statics.calculation.dynamic_factor import ConstantDynamicFactor
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.rope_mass import (
    active_hook_positions,
    falls_override_effective_mult,
    resolve_total_rope_length_m,
    rope_mass_at_nodes,
)
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core.analysis_cases import HoistAnalysisMode, analysis_mode_by_name
from crane_statics.core.analysis_services import AnalysisCalculator, HoistStateService
from crane_statics.core.lift_factor import LiftFactors
from crane_statics.core.load_condition import condition_cases
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.data.models import ConditionSpec, CraneDocument, VesselMotion
from crane_statics.rules import validate_rules_document
from crane_statics.rules.factors import LinearFactor
from crane_statics.rules.suspended import suspended_rope_mass_t
from tests.rules_docs import (
    first_settings,
    GT283,
    legacy_equivalent,
    load_v13,
    rules_doc,
    without_foundation_factors,
)

HOIST = "MH"
HOOK_T = 50.0  # GT283 MH hook block
G = 9.81
OUTREACH = 20.0
SUPPORT, HOOK = "mh_boom_sheave_4", "__hook__MH"
DAF = 1.3

# GT283 node rope masses (reeved_t, spooled_t) with the boom at 20 m MH outreach and the MH
# hook at its lowest hook height, captured before the suspended-rope change.
GOLDEN_ANGLE = 83.0011066330312
GOLDEN = {
    "__hook__AH": (0.017490000000000002, 0.0),
    "__hook__MH": (15.351673416250897, 0.0),
    "__hook__trolley": (0.00248, 0.0),
    "ah_aframe_sheave_1": (0.3101854252482198, 0.0),
    "ah_boom_sheave_3": (0.24847923176995604, 0.0),
    "ah_boom_sheave_4": (0.05194253779114098, 0.0),
    "ah_winch": (0.09615873126940477, 5.966086723902536),
    "bh_aframe_sheave_1": (22.123746008616784, 0.0),
    "bh_boom_sheave_3": (21.372333769264504, 0.0),
    "bh_winch": (0.7514122393522813, 28.020507982766432),
    "mh_aframe_sheave_1": (1.0058550860702664, 0.0),
    "mh_boom_sheave_3": (0.7510808718463179, 0.0),
    "mh_boom_sheave_4": (15.422841419379058, 0.0),
    "mh_winch": (0.32594221735211, 0.09432364053339087),
    "trolley_aframe_sheave_1": (0.15750418176160036, 0.0),
    "trolley_aframe_sheave_2": (0.11948175181878393, 0.0),
    "trolley_boom_sheave_1": (0.22352920995704545, 0.0),
    "trolley_boom_sheave_2": (0.18848, 0.0),
    "trolley_winch": (0.07555163989986187, 0.5721155984900046),
}


def _doc_dict() -> dict:
    return load_v13(GT283).model_dump()


def _positions(doc_dict: dict, angle: float = GOLDEN_ANGLE, tackle_m: float | None = None):
    kin = KinematicsAdapter(doc_dict)
    return active_hook_positions(doc_dict, HOIST, kin.compute_all_node_positions(angle), tackle_m)


def _hook_segment_length_m(positions) -> float:
    a, b = positions[SUPPORT], positions[HOOK]
    return float(((b["x"] - a["x"]) ** 2 + (b["z"] - a["z"]) ** 2) ** 0.5)


# --- rope_mass_at_nodes / suspended_rope_mass_t ------------------------------------------


def test_legacy_node_masses_without_the_keyword_are_the_golden_values() -> None:
    doc_dict = _doc_dict()
    masses = rope_mass_at_nodes(doc_dict, _positions(doc_dict))
    assert set(masses) == set(GOLDEN)
    for node_id, (reeved_t, spooled_t) in GOLDEN.items():
        assert masses[node_id].reeved_t == reeved_t, node_id
        assert masses[node_id].spooled_t == spooled_t, node_id


def test_excluding_the_hook_segment_removes_exactly_the_suspended_rope() -> None:
    doc_dict = _doc_dict()
    positions = _positions(doc_dict)
    legacy = rope_mass_at_nodes(doc_dict, positions)
    dead = rope_mass_at_nodes(doc_dict, positions, exclude_hoist_segment=HOIST)
    suspended = suspended_rope_mass_t(doc_dict, HOIST, positions)
    # Hand value: linear mass x hook-segment length x its 20 falls.
    hoist = next(h for h in doc_dict["hoists"] if h["id"] == HOIST)
    expected = hoist["linear_mass_kg_m"] * _hook_segment_length_m(positions) * 20 / 1000.0
    assert suspended == pytest.approx(expected, rel=1e-12)
    assert suspended == pytest.approx(30.703346832501794, rel=1e-9)
    # The hook node carried only that segment: it is gone. The sheave keeps its other half.
    assert HOOK not in dead
    assert dead[SUPPORT].reeved_t == pytest.approx(
        legacy[SUPPORT].reeved_t - suspended / 2.0, rel=1e-12
    )
    # Nothing else moves: the excluded rope is still reeved, so the drum does not gain it.
    for node_id, entry in legacy.items():
        if node_id in (SUPPORT, HOOK):
            continue
        assert dead[node_id] == entry, node_id


def test_total_rope_mass_is_conserved_dead_plus_suspended() -> None:
    doc_dict = _doc_dict()
    for angle, tackle in ((GOLDEN_ANGLE, None), (70.0, None), (75.0, 30.0)):
        positions = _positions(doc_dict, angle, tackle)
        legacy_total = sum(e.mass_t for e in rope_mass_at_nodes(doc_dict, positions).values())
        dead_total = sum(
            e.mass_t
            for e in rope_mass_at_nodes(doc_dict, positions, exclude_hoist_segment=HOIST).values()
        )
        suspended = suspended_rope_mass_t(doc_dict, HOIST, positions)
        assert suspended > 0.0
        assert dead_total + suspended == pytest.approx(legacy_total, rel=1e-12)
    # And the legacy total is every hoist's whole rope (each one owns a winch node).
    owned = sum(
        resolve_total_rope_length_m(doc_dict, h["id"]) * h["linear_mass_kg_m"] / 1000.0
        for h in doc_dict["hoists"]
    )
    assert legacy_total == pytest.approx(owned, rel=1e-12)


def test_split_block_falls_change_the_suspended_mass_with_the_mult() -> None:
    doc_dict = _doc_dict()
    positions = _positions(doc_dict)
    normal = suspended_rope_mass_t(doc_dict, HOIST, positions)
    split_mult = falls_override_effective_mult(doc_dict, {HOIST: 10})
    split = suspended_rope_mass_t(doc_dict, HOIST, positions, split_mult)
    assert split == pytest.approx(normal * 10 / 20, rel=1e-12)
    legacy = sum(e.mass_t for e in rope_mass_at_nodes(doc_dict, positions, split_mult).values())
    dead = sum(
        e.mass_t
        for e in rope_mass_at_nodes(
            doc_dict, positions, split_mult, exclude_hoist_segment=HOIST
        ).values()
    )
    assert dead + split == pytest.approx(legacy, rel=1e-12)


def test_other_hoists_and_unknown_hoists_have_no_suspended_rope_effect() -> None:
    doc_dict = _doc_dict()
    positions = _positions(doc_dict)
    assert suspended_rope_mass_t(doc_dict, "nope", positions) == 0.0
    assert suspended_rope_mass_t(doc_dict, "BH", positions) == 0.0  # no hook
    legacy = rope_mass_at_nodes(doc_dict, positions)
    assert rope_mass_at_nodes(doc_dict, positions, exclude_hoist_segment="nope") == legacy


# --- the solver: conservation ---------------------------------------------------------------


def _vertical(point, force_kN: float) -> float:
    base = point.baseline_reactions["platform_base"]["Fz"]
    sens = point.sensitivity_reactions["platform_base"]["Fz"]
    return float(base) + float(sens) * force_kN


def test_daf_1_total_vertical_reaction_equals_the_legacy_one_at_the_same_payload() -> None:
    doc = load_v13(GT283)
    doc_dict = doc.model_dump()
    calc = CraneCalculator(doc)
    angle = GOLDEN_ANGLE
    kwargs: dict[str, Any] = dict(
        wind_speed_m_s=0.0,
        offlead_deg=0.0,
        sidelead_deg=0.0,
        accel_x_m_s2=0.0,
        accel_y_m_s2=0.0,
        accel_z_m_s2=0.0,
        vessel_roll_deg=0.0,
        vessel_pitch_deg=0.0,
    )
    legacy = calc.compute_analysis_point(angle, 0.0, HOIST, **kwargs)
    amplified = calc.compute_analysis_point(
        angle, 0.0, HOIST, amplified_rope_hoist_id=HOIST, **kwargs
    )
    assert legacy is not None and amplified is not None
    rope_t = suspended_rope_mass_t(doc_dict, HOIST, _positions(doc_dict, angle))
    factor = LinearFactor(1.0, rope_t)
    payload_t = 400.0
    legacy_force = (payload_t + HOOK_T) * G
    amplified_force = factor.hook_force_kN(payload_t, HOOK_T, G)
    assert amplified_force == pytest.approx(legacy_force + rope_t * G, rel=1e-12)
    # The rope's dead weight left the baseline; the hook force carries it instead.
    base_shift = (
        legacy.baseline_reactions["platform_base"]["Fz"]
        - amplified.baseline_reactions["platform_base"]["Fz"]
    )
    assert abs(base_shift) == pytest.approx(rope_t * G, rel=1e-9)
    assert _vertical(amplified, amplified_force) == pytest.approx(
        _vertical(legacy, legacy_force), rel=1e-12, abs=1e-6
    )
    # And the capacity inversion takes the rope back out: the same payload.
    assert factor.payload_t(amplified_force, HOOK_T, G) == pytest.approx(payload_t, rel=1e-12)


# --- the lift factor -----------------------------------------------------------------------


def _deck(**kw) -> ConditionSpec:
    return ConditionSpec(
        name="deck", lift="onboard", wind_speed_m_s=0.0, vessel_motion=VesselMotion(), **kw
    )


def _no_lead(doc: CraneDocument) -> CraneDocument:
    """``doc`` with MH at no lead and the manual DAF ``DAF`` in every condition."""
    update = {"offlead_deg": 0.0, "sidelead_deg": 0.0, "daf": DAF}
    conditions = {}
    for name, cond in doc.conditions.items():
        hoists = dict(cond.hoists)
        hoists[HOIST] = hoists[HOIST].model_copy(update=update)
        conditions[name] = cond.model_copy(update={"hoists": hoists})
    return doc.model_copy(update={"conditions": conditions})


def _abs_deck_doc(**kw) -> CraneDocument:
    doc = _no_lead(rules_doc("ABS", _deck(**kw)))
    validate_rules_document(doc)
    return doc


def _split_doc(doc: CraneDocument) -> CraneDocument:
    split = {"splitable_block": True, "split_falls": 10, "split_lower_block_mass_t": 30.0}
    hoists = [h.model_copy(update=split) if h.id == HOIST else h for h in doc.hoists]
    conditions = {}
    for name, cond in doc.conditions.items():
        entries = dict(cond.hoists)
        mh = entries[HOIST]
        entries[HOIST] = mh.model_copy(update={"split_contractual_points": mh.contractual_points})
        conditions[name] = cond.model_copy(update={"hoists": entries})
    return doc.model_copy(update={"hoists": hoists, "conditions": conditions})


def test_lift_setup_carries_the_suspended_rope_as_the_factor_extra_mass() -> None:
    doc = _split_doc(_abs_deck_doc())
    doc_dict = doc.model_dump()
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    condition = condition_cases(doc, None)[0]
    lift = LiftFactors(doc, None)
    for angle in (GOLDEN_ANGLE, 75.0):
        positions = _positions(doc_dict, angle)
        normal = lift.setup(
            condition,
            HOIST,
            analysis_mode_by_name(hoist, "normal", first_settings(doc, HOIST)),
            angle,
        )
        assert normal.factor == LinearFactor(DAF, suspended_rope_mass_t(doc_dict, HOIST, positions))
        split = lift.setup(
            condition,
            HOIST,
            analysis_mode_by_name(hoist, "split", first_settings(doc, HOIST)),
            angle,
        )
        split_mult = falls_override_effective_mult(doc_dict, {HOIST: 10})
        assert split.factor == LinearFactor(
            DAF, suspended_rope_mass_t(doc_dict, HOIST, positions, split_mult)
        )
    # The rope hangs at the hook position the tackle length gives.
    mode = analysis_mode_by_name(hoist, "normal", first_settings(doc, HOIST))
    short = lift.setup(condition, HOIST, mode, GOLDEN_ANGLE, tackle_length_m=10.0)
    expected = suspended_rope_mass_t(doc_dict, HOIST, _positions(doc_dict, GOLDEN_ANGLE, 10.0))
    assert short.factor == LinearFactor(DAF, expected)
    assert expected == pytest.approx(10.0 * 20 * 9.17 / 1000.0, rel=1e-9)


def test_rules_less_lift_setup_has_no_suspended_rope() -> None:
    doc = load_v13(GT283)
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    condition = condition_cases(doc, None)[0]
    mode = HoistAnalysisMode("normal", float(hoist.lower_block_mass_t), {}, [])
    setup = LiftFactors(doc, None).setup(condition, HOIST, mode, GOLDEN_ANGLE)
    daf = condition.hoist_settings(HOIST).daf
    assert daf == 1.1  # GT283's authored constant
    assert setup.factor == ConstantDynamicFactor(daf)  # no suspended rope in the factor


# --- the sweep -----------------------------------------------------------------------------

FZ_LIMIT = {"platform_base": {"Fz": 12000.0}}


def test_amplified_rope_lowers_the_capacity_by_the_hand_derived_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rope r as dead load (legacy) against r in the amplified load, both at daf 1.3.

    With a vertical-reaction limit the rope weight moves out of the baseline into the hook
    force one for one, so at the legacy capacity the extra demand is r (daf - 1) g, and the
    capacity falls by r (daf - 1) / daf.
    """
    without_foundation_factors(monkeypatch)  # the legacy run has no pedestal factor
    doc = _abs_deck_doc()
    rules = run_mode_sweep(doc, HOIST, "normal", FZ_LIMIT, 5.0, {})
    legacy = run_mode_sweep(
        legacy_equivalent(doc, 0.0, VesselMotion()), HOIST, "normal", FZ_LIMIT, 5.0, {}
    )
    assert rules is not None and legacy is not None
    rules_curve, legacy_curve = dict(rules["curve_data"]), dict(legacy["curve_data"])
    assert rules_curve.keys() == legacy_curve.keys() and rules_curve
    doc_dict = doc.model_dump()
    kin = KinematicsAdapter(doc_dict)
    for outreach, legacy_t in legacy_curve.items():
        angle = kin.outreach_to_angle(outreach, HOIST)
        assert angle is not None
        rope_t = suspended_rope_mass_t(doc_dict, HOIST, _positions(doc_dict, angle))
        assert rope_t > 10.0
        expected_drop = rope_t * (DAF - 1.0) / DAF
        assert legacy_t - rules_curve[outreach] == pytest.approx(expected_drop, rel=1e-6)
        # In force terms: the legacy payload now demands r (daf - 1) g more.
        extra_kN = LinearFactor(DAF, rope_t).hook_force_kN(legacy_t, HOOK_T, G) - (
            DAF * (legacy_t + HOOK_T) * G
        )
        assert extra_kN - rope_t * G == pytest.approx(rope_t * (DAF - 1.0) * G, rel=1e-9)


# --- the Scene -----------------------------------------------------------------------------


def _scene(doc: CraneDocument) -> tuple[SessionModel, HoistStateService]:
    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist(HOIST)
    return session, HoistStateService(session)


def test_scene_factor_and_point_count_the_rope_at_the_scene_hook() -> None:
    doc = _abs_deck_doc()
    session, service = _scene(doc)
    sc = session.hoist_states[HOIST].scene_state
    sc.tackle_length_m = 40.0  # the hook 40 m below its sheave, as the scene drags it
    doc_dict = doc.model_dump()
    rope_t = suspended_rope_mass_t(
        doc_dict, HOIST, _positions(doc_dict, sc.boom_angle_deg, sc.tackle_length_m)
    )
    assert rope_t == pytest.approx(40.0 * 20 * 9.17 / 1000.0, rel=1e-9)
    assert service.payload_t_to_hook_force_kN(300.0, HOIST) == pytest.approx(
        DAF * (300.0 + HOOK_T + rope_t) * G, rel=1e-12
    )
    # The Scene's analysis point no longer carries the hook rope as dead weight.
    calc = AnalysisCalculator(session, None, service)  # type: ignore[arg-type]
    point = calc.compute_analysis_point()
    legacy_point = CraneCalculator(doc).compute_analysis_point(
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
    )
    assert point is not None and legacy_point is not None
    shift = (
        legacy_point.baseline_reactions["platform_base"]["Fz"]
        - point.baseline_reactions["platform_base"]["Fz"]
    )
    assert abs(shift) == pytest.approx(rope_t * G, rel=1e-9)
