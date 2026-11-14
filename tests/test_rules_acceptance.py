"""Acceptance: the ABS / DNV pipeline against the independent hand-calculation oracle.

Every case builds a document from ``examples/crane_input_GT283_abs.yaml`` or
``examples/crane_input_GT283_dnv.yaml`` with the case's inputs (rules, one condition, the
MH hook mass and its rated load), runs the real pipeline and compares the result at the
reference outreach with ``tests/rules_reference.py`` (case sheet
``docs/superpowers/plans/2026-11-08-abs-dnv-reference-cases.md``) within 1e-3 relative.

Dynamic factors are checked on the capacity curve of ``run_mode_sweep``. The allowable hook
force ``F`` of the limit is taken from the same document without rules (factor 1.0, the
case's wind and vessel motion): the solver and its limits are not under test here, the
rules are. The oracle then fixes the capacity: the payload ``P`` whose live load
``LL = (P + hook) g`` has ``factor(LL) * LL = F``. The payload ropes are massless, so LL is
known without the app (the suspended rope is ``tests/test_rules_suspended.py``), and the
live-load lateral is off (``tests/test_live_load_lateral.py``).

Pedestal (ABS PF, DNV SF1) and retaining (ABS 3.75) factors are checked on the factored
result rows at a known hook force: ``dead * Q0 + live(LL) * s * H``, with ``Q0`` and ``s``
the solver's baseline and sensitivity at that point.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from crane_statics.core import load_document
from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.calculation import CraneCalculator
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.data.models import ConditionSpec, ContractualPoint, CraneDocument, VesselMotion
from crane_statics.rules import RulesValidationError, validate_rules_document
from tests import rules_reference as ref
from tests.authored_helpers import case_document, example_path
from tests.rules_docs import (
    legacy_equivalent,
    listing_example_hoists,
    without_live_lateral,
    without_suspended_rope,
)

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
ABS_EXAMPLE = example_path("crane_input_GT283_abs.yaml")
DNV_EXAMPLE = example_path("crane_input_GT283_dnv.yaml")
LEGACY_EXAMPLES = ("crane_input_22689", "crane_input_GT283", "crane_input_13778_retracted")

G = 9.81
REL = 1e-3
HOOK = "MH"
#: Reference outreach of every case, m (boom about 83 deg on GT283).
OUTREACH_M = 20.0
#: GT283 MH: 20 falls, so its rope tension is the hook force / 20 at any outreach.
MH_FALLS = 20
MH_ROPE_LIMIT = "MH__rope_T"
BH_ROPE_LIMIT = "BH__rope_T"
#: g-fraction of the vertical vessel acceleration used for a_v = 0.05.
A_Z_005G = 0.05 * G


def approx(value: float) -> object:
    return pytest.approx(value, rel=REL)


# --- documents --------------------------------------------------------------------------


def case_doc(
    example: Path,
    condition: ConditionSpec,
    *,
    rated_load_t: float,
    lower_block_mass_t: Optional[float] = None,
    crane_class: Optional[str] = None,
    cabin: Optional[bool] = None,
) -> CraneDocument:
    """``example`` with one condition, MH rated ``rated_load_t`` at the reference outreach.

    MH is swept at the reference outreach only; its rated load sets the chart's maximum
    rated load (ABS representative LL, DNV psi floor W and SF1 SWL). The payload ropes are
    massless.
    """
    doc = load_document(example)
    assert doc.rules is not None
    rules = doc.rules.model_copy(
        update={
            k: v
            for k, v in (("crane_class", crane_class), ("cabin_above_slewing_bearing", cabin))
            if v is not None
        }
    )
    hoists = []
    for h in doc.hoists:
        if h.id == HOOK:
            update: dict[str, object] = {
                "outreach_min_m": OUTREACH_M,
                "outreach_max_m": OUTREACH_M,
            }
            if lower_block_mass_t is not None:
                update["lower_block_mass_t"] = lower_block_mass_t
            h = h.model_copy(update=update)
        hoists.append(h)
    # The condition takes the example's hoist settings, with MH's chart the one rated point.
    entries = {
        hid: entry.model_copy(deep=True)
        for hid, entry in next(iter(doc.conditions.values())).hoists.items()
    }
    entries[HOOK] = entries[HOOK].model_copy(
        update={
            "contractual_points": [ContractualPoint(load_t=rated_load_t, outreach_m=OUTREACH_M)]
        }
    )
    condition = condition.model_copy(update={"hoists": entries})
    doc = doc.model_copy(
        update={"rules": rules, "conditions": {condition.name: condition}, "hoists": hoists}
    )
    return without_suspended_rope(doc)


def lower_block_mass_t(doc: CraneDocument) -> float:
    return float(next(h for h in doc.hoists if h.id == HOOK).lower_block_mass_t)


def sweep(doc: CraneDocument, limits: dict) -> dict[str, Any]:
    payload: Optional[dict[str, Any]] = run_mode_sweep(doc, HOOK, "normal", limits, 10.0, {})
    assert payload is not None
    return payload


def capacity_t(payload: dict) -> float:
    curve = dict(payload["curve_data"])
    assert OUTREACH_M in curve, payload["curve_data"]
    return float(curve[OUTREACH_M])


def allowable_hook_force_kN(
    doc: CraneDocument, limits: dict, wind_m_s: float, motion: VesselMotion
) -> float:
    """The limit's allowable hook force at the reference outreach under ``wind``/``motion``.

    From ``doc`` without rules, whose MH factor is 1.0: ``F = (P + hook) * g``.
    """
    legacy = legacy_equivalent(doc, max(wind_m_s, 1e-6), motion)
    assert legacy.conditions["default"].hoists[HOOK].daf is None
    return (capacity_t(sweep(legacy, limits)) + lower_block_mass_t(doc)) * G


def live_load_at(force_kN: float, factor: Callable[[float], float]) -> float:
    """The live load ``LL`` (kN) with ``factor(LL) * LL = force_kN``, by bisection.

    Every oracle hook force ``factor(LL) * LL`` is increasing in LL.
    """
    lo, hi = 0.0, force_kN
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if factor(mid) * mid < force_kN:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def oracle_capacity_t(force_kN: float, factor: Callable[[float], float], hook_t: float) -> float:
    return live_load_at(force_kN, factor) / G - hook_t


def reference_angle_deg(doc: CraneDocument) -> float:
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(OUTREACH_M, HOOK)
    assert angle is not None
    return float(angle)


def records_at(payload: dict) -> tuple[dict, tuple[str, ...], str]:
    """``{quantity: record}`` (last wins: an override follows its computed value),
    warnings and case of the clause trail at the reference outreach."""
    trail = {x: rest for x, *rest in payload["provenance"]}
    records, warnings, case = trail[OUTREACH_M]
    return {r.quantity: r for r in records}, tuple(warnings), case


@pytest.fixture
def no_lateral(monkeypatch: pytest.MonkeyPatch) -> None:
    without_live_lateral(monkeypatch)


# --- example documents ------------------------------------------------------------------


@pytest.mark.parametrize("example", [ABS_EXAMPLE, DNV_EXAMPLE], ids=lambda p: p.stem)
def test_rules_examples_load_and_sweep_every_condition(example: Path) -> None:
    doc = load_document(example)
    assert doc.rules is not None and doc.conditions
    assert {c.lift for c in doc.conditions.values()} == {"onboard", "offboard"}
    for name in doc.conditions:
        payload = run_mode_sweep(
            doc, HOOK, "normal", {MH_ROPE_LIMIT: {"T": 600.0}}, 5.0, {}, condition_name=name
        )
        assert payload is not None and payload["curve_data"], name
        assert payload["condition"] == name
        assert len(payload["provenance"]) == len(payload["curve_data"])
        for hoist in doc.hoists:
            if hoist.max_hoisting_speed_m_s is None:
                continue  # the boom hoist
            limits = {f"{hoist.rope_id}_T": {"T": 1.0e4}}
            payload = run_mode_sweep(doc, hoist.id, "normal", limits, 10.0, {}, condition_name=name)
            assert payload is not None and payload["provenance"], (name, hoist.id)
            warnings = {w for _x, _records, ws, _case in payload["provenance"] for w in ws}
            assert not any("max_hoisting_speed_m_s" in w for w in warnings), (name, warnings)
        if doc.conditions[name].lift == "onboard":
            assert doc.conditions[name].significant_wave_height_m is None, name


# --- ABS dynamic factor (VAF) -----------------------------------------------------------


def test_abs_onboard_vaf(no_lateral: None) -> None:
    """A4: onboard VAF 1.373 - LL/5220 + a_v in its linear range, a_v = 0.05."""
    motion = VesselMotion(accel_z_m_s2=A_Z_005G, roll_deg=2.0, pitch_deg=1.0)
    cond = ConditionSpec(name="onboard", wind_speed_m_s=15.0, vessel_motion=motion)
    doc = case_doc(ABS_EXAMPLE, cond, rated_load_t=100.0, crane_class="offshore")
    a_v = A_Z_005G / G
    target_ll = 1000.0
    limits = {MH_ROPE_LIMIT: {"T": ref.abs_vaf_onboard(target_ll, a_v) * target_ll / MH_FALLS}}

    force = allowable_hook_force_kN(doc, limits, 15.0, motion)
    payload = sweep(doc, limits)

    factor = lambda ll: ref.abs_vaf_onboard(ll, a_v)  # noqa: E731
    ll = live_load_at(force, factor)
    assert 1.1 + a_v < factor(ll) < 1.33 + a_v  # the linear range, not a clamp
    assert capacity_t(payload) == approx(oracle_capacity_t(force, factor, lower_block_mass_t(doc)))
    records, _warnings, case = records_at(payload)
    assert case == "In-service"
    rec = records["dynamic_factor"]
    assert rec.inputs["a_v_g"] == approx(a_v)
    assert rec.value == approx(ref.abs_vaf_onboard(rec.inputs["LL_kN"], a_v))
    assert rec.inputs["LL_kN"] == approx((100.0 + lower_block_mass_t(doc)) * G)


@pytest.mark.parametrize(
    ("target_ll", "bound"),
    [(150.0, "cap"), (1800.0, "floor")],
    ids=["A2-cap-1.33", "A3-floor-1.1"],
)
def test_abs_onboard_vaf_clamps(no_lateral: None, target_ll: float, bound: str) -> None:
    """A2/A3: the onboard VAF is clamped to [1.1, 1.33] (a_v = 0)."""
    cond = ConditionSpec(name="onboard", wind_speed_m_s=10.0)
    doc = case_doc(
        ABS_EXAMPLE, cond, rated_load_t=10.0, lower_block_mass_t=5.0, crane_class="offshore"
    )
    limits = {MH_ROPE_LIMIT: {"T": ref.abs_vaf_onboard(target_ll, 0.0) * target_ll / MH_FALLS}}

    force = allowable_hook_force_kN(doc, limits, 10.0, VesselMotion())
    payload = sweep(doc, limits)

    factor = lambda ll: ref.abs_vaf_onboard(ll, 0.0)  # noqa: E731
    assert factor(live_load_at(force, factor)) == (1.33 if bound == "cap" else 1.1)
    assert capacity_t(payload) == approx(oracle_capacity_t(force, factor, lower_block_mass_t(doc)))


def test_abs_offboard_vaf(no_lateral: None) -> None:
    """A5/A6/A8: offboard VAF 1 + v_r sqrt(K/(g LL)), v_r = v_h + sqrt(v_d^2 + v_c^2).

    K is the app's hook stiffness at the point (the series rope model is checked against
    H1/H2 in ``tests/test_rules_stiffness.py``); v_r, VAF and the capacity are the oracle's.
    """
    motion = VesselMotion(accel_z_m_s2=A_Z_005G)
    cond = ConditionSpec(
        name="offboard",
        lift="offboard",
        wind_speed_m_s=12.0,
        vessel_motion=motion,
        significant_wave_height_m=1.0,
        v_in_m_s=0.8,
        v_t_m_s=0.6,
    )
    doc = case_doc(ABS_EXAMPLE, cond, rated_load_t=200.0, crane_class="offshore")
    v_h = float(next(h for h in doc.hoists if h.id == HOOK).max_hoisting_speed_m_s or 0.0)
    assert v_h > ref.abs_v_hmin(1.0)  # 0.108 m/s: no below-minimum warning
    a_v = A_Z_005G / G
    v_r = ref.abs_v_r(v_h, 0.8, 0.6)
    limits = {MH_ROPE_LIMIT: {"T": 4000.0 / MH_FALLS}}

    force = allowable_hook_force_kN(doc, limits, 12.0, motion)
    payload = sweep(doc, limits)
    records, warnings, _case = records_at(payload)
    rec = records["dynamic_factor"]
    k = rec.inputs["K_kN_m"]
    assert k > 0.0
    assert rec.inputs["v_r_m_s"] == approx(v_r)
    assert records["min_hoisting_speed"].value == approx(ref.abs_v_hmin(1.0))
    assert not any("below the ABS minimum" in w for w in warnings)

    factor = lambda ll: ref.abs_vaf_offboard(ll, k, v_r, a_v)  # noqa: E731
    ll = live_load_at(force, factor)
    assert factor(ll) > ref.abs_vaf_onboard(ll, a_v)  # the relative-velocity term governs
    assert capacity_t(payload) == approx(oracle_capacity_t(force, factor, lower_block_mass_t(doc)))
    assert rec.value == approx(ref.abs_vaf_offboard(rec.inputs["LL_kN"], k, v_r, a_v))


def test_abs_offboard_never_below_onboard(no_lateral: None) -> None:
    """A7: with a low v_r the relative-velocity VAF is below the onboard VAF, which governs."""
    motion = VesselMotion(accel_z_m_s2=A_Z_005G)
    cond = ConditionSpec(
        name="offboard",
        lift="offboard",
        wind_speed_m_s=12.0,
        vessel_motion=motion,
        significant_wave_height_m=0.0,
        v_in_m_s=0.0,
        v_t_m_s=0.0,
    )
    doc = case_doc(ABS_EXAMPLE, cond, rated_load_t=200.0, crane_class="offshore")
    v_h = 0.02  # case input: a slow hoist, above v_hmin 0.01 m/s at Hsig 0
    hoists = [
        h.model_copy(update={"max_hoisting_speed_m_s": v_h}) if h.id == HOOK else h
        for h in doc.hoists
    ]
    doc = doc.model_copy(update={"hoists": hoists})
    a_v = A_Z_005G / G
    v_r = ref.abs_v_r(v_h, 0.0, 0.0)
    limits = {MH_ROPE_LIMIT: {"T": 4000.0 / MH_FALLS}}

    force = allowable_hook_force_kN(doc, limits, 12.0, motion)
    payload = sweep(doc, limits)
    k = records_at(payload)[0]["dynamic_factor"].inputs["K_kN_m"]

    factor = lambda ll: ref.abs_vaf_offboard(ll, k, v_r, a_v)  # noqa: E731
    ll = live_load_at(force, factor)
    assert 1.0 + v_r * math.sqrt(k / (G * ll)) < ref.abs_vaf_onboard(ll, a_v)
    assert factor(ll) == ref.abs_vaf_onboard(ll, a_v)  # the onboard VAF governs
    assert capacity_t(payload) == approx(oracle_capacity_t(force, factor, lower_block_mass_t(doc)))


def test_abs_heavy_lift_vaf(no_lateral: None) -> None:
    """A10: heavy-lift VAF 1.1 + a_v, a_v = 0.05 (within the 0.07 g heavy-lift limit)."""
    motion = VesselMotion(accel_z_m_s2=A_Z_005G, roll_deg=1.0)
    cond = ConditionSpec(name="mild", wind_speed_m_s=10.0, vessel_motion=motion)
    doc = case_doc(ABS_EXAMPLE, cond, rated_load_t=1000.0, crane_class="heavy_lift")
    limits = {MH_ROPE_LIMIT: {"T": 600.0}}

    force = allowable_hook_force_kN(doc, limits, 10.0, motion)
    payload = sweep(doc, limits)

    vaf = ref.abs_heavy_lift_vaf(A_Z_005G / G)
    assert vaf == pytest.approx(1.15)
    assert capacity_t(payload) == approx(
        oracle_capacity_t(force, lambda _ll: vaf, lower_block_mass_t(doc))
    )
    assert records_at(payload)[0]["dynamic_factor"].value == approx(vaf)


def test_abs_heavy_lift_rejects_a_v_above_0_07_g_at_the_boom_tip() -> None:
    """2-2/11.3: a_z 0.6 m/s^2 (0.061 g) passes the linear check, but with a pitch angular
    acceleration of 0.02 rad/s^2 the boom-tip a_v exceeds 0.07 g: validation rejects the
    document at the largest rated reach; a sweep of it anyway warns at each point."""
    doc = load_document(ABS_EXAMPLE)
    assert doc.rules is not None
    motion = VesselMotion(accel_z_m_s2=0.6, pitch_angular_accel_rad_s2=0.02)
    cond = listing_example_hoists(
        doc, ConditionSpec(name="mild", wind_speed_m_s=10.0, vessel_motion=motion)
    )
    doc = doc.model_copy(
        update={
            "rules": doc.rules.model_copy(update={"crane_class": "heavy_lift"}),
            "conditions": {"mild": cond},
        }
    )
    with pytest.raises(RulesValidationError, match=r"largest boom-tip reach .* 0\.07 g"):
        validate_rules_document(doc)
    payload = run_mode_sweep(doc, HOOK, "normal", {MH_ROPE_LIMIT: {"T": 600.0}}, 5.0, {})
    assert payload is not None
    warnings = {w for _x, _records, ws, _case in payload["provenance"] for w in ws}
    assert any("g at the boom tip" in w and "0.07 g" in w for w in warnings)


@pytest.mark.parametrize("example", [ABS_EXAMPLE, DNV_EXAMPLE], ids=lambda p: p.stem)
def test_payload_hoist_without_hook_mass_or_load_chart_sweeps(example: Path) -> None:
    """A payload hoist with no hook mass, no load chart and (here) no suspended rope mass
    has a representative live load of 0 kN, as at a hook hoisted to its sheave: the sweep
    runs and warns instead of failing."""
    doc = without_suspended_rope(load_document(example))
    hoists = [
        (h.model_copy(update={"lower_block_mass_t": 0.0}) if h.id == "AH" else h)
        for h in doc.hoists
    ]
    doc = doc.model_copy(update={"hoists": hoists})
    name = next(n for n, c in doc.conditions.items() if c.lift == "onboard")
    doc.conditions[name].hoists["AH"].contractual_points = []
    limits = {"AH_rope_T": {"T": 1.0e4}}
    payload = run_mode_sweep(doc, "AH", "normal", limits, 10.0, {}, condition_name=name)
    assert payload is not None and payload["provenance"]
    warnings = {w for _x, _records, ws, _case in payload["provenance"] for w in ws}
    assert any("0 kN" in w and "no representative dynamic factor" in w for w in warnings)


# --- DNV dynamic factor (psi) and cases -------------------------------------------------


def test_dnv_case_i_offboard_psi(no_lateral: None) -> None:
    """D1/D5/D6, Case I: psi = 1 + V_R sqrt(C/(W g)), V_R = max(0.5 V_L, V_H) + sqrt(...).

    No wind and a level vessel: both cases load the crane alike and Case I (first on the
    tie) is reported. MH hoists at 0.25 m/s, so V_H = 0.3 m/s at Hs 2 m governs (D6).
    """
    cond = ConditionSpec(
        name="offboard",
        lift="offboard",
        wind_speed_m_s=0.0,
        significant_wave_height_m=2.0,
        v_in_m_s=0.8,
        v_t_m_s=0.6,
    )
    doc = case_doc(DNV_EXAMPLE, cond, rated_load_t=200.0, cabin=False)
    v_l = float(next(h for h in doc.hoists if h.id == HOOK).max_hoisting_speed_m_s or 0.0)
    v_r = ref.dnv_v_r(v_l, 0.8, 0.6, 2.0)
    assert v_r == pytest.approx(1.3)
    w_max = (200.0 + lower_block_mass_t(doc)) * G
    floor = ref.dnv_psi_floor(w_max)
    limits = {MH_ROPE_LIMIT: {"T": 4000.0 / MH_FALLS}}

    force = allowable_hook_force_kN(doc, limits, 0.0, VesselMotion())
    payload = sweep(doc, limits)
    records, warnings, case = records_at(payload)
    assert case == "Case I"
    rec = records["dynamic_factor"]
    c = rec.inputs["K_kN_m"]
    assert rec.inputs["v_r_m_s"] == approx(v_r)
    assert records["min_hoisting_speed"].value == approx(ref.dnv_v_h(2.0))
    assert any("below the DNV minimum" in w for w in warnings)

    factor = lambda w: max(ref.dnv_psi(c, w, v_r), floor)  # noqa: E731
    w = live_load_at(force, factor)
    assert ref.dnv_psi(c, w, v_r) > floor  # psi governs, not its floor
    assert capacity_t(payload) == approx(oracle_capacity_t(force, factor, lower_block_mass_t(doc)))


def test_dnv_case_ii_governs_with_wind_and_heel(no_lateral: None) -> None:
    """Case II: the condition's wind and 1.5 x its heel/trim; Case I: no wind (4.2.2, 4.2.3).

    The capacity is the lower of the two cases, each at the onboard psi floor.
    """
    motion = VesselMotion(roll_deg=2.0, pitch_deg=1.0)
    cond = ConditionSpec(name="onboard", wind_speed_m_s=20.0, vessel_motion=motion)
    doc = case_doc(DNV_EXAMPLE, cond, rated_load_t=150.0, cabin=False)
    limits = {BH_ROPE_LIMIT: {"T": 500.0}}
    case_i = allowable_hook_force_kN(doc, limits, 0.0, motion)
    case_ii = allowable_hook_force_kN(doc, limits, 20.0, VesselMotion(roll_deg=3.0, pitch_deg=1.5))
    assert case_ii < case_i

    payload = sweep(doc, limits)

    psi = ref.dnv_psi_floor((150.0 + lower_block_mass_t(doc)) * G)
    assert psi == pytest.approx(1.3)
    expected = oracle_capacity_t(min(case_i, case_ii), lambda _w: psi, lower_block_mass_t(doc))
    assert capacity_t(payload) == approx(expected)
    records, _warnings, case = records_at(payload)
    assert case == "Case II"
    assert records["list_trim_incline"].value == approx(math.hypot(3.0, 1.5))


@pytest.mark.parametrize(
    ("w_max_kN", "expected_floor"),
    [(2000.0, 1.3), (3000.0, 1.26), (6000.0, 1.1)],
    ids=["D2-1.3", "D3-1.5-W/12500", "D4-1.1"],
)
def test_dnv_psi_floor_bands(no_lateral: None, w_max_kN: float, expected_floor: float) -> None:
    """D2-D4: the onboard psi is the 8.2.2.1 floor at the curve's maximum working load."""
    cond = ConditionSpec(name="onboard", wind_speed_m_s=10.0)
    hook_t = lower_block_mass_t(load_document(DNV_EXAMPLE))
    rated = w_max_kN / G - hook_t  # W = rated load + hook block (massless rope)
    doc = case_doc(DNV_EXAMPLE, cond, rated_load_t=rated, cabin=False)
    limits = {MH_ROPE_LIMIT: {"T": 600.0}}

    force = allowable_hook_force_kN(doc, limits, 0.0, VesselMotion())
    payload = sweep(doc, limits)

    floor = ref.dnv_psi_floor(w_max_kN)
    assert floor == pytest.approx(expected_floor)
    assert capacity_t(payload) == approx(oracle_capacity_t(force, lambda _w: floor, hook_t))
    records = records_at(payload)[0]
    assert records["psi_floor"].value == approx(floor)
    assert records["psi_floor"].inputs["W_max_kN"] == approx(w_max_kN)


