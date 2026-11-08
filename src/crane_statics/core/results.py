"""Toolkit-neutral result row model shared by the analysis service and views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ResultRow:
    """One results-table row.

    ``kind`` is "rope", "connection" or "factored": a factored row reports a platform-base
    component under the rules profile's pedestal factor ("Platform Base (ABS PF)",
    "Platform Base (DNV SF1)") or the ABS retaining-component factor ("Retaining"); its
    ``entity_id`` is the limits' entity, ``runtime_id`` the entity whose reactions it reads.
    """

    name: str
    unit: str = ""
    demand_kN: float = 0.0
    limit_kN: Optional[float] = None
    utilization_pct: Optional[float] = None
    is_group_header: bool = False
    kind: Optional[str] = None
    entity_id: Optional[str] = None
    component: Optional[str] = None
    runtime_id: Optional[str] = None
