"""Load chart streaming: limit series and contractual points show while a chart computes."""

import gc
import threading

import pytest
from PyQt6.QtCore import QThread

from crane_statics.core.chart_cache import ChartJob
from crane_statics.core.io import load_document
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels import chart_vm as chart_vm_module
from crane_statics.qml_app.viewmodels.chart_vm import _LIMIT_COLORS, ChartViewModel
from tests.test_chart_background import (
    EXAMPLE,
    STEP,
    SweepFake,
    _planned,
    _visible,
)
from tests.qt_helpers import pump_events, wait_until


class LiveSweeps(SweepFake):
    """A SweepFake that can also play a scripted sweep through every streaming callback."""

    def __init__(self) -> None:
        super().__init__()
        self._scripts: dict[ChartJob, tuple[list, list[threading.Event], dict]] = {}

    def script(self, job: ChartJob, steps: list, payload: dict) -> list[threading.Event]:
        """Play ``steps`` for the next sweep of ``job``, then return ``payload``.

        A step is ``("points", batch)``, ``("contractual", verdicts)`` or ``("limits",
        {limit id: points})``. Gate ``i`` must be set before step ``i`` is delivered; the
        last gate (one more than the steps) before the payload is returned."""
        gates = [threading.Event() for _ in range(len(steps) + 1)]
        self._scripts[job] = (steps, gates, payload)
        self.started[job] = threading.Event()
        self._gates.extend(gates)
        return gates

    def __call__(self, doc, hoist_id, mode, *args, **kwargs):
        job = ChartJob(hoist_id, mode)
        if job not in self._scripts:
            return super().__call__(doc, hoist_id, mode, *args, **kwargs)
        self.calls.append(job)
        self.threads[job] = QThread.currentThread()
        steps, gates, payload = self._scripts.pop(job)
        callbacks = {
            "points": kwargs.get("on_points"),
            "contractual": kwargs.get("on_contractual"),
            "limits": kwargs.get("on_limit_points"),
        }
        should_cancel = kwargs.get("should_cancel")
        self.started[job].set()
        for (kind, data), gate in zip(steps, gates):
            self._wait(job, gate, True, should_cancel)
            callback = callbacks[kind]
            if callback is not None:
                callback(data)
        self._wait(job, gates[-1], True, should_cancel)
        return payload


@pytest.fixture
def sweeps(monkeypatch):
    fake = LiveSweeps()
    monkeypatch.setattr(chart_vm_module, "run_mode_sweep", fake)
    return fake


@pytest.fixture
def vm(sweeps):
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    gc.collect()
    session = SessionState()
    view_model = ChartViewModel(session)
    view_model.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    yield view_model
    sweeps.release_all()
    view_model.shutdown()
    pump_events(0.05)


def _payload(steps: list) -> dict:
    """The final payload a sweep that delivered ``steps`` returns."""
    curve = [point for kind, data in steps if kind == "points" for point in data]
    verdicts: list = next((data for kind, data in steps if kind == "contractual"), [])
    limits: dict[str, list] = {}
    for kind, data in steps:
        if kind == "limits":
            for limit_id, points in data.items():
                limits.setdefault(limit_id, []).extend(points)
    labels = {"BH__rope_T": "BH", "MH__rope_T": "MH", "WH__rope_T": "WH", "SH__rope_T": "SH"}
    ranks = {"BH__rope_T": 0, "MH__rope_T": 1, "WH__rope_T": 2, "SH__rope_T": 3}
    return {
        "curve_data": curve,
        "contractual_results": list(verdicts),
        "limit_series": [
            (limit_id, labels[limit_id], ranks[limit_id], points)
            for limit_id, points in sorted(limits.items(), key=lambda item: ranks[item[0]])
        ],
        "n_points": len(curve),
    }


def _verdicts(points: list) -> list:
    """Alternating pass and fail verdicts, with allowables either side of each load."""
    return [
        (cp, cp.load_t + 10.0, True) if index % 2 == 0 else (cp, cp.load_t - 10.0, False)
        for index, cp in enumerate(points)
    ]


