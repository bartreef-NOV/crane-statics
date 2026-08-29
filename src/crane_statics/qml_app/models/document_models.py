"""Column specifications for the QML Model workspace tables.

Uses crane_statics.presentation.formatters for all display logic.
"""

from __future__ import annotations

from typing import Any, Callable

from .table_models import Column
from crane_statics.presentation.formatters import (
    ComponentTableFormatter,
    HoistFormatter,
)


def node_columns(body_id: str) -> list[Column]:
    """Column definitions for node table."""
    cols = ComponentTableFormatter.node_columns(body_id)
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]


def mass_point_columns(body_id: str) -> list[Column]:
    """Column definitions for mass point table."""
    cols = ComponentTableFormatter.mass_point_columns(body_id)
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]


def wind_area_columns(body_id: str) -> list[Column]:
    """Column definitions for wind area table."""
    cols = ComponentTableFormatter.wind_area_columns(body_id)
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]


def hoist_columns(is_boom_hoist: Callable[[Any], bool] | None = None) -> list[Column]:
    """Column definitions for hoist table."""
    cols = HoistFormatter.table_columns(is_boom_hoist)
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]


def rope_segment_columns() -> list[Column]:
    """Column definitions for rope segment table."""
    cols = ComponentTableFormatter.rope_segment_columns()
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]


def contractual_columns() -> list[Column]:
    """Column definitions for contractual point table."""
    cols = ComponentTableFormatter.contractual_columns()
    return [Column(title=c.name, get=c.accessor, decimals=c.decimals) for c in cols]
