"""Row builders turning core results and reports into flat QML-friendly rows.

Uses crane_statics.presentation.formatters for all display logic.
"""

from __future__ import annotations

from typing import Any

from crane_statics.core.results import ResultRow
from crane_statics.presentation.formatters import ResultRowFormatter

RESULT_ROLES = [
    "name",
    "unit",
    "demand",
    "limit",
    "utilization",
    "utilizationValue",
    "isGroupHeader",
    "nested",
    "clickable",
    "tooltip",
]

REPORT_ROLES = ["label", "kind", "fx", "fz", "magnitude", "posX", "posZ", "moment", "passed"]


def is_clickable(row: ResultRow) -> bool:
    """Determine if a result row should be clickable (selectable)."""
    return ResultRowFormatter.is_clickable(row)


def result_row_payload(row: ResultRow) -> dict[str, Any]:
    """Extract result row data for event payloads."""
    return ResultRowFormatter.result_row_payload(row)


def result_rows_to_dicts(rows: list[ResultRow]) -> list[dict[str, Any]]:
    """Transform analysis ResultRows into QML-consumable dicts."""
    return ResultRowFormatter.result_rows_to_dicts(rows)


def report_to_rows(report: dict) -> list[dict[str, Any]]:
    """Flatten an equilibrium / load-summary report into displayable rows."""
    return ResultRowFormatter.report_rows_to_dicts(report)
