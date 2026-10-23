"""EditHistory: stacks, coalescing, depth cap and saved-state tracking."""

import pytest

from crane_statics.core.edit_history import EditHistory


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def history(clock):
    h = EditHistory[str](depth=3, coalesce_window_s=1.0, clock=clock)
    h.reset("a")
    return h


def test_fresh_history_has_nothing_to_undo(history):
    assert not history.can_undo and not history.can_redo
    assert history.undo() is None and history.redo() is None
    assert history.current == "a" and history.is_at_saved


def test_record_undo_redo(history):
    history.record("b")
    history.record("c")
    assert history.undo() == "b"
    assert history.undo() == "a"
    assert history.undo() is None
    assert history.redo() == "b"
    assert history.redo() == "c"
    assert history.redo() is None


def test_record_clears_redo(history):
    history.record("b")
    history.undo()
    history.record("c")
    assert not history.can_redo
    assert history.undo() == "a"


def test_depth_cap_drops_oldest(history):
    for state in "bcde":
        history.record(state)
    assert [history.undo() for _ in range(4)] == ["d", "c", "b", None]


def test_same_key_within_window_merges(history, clock):
    history.record("b", key="slider")
    clock.now = 0.5
    history.record("c", key="slider")
    clock.now = 0.9
    history.record("d", key="slider")
    assert history.undo() == "a"
    assert history.redo() == "d"


def test_key_outside_window_or_different_key_does_not_merge(history, clock):
    history.record("b", key="slider")
    clock.now = 5.0
    history.record("c", key="slider")
    history.record("d", key="other")
    assert history.undo() == "c"
    assert history.undo() == "b"
    assert history.undo() == "a"


def test_undo_breaks_coalescing(history, clock):
    history.record("b", key="slider")
    history.undo()
    history.record("c", key="slider")
    history.record("d", key="slider")
    assert history.undo() == "a"


def test_saved_state_tracking(history):
    history.record("b")
    assert not history.is_at_saved
    history.mark_saved()
    assert history.is_at_saved
    history.record("c")
    assert not history.is_at_saved
    history.undo()
    assert history.is_at_saved
    history.undo()
    assert not history.is_at_saved


def test_saving_mid_gesture_keeps_saved_state_reachable(history, clock):
    history.record("b", key="slider")
    history.mark_saved()
    history.record("c", key="slider")
    assert history.undo() == "b"
    assert history.is_at_saved


def test_reset_to_none_disables_history(history):
    history.reset(None)
    history.record("x")
    assert history.current is None and not history.can_undo and not history.is_at_saved


def test_depth_must_be_positive():
    with pytest.raises(ValueError):
        EditHistory[str](depth=0)
