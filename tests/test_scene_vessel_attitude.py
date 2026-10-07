"""Scene workspace on a heeled/trimmed vessel: slew control and tilt readouts."""

from pathlib import Path

import pytest

from crane_statics.core.io import load_document
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
from tests.test_scene_view_model import MockCanvas

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


def _scene_vm(heel_deg: float = 0.0, trim_deg: float = 0.0) -> SceneViewModel:
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    doc = load_document(EXAMPLE)
    doc.environment.vessel_motion.heel_deg = heel_deg
    doc.environment.vessel_motion.trim_deg = trim_deg
    session = SessionState()
    vm = SceneViewModel(session)
    vm.bindCanvas(MockCanvas())
    session.model.set_document(doc)
    return vm


class TestSlewControl:
    @pytest.mark.parametrize("typed, shown", [(90.0, 90.0), (-90.0, 270.0), (370.0, 10.0)])
    def test_slew_wraps_into_one_turn(self, typed, shown):
        vm = _scene_vm(heel_deg=3.0)

        vm.setSlew(typed)

        assert vm.slew == pytest.approx(shown)
        assert vm._model.get_active_hoist_state().scene_state.slew_deg == pytest.approx(shown)

    def test_the_scene_solves_at_the_chosen_slew(self):
        vm = _scene_vm(heel_deg=3.0)

        vm.setSlew(90.0)

        assert vm._analysis_point.slew_deg == pytest.approx(90.0)
        assert vm._scene_inputs().conditions.slew_deg == pytest.approx(90.0)


class TestAttitudeReadouts:
    def test_a_level_vessel_reads_level(self):
        vm = _scene_vm()

        assert vm.vesselLevel is True
        assert vm.vesselAttitudeText == "Level vessel"
        assert vm.inPlaneTiltText == "0.00°"
        assert vm.outOfPlaneTiltText == "0.00°"

    def test_heel_over_the_side_tilts_the_luffing_plane(self):
        vm = _scene_vm(heel_deg=3.0)

        vm.setSlew(90.0)

        assert vm.vesselLevel is False
        assert vm.vesselAttitudeText == "Heel +3.00°, trim +0.00°"
        assert vm.inPlaneTiltText == "3.00° toward boom tip"
        assert vm.outOfPlaneTiltText == "0.00°"

    def test_heel_over_the_bow_tilts_across_the_luffing_plane(self):
        vm = _scene_vm(heel_deg=3.0)

        vm.setSlew(0.0)

        assert vm.inPlaneTiltText == "0.00°"
        assert vm.outOfPlaneTiltText == "3.00° to boom's right"

    def test_readouts_follow_a_heel_edit(self):
        vm = _scene_vm()
        vm.setSlew(90.0)

        vm._model.document.environment.vessel_motion.heel_deg = -2.0
        vm._model.mark_content_changed()

        assert vm.vesselAttitudeText == "Heel -2.00°, trim +0.00°"
        assert vm.inPlaneTiltText == "2.00° away from boom tip"


class TestSlewFollowsTheActiveHoist:
    def test_switching_hoist_notifies_its_own_slew(self):
        vm = _scene_vm(heel_deg=3.0)
        vm.setSlew(90.0)
        other = next(h for h in vm.hoistIds if h != vm.selectedHoistId)
        emitted: list[int] = []
        vm.attitudeChanged.connect(lambda: emitted.append(1))

        vm.selectHoist(other)

        assert emitted
        assert vm.slew == 0.0

    def test_loading_a_level_document_notifies_the_reset_slew(self):
        vm = _scene_vm()
        vm.setSlew(45.0)
        emitted: list[int] = []
        vm.attitudeChanged.connect(lambda: emitted.append(1))

        vm._model.set_document(load_document(EXAMPLE))

        assert emitted
        assert vm.slew == 0.0


def test_scene_view_model_reads_gravity_through_core():
    source = (
        Path(__file__).parent.parent
        / "src"
        / "crane_statics"
        / "qml_app"
        / "viewmodels"
        / "scene_vm.py"
    ).read_text(encoding="utf-8")

    assert "crane_statics.calculation" not in source
