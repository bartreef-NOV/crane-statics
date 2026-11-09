"""Invertible ABS/DNV dynamic factors implementing ``calculation.dynamic_factor.DynamicFactor``.

The amplified load is ``W = (payload + hook_mass + extra_mass) * g`` in kN, where
``extra_mass`` is the suspended rope mass. For ABS ``W`` is the live load LL; for DNV it
is the working load. The hook force is ``F = factor(W) * W``. Every ``F(W)`` here is
strictly increasing, so ``payload_t`` is a closed-form inverse. Unlike the constant
factor, these inverses floor the payload at zero when the force is below the hook-only
force.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..calculation.dynamic_factor import DynamicFactor

#: ABS 2-2/9.3.1 onboard VAF: ``1.373 - LL / 5220 + a_v`` (LL in kN).
_ABS_INTERCEPT = 1.373
_ABS_LL_SCALE_KN = 5220.0


def _amplified_kN(
    payload_t: float, lower_block_mass_t: float, extra_mass_t: float, g: float
) -> float:
    return (payload_t + lower_block_mass_t + extra_mass_t) * g


def _payload_from_load(
    load_kN: float, lower_block_mass_t: float, extra_mass_t: float, g: float
) -> float:
    return max(0.0, load_kN / g - lower_block_mass_t - extra_mass_t)


@dataclass(frozen=True)
class LinearFactor:
    """``F = value * W``, e.g. the DNV floor or a fixed ABS heavy-lift factor."""

    value: float
    extra_mass_t: float = 0.0

    def hook_force_kN(
        self, payload_t: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        return self.value * _amplified_kN(
            payload_t, lower_block_mass_t, self.extra_mass_t, gravity_m_s2
        )

    def payload_t(
        self, hook_force_kN: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        return _payload_from_load(
            hook_force_kN / self.value, lower_block_mass_t, self.extra_mass_t, gravity_m_s2
        )


@dataclass(frozen=True)
class AbsOnboardFactor:
    """ABS 2-2/9.3.1 onboard VAF: ``clamp(1.373 - W/5220 + a_v, lower + a_v, upper + a_v)``."""

    a_v_g: float
    extra_mass_t: float = 0.0
    lower: float = 1.1
    upper: float = 1.33

    def factor(self, load_kN: float) -> float:
        raw = _ABS_INTERCEPT - load_kN / _ABS_LL_SCALE_KN + self.a_v_g
        return min(max(raw, self.lower + self.a_v_g), self.upper + self.a_v_g)

    def hook_force_kN(
        self, payload_t: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        load = _amplified_kN(payload_t, lower_block_mass_t, self.extra_mass_t, gravity_m_s2)
        return self.factor(load) * load

    def _load_from_force(self, force_kN: float) -> float:
        cap = self.upper + self.a_v_g
        floor = self.lower + self.a_v_g
        # Loads where the linear VAF meets the cap (smaller load) and the floor.
        w_cap = (_ABS_INTERCEPT - self.upper) * _ABS_LL_SCALE_KN
        w_floor = (_ABS_INTERCEPT - self.lower) * _ABS_LL_SCALE_KN
        if force_kN <= w_cap * cap:
            return force_kN / cap
        if force_kN >= w_floor * floor:
            return force_kN / floor
        # F = W (c - W/s)  =>  W = s/2 * (c - sqrt(c^2 - 4F/s)), the increasing root.
        c = _ABS_INTERCEPT + self.a_v_g
        s = _ABS_LL_SCALE_KN
        return 0.5 * s * (c - math.sqrt(max(0.0, c * c - 4.0 * force_kN / s)))

    def payload_t(
        self, hook_force_kN: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        load = self._load_from_force(max(0.0, hook_force_kN))
        return _payload_from_load(load, lower_block_mass_t, self.extra_mass_t, gravity_m_s2)


@dataclass(frozen=True)
class RelativeVelocityFactor:
    """ABS 2-2/9.3.2 / DNV 4.1.3.2: ``psi = 1 + v_r * sqrt(K / (W * g))``, W in kN.

    The force is ``F = W * psi = W + b * sqrt(W)`` with ``b = v_r * sqrt(K / g)``. As
    ``W -> 0`` psi itself grows without bound but ``F -> 0`` (``W * psi -> 0``), so the
    force is evaluated through that form and a zero load gives zero force with no
    division. psi is 1 at any load only when ``v_r = 0``.
    """

    stiffness_kN_m: float
    v_r_m_s: float
    extra_mass_t: float = 0.0

    def _b(self, gravity_m_s2: float) -> float:
        return self.v_r_m_s * math.sqrt(self.stiffness_kN_m / gravity_m_s2)

    def hook_force_kN(
        self, payload_t: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        load = _amplified_kN(payload_t, lower_block_mass_t, self.extra_mass_t, gravity_m_s2)
        load = max(0.0, load)
        return load + self._b(gravity_m_s2) * math.sqrt(load)

    def payload_t(
        self, hook_force_kN: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        b = self._b(gravity_m_s2)
        root = 0.5 * (-b + math.sqrt(b * b + 4.0 * max(0.0, hook_force_kN)))
        return _payload_from_load(root * root, lower_block_mass_t, self.extra_mass_t, gravity_m_s2)


@dataclass(frozen=True)
class MaxFactor:
    """The larger hook force of several factors, e.g. the DNV floor against psi.

    Each part is increasing in the load, so the inverse of the maximum is the minimum
    of the inverses.
    """

    parts: tuple[DynamicFactor, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("MaxFactor needs at least one part")

    def hook_force_kN(
        self, payload_t: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        return max(p.hook_force_kN(payload_t, lower_block_mass_t, gravity_m_s2) for p in self.parts)

    def payload_t(
        self, hook_force_kN: float, lower_block_mass_t: float, gravity_m_s2: float
    ) -> float:
        return min(p.payload_t(hook_force_kN, lower_block_mass_t, gravity_m_s2) for p in self.parts)
