"""Load chart view model: show a clicked chart point's governing case in the Scene."""

from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import pytest
from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal

from crane_statics.core.governing_case import governing_case
from crane_statics.core.io import load_document
from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels import chart_vm as chart_vm_module
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
STEP = 10.0
ROPE = "MH__rope_T"
HINGE = "rear_hinge_Fx"
# Enabled, but WH's rope does not respond to MH's hook load: never a series of MH's chart.
UNRESPONSIVE = "WH__rope_T"


class MockCanvas(QObject):
    """Minimal canvas providing a renderer for headless testing."""

    boomAngleChanged = pyqtSignal(float)
    tackleLengthChanged = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.renderer = CraneSceneRenderer(self)

    def setSceneViewModel(self, scene_vm: Any) -> None:
        pass


def wait_until(predicate, timeout: float = 60.0) -> None:
    """Pump the Qt event loop until ``predicate()`` holds; worker signals arrive this way."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def _count(signal: Any) -> list[int]:
    hits = [0]
    signal.connect(lambda *_: hits.__setitem__(0, hits[0] + 1))
    return hits


class Pair:
    def __init__(self) -> None:
        self.session = SessionState()
        self.scene = SceneViewModel(self.session)
        self.scene.bindCanvas(MockCanvas())
        self.chart = ChartViewModel(self.session)
        self.chart.set_scene_view_model(self.scene)
        self.chart._outreach_step = STEP
        self.session.model.set_document(load_document(EXAMPLE))
        self.chart.setLimitMax(HINGE, "5000")
        self.chart.setLimitEnabled(HINGE, True)

    def draw(self) -> None:
        self.chart.drawBlocking()
        # No background sweeps of the other charts while a test runs.
        self.chart._refresh_timer.stop()
        assert not self.chart.stale and not self.chart.busy

    def series(self, limit_id: str) -> dict[str, Any]:
        return next(s for s in self.chart.limitSeries if s["id"] == limit_id)

    def scene_fields(self) -> dict[str, Any]:
        state = self.session.model.get_active_hoist_state()
        assert state is not None
        return dataclasses.asdict(state.scene_state)


@pytest.fixture
def pair() -> Iterator[Pair]:
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    p = Pair()
    yield p
    p.chart.shutdown()


@pytest.fixture
def drawn(pair: Pair) -> Pair:
    pair.draw()
    return pair


class Gate:
    """Replaces ``governing_case`` in the view model; holds the worker until released."""

    def __init__(self, result: Any = None, delegate: bool = True) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls: list[tuple[Any, ...]] = []
        self.result = result
        self.delegate = delegate

    def __call__(self, *args: Any) -> Any:
        self.calls.append(args)
        self.started.set()
        self.release.wait(30.0)
        return governing_case(*args) if self.delegate else self.result


def test_show_applies_case_and_emits_signal(drawn: Pair) -> None:
    chart, scene = drawn.chart, drawn.scene
    series = drawn.series(ROPE)
    outreach = float(series["points"][0][0])
    assert chart.governingCaseAvailable(ROPE)
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase(ROPE, outreach)
    wait_until(lambda: shown[0] == 1)

    doc = drawn.session.model.document
    assert doc is not None
    expected = governing_case(doc, "MH", "normal", chart._enabled_limits(), outreach, ROPE)
    assert expected is not None
    assert drawn.scene_fields() == expected.scene_fields
    assert scene.governingCaseLabel == f"Governing case: {series['label']} at {outreach:.1f} m"
    assert scene.canRestoreInputs
    # The apply is not an edit: the chart stays drawn, so the label is kept.
    assert not chart.stale
    QCoreApplication.processEvents()
    assert scene.governingCaseLabel != ""


def test_combined_curve_takes_the_lowest_limit(drawn: Pair) -> None:
    chart, scene = drawn.chart, drawn.scene
    outreach = float(chart.curvePoints[-1][0])
    assert chart.governingCaseAvailable("")
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase("", outreach)
    wait_until(lambda: shown[0] == 1)

    doc = drawn.session.model.document
    assert doc is not None
    expected = governing_case(doc, "MH", "normal", chart._enabled_limits(), outreach, None)
    assert expected is not None
    assert drawn.scene_fields() == expected.scene_fields
    name = chart._limit_display_names()[expected.limit_id]
    assert scene.governingCaseLabel == f"Governing case: {name} at {outreach:.1f} m"


def test_unavailable_when_stale_or_busy(pair: Pair) -> None:
    chart = pair.chart
    assert not chart.governingCaseAvailable(ROPE)  # stale: nothing drawn yet
    pair.draw()
    assert chart.governingCaseAvailable(ROPE)

    chart.setLimitMax(ROPE, "1100")
    assert chart.stale
    assert not chart.governingCaseAvailable(ROPE)
    assert not chart.governingCaseAvailable("")

    chart.draw()  # the sweep runs in the background
    assert chart.busy
    assert not chart.governingCaseAvailable(ROPE)
    assert not chart.governingCaseAvailable("")


def test_unavailable_without_document() -> None:
    chart = ChartViewModel(SessionState())
    assert not chart.governingCaseAvailable("")
    shown = _count(chart.showSceneRequested)
    chart.showGoverningCase("", 30.0)
    assert shown[0] == 0


def test_unlimited_series_unavailable(drawn: Pair) -> None:
    chart = drawn.chart
    assert UNRESPONSIVE in chart._enabled_limits()
    assert not chart.governingCaseAvailable(UNRESPONSIVE)
    assert not chart.governingCaseAvailable("rear_hinge_Fz")  # no max: unlimited
    assert not chart.governingCaseAvailable("no_such_limit")

    shown = _count(chart.showSceneRequested)
    chart.showGoverningCase(UNRESPONSIVE, 30.0)
    QCoreApplication.processEvents()
    assert shown[0] == 0
    assert drawn.scene.governingCaseLabel == ""


def test_no_case_posts_status_and_stays(drawn: Pair, monkeypatch) -> None:
    gate = Gate(result=None, delegate=False)
    gate.release.set()
    monkeypatch.setattr(chart_vm_module, "governing_case", gate)
    chart = drawn.chart
    shown = _count(chart.showSceneRequested)
    before = drawn.scene_fields()

    chart.showGoverningCase(ROPE, 30.0)
    wait_until(lambda: chart._case_request is None)

    assert shown[0] == 0
    assert drawn.scene_fields() == before
    assert "No governing case" in chart.statusText


def test_split_mode_uses_chart_mode(pair: Pair, monkeypatch) -> None:
    chart, scene = pair.chart, pair.scene
    chart.setChartMode("split")
    pair.draw()
    assert pair.session.model.chart_mode_for_hoist("MH") == "split"
    assert scene.hookMode == "normal"  # the Scene's own mode differs from the chart's
    gate = Gate()
    gate.release.set()
    monkeypatch.setattr(chart_vm_module, "governing_case", gate)
    series = pair.series(ROPE)
    outreach = float(series["points"][0][0])
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase(ROPE, outreach)
    wait_until(lambda: shown[0] == 1)

    _doc, hoist_id, mode_name, limits, at, limit_id = gate.calls[0]
    assert (hoist_id, mode_name, at, limit_id) == ("MH", "split", outreach, ROPE)
    assert limits == chart._enabled_limits()
    assert scene.hookMode == "split"


def test_overlapping_request_is_ignored(drawn: Pair, monkeypatch) -> None:
    gate = Gate()
    monkeypatch.setattr(chart_vm_module, "governing_case", gate)
    chart = drawn.chart
    outreach = float(drawn.series(ROPE)["points"][0][0])
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase(ROPE, outreach)
    assert gate.started.wait(10.0)
    assert not chart.governingCaseAvailable(ROPE)  # one request at a time
    chart.showGoverningCase("", outreach)
    gate.release.set()
    wait_until(lambda: shown[0] == 1)
    wait_until(lambda: not chart._threads)

    assert len(gate.calls) == 1
    assert shown[0] == 1


def test_result_dropped_after_edit(drawn: Pair, monkeypatch) -> None:
    gate = Gate()
    monkeypatch.setattr(chart_vm_module, "governing_case", gate)
    chart = drawn.chart
    outreach = float(drawn.series(ROPE)["points"][0][0])
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase(ROPE, outreach)
    assert gate.started.wait(10.0)
    chart.setLimitMax(ROPE, "1100")  # the chart the point came from is gone
    chart._refresh_timer.stop()
    before = drawn.scene_fields()
    gate.release.set()
    wait_until(lambda: chart._case_request is None and not chart._threads)

    assert shown[0] == 0
    assert drawn.scene_fields() == before
    assert drawn.scene.governingCaseLabel == ""


def test_result_dropped_after_hoist_change(drawn: Pair, monkeypatch) -> None:
    gate = Gate()
    monkeypatch.setattr(chart_vm_module, "governing_case", gate)
    chart = drawn.chart
    outreach = float(drawn.series(ROPE)["points"][0][0])
    shown = _count(chart.showSceneRequested)

    chart.showGoverningCase(ROPE, outreach)
    assert gate.started.wait(10.0)
    chart.selectHoist("WH")
    chart._refresh_timer.stop()
    chart._cancel_all()
    gate.release.set()
    wait_until(lambda: chart._case_request is None and not chart._threads)

    assert shown[0] == 0
    assert drawn.scene.governingCaseLabel == ""
