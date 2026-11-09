"""DNV profile: cases, dynamic factor, lateral spec, SF1 and provenance."""

from __future__ import annotations

import dataclasses
import inspect
import math
from pathlib import Path

import pytest

from crane_statics.core.analysis_cases import iter_hoist_analysis_modes
from crane_statics.core.io import load_document
from crane_statics.data.models import ConditionSpec, RulesSpec, VesselMotion, payload_hoist_ids
from crane_statics.rules import profile_for
from crane_statics.rules.abs_profile import AbsProfile
from crane_statics.rules.dnv_profile import DnvProfile, dnv_v_h
from crane_statics.rules.factors import LinearFactor, MaxFactor
from crane_statics.rules.foundation import dnv_sf1
from crane_statics.rules.types import CaseSpec
from crane_statics.rules.validation import RulesValidationError
from tests import rules_reference as ref

G = ref.G
GT283 = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
ROPE_T = 1.5
K = 5000.0


def _doc(cabin=False, daf=1.0, speed=0.5):
    doc = load_document(GT283)
    hoists = [
        h.model_copy(update={"hook_daf": daf, "max_hoisting_speed_m_s": speed}) for h in doc.hoists
    ]
    rules = RulesSpec(standard="DNV", cabin_above_slewing_bearing=cabin)
    return doc.model_copy(update={"rules": rules, "hoists": hoists})


def _motion(roll=3.0, pitch=-2.0):
    return VesselMotion(
        accel_x_m_s2=0.4,
        accel_y_m_s2=-0.3,
        accel_z_m_s2=0.5,
        roll_deg=roll,
        pitch_deg=pitch,
        reference_x_m=4.0,
        reference_z_m=-2.0,
        pitch_angular_accel_rad_s2=0.02,
        roll_angular_accel_rad_s2=0.03,
    )


def _cond(lift="onboard", **kw):
    return ConditionSpec(name="c", lift=lift, wind_speed_m_s=12.0, vessel_motion=_motion(), **kw)


def _offboard(h_sig=2.0, v_in=0.8, v_t=0.6, **kw):
    return _cond("offboard", significant_wave_height_m=h_sig, v_in_m_s=v_in, v_t_m_s=v_t, **kw)


def _hoist_mode(doc):
    hoist_id = payload_hoist_ids(doc)[0]
    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    return hoist_id, iter_hoist_analysis_modes(hoist)[0]


def _setup(doc, cond, chart_max_load_t=50.0, profile=None, hook_t=None, rope_t=ROPE_T, **kw):
    hoist_id, mode = _hoist_mode(doc)
    if hook_t is not None:
        mode = dataclasses.replace(mode, lower_block_mass_t=hook_t)
    profile = profile or DnvProfile()
    kw.setdefault("support_x_m", 0.0)
    return profile.lift_setup(doc, cond, hoist_id, mode, K, rope_t, chart_max_load_t, **kw)


def _chart_t_for_w(doc, w_kN):
    """Chart max load giving a working load (chart + hook + rope) of ``w_kN``."""
    _, mode = _hoist_mode(doc)
    return w_kN / G - mode.lower_block_mass_t - ROPE_T


def _factor_at(factor, w_kN, hook_t=2.0):
    """Hook force / W at a working load of ``w_kN`` (payload + hook + suspended rope)."""
    payload = w_kN / G - hook_t - ROPE_T
    return factor.hook_force_kN(payload, hook_t, G) / w_kN


# --- cases -------------------------------------------------------------------------------


def test_two_cases_case_ii_heel_trim_is_1_5_times_case_i():
    cond = _cond()
    case_i, case_ii = DnvProfile().cases(_doc(), cond)
    assert case_i.name == "Case I"
    assert case_ii.name == "Case II"
    assert case_i.vessel_motion.roll_deg == 3.0
    assert case_i.vessel_motion.pitch_deg == -2.0
    assert case_ii.vessel_motion.roll_deg == pytest.approx(1.5 * case_i.vessel_motion.roll_deg)
    assert case_ii.vessel_motion.pitch_deg == pytest.approx(1.5 * case_i.vessel_motion.pitch_deg)


def test_case_wind_i_zero_ii_per_condition():
    case_i, case_ii = DnvProfile().cases(_doc(), _cond())
    assert case_i.wind_speed_m_s == 0.0
    assert case_ii.wind_speed_m_s == 12.0


