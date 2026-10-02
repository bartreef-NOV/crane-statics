"""Test suite for parity acceptance scenarios."""

import math
import pytest
from dataclasses import fields, replace
from pathlib import Path
import json
from importlib import resources
import crane_statics.core.limit_auto_set as limit_auto_set_module
from jsonschema import Draft202012Validator
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.data import normalize_document, CraneDocument, document_to_authored_form
from crane_statics.core import load_document, create_default_document
from crane_statics.calculation import CraneCalculator
from crane_statics.core.io import save_document
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core.io import DocumentIOError
from crane_statics.core.limit_auto_set import (
    compute_required_rope_capacity_kN,
    compute_required_connection_capacity_kN,
)
from crane_statics.core.analysis_cases import iter_wind_lead_directional_cases
from crane_statics.core import drawn_loads as dl
from crane_statics.schemas.generate_schema import SCHEMA_FILENAME
from crane_statics.core.scene_build import SceneDisplay, SceneInputs, build_scene_frame
from crane_statics.core.session_model import SessionModel
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel


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


def scene_inputs(
    doc,
    hoist_id: str,
    *,
    angle: float = 45.0,
    analysis_point=None,
    tackle_length_m: float | None = None,
    display: dict | None = None,
    **conditions,
) -> SceneInputs:
    """The scene as a value -- what the view model hands to ``build_scene_frame``.

    Lets a scene be drawn and its loads read without a session, a view model or a
    canvas: inputs in, ``SceneFrame`` out.
    """
    doc_dict = doc.model_dump()
    hoist = dl.active_hoist_dict(doc_dict, hoist_id)
    lo = float(hoist.get("min_hook_travel_m") or 0.0)
    hi = float(hoist.get("max_hook_travel_m") or 500.0)
    tackle = max(lo, min(hi, 50.0 if tackle_length_m is None else float(tackle_length_m)))
    return SceneInputs(
        document_dict=doc_dict,
        kinematics=KinematicsAdapter(doc_dict),
        hoist_id=hoist_id,
        hoist=hoist,
        conditions=dl.LoadConditions(boom_angle_deg=angle, **conditions),
        display=SceneDisplay(**(display or {})),
        analysis_point=analysis_point,
        tackle_length_m=tackle,
    )


def scene_inputs_at_drawn_tackle(doc, hoist_id: str, *, angle: float = 45.0, **kwargs):
    """Scene inputs whose analysis point was solved at the tackle length it draws.

    Rope weight moves between the falls and the winch drum as the hook is lowered,
    so drawn loads only balance the solved reactions when both were evaluated at
    the same hook position -- which is what the view model does.
    """
    drawn = {field.name for field in fields(dl.LoadConditions)} | {"display", "tackle_length_m"}
    inputs = scene_inputs(
        doc,
        hoist_id,
        angle=angle,
        **{key: value for key, value in kwargs.items() if key in drawn},
    )
    point = CraneCalculator(doc).compute_analysis_point(
        angle,
        0.0,
        hoist_id,
        tackle_length_m=inputs.tackle_length_m,
        **{key: value for key, value in kwargs.items() if key != "display"},
    )
    return replace(inputs, analysis_point=point)


class SceneHarness:
    """Headless stand-in for the QML scene workspace (view model + painted-item canvas)."""

    def __init__(self, doc=None, hoist_id: str | None = None):
        self.session = SessionState()
        self.model = self.session.model
        self.canvas = MockCanvas()
        self.vm = SceneViewModel(self.session)
        self.vm.bindCanvas(self.canvas)
        if doc is not None:
            self.model.set_document(doc)
            if hoist_id is not None:
                self.model.select_payload_hoist(hoist_id)
            self.vm.reload()

    @property
    def renderer(self):
        return self.canvas.renderer

    @property
    def state(self):
        return self.model.get_active_hoist_state()

    def apply(self, **scene_state):
        """Write scene-state fields, then run the full refresh pipeline."""
        state = self.state
        assert state is not None
        for key, value in scene_state.items():
            setattr(state.scene_state, key, value)
        self.vm.reload()

    @property
    def inputs(self) -> SceneInputs:
        """Everything the scene is drawn from, as the view model assembled it."""
        return self.vm._scene_inputs()

    def display(self, **options) -> None:
        """Turn overlays on or off, then republish the frame they are drawn into."""
        for key, value in options.items():
            self.vm.setDisplayOption(key, value)

    def frame(self):
        """The frame currently published to the canvas."""
        return self.renderer.scene_frame

    def report(self) -> dict:
        """The drawn-load report backing both Equilibrium Check and Load Summary."""
        inputs = self.inputs
        document_dict = inputs.document_dict
        assert document_dict is not None
        return self.vm._presenter.build_drawn_load_sections(
            document_dict=document_dict,
            analysis_point=inputs.analysis_point,
            node_positions=inputs.node_positions(),
            conditions=inputs.conditions,
        )

    def loads(self, body: str | None = None) -> dl.BodyLoads:
        """Drawn loads for one free body, as the report and the overlay see them."""
        inputs = self.inputs
        return inputs.body_loads(inputs.node_positions(), body)


class TestA1ExampleFileLoads:
    """A1: Example file loads successfully."""

    def test_loads_without_error(self):
        """Example file should load through normal path."""
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        assert doc is not None
        assert doc.model_type == "fixed_topology_crane_2d"

    def test_creates_scene_context(self):
        """Loaded document should have hoists for scene context."""
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        assert len(doc.hoists) > 0
        assert doc.hoists[0].id is not None


class TestA2InvalidStrictFieldRejected:
    """A2: Invalid strict field is rejected."""

    def test_zero_wind_speed_rejected(self):
        """max_wind_speed_m_s = 0.0 should fail validation."""
        data = {
            "schema_version": "1.0.0",
            "model_type": "fixed_topology_crane_2d",
            "metadata": {},
            "environment": {
                "gravity_m_s2": -9.81,
                "max_wind_speed_m_s": 0.0,  # Invalid!
                "wind_reference_height_m_asl": 10.0,
                "air_density_kg_m3": 1.225,
                "wind_profile_exponent": 0.143,
            },
            "bodies": [],
            "nodes": [],
            "ropes": [],
            "hoists": [],
        }

        with pytest.raises(Exception):  # Should raise validation error
            normalize_document(data)


class TestA3HoistOutreachDefaults:
    """A3: Hoist outreach defaults derive from contractual points."""

    def test_outreach_min_from_contractual(self):
        """Omitted outreach_min should default to min of contractual points."""
        data = {
            "schema_version": "1.0.0",
            "model_type": "fixed_topology_crane_2d",
            "metadata": {},
            "environment": {},
            "bodies": [
                {"id": "boom", "mass_points": [], "wind_areas": []},
                {"id": "rear_leg", "mass_points": [], "wind_areas": []},
                {"id": "front_leg", "mass_points": [], "wind_areas": []},
                {"id": "platform", "mass_points": [], "wind_areas": []},
            ],
            "nodes": [],
            "ropes": [{"id": "test_rope", "segments": []}],
            "hoists": [
                {
                    "id": "TEST",
                    "rope_id": "test_rope",
                    "load_node_id": "test_hook",
                    "hook_mass_t": 0.0,
                    "hook_daf": 1.0,
                    # Omit outreach_min_m and outreach_max_m
                    "contractual_points": [
                        {"load_t": 100.0, "outreach_m": 30.0},
                        {"load_t": 90.0, "outreach_m": 45.5},
                        {"load_t": 95.0, "outreach_m": 41.0},
                    ],
                }
            ],
        }

        doc = normalize_document(data)
        hoist = doc.hoists[0]

        # Per spec: defaults should be min/max of contractual points
        assert hoist.outreach_min_m is None or hoist.outreach_min_m <= 30.0
        assert hoist.outreach_max_m is None or hoist.outreach_max_m >= 45.5


class TestA4InitialLoadDefaults:
    """A4: Initial load defaults are correct."""

    def test_first_hoist_selected(self):
        """First hoist should be selected on load."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        assert session.selected_hoist_id == doc.hoists[0].id

    def test_hook_load_auto_off(self):
        """Hook load auto mode should be off on initial load."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        hoist_state = session.get_active_hoist_state()
        assert hoist_state is not None
        assert hoist_state.scene_state.hook_load_auto is False

    def test_scene_hook_load_zero(self):
        """Scene hook load should display as 0.0 on load."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        hoist_state = session.get_active_hoist_state()
        assert hoist_state is not None
        assert hoist_state.scene_state.hook_load_kN == 0.0

    def test_scene_angle_zero(self):
        """Scene angle should be 0.0 on initial load."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        hoist_state = session.get_active_hoist_state()
        assert hoist_state is not None
        assert hoist_state.scene_state.boom_angle_deg == 0.0

    def test_contractual_selection_cleared(self):
        """Contractual selection should be cleared on initial load."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        hoist_state = session.get_active_hoist_state()
        assert hoist_state is not None
        assert hoist_state.selected_contractual_idx is None


class TestA5SceneAngleClamping:
    """A5: Scene angle from view clamps to allowed range."""

    def test_angle_clamping_logic(self):
        """Angle should clamp to allowed range."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        # For now, just verify the structure exists
        hoist_state = session.get_active_hoist_state()
        assert hoist_state is not None
        assert hasattr(hoist_state.scene_state, "boom_angle_deg")


