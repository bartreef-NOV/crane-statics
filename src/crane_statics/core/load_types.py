"""Value types of the drawn-loads model: vectors, moments, load sets and conditions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LoadVector:
    """A force applied at a world point, in kN."""

    world_x: float
    world_z: float
    fx_kN: float
    fz_kN: float
    category: str
    label: str
    detail: str = ""

    @property
    def magnitude_kN(self) -> float:
        return math.hypot(self.fx_kN, self.fz_kN)


@dataclass(frozen=True)
class LoadMoment:
    """A moment applied at a world point, in kNm."""

    world_x: float
    world_z: float
    moment_kNm: float
    entity_id: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class BodyLoads:
    """Named load categories plus reaction moments for one free-body selection."""

    categories: tuple[tuple[str, tuple[LoadVector, ...]], ...] = ()
    moments: tuple[LoadMoment, ...] = ()

    def category(self, name: str) -> tuple[LoadVector, ...]:
        for category_name, vectors in self.categories:
            if category_name == name:
                return vectors
        return ()

    def vectors(self, *names: str) -> tuple[LoadVector, ...]:
        """All vectors, or only those in the named categories, in report order."""
        wanted = set(names) if names else None
        return tuple(
            vector
            for name, vectors in self.categories
            if wanted is None or name in wanted
            for vector in vectors
        )


@dataclass(frozen=True)
class LoadConditions:
    """In-plane environmental and hoist state a load set is evaluated at.

    Out-of-plane inputs (lateral/roll acceleration, sidelead, Y-wind) are
    absent by design -- see the module docstring.

    ``gravity_x/z_m_s2`` are the crane-frame gravity components (vessel tilt and slew
    resolved); ``None`` means the nominal ``(0, -g)`` of the document environment.
    ``accel_x/z_m_s2`` and ``pitch_accel_rad_s2`` are the vessel's own accelerations
    rotated into the crane frame -- gravity is not folded into them.
    """

    boom_angle_deg: float = 0.0
    hook_load_kN: float = 0.0
    wind_speed_m_s: float = 0.0
    wind_direction: str = "+X"
    accel_x_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0
    offlead_deg: float = 0.0
    split_mode_active: bool = False
    gravity_x_m_s2: Optional[float] = None
    gravity_z_m_s2: Optional[float] = None
