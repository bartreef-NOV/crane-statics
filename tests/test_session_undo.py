"""SessionModel undo/redo: document, limits, Scene state, dirty flag and view-model extras."""

from pathlib import Path

import pytest

from crane_statics.core.io import load_document
from crane_statics.core.session_model import SessionModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture
def session():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    model = SessionModel()
    model.set_document(load_document(EXAMPLE), EXAMPLE)
    return model


def _wind(model: SessionModel) -> float:
    assert model.document is not None
    return model.document.environment.max_wind_speed_m_s


def _edit_wind(model: SessionModel, value: float) -> None:
    assert model.document is not None
    model.document.environment.max_wind_speed_m_s = value
    model.mark_content_changed()


def test_new_session_has_nothing_to_undo(session):
    assert not session.can_undo and not session.can_redo
    assert session.undo() is False and session.redo() is False


def test_undo_redo_document_edit(session):
    original = _wind(session)
    _edit_wind(session, original + 5.0)
    _edit_wind(session, original + 9.0)

    assert session.undo()
    assert _wind(session) == original + 5.0
    assert session.undo()
    assert _wind(session) == original
    assert not session.can_undo
    assert session.redo() and session.redo()
    assert _wind(session) == original + 9.0
    assert not session.can_redo


def test_undo_does_not_alias_snapshots(session):
    original = _wind(session)
    _edit_wind(session, original + 5.0)
    session.undo()
    _edit_wind(session, original + 7.0)  # mutates the restored copy
    session.undo()
    assert _wind(session) == original
    session.redo()
    assert _wind(session) == original + 7.0


def test_dirty_follows_saved_state(session):
    original = _wind(session)
    assert not session.dirty
    _edit_wind(session, original + 1.0)
    assert session.dirty
    session.undo()
    assert not session.dirty
    session.redo()
    assert session.dirty
    session.mark_saved()
    assert not session.dirty
    _edit_wind(session, original + 2.0)
    session.undo()
    assert not session.dirty
    session.undo()
    assert session.dirty


def test_scene_edits_undo_and_coalesce(session):
    state = session.get_active_hoist_state()
    assert state is not None
    start = state.scene_state.boom_angle_deg
    for angle in (start + 1.0, start + 2.0, start + 3.0):
        state.scene_state.boom_angle_deg = angle
        session.mark_content_changed(scope="scene", key="angle")

    assert session.undo()
    restored = session.get_active_hoist_state()
    assert restored is not None
    assert restored.scene_state.boom_angle_deg == start
    assert not session.can_undo


def test_scene_scope_shares_document_snapshot(session):
    state = session.get_active_hoist_state()
    assert state is not None
    state.scene_state.boom_angle_deg += 1.0
    session.mark_content_changed(scope="scene")
    assert session.history.current is not None
    first = session.history.current.document
    state.scene_state.boom_angle_deg += 1.0
    session.mark_content_changed(scope="scene")
    assert session.history.current.document is first


def test_design_limit_edit_undo(session):
    limit = session.design_limits[0]
    before = (limit.max_kN, limit.enabled)
    limit.max_kN = 123.0
    limit.enabled = True
    session.mark_content_changed()

    session.undo()
    restored = session.design_limits_by_id[limit.id]
    assert (restored.max_kN, restored.enabled) == before
    assert session.design_limits[0] is restored


def test_restore_announces_document_change_and_history(session):
    events = []
    session.subscribe("document_changed", lambda doc: events.append("document_changed"))
    session.subscribe("history_changed", lambda: events.append("history_changed"))
    _edit_wind(session, _wind(session) + 1.0)
    events.clear()

    session.undo()

    assert events == ["document_changed", "history_changed"]


def test_marks_made_while_restoring_are_ignored(session):
    _edit_wind(session, _wind(session) + 1.0)
    session.subscribe("document_changed", lambda doc: session.mark_content_changed())

    session.undo()

    assert not session.can_undo
    assert session.can_redo
    assert not session.dirty


def test_extras_are_captured_and_restored(session):
    holder = {"value": 1}
    session.register_history_extra(
        "holder", lambda: holder["value"], lambda value: holder.update(value=value)
    )
    session.set_document(session.document, session.document_path)  # re-baseline with extra
    holder["value"] = 2
    session.mark_content_changed(scope="scene")

    session.undo()
    assert holder["value"] == 1
    session.redo()
    assert holder["value"] == 2


def test_loading_a_document_resets_history(session):
    _edit_wind(session, _wind(session) + 1.0)
    session.set_document(load_document(EXAMPLE), EXAMPLE)
    assert not session.can_undo and not session.can_redo
    session.set_document(None)
    assert not session.can_undo
    session.mark_content_changed()
    assert not session.can_undo
