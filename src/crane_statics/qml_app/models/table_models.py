"""Generic record-backed table model shared by every document table in QML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtProperty, pyqtSignal


@dataclass(frozen=True)
class Column:
    """One displayed column: a header plus how to read and format a record."""

    title: str
    get: Callable[[Any], Any]
    decimals: Optional[int] = None

    def format(self, record: Any) -> str:
        value = self.get(record)
        if value is None:
            return ""
        if self.decimals is not None:
            try:
                return f"{float(value):.{self.decimals}f}"
            except (TypeError, ValueError):
                return str(value)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)


_NUMERIC_ROLE = Qt.ItemDataRole.UserRole + 1


class RecordTableModel(QAbstractTableModel):
    """Read-only table over a list of records, described by a column spec."""

    countChanged = pyqtSignal()

    def __init__(self, columns: Sequence[Column], parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._records: list[Any] = []

    def set_records(self, records: Sequence[Any]) -> None:
        new_records = list(records)
        if len(new_records) != len(self._records):
            self.beginResetModel()
            self._records = new_records
            self.endResetModel()
            self.countChanged.emit()
            return
        # Same row count: patch in place so views keep their scroll position.
        self._records = new_records
        if new_records and self._columns:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(new_records) - 1, len(self._columns) - 1),
            )

    def record_at(self, row: int) -> Optional[Any]:
        return self._records[row] if 0 <= row < len(self._records) else None

    @pyqtProperty(int, notify=countChanged)
    def count(self) -> int:
        return len(self._records)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        column = self._columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return column.format(self._records[index.row()])
        if role == _NUMERIC_ROLE:
            return column.decimals is not None
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].title
        return section + 1

    def roleNames(self):
        return {
            Qt.ItemDataRole.DisplayRole: b"display",
            _NUMERIC_ROLE: b"numeric",
        }
