"""Scene view model behaviour and QML canvas integration."""

import math
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.core.io import load_document
from crane_statics.core.scene_build import SceneDisplay, derive_boom_axes
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


def _hook_guide_anchor(renderer):
    """Scene point the hook guides hang from -- where a tackle drag starts."""
    guide = next(g for g in renderer.scene_frame.guides if g.kind == "hook_height")
    return guide.scene_x, guide.scene_y


def _active_hoist(vm):
    """The authored hoist the scene is drawn for."""
    return next(h for h in vm._model.document.hoists if h.id == vm.selectedHoistId)


def _node_positions(vm, angle=None):
    """World node positions at the angle the scene is currently drawn at."""
    kinematics = vm._kinematics.kinematics()
    return kinematics.compute_all_node_positions(vm.angle if angle is None else angle)


@pytest.mark.parametrize("mode", ["hybrid", "physical", "fixed"])
def test_display_accepts_supported_force_scale_modes(mode):
    assert SceneDisplay(force_scale_mode=mode).force_scale_mode == mode


@pytest.mark.parametrize("mode", ["normalized", "legacy", "", "unknown"])
def test_display_rejects_unknown_force_scale_modes(mode):
    assert SceneDisplay(force_scale_mode=mode).force_scale_mode == "hybrid"


class MockCanvas(QObject):
    """Minimal mock canvas providing renderer for headless testing."""

    boomAngleChanged = pyqtSignal(float)
    tackleLengthChanged = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.renderer = CraneSceneRenderer(self)
        self._scene_vm = None

    def setSceneViewModel(self, scene_vm):
        self._scene_vm = scene_vm


@pytest.fixture
def scene_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = SceneViewModel(session)
    canvas = MockCanvas()
    vm.bindCanvas(canvas)
    session.model.set_document(load_document(EXAMPLE))
    return vm


