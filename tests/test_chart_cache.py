"""The chart result cache, its document fingerprint and the precompute job planner."""

from __future__ import annotations

from pathlib import Path

from crane_statics.core import load_document
from crane_statics.core.chart_cache import (
    ChartCache,
    ChartJob,
    ChartKey,
    chart_fingerprint,
    empty_payload,
    plan_chart_jobs,
)

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}


def _key(name: str) -> ChartKey:
    return ChartKey(name, "normal", 5.0, "fp")


def test_fingerprint_changes_with_document_limits_and_names_and_restores_on_undo() -> None:
    doc = load_document(EXAMPLE)
    base = chart_fingerprint(doc, LIMITS, {})
    assert chart_fingerprint(doc, LIMITS, {}) == base

    cp = doc.hoists[0].contractual_points[0]
    original = cp.load_t
    cp.load_t = original + 1.0
    assert chart_fingerprint(doc, LIMITS, {}) != base
    cp.load_t = original
    assert chart_fingerprint(doc, LIMITS, {}) == base

    assert chart_fingerprint(doc, {"boom_hoist": {"T": 4000.0}}, {}) != base
    assert chart_fingerprint(doc, LIMITS, {"boom_hoist": "Boom hoist"}) != base


def test_empty_payload_is_empty() -> None:
    payload = empty_payload()
    assert payload["curve_data"] == []
    assert payload["contractual_results"] == []
    assert payload["limit_series"] == []
    assert payload["n_points"] == 0


def test_cache_is_lru_with_bound() -> None:
    cache = ChartCache(max_entries=2)
    a, b, c = _key("a"), _key("b"), _key("c")
    cache.put(a, empty_payload())
    cache.put(b, empty_payload())
    assert cache.get(a) is not None
    cache.put(c, empty_payload())
    assert len(cache) == 2
    assert cache.get(b) is None
    assert cache.get(a) is not None
    assert cache.get(c) is not None
    cache.clear()
    assert len(cache) == 0


def test_plan_orders_visible_then_other_mode_then_other_hoists() -> None:
    def splitable(hoist_id: str) -> bool:
        return hoist_id == "B"

    assert plan_chart_jobs(ChartJob("B", "normal"), ["A", "B", "C"], splitable) == [
        ChartJob("B", "normal"),
        ChartJob("B", "split"),
        ChartJob("A", "normal"),
        ChartJob("C", "normal"),
    ]
    assert plan_chart_jobs(ChartJob("B", "split"), ["A", "B", "C"], splitable) == [
        ChartJob("B", "split"),
        ChartJob("B", "normal"),
        ChartJob("A", "normal"),
        ChartJob("C", "normal"),
    ]


def test_plan_never_plans_split_for_a_non_splittable_hoist() -> None:
    jobs = plan_chart_jobs(ChartJob("A", "normal"), ["A", "B"], lambda _h: False)
    assert jobs == [ChartJob("A", "normal"), ChartJob("B", "normal")]


def test_plan_has_no_duplicates() -> None:
    jobs = plan_chart_jobs(ChartJob("A", "split"), ["A", "A", "B"], lambda _h: True)
    assert len(jobs) == len(set(jobs))
