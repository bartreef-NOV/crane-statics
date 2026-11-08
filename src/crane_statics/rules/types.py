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
    drag coefficient (the area the profile uses: ABS fills its 5.19.3 default), and
    ``min_fraction`` the minimum total side load as a fraction of the vertical design load.
    ``wind_force_per_speed_sq`` is the wind force on the suspended load per squared wind
    speed, kN/(m/s)^2, by the standard's pressure formula: the force at wind speed V is
    ``wind_force_per_speed_sq * V**2`` (0: no wind on the load).
    ``accel_fraction_per_m_x``/``_y`` are the horizontal accelerations, in g per metre of
    height above ``reference_z_m``, that the pitch (x) and roll (y) angular accelerations
    add at a point (the solver's lever arm ``z - reference_z``): with them the horizontal
    acceleration at the boom tip is ``accel_fraction + accel_fraction_per_m * |z - z_ref|``.
    """

    accel_fraction_x: float
    accel_fraction_y: float
    incline_deg: float
    wind_area_m2: float
    wind_cd: float
    min_fraction: float
    wind_force_per_speed_sq: float = 0.0
    accel_fraction_per_m_x: float = 0.0
    accel_fraction_per_m_y: float = 0.0
    reference_z_m: float = 0.0

    def wind_force_kN(self, wind_speed_m_s: float) -> float:
        """Wind force on the suspended load at ``wind_speed_m_s``, kN."""
        return self.wind_force_per_speed_sq * float(wind_speed_m_s) ** 2


@dataclass(frozen=True)
class FoundationFactors:
    """Pedestal/foundation multipliers; ``live_factor`` takes the live load in kN."""

    live_factor: Callable[[float], float]
    dead_factor: float


def _unit_factor(_live_load_kN: float) -> float:
    return 1.0


#: No foundation factor (legacy, DNV without a cabin above the slewing bearing): the
#: calculation then leaves the platform base on its unfactored, linear path.
NEUTRAL_FOUNDATION = FoundationFactors(live_factor=_unit_factor, dead_factor=1.0)


@dataclass(frozen=True)
class LiftSetup:
    """Everything a profile hands the calculation for one condition, hoist and mode."""

    factor: DynamicFactor
    lateral: LateralSpec
    foundation: FoundationFactors
    retaining_live_factor: float
    records: tuple[ProvenanceRecord, ...]
    warnings: tuple[str, ...]
