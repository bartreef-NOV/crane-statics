"""ABS profile: dynamic factor, lateral spec, foundation factors and provenance."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crane_statics.core.analysis_cases import iter_hoist_analysis_modes
from crane_statics.core.io import load_document
from crane_statics.data.models import ConditionSpec, RulesSpec, VesselMotion, payload_hoist_ids
from crane_statics.rules.abs_profile import AbsProfile
from crane_statics.rules.factors import AbsOnboardFactor, LinearFactor, MaxFactor
from crane_statics.rules.foundation import abs_pedestal_factor
from crane_statics.rules.validation import RulesValidationError
from tests import rules_reference as ref

G = ref.G
GT283 = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
LL_KN = 1000.0
ROPE_T = 1.5
K = 5000.0


def _doc(crane_class="offshore", daf=1.0, speed=0.5):
    doc = load_document(GT283)
    hoists = [
        h.model_copy(update={"hook_daf": daf, "max_hoisting_speed_m_s": speed}) for h in doc.hoists
    ]
    return doc.model_copy(
        update={"rules": RulesSpec(standard="ABS", crane_class=crane_class), "hoists": hoists}
    )


def _cond(lift="onboard", accel_z=0.0, **kw):
    motion = VesselMotion(
        accel_x_m_s2=kw.pop("accel_x", 0.0),
        accel_y_m_s2=kw.pop("accel_y", 0.0),
        accel_z_m_s2=accel_z,
        roll_deg=kw.pop("roll", 0.0),
        pitch_deg=kw.pop("pitch", 0.0),
    )
    return ConditionSpec(name="c", lift=lift, wind_speed_m_s=12.0, vessel_motion=motion, **kw)


def _offboard(h_sig=2.0, v_in=0.8, v_t=0.6, **kw):
    return _cond("offboard", significant_wave_height_m=h_sig, v_in_m_s=v_in, v_t_m_s=v_t, **kw)


def _setup(doc, cond, chart_max_load_t=50.0):
    hoist_id = payload_hoist_ids(doc)[0]
    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    mode = iter_hoist_analysis_modes(hoist)[0]
    return AbsProfile().lift_setup(doc, cond, hoist_id, mode, K, ROPE_T, chart_max_load_t)


def _factor_at(factor, ll_kN, hook_t=2.0):
    """Hook force / LL at a live load of ``ll_kN`` (payload + hook + suspended rope)."""
    payload = ll_kN / G - hook_t - ROPE_T
    return factor.hook_force_kN(payload, hook_t, G) / ll_kN


def test_offshore_onboard_factor_matches_oracle():
    setup = _setup(_doc(), _cond())
    assert isinstance(setup.factor, AbsOnboardFactor)
    expected = ref.abs_vaf_onboard(LL_KN, 0.0)
    assert expected == pytest.approx(1.181429, abs=1e-6)
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(expected, rel=1e-12)


def test_offshore_onboard_uses_vertical_acceleration():
    a_v = 0.04
    setup = _setup(_doc(), _cond(accel_z=-a_v * G))
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(
        ref.abs_vaf_onboard(LL_KN, a_v), rel=1e-12
    )


def test_heavy_lift_factor_matches_oracle():
    setup = _setup(_doc("heavy_lift"), _cond(accel_z=0.05 * G))
    assert isinstance(setup.factor, LinearFactor)
    expected = ref.abs_heavy_lift_vaf(0.05)
    assert expected == pytest.approx(1.15)
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(expected, rel=1e-12)


def test_offboard_factor_matches_oracle():
    setup = _setup(_doc(speed=0.5), _offboard(v_in=0.8, v_t=0.6))
    assert isinstance(setup.factor, MaxFactor)
    v_r = ref.abs_v_r(0.5, 0.8, 0.6)
    expected = ref.abs_vaf_offboard(LL_KN, K, v_r, 0.0)
    assert expected == pytest.approx(2.070883, abs=1e-6)
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(expected, rel=1e-12)


def test_offboard_factor_never_below_onboard():
    setup = _setup(_doc(speed=0.5), _offboard(v_in=0.0, v_t=0.0, accel_z=0.1 * G))
    ll = 200000.0  # large LL: the relative-velocity term is small
    v_r = ref.abs_v_r(0.5, 0.0, 0.0)
    assert _factor_at(setup.factor, ll) == pytest.approx(
        ref.abs_vaf_offboard(ll, K, v_r, 0.1), rel=1e-12
    )


def test_foundation_factors_offshore_and_heavy_lift():
    offshore = _setup(_doc(), _cond())
    heavy = _setup(_doc("heavy_lift"), _cond())
    assert offshore.foundation.live_factor(1000.0) == pytest.approx(
        ref.abs_pedestal_factor(1000.0, "offshore")
    )
    assert offshore.foundation.live_factor(1000.0) == pytest.approx(1.31)
    assert heavy.foundation.live_factor(3000.0) == pytest.approx(
        ref.abs_pedestal_factor(3000.0, "heavy_lift")
    )
    assert heavy.foundation.live_factor(3000.0) == pytest.approx(1.0)
    assert offshore.foundation.dead_factor == 1.0
    assert offshore.retaining_live_factor == 3.75


@pytest.mark.parametrize("ll", [0.0, 100.0, 1000.0, 1440.0, 2000.0, 3000.0, 5000.0])
@pytest.mark.parametrize("crane_class", ["offshore", "heavy_lift"])
def test_pedestal_factor_matches_oracle(ll, crane_class):
    assert abs_pedestal_factor(ll, crane_class) == pytest.approx(
        ref.abs_pedestal_factor(ll, crane_class), rel=1e-12
    )


def test_pedestal_factor_rejects_unknown_class():
    with pytest.raises(RulesValidationError):
        abs_pedestal_factor(1000.0, "shipboard")


def test_lateral_spec():
    cond = _cond(accel_x=0.5, accel_y=-0.3, roll=3.0, pitch=-4.0)
    cond = cond.model_copy(update={"load_wind_area_m2": 12.0, "load_drag_coefficient": 1.2})
    lateral = _setup(_doc(), cond).lateral
    assert lateral.min_fraction == 0.02
    assert lateral.accel_fraction_x == pytest.approx(0.5 / G)
    assert lateral.accel_fraction_y == pytest.approx(0.3 / G)
    assert lateral.incline_deg == pytest.approx(5.0)
    l_kN = 1000.0
    assert l_kN * math.sin(math.radians(lateral.incline_deg)) == pytest.approx(
        ref.abs_list_trim_load(l_kN, 3.0, -4.0)
    )
    assert lateral.wind_area_m2 == 12.0
    assert lateral.wind_cd == 1.2


def test_manual_daf_overrides_and_keeps_computed_record():
    setup = _setup(_doc(daf=1.4), _cond())
    assert setup.factor == LinearFactor(1.4, ROPE_T)
    # The suspended rope stays in LL: the effective factor on the whole LL is the daf.
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(1.4, rel=1e-12)
    dyn = [r for r in setup.records if r.quantity == "dynamic_factor"]
    sources = {r.source: r for r in dyn}
    assert set(sources) == {"computed", "override"}
    assert sources["override"].value == 1.4
    doc = _doc()
    hoist = next(h for h in doc.hoists if h.id == payload_hoist_ids(doc)[0])
    ll = (50.0 + hoist.hook_mass_t + ROPE_T) * G
    assert sources["computed"].value == pytest.approx(ref.abs_vaf_onboard(ll, 0.0), rel=1e-12)


def test_heavy_lift_manual_daf_overrides_and_keeps_rope():
    setup = _setup(_doc("heavy_lift", daf=1.25), _cond(accel_z=0.05 * G))
    assert setup.factor == LinearFactor(1.25, ROPE_T)
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(1.25, rel=1e-12)
    sources = {r.source: r for r in setup.records if r.quantity == "dynamic_factor"}
    assert sources["override"].value == 1.25
    assert sources["computed"].value == pytest.approx(ref.abs_heavy_lift_vaf(0.05), rel=1e-12)
    assert "2-2/11.3" in sources["override"].clause


def test_zero_load_wind_area_warns_default_area_not_applied():
    assert any("5.19.3" in w for w in _setup(_doc(), _cond()).warnings)
    cond = _cond().model_copy(update={"load_wind_area_m2": 10.0})
    assert not any("5.19.3" in w for w in _setup(_doc(), cond).warnings)


def test_default_daf_is_not_an_override():
    setup = _setup(_doc(daf=1.0), _cond())
    assert all(r.source == "computed" for r in setup.records)
    assert isinstance(setup.factor, AbsOnboardFactor)


def test_records_carry_clause_formula_and_inputs():
    setup = _setup(_doc(), _offboard())
    clauses = {r.quantity: r.clause for r in setup.records}
    assert "2-2/9.3.2" in clauses["dynamic_factor"]
    assert "2-2/5.15" in clauses["pedestal_factor"]
    assert "2-2/5.13.5(c)" in clauses["retaining_live_factor"]
    for record in setup.records:
        assert record.clause.startswith("ABS ")
        assert "p." in record.clause
        assert record.formula
        assert math.isfinite(record.value)
    dyn = next(r for r in setup.records if r.quantity == "dynamic_factor")
    assert dyn.inputs["K_kN_m"] == K
    assert dyn.inputs["v_r_m_s"] == pytest.approx(ref.abs_v_r(0.5, 0.8, 0.6))


def test_heavy_lift_clause():
    setup = _setup(_doc("heavy_lift"), _cond())
    dyn = next(r for r in setup.records if r.quantity == "dynamic_factor")
    assert "2-2/11.3" in dyn.clause


def test_hoisting_speed_below_minimum_warns_and_keeps_speed():
    setup = _setup(_doc(speed=0.15), _offboard(h_sig=2.0))
    v_hmin = ref.abs_v_hmin(2.0)
    assert v_hmin > 0.15
    speed = [w for w in setup.warnings if "v_hmin" in w]
    assert len(speed) == 1
    assert "0.15" in speed[0]
    v_r = ref.abs_v_r(0.15, 0.8, 0.6)
    assert _factor_at(setup.factor, LL_KN) == pytest.approx(
        ref.abs_vaf_offboard(LL_KN, K, v_r, 0.0), rel=1e-12
    )


def test_hoisting_speed_at_minimum_has_no_warning():
    setup = _setup(_doc(speed=0.5), _offboard(h_sig=2.0))
    assert not any("v_hmin" in w for w in setup.warnings)


def test_cases_single_in_service():
    cond = _cond(accel_z=0.3, roll=2.0)
    cases = AbsProfile().cases(_doc(), cond)
    assert len(cases) == 1
    assert cases[0].name == "In-service"
    assert cases[0].wind_speed_m_s == 12.0
    assert cases[0].vessel_motion == cond.vessel_motion


def test_non_abs_document_rejected():
    doc = _doc().model_copy(update={"rules": RulesSpec(standard="DNV")})
    with pytest.raises(RulesValidationError):
        _setup(doc, _cond())
