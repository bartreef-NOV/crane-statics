"""Shared value types for the rules package. Pure: no Qt, no UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


@dataclass(frozen=True)
class ProvenanceRecord:
    """How one rule-derived quantity was obtained, for the calculation trail."""

    quantity: str
    value: float
    unit: str
    clause: str
    formula: str
    inputs: Mapping[str, float]
    source: Literal["computed", "override"]
