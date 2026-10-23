"""Application-shell view model: document lifecycle, dirty state and notifications."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from crane_statics.core.io import (
    DocumentIOError,
    create_default_document,
    load_document,
    save_document,
)
from crane_statics.qml_app.session import SessionState


class AppViewModel(QObject):
    """Owns the session and exposes file actions plus window state to QML."""

    titleChanged = pyqtSignal()
    dirtyChanged = pyqtSignal()
    hasDocumentChanged = pyqtSignal()
    statusTextChanged = pyqtSignal()
    currentPathChanged = pyqtSignal()
    documentChanged = pyqtSignal()
    historyChanged = pyqtSignal()
    layoutResetRequested = pyqtSignal()
    notification = pyqtSignal(str, str)

    def __init__(self, session: Optional[SessionState] = None, parent=None):
        super().__init__(parent)
        self.session = session if session is not None else SessionState()
        self._model = self.session.model
        self._status_text = "No document loaded"
        self.session.dirty_changed.connect(self._on_dirty_changed)
        self.session.notification.connect(self.notification)
        self._model.subscribe("history_changed", self.historyChanged.emit)

    def _on_dirty_changed(self, _dirty: bool) -> None:
        self.dirtyChanged.emit()
        self.titleChanged.emit()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=titleChanged)
    def title(self) -> str:
        if self._model.document is None:
            return "Crane Statics"
        name = self._model.document_path.name if self._model.document_path else "Untitled"
        return f"Crane Statics - {name}{' ●' if self._model.dirty else ''}"

    @pyqtProperty(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        return bool(self._model.dirty)

    @pyqtProperty(bool, notify=hasDocumentChanged)
    def hasDocument(self) -> bool:
        return self._model.document is not None

    @pyqtProperty(bool, notify=historyChanged)
    def canUndo(self) -> bool:
        return self._model.can_undo

    @pyqtProperty(bool, notify=historyChanged)
    def canRedo(self) -> bool:
        return self._model.can_redo

    @pyqtProperty(str, notify=currentPathChanged)
    def currentPath(self) -> str:
        return str(self._model.document_path) if self._model.document_path else ""

    @pyqtProperty(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._status_text

    @pyqtSlot(str)
    def setStatusText(self, text: str) -> None:
        if text != self._status_text:
            self._status_text = text
            self.statusTextChanged.emit()

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    @pyqtSlot()
    def newDocument(self) -> None:
        self._apply_document(create_default_document(), None, "New document created")

    @pyqtSlot(QUrl)
    def open(self, url: QUrl) -> None:
        path = Path(url.toLocalFile() if url.isLocalFile() else url.toString())
        try:
            doc = load_document(path)
        except DocumentIOError as exc:
            self.notification.emit(str(exc), "error")
            return
        self._apply_document(doc, path, f"Loaded {path.name}")

    @pyqtSlot(str)
    def openPath(self, path_str: str) -> None:
        self.open(QUrl.fromLocalFile(str(Path(path_str).resolve())))

    @pyqtSlot(result=bool)
    def save(self) -> bool:
        if self._model.document is None:
            self.notification.emit("No document is open.", "warning")
            return False
        if self._model.document_path is None:
            return False
        return self._write(self._model.document_path)

    @pyqtSlot(QUrl, result=bool)
    def saveAs(self, url: QUrl) -> bool:
        if self._model.document is None:
            self.notification.emit("No document is open.", "warning")
            return False
        path = Path(url.toLocalFile() if url.isLocalFile() else url.toString())
        if not path.suffix:
            path = path.with_suffix(".yaml")
        return self._write(path)

    @pyqtSlot()
    def closeDocument(self) -> None:
        self._apply_document(None, None, "No document loaded")
        self.notification.emit("Document closed", "info")

    @pyqtSlot()
    def undo(self) -> None:
        if self._model.undo():
            self.setStatusText("Undo")

    @pyqtSlot()
    def redo(self) -> None:
        if self._model.redo():
            self.setStatusText("Redo")

    @pyqtSlot()
    def resetLayout(self) -> None:
        if self._model.document is not None:
            self._model.add_notification("Layout reset", "info")
            self.layoutResetRequested.emit()

    def _write(self, path: Path) -> bool:
        doc = self._model.document
        if doc is None:
            return False
        try:
            save_document(doc, path)
        except DocumentIOError as exc:
            self.notification.emit(str(exc), "error")
            return False
        self._model.document_path = path
        self._model.mark_saved()
        self.setStatusText(f"Saved {path.name}")
        self.currentPathChanged.emit()
        self.titleChanged.emit()
        return True

    def _apply_document(self, doc, path: Optional[Path], status: str) -> None:
        self._model.set_document(doc, path)
        self.setStatusText(status)
        self.hasDocumentChanged.emit()
        self.currentPathChanged.emit()
        self.titleChanged.emit()
        self.dirtyChanged.emit()
        self.documentChanged.emit()
