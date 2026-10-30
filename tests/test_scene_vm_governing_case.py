"""Scene view model: apply a chart point's governing case, label it, restore the inputs."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Callable

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.core.governing_case import GoverningCase
from crane_statics.core.io import load_document
from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
LABEL = "Governing case: MH__rope at 30.0 m"
# The ± vessel-motion limits the test document gets (Model field -> value).
VESSEL_LIMITS = {
    "accel_x_m_s2": 0.5,
    "accel_y_m_s2": 0.3,
    "accel_z_m_s2": 0.8,
    "pitch_angular_accel_rad_s2": 0.05,
    "roll_angular_accel_rad_s2": 0.04,
    "roll_deg": 2.0,
    "pitch_deg": 1.5,
}


class MockCanvas(QObject):
    """Minimal canvas providing a renderer for headless testing."""

    boomAngleChanged = pyqtSignal(float)
    tackleLengthChanged = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.renderer = CraneSceneRenderer(self)

    def setSceneViewModel(self, scene_vm: Any) -> None:
        pass


def _document():
    doc = load_document(EXAMPLE)
    for name, value in VESSEL_LIMITS.items():
        setattr(doc.environment.vessel_motion, name, value)
    return doc


@pytest.fixture
def session() -> SessionState:
    return SessionState()


@pytest.fixture
def vm(session: SessionState) -> SceneViewModel:
    scene_vm = SceneViewModel(session)
    scene_vm.bindCanvas(MockCanvas())
    session.model.set_document(_document())
    return scene_vm


def _state(vm: SceneViewModel) -> dict[str, Any]:
    state = vm._model.get_active_hoist_state()
    assert state is not None
    return dataclasses.asdict(state.scene_state)


def _case(vm: SceneViewModel, mode_name: str = "normal", **overrides: Any) -> GoverningCase:
    """A case with every Scene field set away from its current value."""
    fields: dict[str, Any] = {
        "boom_angle_deg": 55.0,
        "hook_load_kN": 4321.0,
        "hook_load_auto": False,
        # Above the Scene's tackle range: the load curve's payout must land unclamped.
        "tackle_length_m": vm.tackleMax + 1.0,
        "offlead_deg": -2.5,
        "sidelead_deg": 3.5,
        "wind_speed_m_s": 17.0,
        "wind_direction": "-Y",
        "accel_x_m_s2": -0.5,
        "accel_y_m_s2": 0.3,
        "accel_z_m_s2": -0.8,
        "pitch_accel_rad_s2": 0.05,
        "roll_accel_rad_s2": -0.04,
        "vessel_roll_deg": -2.0,
        "vessel_pitch_deg": 1.5,
        "crane_slewing_angle_deg": 135.0,
    }
    fields.update(overrides)
    assert set(fields) == set(_state(vm))
    return GoverningCase(
        limit_id="MH__rope", mode_name=mode_name, scene_fields=fields, outreach_m=30.0
    )


def _count(signal: Any) -> list[int]:
    hits = [0]
    signal.connect(lambda *_: hits.__setitem__(0, hits[0] + 1))
    return hits


def test_apply_sets_fields_and_label(vm: SceneViewModel) -> None:
    case = _case(vm)
    changed = _count(vm.governingCaseChanged)
    vm.apply_governing_case(case, LABEL)

    assert _state(vm) == case.scene_fields
    assert vm.tackle == case.scene_fields["tackle_length_m"]  # the payout is kept, not clamped
    assert vm.governingCaseLabel == LABEL
    assert vm.canRestoreInputs
    assert changed[0] >= 1
    # Outreach and the payload shown follow the case; results are re-solved for it.
    kin = vm._kinematics.kinematics()
    assert kin is not None
    assert vm.outreach == pytest.approx(kin.compute_outreach(55.0, "MH"))
    assert vm._hoist_state.payload_t_to_hook_force_kN(vm.hookLoadTonnes) == pytest.approx(4321.0)
    assert vm._analysis_point is not None
    assert vm.resultRowsModel.count > 0
    # A programmatic apply is not a user edit: the document stays clean.
    assert not vm._model.dirty


def test_tackle_range_covers_a_case_payout_above_the_hook_travel(vm: SceneViewModel) -> None:
    """The tackle field and the canvas would otherwise clamp the case's payout back."""
    configured_max = vm.tackleMax
    case = _case(vm)
    bounds = _count(vm.tackleBoundsChanged)
    vm.apply_governing_case(case, LABEL)

    assert vm.tackleMax == case.scene_fields["tackle_length_m"] > configured_max
    assert bounds[0] >= 1
    assert vm._scene_inputs().tackle_length_m == case.scene_fields["tackle_length_m"]

    vm.restoreInputs()
    assert vm.tackleMax == configured_max


