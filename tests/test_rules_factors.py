from __future__ import annotations

from dataclasses import replace

import pytest

from crane_statics.calculation.dynamic_factor import ConstantDynamicFactor
from crane_statics.rules.factors import (
    AbsOnboardFactor,
    LinearFactor,
    MaxFactor,
    RelativeVelocityFactor,
)
from crane_statics.rules.types import ProvenanceRecord
from tests import rules_reference as ref

G = ref.G
HOOK = 2.0


def _all_factors():
    return [
        LinearFactor(1.26),
        LinearFactor(1.26, extra_mass_t=1.5),
        AbsOnboardFactor(0.0),
        AbsOnboardFactor(0.2, extra_mass_t=1.5),
        RelativeVelocityFactor(5000.0, 1.3),
        RelativeVelocityFactor(5000.0, 1.3, extra_mass_t=1.5),
        MaxFactor((LinearFactor(1.26), RelativeVelocityFactor(5000.0, 1.3))),
        MaxFactor((AbsOnboardFactor(0.1), RelativeVelocityFactor(2000.0, 0.8))),
        ConstantDynamicFactor(1.2),
    ]


@pytest.mark.parametrize("factor", _all_factors())
@pytest.mark.parametrize("payload", [0.0, 50.0, 300.0, 1200.0])
@pytest.mark.parametrize("hook", [0.0, HOOK])
def test_round_trip(factor, payload, hook):
    force = factor.hook_force_kN(payload, hook, G)
    assert factor.payload_t(force, hook, G) == pytest.approx(payload, abs=1e-6)


def test_abs_onboard_matches_oracle():
    f = AbsOnboardFactor(0.0)
    assert f.hook_force_kN(1000.0 / G, 0.0, G) == pytest.approx(1000.0 * 1.181429, rel=1e-6)
    for ll in (100.0, 1000.0, 2000.0):
        assert f.hook_force_kN(ll / G, 0.0, G) == pytest.approx(
            ll * ref.abs_vaf_onboard(ll, 0.0), rel=1e-9
        )


def test_abs_cap_floor_and_a_v_bounds():
    assert AbsOnboardFactor(0.0).hook_force_kN(100.0 / G, 0.0, G) == pytest.approx(133.0)
    assert AbsOnboardFactor(0.0).hook_force_kN(2000.0 / G, 0.0, G) == pytest.approx(2200.0)
    a = 0.15
    assert AbsOnboardFactor(a).hook_force_kN(100.0 / G, 0.0, G) == pytest.approx(100 * (1.33 + a))
    assert AbsOnboardFactor(a).hook_force_kN(2000.0 / G, 0.0, G) == pytest.approx(2000 * (1.1 + a))


def test_relative_velocity_matches_oracle():
    w = 1000.0
    psi = RelativeVelocityFactor(5000.0, 1.3).hook_force_kN(w / G, 0.0, G) / w
    assert psi == pytest.approx(1.928098, abs=1e-6)
    assert psi == pytest.approx(ref.dnv_psi(5000.0, w, 1.3))


def test_max_with_zero_velocity_equals_onboard():
    m = MaxFactor((AbsOnboardFactor(0.0), RelativeVelocityFactor(5000.0, 0.0)))
    onboard = AbsOnboardFactor(0.0)
    for p in (0.0, 50.0, 300.0, 1200.0):
        assert m.hook_force_kN(p, HOOK, G) == pytest.approx(onboard.hook_force_kN(p, HOOK, G))


def test_dnv_floor_via_max():
    w = 1000.0
    m = MaxFactor((LinearFactor(1.26), RelativeVelocityFactor(5000.0, 1.3)))
    assert m.hook_force_kN(w / G, 0.0, G) == pytest.approx(w * ref.dnv_psi(5000.0, w, 1.3))
    low = MaxFactor((LinearFactor(1.26), RelativeVelocityFactor(5000.0, 0.01)))
    assert low.hook_force_kN(w / G, 0.0, G) == pytest.approx(w * 1.26)


@pytest.mark.parametrize(
    "factor", [LinearFactor(1.3), AbsOnboardFactor(0.0), RelativeVelocityFactor(5000.0, 1.3)]
)
def test_zero_load_gives_zero_force_without_raising(factor):
    assert factor.hook_force_kN(0.0, 0.0, G) == 0.0
    assert factor.payload_t(0.0, 0.0, G) == 0.0


def test_extra_mass_adds_extra_psi_g():
    lin = LinearFactor(1.3)
    with_extra = LinearFactor(1.3, extra_mass_t=3.0)
    delta = with_extra.hook_force_kN(100.0, HOOK, G) - lin.hook_force_kN(100.0, HOOK, G)
    assert delta == pytest.approx(3.0 * 1.3 * G)
    # Load-dependent factors amplify the extra mass like hook mass.
    for cls in (AbsOnboardFactor(0.0), RelativeVelocityFactor(5000.0, 1.3)):
        extra = replace(cls, extra_mass_t=3.0)
        assert extra.hook_force_kN(100.0, HOOK, G) == pytest.approx(
            cls.hook_force_kN(100.0, HOOK + 3.0, G)
        )


@pytest.mark.parametrize("factor", _all_factors())
def test_payload_clamped_when_force_below_hook_only(factor):
    if isinstance(factor, ConstantDynamicFactor):
        pytest.skip("constant factor is intentionally unfloored")
    assert factor.payload_t(0.0, 5.0, G) == 0.0


def test_provenance_record():
    rec = ProvenanceRecord("vaf", 1.2, "-", "ABS 2-2/9.3.1", "f", {"LL": 1.0}, "computed")
    assert rec.source == "computed"