def test_dnv_sf1_on_the_capacity_curve(no_lateral: None) -> None:
    """D7 on the chart: a platform-base limit checks SF1 times dead and live load."""
    cond = ConditionSpec(name="onboard", wind_speed_m_s=0.0)
    rated = 2000.0 / G  # SWL 2000 kN: SF1 1.3
    doc = case_doc(DNV_EXAMPLE, cond, rated_load_t=rated, cabin=True)
    calc = CraneCalculator(doc)
    angle = reference_angle_deg(doc)
    point = calc.compute_analysis_point(angle, 0.0, HOOK, wind_speed_m_s=0.0)
    assert point is not None
    limit = 2.0 * abs(float(point.baseline_reactions["platform_base"]["Fz"]))
    sf1 = ref.dnv_sf1(rated * G)
    assert sf1 == 1.3

    payload = sweep(doc, {"platform_base_Fz": {"Fz": limit}})
    force = allowable_hook_force_kN(
        doc, {"platform_base_Fz": {"Fz": limit / sf1}}, 0.0, VesselMotion()
    )

    psi = ref.dnv_psi_floor((rated + lower_block_mass_t(doc)) * G)
    expected = oracle_capacity_t(force, lambda _w: psi, lower_block_mass_t(doc))
    assert capacity_t(payload) == approx(expected)
    assert records_at(payload)[0]["pedestal_factor"].value == approx(sf1)