def test_tackle_range_keeps_the_case_payout_after_the_tackle_is_lowered(
    vm: SceneViewModel,
) -> None:
    """Lowering the tackle must not ratchet the range down until Restore."""
    configured_max = vm.tackleMax
    case = _case(vm)
    case_tackle = case.scene_fields["tackle_length_m"]
    vm.apply_governing_case(case, LABEL)

    vm.setTackle(configured_max / 2)
    assert vm.tackleMax == case_tackle

    bounds = _count(vm.tackleBoundsChanged)
    vm.restoreInputs()
    assert vm.tackleMax == configured_max
    assert bounds[0] >= 1


@pytest.mark.parametrize("signal", ["boomAngleChanged", "tackleLengthChanged"])
def test_canvas_drag_clears_label_keeps_restore(vm: SceneViewModel, signal: str) -> None:
    vm.apply_governing_case(_case(vm), LABEL)
    getattr(vm._canvas, signal).emit(10.0)

    assert vm.governingCaseLabel == ""
    assert vm.canRestoreInputs


def test_apply_runs_without_vessel_clamp_side_effects(vm: SceneViewModel) -> None:
    vm.setHookLoadAuto(True)  # auto would recompute the hook load if a setter ran
    vm.setAngle(vm.angleMin)
    case = _case(vm, boom_angle_deg=1.0)
    vm.apply_governing_case(case, LABEL)

    state = _state(vm)
    for name in (
        "accel_x_m_s2",
        "accel_y_m_s2",
        "accel_z_m_s2",
        "pitch_accel_rad_s2",
        "roll_accel_rad_s2",
        "vessel_roll_deg",
        "vessel_pitch_deg",
    ):
        assert state[name] == case.scene_fields[name], name
    assert state["hook_load_kN"] == 4321.0
    assert state["hook_load_auto"] is False
    assert state["boom_angle_deg"] == 1.0


SETTERS: dict[str, Callable[[SceneViewModel], None]] = {
    "angle": lambda vm: vm.setAngle(40.0),
    "outreach": lambda vm: vm.setOutreach(vm.outreach + 1.0),
    "tackle": lambda vm: vm.setTackle(20.0),
    "hook_load": lambda vm: vm.setHookLoadTonnes(12.0),
    "hook_load_auto": lambda vm: vm.setHookLoadAuto(True),
    "offlead": lambda vm: vm.setOfflead(1.0),
    "sidelead": lambda vm: vm.setSidelead(1.0),
    "wind_speed": lambda vm: vm.setWindSpeed(5.0),
    "wind_direction": lambda vm: vm.setWindDirection("+X"),
    "accel_x": lambda vm: vm.setAccelX(0.1),
    "vessel_roll": lambda vm: vm.setVesselRoll(0.5),
    "slew": lambda vm: vm.setCraneSlewingAngle(10.0),
    "hook_mode": lambda vm: vm.setHookMode("split"),
    "contractual": lambda vm: vm.selectContractual(0),
}


