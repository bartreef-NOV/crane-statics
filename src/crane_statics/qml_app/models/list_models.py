"""Generic dictionary-backed list model for QML views."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal

from crane_statics.qml_app.qt_compat import pyqtProperty


class DictListModel(QAbstractListModel):
    """Exposes a list of uniform dicts to QML, one role per declared key."""

    countChanged = pyqtSignal()

    def __init__(self, roles: Sequence[str], parent=None):
        super().__init__(parent)
        self._role_names = list(roles)
        self._roles = {
            Qt.ItemDataRole.UserRole + offset: name.encode()
            for offset, name in enumerate(self._role_names)
        }
        self._rows: list[dict[str, Any]] = []

    def set_rows(self, rows: Sequence[dict[str, Any]]) -> None:
        new_rows = [dict(row) for row in rows]
        if len(new_rows) != len(self._rows):
            self.beginResetModel()
            self._rows = new_rows
            self.endResetModel()
            self.countChanged.emit()
            return
        # Same row count: patch in place so views keep their scroll position.
        changed = [i for i, (old, new) in enumerate(zip(self._rows, new_rows)) if old != new]
        self._rows = new_rows
        if changed:
            self.dataChanged.emit(
                self.index(changed[0], 0),
                self.index(changed[-1], 0),
                list(self._roles),
            )

    def row_at(self, index: int) -> Optional[dict[str, Any]]:
        return self._rows[index] if 0 <= index < len(self._rows) else None

    @pyqtProperty(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.UserRole):
        if not index.isValid():
            return None
        name = self._roles.get(role)
        if name is None:
            return None
        return self._rows[index.row()].get(name.decode())

    def roleNames(self):
        return dict(self._roles)
