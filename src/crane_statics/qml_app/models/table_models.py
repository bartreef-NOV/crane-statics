"""Generic record-backed table model shared by every document table in QML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)


@dataclass(frozen=True)
class Column:
    """One displayed column: a header, how to read a record, and how to edit it.

    ``field`` names the entry this column writes in the table's edit-field map;
    without one the column is derived or immutable and stays read-only. ``editable``
    narrows that per record, for tables whose rows do not all carry the same
    authored fields.
    """

    title: str
    get: Callable[[Any], Any]
    decimals: Optional[int] = None
    field: Optional[str] = None
    editor: str = ""
    editable: Optional[Callable[[Any], bool]] = None

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

    def is_editable(self, record: Any) -> bool:
        if not self.field:
            return False
        return True if self.editable is None else bool(self.editable(record))

    def edit_value(self, record: Any) -> Any:
        """What to seed the in-cell editor with.

        Check boxes and integer editors need the value itself; every other editor
        is a text field, where the formatted text is what the operator was already
        reading in the cell.
        """
        value = self.get(record)
        if self.editor == "bool":
            return bool(value)
        if self.editor == "int":
            return 0 if value is None else int(value)
        return self.format(record)


_NUMERIC_ROLE = Qt.ItemDataRole.UserRole + 1
_EDITABLE_ROLE = Qt.ItemDataRole.UserRole + 2
_EDITOR_ROLE = Qt.ItemDataRole.UserRole + 3
_EDIT_ROLE = Qt.ItemDataRole.UserRole + 4


class RecordTableModel(QAbstractTableModel):
    """Table over a list of records, described by a column spec.

    Cells are editable where the column says so and only when the owner supplied a
    ``commit`` hook: the model holds no document, so an edit is handed straight
    back to the view model that built the table.
    """

    countChanged = pyqtSignal()

    def __init__(
        self,
        columns: Sequence[Column],
        parent=None,
        commit: Optional[Callable[[int, str, Any], bool]] = None,
    ):
        super().__init__(parent)
        self._columns = list(columns)
        self._records: list[Any] = []
        self._commit = commit

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
        record = self._records[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return column.format(record)
        if role == _NUMERIC_ROLE:
            return column.decimals is not None
        if role == _EDITABLE_ROLE:
            return self._can_edit(column, record)
        if role == _EDITOR_ROLE:
            return column.editor or ("number" if column.decimals is not None else "text")
        if role == _EDIT_ROLE:
            return column.edit_value(record)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].title
        return section + 1

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        if not self._can_edit(self._columns[index.column()], self._records[index.row()]):
            return base & ~Qt.ItemFlag.ItemIsEditable
        return base | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role not in (Qt.ItemDataRole.EditRole, _EDIT_ROLE):
            return False
        column = self._columns[index.column()]
        if not self._can_edit(column, self._records[index.row()]) or self._commit is None:
            return False
        # The commit re-reads the document and resets the records, which is what
        # repaints the cell; there is nothing to write into the row held here.
        return bool(self._commit(index.row(), str(column.field), value))

    @pyqtSlot(int, int, "QVariant", result=bool)
    def commitCell(self, row: int, column: int, value: Any) -> bool:
        """Apply one edited cell, addressed the way a QML delegate knows it."""
        return self.setData(self.index(int(row), int(column)), value, _EDIT_ROLE)

    @pyqtSlot(int, int, result=bool)
    def isCellEditable(self, row: int, column: int) -> bool:
        """Whether a cell accepts editing, asked before an editor is opened.

        The table asks rather than opening one and finding out, because Qt warns
        when told to edit a read-only index.
        """
        index = self.index(int(row), int(column))
        if not index.isValid():
            return False
        return bool(self.flags(index) & Qt.ItemFlag.ItemIsEditable)

    def _can_edit(self, column: Column, record: Any) -> bool:
        return self._commit is not None and column.is_editable(record)

    def roleNames(self):
        return {
            Qt.ItemDataRole.DisplayRole: b"display",
            _NUMERIC_ROLE: b"numeric",
            _EDITABLE_ROLE: b"editable",
            _EDITOR_ROLE: b"editorKind",
            _EDIT_ROLE: b"edit",
        }
