"""The dynamic factor is the single payload <-> hook-force conversion."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from crane_statics.calculation.dynamic_factor import (
    ConstantDynamicFactor,
    as_dynamic_factor,
)
from crane_statics.core.limit_auto_set import _required_hook_force_kN

GRAVITY = 9.81


def test_constant_factor_applies_to_payload_and_hook_block():
    factor = ConstantDynamicFactor(1.3)

    assert factor.hook_force_kN(10.0, 2.0, GRAVITY) == pytest.approx((10.0 + 2.0) * 1.3 * GRAVITY)


def test_constant_factor_inverse_round_trips():
    factor = ConstantDynamicFactor(1.15)
    force = factor.hook_force_kN(37.5, 4.0, GRAVITY)

    assert factor.payload_t(force, 4.0, GRAVITY) == pytest.approx(37.5)


def test_inverse_is_not_floored():
    assert ConstantDynamicFactor(1.0).payload_t(10.0, 5.0, GRAVITY) < 0.0


def test_plain_numbers_become_constant_factors():
    assert as_dynamic_factor(1.2) == ConstantDynamicFactor(1.2)
    assert as_dynamic_factor(2) == ConstantDynamicFactor(2.0)


def test_factor_objects_pass_through_unchanged():
    @dataclass(frozen=True)
    class LoadDependent:
        def hook_force_kN(self, payload_t: float, hook_mass_t: float, gravity_m_s2: float):
            return (payload_t + hook_mass_t) * (1.0 + 0.01 * payload_t) * gravity_m_s2

        def payload_t(self, hook_force_kN: float, hook_mass_t: float, gravity_m_s2: float):
            raise NotImplementedError

    factor = LoadDependent()

    assert as_dynamic_factor(factor) is factor


def test_required_hook_force_uses_the_factor_conversion():
    assert _required_hook_force_kN(20.0, 3.0, 1.1, -GRAVITY) == pytest.approx(
        ConstantDynamicFactor(1.1).hook_force_kN(20.0, 3.0, GRAVITY)
    )