def _pending(points: list) -> list[dict]:
    return [
        {"outreach": float(cp.outreach_m), "load": float(cp.load_t), "status": "pending"}
        for cp in points
    ]


def _table(vm: ChartViewModel) -> list[dict]:
    model = vm.contractualModel
    return [model.record_at(index) for index in range(model.count)]


def _curve_steps() -> list:
    return [
        ("points", [(30.0, 250.0), (35.0, 240.0)]),
        ("limits", {"MH__rope_T": [(30.0, 900.0)]}),
        ("points", [(40.0, 230.0)]),
        ("limits", {"MH__rope_T": [(35.0, 880.0)], "SH__rope_T": [(35.0, 5000.0)]}),
    ]


def _disable_limits(vm: ChartViewModel, *limit_ids: str) -> None:
    for limit_id in limit_ids:
        vm.setLimitEnabled(limit_id, False)


def test_contractual_markers_are_grey_from_the_start_then_decided(vm, sweeps):
    job = _visible(vm)
    points = vm._contractual_points()
    assert points
    verdicts = _verdicts(points)
    steps = [("contractual", verdicts), ("points", [(30.0, 250.0)])]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    wait_until(sweeps.started[job].is_set)
    pump_events(0.05)

    assert vm.markers == _pending(points)
    assert [row["status"] for row in _table(vm)] == ["pending"] * len(points)
    assert vm.chartComplete is False

    gates[0].set()
    wait_until(lambda: vm.markers and vm.markers[0]["status"] != "pending", timeout=10.0)

    assert [m["status"] for m in vm.markers] == [
        "pass" if passed else "fail" for _cp, _allowable, passed in verdicts
    ]
    assert [(m["outreach"], m["load"]) for m in vm.markers] == [
        (cp.outreach_m, cp.load_t) for cp in points
    ]
    assert [row["allowable"] for row in _table(vm)] == [
        f"{allowable:.1f}" for _cp, allowable, _passed in verdicts
    ]
    assert vm.chartComplete is False
    assert vm.busy is True


def test_limit_series_stream_in_with_stable_colours(vm, sweeps):
    # Two enabled limits in display order BH, MH; BH never yields a point.
    _disable_limits(vm, "WH__rope_T", "SH__rope_T")
    job = _visible(vm)
    steps = [
        ("points", [(30.0, 250.0)]),
        ("limits", {"MH__rope_T": [(30.0, 900.0)]}),
        ("limits", {"MH__rope_T": [(35.0, 880.0)]}),
    ]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    wait_until(sweeps.started[job].is_set)
    assert vm.limitSeries == []
    gates[0].set()
    gates[1].set()
    wait_until(lambda: bool(vm.limitSeries), timeout=10.0)

    assert vm.limitSeries == [
        {"id": "MH__rope_T", "label": "MH", "color": _LIMIT_COLORS[1], "points": [[30.0, 900.0]]}
    ]
    gates[2].set()
    wait_until(lambda: len(vm.limitSeries[0]["points"]) == 2, timeout=10.0)
    assert vm.limitSeries[0]["points"] == [[30.0, 900.0], [35.0, 880.0]]
    assert vm.chartComplete is False

    gates[3].set()
    wait_until(lambda: vm.chartComplete, timeout=10.0)
    assert vm.limitSeries == [
        {
            "id": "MH__rope_T",
            "label": "MH",
            "color": _LIMIT_COLORS[1],
            "points": [[30.0, 900.0], [35.0, 880.0]],
        }
    ]


def test_split_mode_streams_its_own_contractual_points(vm, sweeps):
    if not vm.splitable:
        pytest.skip("Selected hoist cannot split")
    vm.setChartMode("split")
    split = _visible(vm)
    assert split.mode == "split"
    split_points = vm._contractual_points()
    normal_points = list(vm._model.contractual_points_for_mode(split.hoist_id, "normal"))
    assert split_points and _pending(split_points) != _pending(normal_points)
    sweeps.script(split, [], _payload([]))

    vm.draw()
    wait_until(sweeps.started[split].is_set)

    assert vm.markers == _pending(split_points)
    assert len(_table(vm)) == len(split_points)

    # A mode without contractual points (the normal mode, emptied): no markers, no rows.
    vm.setChartMode("normal")
    normal = _visible(vm)
    for _ in range(len(normal_points)):
        vm.deleteContractualPoint(0)
    assert vm._contractual_points() == []
    sweeps.script(normal, [], _payload([]))
    vm.draw()
    wait_until(sweeps.started[normal].is_set, timeout=10.0)
    wait_until(lambda: vm._running is not None and vm._running_is_wanted(), timeout=10.0)

    assert vm.markers == []
    assert _table(vm) == []
    assert vm.chartComplete is False


