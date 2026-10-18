"""The per-mode sweep entry point and its batch callback."""

from __future__ import annotations

from pathlib import Path

import pytest

import crane_statics.calculation.engine as engine
from crane_statics.core import load_document
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep, run_mode_sweep

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}
STEP = 5.0


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