@pytest.mark.parametrize("index", [0, 1])
def test_cases_have_zero_accelerations(index):
    motion = DnvProfile().cases(_doc(), _cond())[index].vessel_motion
    assert motion.accel_x_m_s2 == 0.0
    assert motion.accel_y_m_s2 == 0.0
    assert motion.accel_z_m_s2 == 0.0
    assert motion.pitch_angular_accel_rad_s2 == 0.0
    assert motion.roll_angular_accel_rad_s2 == 0.0


ACCEL_WARNING = (
    "conditions.c.vessel_motion: vessel accelerations are not applied under DNV: "
    "ship-motion inertia is Case III, out of scope"
)


@pytest.mark.parametrize("lift", ["onboard", "offboard"])
def test_nonzero_vessel_accelerations_warn_they_are_not_applied(lift):
    cond = _cond() if lift == "onboard" else _offboard()
    for case in DnvProfile().cases(_doc(), cond):
        setup = _setup(_doc(), cond, case=case)
        assert setup.warnings.count(ACCEL_WARNING) == 1


@pytest.mark.parametrize(
    "field",
    [
        "accel_x_m_s2",
        "accel_y_m_s2",
        "accel_z_m_s2",
        "pitch_angular_accel_rad_s2",
        "roll_angular_accel_rad_s2",
    ],
)
def test_any_single_nonzero_acceleration_warns(field):
    motion = VesselMotion(roll_deg=3.0, **{field: 0.1})
    cond = ConditionSpec(name="c", wind_speed_m_s=12.0, vessel_motion=motion)
    assert ACCEL_WARNING in _setup(_doc(), cond).warnings


def test_zero_accelerations_do_not_warn():
    motion = VesselMotion(roll_deg=3.0, pitch_deg=-2.0, reference_x_m=4.0)
    cond = ConditionSpec(name="c", wind_speed_m_s=12.0, vessel_motion=motion)
    assert not any("accelerations" in w for w in _setup(_doc(), cond).warnings)