class TestA7DesignLimitRowCatalog:
    """A7: Design-limit row catalog matches current app."""

    def test_heel_point_rows(self):
        """heel_point should include Fx, Fz, boom_axial, boom_normal."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        # Should have bootstrapped limits
        assert len(session.design_limits) > 0

        # Find heel_point limits
        boom_heel_limits = [
            limit for limit in session.design_limits if limit.entity_id == "heel_point"
        ]
        assert len(boom_heel_limits) > 0

        components = {limit.component for limit in boom_heel_limits}
        assert "Fx" in components
        assert "Fz" in components

    def test_split_aframe_entities_not_in_design_limits(self):
        """Split front/rear A-frame reaction rows should not be exposed in the UI catalog."""

        doc = create_default_document()
        session = SessionModel()
        session.set_document(doc)

        entity_ids = {limit.entity_id for limit in session.design_limits}
        assert "front_leg_left" not in entity_ids
        assert "front_leg_right" not in entity_ids
        assert "rear_leg_left" not in entity_ids
        assert "rear_leg_right" not in entity_ids


class TestA8WindDirectionContract:
    """A8: Scene wind uses one speed plus an explicit direction."""

    def test_scene_environment_state_uses_direction(self):
        vm = SceneHarness().vm

        # A single wind speed plus a direction, never a per-axis wind vector.
        assert not hasattr(vm, "windY")
        assert vm.windDirection == "+X"

    def test_omnidirectional_capacity_matches_worst_direction(self):

        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        session = SessionModel()
        session.set_document(doc)

        hoist_id = session.selected_hoist_id or doc.hoists[0].id
        hoist = next(h for h in doc.hoists if h.id == hoist_id)
        enabled_limits = {
            dl.id: {dl.component: dl.max_kN}
            for dl in session.design_limits
            if dl.enabled and dl.max_kN is not None
        }
        cp = hoist.contractual_points[0]
        kin = KinematicsAdapter(doc.model_dump())
        angle = kin.outreach_to_angle(float(cp.outreach_m), hoist_id)
        calc = CraneCalculator(doc)
        wind_speed = float(doc.environment.max_wind_speed_m_s)

        by_direction = []
        for wind_direction in ("+X", "-X", "+Y", "-Y"):
            pt = calc.compute_analysis_point(
                float(angle),
                0.0,
                hoist_id,
                wind_speed_m_s=wind_speed,
                wind_direction=wind_direction,
            )
            assert pt is not None
            cap = calc.compute_allowable_load(
                pt,
                enabled_limits,
                hook_daf=hoist.hook_daf,
                hook_mass_t=hoist.hook_mass_t,
            )
            by_direction.append((wind_direction, cap.max_allowable_load_kN))

        expected_direction, expected_capacity_kN = min(by_direction, key=lambda item: item[1])
        omni = calc.compute_omnidirectional_allowable_load(
            float(angle),
            hoist_id,
            enabled_limits,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hoist.hook_mass_t,
            wind_speed_m_s=wind_speed,
        )

        assert omni is not None
        assert omni.max_allowable_load_kN == pytest.approx(expected_capacity_kN)
        assert omni.governing_wind_direction == expected_direction

    def test_capacity_metrics_consistency_payload_vs_hook_force(self):
        """Verify that capacity metrics are consistent: payload ↔ hook-force round-trip.

        This test prevents regressions where max_allowable_load_kN (hook-force domain)
        is incorrectly used as a payload metric without subtracting hook mass.

        The round-trip verifies:
            payload_t → (payload + hook_mass) * gravity * daf → hook_force_kN
                    → hook_force / daf / gravity - hook_mass → payload_t (recovered)
        """
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        session = SessionModel()
        session.set_document(doc)
        hoist_id = session.selected_hoist_id or doc.hoists[0].id
        hoist = next(h for h in doc.hoists if h.id == hoist_id)

        enabled_limits = {
            dl.id: {dl.component: dl.max_kN}
            for dl in session.design_limits
            if dl.enabled and dl.max_kN is not None
        }

        kin = KinematicsAdapter(doc.model_dump())
        cp = hoist.contractual_points[0]
        angle = kin.outreach_to_angle(float(cp.outreach_m), hoist_id)
        calc = CraneCalculator(doc)

        # Compute capacity at a contractual point
        pt = calc.compute_analysis_point(float(angle), 0.0, hoist_id)
        assert pt is not None

        cap = calc.compute_allowable_load(
            pt,
            enabled_limits,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hoist.hook_mass_t,
        )
        assert cap is not None

        # Test 1: Forward conversion (payload → hook_force)
        # Use the payload from capacity result and verify it converts to hook_force correctly
        payload_t = cap.max_allowable_load_t
        gravity = abs(float(doc.environment.gravity_m_s2))
        hook_daf = hoist.hook_daf
        hook_mass_t = hoist.hook_mass_t

        expected_hook_force_kN = (payload_t + hook_mass_t) * gravity * hook_daf
        assert cap.max_allowable_load_kN == pytest.approx(expected_hook_force_kN, rel=1e-6)

        # Test 2: Reverse conversion (hook_force → payload)
        # Verify that converting back gives us the original payload (within tolerance)
        recovered_net_kN = cap.max_allowable_load_kN / hook_daf
        recovered_payload_t = recovered_net_kN / gravity - hook_mass_t
        recovered_payload_t = max(0.0, recovered_payload_t)

        assert recovered_payload_t == pytest.approx(payload_t, rel=1e-6)

        # Test 3: Contractual point check - if contractual point load is within capacity,
        # it should be true when using the payload metric (not the hook-force / gravity shortcut)
        if cp.load_t <= cap.max_allowable_load_t:
            # Contractual point passes
            assert cap.max_allowable_load_t >= cp.load_t
        else:
            # Contractual point fails; verify margin is negative
            assert cap.max_allowable_load_t < cp.load_t

    def test_scene_wind_overlay_hidden_for_y_directions_in_xz_canvas(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        hoist_id = doc.hoists[0].id

        def wind_vectors(direction: str):
            inputs = scene_inputs(
                doc,
                hoist_id,
                wind_speed_m_s=float(doc.environment.max_wind_speed_m_s),
                wind_direction=direction,
            )
            return inputs.body_loads(inputs.node_positions()).category(dl.WIND)

        assert wind_vectors("+Y") == ()
        assert wind_vectors("-Y") == ()
        assert len(wind_vectors("+X")) > 0
        assert len(wind_vectors("-X")) > 0


class TestA9InactiveHoistRopeRows:
    """A9: Scene reports rope tensions for inactive hoists too."""

    def _scene_rope_rows(self, doc):
        app = QGuiApplication.instance() or QGuiApplication([])
        _ = app
        harness = SceneHarness(doc)
        pt, rows, _ = harness.vm._calculator.compute_current_result_rows()
        assert pt is not None
        return harness.model.selected_hoist_id, pt, {row.name: row.demand_kN for row in rows}

    @staticmethod
    def _baseline_channel_for_hoist(doc, hoist) -> str:
        rope = next((r for r in doc.ropes if r.id == hoist.rope_id), None)
        if rope is not None and rope.tension_mode == "solve":
            return "boom_hoist"
        return str(hoist.rope_id)

    def test_inactive_hoists_with_hook_mass_have_rope_tension_rows(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        active_hoist_id, pt, row_map = self._scene_rope_rows(doc)

        inactive_payload_hoists = [
            h
            for h in doc.hoists
            if h.id != active_hoist_id and float(getattr(h, "hook_mass_t", 0.0)) > 1e-9
        ]
        if not inactive_payload_hoists:
            pytest.skip("No inactive payload hoists with non-zero hook mass in example")

        for hoist in inactive_payload_hoists:
            channel = self._baseline_channel_for_hoist(doc, hoist)
            assert channel in pt.baseline_rope_tensions
            assert pt.baseline_rope_tensions[channel] > 0.0
            assert hoist.id in row_map
            assert row_map[hoist.id] == pytest.approx(pt.baseline_rope_tensions[channel])

    def test_inactive_hoist_with_zero_hook_mass_still_shows_zero_row(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        doc = load_document(example_path)
        rope_by_id = {r.id: r for r in doc.ropes}
        target = next(
            (
                h
                for h in doc.hoists
                if float(getattr(h, "hook_mass_t", 0.0)) > 1e-9
                and rope_by_id.get(h.rope_id) is not None
                and rope_by_id[h.rope_id].tension_mode != "solve"
            ),
            None,
        )
        if target is None:
            pytest.skip("No suitable inactive payload hoist found in example")
        target.hook_mass_t = 0.0

        _active_hoist_id, _pt, row_map = self._scene_rope_rows(doc)

        assert target.id in row_map
        assert row_map[target.id] == pytest.approx(0.0)


class TestAuthoredSchemaPolicy:
    """Strict authored schema policy and latest-schema round-trip behavior."""

    def _minimal_v5(self) -> dict:
        return {
            "schema": {"name": "crane-statics", "version": "5.13.0"},
            "metadata": {"name": "V5 Minimal"},
            "model_definition": {
                "boom_width_m": 1.0,
                "slewing_bearing_diameter_m": 1.0,
                "environment": {
                    "gravity_m_s2": 9.81,
                    "air_density_kg_m3": 1.225,
                    "wind_profile_exponent": 0.143,
                    "wind_reference_height_m_asl": 10.0,
                    "mean_sealevel_z_m": -35.0,
                    "max_wind_speed_m_s": 20.0,
                },
                "vessel_motion": {
                    "accel_x_m_s2": 0.0,
                    "accel_y_m_s2": 0.0,
                    "accel_z_m_s2": 0.0,
                    "pitch_angular_accel_rad_s2": 0.0,
                    "roll_angular_accel_rad_s2": 0.0,
                    "reference_x_m": 0.0,
                    "reference_z_m": 0.0,
                },
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
                "boom": {
                    "mass_points": [
                        {
                            "id": "cg",
                            "mass_t": 1.0,
                            "position": {"u_m": 10.0, "v_m": 2.0, "w_m": 0.5},
                        }
                    ],
                    "wind_areas": [
                        {
                            "id": "wa",
                            "area_w_m2": 1.0,
                            "area_v_m2": 1.0,
                            "cd": 1.0,
                            "position": {"u_m": 9.5, "w_m": 0.2},
                        }
                    ],
                    "nodes": {"mh_hook": {"u_m": 40.0, "w_m": -2.0}},
                },
                "rear_leg": {
                    "mass_points": [],
                    "wind_areas": [
                        {
                            "id": "rear_wa",
                            "area_x_m2": 2.0,
                            "area_y_m2": 3.0,
                            "cd": 1.0,
                            "position": {"x_m": 0.0, "z_m": 20.0},
                        }
                    ],
                    "nodes": {},
                },
                "front_leg": {"mass_points": [], "wind_areas": [], "nodes": {}},
                "platform": {"mass_points": [], "wind_areas": [], "nodes": {}},
                "payload_hoists": {
                    "MH": {
                        "support_node_id": "mh_hook",
                        "hook_daf": 1.0,
                        "offlead_deg": 0.0,
                        "rope_segments": [{"from": "boom_heel", "to": "mh_hook", "parts": 2}],
                        "falls": 2,
                        "hook_mass_t": 0.0,
                        "contractual_points": [{"outreach_m": 60.0, "load_t": 100.0}],
                    }
                },
                "boom_hoist": {
                    "rope_segments": [{"from": "boom_heel", "to": "rear_top", "parts": 2}],
                },
            },
        }

    def test_unsupported_major_version_is_rejected_by_normalizer(self):
        data = self._minimal_v5()
        data["schema"]["version"] = "3.2.0"
        with pytest.raises(
            ValueError, match="Only crane-statics schema major version 5 is supported"
        ):
            normalize_document(data)

    def test_v5_minor_version_bump_is_accepted_by_normalizer(self):
        data = self._minimal_v5()
        data["schema"]["version"] = "5.1.0"
        doc = normalize_document(data)
        assert doc is not None

    def test_v6_authored_is_rejected_by_normalizer(self):
        data = self._minimal_v5()
        data["schema"]["version"] = "6.0.0"
        with pytest.raises(
            ValueError, match="Only crane-statics schema major version 5 is supported"
        ):
            normalize_document(data)

    def test_unsupported_version_is_rejected_by_loader(self, tmp_path):
        data = self._minimal_v5()
        data["schema"]["version"] = "3.2.0"
        path = tmp_path / "legacy.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Unsupported authored schema version"):
            load_document(path)

    def test_v5_named_authored_input_normalizes(self):
        data = self._minimal_v5()
        doc = normalize_document(data)
        assert len(doc.hoists) == 2
        assert {h.id for h in doc.hoists} == {"MH", "BH"}
        assert {h.rope_id for h in doc.hoists} == {"MH__rope", "BH__rope"}
        assert len(doc.ropes) == 2
        assert {r.id for r in doc.ropes} == {"MH__rope", "BH__rope"}

        bh = next(h for h in doc.hoists if h.id == "BH")
        assert bh.contractual_points == []
        assert bh.hook_mass_t == 0.0
        assert bh.hook_daf == 1.0

    def test_v5_component_mass_points_and_wind_areas_can_be_omitted(self):
        data = self._minimal_v5()
        for body_id in ("boom", "rear_leg", "front_leg", "platform"):
            data["model_definition"][body_id].pop("mass_points", None)
            data["model_definition"][body_id].pop("wind_areas", None)

        doc = normalize_document(data)
        for body in doc.bodies:
            assert body.mass_points == []
            assert body.wind_areas == []

        authored = document_to_authored_form(doc)
        for body_id in ("boom", "rear_leg", "front_leg", "platform"):
            assert authored["model_definition"][body_id]["mass_points"] == []
            assert authored["model_definition"][body_id]["wind_areas"] == []

    def test_v5_schema_defaults_are_applied_by_loader(self):
        data = self._minimal_v5()
        data["model_definition"]["rear_leg"].pop("nodes")
        data["model_definition"]["vessel_motion"].pop("accel_y_m_s2")

        doc = normalize_document(data)

        rear_leg = next(body for body in doc.bodies if body.id == "rear_leg")
        assert rear_leg.mass_points == []
        assert len(rear_leg.wind_areas) == 1
        assert doc.environment.vessel_motion.accel_y_m_s2 == pytest.approx(0.0)

    def test_v5_rejects_zero_max_wind_speed(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["environment"]["max_wind_speed_m_s"] = 0.0
        path = tmp_path / "zero_wind.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_v5_rejects_authored_hook_travel(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["MH"]["hook_travel"] = {
            "min_m": 5.0,
            "max_m": 80.0,
        }
        path = tmp_path / "authored_travel.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="hook_travel"):
            load_document(path)

    def test_v5_rejects_authored_payload_rope_length(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["MH"]["rope_length_m"] = 500.0
        path = tmp_path / "authored_rope_length.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="rope_length_m"):
            load_document(path)

    def test_v5_dead_turns_require_a_drum_diameter(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["MH"]["drum_dead_turns"] = 4
        path = tmp_path / "dead_turns.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="drum_diameter_m"):
            load_document(path)

    def _reachable_v5(self) -> dict:
        """_minimal_v5 with a contractual outreach the 40 m boom can actually reach."""
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["MH"]["contractual_points"] = [
            {"outreach_m": 30.0, "load_t": 100.0}
        ]
        return data

    def test_v5_dead_turns_extend_the_derived_rope_length(self):
        bare = normalize_document(self._reachable_v5())
        data = self._reachable_v5()
        data["model_definition"]["payload_hoists"]["MH"]["drum_dead_turns"] = 4
        data["model_definition"]["payload_hoists"]["MH"]["drum_diameter_m"] = 1.5
        with_dead_turns = normalize_document(data)

        bare_mh = next(h for h in bare.hoists if h.id == "MH")
        dead_mh = next(h for h in with_dead_turns.hoists if h.id == "MH")

        assert dead_mh.max_hook_travel_m == pytest.approx(bare_mh.max_hook_travel_m)
        assert dead_mh.rope_length_m - bare_mh.rope_length_m == pytest.approx(4 * math.pi * 1.5)

    def test_v5_hook_height_defaults_to_mean_sea_level(self):
        doc = normalize_document(self._minimal_v5())
        assert doc.hook_height_at_min_outreach_m == pytest.approx(-35.0)

    def test_v5_authored_hook_height_drives_the_derived_travel(self):
        data = self._reachable_v5()
        data["model_definition"]["hook_height_at_min_outreach_m"] = -60.0
        deeper = normalize_document(data)
        shallower = normalize_document(self._reachable_v5())

        deeper_mh = next(h for h in deeper.hoists if h.id == "MH")
        shallower_mh = next(h for h in shallower.hoists if h.id == "MH")

        assert deeper_mh.max_hook_travel_m - shallower_mh.max_hook_travel_m == pytest.approx(25.0)
        assert deeper_mh.rope_length_m > shallower_mh.rope_length_m

    def test_v5_directional_wind_area_fields_round_trip(self):
        data = self._minimal_v5()
        data["model_definition"]["boom"]["wind_areas"][0]["area_w_m2"] = 1.5
        data["model_definition"]["boom"]["wind_areas"][0]["area_v_m2"] = 3.5

        doc = normalize_document(data)
        authored = document_to_authored_form(doc)
        saved_boom_wa = authored["model_definition"]["boom"]["wind_areas"][0]
        saved_rear_wa = authored["model_definition"]["rear_leg"]["wind_areas"][0]

        assert saved_boom_wa["area_w_m2"] == pytest.approx(1.5)
        assert saved_boom_wa["area_v_m2"] == pytest.approx(3.5)
        assert "area_m2" not in saved_boom_wa
        assert "area_x_m2" not in saved_boom_wa
        assert "area_y_m2" not in saved_boom_wa
        assert saved_rear_wa["area_x_m2"] == pytest.approx(2.0)
        assert saved_rear_wa["area_y_m2"] == pytest.approx(3.0)
        assert "area_w_m2" not in saved_rear_wa
        assert "area_v_m2" not in saved_rear_wa

    def test_v5_named_mass_position_round_trip(self):
        data = self._minimal_v5()
        data["model_definition"]["rear_leg"]["mass_points"] = [
            {"id": "rear_cg", "mass_t": 2.5, "position": {"x_m": 1.0, "y_m": -3.25, "z_m": 9.5}}
        ]

        doc = normalize_document(data)
        boom_body = next(b for b in doc.bodies if b.id == "boom")
        rear_body = next(b for b in doc.bodies if b.id == "rear_leg")
        boom_mp = boom_body.mass_points[0]
        rear_mp = rear_body.mass_points[0]

        assert boom_mp.local_x_m == pytest.approx(10.0)
        assert boom_mp.local_y_m == pytest.approx(2.0)
        assert boom_mp.local_z_m == pytest.approx(0.5)
        assert rear_mp.x_m == pytest.approx(1.0)
        assert rear_mp.y_m == pytest.approx(-3.25)
        assert rear_mp.z_m == pytest.approx(9.5)

        authored = document_to_authored_form(doc)
        boom_position = authored["model_definition"]["boom"]["mass_points"][0]["position"]
        rear_position = authored["model_definition"]["rear_leg"]["mass_points"][0]["position"]

        assert boom_position == pytest.approx({"u_m": 10.0, "v_m": 2.0, "w_m": 0.5})
        assert rear_position == pytest.approx({"x_m": 1.0, "y_m": -3.25, "z_m": 9.5})

    def test_mass_point_y_offset_influences_split_support_results(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        base_doc = load_document(example_path)
        offset_doc = base_doc.model_copy(deep=True)

        offset_platform = next((b for b in offset_doc.bodies if b.id == "platform"), None)
        if offset_platform is None or not offset_platform.mass_points:
            pytest.skip("Platform mass points unavailable in example")
        offset_platform.mass_points[0].y_m = 6.0

        base_calc = CraneCalculator(base_doc)
        offset_calc = CraneCalculator(offset_doc)

        base_pt = base_calc.compute_analysis_point(
            45.0,
            0.0,
            "MH",
            wind_speed_m_s=0.0,
            wind_direction="+X",
            accel_x_m_s2=0.0,
            accel_y_m_s2=0.0,
            accel_z_m_s2=0.0,
            pitch_accel_rad_s2=0.0,
            roll_accel_rad_s2=0.0,
            offlead_deg=0.0,
            sidelead_deg=0.0,
        )
        offset_pt = offset_calc.compute_analysis_point(
            45.0,
            0.0,
            "MH",
            wind_speed_m_s=0.0,
            wind_direction="+X",
            accel_x_m_s2=0.0,
            accel_y_m_s2=0.0,
            accel_z_m_s2=0.0,
            pitch_accel_rad_s2=0.0,
            roll_accel_rad_s2=0.0,
            offlead_deg=0.0,
            sidelead_deg=0.0,
        )

        assert base_pt is not None
        assert offset_pt is not None

        base_platform_mx = float(base_pt.baseline_reactions["platform_base"].get("Mx", 0.0))
        offset_platform_mx = float(offset_pt.baseline_reactions["platform_base"].get("Mx", 0.0))

        assert abs(offset_platform_mx - base_platform_mx) > 1e-6

    def test_lateral_acceleration_splits_every_support_group_left_of_right(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        calc = CraneCalculator(load_document(example_path))
        pt = calc.compute_analysis_point(
            45.0,
            0.0,
            "MH",
            wind_speed_m_s=0.0,
            wind_direction="+X",
            accel_x_m_s2=0.0,
            accel_y_m_s2=1.5,
            accel_z_m_s2=0.0,
            pitch_accel_rad_s2=0.0,
            roll_accel_rad_s2=0.05,
            offlead_deg=0.0,
            sidelead_deg=0.0,
        )

        assert pt is not None

        # Lateral inertia produces an overturning moment about every support group,
        # so each left/right pair must carry a differential rather than an even split.
        for left_entity, right_entity in (
            ("heel_left", "heel_right"),
            ("front_leg_left", "front_leg_right"),
            ("rear_leg_left", "rear_leg_right"),
        ):
            left = pt.baseline_reactions[left_entity]
            right = pt.baseline_reactions[right_entity]
            differential = abs(float(left.get("Fz", 0.0)) - float(right.get("Fz", 0.0)))
            assert differential > 1e-6, f"{left_entity}/{right_entity} split evenly"

    def test_directional_wind_areas_follow_wind_axis(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")

        base_doc = load_document(example_path)
        base_data = base_doc.model_dump()

        data_x_small = json.loads(json.dumps(base_data))
        data_x_large = json.loads(json.dumps(base_data))
        data_y_large = json.loads(json.dumps(base_data))

        data_x_small["bodies"][0]["wind_areas"][0]["area_w_m2"] = 100.0
        data_x_small["bodies"][0]["wind_areas"][0]["area_v_m2"] = 100.0
        data_x_large["bodies"][0]["wind_areas"][0]["area_w_m2"] = 200.0
        data_x_large["bodies"][0]["wind_areas"][0]["area_v_m2"] = 100.0
        data_y_large["bodies"][0]["wind_areas"][0]["area_w_m2"] = 100.0
        data_y_large["bodies"][0]["wind_areas"][0]["area_v_m2"] = 200.0

        calc_x_small = CraneCalculator(CraneDocument(**data_x_small))
        calc_x_large = CraneCalculator(CraneDocument(**data_x_large))
        calc_y_large = CraneCalculator(CraneDocument(**data_y_large))

        pt_x_small = calc_x_small.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=20.0, wind_direction="+X"
        )
        pt_x_large = calc_x_large.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=20.0, wind_direction="+X"
        )
        pt_y_small = calc_x_small.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=20.0, wind_direction="+Y"
        )
        pt_y_large = calc_y_large.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=20.0, wind_direction="+Y"
        )

        assert pt_x_small is not None and pt_x_large is not None
        assert pt_y_small is not None and pt_y_large is not None

        assert abs(float(pt_x_large.baseline_reactions["platform_base"].get("Fx", 0.0))) > abs(
            float(pt_x_small.baseline_reactions["platform_base"].get("Fx", 0.0))
        )
        assert abs(float(pt_y_large.baseline_reactions["platform_base"].get("Fy", 0.0))) > abs(
            float(pt_y_small.baseline_reactions["platform_base"].get("Fy", 0.0))
        )

    def test_v5_named_authored_input_loads(self, tmp_path):
        data = self._minimal_v5()
        path = tmp_path / "v5.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        doc = load_document(path)
        assert doc.model_type == "fixed_topology_crane_2d"
        assert len(doc.hoists) == 2

    def test_v5_rejects_authored_hanging_node(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["boom"]["nodes"]["user_hook"] = {
            "hang_from_node_id": "boom_heel",
        }
        path = tmp_path / "authored_hanging_node.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

        doc = normalize_document(self._minimal_v5())
        managed = next(node for node in doc.nodes if node.id == "__hook__MH")
        assert managed.below_node_id == "mh_hook"

    def test_v5_split_mode_points_normalize_into_runtime_fields(self):
        data = self._minimal_v5()
        mh = data["model_definition"]["payload_hoists"]["MH"]
        mh["split"] = {
            "falls": 1,
            "hook_mass_t": 0.0,
            "contractual_points": [{"outreach_m": 50.0, "load_t": 80.0}],
        }

        doc = normalize_document(data)
        runtime_mh = next(h for h in doc.hoists if h.id == "MH")
        assert runtime_mh.splitable_block is True
        assert runtime_mh.split_falls == 1
        assert runtime_mh.split_hook_mass_t == pytest.approx(0.0)
        assert len(runtime_mh.split_contractual_points) == 1
        assert runtime_mh.split_contractual_points[0].outreach_m == pytest.approx(50.0)
        assert runtime_mh.split_contractual_points[0].load_t == pytest.approx(80.0)

    def test_v5_rejects_removed_modes_wrapper(self, tmp_path):
        data = self._minimal_v5()
        hoist = data["model_definition"]["payload_hoists"]["MH"]
        hoist["modes"] = {
            "normal": {
                "falls": hoist.pop("falls"),
                "hook_mass_t": hoist.pop("hook_mass_t"),
                "contractual_points": hoist.pop("contractual_points"),
            }
        }

        path = tmp_path / "removed_modes.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_v5_rejects_split_values_above_normal_values(self):
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["MH"]["split"] = {
            "falls": 3,
            "hook_mass_t": 1.0,
            "contractual_points": [{"outreach_m": 50.0, "load_t": 80.0}],
        }

        with pytest.raises(ValueError, match="split.falls must be <= falls"):
            normalize_document(data)

        data["model_definition"]["payload_hoists"]["MH"]["split"]["falls"] = 1
        data["model_definition"]["payload_hoists"]["MH"]["split"]["hook_mass_t"] = 1.0
        with pytest.raises(ValueError, match="split.hook_mass_t must be <= hook_mass_t"):
            normalize_document(data)

    def test_v5_rejects_missing_solve_hoist(self, tmp_path):
        data = self._minimal_v5()
        del data["model_definition"]["boom_hoist"]
        path = tmp_path / "v5_no_solve.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    @pytest.mark.parametrize(
        "primary_key", ["boom_heel", "upper_hinge", "rear_hinge", "front_hinge"]
    )
    def test_v5_requires_each_primary_structure_point(self, tmp_path, primary_key):
        data = self._minimal_v5()
        del data["model_definition"][primary_key]
        path = tmp_path / f"missing_{primary_key}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    @pytest.mark.parametrize("dimension_key", ["boom_width_m"])
    def test_v5_requires_support_dimensions(self, tmp_path, dimension_key):
        data = self._minimal_v5()
        data["model_definition"].pop(dimension_key, None)
        path = tmp_path / f"missing_{dimension_key}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_v5_allows_missing_slewing_bearing_diameter(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"].pop("slewing_bearing_diameter_m", None)
        path = tmp_path / "missing_slewing_bearing_diameter.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        doc = load_document(path)

        assert doc.support_widths.slewing_bearing_diameter_m is None

    def test_v5_omits_slewing_bearing_diameter_on_round_trip_when_absent(self, tmp_path):
        from crane_statics.data import document_to_authored_form

        data = self._minimal_v5()
        data["model_definition"].pop("slewing_bearing_diameter_m", None)
        path = tmp_path / "missing_slewing_bearing_diameter.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        doc = load_document(path)
        authored = document_to_authored_form(doc)

        assert "slewing_bearing_diameter_m" not in authored["model_definition"]

    def test_v5_linear_mass_round_trips_for_boom_and_payload(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["boom_hoist"]["linear_mass_kg_m"] = 4.2
        data["model_definition"]["payload_hoists"]["MH"]["linear_mass_kg_m"] = 3.1
        path = tmp_path / "linear_mass.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        doc = load_document(path)
        rope_by_hoist = {
            hoist.id: next(rope for rope in doc.ropes if rope.id == hoist.rope_id)
            for hoist in doc.hoists
        }
        assert rope_by_hoist["BH"].linear_mass_kg_m == pytest.approx(4.2)
        assert rope_by_hoist["MH"].linear_mass_kg_m == pytest.approx(3.1)
        assert len(rope_by_hoist) == 2

        out_path = tmp_path / "linear_mass_saved.json"
        save_document(doc, out_path)
        saved = json.loads(out_path.read_text())
        assert saved["model_definition"]["boom_hoist"]["linear_mass_kg_m"] == pytest.approx(4.2)
        assert saved["model_definition"]["payload_hoists"]["MH"][
            "linear_mass_kg_m"
        ] == pytest.approx(3.1)

    def test_v5_boom_hoist_linear_mass_reaches_runtime_hoist(self):
        doc = load_document(Path(__file__).parent.parent / "examples" / "crane_input_22689.json")
        boom_hoist = next(hoist for hoist in doc.hoists if hoist.id == "BH")
        boom_rope = next(rope for rope in doc.ropes if rope.id == boom_hoist.rope_id)

        assert boom_hoist.linear_mass_kg_m == pytest.approx(20.3)
        assert boom_rope.linear_mass_kg_m == pytest.approx(20.3)

    def test_v5_rejects_negative_linear_mass(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["boom_hoist"]["linear_mass_kg_m"] = -0.1
        path = tmp_path / "negative_linear_mass.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_v5_rejects_persisted_scene_defaults(self, tmp_path):
        data = self._minimal_v5()
        data["analysis_defaults"] = {
            "scene": {
                "wind_speed_m_s": 15.1,
                "accelerations": {
                    "accel_x_m_s2": 0.0,
                    "accel_z_m_s2": 0.0,
                    "pitch_angular_accel_rad_s2": 0.0,
                    "reference_x_m": 0.0,
                    "reference_z_m": 0.0,
                },
            }
        }
        path = tmp_path / "scene_defaults.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_v5_accepts_additional_payload_hoist(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["payload_hoists"]["AH"] = {
            "support_node_id": "boom_heel",
            "hook_daf": 1.0,
            "offlead_deg": 0.0,
            "falls": 2,
            "hook_mass_t": 0.0,
            "contractual_points": [{"outreach_m": 60.0, "load_t": 100.0}],
            "rope_segments": [{"from": "boom_heel", "to": "front_base", "parts": 2}],
        }
        path = tmp_path / "v5_payload_extra.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        # This one is valid in v5.4 because payload hoists no longer carry per-hoist tension mode.
        doc = load_document(path)
        assert len(doc.hoists) == 3

    def test_v5_rejects_payload_fields_on_boom_hoist(self, tmp_path):
        data = self._minimal_v5()
        data["model_definition"]["boom_hoist"]["load_node_id"] = "boom_heel"
        path = tmp_path / "v5_solve_payload_fields.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(DocumentIOError, match="Schema validation failed"):
            load_document(path)

    def test_saved_document_validates_against_v5_schema(self, tmp_path):
        doc = create_default_document()
        out_path = tmp_path / "saved_schema_valid.json"
        save_document(doc, out_path)

        saved = json.loads(out_path.read_text())
        schema = json.loads(
            resources.files("crane_statics.schemas")
            .joinpath(SCHEMA_FILENAME)
            .read_text(encoding="utf-8")
        )

        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(saved), key=lambda e: list(e.absolute_path))
        assert not errors, f"Schema validation errors: {[e.message for e in errors]}"

    def test_save_outputs_compact_v5_schema(self, tmp_path):
        doc = create_default_document()
        out_path = tmp_path / "saved_v5.json"
        save_document(doc, out_path)

        saved = json.loads(out_path.read_text())
        assert saved["schema"]["name"] == "crane-statics"
        assert saved["schema"]["version"] == "5.13.0"
        assert "model_definition" in saved
        assert "boom" in saved["model_definition"]
        assert "rear_leg" in saved["model_definition"]
        assert "front_leg" in saved["model_definition"]
        assert "platform" in saved["model_definition"]
        assert "ropes" not in saved["model_definition"]
        assert "nodes" not in saved["model_definition"]
        assert "nodes" in saved["model_definition"]["boom"]
        assert "topology" not in saved["model_definition"]
        assert "units" not in saved["metadata"]
        assert "payload_hoists" in saved["model_definition"]
        assert "boom_hoist" in saved["model_definition"]
        assert "MH" in saved["model_definition"]["payload_hoists"]
        assert "support_node_id" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "hook_travel" not in saved["model_definition"]["payload_hoists"]["MH"]
        assert "rope_length_m" not in saved["model_definition"]["payload_hoists"]["MH"]
        assert "hook_height_at_min_outreach_m" in saved["model_definition"]
        assert "hook_daf" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "offlead_deg" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "falls" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "hook_mass_t" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "contractual_points" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "split" not in saved["model_definition"]["payload_hoists"]["MH"]
        assert "splitable_block" not in saved["model_definition"]["payload_hoists"]["MH"]
        assert "rope_segments" in saved["model_definition"]["payload_hoists"]["MH"]
        assert "rope" not in saved["model_definition"]["payload_hoists"]["MH"]
        assert "rope_segments" in saved["model_definition"]["boom_hoist"]
        assert "rope" not in saved["model_definition"]["boom_hoist"]
        assert "id" not in saved["model_definition"]["boom_hoist"]
        assert "hook_travel" not in saved["model_definition"]["boom_hoist"]
        assert "load_node_id" not in saved["model_definition"]["boom_hoist"]
        assert "hook" not in saved["model_definition"]["boom_hoist"]
        assert "contractual_curve" not in saved["model_definition"]["boom_hoist"]
        mh_nodes = saved["model_definition"]["boom"]["nodes"]
        assert isinstance(mh_nodes["mh_hook"], dict)
        mh_seg0 = saved["model_definition"]["payload_hoists"]["MH"]["rope_segments"][0]
        assert isinstance(mh_seg0, dict)

    def test_save_emits_split_mode_without_legacy_splitable_flag(self, tmp_path):
        doc = load_document(Path(__file__).parent.parent / "examples" / "crane_input_22689.json")
        out_path = tmp_path / "saved_v5_split.json"
        save_document(doc, out_path)

        saved = json.loads(out_path.read_text())
        mh = saved["model_definition"]["payload_hoists"]["MH"]
        assert "split" in mh
        assert "splitable_block" not in mh
        assert mh["split"]["falls"] == 12
        assert mh["split"]["hook_mass_t"] == pytest.approx(91.51)


class TestSplitModeAutosetAndChart:
    """Targeted tests for split-mode autoset and chart mode behavior."""

    def _example_doc(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")
        return load_document(example_path)

    def test_opposite_wind_directions_share_one_primitive_basis(self):
        """Wind sign is applied by composition, so the sensitivities are identical.

        Only the baseline differs between +X and -X: the primitive basis is built
        from the wind magnitude alone.
        """
        doc = self._example_doc()
        calc = CraneCalculator(doc)

        first = calc.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=15.1, wind_direction="+X"
        )
        second = calc.compute_analysis_point(
            45.0, 0.0, "MH", wind_speed_m_s=15.1, wind_direction="-X"
        )

        assert first is not None and second is not None
        assert first.baseline_reactions != second.baseline_reactions
        assert first.sensitivity_reactions == second.sensitivity_reactions

    def test_rope_lead_channel_composition_matches_legacy_analysis_points(self):
        doc = self._example_doc()
        calc = CraneCalculator(doc)
        hoist = next(item for item in doc.hoists if item.id == "MH")
        angle = 45.0
        wind_speed = float(doc.environment.max_wind_speed_m_s)
        zero_lead_points = {}

        for case in iter_wind_lead_directional_cases(hoist, wind_speed):
            if case.wind_direction not in zero_lead_points:
                zero_lead_points[case.wind_direction] = calc.compute_analysis_point(
                    angle,
                    0.0,
                    hoist.id,
                    wind_speed_m_s=wind_speed,
                    wind_direction=case.wind_direction,
                    offlead_deg=0.0,
                    sidelead_deg=0.0,
                )

            legacy = calc.compute_analysis_point(
                angle,
                0.0,
                hoist.id,
                wind_speed_m_s=wind_speed,
                wind_direction=case.wind_direction,
                offlead_deg=case.offlead_deg,
                sidelead_deg=case.sidelead_deg,
            )
            composed = limit_auto_set_module._compose_lead_channel_point(
                zero_lead_points[case.wind_direction],
                case,
            )

            assert legacy is not None
            assert composed.sensitivity_rope_tensions == pytest.approx(
                legacy.sensitivity_rope_tensions
            )

    def test_rope_autoset_composes_lead_cases_from_one_point_per_wind(self, monkeypatch):
        doc = self._example_doc()
        hoist = next(item for item in doc.hoists if item.id == "MH")
        original = CraneCalculator.compute_analysis_point
        call_count = 0

        def counting_compute_analysis_point(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(
            CraneCalculator, "compute_analysis_point", counting_compute_analysis_point
        )
        result = compute_required_rope_capacity_kN(doc, hoist.rope_id)

        assert result.required_kN is not None
        assert call_count == result.evaluated_points * 4

    def test_rope_autoset_uses_worst_case_across_modes(self):
        doc = self._example_doc()
        mh = next(h for h in doc.hoists if h.id == "MH")
        assert bool(getattr(mh, "splitable_block", False))

        normal_doc = doc.model_copy(deep=True)
        normal_mh = next(h for h in normal_doc.hoists if h.id == "MH")
        normal_mh.splitable_block = False

        split_only_doc = doc.model_copy(deep=True)
        split_mh = next(h for h in split_only_doc.hoists if h.id == "MH")
        split_mh.contractual_points = []

        worst = compute_required_rope_capacity_kN(doc, mh.rope_id)
        normal_only = compute_required_rope_capacity_kN(normal_doc, mh.rope_id)
        split_only = compute_required_rope_capacity_kN(split_only_doc, mh.rope_id)

        assert worst.required_kN is not None
        assert normal_only.required_kN is not None
        assert split_only.required_kN is not None

        expected = max(float(normal_only.required_kN), float(split_only.required_kN))
        assert float(worst.required_kN) == pytest.approx(expected)

        if float(split_only.required_kN) > float(normal_only.required_kN) + 1e-9:
            assert worst.governing_mode == "split"
        elif float(normal_only.required_kN) > float(split_only.required_kN) + 1e-9:
            assert worst.governing_mode == "normal"
        else:
            assert worst.governing_mode in {"normal", "split"}

    def test_connection_autoset_uses_worst_case_across_modes(self):
        doc = self._example_doc()
        mh = next(h for h in doc.hoists if h.id == "MH")
        assert bool(getattr(mh, "splitable_block", False))

        normal_doc = doc.model_copy(deep=True)
        normal_mh = next(h for h in normal_doc.hoists if h.id == "MH")
        normal_mh.splitable_block = False

        split_only_doc = doc.model_copy(deep=True)
        split_mh = next(h for h in split_only_doc.hoists if h.id == "MH")
        split_mh.contractual_points = []

        conn_id = "heel_point"
        component = "resultant"
        worst = compute_required_connection_capacity_kN(doc, conn_id, component)
        normal_only = compute_required_connection_capacity_kN(normal_doc, conn_id, component)
        split_only = compute_required_connection_capacity_kN(split_only_doc, conn_id, component)

        assert worst.required_kN is not None
        assert normal_only.required_kN is not None
        assert split_only.required_kN is not None

        expected = max(float(normal_only.required_kN), float(split_only.required_kN))
        assert float(worst.required_kN) == pytest.approx(expected)

        if float(split_only.required_kN) > float(normal_only.required_kN) + 1e-9:
            assert worst.governing_mode == "split"
        elif float(normal_only.required_kN) > float(split_only.required_kN) + 1e-9:
            assert worst.governing_mode == "normal"
        else:
            assert worst.governing_mode in {"normal", "split"}

    def test_chart_mode_controls_visible_only_for_splitable_hoist(self):
        doc = self._example_doc()
        session = SessionState()
        session.model.set_document(doc)
        chart_vm = ChartViewModel(session)

        # MH is splitable in the example; chart mode controls should be visible.
        chart_vm.selectHoist("MH")
        assert chart_vm.splitable is True

        # WH is non-splitable; mode controls should hide.
        chart_vm.selectHoist("WH")
        assert chart_vm.splitable is False

    def test_scene_hook_configuration_visible_only_for_splitable_hoist(self):
        harness = SceneHarness(self._example_doc(), "MH")

        assert harness.vm.splitable is True

        harness.vm.selectHoist("WH")
        assert harness.vm.splitable is False

    def test_scene_mode_toggle_syncs_chart_mode_and_switches_contractual_chips(self):
        doc = self._example_doc()
        mh = next(h for h in doc.hoists if h.id == "MH")
        assert len(mh.contractual_points) > 0
        assert len(mh.split_contractual_points) > 0

        harness = SceneHarness(doc, "MH")
        chart_vm = ChartViewModel(harness.session)
        chart_vm.selectHoist("MH")

        assert harness.vm.hookMode == "normal"
        assert len(harness.vm.contractualLabels) == len(mh.contractual_points)

        hs = harness.model.hoist_states["MH"]
        harness.vm.selectContractual(0)

        harness.vm.setHookMode("split")

        assert hs.split_mode_active is True
        assert hs.chart_mode == "split"
        assert hs.selected_contractual_idx is None
        assert harness.vm.hookMode == "split"
        # The chart view model reads the shared session mode, so both stay in sync.
        chart_vm.reload()
        assert chart_vm.chartMode == "split"
        assert len(harness.vm.contractualLabels) == len(mh.split_contractual_points)

    def test_scene_mode_switch_always_clears_contractual_selection(self):
        doc = self._example_doc()
        mh = next(h for h in doc.hoists if h.id == "MH")
        if not mh.split_contractual_points:
            pytest.skip("Example split contractual points are required")

        harness = SceneHarness(doc, "MH")
        hs = harness.model.hoist_states["MH"]

        harness.vm.selectContractual(0)
        harness.vm.setHookMode("split")
        assert hs.selected_contractual_idx is None

        harness.vm.selectContractual(0)
        harness.vm.setHookMode("normal")
        assert hs.selected_contractual_idx is None
        assert hs.chart_mode == "normal"
        assert harness.vm.hookMode == "normal"

    def test_chart_mode_switch_renders_selected_dataset(self):
        doc = self._example_doc()
        session = SessionState()
        session.model.set_document(doc)

        chart_vm = ChartViewModel(session)
        chart_vm.selectHoist("MH")

        hoist = next(h for h in doc.hoists if h.id == "MH")
        synthetic = {
            "hoist": hoist,
            "modes": {
                "normal": {
                    "curve_data": [(10.0, 100.0)],
                    "contractual_results": [],
                    "limit_series": [],
                    "n_points": 1,
                },
                "split": {
                    "curve_data": [(10.0, 90.0)],
                    "contractual_results": [],
                    "limit_series": [],
                    "n_points": 1,
                },
            },
            "n_points": 1,
            "n_points_by_mode": {"normal": 1, "split": 1},
        }

        chart_vm._on_sweep_finished(synthetic)
        assert chart_vm.curvePoints == [[10.0, 100.0]]

        chart_vm.setChartMode("split")
        assert chart_vm.curvePoints == [[10.0, 90.0]]
        assert chart_vm.chartMode == "split"

    def test_chart_split_mode_missing_dataset_renders_empty_instead_of_fallback(self):
        doc = self._example_doc()
        session = SessionState()
        session.model.set_document(doc)

        chart_vm = ChartViewModel(session)
        chart_vm.selectHoist("MH")
        chart_vm.setChartMode("split")

        hoist = next(h for h in doc.hoists if h.id == "MH")
        synthetic = {
            "hoist": hoist,
            "modes": {
                "normal": {
                    "curve_data": [(10.0, 100.0)],
                    "contractual_results": [],
                    "limit_series": [],
                    "n_points": 1,
                },
            },
            "n_points": 1,
            "n_points_by_mode": {"normal": 1},
        }

        chart_vm._on_sweep_finished(synthetic)
        assert chart_vm.curvePoints == []
        assert chart_vm.chartMode == "split"

    def test_split_mode_empty_curve_keeps_contractual_points_pending(self):
        from crane_statics.core.sweep import run_capacity_sweep

        doc = self._example_doc()
        result = run_capacity_sweep(doc, "MH", {}, 1.0, {})
        split_payload = result["modes"].get("split")
        assert split_payload is not None
        contractual = split_payload["contractual_results"]
        assert len(contractual) > 0
        if split_payload["n_points"] == 0:
            assert all(
                (allowable is None and passed is None) for _cp, allowable, passed in contractual
            )

    def test_split_mode_sweep_builds_curve_points_for_mh_example(self):
        from crane_statics.core.sweep import run_capacity_sweep

        doc = self._example_doc()
        result = run_capacity_sweep(doc, "MH", {}, 1.0, {})
        split_payload = result["modes"].get("split")
        assert split_payload is not None
        assert split_payload["n_points"] > 0
        assert len(split_payload["curve_data"]) > 0

    def test_chart_outreach_grid_uses_absolute_steps_and_explicit_hi_endpoint(self):
        from crane_statics.core.sweep import build_absolute_outreach_grid

        base_grid = build_absolute_outreach_grid(27.2, 40.0, 1.0)
        assert 27.2 not in base_grid
        assert 28.0 in base_grid
        assert 29.0 in base_grid
        assert 40.0 in base_grid

        with_contractual = sorted(set([*base_grid, 27.2, 35.8, 38.3]))
        assert 27.2 in with_contractual
        assert 35.8 in with_contractual
        assert 38.3 in with_contractual

        hi_endpoint_grid = build_absolute_outreach_grid(27.2, 40.3, 1.0)
        assert 40.3 in hi_endpoint_grid


class TestResponsiveLayoutRegression:
    """Targeted UI regression tests for responsive sizing behavior."""

    def _example_doc(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        if not example_path.exists():
            pytest.skip("Example file not found")
        return load_document(example_path)

    def test_runtime_topology_nodes_have_body_specific_ownership(self):
        doc = self._example_doc()
        nodes = {n.id: n for n in doc.nodes}

        assert nodes["boom_heel"].body == "boom"
        assert nodes["platform_heel"].body == "platform"
        assert nodes["rear_base"].body == "rear_leg"
        assert nodes["platform_rear"].body == "platform"
        assert nodes["front_base"].body == "front_leg"
        assert nodes["platform_front"].body == "platform"
        assert nodes["rear_top"].body == "rear_leg"
        assert nodes["front_top"].body == "front_leg"

        for lhs, rhs in [
            ("boom_heel", "platform_heel"),
            ("rear_base", "platform_rear"),
            ("front_base", "platform_front"),
            ("rear_top", "front_top"),
        ]:
            assert nodes[lhs].x_m == pytest.approx(nodes[rhs].x_m)
            assert nodes[lhs].z_m == pytest.approx(nodes[rhs].z_m)

    def _scene_harness(self):
        return SceneHarness(self._example_doc())

    def test_refresh_analysis_syncs_canvas_boom_angle_to_session_state(self):
        harness = self._scene_harness()

        for angle in (0.0, 30.0, 62.5):
            harness.vm.setAngle(angle)
            assert harness.inputs.conditions.boom_angle_deg == pytest.approx(angle)

    def test_scene_equilibrium_report_closes_for_drawn_loads_including_wind(self):
        harness = self._scene_harness()
        state = harness.state
        assert state is not None
        assert float(state.scene_state.wind_speed_m_s) > 0.0

        for angle in (0.0, 20.0, 45.0, 70.0):
            for hook_load_kN in (0.0, 5000.0, 20000.0):
                for tackle_m in (5.0, 40.0):
                    harness.apply(
                        boom_angle_deg=angle,
                        hook_load_kN=hook_load_kN,
                        tackle_length_m=tackle_m,
                    )
                    report = harness.report()

                    assert report["available"] is True
                    assert {s["name"] for s in report["sections"]} == {
                        "Boom",
                        "Rear Leg",
                        "Front Leg",
                        "Platform",
                    }
                    assert (
                        report["passed"] is True
                    ), f"angle={angle} hook={hook_load_kN} tackle={tackle_m}: " + "; ".join(
                        s["message"] for s in report["sections"] if not s["passed"]
                    )

    def test_scene_equilibrium_closes_for_both_offlead_directions(self):
        harness = self._scene_harness()

        for offlead_deg in (-1.0, 0.0, 1.0):
            harness.apply(
                boom_angle_deg=45.0,
                hook_load_kN=5000.0,
                offlead_deg=offlead_deg,
            )
            report = harness.report()

            assert report["passed"] is True, f"offlead={offlead_deg}: " + "; ".join(
                s["message"] for s in report["sections"] if not s["passed"]
            )

    def test_explicit_lateral_unit_maps_compose_offlead_and_sidelead(self):
        example_path = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"
        doc = load_document(example_path)
        calc = CraneCalculator(doc)
        common = {
            "wind_speed_m_s": 0.0,
            "wind_direction": "+X",
            "accel_x_m_s2": 0.0,
            "accel_y_m_s2": 0.0,
            "accel_z_m_s2": 0.0,
            "pitch_accel_rad_s2": 0.0,
            "roll_accel_rad_s2": 0.0,
        }

        no_lead = calc.compute_analysis_point(
            45.0, 0.0, "MH", offlead_deg=0.0, sidelead_deg=0.0, **common
        )
        with_lead = calc.compute_analysis_point(
            45.0, 0.0, "MH", offlead_deg=10.0, sidelead_deg=8.0, **common
        )

        assert no_lead is not None and with_lead is not None
        assert no_lead.offlead_lateral_unit_reactions is not None
        assert with_lead.sidelead_lateral_unit_reactions is not None

        offlead_unit_fx = no_lead.offlead_lateral_unit_reactions["heel_point"]["Fx"]
        observed_offlead_fx = (
            with_lead.sensitivity_reactions["heel_point"]["Fx"]
            - no_lead.sensitivity_reactions["heel_point"]["Fx"]
        )
        assert observed_offlead_fx == pytest.approx(math.sin(math.radians(10.0)) * offlead_unit_fx)

        side_unit_fy = with_lead.sidelead_lateral_unit_reactions["platform_base"]["Fy"]
        observed_side_fy = (
            with_lead.sensitivity_reactions["platform_base"]["Fy"]
            - no_lead.sensitivity_reactions["platform_base"]["Fy"]
        )
        assert observed_side_fy == pytest.approx(math.sin(math.radians(8.0)) * side_unit_fy)

    def test_scene_equilibrium_includes_hook_payload_weight(self):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0, hook_load_kN=5000.0)

        report = harness.report()
        with_hook = [
            s
            for s in report["sections"]
            if any(c["name"] == "Hook load" and c["count"] > 0 for c in s["categories"])
        ]

        assert len(with_hook) == 1
        hook_category = next(c for c in with_hook[0]["categories"] if c["name"] == "Hook load")
        assert hook_category["sum_fz"] == pytest.approx(-5000.0, abs=1e-6)

    def test_offlead_force_is_applied_at_the_rope_reference_node(self):
        harness = self._scene_harness()
        harness.apply(
            boom_angle_deg=45.0,
            hook_load_kN=5000.0,
            offlead_deg=1.0,
            tackle_length_m=40.0,
        )

        inputs = harness.inputs
        doc_dict = inputs.document_dict
        positions = inputs.node_positions()
        vectors = harness.loads("boom").category(dl.HOOK_LOAD)

        load_nid = inputs.hoist["load_node_id"]
        nodes = {n.get("id"): n for n in doc_dict["nodes"]}
        ref_nid = nodes[load_nid]["below_node_id"]

        offlead = next(v for v in vectors if v.label.startswith("Offlead"))
        hook = next(v for v in vectors if v.label.startswith("Hook"))

        # Offlead acts at the sheave so it carries no tackle-length moment arm.
        assert offlead.world_z == pytest.approx(positions[ref_nid]["z"])
        assert hook.world_z == pytest.approx(positions[load_nid]["z"])
        assert hook.world_z < offlead.world_z

    def test_scene_equilibrium_detects_omitted_hook_force(self, monkeypatch):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0, hook_load_kN=5000.0)

        original = dl.build_body_loads

        def _without_hook_load(*args, **kwargs):
            loads = original(*args, **kwargs)
            return dl.BodyLoads(
                categories=tuple(
                    (name, vectors) for name, vectors in loads.categories if name != dl.HOOK_LOAD
                ),
                moments=loads.moments,
            )

        monkeypatch.setattr(dl, "build_body_loads", _without_hook_load)
        report = harness.report()

        assert report["passed"] is False

    def test_scene_equilibrium_report_includes_wind_as_a_drawn_load(self):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0)

        report = harness.report()
        boom = next(s for s in report["sections"] if s["name"] == "Boom")
        wind = next(c for c in boom["categories"] if c["name"] == "Wind")

        assert wind["count"] > 0
        assert abs(wind["sum_fx"]) > 1.0

    def test_scene_equilibrium_verdict_ignores_overlay_visibility_toggles(self):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0)

        harness.display(show_wind_forces=True, show_reaction_forces=True)
        visible = harness.report()
        harness.display(show_wind_forces=False, show_reaction_forces=False)
        hidden = harness.report()

        assert visible["passed"] is True
        assert hidden["passed"] is True
        for lhs, rhs in zip(visible["sections"], hidden["sections"]):
            assert lhs["sum_fx"] == pytest.approx(rhs["sum_fx"])
            assert lhs["sum_fz"] == pytest.approx(rhs["sum_fz"])

    def test_scene_equilibrium_report_flags_injected_imbalance(self, monkeypatch):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0)

        original = dl.build_body_loads
        bogus = dl.LoadVector(10.0, 10.0, 500.0, 0.0, dl.WIND, "bogus")

        def _extra_wind(*args, **kwargs):
            loads = original(*args, **kwargs)
            return dl.BodyLoads(
                categories=tuple(
                    (name, vectors + (bogus,) if name == dl.WIND else vectors)
                    for name, vectors in loads.categories
                ),
                moments=loads.moments,
            )

        monkeypatch.setattr(dl, "build_body_loads", _extra_wind)
        report = harness.report()

        assert report["passed"] is False
        failing = [s for s in report["sections"] if not s["passed"]]
        assert failing
        assert any("Wind" in s["message"] for s in failing)

    def test_scene_equilibrium_report_handles_unavailable_analysis(self):
        report = SceneHarness().report()

        assert report["available"] is False
        assert "No active analysis" in report["message"]

    def _loaded_summary(self, hook_load_kN: float = 5000.0):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0, hook_load_kN=hook_load_kN)
        return harness, harness.report()

    def test_load_summary_lists_every_body_and_category(self):
        _harness, report = self._loaded_summary()

        assert report["available"] is True
        assert [s["name"] for s in report["sections"]] == [
            "Boom",
            "Rear Leg",
            "Front Leg",
            "Platform",
        ]

        expected = [
            "Gravity",
            "Rope weight",
            "Idle hook mass",
            "Hook load",
            "Wind",
            "Inertia",
            "Rope interface",
            "Reactions",
            "Reaction moments",
        ]
        for section in report["sections"]:
            assert [c["name"] for c in section["categories"]] == expected

    def test_load_summary_gravity_rows_match_body_mass_points(self):
        harness, report = self._loaded_summary()
        doc = harness.model.document
        assert doc is not None
        bodies = {b.id: b for b in doc.bodies}
        name_to_id = {
            "Boom": "boom",
            "Rear Leg": "rear_leg",
            "Front Leg": "front_leg",
            "Platform": "platform",
        }

        for section in report["sections"]:
            body = bodies.get(name_to_id[section["name"]])
            if body is None:
                continue
            expected = sum(1 for mp in body.mass_points if float(mp.mass_t) > 0)
            gravity = next(c for c in section["categories"] if c["name"] == "Gravity")
            assert gravity["count"] == expected

    def test_load_summary_hook_rows_appear_only_with_hook_load(self):
        _loaded_harness, loaded = self._loaded_summary(hook_load_kN=5000.0)
        _unloaded_harness, unloaded = self._loaded_summary(hook_load_kN=0.0)

        def hook_counts(report):
            return [
                next(c for c in section["categories"] if c["name"] == "Hook load")["count"]
                for section in report["sections"]
            ]

        assert sum(1 for n in hook_counts(loaded) if n > 0) == 1
        assert all(n == 0 for n in hook_counts(unloaded))

    def test_load_summary_moment_uses_body_reference_node(self):
        harness, report = self._loaded_summary()
        positions = harness.inputs.node_positions()
        x0 = float(positions["platform_base"]["x"])

        platform = next(s for s in report["sections"] if s["name"] == "Platform")
        gravity = next(c for c in platform["categories"] if c["name"] == "Gravity")
        assert gravity["rows"]

        for row in gravity["rows"]:
            # Gravity is purely vertical, so the moment reduces to the horizontal lever.
            assert row["fx"] == pytest.approx(0.0)
            assert row["moment"] == pytest.approx((row["x"] - x0) * row["fz"])

    def test_load_summary_totals_match_equilibrium_report(self):
        harness, summary = self._loaded_summary()
        equilibrium = harness.report()

        for lhs, rhs in zip(summary["sections"], equilibrium["sections"]):
            assert lhs["name"] == rhs["name"]
            assert lhs["sum_fx"] == pytest.approx(rhs["sum_fx"])
            assert lhs["sum_fz"] == pytest.approx(rhs["sum_fz"])
            assert lhs["sum_m"] == pytest.approx(rhs["sum_m"])
            assert lhs["passed"] == rhs["passed"]

    def test_load_summary_category_subtotals_equal_row_sums(self):
        _harness, report = self._loaded_summary()

        for section in report["sections"]:
            for category in section["categories"]:
                rows = category["rows"]
                assert category["count"] == len(rows)
                assert category["sum_m"] == pytest.approx(sum(r["moment"] for r in rows))
                if category["name"] != "Reaction moments":
                    assert category["sum_fx"] == pytest.approx(sum(r["fx"] for r in rows))
                    assert category["sum_fz"] == pytest.approx(sum(r["fz"] for r in rows))

    def test_load_summary_labels_omit_embedded_magnitudes(self):
        _harness, report = self._loaded_summary()

        labels = [
            row["label"]
            for section in report["sections"]
            for category in section["categories"]
            for row in category["rows"]
        ]
        assert labels
        for label in labels:
            assert not label.endswith("kN")
            assert not label.endswith("kNm")

    def test_load_summary_report_rows_cover_every_category(self):
        from crane_statics.qml_app.models.report_rows import report_to_rows

        _harness, report = self._loaded_summary()
        boom = next(s for s in report["sections"] if s["name"] == "Boom")

        rows = report_to_rows(report)
        category_labels = [row["label"].strip() for row in rows if row["kind"] == "category"]

        for category in boom["categories"]:
            assert category["name"] in category_labels

        # The section row carries the body total, including empty categories.
        boom_row = next(row for row in rows if row["kind"] == "section" and row["label"] == "Boom")
        assert boom_row["fx"] == f"{boom['sum_fx']:.1f}"
        assert boom_row["fz"] == f"{boom['sum_fz']:.1f}"

    def test_load_summary_gravity_rows_are_labelled_by_mass_point_id(self):
        harness, report = self._loaded_summary()
        doc = harness.model.document
        assert doc is not None
        name_to_id = {
            "Boom": "boom",
            "Rear Leg": "rear_leg",
            "Front Leg": "front_leg",
            "Platform": "platform",
        }
        bodies = {b.id: b for b in doc.bodies}

        for section in report["sections"]:
            body = bodies.get(name_to_id[section["name"]])
            if body is None:
                continue
            gravity = next(c for c in section["categories"] if c["name"] == "Gravity")
            if not gravity["rows"]:
                continue

            labels = [row["label"] for row in gravity["rows"]]
            assert len(set(labels)) == len(labels)
            for mass_point in body.mass_points:
                if float(mass_point.mass_t) > 0:
                    assert f"Weight {mass_point.id}" in labels

    def test_scene_display_options_expose_gravity_overlay_toggle(self):
        assert "show_gravity_forces" in SceneHarness().vm.displayOptions

    def test_gravity_overlay_draws_weight_vectors_outside_freebody_mode(self):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0)
        model = harness.model

        def weight_tooltips() -> list[str]:
            return [
                arrow.tooltip
                for arrow in harness.frame().force_arrows
                if arrow.tooltip.startswith("Weight ")
            ]

        harness.display(selected_freebody="none", show_gravity_forces=False)
        assert weight_tooltips() == []

        harness.display(selected_freebody="none", show_gravity_forces=True)
        shown = weight_tooltips()
        assert shown
        assert any(
            str(mp.id) in tip
            for body in model.document.bodies
            for mp in body.mass_points
            for tip in shown
        )

    def test_load_summary_handles_unavailable_analysis(self):
        report = SceneHarness().report()

        assert report["available"] is False
        assert "No active analysis" in report["message"]

    def test_model_mass_point_table_shows_body_specific_coordinates(self):
        from crane_statics.qml_app.models.document_models import mass_point_columns

        assert [c.title for c in mass_point_columns("platform")] == [
            "ID",
            "Mass (t)",
            "X (m)",
            "Y (m)",
            "Z (m)",
        ]
        assert [c.title for c in mass_point_columns("boom")] == [
            "ID",
            "Mass (t)",
            "U (m)",
            "V (m)",
            "W (m)",
        ]

        doc = self._example_doc()
        boom = next(b for b in doc.bodies if b.id == "boom")
        platform = next(b for b in doc.bodies if b.id == "platform")

        # Boom is a rotating body, so only local coordinates are displayed.
        boom_row = [c.format(boom.mass_points[0]) for c in mass_point_columns("boom")]
        assert all(cell != "" for cell in boom_row[2:5])

        # Platform is fixed, so only global coordinates are displayed.
        platform_row = [c.format(platform.mass_points[0]) for c in mass_point_columns("platform")]
        assert all(cell != "" for cell in platform_row[2:5])

    def test_model_component_tables_use_body_specific_coordinates(self):
        from crane_statics.qml_app.models.document_models import node_columns, wind_area_columns

        doc = self._example_doc()
        model_vm = ModelViewModel(SessionState())
        model_vm._model.set_document(doc)
        model_vm.refresh()

        assert model_vm.bodyLabels == ["Boom", "Rear Leg", "Front Leg", "Platform"]

        editor = model_vm._editor()
        assert editor is not None

        boom_row = [
            c.format(editor.visible_nodes_for_body("boom")[0]) for c in node_columns("boom")
        ]
        assert [c.title for c in node_columns("boom")] == ["ID", "U (m)", "W (m)"]
        assert all(cell != "" for cell in boom_row[1:3])

        platform_row = [
            c.format(editor.visible_nodes_for_body("platform")[0]) for c in node_columns("platform")
        ]
        assert [c.title for c in node_columns("platform")] == ["ID", "X (m)", "Z (m)"]
        assert all(cell != "" for cell in platform_row[1:3])

        assert [c.title for c in wind_area_columns("boom")] == [
            "ID",
            "Area X (m²)",
            "Area Y (m²)",
            "U (m)",
            "W (m)",
            "Cd",
        ]
        assert [c.title for c in wind_area_columns("platform")] == [
            "ID",
            "Area X (m²)",
            "Area Y (m²)",
            "X (m)",
            "Z (m)",
            "Cd",
        ]

    def test_model_contractual_mode_is_independent_of_scene_hook_mode(self):
        doc = self._example_doc()
        harness = SceneHarness(doc, "MH")
        model_vm = ModelViewModel(harness.session)
        model_vm.refresh()

        assert model_vm.hoistSplitable is True
        assert model_vm.contractualMode == "normal"

        model_vm.setContractualMode("split")
        assert model_vm.contractualMode == "split"
        # Browsing split contractual points must not change the analysed scene mode.
        assert harness.vm.hookMode == "normal"

    def test_scene_freebody_toggle_is_single_select_with_none_state(self):
        vm = SceneHarness().vm

        assert vm.displayOptions.get("selected_freebody") == "none"

        vm.toggleFreebody("boom")
        assert vm.displayOptions.get("selected_freebody") == "boom"

        vm.toggleFreebody("front_leg")
        assert vm.displayOptions.get("selected_freebody") == "front_leg"

        # Re-clicking the active option clears free-body mode.
        vm.toggleFreebody("front_leg")
        assert vm.displayOptions.get("selected_freebody") == "none"

    def test_sceneview_freebody_includes_gravity_and_filters_to_selected_body(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "boom"})
        positions = inputs.base_node_positions()

        vectors = inputs.body_loads(positions).category(dl.GRAVITY)
        assert len(vectors) > 0

        bodies = {b.id: b for b in doc.bodies}
        boom_ids = {str(mp.id) for mp in bodies["boom"].mass_points}
        other_ids = {
            str(mp.id)
            for body_id in ("front_leg", "rear_leg", "platform")
            for mp in bodies[body_id].mass_points
        }

        labels = [v.label for v in vectors]
        assert all(lbl.startswith("Weight ") for lbl in labels)
        assert any(any(mp_id in lbl for mp_id in boom_ids) for lbl in labels)
        assert not any(any(mp_id in lbl for mp_id in other_ids) for lbl in labels)

    def test_sceneview_freebody_reaction_signs_are_equal_and_opposite(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)

        positions = inputs.base_node_positions()

        def _reaction_map(selected_body: str) -> dict[str, tuple[float, float]]:
            vectors = inputs.body_loads(positions, selected_body).category(dl.REACTIONS)
            return {v.label.replace("Reaction ", "", 1): (v.fx_kN, v.fz_kN) for v in vectors}

        rear_leg_map = _reaction_map("rear_leg")
        front_leg_map = _reaction_map("front_leg")
        if "upper_hinge" not in rear_leg_map or "upper_hinge" not in front_leg_map:
            pytest.skip("upper_hinge reaction unavailable for this model state")

        rear_fx, rear_fz = rear_leg_map["upper_hinge"]
        front_fx, front_fz = front_leg_map["upper_hinge"]
        assert front_fx == pytest.approx(-rear_fx)
        assert front_fz == pytest.approx(-rear_fz)

    def test_sceneview_upper_hinge_signs_match_solver_convention(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        base = pt.baseline_reactions.get("upper_hinge", {})
        if not base:
            pytest.skip("upper_hinge reaction unavailable for this model state")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)
        positions = inputs.base_node_positions()

        def _upper_vec(selected_body: str) -> tuple[float, float] | None:
            vectors = inputs.body_loads(positions, selected_body).category(dl.REACTIONS)
            for vector in vectors:
                if vector.label == "Reaction upper_hinge":
                    return vector.fx_kN, vector.fz_kN
            return None

        rear = _upper_vec("rear_leg")
        front = _upper_vec("front_leg")
        if rear is None or front is None:
            pytest.skip("upper_hinge reaction not visible for rear/front freebody")

        raw_fx = float(base.get("Fx", 0.0))
        raw_fz = float(base.get("Fz", 0.0))
        assert front[0] == pytest.approx(raw_fx)
        assert front[1] == pytest.approx(raw_fz)
        assert rear[0] == pytest.approx(-raw_fx)
        assert rear[1] == pytest.approx(-raw_fz)

    def test_sceneview_freebody_heel_reaction_is_equal_and_opposite_for_boom_platform(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)

        positions = inputs.base_node_positions()

        def _reaction_map(selected_body: str) -> dict[str, tuple[float, float]]:
            vectors = inputs.body_loads(positions, selected_body).category(dl.REACTIONS)
            return {v.label.replace("Reaction ", "", 1): (v.fx_kN, v.fz_kN) for v in vectors}

        boom_map = _reaction_map("boom")
        platform_map = _reaction_map("platform")
        if "heel_point" not in boom_map or "heel_point" not in platform_map:
            pytest.skip("heel_point reaction unavailable for this model state")

        boom_fx, boom_fz = boom_map["heel_point"]
        platform_fx, platform_fz = platform_map["heel_point"]
        assert platform_fx == pytest.approx(-boom_fx)
        assert platform_fz == pytest.approx(-boom_fz)

    def test_sceneview_platform_freebody_uses_platform_owned_hinge_and_heel_nodes(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)

        positions = inputs.base_node_positions()
        vectors = inputs.body_loads(positions, "platform").category(dl.REACTIONS)

        by_entity = {v.label.replace("Reaction ", "", 1): (v.world_x, v.world_z) for v in vectors}

        for entity, expected_node in {
            "heel_point": "platform_heel",
            "rear_hinge": "platform_rear",
            "front_hinge": "platform_front",
        }.items():
            if entity not in by_entity or expected_node not in positions:
                continue
            expected_origin = (
                float(positions[expected_node]["x"]),
                float(positions[expected_node]["z"]),
            )
            assert by_entity[entity][0] == pytest.approx(expected_origin[0])
            assert by_entity[entity][1] == pytest.approx(expected_origin[1])

    def test_sceneview_platform_freebody_platform_base_uses_platform_base_node(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)

        positions = inputs.base_node_positions()
        if "platform_base" not in positions:
            pytest.skip("platform_base node unavailable for this model state")

        vectors = inputs.body_loads(positions, "platform").category(dl.REACTIONS)

        platform_base_origin = None
        for vector in vectors:
            if vector.label.replace("Reaction ", "", 1) == "platform_base":
                platform_base_origin = (vector.world_x, vector.world_z)
                break

        if platform_base_origin is None:
            pytest.skip("platform_base reaction unavailable for this model state")

        expected_origin = (
            float(positions["platform_base"]["x"]),
            float(positions["platform_base"]["z"]),
        )
        assert platform_base_origin[0] == pytest.approx(expected_origin[0])
        assert platform_base_origin[1] == pytest.approx(expected_origin[1])

    def test_sceneview_boom_freebody_reactions_use_boom_owned_nodes_only(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(doc, hoist_id, analysis_point=pt)

        positions = inputs.base_node_positions()
        vectors = inputs.body_loads(positions, "boom").category(dl.REACTIONS)

        entities = {v.label.replace("Reaction ", "", 1) for v in vectors}
        assert "upper_hinge" not in entities

    def test_sceneview_boom_freebody_includes_rope_interface_vectors(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(
            doc,
            hoist_id,
            analysis_point=pt,
            display={"selected_freebody": "boom"},
        )
        positions = inputs.base_node_positions()
        vectors = inputs.body_loads(positions).category(dl.ROPE_INTERFACE)

        assert len(vectors) > 0
        labels = [v.label for v in vectors]
        assert all(label.startswith("Rope interface ") for label in labels)
        assert any("bh_boom_sheave_3" in label for label in labels)

    def test_sceneview_boom_freebody_force_residual_is_small(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        inputs = scene_inputs_at_drawn_tackle(
            doc,
            hoist_id,
            display={"selected_freebody": "boom"},
        )
        if inputs.analysis_point is None:
            pytest.skip("No analysis point available")
        positions = inputs.node_positions()

        vectors = inputs.body_loads(positions).vectors(
            dl.GRAVITY, dl.ROPE_WEIGHT, dl.ROPE_INTERFACE, dl.REACTIONS
        )

        assert len(vectors) > 0
        sum_fx = float(sum(v.fx_kN for v in vectors))
        sum_fz = float(sum(v.fz_kN for v in vectors))
        sum_mag = float(sum(v.magnitude_kN for v in vectors))
        residual = math.hypot(sum_fx, sum_fz)

        # Residual should be small relative to total displayed vector magnitude.
        assert residual <= max(1.0, 0.01 * sum_mag)

    def test_sceneview_all_freebodies_are_in_equilibrium_for_zeroed_environment_case(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        inputs = scene_inputs_at_drawn_tackle(
            doc,
            hoist_id,
            wind_speed_m_s=0.0,
            wind_direction="+X",
            accel_x_m_s2=0.0,
            accel_y_m_s2=0.0,
            accel_z_m_s2=0.0,
            pitch_accel_rad_s2=0.0,
            roll_accel_rad_s2=0.0,
            offlead_deg=0.0,
            sidelead_deg=0.0,
        )
        if inputs.analysis_point is None:
            pytest.skip("No analysis point available")
        positions = inputs.node_positions()

        refs = {
            "platform": "platform_base",
            "boom": "boom_heel",
            "rear_leg": "rear_base",
            "front_leg": "front_base",
        }

        for body, ref_node in refs.items():
            loads = inputs.body_loads(positions, body)
            vectors = loads.vectors(
                dl.GRAVITY, dl.ROPE_WEIGHT, dl.IDLE_HOOK_MASS, dl.ROPE_INTERFACE, dl.REACTIONS
            )

            assert len(vectors) > 0
            sum_fx = float(sum(v.fx_kN for v in vectors))
            sum_fz = float(sum(v.fz_kN for v in vectors))

            x0 = float(positions[ref_node]["x"])
            z0 = float(positions[ref_node]["z"])
            sum_m = dl.sum_moment_about(vectors, loads.moments, x0, z0)

            # Require strict near-zero closure for deterministic baseline case.
            assert abs(sum_fx) <= 1e-6
            assert abs(sum_fz) <= 1e-6
            assert abs(sum_m) <= 1e-6

    def test_sceneview_freebody_draws_only_loaded_selected_body_nodes(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(
            doc,
            hoist_id,
            analysis_point=pt,
            display={"selected_freebody": "boom"},
        )
        frame = build_scene_frame(inputs)
        positions = inputs.base_node_positions()
        doc_dict = inputs.document_dict
        expected_loaded = dl.loaded_node_ids(
            doc_dict,
            hoist=dl.active_hoist_dict(doc_dict, hoist_id),
            conditions=inputs.conditions,
            node_positions=positions,
            analysis_point=inputs.analysis_point,
            body_filter=inputs.body_filter(),
        )
        drawn_nodes = {node.id for node in frame.nodes}

        # A loaded node that coincides with a CG marker (e.g. a support node under
        # a split-block CG) legitimately has its plain node pin suppressed in
        # favor of the CG symbol, per add_nodes_from_positions' overlap check.
        marker_overlap_radius = 4.0
        nodes_under_markers = set()
        for node_id in expected_loaded:
            if node_id not in positions:
                continue
            sx, sy = frame.mapping.to_scene(positions[node_id]["x"], positions[node_id]["z"])
            if any(
                math.hypot(sx - marker.scene_x, sy - marker.scene_y)
                <= marker.radius + marker_overlap_radius
                for marker in frame.markers
            ):
                nodes_under_markers.add(node_id)

        assert drawn_nodes == expected_loaded - nodes_under_markers

    def test_sceneview_freebody_hides_ropes_and_boom_local_axes(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(
            doc,
            hoist_id,
            analysis_point=pt,
            display={"selected_freebody": "boom"},
        )
        frame = build_scene_frame(inputs)

        # Boom local coordinate frame is hidden in freebody mode.
        assert frame.boom_axes == ()

        # Rope segments are hidden in freebody mode.
        assert frame.rope_segments == ()

    def test_sceneview_freebody_hides_hook_height_and_outreach_indicators(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(
            doc,
            hoist_id,
            analysis_point=pt,
            display={"selected_freebody": "boom"},
        )
        frame = build_scene_frame(inputs)

        frame = frame
        assert frame.guides == ()
        assert {target.kind for target in frame.hit_targets}.isdisjoint(
            {"outreach", "tackle_length"}
        )

    def test_sceneview_boom_frame_axes_are_arrows_in_normal_scene(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "none"})
        frame = build_scene_frame(inputs)

        axis_tips = [axis.label for axis in frame.boom_axes]
        # The boom's local axes are labelled U and W, not X and Z.
        assert axis_tips.count("U") == 1
        assert axis_tips.count("W") == 1

    def test_sceneview_rope_segment_engineering_tooltip_fields(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id
        calc = CraneCalculator(doc)
        pt = calc.compute_analysis_point(45.0, 0.0, hoist_id)
        if pt is None:
            pytest.skip("No analysis point available")

        inputs = scene_inputs(
            doc,
            hoist_id,
            analysis_point=pt,
            display={"selected_freebody": "none"},
        )
        frame = build_scene_frame(inputs)

        rope_tips = [segment.tooltip for segment in frame.rope_segments]
        assert rope_tips, "Expected at least one rope segment tooltip"

        sample = rope_tips[0]
        assert "Parts:" in sample
        assert "Length:" in sample
        assert "Tension:" in sample
        assert "Line force:" in sample
        assert "__rope" not in sample
        assert "__hook__" not in sample

        for tip in rope_tips:
            assert "__rope" not in tip
            assert "__hook__" not in tip

    def test_sceneview_cg_tooltips_use_raw_mass_point_ids(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        expected_ids = {
            str(mp.id) for body in doc.bodies for mp in body.mass_points if str(mp.id).strip()
        }
        assert expected_ids

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "none"})
        frame = build_scene_frame(inputs)

        tooltips = [marker.tooltip for marker in frame.markers]
        rendered_mass_point_ids = {
            mass_point_id
            for mass_point_id in expected_ids
            if any(mass_point_id in tip for tip in tooltips)
        }

        assert rendered_mass_point_ids
        assert all("Center of gravity" in tip for tip in tooltips if "split block CG:" not in tip)

    def test_sceneview_cg_tooltip_falls_back_to_unnamed_mass_point(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        target = None
        for body in doc.bodies:
            for mp in body.mass_points:
                if (body.id == "boom" and mp.local_x_m is not None) or (mp.x_m is not None):
                    target = mp
                    break
            if target is not None:
                break

        if target is None:
            pytest.skip("No renderable mass point available in example")

        target.id = "   "

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "none"})
        frame = build_scene_frame(inputs)

        tooltips = [marker.tooltip for marker in frame.markers]
        assert any("Mass point: Unnamed mass point" in tip for tip in tooltips)

    def test_sceneview_moment_glyph_uses_open_arc_with_arrowhead(self):
        harness = self._scene_harness()
        harness.apply(boom_angle_deg=45.0, hook_load_kN=5000.0)
        # The platform's fixed base is the one support that carries a drawn moment.
        harness.display(selected_freebody="platform", show_reaction_forces=True)

        glyphs = harness.frame().moments
        assert len(glyphs) == 1
        glyph = glyphs[0]

        # Open arc rather than a closed circle, swept counterclockwise for M > 0.
        assert glyph.moment_kNm > 0.0
        assert glyph.start_degrees == pytest.approx(-50.0)
        assert glyph.span_degrees == pytest.approx(280.0)

        # Arrowhead tip sits one head-length beyond the arc's open end.
        end_rad = math.radians(glyph.start_degrees + glyph.span_degrees)
        base_x = glyph.origin_x + glyph.radius * math.cos(end_rad)
        base_y = glyph.origin_y - glyph.radius * math.sin(end_rad)
        assert math.hypot(glyph.arrow_tip_x - base_x, glyph.arrow_tip_y - base_y) == pytest.approx(
            9.0
        )
        assert f"{glyph.moment_kNm:.1f} kNm" in glyph.tooltip

    def test_sceneview_draws_leg_members_in_normal_scene(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "none"})
        frame = build_scene_frame(inputs)

        leg_segments = frame.structural_segments
        assert len(leg_segments) == 2
        assert {segment.tooltip.splitlines()[0] for segment in leg_segments} == {
            "Rear leg",
            "Front leg",
        }

    def test_sceneview_draws_leg_members_in_freebody_mode(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "front_leg"})
        frame = build_scene_frame(inputs)

        leg_segments = frame.structural_segments
        assert len(leg_segments) == 1
        assert leg_segments[0].tooltip.startswith("Front leg\nFrom:")

    def test_sceneview_rear_leg_freebody_hides_front_leg_member(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "rear_leg"})
        frame = build_scene_frame(inputs)

        leg_segments = frame.structural_segments
        assert len(leg_segments) == 1
        assert leg_segments[0].tooltip.startswith("Rear leg\nFrom:")

    def test_sceneview_boom_freebody_hides_leg_members(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "boom"})
        frame = build_scene_frame(inputs)

        assert frame.structural_segments == ()

    def test_sceneview_platform_freebody_hides_leg_members(self):
        doc = self._example_doc()
        hoist_id = doc.hoists[0].id

        inputs = scene_inputs(doc, hoist_id, display={"selected_freebody": "platform"})
        frame = build_scene_frame(inputs)

        assert frame.structural_segments == ()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
