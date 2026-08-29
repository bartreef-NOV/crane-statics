"""Toolkit-neutral result row model shared by the analysis service and views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ResultRow:
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
