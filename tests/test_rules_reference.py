"""Anchor values for the hand-calculation oracle (arithmetic in the case sheet)."""

import pytest

from tests.rules_reference import (
    abs_heavy_lift_vaf,
    abs_list_trim_load,
    abs_live_load_wind_area,
    abs_pedestal_factor,
    abs_v_hmin,
    abs_v_r,
    abs_vaf_offboard,
    abs_vaf_onboard,
    abs_wind_pressure,
    dnv_psi,
    dnv_psi_floor,
    dnv_sf1,
    dnv_v_h,
    dnv_v_r,
    hook_stiffness,
)


def approx(x, **kw):
    return pytest.approx(x, rel=1e-4, **kw)


def test_abs_onboard():
    assert abs_vaf_onboard(1000, 0) == approx(1.181429)
    assert abs_vaf_onboard(100, 0) == approx(1.33)
    assert abs_vaf_onboard(2000, 0) == approx(1.1)
    assert abs_vaf_onboard(1000, 0.05) == approx(1.231429)


def test_abs_offboard():
    assert abs_v_r(0.5, 0.8, 0.6) == approx(1.5)
    assert abs_vaf_offboard(1000, 5000, 1.5, 0) == approx(2.070883)
    assert abs_vaf_offboard(1000, 5000, 0.0, 0) == approx(abs_vaf_onboard(1000, 0))


def test_abs_hoist_speed_and_heavy_lift():
    assert abs_v_hmin(1.0) == approx(0.108)
    assert abs_v_hmin(2.0) == approx(0.201)
    assert abs_heavy_lift_vaf(0.05) == approx(1.15)


def test_abs_pedestal_factor():
    assert abs_pedestal_factor(1000, "offshore") == approx(1.31)
    assert abs_pedestal_factor(0, "offshore") == approx(1.5)
    assert abs_pedestal_factor(2000, "offshore") == approx(1.2)
    assert abs_pedestal_factor(2000, "heavy_lift") == approx(1.06)
    assert abs_pedestal_factor(3000, "heavy_lift") == approx(1.0)


def test_abs_wind_and_list_trim():
    assert abs_live_load_wind_area(1000) == approx(12.15)
    assert abs_wind_pressure(20, 1.0) == approx(0.244350)
    assert abs_list_trim_load(1000, 5, 2) == pytest.approx(93.85, abs=0.01)


def test_dnv():
    assert dnv_psi(5000, 1000, 1.3) == approx(1.928098)
    assert dnv_psi_floor(2000) == approx(1.3)
    assert dnv_psi_floor(3000) == approx(1.26)
    assert dnv_psi_floor(6000) == approx(1.1)
    assert dnv_v_h(2.0) == approx(0.3)
    assert dnv_v_r(0.5, 0.8, 0.6, 2.0) == approx(1.3)
    assert dnv_sf1(2000) == approx(1.3)
    assert dnv_sf1(3000) == approx(1.1)


def test_hook_stiffness():
    assert hook_stiffness([(0.5, 100.0, 100000.0)]) == approx(4000.0)
    two = [(0.5, 100.0, 100000.0), (0.5, 50.0, 200000.0)]
    assert hook_stiffness(two) == approx(3200.0)