# --- foundation and retaining factors on the result rows --------------------------------


def _factored_rows(doc: CraneDocument, hook_kN: float) -> tuple[dict, dict, float, float]:
    """``{name: row}`` of the factored and of all rows at ``hook_kN``, and the platform
    Fz baseline and sensitivity, with the Scene on MH at the reference outreach."""
    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist(HOOK)
    session.set_scene_condition(next(iter(doc.conditions)), None, seed=True)
    state = session.get_active_hoist_state()
    assert state is not None
    angle = reference_angle_deg(doc)
    state.scene_state = dataclasses.replace(state.scene_state, boom_angle_deg=angle)
    calculator = AnalysisCalculator(session, KinematicsService(session), HoistStateService(session))
    pt = calculator.compute_analysis_point()
    assert pt is not None
    _ropes, rows = calculator.compute_result_rows(pt, hook_load_kN=hook_kN)
    factored = {r.name: r for r in rows if r.kind == "factored"}
    plain = {(r.entity_id, r.component): r for r in rows if r.kind == "connection"}
    b = float(pt.baseline_reactions["platform_base"]["Fz"])
    s = float(pt.sensitivity_reactions["platform_base"]["Fz"])
    assert plain[("platform_base", "Fz")].demand_kN == pytest.approx(b + s * hook_kN, rel=1e-9)
    return factored, plain, b, s


