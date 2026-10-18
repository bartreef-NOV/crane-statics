"""Load chart view model: probe solves and limit results are reused across redraws."""

import gc
from pathlib import Path

import pytest

from crane_statics.core import sweep as sweep_module
from crane_statics.core.chart_cache import ChartKey
from crane_statics.core.io import load_document
from crane_statics.core.sweep import build_absolute_outreach_grid, run_mode_sweep
from crane_statics.core.sweep_cache import ComputeCache
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from tests.test_chart_background import _planned, _visible, pump_events, wait_idle

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
STEP = 5.0


class Counter:
    """Counts the calls of a function it delegates to (called from worker threads)."""

    def __init__(self, real) -> None:
        self.real = real
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.real(*args, **kwargs)


@pytest.fixture
def probes(monkeypatch):
    counter = Counter(sweep_module.build_probes)
    monkeypatch.setattr(sweep_module, "build_probes", counter)
    return counter


@pytest.fixture
def envelopes(monkeypatch):
    counter = Counter(sweep_module.envelope_capacity)
    monkeypatch.setattr(sweep_module, "envelope_capacity", counter)
    return counter


@pytest.fixture
def vm(probes, envelopes):
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    # Drop view models left by earlier tests so their timers cannot start sweeps here.
    gc.collect()
    session = SessionState()
    view_model = ChartViewModel(session)
    view_model.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    yield view_model
    view_model.shutdown()
    pump_events(0.05)


def _enable_limits(vm: ChartViewModel) -> tuple[str, str]:
    """Auto-set one rope and one connection limit; returns their ids."""
    chosen = []
    for model in (vm.ropeLimitsModel, vm.connectionLimitsModel):
        for index in range(model.count):
            limit_id = model.row_at(index)["limitId"]
            vm.autoSetLimit(limit_id)
            if vm._model.design_limits_by_id[limit_id].enabled:
                chosen.append(limit_id)
                break
    if len(chosen) != 2:
        pytest.skip("Example has no auto-settable rope and connection limit")
    return chosen[0], chosen[1]


def _draw(vm: ChartViewModel) -> None:
    vm.draw()
    wait_idle(vm, timeout=120.0)


def _reset(*counters: Counter) -> None:
    for counter in counters:
        counter.calls = 0


def _uncached_payload(vm: ChartViewModel) -> dict:
    job = _visible(vm)
    doc = vm._model.document
    assert doc is not None
    payload = run_mode_sweep(
        doc,
        job.hoist_id,
        job.mode,
        vm._enabled_limits(),
        vm.outreachStep,
        vm._limit_display_names(),
    )
    assert payload is not None
    return payload


def _grid(vm: ChartViewModel) -> list[float]:
    hoist = vm._model.payload_hoist_by_id(vm.selectedHoistId)
    assert hoist is not None
    return build_absolute_outreach_grid(
        float(hoist.outreach_min_m or 0.0), float(hoist.outreach_max_m or 200.0), STEP
    )


def test_a_limit_edit_makes_no_probe_solves(vm, probes, envelopes):
    rope_id, _connection_id = _enable_limits(vm)
    _draw(vm)
    angles = probes.calls
    assert angles > 0
    assert len(vm._enabled_limits()) >= 2
    _reset(probes, envelopes)

    current = vm._model.design_limits_by_id[rope_id].max_kN
    vm.setLimitMax(rope_id, f"{0.8 * current:.1f}")
    wait_idle(vm, timeout=120.0)

    assert probes.calls == 0
    # Of the enabled limits only the edited one is evaluated again, once per angle.
    assert envelopes.calls == angles
    expected = _uncached_payload(vm)
    assert vm.curvePoints == [[float(x), float(y)] for x, y in expected["curve_data"]]
    assert [series["points"] for series in vm.limitSeries] == [
        [[float(x), float(y)] for x, y in points] for *_rest, points in expected["limit_series"]
    ]
    assert vm.stale is False