def test_support_x_m_is_keyword_required():
    param = inspect.signature(DnvProfile.lift_setup).parameters["support_x_m"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


@pytest.mark.parametrize("lift", ["onboard", "offboard"])
def test_zero_working_load_does_not_raise(lift):
    # No hook mass, no load chart, no suspended rope: the curve's maximum W is 0 kN.
    cond = _cond() if lift == "onboard" else _offboard()
    setup = _setup(_doc(cabin=True), cond, chart_max_load_t=0.0, hook_t=0.0, rope_t=0.0)
    assert not any(r.quantity == "dynamic_factor" and r.source == "computed" for r in setup.records)
    assert any("maximum working load is 0 kN" in w for w in setup.warnings)
    for record in setup.records:
        assert math.isfinite(record.value)
    floor = next(r for r in setup.records if r.quantity == "psi_floor")
    assert floor.value == 1.3
    assert setup.factor.hook_force_kN(1000.0 / G, 0.0, G) / 1000.0 >= 1.3


def test_clause_strings_carry_printed_pages():
    case_i, case_ii = DnvProfile().cases(_doc(), _cond())
    clauses_i = {r.quantity: r.clause for r in _setup(_doc(), _cond(), case=case_i).records}
    clauses_ii = {r.quantity: r.clause for r in _setup(_doc(), _cond(), case=case_ii).records}
    assert clauses_i["list_trim_incline"] == "DNV-ST-0378 4.1.2.3, Table 4-1, p.54"
    assert clauses_ii["list_trim_incline"] == "DNV-ST-0378 4.2.3.2, p.58"
    assert clauses_i["load_wind_area"] == "DNV-ST-0378 4.2.3.3, p.58"
    assert clauses_ii["load_wind_force"] == "DNV-ST-0378 4.2.3.3, p.58"


# --- dynamic factor ----------------------------------------------------------------------


def test_offboard_psi_matches_oracle():
    setup = _setup(_doc(speed=0.5), _offboard(h_sig=2.0, v_in=0.8, v_t=0.6))
    assert isinstance(setup.factor, MaxFactor)
    v_r = ref.dnv_v_r(0.5, 0.8, 0.6, 2.0)
    expected = ref.dnv_psi(K, 1000.0, v_r)
    assert expected == pytest.approx(1.928098, abs=1e-6)
    assert _factor_at(setup.factor, 1000.0) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("w_kN, floor", [(2000.0, 1.3), (6000.0, 1.1)])
def test_offboard_psi_never_below_floor(w_kN, floor):
    doc = _doc(speed=0.5)
    cond = _offboard(h_sig=0.0, v_in=0.0, v_t=0.0)
    setup = _setup(doc, cond, chart_max_load_t=_chart_t_for_w(doc, w_kN))
    assert ref.dnv_psi_floor(w_kN) == pytest.approx(floor)
    v_r = ref.dnv_v_r(0.5, 0.0, 0.0, 0.0)
    psi = ref.dnv_psi(K, w_kN, v_r)
    assert psi < floor  # the floor governs at this working load
    assert _factor_at(setup.factor, w_kN) == pytest.approx(floor, rel=1e-12)


def test_offboard_floor_from_chart_max_applies_at_every_load():
    """The floor is fixed by the chart's maximum working load, psi by the point's W."""
    doc = _doc(speed=0.5)
    cond = _offboard(h_sig=0.0, v_in=0.0, v_t=0.0)
    setup = _setup(doc, cond, chart_max_load_t=_chart_t_for_w(doc, 6000.0))
    w = 100000.0
    assert _factor_at(setup.factor, w) == pytest.approx(1.1, rel=1e-12)
    w_small = 50.0
    v_r = ref.dnv_v_r(0.5, 0.0, 0.0, 0.0)
    assert _factor_at(setup.factor, w_small) == pytest.approx(
        max(1.1, ref.dnv_psi(K, w_small, v_r)), rel=1e-12
    )


@pytest.mark.parametrize("w_kN", [2000.0, 3000.0, 3750.0, 6000.0])
def test_onboard_is_floor_only(w_kN):
    doc = _doc()
    setup = _setup(doc, _cond(), chart_max_load_t=_chart_t_for_w(doc, w_kN))
    floor = ref.dnv_psi_floor(w_kN)
    assert isinstance(setup.factor, LinearFactor)
    assert setup.factor.extra_mass_t == ROPE_T
    assert _factor_at(setup.factor, w_kN) == pytest.approx(floor, rel=1e-12)


def test_v_h_matches_oracle():
    for h_s in (0.0, 1.0, 2.0, 4.5):
        assert dnv_v_h(h_s) == pytest.approx(ref.dnv_v_h(h_s), rel=1e-12)


def test_hoisting_speed_below_v_h_warns_and_keeps_speed():
    setup = _setup(_doc(speed=0.2), _offboard(h_sig=2.0))
    assert ref.dnv_v_h(2.0) > 0.2
    speed = [w for w in setup.warnings if "VH" in w]
    assert len(speed) == 1
    assert "0.2" in speed[0]
    assert "shaded" in speed[0]
    assert "deferred" in speed[0]
    v_r = ref.dnv_v_r(0.2, 0.8, 0.6, 2.0)
    assert _factor_at(setup.factor, 1000.0) == pytest.approx(
        max(1.3, ref.dnv_psi(K, 1000.0, v_r)), rel=1e-12
    )


def test_hoisting_speed_at_or_above_v_h_has_no_warning():
    setup = _setup(_doc(speed=0.5), _offboard(h_sig=2.0))
    assert not any("VH" in w for w in setup.warnings)


def test_zero_load_wind_area_has_no_default_area_warning():
    assert _setup(_doc(), _cond()).warnings == (ACCEL_WARNING,)


def test_manual_daf_overrides_and_keeps_computed_record():
    doc = _doc(daf=1.45, speed=0.5)
    setup = _setup(doc, _offboard())
    assert setup.factor == LinearFactor(1.45, ROPE_T)
    assert _factor_at(setup.factor, 1000.0) == pytest.approx(1.45, rel=1e-12)
    sources = {r.source: r for r in setup.records if r.quantity == "dynamic_factor"}
    assert set(sources) == {"computed", "override"}
    assert sources["override"].value == 1.45
    _, mode = _hoist_mode(doc)
    w = (50.0 + mode.lower_block_mass_t + ROPE_T) * G
    v_r = ref.dnv_v_r(0.5, 0.8, 0.6, 2.0)
    expected = max(ref.dnv_psi_floor(w), ref.dnv_psi(K, w, v_r))
    assert sources["computed"].value == pytest.approx(expected, rel=1e-12)


def test_default_daf_is_not_an_override():
    setup = _setup(_doc(daf=1.0), _cond())
    assert all(r.source == "computed" for r in setup.records)


# --- foundation --------------------------------------------------------------------------


@pytest.mark.parametrize("swl", [0.0, 1000.0, 2499.0, 2500.0, 6000.0])
def test_sf1_matches_oracle(swl):
    assert dnv_sf1(swl) == pytest.approx(ref.dnv_sf1(swl))


@pytest.mark.parametrize("swl_kN, sf1", [(1000.0, 1.3), (3000.0, 1.1)])
def test_sf1_with_cabin_flag(swl_kN, sf1):
    setup = _setup(_doc(cabin=True), _cond(), chart_max_load_t=swl_kN / G)
    assert setup.foundation.dead_factor == pytest.approx(sf1)
    assert setup.foundation.live_factor(123.0) == pytest.approx(sf1)
    assert setup.foundation.live_factor(9000.0) == pytest.approx(sf1)
    assert setup.retaining_live_factor == 1.0


def test_sf1_is_one_without_cabin_flag():
    setup = _setup(_doc(cabin=False), _cond(), chart_max_load_t=1000.0 / G)
    assert setup.foundation.dead_factor == 1.0
    assert setup.foundation.live_factor(1000.0) == 1.0
    assert setup.retaining_live_factor == 1.0


# --- lateral -----------------------------------------------------------------------------


def test_lateral_default_case_i():
    cond = _cond().model_copy(update={"load_wind_area_m2": 12.0, "load_drag_coefficient": 1.2})
    lateral = _setup(_doc(), cond).lateral
    assert lateral.accel_fraction_x == 0.0
    assert lateral.accel_fraction_y == 0.0
    assert lateral.min_fraction == 0.0
    assert lateral.incline_deg == pytest.approx(math.hypot(3.0, 2.0))
    assert lateral.wind_area_m2 == 12.0
    assert lateral.wind_cd == 1.2


def test_lateral_case_ii_incline():
    doc, cond = _doc(), _cond()
    case_ii = DnvProfile().cases(doc, cond)[1]
    lateral = _setup(doc, cond, case=case_ii).lateral
    assert lateral.incline_deg == pytest.approx(1.5 * math.hypot(3.0, 2.0))
    incline = next(
        r for r in _setup(doc, cond, case=case_ii).records if r.quantity == "list_trim_incline"
    )
    assert incline.value == pytest.approx(lateral.incline_deg)


# --- records and shared interface --------------------------------------------------------


def test_records_carry_clause_formula_and_inputs():
    setup = _setup(_doc(cabin=True), _offboard())
    clauses = {r.quantity: r.clause for r in setup.records}
    assert "4.1.3.2" in clauses["dynamic_factor"]
    assert "8.2.2.1" in clauses["psi_floor"]
    assert "8.2.2.2" in clauses["min_hoisting_speed"]
    assert "8.2.2.4" in clauses["pedestal_factor"]
    for record in setup.records:
        assert record.clause.startswith("DNV-ST-0378 ")
        assert record.formula
        assert math.isfinite(record.value)
    dyn = next(r for r in setup.records if r.quantity == "dynamic_factor")
    assert dyn.inputs["K_kN_m"] == K
    assert dyn.inputs["v_r_m_s"] == pytest.approx(ref.dnv_v_r(0.5, 0.8, 0.6, 2.0))


def test_offboard_missing_inputs_rejected():
    with pytest.raises(RulesValidationError):
        _setup(_doc(), _cond("offboard"))
    with pytest.raises(RulesValidationError):
        _setup(_doc(speed=None), _offboard())


def test_non_dnv_document_rejected():
    doc = _doc().model_copy(update={"rules": RulesSpec(standard="ABS", crane_class="offshore")})
    with pytest.raises(RulesValidationError):
        _setup(doc, _cond())
    with pytest.raises(RulesValidationError):
        DnvProfile().cases(doc, _cond())


def test_abs_lift_setup_accepts_case_keyword():
    doc = _doc().model_copy(update={"rules": RulesSpec(standard="ABS", crane_class="offshore")})
    cond = _cond()
    (case,) = AbsProfile().cases(doc, cond)
    with_case = _setup(doc, cond, profile=AbsProfile(), case=case)
    without = _setup(doc, cond, profile=AbsProfile())
    assert with_case.lateral == without.lateral
    assert with_case.factor == without.factor
    motion = case.vessel_motion.model_copy(update={"roll_deg": 6.0, "pitch_deg": 8.0})
    tilted = CaseSpec(case.name, case.wind_speed_m_s, motion)
    lateral = _setup(doc, cond, profile=AbsProfile(), case=tilted).lateral
    assert lateral.incline_deg == pytest.approx(10.0)


def test_profile_for():
    assert isinstance(profile_for(RulesSpec(standard="DNV")), DnvProfile)
    assert isinstance(profile_for(RulesSpec(standard="ABS", crane_class="offshore")), AbsProfile)