@pytest.mark.parametrize(
    ("crane_class", "target_ll", "hook_t", "expected_pf"),
    [
        ("offshore", 200.0, 5.0, 1.5),
        ("offshore", 1000.0, 50.0, 1.31),
        ("offshore", 2000.0, 50.0, 1.2),
        ("heavy_lift", 2000.0, 50.0, 1.06),
        ("heavy_lift", 3000.0, 50.0, 1.0),
    ],
    ids=["A12-cap-1.5", "A11-mid", "A13-offshore-floor-1.2", "A14-heavy-lift", "A15-floor-1.0"],
)
def test_abs_pedestal_and_retaining_rows(
    crane_class: str, target_ll: float, hook_t: float, expected_pf: float
) -> None:
    """A11-A15 and 5.13.5(c): pedestal rows b + PF(LL) s H, retaining rows b + 3.75 s H."""
    cond = ConditionSpec(name="onboard", wind_speed_m_s=10.0)
    doc = case_doc(
        ABS_EXAMPLE, cond, rated_load_t=100.0, lower_block_mass_t=hook_t, crane_class=crane_class
    )
    if crane_class == "heavy_lift":
        vaf: Callable[[float], float] = lambda _ll: ref.abs_heavy_lift_vaf(0.0)  # noqa: E731
    else:
        vaf = lambda ll: ref.abs_vaf_onboard(ll, 0.0)  # noqa: E731
    hook_kN = vaf(target_ll) * target_ll

    factored, _plain, b, s = _factored_rows(doc, hook_kN)

    pf = ref.abs_pedestal_factor(target_ll, crane_class)
    assert pf == pytest.approx(expected_pf)
    pedestal = factored["Platform Base (ABS PF) / Fz"]
    assert pedestal.demand_kN == approx(b + pf * s * hook_kN)
    retaining = factored["Retaining / Fz"]
    assert retaining.demand_kN == approx(b + 3.75 * s * hook_kN)


