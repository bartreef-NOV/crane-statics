"""Load chart background jobs: priority queue, streaming and stale-result discarding."""

import gc
import threading
import time
from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QThread

from crane_statics.core.chart_cache import ChartJob, ChartKey, plan_chart_jobs
from crane_statics.core.io import load_document
from crane_statics.core.sweep import SweepCancelled, run_mode_sweep
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels import chart_vm as chart_vm_module
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
STEP = 5.0


def wait_until(predicate, timeout=30.0) -> None:
    """Pump the Qt event loop until ``predicate()`` holds; worker signals arrive this way."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def pump_events(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def _idle(vm: ChartViewModel) -> bool:
    return (
        getattr(vm, "_running", None) is None
        and not getattr(vm, "_queue", None)
        and getattr(vm, "_worker", None) is None
        and not vm._refresh_timer.isActive()
    )


def wait_idle(vm: ChartViewModel, timeout=30.0) -> None:
    wait_until(lambda: _idle(vm), timeout)


class SweepFake:
    """Records every sweep; delegates to the real one unless a job is held or streamed."""

    def __init__(self) -> None:
        self.calls: list[ChartJob] = []
        self.cancelled: list[ChartJob] = []
        self.started: dict[ChartJob, threading.Event] = {}
        self.threads: dict[ChartJob, QThread] = {}
        self._held: dict[ChartJob, tuple[threading.Event, bool]] = {}
        self._streams: dict[ChartJob, tuple[list, list[threading.Event]]] = {}
        self._gates: list[threading.Event] = []
        self._failing: set[ChartJob] = set()
        self._real = run_mode_sweep

    def hold(self, job: ChartJob, honour_cancel: bool = True) -> threading.Event:
        """Block the next sweep of ``job`` until the returned event is set."""
        release = threading.Event()
        self._held[job] = (release, honour_cancel)
        self.started[job] = threading.Event()
        self._gates.append(release)
        return release

    def stream(self, job: ChartJob, batches: list, fail: bool = False) -> list[threading.Event]:
        """Deliver ``batches`` one at a time; batch ``i`` waits on gate ``i`` once sent.

        With ``fail`` the sweep raises after the last batch instead of returning."""
        gates = [threading.Event() for _ in batches]
        self._streams[job] = (batches, gates)
        if fail:
            self._failing.add(job)
        self.started[job] = threading.Event()
        self._gates.extend(gates)
        return gates

    def release_all(self) -> None:
        for gate in self._gates:
            gate.set()

    def _wait(self, job, gate, honour_cancel, should_cancel) -> None:
        while not gate.wait(0.01):
            if honour_cancel and should_cancel is not None and should_cancel():
                self.cancelled.append(job)
                raise SweepCancelled()

    def __call__(self, doc, hoist_id, mode, *args, should_cancel=None, on_points=None, **kwargs):
        job = ChartJob(hoist_id, mode)
        self.calls.append(job)
        self.threads[job] = QThread.currentThread()
        if job in self._streams:
            batches, gates = self._streams.pop(job)
            self.started[job].set()
            for batch, gate in zip(batches, gates):
                if on_points is not None:
                    on_points(list(batch))
                self._wait(job, gate, True, should_cancel)
            if job in self._failing:
                raise RuntimeError("sweep blew up")
            curve = [point for batch in batches for point in batch]
            return {
                "curve_data": curve,
                "contractual_results": [],
                "limit_series": [],
                "n_points": len(curve),
            }
        held = self._held.pop(job, None)
        if held is not None:
            release, honour_cancel = held
            self.started[job].set()
            self._wait(job, release, honour_cancel, should_cancel)
            if not honour_cancel:
                # Simulates a sweep that completes before it notices the cancel request.
                should_cancel = None
        return self._real(
            doc,
            hoist_id,
            mode,
            *args,
            should_cancel=should_cancel,
            on_points=on_points,
            **kwargs,
        )


@pytest.fixture
def sweeps(monkeypatch):
    fake = SweepFake()
    monkeypatch.setattr(chart_vm_module, "run_mode_sweep", fake)
    return fake


@pytest.fixture
def vm(sweeps):
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    # Drop view models left by earlier tests so their timers cannot start sweeps here.
    gc.collect()
    session = SessionState()
    view_model = ChartViewModel(session)
    view_model.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    yield view_model
    sweeps.release_all()
    view_model.shutdown()
    pump_events(0.05)


def _visible(vm: ChartViewModel) -> ChartJob:
    return ChartJob(vm.selectedHoistId, vm.chartMode)


def _planned(vm: ChartViewModel) -> list[ChartJob]:
    return plan_chart_jobs(_visible(vm), vm.hoistIds, vm._model.is_splitable_hoist)


def _expected_curve(vm: ChartViewModel, job: ChartJob) -> list[list[float]]:
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
    return [[float(x), float(y)] for x, y in (payload or {}).get("curve_data", [])]


def _record_puts(vm: ChartViewModel) -> list[ChartKey]:
    puts: list[ChartKey] = []
    original = vm._cache.put

    def recording(key, payload):
        puts.append(key)
        original(key, payload)

    vm._cache.put = recording  # type: ignore[method-assign]
    return puts


def _other_hoist(vm: ChartViewModel) -> str:
    other = next((h for h in vm.hoistIds if h != vm.selectedHoistId), None)
    if other is None:
        pytest.skip("Example has one payload hoist")
    return str(other)


def test_draw_fills_the_cache_for_every_planned_job(vm, sweeps):
    jobs = _planned(vm)

    vm.draw()
    wait_idle(vm)

    fingerprint = vm._wanted_key().fingerprint
    for job in jobs:
        assert vm._cache.get(ChartKey(job.hoist_id, job.mode, STEP, fingerprint)) is not None
    assert sweeps.calls[0] == jobs[0]
    assert sorted(sweeps.calls) == sorted(jobs)


def test_switching_back_does_not_resweep_after_background_fill(vm, sweeps):
    first = vm.selectedHoistId
    vm.draw()
    wait_idle(vm)
    swept = len(sweeps.calls)

    for hoist_id in vm.hoistIds:
        vm.selectHoist(hoist_id)
        assert vm.stale is False
        assert vm.curvePoints
        vm.setChartMode("split")
        vm.setChartMode("normal")
        assert vm.stale is False
    vm.selectHoist(first)
    pump_events(0.4)
    wait_idle(vm)

    assert len(sweeps.calls) == swept
    assert vm.stale is False
    assert vm.busy is False


def test_selecting_an_unfinished_chart_jumps_the_queue(vm, sweeps):
    first = _visible(vm)
    other = _other_hoist(vm)
    sweeps.hold(first)
    vm.draw()
    wait_until(sweeps.started[first].is_set)

    vm.selectHoist(other)
    wait_idle(vm)

    assert sweeps.cancelled == [first]
    assert sweeps.calls[:3] == [first, ChartJob(other, "normal"), first]


def test_hoist_switch_during_a_sweep_shows_the_new_hoist(vm, sweeps):
    first = _visible(vm)
    other = _other_hoist(vm)
    # The held sweep ignores the cancel request and completes after the switch.
    release = sweeps.hold(first, honour_cancel=False)
    vm.draw()
    wait_until(sweeps.started[first].is_set)

    vm.selectHoist(other)
    release.set()
    wait_idle(vm)

    assert vm.selectedHoistId == other
    assert vm.curvePoints == _expected_curve(vm, ChartJob(other, "normal"))
    assert vm.stale is False
    assert vm.busy is False
    assert sweeps.calls.count(first) == 1


def test_edit_during_background_discards_old_fingerprint_results(vm, sweeps):
    visible = _visible(vm)
    release = sweeps.hold(visible, honour_cancel=False)
    vm.draw()
    wait_until(sweeps.started[visible].is_set)
    old_fingerprint = vm._wanted_key().fingerprint
    puts = _record_puts(vm)

    row = vm.ropeLimitsModel.record_at(0)
    current = vm._model.design_limits_by_id[row["limitId"]].max_kN or 1000.0
    vm.setLimitEnabled(row["limitId"], True)
    vm.setLimitMax(row["limitId"], f"{0.5 * current:.1f}")
    release.set()
    wait_idle(vm)

    assert vm._wanted_key().fingerprint != old_fingerprint
    assert puts
    assert all(key.fingerprint != old_fingerprint for key in puts)
    assert vm.curvePoints == _expected_curve(vm, visible)
    assert vm.stale is False


def test_streaming_grows_the_visible_curve(vm, sweeps):
    visible = _visible(vm)
    hoist = vm._model.payload_hoist_by_id(visible.hoist_id)
    batches = [[(10.0 + 5 * b + i, 200.0 - 5 * b - i) for i in range(5)] for b in range(4)]
    gates = sweeps.stream(visible, batches)
    updates: list[int] = []
    vm.chartUpdated.connect(lambda: updates.append(1))

    vm.draw()
    ranges = []
    for count, gate in enumerate(gates, start=1):
        wait_until(lambda n=5 * count: len(vm.curvePoints) >= n, timeout=10.0)
        assert len(vm.curvePoints) == 5 * count
        assert vm.busy is True
        ranges.append(dict(vm.axisRanges))
        gate.set()
    wait_until(lambda: vm._cache.get(vm._wanted_key()) is not None, timeout=10.0)

    final = [[float(x), float(y)] for batch in batches for x, y in batch]
    assert vm.curvePoints == final
    assert len(updates) <= len(batches) + 2
    for partial in ranges:
        assert partial["yMin"] == 0.0
        assert partial["xMin"] <= float(hoist.outreach_min_m)
        assert partial["xMax"] >= float(hoist.outreach_max_m)
    assert all((r["xMin"], r["xMax"]) == (ranges[0]["xMin"], ranges[0]["xMax"]) for r in ranges)


def _stream_batches() -> list:
    return [[(10.0 + 5 * b + i, 200.0 - 5 * b - i) for i in range(5)] for b in range(3)]


def test_failed_wanted_sweep_leaves_no_partial_curve(vm, sweeps):
    gates = sweeps.stream(_visible(vm), _stream_batches(), fail=True)
    vm.draw()
    wait_until(lambda: len(vm.curvePoints) == 5, timeout=10.0)
    assert vm.chartComplete is False

    for gate in gates:
        gate.set()
    wait_idle(vm)

    assert vm.curvePoints == []
    assert vm.limitSeries == []
    assert vm.markers == []
    assert vm._partial is False
    assert vm.chartComplete is True
    assert vm.statusText == "⚠ Sweep error"
    assert vm.busy is False


def test_export_is_refused_mid_stream_and_allowed_after_completion(vm, sweeps, tmp_path):
    from PyQt6.QtCore import QUrl

    gates = sweeps.stream(_visible(vm), _stream_batches())
    vm.draw()
    wait_until(lambda: len(vm.curvePoints) == 5, timeout=10.0)
    target = tmp_path / "partial.csv"

    assert vm.exportCsv(QUrl.fromLocalFile(str(target))) is False
    assert not target.exists()
    assert vm.statusText == "Export unavailable while the chart is still computing"

    for gate in gates:
        gate.set()
    wait_until(lambda: vm._cache.get(vm._wanted_key()) is not None, timeout=10.0)
    assert vm.exportCsv(QUrl.fromLocalFile(str(target))) is True
    capacity_rows = [
        line
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.startswith("capacity,")
    ]
    assert len(capacity_rows) == 15


def test_chart_complete_notifies_when_a_stream_starts_and_finishes(vm, sweeps):
    gates = sweeps.stream(_visible(vm), _stream_batches())
    seen: list[bool] = []
    vm.chartCompleteChanged.connect(lambda: seen.append(vm.chartComplete))
    assert vm.chartComplete is True

    vm.draw()
    wait_until(lambda: len(vm.curvePoints) == 5, timeout=10.0)
    assert seen == [False]
    for gate in gates:
        gate.set()
    wait_until(lambda: vm._cache.get(vm._wanted_key()) is not None, timeout=10.0)

    assert seen == [False, True]


def test_background_jobs_do_not_touch_the_displayed_chart(vm, sweeps):
    background = next(job for job in _planned(vm)[1:] if job.hoist_id != vm.selectedHoistId)
    release = sweeps.hold(background)
    vm.draw()
    wait_until(sweeps.started[background].is_set)
    shown = list(vm.curvePoints)
    status = vm.statusText
    updates: list[int] = []
    vm.chartUpdated.connect(lambda: updates.append(1))

    release.set()
    wait_idle(vm)

    assert shown
    assert updates == []
    assert vm.curvePoints == shown
    assert vm.statusText == status
    assert vm.stale is False
    assert vm.busy is False


def test_background_completion_keeps_an_unrelated_status(vm, sweeps, tmp_path):
    from PyQt6.QtCore import QUrl

    background = next(job for job in _planned(vm)[1:] if job.hoist_id != vm.selectedHoistId)
    release = sweeps.hold(background)
    vm.draw()
    wait_until(sweeps.started[background].is_set)
    assert vm.exportCsv(QUrl.fromLocalFile(str(tmp_path / "chart.csv"))) is True
    assert vm.statusText == "Exported chart.csv"

    release.set()
    wait_idle(vm)

    assert vm.statusText == "Exported chart.csv"


def test_document_replaced_while_running_is_safe(vm, sweeps):
    visible = _visible(vm)
    release = sweeps.hold(visible, honour_cancel=False)
    vm.draw()
    wait_until(sweeps.started[visible].is_set)
    old_fingerprint = vm._wanted_key().fingerprint
    puts = _record_puts(vm)

    replacement = load_document(EXAMPLE)
    replacement.environment.max_wind_speed_m_s += 1.0
    vm._session.model.set_document(replacement)
    release.set()
    wait_idle(vm)

    assert all(key.fingerprint != old_fingerprint for key in puts)
    assert vm.curvePoints == _expected_curve(vm, _visible(vm))
    assert vm.busy is False


def test_shutdown_stops_a_running_background_job(vm, sweeps):
    background = next(job for job in _planned(vm)[1:] if job.hoist_id != vm.selectedHoistId)
    sweeps.hold(background)
    vm.draw()
    wait_until(sweeps.started[background].is_set)
    thread = sweeps.threads[background]

    vm.shutdown()

    assert sweeps.cancelled == [background]
    assert not thread.isRunning()
    pump_events(0.3)
    calls = len(sweeps.calls)
    vm.draw()
    pump_events(0.1)
    assert len(sweeps.calls) == calls


def test_parent_deleting_the_view_model_stops_its_workers(sweeps):
    # The QML engine owns the view model and may delete it without shutdown().
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    parent = QObject()
    session = SessionState()
    view_model = ChartViewModel(session, parent)
    view_model.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    background = next(job for job in _planned(view_model)[1:])
    release = sweeps.hold(background)
    view_model.draw()
    wait_until(sweeps.started[background].is_set)
    thread = sweeps.threads[background]
    calls = len(sweeps.calls)

    sip.delete(parent)
    release.set()
    # Its first signal finds the receiver gone: the sweep is cancelled, nothing follows.
    wait_until(lambda: not thread.isRunning(), timeout=10.0)
    pump_events(0.5)

    assert sip.isdeleted(view_model)
    assert len(sweeps.calls) == calls


def test_non_splittable_hoist_gets_no_split_job(vm, sweeps):
    non_splittable = [h for h in vm.hoistIds if not vm._model.is_splitable_hoist(h)]
    if not non_splittable:
        pytest.skip("No non-splittable hoist in example")

    vm.draw()
    wait_idle(vm)

    for hoist_id in non_splittable:
        assert ChartJob(hoist_id, "normal") in sweeps.calls
        assert ChartJob(hoist_id, "split") not in sweeps.calls
