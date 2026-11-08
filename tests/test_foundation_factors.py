"""Pedestal (ABS PF, DNV SF1) and retaining-component (ABS 3.75) load factors (Task 12).

The factored demand of a platform-base limit is ``dead * baseline + live(LL) * s * H``
(``calculation.allowable.DemandScale``), LL the unamplified live load in kN.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import pytest

from crane_statics.calculation import CraneCalculator
from crane_statics.calculation.allowable import DemandScale
from crane_statics.calculation.engine import compute_platform_base_max_bearing_line_load_kN_per_m
from crane_statics.core import load_document
from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.lift_factor import LiftFactors, demand_scales, live_load_kN
from crane_statics.core.limit_factory import DesignLimitFactory
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from tests import rules_reference as ref
from tests.rules_docs import gale, rules_doc

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
G = 9.81
DAF = 1.3
HOOK_T = 2.0


@pytest.fixture(scope="module")
def solved():
    calc = CraneCalculator(load_document(EXAMPLE))
    point = calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
    assert point is not None
    return calc, point


def _fz(point) -> tuple[float, float]:
    return (
        float(point.baseline_reactions["platform_base"]["Fz"]),
        float(point.sensitivity_reactions["platform_base"]["Fz"]),
    )


def _ll(hook_kN: float) -> float:
    """The unamplified live load at hook force ``hook_kN`` (constant DAF, hook mass)."""
    return (max(0.0, hook_kN / DAF / G - HOOK_T) + HOOK_T) * G


def _cap(calc, point, limits, scale=None):
    return calc.compute_allowable_load(
        point, limits, hook_daf=DAF, hook_mass_t=HOOK_T, demand_scale=scale
    ).max_allowable_load_kN


def test_no_scale_equals_todays_capacity(solved) -> None:
    calc, point = solved
    b, s = _fz(point)
    limits = {
        "platform_base_Fz": {"Fz": b + 400.0 * s},
        "platform_base_fradial": {"fradial": 500.0},
        "boom_hoist_T": {"T": 3000.0},
    }
    today = calc.compute_allowable_load(point, limits, hook_daf=DAF, hook_mass_t=HOOK_T)
    no_scales: tuple[Optional[dict[str, DemandScale]], ...] = (None, {})
    for scale in no_scales:
        capacity = calc.compute_allowable_load(
            point, limits, hook_daf=DAF, hook_mass_t=HOOK_T, demand_scale=scale
        )
        assert capacity == today


def test_constant_live_factor_divides_the_linear_capacity(solved) -> None:
    calc, point = solved
    b, s = _fz(point)
    limit = b + 400.0 * s
    capacity = _cap(
        calc,
        point,
        {"platform_base_Fz": {"Fz": limit}},
        {"platform_base": DemandScale(live=lambda _ll: 1.2)},
    )
    assert capacity == pytest.approx((limit - b) / (1.2 * s), rel=1e-9)


def test_abs_pedestal_factor_solves_the_monotone_equation(solved) -> None:
    calc, point = solved
    b, s = _fz(point)
    h_target = 1000.0  # LL = 769 kN: PF in its linear range (1.368)
    pf_target = ref.abs_pedestal_factor(_ll(h_target), "offshore")
    assert 1.2 < pf_target < 1.5
    limit = b + pf_target * s * h_target
    scale = DemandScale(live=lambda ll: ref.abs_pedestal_factor(ll, "offshore"))
    capacity = _cap(calc, point, {"platform_base_Fz": {"Fz": limit}}, {"platform_base": scale})
    demand = b + ref.abs_pedestal_factor(_ll(capacity), "offshore") * s * capacity
    assert demand == pytest.approx(limit, abs=1e-6)
    assert capacity == pytest.approx(h_target, rel=1e-9)


def test_scale_applies_to_magnitude_limits(solved) -> None:
    calc, point = solved
    base = point.baseline_reactions["platform_base"]
    sens = point.sensitivity_reactions["platform_base"]
    d = float(calc.doc.support_widths.slewing_bearing_diameter_m)
    limit = compute_platform_base_max_bearing_line_load_kN_per_m(
        fz_kN=base["Fz"] + 500.0 * sens["Fz"],
        mx_kNm=base.get("Mx", 0.0) + 500.0 * sens.get("Mx", 0.0),
        my_kNm=base.get("My", 0.0) + 500.0 * sens.get("My", 0.0),
        slewing_bearing_diameter_m=d,
    )
    limits = {"platform_base_max_bearing_line_load": {"max_bearing_line_load": limit}}
    plain = _cap(calc, point, limits)
    scaled = _cap(calc, point, limits, {"platform_base": DemandScale(live=lambda _ll: 1.5)})
    # A constant live factor scales only the H term: the capacity is exactly H / 1.5.
    assert plain == pytest.approx(500.0, rel=1e-6)
    assert scaled == pytest.approx(plain / 1.5, rel=1e-6)


def test_retaining_limit_takes_the_retaining_factor(solved) -> None:
    calc, point = solved
    b, s = _fz(point)
    limit = b + 2000.0 * s
    scales = {
        "platform_base": DemandScale(live=lambda _ll: 1.5),
        "platform_base_retaining": DemandScale(live=lambda _ll: 3.75, dead=1.0),
    }
    capacity = calc.compute_allowable_load(
        point,
        {"platform_base_retaining_Fz": {"Fz": limit}},
        hook_daf=DAF,
        hook_mass_t=HOOK_T,
        demand_scale=scales,
    )
    assert capacity.max_allowable_load_kN == pytest.approx((limit - b) / (3.75 * s), rel=1e-9)
    assert capacity.governing_limit_id == "platform_base_retaining_Fz"


def test_dnv_sf1_scales_dead_and_live_terms(solved) -> None:
    calc, point = solved
    b, s = _fz(point)
    sf1 = ref.dnv_sf1(1000.0)
    limit = 2.0 * b + 400.0 * s
    capacity = _cap(
        calc,
        point,
        {"platform_base_Fz": {"Fz": limit}},
        {"platform_base": DemandScale(live=lambda _ll: sf1, dead=sf1)},
    )
    assert capacity == pytest.approx((limit - sf1 * b) / (sf1 * s), rel=1e-9)


def test_scale_leaves_other_entities_alone(solved) -> None:
    calc, point = solved
    limits = {"boom_hoist_T": {"T": 3000.0}, "heel_point_Fz": {"Fz": 5000.0}}
    scale = {"platform_base": DemandScale(live=lambda _ll: 1.5, dead=1.3)}
    assert _cap(calc, point, limits, scale) == pytest.approx(_cap(calc, point, limits), rel=1e-9)


# --- core: limits, scales, rows ------------------------------------------------------------


def test_retaining_limits_only_on_an_abs_document() -> None:
    legacy = {dl.id for dl in DesignLimitFactory.create_for_document(load_document(EXAMPLE))}
    assert not any("retaining" in lid for lid in legacy)
    dnv = {dl.id for dl in DesignLimitFactory.create_for_document(rules_doc("DNV", gale()))}
    assert not any("retaining" in lid for lid in dnv)
    abs_limits = DesignLimitFactory.create_for_document(rules_doc("ABS", gale()))
    platform = {dl.component for dl in abs_limits if dl.entity_id == "platform_base"}
    retaining = {dl.component for dl in abs_limits if dl.entity_id == "platform_base_retaining"}
    assert retaining == platform
    assert all(
        dl.id == f"platform_base_retaining_{dl.component}"
        for dl in abs_limits
        if dl.entity_id == "platform_base_retaining"
    )


def test_core_scales_follow_the_lift_setup() -> None:
    from crane_statics.core.lift_factor import legacy_lift_setup

    doc = rules_doc("ABS", gale())
    hoist = next(h for h in doc.hoists if h.id == "MH")
    assert demand_scales(legacy_lift_setup(hoist), lambda h: h) is None

    from crane_statics.core.lift_factor import LiftFactors
    from crane_statics.core.load_condition import condition_cases
    from crane_statics.core.analysis_cases import analysis_mode_by_name

    condition = condition_cases(doc, None)[0]
    mode = analysis_mode_by_name(hoist, "normal")
    setup = LiftFactors(doc, CraneCalculator(doc)).setup(condition, "MH", mode, 45.0)
    scales = demand_scales(setup, lambda h: h)
    assert scales is not None
    assert scales["platform_base"].dead == 1.0
    assert scales["platform_base"].live(1000.0) == pytest.approx(
        ref.abs_pedestal_factor(1000.0, "offshore")
    )
    assert scales["platform_base_retaining"].live(1000.0) == 3.75
    assert scales["platform_base_retaining"].dead == 1.0
    # LL: the payload the factor's inverse gives, plus hook block and suspended rope.
    factor = setup.factor
    hook_kN = factor.hook_force_kN(50.0, 3.0, G)
    assert live_load_kN(factor, hook_kN, 3.0, 0.7, G) == pytest.approx((50.0 + 3.0 + 0.7) * G)


def _rows(doc):
    session = SessionModel()
    session.set_document(doc)
    hoist_svc = HoistStateService(session)
    calculator = AnalysisCalculator(session, KinematicsService(session), hoist_svc)
    pt = calculator.compute_analysis_point()
    assert pt is not None
    hook_kN = 800.0
    _ropes, conn_rows = calculator.compute_result_rows(pt, hook_load_kN=hook_kN)
    return session, hoist_svc, pt, hook_kN, conn_rows


def test_legacy_rows_have_no_factored_rows() -> None:
    *_, rows = _rows(load_document(EXAMPLE))
    assert not any(r.kind == "factored" for r in rows)


def test_abs_rows_add_pedestal_and_retaining_rows() -> None:
    doc = rules_doc("ABS", gale())
    session, hoist_svc, pt, hook_kN, rows = _rows(doc)
    factored = {(r.name, r.component): r for r in rows if r.kind == "factored"}
    assert factored
    pf_row = factored[("Platform Base (ABS PF) / Fz", "Fz")]
    ret_row = factored[("Retaining / Fz", "Fz")]
    hoist_id = session.selected_hoist_id
    hoist = session.payload_hoist_by_id(hoist_id)
    _falls, hook_t, _ = hoist_svc.effective_hoist_parameters(hoist_id)
    ll = live_load_kN(
        hoist_svc.dynamic_factor(hoist),
        hook_kN,
        hook_t,
        hoist_svc.suspended_rope_mass_t(hoist_id),
        G,
    )
    b, s = _fz(pt)
    pf = ref.abs_pedestal_factor(ll, "offshore")
    assert pf_row.demand_kN == pytest.approx(b + pf * s * hook_kN, rel=1e-9)
    assert ret_row.demand_kN == pytest.approx(b + 3.75 * s * hook_kN, rel=1e-9)


def test_dnv_rows_label_sf1_and_have_no_retaining_rows() -> None:
    doc = rules_doc("DNV", gale())
    assert doc.rules is not None
    doc = doc.model_copy(
        update={"rules": doc.rules.model_copy(update={"cabin_above_slewing_bearing": True})}
    )
    _session, _hoist_svc, pt, hook_kN, rows = _rows(doc)
    factored = [r for r in rows if r.kind == "factored"]
    assert factored and all(r.name.startswith("Platform Base (DNV SF1) / ") for r in factored)
    row = next(r for r in factored if r.component == "Fz")
    b, s = _fz(pt)
    sf1 = row.demand_kN / (b + s * hook_kN)
    assert sf1 in (pytest.approx(1.3), pytest.approx(1.1))


def test_abs_sweep_applies_the_pedestal_factor_to_platform_limits(monkeypatch) -> None:
    doc = rules_doc("ABS", gale())
    calc = CraneCalculator(doc)
    point = calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
    assert point is not None
    b, s = _fz(point)
    limits = {"platform_base_Fz": {"Fz": 1.5 * b + 300.0 * s}}
    factored = run_mode_sweep(doc, "MH", "normal", limits, 5.0, {})
    assert factored is not None
    monkeypatch.setattr(LiftFactors, "demand_scales", lambda *_a, **_k: None)
    plain = run_mode_sweep(doc, "MH", "normal", limits, 5.0, {})
    assert plain is not None
    pairs = list(zip(dict(plain["curve_data"]).values(), dict(factored["curve_data"]).values()))
    assert pairs and all(f <= p + 1e-9 for p, f in pairs)
    assert any(f < p - 1e-6 for p, f in pairs if math.isfinite(p))


@pytest.mark.parametrize("component", ["fradial", "max_bearing_line_load"])
def test_envelope_magnitude_pruning_is_exact_under_a_load_dependent_scale(
    monkeypatch, component
) -> None:
    from crane_statics.core import chart_envelope
    from crane_statics.core.chart_envelope import build_probes, envelope_capacity
    from crane_statics.data.models import VesselMotion

    doc = rules_doc("ABS", gale())
    calc = CraneCalculator(doc)
    vessel = VesselMotion(accel_x_m_s2=0.8, roll_deg=4.0, pitch_deg=2.5)
    probes = build_probes(calc, "MH", 45.0, 0.0, None, vessel=vessel)
    assert probes is not None
    from crane_statics.core.demand_extraction import extract_connection_component_response

    demand0 = extract_connection_component_response(
        probes.zero,
        0.0,
        "platform_base",
        component,
        support_widths_diameter_m=doc.support_widths.slewing_bearing_diameter_m,
    )
    assert demand0 is not None
    # Above the zero-hook demand of every case, reached at a finite hook load.
    margin = 0.5 * abs(probes.zero.baseline_reactions["platform_base"]["Fz"])
    if component != "fradial":
        margin = 200.0
    limits = {f"platform_base_{component}": {component: 3.0 * abs(demand0) + margin}}
    scale = {"platform_base": DemandScale(live=lambda ll: ref.abs_pedestal_factor(ll, "offshore"))}

    def run(scales):
        return envelope_capacity(
            calc,
            probes,
            limits,
            vessel=vessel,
            offlead_deg=2.0,
            sidelead_deg=1.0,
            hook_daf=DAF,
            hook_mass_t=HOOK_T,
            demand_scale=scales,
        ).max_allowable_load_kN

    plain, pruned = run(None), run(scale)
    monkeypatch.setattr(chart_envelope, "_EXACT_CANDIDATES", 10**9)
    exhaustive = run(scale)
    assert pruned == pytest.approx(exhaustive, rel=1e-12)
    assert pruned < plain


def test_auto_set_takes_the_factored_demand(monkeypatch) -> None:
    from crane_statics.core.limit_auto_set import compute_required_connection_capacity_kN

    doc = rules_doc("ABS", gale())
    pedestal = compute_required_connection_capacity_kN(doc, "platform_base", "Fz").required_kN
    retaining = compute_required_connection_capacity_kN(
        doc, "platform_base_retaining", "Fz"
    ).required_kN
    monkeypatch.setattr(LiftFactors, "demand_scales", lambda *_a, **_k: None)
    plain = compute_required_connection_capacity_kN(doc, "platform_base", "Fz").required_kN
    assert plain is not None and pedestal is not None and retaining is not None
    assert plain < pedestal < retaining


# --- review round 1 -----------------------------------------------------------------------


def test_dnv_without_cabin_has_no_foundation_scale() -> None:
    """SF1 does not apply: no scales, plain rows keep their limit, no factored rows."""
    from crane_statics.core.analysis_cases import analysis_mode_by_name
    from crane_statics.core.load_condition import condition_cases
    from crane_statics.rules.types import NEUTRAL_FOUNDATION

    doc = rules_doc("DNV", gale())
    assert doc.rules is not None and not doc.rules.cabin_above_slewing_bearing
    hoist = next(h for h in doc.hoists if h.id == "MH")
    lift = LiftFactors(doc, CraneCalculator(doc))
    for condition in condition_cases(doc, None):
        mode = analysis_mode_by_name(hoist, "normal")
        setup = lift.setup(condition, "MH", mode, 45.0)
        assert setup.foundation is NEUTRAL_FOUNDATION
        assert lift.demand_scales(condition, "MH", mode, 45.0, setup) is None

    session = SessionModel()
    session.set_document(doc)
    limit = session.design_limits_by_id["platform_base_Fz"]
    limit.max_kN, limit.enabled = 1.0e6, True
    calculator = AnalysisCalculator(session, KinematicsService(session), HoistStateService(session))
    pt = calculator.compute_analysis_point()
    assert pt is not None
    _ropes, rows = calculator.compute_result_rows(pt, hook_load_kN=800.0)
    assert not any(r.kind == "factored" for r in rows)
    plain = next(r for r in rows if r.entity_id == "platform_base" and r.component == "Fz")
    assert plain.limit_kN == 1.0e6 and plain.utilization_pct is not None


def test_retaining_limit_without_its_scale_raises(solved) -> None:
    calc, point = solved
    limits = {"platform_base_retaining_Fz": {"Fz": 1.0e6}}
    for scales in (None, {"platform_base": DemandScale(live=lambda _ll: 1.5)}):
        with pytest.raises(ValueError, match="platform_base_retaining"):
            calc.compute_allowable_load(point, limits, demand_scale=scales)


def test_factored_point_and_capacity_share_one_live_load_default(solved) -> None:
    from crane_statics.core.lift_factor import factored_point

    calc, point = solved
    b, s = _fz(point)
    scale = DemandScale(live=lambda ll: ref.abs_pedestal_factor(ll, "offshore"))
    limit = b + 900.0 * s
    capacity = _cap(calc, point, {"platform_base_Fz": {"Fz": limit}}, {"platform_base": scale})
    factored = factored_point(
        point, scale, capacity, "platform_base", hook_daf=DAF, hook_mass_t=HOOK_T, gravity_m_s2=G
    )
    demand = factored.baseline_reactions["platform_base"]["Fz"] + (
        factored.sensitivity_reactions["platform_base"]["Fz"] * capacity
    )
    assert demand == pytest.approx(limit, abs=1e-6)


def _windy_my(point):
    """``point`` with a 50 kN constant (load wind) lateral, and its platform-base My."""
    from crane_statics.calculation.hook_lateral import add_hook_lateral

    windy = add_hook_lateral(point, 0.0, 0.0, 50.0, 0.0)
    b0 = float(point.baseline_reactions["platform_base"]["My"])
    b1 = float(windy.baseline_reactions["platform_base"]["My"])
    s = float(windy.sensitivity_reactions["platform_base"]["My"])
    assert abs(b1 - b0) > 1000.0 and s > 0.0  # the constant loads My
    assert s == pytest.approx(float(point.sensitivity_reactions["platform_base"]["My"]))
    return windy, b0, b1, s


def test_retaining_factor_leaves_the_load_wind_constant_unscaled(solved) -> None:
    calc, point = solved
    windy, _b0, b1, s = _windy_my(point)
    limit = b1 + 1000.0 * s
    capacity = _cap(
        calc,
        windy,
        {"platform_base_retaining_My": {"My": limit}},
        {"platform_base_retaining": DemandScale(live=lambda _ll: 3.75, dead=1.0)},
    )
    # The wind term (in b1) at 1.0, the H term at 3.75.
    assert capacity == pytest.approx((limit - b1) / (3.75 * s), rel=1e-9)


def test_abs_pf_leaves_the_load_wind_unfactored_documented_limitation(solved) -> None:
    """Pins spec 9.7: ABS PF multiplies the H terms only, not the load wind (the
    non-conservative reading of 5.15, owner to confirm). The wind part stays at 1.0."""
    calc, point = solved
    windy, b0, b1, s = _windy_my(point)
    limit = b1 + 1000.0 * s
    scale = DemandScale(live=lambda ll: ref.abs_pedestal_factor(ll, "offshore"))
    capacity = _cap(calc, windy, {"platform_base_My": {"My": limit}}, {"platform_base": scale})
    pf = ref.abs_pedestal_factor(_ll(capacity), "offshore")
    assert pf > 1.2
    assert b1 + pf * s * capacity == pytest.approx(limit, abs=1e-6)
    # The conservative reading (PF on the wind too) would exceed the limit at this H.
    assert b0 + pf * (b1 - b0) + pf * s * capacity > limit + 1.0


def test_auto_set_values_match_the_hand_factored_demand(monkeypatch) -> None:
    from crane_statics.core.analysis_cases import analysis_mode_by_name
    from crane_statics.core.limit_auto_set import compute_required_connection_capacity_kN
    from crane_statics.core.load_condition import condition_document, load_conditions
    from tests.rules_docs import without_live_lateral

    without_live_lateral(monkeypatch)  # the governing lateral direction is not recorded
    doc = rules_doc("ABS", gale())
    (condition,) = load_conditions(doc)
    calc = CraneCalculator(condition_document(doc, condition))
    lift = LiftFactors(doc, calc)
    g = abs(float(doc.environment.gravity_m_s2))

    def hand(entity: str, live) -> None:
        result = compute_required_connection_capacity_kN(doc, entity, "Fz")
        assert result.required_kN is not None and result.governing_hoist_id is not None
        hoist = next(h for h in doc.hoists if h.id == result.governing_hoist_id)
        mode = analysis_mode_by_name(hoist, str(result.governing_mode))
        cp = mode.contractual_points[int(result.governing_cp_index or 0)]
        angle = float(result.governing_angle_deg or 0.0)
        pt = calc.compute_analysis_point(
            angle,
            0.0,
            hoist.id,
            wind_speed_m_s=condition.wind_speed_m_s,
            wind_direction=result.governing_wind_direction,
            offlead_deg=result.governing_offlead_deg,
            sidelead_deg=result.governing_sidelead_deg,
            hoist_runtime_overrides=mode.runtime_overrides,
            amplified_rope_hoist_id=hoist.id,
        )
        assert pt is not None
        setup = lift.setup(condition, hoist.id, mode, angle)
        hook_kN = setup.factor.hook_force_kN(cp.load_t, mode.hook_mass_t, g)
        rope_t = lift.suspended_rope_mass_t(hoist.id, mode, angle)
        ll = (cp.load_t + mode.hook_mass_t + rope_t) * g
        b, s = _fz(pt)
        assert result.required_kN == pytest.approx(abs(b + live(ll) * s * hook_kN), rel=1e-9)

    hand("platform_base", lambda ll: ref.abs_pedestal_factor(ll, "offshore"))
    hand("platform_base_retaining", lambda _ll: 3.75)


def test_dnv_sf1_envelope_scales_dead_and_live_terms() -> None:
    from crane_statics.core.analysis_cases import analysis_mode_by_name
    from crane_statics.core.chart_envelope import build_probes, envelope_capacity
    from crane_statics.core.lift_factor import chart_max_load_t
    from crane_statics.core.load_condition import condition_cases, condition_document

    doc = rules_doc("DNV", gale())
    assert doc.rules is not None
    doc = doc.model_copy(
        update={"rules": doc.rules.model_copy(update={"cabin_above_slewing_bearing": True})}
    )
    hoist = next(h for h in doc.hoists if h.id == "MH")
    mode = analysis_mode_by_name(hoist, "normal")
    g = abs(float(doc.environment.gravity_m_s2))
    sf1 = ref.dnv_sf1(chart_max_load_t(mode) * g)
    lift = LiftFactors(doc, CraneCalculator(doc))
    for condition in condition_cases(doc, None):
        calc = CraneCalculator(condition_document(doc, condition))
        probes = build_probes(
            calc,
            "MH",
            45.0,
            condition.wind_speed_m_s,
            None,
            vessel=condition.vessel_motion,
            amplified_rope_hoist_id="MH",
        )
        assert probes is not None
        setup = lift.setup(condition, "MH", mode, 45.0, probes.zero)
        scales = lift.demand_scales(condition, "MH", mode, 45.0, setup)
        assert scales is not None and scales["platform_base"].dead == pytest.approx(sf1)
        b, s = _fz(probes.zero)
        limit = 2.0 * b

        def run(scale):
            return envelope_capacity(
                calc,
                probes,
                {"platform_base_Fz": {"Fz": limit}},
                vessel=condition.vessel_motion,
                offlead_deg=0.0,
                sidelead_deg=0.0,
                hook_daf=setup.factor,
                hook_mass_t=mode.hook_mass_t,
                demand_scale=scale,
            ).max_allowable_load_kN

        plain, factored = run(None), run(scales)
        worst_b = limit - plain * s  # the worst baseline of the envelope, the same in both
        assert factored == pytest.approx((limit - sf1 * worst_b) / (sf1 * s), rel=1e-9)
