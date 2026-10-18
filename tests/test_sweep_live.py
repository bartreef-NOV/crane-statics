"""Live-series callbacks: contractual verdicts and per-limit points stream during a sweep."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from crane_statics.core import load_document
from crane_statics.core.sweep import limit_series_layout, run_mode_sweep
from crane_statics.data.models import CraneDocument

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
STEP = 5.0
VESSEL = {"accel_x_m_s2": 0.5, "roll_deg": 2.0}
# WH__rope does not respond to MH, so it is enabled but has no series points.
LIMITS: dict[str, dict] = {
    "MH__rope": {"T": 1500.0},
    "platform_base": {"max_bearing_line_load": 6000.0},
    "rear_hinge": {"Fx": 5000.0},
    "boom_hoist": {"T": 8000.0},
    "WH__rope": {"T": 100000.0},
}
NAMES = {"platform_base": "Bearing line load", "rear_hinge": "Rear hinge Fx"}


@pytest.fixture(scope="module")
def doc() -> CraneDocument:
    document = load_document(EXAMPLE)
    vm = document.environment.vessel_motion
    for field, value in VESSEL.items():
        setattr(vm, field, float(value))
    document.environment.max_wind_speed_m_s = 20.0
    return document


def _sweep(doc: CraneDocument, mode: str = "normal", **kwargs: Any) -> Optional[dict[str, Any]]:
    payload: Optional[dict[str, Any]] = run_mode_sweep(
        doc, HOIST, mode, LIMITS, STEP, NAMES, **kwargs
    )
    return payload


def test_layout_matches_the_final_series_order_and_labels(doc: CraneDocument) -> None:
    payload = _sweep(doc)
    assert payload is not None
    layout = limit_series_layout(doc, LIMITS, NAMES)
    assert {lid for lid, _label, _rank in layout} == set(LIMITS)
    rows = payload["limit_series"]
    assert len(rows) >= 2 and len(rows) < len(layout)
    with_points = {row[0] for row in rows}
    assert [row[:3] for row in rows] == [row for row in layout if row[0] in with_points]


def test_on_contractual_fires_once_before_any_curve_batch(doc: CraneDocument) -> None:
    events: list[tuple[str, Any]] = []
    payload = _sweep(
        doc,
        on_contractual=lambda rows: events.append(("contractual", rows)),
        on_points=lambda pts: events.append(("points", pts)),
        on_limit_points=lambda pts: events.append(("limits", pts)),
    )
    assert payload is not None and payload["contractual_results"]
    assert [kind for kind, _ in events].count("contractual") == 1
    assert events[0][0] == "contractual"
    assert events[0][1] == payload["contractual_results"]
    assert len(events) > 1


def test_on_contractual_not_called_without_contractual_points(doc: CraneDocument) -> None:
    calls: list[Any] = []
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    saved = (list(hoist.contractual_points), hoist.split_contractual_points)
    hoist.contractual_points = []
    hoist.split_contractual_points = []
    try:
        for mode in ("normal", "split"):
            payload = _sweep(doc, mode, on_contractual=calls.append)
            assert payload is None or payload["contractual_results"] == []
    finally:
        hoist.contractual_points, hoist.split_contractual_points = saved
    assert calls == []


def test_limit_batches_concatenate_to_the_final_series(doc: CraneDocument) -> None:
    point_batches: list[list] = []
    limit_batches: list[dict[str, list]] = []
    payload = _sweep(
        doc,
        batch_points=4,
        on_points=point_batches.append,
        on_limit_points=limit_batches.append,
    )
    assert payload is not None
    assert len(point_batches) > 2
    assert len(limit_batches) == len(point_batches)
    assert all(batch for batch in limit_batches)
    joined: dict[str, list] = {}
    for batch in limit_batches:
        for lid, pts in batch.items():
            assert isinstance(lid, str) and pts
            joined.setdefault(lid, []).extend(pts)
    assert len(joined) >= 2
    assert joined == {row[0]: row[3] for row in payload["limit_series"]}


def test_callbacks_do_not_change_the_payload(doc: CraneDocument) -> None:
    plain = _sweep(doc)
    streamed = _sweep(
        doc,
        batch_points=4,
        on_points=lambda _pts: None,
        on_contractual=lambda _rows: None,
        on_limit_points=lambda _pts: None,
    )
    assert streamed == plain


def test_an_empty_limit_in_the_middle_does_not_shift_the_others(doc: CraneDocument) -> None:
    # Ranks: BH 0, MH 1, WH 2, SH 3 for the ropes; non-rope limits start at 4 plus their
    # position among ALL enabled limits, the empty WH__rope included.
    limits: dict[str, dict] = {
        "MH__rope": {"T": 1500.0},
        "WH__rope": {"T": 100000.0},
        "platform_base": {"max_bearing_line_load": 6000.0},
        "rear_hinge": {"Fx": 5000.0},
        "boom_hoist": {"T": 8000.0},
    }
    layout = limit_series_layout(doc, limits, {})
    assert layout == [
        ("MH__rope", "MH__rope", 1),
        ("WH__rope", "WH__rope", 2),
        ("platform_base", "platform_base", 6),
        ("rear_hinge", "rear_hinge", 7),
        ("boom_hoist", "boom_hoist", 8),
    ]
    payload = run_mode_sweep(doc, HOIST, "normal", limits, STEP, {})
    assert payload is not None
    rows = [row[:3] for row in payload["limit_series"]]
    assert "WH__rope" not in {row[0] for row in rows}
    assert len(rows) >= 3
    assert rows == [row for row in layout if row[0] in {r[0] for r in rows}]


def test_unsolved_stage_one_gives_pending_verdicts_and_no_limit_batches(
    doc: CraneDocument, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("crane_statics.core.sweep.build_probes", lambda *a, **k: None)
    contractual: list[list] = []
    limit_batches: list[dict] = []
    payload = _sweep(
        doc,
        on_contractual=contractual.append,
        on_limit_points=limit_batches.append,
    )
    assert payload is not None
    assert payload["n_points"] == 0 and payload["curve_data"] == []
    assert payload["limit_series"] == []
    pending = payload["contractual_results"]
    assert pending and all(allow is None and ok is None for _cp, allow, ok in pending)
    assert contractual == [pending]
    assert limit_batches == []