def _stream_until_decided(vm: ChartViewModel, sweeps: LiveSweeps) -> list[threading.Event]:
    """Start the wanted chart and let it deliver verdicts, curve points and limit series."""
    job = _visible(vm)
    steps = [("contractual", _verdicts(vm._contractual_points()))] + _curve_steps()
    gates = sweeps.script(job, steps, _payload(steps))
    vm.draw()
    for gate in gates[:-1]:
        gate.set()
    wait_until(lambda: len(vm.limitSeries) == 2, timeout=10.0)
    assert any(m["status"] != "pending" for m in vm.markers)
    return gates


def _hold_next(vm: ChartViewModel, sweeps, job: ChartJob) -> None:
    sweeps.script(job, [], _payload([]))


@pytest.mark.parametrize("action", ["hoist", "mode", "edit", "cancel"])
def test_mid_stream_switch_leaves_nothing_behind(vm, sweeps, action):
    first = _visible(vm)
    _stream_until_decided(vm, sweeps)

    if action == "hoist":
        other = next(h for h in vm.hoistIds if h != first.hoist_id)
        wanted = ChartJob(other, "normal")
        _hold_next(vm, sweeps, wanted)
        vm.selectHoist(other)
    elif action == "mode":
        if not vm.splitable:
            pytest.skip("Selected hoist cannot split")
        wanted = ChartJob(first.hoist_id, "split")
        _hold_next(vm, sweeps, wanted)
        vm.setChartMode("split")
    elif action == "edit":
        wanted = first
        _hold_next(vm, sweeps, wanted)
        vm.addContractualPoint({"outreach_m": 45.0, "load_t": 10.0})
        # At once, before the old worker notices the cancel: nothing of it stays on screen.
        assert vm.limitSeries == []
        assert vm.curvePoints == []
        assert all(m["status"] == "pending" for m in vm.markers)
    else:
        wanted = None
        vm._cancel_all()

    if wanted is None:
        wait_until(lambda: vm._running is None, timeout=10.0)
        pump_events(0.05)
        expected: list[dict] = []
    else:
        assert _visible(vm) == wanted
        wait_until(sweeps.started[wanted].is_set, timeout=10.0)
        wait_until(lambda: vm._running is not None and vm._running_is_wanted(), timeout=10.0)
        expected = _pending(vm._contractual_points())
        assert expected

    assert vm.limitSeries == []
    assert vm.markers == expected
    assert [row["status"] for row in _table(vm)] == ["pending"] * len(vm._contractual_points())
    assert all(row["allowable"] == "" for row in _table(vm))
    assert all(p[1] != 250.0 for p in vm.curvePoints)


def test_cached_chart_renders_without_streaming(vm, sweeps):
    points = vm._contractual_points()
    verdicts = _verdicts(points)
    steps = [
        ("contractual", verdicts),
        ("points", [(30.0, 250.0), (40.0, 230.0)]),
        ("limits", {"MH__rope_T": [(30.0, 900.0)], "SH__rope_T": [(35.0, 150.0)]}),
    ]
    vm._cache.put(vm._wanted_key(), _payload(steps))

    vm.reload()
    vm._refresh_timer.stop()

    assert sweeps.calls == []
    assert vm.chartComplete is True
    assert vm.curvePoints == [[30.0, 250.0], [40.0, 230.0]]
    # The colour is the position among all enabled limits (BH, MH, WH, SH).
    assert vm.limitSeries == [
        {"id": "MH__rope_T", "label": "MH", "color": _LIMIT_COLORS[1], "points": [[30.0, 900.0]]},
        {"id": "SH__rope_T", "label": "SH", "color": _LIMIT_COLORS[3], "points": [[35.0, 150.0]]},
    ]
    assert [m["status"] for m in vm.markers] == [
        "pass" if passed else "fail" for _cp, _allowable, passed in verdicts
    ]
    assert [row["allowable"] for row in _table(vm)] == [
        f"{allowable:.1f}" for _cp, allowable, _passed in verdicts
    ]


