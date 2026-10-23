"""Dynamic factor: the one place payload mass and hook force are converted.

The solver works in the hook-force domain; the factor only appears where a payload mass
is turned into a hook force and back. Keeping both conversions here lets a factor that
depends on the load (or on a rule set) replace the constant without touching the solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union


class DynamicFactor(Protocol):
    """Converts between payload mass and the force applied at the hook."""

    def hook_force_kN(self, payload_t: float, hook_mass_t: float, gravity_m_s2: float) -> float:
        """Hook force for a payload; the factor applies to payload and hook block alike."""
        ...

    def payload_t(self, hook_force_kN: float, hook_mass_t: float, gravity_m_s2: float) -> float:
        """Inverse of ``hook_force_kN``; not floored, so a heavy hook gives a negative payload."""
        ...


@dataclass(frozen=True)
class ConstantDynamicFactor:
    """A fixed factor, as authored per hoist."""

    value: float = 1.0

    def hook_force_kN(self, payload_t: float, hook_mass_t: float, gravity_m_s2: float) -> float:
        return (payload_t + hook_mass_t) * self.value * gravity_m_s2

    def payload_t(self, hook_force_kN: float, hook_mass_t: float, gravity_m_s2: float) -> float:
        return hook_force_kN / self.value / gravity_m_s2 - hook_mass_t


DynamicFactorLike = Union[float, DynamicFactor]


def as_dynamic_factor(factor: DynamicFactorLike) -> DynamicFactor:
    """A plain number is a constant factor; anything else is already a ``DynamicFactor``."""
    if isinstance(factor, (int, float)):
        return ConstantDynamicFactor(float(factor))
    return factor
