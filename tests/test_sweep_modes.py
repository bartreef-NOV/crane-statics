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
    assert swept == same
    assert swept["curve_data"] != dummy["curve_data"]  # the wind speed does matter here


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
    assert swept == same
    assert swept["curve_data"] != at_origin["curve_data"]  # the reference point matters