@pytest.mark.parametrize("edit", SETTERS.values(), ids=SETTERS.keys())
def test_user_setter_clears_label_keeps_restore(
    vm: SceneViewModel, edit: Callable[[SceneViewModel], None]
) -> None:
    vm.apply_governing_case(_case(vm), LABEL)
    changed = _count(vm.governingCaseChanged)
    edit(vm)

    assert vm.governingCaseLabel == ""
    assert vm.canRestoreInputs
    assert changed[0] >= 1


def test_second_apply_keeps_original_snapshot(vm: SceneViewModel) -> None:
    original = _state(vm)
    vm.apply_governing_case(_case(vm), LABEL)
    second = _case(vm, boom_angle_deg=35.0, hook_load_kN=999.0)
    vm.apply_governing_case(second, "Governing case: rear_hinge at 40.0 m")
    assert _state(vm) == second.scene_fields
    assert vm.governingCaseLabel == "Governing case: rear_hinge at 40.0 m"

    vm.restoreInputs()
    assert _state(vm) == original


def test_restore_restores_fields_and_auto_flag_and_hides_button(vm: SceneViewModel) -> None:
    vm.setHookLoadAuto(True)
    vm._model.set_dirty(False)
    original = _state(vm)
    original_t = vm.hookLoadTonnes
    original_outreach = vm.outreach
    assert original["hook_load_auto"] is True

    vm.apply_governing_case(_case(vm), LABEL)
    changed = _count(vm.governingCaseChanged)
    vm.restoreInputs()

    assert _state(vm) == original
    assert vm.hookLoadAuto
    assert vm.hookLoadTonnes == original_t
    assert vm.outreach == pytest.approx(original_outreach)
    assert not vm.canRestoreInputs
    assert vm.governingCaseLabel == ""
    assert changed[0] >= 1
    assert vm._model.dirty  # restoring is an edit of the inputs, as a setter is


def test_apply_split_case_sets_split_mode_and_restore_reverts(vm: SceneViewModel) -> None:
    model = vm._model
    model.set_chart_mode("MH", "split")  # the chart the case came from
    before = model.split_flags()
    assert vm.hookMode == "normal"

    vm.apply_governing_case(_case(vm, mode_name="split"), LABEL)
    assert vm.hookMode == "split"
    assert model.hoist_states["MH"].chart_mode == "split"
    assert vm.governingCaseLabel == LABEL

    vm.restoreInputs()
    after = model.split_flags()
    assert after == before
    assert vm.hookMode == "normal"


def test_restore_keeps_a_chart_mode_chosen_after_the_apply(vm: SceneViewModel) -> None:
    model = vm._model
    flags_before_apply = model.split_flags()
    assert model.hoist_states["MH"].chart_mode == "normal"
    vm.apply_governing_case(_case(vm, mode_name="split"), LABEL)
    model.set_chart_mode("MH", "split")  # the Load Chart radio, between apply and Restore

    vm.restoreInputs()
    assert model.hoist_states["MH"].chart_mode == "split"
    assert model.split_flags() == flags_before_apply
    assert vm.hookMode == "normal"


def test_apply_normal_case_leaves_split_and_restore_reverts(vm: SceneViewModel) -> None:
    vm.setHookMode("split")
    model = vm._model
    before = model.split_flags()

    vm.apply_governing_case(_case(vm, mode_name="normal"), LABEL)
    assert vm.hookMode == "normal"

    vm.restoreInputs()
    after = model.split_flags()
    assert after == before
    assert vm.hookMode == "split"


def test_hoist_change_clears_snapshot(vm: SceneViewModel) -> None:
    vm.apply_governing_case(_case(vm), LABEL)
    vm.selectHoist("WH")

    assert not vm.canRestoreInputs
    assert vm.governingCaseLabel == ""
    wh_state = _state(vm)
    vm.restoreInputs()  # nothing to restore
    assert _state(vm) == wh_state


def test_document_change_clears_snapshot(vm: SceneViewModel, session: SessionState) -> None:
    vm.apply_governing_case(_case(vm), LABEL)
    session.model.set_document(_document())

    assert not vm.canRestoreInputs
    assert vm.governingCaseLabel == ""
