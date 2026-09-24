"""Column specifications for the QML Model workspace tables.

Uses crane_statics.presentation.formatters for all display logic.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .table_models import Column
from crane_statics.presentation.formatters import (
    ComponentTableFormatter,
    HoistFormatter,
)


def _to_qml(columns: Sequence[Any]) -> list[Column]:
    """Restate presentation columns in the shape the Qt table model wants."""
    return [
        Column(
            title=c.name,
            get=c.accessor,
            decimals=c.decimals,
            field=c.field,
            editor=c.editor_kind() if c.field else "",
            editable=c.editable,
        )
        for c in columns
    ]


def node_columns(body_id: str) -> list[Column]:
    """Column definitions for node table."""
    return _to_qml(ComponentTableFormatter.node_columns(body_id))


def mass_point_columns(body_id: str) -> list[Column]:
    """Column definitions for mass point table."""
    return _to_qml(ComponentTableFormatter.mass_point_columns(body_id))


def wind_area_columns(body_id: str) -> list[Column]:
    """Column definitions for wind area table."""
    return _to_qml(ComponentTableFormatter.wind_area_columns(body_id))


def hoist_columns(is_boom_hoist: Callable[[Any], bool] | None = None) -> list[Column]:
    """Column definitions for hoist table."""
    return _to_qml(HoistFormatter.table_columns(is_boom_hoist))


def rope_segment_columns() -> list[Column]:
    """Column definitions for rope segment table."""
    return _to_qml(ComponentTableFormatter.rope_segment_columns())


def contractual_columns() -> list[Column]:
    """Column definitions for contractual point table."""
    return _to_qml(ComponentTableFormatter.contractual_columns())
