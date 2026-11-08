"""Shared value types for the rules package. Pure: no Qt, no UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping

from ..calculation.dynamic_factor import DynamicFactor
from ..data.models import VesselMotion


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


@dataclass(frozen=True)
class CaseSpec:
    """One in-service load case a profile derives from a condition."""

    name: str
    wind_speed_m_s: float
    vessel_motion: VesselMotion


@dataclass(frozen=True)
class LateralSpec:
    """Horizontal live-load settings at the boom tip.

    ``accel_fraction_*`` are the vessel accelerations in g, ``incline_deg`` the combined
    list/trim angle, ``wind_area_m2``/``wind_cd`` the suspended load's projected area and
    drag coefficient, and ``min_fraction`` the minimum total side load as a fraction of
    the vertical design load.
    """

    accel_fraction_x: float
    accel_fraction_y: float
    incline_deg: float
    wind_area_m2: float
    wind_cd: float
    min_fraction: float


@dataclass(frozen=True)
class FoundationFactors:
    """Pedestal/foundation multipliers; ``live_factor`` takes the live load in kN."""

    live_factor: Callable[[float], float]
    dead_factor: float


@dataclass(frozen=True)
class LiftSetup:
    """Everything a profile hands the calculation for one condition, hoist and mode."""

    factor: DynamicFactor
    lateral: LateralSpec
    foundation: FoundationFactors
    retaining_live_factor: float
    records: tuple[ProvenanceRecord, ...]
    warnings: tuple[str, ...]