class TestSceneViewModelState:
    def test_document_load_populates_hoists_and_results(self, scene_vm):
        assert scene_vm.hoistIds
        assert scene_vm.selectedHoistId == scene_vm.hoistIds[0]
        assert scene_vm.ropeRowsModel.count > 0
        assert scene_vm.connectionRowsModel.count > 0

    def test_startup_hook_load_includes_active_hoist_mass(self, scene_vm):
        state = scene_vm._model.get_active_hoist_state()
        hoist = scene_vm._hoist_state.selected_hoist()

        assert state is not None
        assert hoist is not None
        expected = (
            (hoist.static_hook_load_t + hoist.hook_mass_t)
            * hoist.hook_daf
            * scene_vm._hoist_state.gravity_abs()
        )
        assert state.scene_state.hook_load_kN == pytest.approx(expected)

    def test_second_canvas_stays_synchronized(self, scene_vm):
        second_canvas = MockCanvas()
        scene_vm.bindCanvas(second_canvas)

        assert scene_vm._canvas is not second_canvas

        scene_vm.setAngle(scene_vm.angle + 1.0)

        # One frame is built per state change and handed to every bound canvas.
        assert second_canvas.renderer.scene_frame is scene_vm._canvas.renderer.scene_frame
        assert second_canvas.renderer.scene_frame.revision > 0

    def test_canvas_publishes_geometry_frame(self, scene_vm):
        frame = scene_vm._canvas.renderer.scene_frame

        assert frame.revision > 0
        assert frame.fit_rect[2] > 0
        assert frame.fit_rect[3] > 0
        assert frame.nodes
        assert frame.rope_segments
        assert {segment.tooltip.splitlines()[0] for segment in frame.structural_segments} == {
            "Rear leg",
            "Front leg",
        }
        assert frame.markers
        assert all(marker.kind == "center_of_gravity" for marker in frame.markers)
        assert all(
            math.hypot(node.scene_x - marker.scene_x, node.scene_y - marker.scene_y)
            > marker.radius + 4.0
            for node in frame.nodes
            for marker in frame.markers
        )
        assert all(segment.tooltip.startswith("Rope:") for segment in frame.rope_segments)

    def test_qml_scene_frame_matches_the_renderer_frame(self, scene_vm):
        frame = scene_vm.sceneFrame

        assert frame["revision"] == scene_vm._canvas.renderer.scene_frame.revision
        assert frame["nodes"]
        assert frame["ropeSegments"]
        assert frame["fitRect"]["width"] > 0
        assert {axis["label"] for axis in frame["boomAxes"]} == {"X", "Z"}

    def test_qml_scene_frame_revision_changes_with_geometry(self, scene_vm):
        previous = scene_vm.sceneFrame["revision"]

        scene_vm.setAngle(scene_vm.angle + 1.0)

        assert scene_vm.sceneFrame["revision"] > previous

    def test_boom_axes_are_derived_from_heel_and_load_node(self, scene_vm):
        positions = _node_positions(scene_vm)
        heel = positions["boom_heel"]
        hoist = _active_hoist(scene_vm)
        load_pos = positions[hoist.load_node_id]

        x_axis, z_axis = derive_boom_axes(positions, hoist.load_node_id)
        dx = load_pos["x"] - heel["x"]
        dz = load_pos["z"] - heel["z"]
        axis_len = math.hypot(dx, dz)

        assert axis_len > 0.0
        assert x_axis == pytest.approx((dx / axis_len, dz / axis_len), rel=1e-6, abs=1e-6)
        assert z_axis == pytest.approx((-dz / axis_len, dx / axis_len), rel=1e-6, abs=1e-6)

    def test_canvas_publishes_guides_and_waterline(self, scene_vm):
        frame = scene_vm._canvas.renderer.scene_frame

        assert {guide.kind for guide in frame.guides} == {"outreach", "hook_height"}
        assert all(guide.label for guide in frame.guides)
        assert frame.waterline is not None
        assert frame.waterline.label.startswith("MSL")
        assert {target.kind for target in frame.hit_targets} == {
            "boom_angle",
            "outreach",
            "tackle_length",
        }
        assert {axis.label for axis in frame.boom_axes} == {"X", "Z"}
        assert all(
            axis.color and math.hypot(axis.end_x - axis.start_x, axis.end_y - axis.start_y) > 0
            for axis in frame.boom_axes
        )
        assert all(guide.label for guide in frame.guides)

    def test_set_angle_updates_session_and_outreach(self, scene_vm):
        scene_vm.setAngle(50.0)
        state = scene_vm._model.get_active_hoist_state()

        assert state.scene_state.boom_angle_deg == pytest.approx(50.0)
        assert scene_vm.angle == pytest.approx(50.0)
        assert scene_vm.outreach > 0.0

    def test_set_angle_republishes_the_frame_at_the_new_angle(self, scene_vm):
        scene_vm.setAngle(40.0)
        frame = scene_vm._canvas.renderer.scene_frame

        load_node_id = _active_hoist(scene_vm).load_node_id
        world = _node_positions(scene_vm, 40.0)[load_node_id]
        drawn = next(node for node in frame.nodes if node.id == load_node_id)
        kinematic_x, kinematic_y = frame.mapping.to_scene(world["x"], world["z"])

        assert drawn.scene_x == pytest.approx(kinematic_x)
        # The load node is drawn as the hook, hanging below its kinematic position.
        assert drawn.scene_y > kinematic_y

    def test_set_outreach_maps_back_to_angle(self, scene_vm):
        scene_vm.setAngle(45.0)
        target = scene_vm.outreach
        scene_vm.setAngle(20.0)

        scene_vm.setOutreach(target)

        assert scene_vm.outreach == pytest.approx(target, abs=0.5)

    def test_scene_drag_updates_boom_angle(self, scene_vm):
        renderer = scene_vm._canvas.renderer
        heel_x, heel_z = renderer.heel_world
        target_x, target_y = renderer.scene_frame.mapping.to_scene(heel_x + 20.0, heel_z + 20.0)

        scene_vm.sceneDragStart("boom_angle", target_x, target_y)
        scene_vm.sceneDragUpdate(target_x, target_y)
        scene_vm.sceneDragEnd()

        assert scene_vm.angle == pytest.approx(45.0)

    def test_scene_drag_updates_tackle_length(self, scene_vm):
        renderer = scene_vm._canvas.renderer
        start_x, start_y = _hook_guide_anchor(renderer)

        scene_vm.sceneDragStart("tackle_length", start_x, start_y)
        scene_vm.sceneDragUpdate(start_x, start_y + renderer.map_scale * 2.0)
        scene_vm.sceneDragEnd()

        assert scene_vm.tackle == pytest.approx(scene_vm.tackleMin + 2.0)

    def test_scene_drag_alt_snaps_tackle_length_to_half_metre(self, scene_vm):
        renderer = scene_vm._canvas.renderer
        start_x, start_y = _hook_guide_anchor(renderer)

        scene_vm.sceneDragStart("tackle_length", start_x, start_y)
        scene_vm.sceneDragUpdate(start_x, start_y + renderer.map_scale * 2.26, True)
        scene_vm.sceneDragEnd()

        assert scene_vm.tackle == pytest.approx(scene_vm.tackleMin + 2.5)

    def test_view_model_resolves_boom_drag_target_from_frame(self, scene_vm):
        axis = scene_vm.sceneFrame["hitTargets"][0]

        assert scene_vm.sceneDragTargetAt(axis["start_x"], axis["start_y"]) == "boom_angle"

    def test_keyboard_outreach_nudge_updates_shared_geometry(self, scene_vm):
        scene_vm.setAngle(45.0)
        before = scene_vm.outreach

        scene_vm.nudgeOutreach(1.0)

        assert scene_vm.outreach != pytest.approx(before)

    def test_unreachable_outreach_reports_status(self, scene_vm):
        messages: list[str] = []
        scene_vm.statusMessage.connect(messages.append)

        scene_vm.setOutreach(9999.0)

        assert messages and "outside the reachable range" in messages[-1]

    def test_angle_is_clamped_in_auto_load_mode(self, scene_vm):
        scene_vm.setHookLoadAuto(True)
        scene_vm.setAngle(400.0)

        assert scene_vm.angle <= scene_vm.angleMax + 1e-9

    def test_hook_load_converts_to_kn(self, scene_vm):
        scene_vm.setHookLoadTonnes(10.0)
        state = scene_vm._model.get_active_hoist_state()

        expected = scene_vm._hoist_state.payload_t_to_hook_force_kN(10.0)
        assert state.scene_state.hook_load_kN == pytest.approx(expected)
        assert scene_vm.hookLoadTonnes == pytest.approx(10.0)

    def test_environment_setters_write_through_to_session(self, scene_vm):
        scene_vm.setWindSpeed(12.5)
        scene_vm.setWindDirection("-Y")
        scene_vm.setAccelX(0.25)
        scene_vm.setPitchAccel(0.05)
        sc = scene_vm._model.get_active_hoist_state().scene_state

        assert sc.wind_speed_m_s == pytest.approx(12.5)
        assert sc.wind_direction == "-Y"
        assert sc.accel_x_m_s2 == pytest.approx(0.25)
        assert sc.pitch_accel_rad_s2 == pytest.approx(0.05)

    def test_unknown_wind_direction_is_ignored(self, scene_vm):
        scene_vm.setWindDirection("sideways")
        assert scene_vm.windDirection in {"+X", "-X", "+Y", "-Y"}

    def test_signed_wind_speed_controls_direction_sign(self, scene_vm):
        scene_vm.setWindAxis("Y")
        scene_vm.setWindSpeed(-12.5)

        state = scene_vm._model.get_active_hoist_state().scene_state
        assert scene_vm.windSpeed == pytest.approx(-12.5)
        assert state.wind_speed_m_s == pytest.approx(12.5)
        assert state.wind_direction == "-Y"

    def test_wind_axis_preserves_signed_velocity(self, scene_vm):
        scene_vm.setWindSpeed(-12.5)
        scene_vm.setWindAxis("Y")

        assert scene_vm.windSpeed == pytest.approx(-12.5)
        assert scene_vm.windAxis == "Y"
        assert scene_vm.windDirection == "-Y"

    def test_display_options_reach_the_published_frame(self, scene_vm):
        assert scene_vm._canvas.renderer.scene_frame.force_arrows == ()

        scene_vm.setDisplayOption("show_gravity_forces", True)

        assert scene_vm.displayOptions["show_gravity_forces"] is True
        assert scene_vm._canvas.renderer.scene_frame.force_arrows

    def test_force_arrows_are_published_when_an_overlay_is_visible(self, scene_vm):
        scene_vm.setHookLoadTonnes(10.0)
        scene_vm.setDisplayOption("show_hook_forces", True)
        arrows = scene_vm._canvas.renderer.scene_frame.force_arrows

        assert arrows
        assert all(arrow.kind == "force" for arrow in arrows)
        assert all(arrow.tooltip for arrow in arrows)

    def test_force_labels_are_published_when_enabled(self, scene_vm):
        scene_vm.setHookLoadTonnes(10.0)
        scene_vm.setDisplayOption("show_hook_forces", True)
        scene_vm.setDisplayOption("show_labels", True)
        labels = scene_vm._canvas.renderer.scene_frame.labels

        assert labels
        assert any(label.kind == "force" and label.text.startswith("Hook") for label in labels)

    def test_freebody_toggle_is_single_select_with_none(self, scene_vm):
        scene_vm.toggleFreebody("boom")
        assert scene_vm.displayOptions["selected_freebody"] == "boom"

        scene_vm.toggleFreebody("boom")
        assert scene_vm.displayOptions["selected_freebody"] == "none"

    def test_winch_spools_read_out_every_winch_bearing_hoist(self, scene_vm):
        frame = scene_vm._canvas.renderer.scene_frame

        assert [spool.hoist_id for spool in frame.winch_spools] == ["MH", "WH", "SH", "BH"]
        assert all(
            re.fullmatch(r"\d+\.\d m \(\d+\.\d t\)", spool.value_text)
            for spool in frame.winch_spools
        )

    def test_winch_spool_rows_replace_the_winch_cg_markers(self, scene_vm):
        """The spooled rope mass is a readout now, not a centre-of-gravity symbol.

        ``calculation.rope_mass`` never fed the load model, so a CG symbol
        overstated what the winch mass was; ``core.drawn_loads`` still does not
        read it.
        """
        frame = scene_vm._canvas.renderer.scene_frame

        assert frame.winch_spools
        assert not any("Winch:" in marker.tooltip for marker in frame.markers)

    def test_winch_spools_reach_qml_as_camel_case_rows(self, scene_vm):
        rows = scene_vm.sceneFrame["winchSpools"]

        assert [row["hoist_id"] for row in rows] == ["MH", "WH", "SH", "BH"]
        assert all(row["value_text"] for row in rows)

    def test_winch_spools_respect_the_free_body_cut(self, scene_vm):
        """Winch ownership is authored per body: sh_winch on boom, the rest on platform.

        There is no platform free body, so a leg cut owns no winch at all and the
        readout is empty -- the same way the winch CG markers used to vanish.
        """
        scene_vm.toggleFreebody("boom")
        boom_ids = [spool.hoist_id for spool in scene_vm._canvas.renderer.scene_frame.winch_spools]

        scene_vm.toggleFreebody("boom")
        scene_vm.toggleFreebody("front_leg")
        leg_spools = scene_vm._canvas.renderer.scene_frame.winch_spools

        assert boom_ids == ["SH"]
        assert leg_spools == ()

    def test_winch_spool_readout_is_on_by_default_and_toggleable(self, scene_vm):
        assert scene_vm.displayOptions["show_winch_spools"] is True

        scene_vm.setDisplayOption("show_winch_spools", False)

        assert scene_vm._canvas.renderer.scene_frame.winch_spools == ()

    def test_freebody_frame_hides_guides_and_waterline(self, scene_vm):
        scene_vm.toggleFreebody("boom")
        frame = scene_vm._canvas.renderer.scene_frame

        assert frame.guides == ()
        assert frame.waterline is None
        assert frame.hit_targets == ()


