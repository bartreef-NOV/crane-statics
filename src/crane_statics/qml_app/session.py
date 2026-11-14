"""Qt signal adapter for the pure application session model."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.core.session_model import SessionModel


class SessionState(QObject):
    """The session's change events, as Qt signals.

    This is the whole seam between the pure :class:`SessionModel` and the view
    models: six signals, plus the ``model`` the view models read and write
    directly. It deliberately does not mirror the model's members. A mirror buys
    no encapsulation here -- ``SessionModel``'s state is public and mutable, and
    the view models already write straight through it -- while costing a second
    edit for every session member added. See
    ``docs/adr/0001-session-state-is-the-signal-seam.md``.
    """

    dirty_changed = pyqtSignal(bool)
    document_changed = pyqtSignal(object)
    content_changed = pyqtSignal()
    hoist_selected = pyqtSignal(str)
    design_limits_changed = pyqtSignal(list)
    notification = pyqtSignal(str, str)

    def __init__(
        self, model: Optional[SessionModel] = None, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self.model = model if model is not None else SessionModel()
        for event, signal in (
            ("dirty_changed", self.dirty_changed),
            ("document_changed", self.document_changed),
            ("content_changed", self.content_changed),
            ("hoist_selected", self.hoist_selected),
            ("design_limits_changed", self.design_limits_changed),
            ("notification", self.notification),
        ):
            self.model.subscribe(event, signal.emit)
