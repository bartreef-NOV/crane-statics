"""Undo/redo across the real view models: Scene, Model and shell."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.core.io import load_document
from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
from tests.authored_helpers import example_path

EXAMPLE = example_path("crane_input_22689.yaml")


class _Canvas(QObject):
    boomAngleChanged = pyqtSignal(float)
    tackleLengthChanged = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.renderer = CraneSceneRenderer(self)

    def setSceneViewModel(self, scene_vm):
        pass


@pytest.fixture
def vms(tmp_path):
    session = SessionState()
    app = AppViewModel(session)
    model = ModelViewModel(session)
    scene = SceneViewModel(session)
    scene.bindCanvas(_Canvas())
    session.model.set_document(load_document(EXAMPLE), EXAMPLE)
    session.model.history._window = 0.0  # no time-based merging between test steps
    return app, model, scene


def test_scene_edit_undo_redo_restores_inputs_and_hook_load(vms):
    app, _model, scene = vms
    wind = scene.windSpeed
    load_t = scene.hookLoadTonnes
    scene.setWindSpeed(wind + 2.0)
    scene.setHookLoadTonnes(load_t + 10.0)
    assert app.canUndo and app.dirty

    app.undo()
    assert scene.hookLoadTonnes == pytest.approx(load_t)
    assert scene.windSpeed == pytest.approx(wind + 2.0)
    app.undo()
    assert scene.windSpeed == pytest.approx(wind)
    assert not app.canUndo and not app.dirty

    app.redo()
    app.redo()
    assert scene.windSpeed == pytest.approx(wind + 2.0)
    assert scene.hookLoadTonnes == pytest.approx(load_t + 10.0)
    assert not app.canRedo and app.dirty


def test_slider_drag_is_one_undo_step(vms):
    app, _model, scene = vms
    scene._model.history._window = 60.0
    start = scene.angle
    lo, hi = scene._kinematics.spinbox_angle_bounds(scene.selectedHoistId)
    step = (hi - lo) / 50.0
    for i in range(1, 6):
        scene.setAngle(min(hi, start + i * step))

    app.undo()
    assert scene.angle == pytest.approx(start)
    assert not app.canUndo


def test_model_edit_undo_redo(vms):
    app, model, scene = vms
    doc = model._model.document
    before = doc.environment.air_density_kg_m3
    model.setEnvironmentValue("air_density_kg_m3", before + 0.3)

    app.undo()
    assert model._model.document.environment.air_density_kg_m3 == before
    app.redo()
    assert model._model.document.environment.air_density_kg_m3 == before + 0.3


def test_undo_signals_history_changes(vms):
    app, model, _scene = vms
    seen = []
    app.historyChanged.connect(lambda: seen.append(app.canUndo))
    model.setEnvironmentValue(
        "air_density_kg_m3", model._model.document.environment.air_density_kg_m3 + 0.1
    )
    app.undo()
    assert seen[-2:] == [True, False]


def test_save_marks_clean_state(vms, tmp_path):
    app, model, _scene = vms
    from PyQt6.QtCore import QUrl

    value = model._model.document.environment.air_density_kg_m3
    model.setEnvironmentValue("air_density_kg_m3", value + 0.1)
    assert app.saveAs(QUrl.fromLocalFile(str(tmp_path / "x.yaml")))
    assert not app.dirty
    model.setEnvironmentValue("air_density_kg_m3", value + 0.2)
    assert app.dirty
    app.undo()
    assert not app.dirty
    app.undo()
    assert app.dirty


def test_opening_a_document_clears_history(vms):
    app, model, _scene = vms
    model.setEnvironmentValue(
        "air_density_kg_m3", model._model.document.environment.air_density_kg_m3 + 0.1
    )
    app.openPath(str(EXAMPLE))
    assert not app.canUndo and not app.canRedo


def test_condition_edit_is_undoable():
    from tests.rules_docs import gale, rules_doc

    session = SessionState()
    model = ModelViewModel(session)
    session.model.set_document(rules_doc("DNV", gale("a", wind=25.0), gale("b")))
    session.model.history._window = 0.0
    model.setConditionValue("wind_speed_m_s", 31.0)
    assert session.model.document.conditions["a"].wind_speed_m_s == 31.0

    assert session.model.undo()
    assert session.model.document.conditions["a"].wind_speed_m_s == 25.0
    assert model.condition["wind_speed_m_s"] == 25.0
    assert model.selectedCondition == "a"
