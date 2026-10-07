"""Scene workspace on a heeled/trimmed vessel: heel, trim and slew controls, tilt readouts."""

from pathlib import Path

import pytest

from crane_statics.calculation.vessel_attitude import VesselAttitude, crane_frame_gravity
from crane_statics.core.io import load_document
from crane_statics.data.authored_models import MAX_VESSEL_TILT_DEG
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

        assert vm.heel == 0.0
        assert vm.trim == 0.0
        assert vm.inPlaneTiltText == "0.00°"
        assert vm.outOfPlaneTiltText == "0.00°"

    def test_heel_over_the_side_tilts_the_luffing_plane(self):
        vm = _scene_vm(heel_deg=3.0)

        vm.setSlew(90.0)

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

        assert vm.heel == -2.0
        assert vm.inPlaneTiltText == "2.00° away from boom tip"


class TestSceneHeelAndTrim:
    def test_starts_at_the_models_attitude(self):
        vm = _scene_vm(heel_deg=2.0, trim_deg=-1.0)

        assert vm.heel == 2.0
        assert vm.trim == -1.0
        assert vm.attitudeOverridden is False
        assert vm.modelAttitudeText == "Heel +2.00°, trim -1.00°"
        assert vm.maxTiltDeg == MAX_VESSEL_TILT_DEG

    def test_the_scene_solves_and_draws_at_its_own_heel_and_trim(self):
        vm = _scene_vm()
        vm.setSlew(90.0)

        vm.setHeel(3.0)
        vm.setTrim(1.0)

        attitude = VesselAttitude(3.0, 1.0)
        assert vm.heel == 3.0
        assert vm.trim == 1.0
        assert vm.attitudeOverridden is True
        assert vm._analysis_point.crane_gravity == crane_frame_gravity(attitude, 90.0)
        assert vm._scene_inputs().vessel_attitude() == attitude
        assert vm.inPlaneTiltText == "3.00° toward boom tip"

    def test_a_scene_edit_leaves_the_model_and_document_alone(self):
        vm = _scene_vm()

        vm.setHeel(3.0)

        assert vm._model.dirty is False
        assert vm._model.document.environment.vessel_motion.heel_deg == 0.0
        assert vm.modelAttitudeText == "Level vessel"

    def test_each_edit_notifies(self):
        vm = _scene_vm()
        emitted: list[int] = []
        vm.attitudeChanged.connect(lambda: emitted.append(1))

        vm.setTrim(1.5)

        assert emitted

    def test_a_clamped_angle_is_shown_as_kept(self):
        vm = _scene_vm()

        vm.setHeel(45.0)

        assert vm.heel == MAX_VESSEL_TILT_DEG

    def test_the_override_applies_to_every_hoist(self):
        vm = _scene_vm()
        vm.setHeel(3.0)
        other = next(h for h in vm.hoistIds if h != vm.selectedHoistId)

        vm.selectHoist(other)

        assert vm.heel == 3.0
        assert vm.attitudeOverridden is True

    def test_reset_returns_to_the_models_attitude(self):
        vm = _scene_vm(heel_deg=2.0)
        vm.setHeel(5.0)

        vm.resetAttitude()

        assert vm.heel == 2.0
        assert vm.attitudeOverridden is False
        assert vm._analysis_point.crane_gravity == crane_frame_gravity(
            VesselAttitude(2.0, 0.0), vm.slew
        )

    def test_loading_a_document_drops_the_override(self):
        vm = _scene_vm()
        vm.setHeel(5.0)

        vm._model.set_document(load_document(EXAMPLE))

        assert vm.heel == 0.0
        assert vm.attitudeOverridden is False

    def test_model_edits_no_longer_move_an_overridden_scene(self):
        vm = _scene_vm()
        vm.setHeel(3.0)

        vm._model.document.environment.vessel_motion.heel_deg = -2.0
        vm._model.mark_content_changed()

        assert vm.heel == 3.0
        assert vm.modelAttitudeText == "Heel -2.00°, trim +0.00°"

    def test_auto_load_is_recomputed_at_the_new_heel(self):
        vm = _scene_vm()
        vm.setSlew(90.0)
        state = vm._model.get_active_hoist_state()
        state.scene_state.hook_load_auto = True
        vm.recomputeAutoLoad()
        level_load = state.scene_state.hook_load_kN

        vm.setHeel(5.0)

        assert state.scene_state.hook_load_kN != pytest.approx(level_load)

    def test_the_load_chart_is_not_affected(self):
        from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

        if not EXAMPLE.exists():
            pytest.skip("Example file not found")
        session = SessionState()
        chart_vm = ChartViewModel(session)
        vm = SceneViewModel(session)
        vm.bindCanvas(MockCanvas())
        session.model.set_document(load_document(EXAMPLE))
        chart_vm.drawBlocking()
        level_curve = list(chart_vm.curvePoints)

        vm.setHeel(3.0)

        assert chart_vm.stale is False
        chart_vm.drawBlocking()
        chart_vm.shutdown()
        assert chart_vm.curvePoints == level_curve
        assert chart_vm.conditionText == ""


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