def test_a_limit_disable_makes_no_evaluations(vm, probes, envelopes):
    _rope_id, connection_id = _enable_limits(vm)
    _draw(vm)
    _reset(probes, envelopes)

    vm.setLimitEnabled(connection_id, False)
    wait_idle(vm, timeout=120.0)

    assert probes.calls == 0
    assert envelopes.calls == 0
    expected = _uncached_payload(vm)
    assert vm.curvePoints == [[float(x), float(y)] for x, y in expected["curve_data"]]


def test_a_contractual_edit_makes_no_new_probe_solves_for_known_angles(vm, probes):
    _enable_limits(vm)
    _draw(vm)
    grid = _grid(vm)
    _reset(probes)

    vm.addContractualPoint({"outreach_m": grid[len(grid) // 2], "load_t": 10.0})
    wait_idle(vm, timeout=120.0)
    assert probes.calls == 0

    vm.addContractualPoint({"outreach_m": grid[len(grid) // 2] + 0.5 * STEP, "load_t": 10.0})
    wait_idle(vm, timeout=120.0)
    assert probes.calls == 1
    expected = _uncached_payload(vm)
    assert vm.curvePoints == [[float(x), float(y)] for x, y in expected["curve_data"]]
    assert [m["status"] for m in vm.markers] == [
        "pending" if passed is None else ("pass" if passed else "fail")
        for _cp, _allowable, passed in expected["contractual_results"]
    ]


def test_a_document_edit_rebuilds_probes(vm, probes):
    _draw(vm)
    old_cache = vm._compute_cache
    _reset(probes)

    vm._model.document.environment.max_wind_speed_m_s += 1.0
    vm._model.mark_content_changed()
    wait_idle(vm, timeout=120.0)

    assert probes.calls > 0
    # The old fingerprint's entries can never hit again: the cache is replaced.
    assert vm._compute_cache is not old_cache
    expected = _uncached_payload(vm)
    assert vm.curvePoints == [[float(x), float(y)] for x, y in expected["curve_data"]]


def test_document_replaced_gets_a_new_cache(vm, probes):
    _draw(vm)
    old_cache = vm._compute_cache
    assert old_cache.probe_count() > 0
    _reset(probes)

    # The same content: only a new cache, not a changed fingerprint, forces the solves.
    vm._session.model.set_document(load_document(EXAMPLE))
    assert vm._compute_cache is not old_cache
    _draw(vm)

    assert probes.calls > 0


def test_background_precompute_still_fills_the_result_cache(vm):
    _enable_limits(vm)
    jobs = _planned(vm)

    _draw(vm)

    fingerprint = vm._wanted_key().fingerprint
    for job in jobs:
        assert vm._cache.get(ChartKey(job.hoist_id, job.mode, STEP, fingerprint)) is not None


def _probes_when_visible_done(vm: ChartViewModel, probes: Counter) -> list[int]:
    """Snapshot the probe counter as the wanted chart is cached, before the next job starts."""
    snapshots: list[int] = []
    original = vm._cache.put

    def recording(key, payload):
        if key == vm._wanted_key():
            snapshots.append(probes.calls)
        original(key, payload)

    vm._cache.put = recording  # type: ignore[method-assign]
    return snapshots


def test_background_jobs_do_not_evict_the_visible_charts_probes(vm, probes):
    rope_id, _connection_id = _enable_limits(vm)
    job = _visible(vm)
    _uncached_payload(vm)
    visible_angles = probes.calls
    _reset(probes)
    # Room for the visible chart and a few more: the background charts cannot all fit.
    vm._compute_cache = ComputeCache(max_probe_sets=visible_angles + 3)
    _draw(vm)
    assert probes.calls > visible_angles + 3
    assert _visible(vm) == job
    snapshots = _probes_when_visible_done(vm, probes)
    _reset(probes)

    current = vm._model.design_limits_by_id[rope_id].max_kN
    vm.setLimitMax(rope_id, f"{0.8 * current:.1f}")
    wait_idle(vm, timeout=120.0)

    assert snapshots == [0]
    expected = _uncached_payload(vm)
    assert vm.curvePoints == [[float(x), float(y)] for x, y in expected["curve_data"]]
