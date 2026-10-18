"""Compute cache for load-chart sweeps: fingerprint, probe sets and limit results."""

from __future__ import annotations

from pathlib import Path

from crane_statics.core import load_document
from crane_statics.core.sweep_cache import (
    ComputeCache,
    LimitResult,
    compute_fingerprint,
    limit_signature,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


class _Counter:
    def __init__(self, value=None) -> None:
        self.calls = 0
        self.value = value

    def __call__(self):
        self.calls += 1
        return self.value


def test_compute_fingerprint_ignores_contractual_points_only() -> None:
    doc = load_document(EXAMPLE)
    base = compute_fingerprint(doc)
    hoist = doc.hoists[0]
    hoist.contractual_points[0].load_t += 1.0
    assert compute_fingerprint(doc) == base
    if hoist.split_contractual_points:
        hoist.split_contractual_points[0].load_t += 1.0
        assert compute_fingerprint(doc) == base
    doc.environment.max_wind_speed_m_s += 1.0
    changed_wind = compute_fingerprint(doc)
    assert changed_wind != base
    doc.environment.vessel_motion.accel_x_m_s2 += 0.5
    assert compute_fingerprint(doc) != changed_wind


def test_probes_are_built_once_per_angle_and_none_is_cached() -> None:
    scope = ComputeCache().scope("fp", "MH", "normal")
    build = _Counter(object())
    first = scope.probes(30.0, build)
    assert scope.probes(30.0, build) is first
    assert build.calls == 1
    missing = _Counter(None)
    assert scope.probes(40.0, missing) is None
    assert scope.probes(40.0, missing) is None
    assert missing.calls == 1


def test_scopes_are_independent() -> None:
    cache = ComputeCache()
    build = _Counter(object())
    cache.scope("a", "MH", "normal").probes(30.0, build)
    cache.scope("b", "MH", "normal").probes(30.0, build)
    cache.scope("a", "AH", "normal").probes(30.0, build)
    cache.scope("a", "MH", "split").probes(30.0, build)
    assert build.calls == 4
    cache.scope("a", "MH", "normal").probes(30.0, build)
    assert build.calls == 4
    assert cache.probe_count() == 4


def test_probe_bound_evicts_least_recently_used() -> None:
    scope = ComputeCache(max_probe_sets=2).scope("fp", "MH", "normal")
    builds = {angle: _Counter(object()) for angle in (1.0, 2.0, 3.0)}
    for angle in (1.0, 2.0, 1.0, 3.0):
        scope.probes(angle, builds[angle])
    scope.probes(1.0, builds[1.0])
    scope.probes(2.0, builds[2.0])
    assert builds[1.0].calls == 1
    assert builds[2.0].calls == 2


def test_limit_results_are_cached_per_signature() -> None:
    scope = ComputeCache().scope("fp", "MH", "normal")
    sig_a = limit_signature("rope", {"T": 5.0})
    sig_b = limit_signature("rope", {"T": 6.0})
    assert sig_a != sig_b
    assert sig_a != limit_signature("rope", {"Fx": 5.0})
    assert limit_signature("p", {"Fx": 1.0, "Fz": 2.0}) == limit_signature(
        "p", {"Fz": 2.0, "Fx": 1.0}
    )
    result_a = _Counter(LimitResult(10.0, 98.0, True))
    result_b = _Counter(LimitResult(20.0, 196.0, False))
    assert scope.limit_result(30.0, sig_a, result_a) == LimitResult(10.0, 98.0, True)
    assert scope.limit_result(30.0, sig_b, result_b) == LimitResult(20.0, 196.0, False)
    scope.limit_result(30.0, sig_a, result_a)
    assert (result_a.calls, result_b.calls) == (1, 1)
    scope.limit_result(31.0, sig_a, result_a)
    assert result_a.calls == 2


def test_limit_bound_evicts() -> None:
    scope = ComputeCache(max_limit_results=2).scope("fp", "MH", "normal")
    sig = limit_signature("rope", {"T": 5.0})
    counters = {angle: _Counter(LimitResult(1.0, 9.8, True)) for angle in (1.0, 2.0, 3.0)}
    for angle in (1.0, 2.0, 3.0):
        scope.limit_result(angle, sig, counters[angle])
    scope.limit_result(1.0, sig, counters[1.0])
    scope.limit_result(3.0, sig, counters[3.0])
    assert counters[1.0].calls == 2
    assert counters[3.0].calls == 1