def test_background_jobs_do_not_touch_series_or_markers(vm, sweeps):
    visible = _visible(vm)
    # The job right behind the wanted one; every later job is held.
    background = _planned(vm)[1]
    steps = [("contractual", _verdicts(vm._contractual_points()))] + _curve_steps()
    background_points = vm._model.contractual_points_for_mode(background.hoist_id, background.mode)
    background_steps = [
        ("contractual", _verdicts(background_points)),
        ("points", [(50.0, 100.0)]),
        ("limits", {"WH__rope_T": [(50.0, 300.0)]}),
    ]
    gates = sweeps.script(visible, steps, _payload(steps))
    background_gates = sweeps.script(background, background_steps, _payload(background_steps))
    for job in _planned(vm):
        if job not in (visible, background):
            sweeps.hold(job)

    vm.draw()
    for gate in gates:
        gate.set()
    wait_until(sweeps.started[background].is_set, timeout=10.0)
    shown = (list(vm.curvePoints), list(vm.limitSeries), list(vm.markers), _table(vm))
    assert vm.chartComplete is True
    assert shown[1] and shown[2]
    updates: list[int] = []
    vm.chartUpdated.connect(lambda: updates.append(1))

    for gate in background_gates:
        gate.set()
    wait_until(lambda: vm._cache.get(vm._job_key(background)) is not None, timeout=10.0)
    pump_events(0.05)

    assert updates == []
    assert (vm.curvePoints, vm.limitSeries, vm.markers, _table(vm)) == shown


def test_limit_series_do_not_stretch_the_partial_y_axis(vm, sweeps):
    job = _visible(vm)
    steps = [("contractual", _verdicts(vm._contractual_points()))] + _curve_steps()
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    for gate in gates[:-1]:
        gate.set()
    wait_until(lambda: len(vm.limitSeries) == 2, timeout=10.0)

    assert vm.chartComplete is False
    assert max(p[1] for series in vm.limitSeries for p in series["points"]) == 5000.0
    assert max(m["load"] for m in vm.markers) > 250.0
    y_top = 250.0
    assert vm.axisRanges["yMax"] == pytest.approx(y_top + max(1.0, y_top * 0.05))
    assert vm.axisRanges["yMin"] == 0.0


def test_markers_set_the_partial_y_axis_until_the_curve_arrives(vm, sweeps):
    job = _visible(vm)
    hoist = vm._model.payload_hoist_by_id(job.hoist_id)
    loads = [cp.load_t for cp in vm._contractual_points()]
    # A limit series far above every marker, with no capacity point yet.
    steps = [("limits", {"MH__rope_T": [(30.0, 50000.0)]}), ("points", [(30.0, 250.0)])]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    gates[0].set()
    wait_until(lambda: bool(vm.limitSeries), timeout=10.0)

    assert vm.curvePoints == []
    ranges = vm.axisRanges
    y_top = max(loads)
    assert ranges["yMax"] == pytest.approx(y_top + max(1.0, y_top * 0.05))
    assert ranges["yMin"] == 0.0
    assert all(ranges["yMin"] <= m["load"] <= ranges["yMax"] for m in vm.markers)
    assert ranges["xMin"] <= float(hoist.outreach_min_m)
    assert ranges["xMax"] >= float(hoist.outreach_max_m)

    # The first curve batch takes over the y range.
    gates[1].set()
    wait_until(lambda: bool(vm.curvePoints), timeout=10.0)
    assert vm.axisRanges["yMax"] == pytest.approx(250.0 + max(1.0, 250.0 * 0.05))
    assert vm.axisRanges["yMin"] == 0.0