@pytest.mark.parametrize(
    ("cabin", "swl_kN", "expected_sf1"),
    [
        (True, 2000.0, 1.3),
        (True, 3000.0, 1.1),
        (True, 2500.0, 1.1),
        (True, 2200.0, 1.3),
        (False, 2000.0, None),
    ],
    ids=["D7-cabin-1.3", "D8-cabin-1.1", "SWL-2500-1.1", "SWL-2200-hook-excluded-1.3", "no-cabin"],
)
def test_dnv_sf1_rows(cabin: bool, swl_kN: float, expected_sf1: Optional[float]) -> None:
    """D7/D8: with a cabin above the slewing bearing SF1 scales dead and live load alike;
    without one SF1 does not apply and there are no factored rows."""
    cond = ConditionSpec(name="onboard", wind_speed_m_s=10.0)
    doc = case_doc(DNV_EXAMPLE, cond, rated_load_t=swl_kN / G, cabin=cabin)
    rated_kN = float(doc.conditions["onboard"].hoists[HOOK].contractual_points[0].load_t) * G
    assert rated_kN == swl_kN  # exact: the 2500 kN boundary is hit, not approached
    if swl_kN == 2200.0:
        # SWL excludes the hook block (4.1.2.1): with it the load would be above 2500 kN.
        assert swl_kN + lower_block_mass_t(doc) * G > 2500.0
    hook_kN = 2500.0

    factored, plain, b, s = _factored_rows(doc, hook_kN)

    if expected_sf1 is None:
        assert not factored
        return
    sf1 = ref.dnv_sf1(swl_kN)
    assert sf1 == expected_sf1
    assert factored["Platform Base (DNV SF1) / Fz"].demand_kN == approx(sf1 * (b + s * hook_kN))
    assert not any(name.startswith("Retaining") for name in factored)