class TestContractualPoints:
    def test_labels_are_sorted_by_outreach(self, scene_vm):
        labels = scene_vm.contractualLabels
        assert labels

        outreaches = [float(label.split("@")[1].strip().split(" ")[0]) for label in labels]
        assert outreaches == sorted(outreaches)

    def test_selecting_a_point_moves_geometry_and_load(self, scene_vm):
        scene_vm.selectContractual(0)

        assert scene_vm.selectedContractualIdx == 0
        assert scene_vm.hookLoadTonnes > 0.0

    def test_manual_angle_change_clears_selection(self, scene_vm):
        scene_vm.selectContractual(0)
        scene_vm.setAngle(scene_vm.angle + 5.0)

        assert scene_vm.selectedContractualIdx == -1


class TestHookMode:
    def test_split_mode_rejected_for_non_splitable_hoist(self, scene_vm):
        non_splitable = next(
            (hid for hid in scene_vm.hoistIds if not _is_splitable(scene_vm, hid)), None
        )
        if non_splitable is None:
            pytest.skip("Example has no non-splitable payload hoist")
        scene_vm.selectHoist(non_splitable)
        messages: list[str] = []
        scene_vm.statusMessage.connect(messages.append)

        scene_vm.setHookMode("split")

        assert scene_vm.hookMode == "normal"
        assert messages and "not configured as splitable" in messages[-1]

    def test_split_mode_switches_contractual_dataset(self, scene_vm):
        splitable = next((hid for hid in scene_vm.hoistIds if _is_splitable(scene_vm, hid)), None)
        if splitable is None:
            pytest.skip("Example has no splitable hoist")
        scene_vm.selectHoist(splitable)
        normal_labels = list(scene_vm.contractualLabels)

        scene_vm.setHookMode("split")

        assert scene_vm.hookMode == "split"
        assert scene_vm.contractualLabels != normal_labels
        assert scene_vm.selectedContractualIdx == -1