def test_partial_y_axis_without_curve_or_markers_keeps_the_default(vm, sweeps):
    for _ in range(len(vm._contractual_points())):
        vm.deleteContractualPoint(0)
    assert vm._contractual_points() == []
    job = _visible(vm)
    steps = [("limits", {"MH__rope_T": [(30.0, 50000.0)]})]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    gates[0].set()
    wait_until(lambda: bool(vm.limitSeries), timeout=10.0)

    assert vm.chartComplete is False
    assert vm.curvePoints == [] and vm.markers == []
    assert vm.axisRanges["yMin"] == 0.0
    assert vm.axisRanges["yMax"] == pytest.approx(2.0)


def test_a_disabled_limit_takes_no_colour(vm, sweeps):
    # BH comes first in display order; disabled, it must not shift MH's colour.
    _disable_limits(vm, "BH__rope_T")
    job = _visible(vm)
    steps = [("points", [(30.0, 250.0)]), ("limits", {"MH__rope_T": [(30.0, 900.0)]})]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    gates[0].set()
    gates[1].set()
    wait_until(lambda: bool(vm.limitSeries), timeout=10.0)
    assert [(s["id"], s["color"]) for s in vm.limitSeries] == [("MH__rope_T", _LIMIT_COLORS[0])]

    gates[2].set()
    wait_until(lambda: vm.chartComplete, timeout=10.0)
    assert [(s["id"], s["color"]) for s in vm.limitSeries] == [("MH__rope_T", _LIMIT_COLORS[0])]


def test_background_job_promoted_mid_stream_shows_what_it_delivered(vm, sweeps):
    visible = _visible(vm)
    background = _planned(vm)[1]
    assert background == ChartJob(visible.hoist_id, "split")
    split_points = vm._model.contractual_points_for_mode(background.hoist_id, "split")
    verdicts = _verdicts(split_points)
    steps = [("points", [(30.0, 250.0)])]
    background_steps = [
        ("contractual", verdicts),
        ("points", [(40.0, 230.0)]),
        ("limits", {"MH__rope_T": [(40.0, 700.0)]}),
    ]
    gates = sweeps.script(visible, steps, _payload(steps))
    background_gates = sweeps.script(background, background_steps, _payload(background_steps))
    for job in _planned(vm)[2:]:
        sweeps.hold(job)

    vm.draw()
    for gate in gates:
        gate.set()
    wait_until(sweeps.started[background].is_set, timeout=10.0)
    for gate in background_gates[:-1]:
        gate.set()
    wait_until(
        lambda: vm._running is not None and bool(vm._running.stream.limit_points), timeout=10.0
    )
    # Still the finished normal chart on screen.
    assert vm.chartComplete is True
    assert vm.curvePoints == [[30.0, 250.0]]

    vm.setChartMode("split")

    assert vm._running is not None and vm._running.job == background
    assert vm.chartComplete is False
    assert vm.curvePoints == [[40.0, 230.0]]
    assert vm.limitSeries == [
        {"id": "MH__rope_T", "label": "MH", "color": _LIMIT_COLORS[1], "points": [[40.0, 700.0]]}
    ]
    assert [m["status"] for m in vm.markers] == [
        "pass" if passed else "fail" for _cp, _allowable, passed in verdicts
    ]
    assert [row["allowable"] for row in _table(vm)] == [
        f"{allowable:.1f}" for _cp, allowable, _passed in verdicts
    ]


def test_signals_of_one_turn_emit_chart_updated_once(vm, sweeps):
    job = _visible(vm)
    release = sweeps.hold(job)
    vm.draw()
    wait_until(sweeps.started[job].is_set, timeout=10.0)
    worker = vm._running.worker
    updates: list[int] = []
    vm.chartUpdated.connect(lambda: updates.append(1))

    vm._on_worker_points(worker, [(30.0, 250.0), (31.0, 240.0)])
    vm._on_worker_limit_points(worker, {"MH__rope_T": [(30.0, 900.0)]})
    vm._on_worker_points(worker, [(32.0, 230.0)])
    assert updates == []
    pump_events(0.05)

    assert len(updates) == 1
    assert vm.curvePoints == [[30.0, 250.0], [31.0, 240.0], [32.0, 230.0]]
    assert [(s["id"], s["points"]) for s in vm.limitSeries] == [("MH__rope_T", [[30.0, 900.0]])]
    release.set()