# --- legacy examples reproduce their goldens --------------------------------------------

#: Sweeps of the legacy examples recorded at 740eb11, before the rules work: every payload
#: hoist and mode, the session's default limits, 5 m outreach step.
SWEEP_GOLDEN = ROOT / "tests" / "golden" / "legacy_example_sweeps.json"


def _legacy_sweeps(name: str) -> dict[str, dict]:
    doc = load_document(example_path(f"{name}.yaml"))
    # v13: a rules-less document has its one condition ``default`` (was: no conditions).
    assert doc.rules is None and list(doc.conditions) == ["default"]
    session = SessionModel()
    session.set_document(doc)
    limits = {
        dl.id: {dl.component: dl.allowable_kN}
        for dl in session.design_limits
        if dl.enabled and dl.allowable_kN is not None
    }
    out: dict[str, dict] = {}
    for hoist_id in session.payload_hoist_ids():
        for mode in ("normal", "split"):
            payload = run_mode_sweep(doc, hoist_id, mode, limits, 5.0, {})
            if payload is None:
                continue
            assert payload["provenance"] == []
            out[f"{name}/{hoist_id}/{mode}"] = {
                "curve": [list(p) for p in payload["curve_data"]],
                "contractual": [
                    [cp.outreach_m, cp.load_t, load, ok]
                    for cp, load, ok in payload["contractual_results"]
                ],
                "limits": {
                    lid: [list(p) for p in pts]
                    for lid, _label, _rank, pts in payload["limit_series"]
                },
            }
    return out


