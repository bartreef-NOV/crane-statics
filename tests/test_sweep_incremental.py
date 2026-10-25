"""A limit edit re-sweeps through the compute cache: same results, only the edit evaluated."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

import crane_statics.core.sweep as sweep
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core import load_document
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.core.sweep_cache import ComputeCache, ComputeScope, LimitResult
from crane_statics.core.sweep_cache import compute_fingerprint, limit_signature
from crane_statics.data.models import CraneDocument

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
STEP = 10.0
VESSEL = {"accel_x_m_s2": 0.5, "roll_deg": 2.0}
# MH__rope binds at short outreach, the bearing line load at mid outreach and rear_hinge Fx
# at long outreach; boom_hoist responds but never binds, WH__rope does not respond to MH.
LIMITS: dict[str, dict] = {
    "MH__rope": {"T": 1500.0},
    "platform_base": {"max_bearing_line_load": 6000.0},
    "rear_hinge": {"Fx": 5000.0},
    "boom_hoist": {"T": 8000.0},
    "WH__rope": {"T": 100000.0},
}


@pytest.fixture(scope="module")
def doc() -> CraneDocument:
    document = load_document(EXAMPLE)
    vm = document.environment.vessel_motion
    for field, value in VESSEL.items():
        setattr(vm, field, float(value))
    document.environment.max_wind_speed_m_s = 20.0
    return document


def _scope(doc: CraneDocument, mode: str = "normal") -> ComputeScope:
    return ComputeCache().scope(compute_fingerprint(doc), HOIST, mode)


def _sweep(
    doc: CraneDocument,
    limits: dict,
    scope: Optional[ComputeScope] = None,
    mode: str = "normal",
) -> Optional[dict[str, Any]]:
    return run_mode_sweep(doc, HOIST, mode, limits, STEP, {}, compute_scope=scope)


def _comparable(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if payload is None:
        return None
    return {
        "curve_data": payload["curve_data"],
        "limit_series": payload["limit_series"],
        "n_points": payload["n_points"],
        "contractual": [(allow, ok) for _cp, allow, ok in payload["contractual_results"]],
    }


def _counting(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"build_probes": [], "envelope_capacity": []}

    def _wrap(name: str, func: Callable[..., Any], record: Callable[..., Any]) -> None:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls[name].append(record(*args, **kwargs))
            return func(*args, **kwargs)

        monkeypatch.setattr(sweep, name, wrapper)

    _wrap("build_probes", sweep.build_probes, lambda *a, **k: a[2])
    _wrap("envelope_capacity", sweep.envelope_capacity, lambda calc, probes, limits, **k: limits)
    return calls


def test_scope_does_not_change_results_cold_and_warm(doc: CraneDocument) -> None:
    for mode in ("normal", "split"):
        plain = _comparable(_sweep(doc, LIMITS, mode=mode))
        if plain is None:
            continue
        scope = _scope(doc, mode)
        assert _comparable(_sweep(doc, LIMITS, scope, mode)) == plain  # cold
        assert _comparable(_sweep(doc, LIMITS, scope, mode)) == plain  # warm
        assert plain["contractual"]
        if mode == "normal":
            assert plain["n_points"] >= 10
            series = {row[0] for row in plain["limit_series"]}
            assert {"MH__rope", "platform_base", "rear_hinge"} <= series
            assert "WH__rope" not in series


def test_changing_adding_removing_one_limit_equals_a_full_recompute(doc: CraneDocument) -> None:
    scope = _scope(doc)
    _sweep(doc, LIMITS, scope)
    changed = {**LIMITS, "MH__rope": {"T": 1800.0}}
    added = {**changed, "platform_base_Fz": {"Fz": 55000.0}}
    removed = {k: v for k, v in added.items() if k != "rear_hinge"}
    for limits in (changed, added, removed, {}):
        expected = _comparable(_sweep(doc, limits))
        assert expected is not None
        assert _comparable(_sweep(doc, limits, scope)) == expected
    assert _comparable(_sweep(doc, LIMITS, scope)) == _comparable(_sweep(doc, LIMITS))


def test_warm_scope_makes_no_probe_solves_and_one_evaluation_per_limit_angle(
    doc: CraneDocument, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    scope = _scope(doc)
    _sweep(doc, LIMITS, scope)
    angles = len(calls["envelope_capacity"]) // len(LIMITS)
    assert angles >= 10
    assert all(len(limits) == 1 for limits in calls["envelope_capacity"])

    calls["build_probes"].clear()
    calls["envelope_capacity"].clear()
    changed = {**LIMITS, "MH__rope": {"T": 1800.0}}
    payload = _sweep(doc, changed, scope)
    assert payload is not None and payload["n_points"] > 0
    assert calls["build_probes"] == []
    assert calls["envelope_capacity"] == [{"MH__rope": {"T": 1800.0}}] * angles


def test_no_enabled_limits_gives_an_unlimited_empty_curve(doc: CraneDocument) -> None:
    scope = _scope(doc)
    for limits in ({}, {"MH__rope": {"T": None}}, {"MH__rope": {"T": 0.0}}):
        plain = _comparable(_sweep(doc, limits))
        assert plain is not None
        assert plain["n_points"] == 0
        assert plain["limit_series"] == []
        assert _comparable(_sweep(doc, limits, scope)) == plain


def test_toggling_a_value_back_reuses_the_cached_results(
    doc: CraneDocument, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    scope = _scope(doc)
    first = _comparable(_sweep(doc, LIMITS, scope))
    _sweep(doc, {**LIMITS, "MH__rope": {"T": 1800.0}}, scope)
    calls["build_probes"].clear()
    calls["envelope_capacity"].clear()
    assert _comparable(_sweep(doc, LIMITS, scope)) == first
    assert calls["build_probes"] == []
    assert calls["envelope_capacity"] == []


def test_same_entity_different_components_are_separate(doc: CraneDocument) -> None:
    limits = {
        "platform_base_Fz": {"Fz": 55000.0},
        "platform_base_max_bearing_line_load": {"max_bearing_line_load": 6000.0},
    }
    scope = _scope(doc)
    payload = _sweep(doc, limits, scope)
    assert _comparable(payload) == _comparable(_sweep(doc, limits))
    assert payload is not None

    hoist = next(h for h in doc.hoists if h.id == HOIST)
    kin = KinematicsAdapter(doc.model_dump())
    outreach, load_t = payload["curve_data"][len(payload["curve_data"]) // 2]
    angle = kin.outreach_to_angle(outreach, hoist.id)
    assert angle is not None

    def _miss() -> LimitResult:
        raise AssertionError("expected a cached result")

    results = [
        scope.limit_result(angle, limit_signature(lid, comps), _miss)
        for lid, comps in limits.items()
    ]
    assert results[0] != results[1]
    assert load_t == min(results, key=lambda r: r.load_kN).load_t
