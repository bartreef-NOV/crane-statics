"""The per-mode sweep entry point and its batch callback."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import crane_statics.calculation.engine as engine
from crane_statics.core import load_document
from crane_statics.core.governing_case import governing_case
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.core.load_condition import DEFAULT_CONDITION_NAME, condition_cases
from crane_statics.core.sweep_cache import ComputeCache, compute_fingerprint
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep, run_mode_sweep
from crane_statics.data.models import CraneDocument, VesselMotion
from tests.rules_docs import (
    without_foundation_factors,
    without_live_lateral,
    MOTION,
    gale,
    legacy_equivalent,
    rules_doc,
    without_suspended_rope,
)

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}
STEP = 10.0


def _doc():
    return load_document(EXAMPLE)


def test_mode_payload_equals_the_combined_sweep() -> None:
    doc = _doc()
    combined = run_capacity_sweep(doc, HOIST, LIMITS, STEP, {})
    for mode in ("normal", "split"):
        if mode not in combined["modes"]:
            continue
        payload = run_mode_sweep(doc, HOIST, mode, LIMITS, STEP, {})
        assert payload is not None
        assert payload["curve_data"] == combined["modes"][mode]["curve_data"]
    if "split" not in combined["modes"]:
        pytest.skip("example has no split mode")


def test_batches_concatenate_to_the_curve() -> None:
    batches: list[list[tuple[float, float]]] = []
    payload = run_mode_sweep(
        _doc(), HOIST, "normal", LIMITS, STEP, {}, on_points=batches.append, batch_points=4
    )
    assert payload is not None
    assert len(batches) > 1
    assert all(len(b) <= 4 for b in batches)
    assert sum(batches, []) == payload["curve_data"]


def test_inapplicable_split_returns_none() -> None:
    doc = _doc()
    next(h for h in doc.hoists if h.id == HOIST).splitable_block = False
    assert run_mode_sweep(doc, HOIST, "split", LIMITS, STEP, {}) is None


def test_cancel_raises() -> None:
    with pytest.raises(SweepCancelled):
        run_mode_sweep(_doc(), HOIST, "normal", LIMITS, STEP, {}, should_cancel=lambda: True)


def test_sweep_does_not_grow_the_calculator_cache() -> None:
    doc = _doc()
    before = len(engine._CALCULATOR_CACHE)
    run_mode_sweep(doc, HOIST, "normal", LIMITS, STEP, {})
    assert len(engine._CALCULATOR_CACHE) == before


# --- load conditions -----------------------------------------------------------------------

RULES_LIMITS: dict[str, dict] = {
    "boom_hoist": {"T": 5000.0},
    "platform_base": {"max_bearing_line_load": 3000.0},
}
RULES_STEP = 20.0


def _rules_doc(standard, *conditions) -> CraneDocument:
    """``rules_doc`` without payload-rope mass: its rules runs equal the legacy equivalents."""
    return without_suspended_rope(rules_doc(standard, *conditions))


def test_legacy_sweep_without_a_condition_is_the_default_condition() -> None:
    doc = _doc()
    payload = run_mode_sweep(doc, HOIST, "normal", LIMITS, STEP, {}, condition_name=None)
    named = run_mode_sweep(
        doc, HOIST, "normal", LIMITS, STEP, {}, condition_name=DEFAULT_CONDITION_NAME
    )
    assert payload is not None and payload["curve_data"]
    assert payload == named


def test_sweep_for_an_unknown_condition_raises_naming_it() -> None:
    with pytest.raises(KeyError, match="nope"):
        run_mode_sweep(_doc(), HOIST, "normal", LIMITS, STEP, {}, condition_name="nope")
    with pytest.raises(KeyError, match="nope"):
        run_mode_sweep(
            _rules_doc("ABS", gale()), HOIST, "normal", LIMITS, STEP, {}, condition_name="nope"
        )


def test_rules_sweep_uses_the_condition_wind_and_motion_not_the_dummies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("ABS", gale(wind=30.0))
    swept = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    same = run_mode_sweep(
        legacy_equivalent(doc, 30.0, MOTION), HOIST, "normal", RULES_LIMITS, RULES_STEP, {}
    )
    dummy = run_mode_sweep(
        legacy_equivalent(doc, 20.0, MOTION), HOIST, "normal", RULES_LIMITS, RULES_STEP, {}
    )
    assert swept is not None and same is not None and dummy is not None
    assert swept["curve_data"]
    assert _curves(swept) == _curves(same)
    assert swept["curve_data"] != dummy["curve_data"]  # the wind speed does matter here


def _curves(payload: dict) -> dict:
    """The payload without its clause trail (a legacy equivalent has none)."""
    return {k: v for k, v in payload.items() if k not in ("provenance", "condition")}


def _legacy_curve(doc: CraneDocument, wind: float, motion: VesselMotion) -> dict[float, float]:
    payload = run_mode_sweep(
        legacy_equivalent(doc, wind, motion), HOIST, "normal", RULES_LIMITS, RULES_STEP, {}
    )
    assert payload is not None
    return dict(payload["curve_data"])


def test_rules_chart_is_the_minimum_over_the_condition_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("DNV", gale(wind=30.0), gale("calm", wind=5.0))
    case_i, case_ii = condition_cases(doc, "gale")
    swept = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    per_case = [_legacy_curve(doc, c.wind_speed_m_s, c.vessel_motion) for c in (case_i, case_ii)]
    assert swept is not None and swept["curve_data"]
    for outreach, load_t in swept["curve_data"]:
        assert load_t == min(curve[outreach] for curve in per_case if outreach in curve)
    assert any(per_case[0][x] != per_case[1][x] for x in per_case[0] if x in per_case[1])


def test_rules_sweep_without_a_condition_takes_the_first() -> None:
    doc = _rules_doc("ABS", gale(wind=30.0), gale("calm", wind=5.0))
    first = run_mode_sweep(doc, HOIST, "normal", LIMITS, RULES_STEP, {}, condition_name="gale")
    assert run_mode_sweep(doc, HOIST, "normal", LIMITS, RULES_STEP, {}) == first
    calm = run_mode_sweep(doc, HOIST, "normal", LIMITS, RULES_STEP, {}, condition_name="calm")
    assert calm != first


def test_rules_governing_case_uses_the_condition(monkeypatch: pytest.MonkeyPatch) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("ABS", gale(wind=30.0))
    case = governing_case(doc, HOIST, "normal", RULES_LIMITS, 30.0, None, condition_name="gale")
    same = governing_case(
        legacy_equivalent(doc, 30.0, MOTION), HOIST, "normal", RULES_LIMITS, 30.0, None
    )
    assert case is not None and same is not None
    # The manual daf (GT283 MH 1.1) is the factor of both, so only the names differ.
    assert case == replace(same, condition_name="gale", case_name="In-service")
    assert case.scene_fields["wind_speed_m_s"] == 30.0


def test_rules_governing_case_is_the_lowest_case_of_the_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("DNV", gale(wind=30.0))
    case = governing_case(doc, HOIST, "normal", RULES_LIMITS, 30.0, None, condition_name="gale")
    per_case = [
        governing_case(
            legacy_equivalent(doc, c.wind_speed_m_s, c.vessel_motion),
            HOIST,
            "normal",
            RULES_LIMITS,
            30.0,
            None,
        )
        for c in condition_cases(doc, "gale")
    ]
    assert case is not None
    lowest = min(
        (c for c in per_case if c is not None), key=lambda c: c.scene_fields["hook_load_kN"]
    )
    governing = condition_cases(doc, "gale")[per_case.index(lowest)].case
    assert governing is not None
    assert case == replace(lowest, condition_name="gale", case_name=governing.name)


def test_rules_auto_set_uses_every_condition_case(monkeypatch: pytest.MonkeyPatch) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("ABS", gale(wind=30.0), gale("calm", wind=5.0, motion=VesselMotion()))
    rope_id = next(h for h in doc.hoists if h.id == "BH").rope_id  # wind and motion matter
    rules = compute_required_rope_capacity_kN(doc, rope_id)
    per_condition = [
        compute_required_rope_capacity_kN(legacy_equivalent(doc, 30.0, MOTION), rope_id),
        compute_required_rope_capacity_kN(legacy_equivalent(doc, 5.0, VesselMotion()), rope_id),
    ]
    assert rules.required_kN is not None
    required = [r.required_kN for r in per_condition if r.required_kN is not None]
    assert len(required) == 2
    assert rules.required_kN == max(required)
    assert per_condition[0].required_kN != per_condition[1].required_kN


def test_rules_conditions_share_one_compute_cache_without_mixing_cases() -> None:
    doc = rules_doc(
        "DNV",
        gale(wind=30.0),
        gale("calm", wind=5.0, motion=MOTION.model_copy(update={"roll_deg": 1.0})),
    )
    cache = ComputeCache()
    fingerprint = compute_fingerprint(doc)
    payloads = {}
    for name in ("gale", "calm"):
        unscoped = run_mode_sweep(
            doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name=name
        )
        # Both conditions use the same (fingerprint, hoist, mode) scope, as chart_vm does.
        scope = cache.scope(fingerprint, HOIST, "normal")
        scoped = run_mode_sweep(
            doc,
            HOIST,
            "normal",
            RULES_LIMITS,
            RULES_STEP,
            {},
            compute_scope=scope,
            condition_name=name,
        )
        assert unscoped is not None and unscoped["curve_data"]
        assert scoped == unscoped
        payloads[name] = scoped
    assert payloads["gale"] != payloads["calm"]


ANGULAR_MOTION = VesselMotion(
    accel_z_m_s2=0.5,
    roll_deg=3.0,
    pitch_deg=1.5,
    pitch_angular_accel_rad_s2=0.04,
    roll_angular_accel_rad_s2=0.06,
    reference_x_m=12.0,
    reference_z_m=-6.0,
)


def test_rules_sweep_uses_the_condition_reference_point(monkeypatch: pytest.MonkeyPatch) -> None:
    without_live_lateral(monkeypatch)  # the legacy equivalent has no hook lateral
    without_foundation_factors(monkeypatch)  # nor pedestal factors
    doc = _rules_doc("ABS", gale(wind=15.0, motion=ANGULAR_MOTION))
    swept = run_mode_sweep(doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {})
    same = run_mode_sweep(
        legacy_equivalent(doc, 15.0, ANGULAR_MOTION), HOIST, "normal", RULES_LIMITS, RULES_STEP, {}
    )
    origin = ANGULAR_MOTION.model_copy(update={"reference_x_m": 0.0, "reference_z_m": 0.0})
    at_origin = run_mode_sweep(
        legacy_equivalent(doc, 15.0, origin), HOIST, "normal", RULES_LIMITS, RULES_STEP, {}
    )
    assert swept is not None and same is not None and at_origin is not None
    assert swept["curve_data"]
    assert _curves(swept) == _curves(same)
    assert swept["curve_data"] != at_origin["curve_data"]  # the reference point matters


# --- clause trail (provenance) -------------------------------------------------------------


def test_legacy_payload_has_no_provenance() -> None:
    payload = run_mode_sweep(_doc(), HOIST, "normal", LIMITS, STEP, {})
    assert payload is not None and payload["curve_data"]
    assert payload["provenance"] == []
    assert payload["condition"] == DEFAULT_CONDITION_NAME


def test_rules_payload_carries_the_records_of_every_curve_point() -> None:
    doc = _rules_doc("ABS", gale(wind=30.0))
    payload = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    assert payload is not None and payload["curve_data"]
    assert payload["condition"] == "gale"
    prov = payload["provenance"]
    assert [p[0] for p in prov] == [x for x, _y in payload["curve_data"]]
    for _outreach, records, warnings, case_name in prov:
        assert case_name == "In-service"
        assert isinstance(records, tuple) and isinstance(warnings, tuple)
        factor = [r for r in records if r.quantity == "dynamic_factor"]
        # GT283 authors a non-default hook_daf, so the computed factor is followed by its override.
        assert [r.source for r in factor][0] == "computed"
        assert {r.source for r in factor} <= {"computed", "override"}
        assert factor[0].clause


def test_rules_records_are_the_setup_the_capacity_was_computed_with() -> None:
    from crane_statics.core.analysis_cases import analysis_mode_by_name
    from crane_statics.core.lift_factor import LiftFactors
    from crane_statics.calculation.engine import CraneCalculator
    from crane_statics.core.chart_envelope import build_probes
    from crane_statics.core.lift_factor import amplified_rope_hoist_id
    from crane_statics.core.load_condition import condition_document
    from crane_statics.calculation.solver.kinematics import KinematicsAdapter

    doc = _rules_doc("ABS", gale(wind=30.0))
    payload = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    assert payload is not None
    outreach, records, warnings, _case = payload["provenance"][len(payload["provenance"]) // 2]
    (case,) = condition_cases(doc, "gale")
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach, HOIST)
    calc = CraneCalculator(condition_document(doc, case))
    assert angle is not None
    probes = build_probes(
        calc,
        HOIST,
        angle,
        case.wind_speed_m_s,
        mode.runtime_overrides,
        vessel=case.vessel_motion,
        amplified_rope_hoist_id=amplified_rope_hoist_id(case, HOIST),
    )
    assert probes is not None
    setup = LiftFactors(doc, calc).setup(case, HOIST, mode, angle, probes.zero)
    assert records == setup.records
    assert warnings == setup.warnings


def _case_setup(doc: CraneDocument, case, outreach: float):
    """The LiftSetup of ``case`` at ``outreach``, built directly (not through the sweep)."""
    from crane_statics.calculation.engine import CraneCalculator
    from crane_statics.calculation.solver.kinematics import KinematicsAdapter
    from crane_statics.core.analysis_cases import analysis_mode_by_name
    from crane_statics.core.chart_envelope import build_probes
    from crane_statics.core.lift_factor import LiftFactors, amplified_rope_hoist_id
    from crane_statics.core.load_condition import condition_document

    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, "normal")
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach, HOIST)
    assert angle is not None
    calc = CraneCalculator(condition_document(doc, case))
    probes = build_probes(
        calc,
        HOIST,
        angle,
        case.wind_speed_m_s,
        mode.runtime_overrides,
        vessel=case.vessel_motion,
        amplified_rope_hoist_id=amplified_rope_hoist_id(case, HOIST),
    )
    assert probes is not None
    return LiftFactors(doc, calc).setup(case, HOIST, mode, angle, probes.zero)


def test_dnv_provenance_is_the_lowest_payload_cases_own_setup() -> None:
    doc = _rules_doc("DNV", gale(wind=30.0), gale("calm", wind=5.0))
    payload = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    assert payload is not None and payload["provenance"]
    case_i, case_ii = condition_cases(doc, "gale")
    per_case = [_legacy_curve(doc, c.wind_speed_m_s, c.vessel_motion) for c in (case_i, case_ii)]
    for outreach, records, warnings, case_name in payload["provenance"]:
        loads = [curve[outreach] for curve in per_case]
        governing = (case_i, case_ii)[loads.index(min(loads))]
        assert governing.case is not None and case_name == governing.case.name
        setup = _case_setup(doc, governing, outreach)
        assert records == setup.records and warnings == setup.warnings


def test_manual_daf_is_recorded_as_an_override() -> None:
    doc = _rules_doc("ABS", gale())
    hoists = [h.model_copy(update={"hook_daf": 1.7}) if h.id == HOIST else h for h in doc.hoists]
    doc = doc.model_copy(update={"hoists": hoists})
    payload = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    assert payload is not None and payload["provenance"]
    for _x, records, _w, _c in payload["provenance"]:
        sources = [r.source for r in records if r.quantity == "dynamic_factor"]
        assert sources == ["computed", "override"]


def test_cached_rerun_returns_the_same_provenance() -> None:
    doc = _rules_doc("ABS", gale())
    cache = ComputeCache()
    scope = cache.scope(compute_fingerprint(doc), HOIST, "normal")
    first = run_mode_sweep(
        doc,
        HOIST,
        "normal",
        RULES_LIMITS,
        RULES_STEP,
        {},
        compute_scope=scope,
        condition_name="gale",
    )
    again = run_mode_sweep(
        doc,
        HOIST,
        "normal",
        RULES_LIMITS,
        RULES_STEP,
        {},
        compute_scope=scope,
        condition_name="gale",
    )
    plain = run_mode_sweep(
        doc, HOIST, "normal", RULES_LIMITS, RULES_STEP, {}, condition_name="gale"
    )
    assert first is not None and first["provenance"]
    assert first == again == plain


@pytest.mark.parametrize("example", ["crane_input_GT283_abs.yaml", "crane_input_GT283_dnv.yaml"])
def test_every_curve_point_has_a_trail(example: str) -> None:
    """The shipped rules examples: every curve outreach has a non-empty clause trail."""
    from crane_statics.data import payload_hoist_ids

    doc = load_document(ROOT / "examples" / example)
    for hoist_id in payload_hoist_ids(doc):
        payload = run_mode_sweep(doc, hoist_id, "normal", RULES_LIMITS, RULES_STEP, {})
        assert payload is not None and payload["curve_data"], hoist_id
        prov = payload["provenance"]
        assert {p[0] for p in prov} == {p[0] for p in payload["curve_data"]}, hoist_id
        assert all(records for _x, records, _w, _c in prov), hoist_id