def test_finished_chart_without_curve_points_does_not_use_the_partial_axes(vm, sweeps):
    job = _visible(vm)
    steps = [("contractual", _verdicts(vm._contractual_points()))]
    gates = sweeps.script(job, steps, _payload(steps))

    vm.draw()
    for gate in gates:
        gate.set()
    wait_until(lambda: vm._cache.get(vm._wanted_key()) is not None, timeout=10.0)
    pump_events(0.05)

    assert vm.chartComplete is True
    assert vm.curvePoints == [] and vm.markers
    xs = [m["outreach"] for m in vm.markers]
    ranges = vm.axisRanges
    assert ranges["xMin"] == pytest.approx(min(xs) - max(1.0, (max(xs) - min(xs)) * 0.05))


def test_an_edit_keeps_the_unchanged_limit_series_on_screen(vm, sweeps):
    job = _visible(vm)
    first = [
        ("contractual", _verdicts(vm._contractual_points())),
        ("points", [(30.0, 250.0), (40.0, 230.0)]),
        ("limits", {"MH__rope_T": [(30.0, 900.0)], "SH__rope_T": [(35.0, 5000.0)]}),
    ]
    gates = sweeps.script(job, first, _payload(first))
    vm.draw()
    for gate in gates:
        gate.set()
    wait_until(lambda: vm.chartComplete and bool(vm.limitSeries), timeout=10.0)
    mh_before = next(s for s in vm.limitSeries if s["id"] == "MH__rope_T")

    # Edit SH only; the redraw replays every limit, as the real sweep does from its cache.
    second = [
        ("points", [(30.0, 250.0)]),
        ("limits", {"MH__rope_T": [(30.0, 900.0)], "SH__rope_T": [(35.0, 4000.0)]}),
    ]
    gates = sweeps.script(job, second, _payload(second))
    vm.setLimitMax("SH__rope_T", "1234")
    vm.draw()
    wait_until(sweeps.started[job].is_set, timeout=10.0)
    wait_until(lambda: vm._running is not None and vm._running_is_wanted(), timeout=10.0)

    # Streaming: MH stays where it was, SH is gone until its new points arrive, the curve restarts.
    assert vm.chartComplete is False
    assert vm.curvePoints == []
    assert [s["id"] for s in vm.limitSeries] == ["MH__rope_T"]
    assert vm.limitSeries[0] == mh_before

    gates[0].set()
    gates[1].set()
    wait_until(lambda: len(vm.limitSeries) == 2, timeout=10.0)
    # The replay of MH is ignored; SH shows only its new points.
    assert next(s for s in vm.limitSeries if s["id"] == "MH__rope_T")["points"] == [[30.0, 900.0]]
    assert next(s for s in vm.limitSeries if s["id"] == "SH__rope_T")["points"] == [[35.0, 4000.0]]

    gates[2].set()
    wait_until(lambda: vm.chartComplete, timeout=10.0)
    assert [s["id"] for s in vm.limitSeries] == ["MH__rope_T", "SH__rope_T"]


def test_a_changed_hoist_keeps_nothing_from_the_chart_on_screen(vm, sweeps):
    job = _visible(vm)
    first = [("points", [(30.0, 250.0)]), ("limits", {"MH__rope_T": [(30.0, 900.0)]})]
    gates = sweeps.script(job, first, _payload(first))
    vm.draw()
    for gate in gates:
        gate.set()
    wait_until(lambda: vm.chartComplete and bool(vm.limitSeries), timeout=10.0)

    assert (
        vm._unchanged_limit_series(
            vm._wanted_key()._replace(hoist_id="other"),
            vm._displayed_chart.compute,
            vm._enabled_limits(),
        )
        == {}
    )
    assert (
        vm._unchanged_limit_series(vm._wanted_key(), "another-document", vm._enabled_limits()) == {}
    )
