"""Scene-only heel and trim: what the Scene solves at without touching the document.

The Scene can try a heel and trim of its own. It follows the Model's design
attitude until edited, and only the Scene's own solve sees the edit: the saved
document, the load chart and auto-set keep reading ``session.document``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.vessel_attitude import VesselAttitude, crane_frame_gravity
from crane_statics.core.io import load_document
from crane_statics.core.scene_attitude import document_dict_with_attitude, document_with_attitude
from crane_statics.core.session_model import SessionModel
from crane_statics.data.authored_models import MAX_VESSEL_TILT_DEG

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


def _tilted(doc, heel_deg: float, trim_deg: float):
    tilted = doc.model_copy(deep=True)
    tilted.environment.vessel_motion.heel_deg = heel_deg
    tilted.environment.vessel_motion.trim_deg = trim_deg
    return tilted


def _session(doc) -> SessionModel:
    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist("MH")
    return session


def _services(session: SessionModel, **scene_state: Any):
    from crane_statics.core.analysis_presenter import AnalysisPresenter
    from crane_statics.core.analysis_services import (
        AnalysisCalculator,
        HoistStateService,
        KinematicsService,
    )

    state = session.get_active_hoist_state()
    assert state is not None
    state.scene_state.boom_angle_deg = 45.0
    state.scene_state.tackle_length_m = 40.0
    for key, value in scene_state.items():
        setattr(state.scene_state, key, value)
    hoist_svc = HoistStateService(session)
    calculator = AnalysisCalculator(session, KinematicsService(session), hoist_svc)
    return calculator, AnalysisPresenter(session, calculator, hoist_svc)


class TestSessionSceneAttitude:
    def test_follows_the_document_until_set(self, document):
        session = _session(_tilted(document, 2.0, -1.0))

        assert session.scene_attitude() == VesselAttitude(2.0, -1.0)
        assert session.scene_attitude_overridden is False

    def test_a_scene_edit_overrides_the_document(self, document):
        session = _session(document)

        session.set_scene_attitude(3.0, 1.0)

        assert session.scene_attitude() == VesselAttitude(3.0, 1.0)
        assert session.document_attitude() == VesselAttitude()
        assert session.scene_attitude_overridden is True

    def test_setting_the_documents_own_attitude_follows_the_document_again(self, document):
        session = _session(_tilted(document, 2.0, 0.0))
        session.set_scene_attitude(3.0, 0.0)

        session.set_scene_attitude(2.0, 0.0)

        assert session.scene_attitude_overridden is False
        session.document.environment.vessel_motion.heel_deg = 4.0
        assert session.scene_attitude() == VesselAttitude(4.0, 0.0)

    def test_a_model_edit_that_matches_the_override_follows_the_model_again(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 0.0)

        session.document.environment.vessel_motion.heel_deg = 3.0
        session.mark_content_changed()

        assert session.scene_attitude_overridden is False
        session.document.environment.vessel_motion.heel_deg = 1.0
        session.mark_content_changed()
        assert session.scene_attitude() == VesselAttitude(1.0, 0.0)

    def test_an_override_ignores_later_model_edits(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 0.0)

        session.document.environment.vessel_motion.heel_deg = 1.0

        assert session.scene_attitude() == VesselAttitude(3.0, 0.0)

    @pytest.mark.parametrize("typed, kept", [(45.0, MAX_VESSEL_TILT_DEG), (-90.0, -30.0)])
    def test_angles_are_clamped_to_the_schema_limit(self, document, typed, kept):
        session = _session(document)

        session.set_scene_attitude(typed, typed)

        assert session.scene_attitude() == VesselAttitude(kept, kept)

    def test_a_non_finite_angle_keeps_the_current_one(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 1.0)

        session.set_scene_attitude(float("nan"), 2.0)

        assert session.scene_attitude() == VesselAttitude(3.0, 2.0)

    def test_reset_returns_to_the_document(self, document):
        session = _session(_tilted(document, 2.0, 0.0))
        session.set_scene_attitude(5.0, 5.0)

        session.reset_scene_attitude()

        assert session.scene_attitude() == VesselAttitude(2.0, 0.0)
        assert session.scene_attitude_overridden is False

    def test_loading_a_document_clears_the_override(self, document):
        session = _session(document)
        session.set_scene_attitude(5.0, 5.0)

        session.set_document(_tilted(document, 1.0, 0.0))

        assert session.scene_attitude() == VesselAttitude(1.0, 0.0)
        assert session.scene_attitude_overridden is False

    def test_no_document_is_level(self):
        session = SessionModel()

        assert session.scene_attitude() == VesselAttitude()
        assert session.scene_document() is None

    def test_a_scene_edit_does_not_dirty_the_document(self, document):
        session = _session(document)
        events: list[str] = []
        session.subscribe("content_changed", lambda: events.append("content"))

        session.set_scene_attitude(3.0, 1.0)

        assert session.dirty is False
        assert events == []


class TestSceneDocument:
    def test_is_the_document_itself_when_not_overridden(self, document):
        session = _session(document)

        assert session.scene_document() is session.document

    def test_carries_the_override_and_leaves_the_document_alone(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 1.0)

        scene_doc = session.scene_document()

        assert scene_doc is not session.document
        assert scene_doc.environment.vessel_motion.heel_deg == 3.0
        assert scene_doc.environment.vessel_motion.trim_deg == 1.0
        assert session.document.environment.vessel_motion.heel_deg == 0.0
        assert session.document.environment.vessel_motion.trim_deg == 0.0
        # Everything but the attitude is shared, not copied.
        assert scene_doc.hoists is session.document.hoists
        assert scene_doc.environment.vessel_motion.accel_x_m_s2 == (
            session.document.environment.vessel_motion.accel_x_m_s2
        )


class TestSceneDocumentDict:
    def test_is_the_dict_itself_when_not_overridden(self, document):
        session = _session(document)
        source = document.model_dump()

        assert session.scene_document_dict(source) is source

    def test_carries_the_override(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 1.0)
        source = document.model_dump()

        scene_dict = session.scene_document_dict(source)

        assert scene_dict["environment"]["vessel_motion"]["heel_deg"] == 3.0
        assert scene_dict["environment"]["vessel_motion"]["trim_deg"] == 1.0
        assert source["environment"]["vessel_motion"]["heel_deg"] == 0.0


class TestAttitudeCopies:
    def test_document_copy_changes_only_the_attitude(self, document):
        copy = document_with_attitude(document, VesselAttitude(2.0, -1.0))

        assert copy.environment.vessel_motion.heel_deg == 2.0
        assert copy.environment.vessel_motion.trim_deg == -1.0
        assert document.environment.vessel_motion.heel_deg == 0.0
        assert copy.nodes is document.nodes

    def test_dict_copy_does_not_mutate_its_input(self, document):
        source = document.model_dump()
        before = source["environment"]["vessel_motion"].copy()

        copy = document_dict_with_attitude(source, VesselAttitude(2.0, -1.0))

        assert copy["environment"]["vessel_motion"]["heel_deg"] == 2.0
        assert copy["environment"]["vessel_motion"]["trim_deg"] == -1.0
        assert source["environment"]["vessel_motion"] == before
        assert copy["nodes"] is source["nodes"]

    def test_dict_copy_tolerates_a_missing_environment(self):
        copy = document_dict_with_attitude({"nodes": []}, VesselAttitude(1.0, 0.0))

        assert copy["environment"]["vessel_motion"] == {"heel_deg": 1.0, "trim_deg": 0.0}


class TestSceneAnalysisUsesTheSceneAttitude:
    def test_the_scene_point_is_solved_at_the_scene_attitude(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 1.0)
        calculator, _ = _services(session, slew_deg=75.0)

        point = calculator.compute_analysis_point()

        assert point is not None
        assert point.crane_gravity == crane_frame_gravity(VesselAttitude(3.0, 1.0), 75.0)

    def test_auto_load_follows_the_scene_attitude(self, document):
        session = _session(document)
        calculator, _ = _services(session, slew_deg=90.0)
        level = calculator.compute_auto_load()

        session.set_scene_attitude(5.0, 0.0)
        heeled = calculator.compute_auto_load()

        assert level is not None and heeled is not None
        assert heeled.max_allowable_load_kN != pytest.approx(level.max_allowable_load_kN)

    def test_contribution_overview_reconstructs_an_overridden_demand(self, document):
        session = _session(document)
        session.set_scene_attitude(3.0, 1.0)
        _, presenter = _services(session, slew_deg=75.0, hook_load_kN=5000.0)
        row = {"kind": "connection", "entity_id": "heel_point", "component": "Fx"}

        overview = presenter.build_load_contribution_overview(row)

        assert overview is not None
        assert "Vessel attitude" in [term["name"] for term in overview["terms"]]
        assert overview["delta_kN"] == pytest.approx(0.0, abs=1e-6)

    def test_contribution_overview_has_no_attitude_term_when_the_scene_levels_it(self, document):
        session = _session(_tilted(document, 3.0, 1.0))
        session.set_scene_attitude(0.0, 0.0)
        _, presenter = _services(session, hook_load_kN=5000.0)
        row = {"kind": "connection", "entity_id": "heel_point", "component": "Fx"}

        overview = presenter.build_load_contribution_overview(row)

        assert overview is not None
        assert "Vessel attitude" not in [term["name"] for term in overview["terms"]]
        assert overview["delta_kN"] == pytest.approx(0.0, abs=1e-6)