class TestReportsAndOverview:
    def test_equilibrium_report_populates_rows(self, scene_vm):
        titles: list[tuple[str, str]] = []
        scene_vm.reportReady.connect(lambda title, verdict: titles.append((title, verdict)))

        scene_vm.requestEquilibriumCheck()

        assert titles and titles[-1][0] == "Equilibrium Check"
        assert scene_vm.reportModel.count > 0

    def test_load_summary_rows_include_categories(self, scene_vm):
        scene_vm.requestLoadSummary()
        kinds = {scene_vm.reportModel.row_at(i)["kind"] for i in range(scene_vm.reportModel.count)}

        assert "section" in kinds
        assert "category" in kinds

    def test_load_overview_emitted_for_clickable_row(self, scene_vm):
        scene_vm.setHookLoadTonnes(50.0)
        overviews: list[dict] = []
        scene_vm.loadOverviewReady.connect(overviews.append)

        clickable = next(
            (
                i
                for i in range(scene_vm.ropeRowsModel.count)
                if scene_vm.ropeRowsModel.row_at(i)["clickable"]
            ),
            None,
        )
        if clickable is None:
            pytest.skip("No clickable rope row in example")

        scene_vm.openLoadOverview("rope", clickable)

        assert overviews
        assert len(overviews[-1]["terms"]) == 6


def _is_splitable(vm: SceneViewModel, hoist_id: str) -> bool:
    doc = vm._model.document
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    return bool(hoist is not None and getattr(hoist, "splitable_block", False))