@pytest.mark.parametrize("name", LEGACY_EXAMPLES)
def test_legacy_example_sweeps_reproduce_their_golden(name: str) -> None:
    golden = json.loads(SWEEP_GOLDEN.read_text(encoding="utf-8"))
    expected = {k: v for k, v in golden.items() if k.split("/")[0] == name}
    assert expected
    got = _legacy_sweeps(name)
    assert set(got) == set(expected)
    for key, value in expected.items():
        _assert_rows_close(got[key]["contractual"], value["contractual"], key)
        _assert_rows_close(got[key]["curve"], value["curve"], key)
        assert set(got[key]["limits"]) == set(value["limits"]), key
        for lid, pts in value["limits"].items():
            _assert_rows_close(got[key]["limits"][lid], pts, (key, lid))


def _assert_rows_close(got: list, expected: list, where: object) -> None:
    assert len(got) == len(expected), where
    for got_row, row in zip(got, expected):
        assert len(got_row) == len(row), where
        for g, e in zip(got_row, row):
            if isinstance(e, float):
                assert g == pytest.approx(e, rel=1e-9, abs=1e-9), (where, got_row, row)
            else:
                assert g == e, (where, got_row, row)


def test_legacy_22689_reproduces_its_workbook_golden() -> None:
    from scripts.excel_workbook.reference import CASES, GOLDEN_PATH, YAML_PATH, app_results

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert YAML_PATH.name == "crane_input_22689.yaml"
    for name, entry in golden["cases"].items():
        live = app_results(example_path(YAML_PATH), CASES[name])
        assert set(live) == set(entry["app_results"]), name
        for key, value in entry["app_results"].items():
            assert math.isclose(value, live[key], rel_tol=0.0, abs_tol=1e-9), (name, key)


def test_legacy_gt283_reproduces_its_point_golden() -> None:
    golden = json.loads((ROOT / "tests" / "golden" / "gt283_mh_45deg.json").read_text())
    doc = case_document(load_document(example_path("crane_input_GT283.yaml")))
    calc = CraneCalculator(doc)
    point = calc.compute_analysis_point(
        boom_angle_deg=45.0,
        hook_load_kN=0.0,
        hoist_id="MH",
        wind_speed_m_s=10.0,
        wind_direction="+X",
        # v12 defaulted to the hoist's authored offlead; v13 keeps it on the condition.
        offlead_deg=doc.conditions["default"].hoists["MH"].offlead_deg,
    )
    assert point is not None

    def flat(reactions: dict) -> dict:
        return {(e, k): v for e, comps in reactions.items() for k, v in comps.items()}

    assert flat(point.baseline_reactions) == pytest.approx(flat(golden["baseline"]))
    assert flat(point.sensitivity_reactions) == pytest.approx(flat(golden["sensitivity"]))
