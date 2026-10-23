"""Bounded undo/redo history of opaque state snapshots (Qt-free)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")

DEFAULT_HISTORY_DEPTH = 100
# Edits with the same key closer together than this merge into one undo step.
DEFAULT_COALESCE_WINDOW_S = 0.6


@dataclass(frozen=True)
class _Entry(Generic[T]):
    token: int
    snapshot: T


class EditHistory(Generic[T]):
    """Undo/redo stacks around a *current* snapshot.

    ``record`` is called after a mutation with a snapshot of the new state; the previous
    current snapshot becomes the undo target. ``undo`` and ``redo`` return the snapshot
    to restore. Each state carries a token so ``is_at_saved`` can tell whether the
    current state is the one passed to ``mark_saved``.
    """

    def __init__(
        self,
        depth: int = DEFAULT_HISTORY_DEPTH,
        coalesce_window_s: float = DEFAULT_COALESCE_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if depth < 1:
            raise ValueError("depth must be >= 1")
        self._depth = depth
        self._window = coalesce_window_s
        self._clock = clock
        self._undo: deque[_Entry[T]] = deque(maxlen=depth)
        self._redo: list[_Entry[T]] = []
        self._current: Optional[_Entry[T]] = None
        self._next_token = 0
        self._saved_token: Optional[int] = None
        self._last_key: Optional[str] = None
        self._last_time = 0.0

    def _new_entry(self, snapshot: T) -> _Entry[T]:
        self._next_token += 1
        return _Entry(self._next_token, snapshot)

    def reset(self, snapshot: Optional[T]) -> None:
        """Drop all history; ``snapshot`` becomes the saved baseline (None = no document)."""
        self._undo.clear()
        self._redo.clear()
        self._last_key = None
        self._current = None if snapshot is None else self._new_entry(snapshot)
        self._saved_token = None if self._current is None else self._current.token

    @property
    def current(self) -> Optional[T]:
        return None if self._current is None else self._current.snapshot

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def is_at_saved(self) -> bool:
        return self._current is not None and self._current.token == self._saved_token

    def mark_saved(self) -> None:
        """The current state is what is on disk; later edits start a new undo step."""
        self._saved_token = None if self._current is None else self._current.token
        self._last_key = None

    def record(self, snapshot: T, key: Optional[str] = None) -> None:
        """Make ``snapshot`` current after an edit, clearing redo."""
        if self._current is None:
            return
        now = self._clock()
        merge = (
            key is not None
            and key == self._last_key
            and now - self._last_time <= self._window
            and bool(self._undo)
        )
        if not merge:
            self._undo.append(self._current)
        self._current = self._new_entry(snapshot)
        self._redo.clear()
        self._last_key = key
        self._last_time = now

    def undo(self) -> Optional[T]:
        if not self._undo or self._current is None:
            return None
        self._redo.append(self._current)
        self._current = self._undo.pop()
        self._last_key = None
        return self._current.snapshot

    def redo(self) -> Optional[T]:
        if not self._redo or self._current is None:
            return None
        self._undo.append(self._current)
        self._current = self._redo.pop()
        self._last_key = None
        return self._current.snapshot
