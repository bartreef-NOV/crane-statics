"""Hook-load capacity inversion primitives."""

import math
import random

import pytest

from crane_statics.calculation.capacity import (
    solve_bearing_line_load_capacity_kN,
    solve_capacity_limit_kN,
)


def _bearing_q(fz: float, mx: float, my: float, diameter: float) -> float:
    return fz / (math.pi * diameter) + 4.0 * math.hypot(mx, my) / (math.pi * diameter**2)


def _bisected(limit, fz0, fz_s, mx0, mx_s, my0, my_s, diameter):
    return solve_capacity_limit_kN(
        limit,
        lambda h: _bearing_q(fz0 + fz_s * h, mx0 + mx_s * h, my0 + my_s * h, diameter),
        tolerance=1e-6,
    )


class TestBearingLineLoadCapacity:
    def test_matches_the_bisection_over_random_cases(self):
        rng = random.Random(20261006)
        checked = 0
        for _ in range(2000):
            diameter = rng.uniform(4.0, 20.0)
            case = dict(
                fz0=rng.uniform(0.0, 40000.0),
                fz_s=rng.uniform(-0.5, 1.5),
                mx0=rng.uniform(-20000.0, 20000.0),
                mx_s=rng.uniform(-50.0, 50.0),
                my0=rng.uniform(-800000.0, 800000.0),
                my_s=rng.uniform(-200.0, 200.0),
            )
            q0 = _bearing_q(case["fz0"], case["mx0"], case["my0"], diameter)
            limit = q0 * rng.uniform(0.8, 3.0)
            expected = _bisected(limit, diameter=diameter, **case)
            actual = solve_bearing_line_load_capacity_kN(
                limit, diameter_m=diameter, tolerance=1e-6, **case
            )
            if math.isinf(expected):
                assert math.isinf(actual), case
            else:
                assert actual == pytest.approx(expected, rel=1e-10, abs=1e-9), case
            checked += 1
        assert checked == 2000

    def test_already_exceeded_gives_zero(self):
        assert (
            solve_bearing_line_load_capacity_kN(
                10.0, fz0=1e5, fz_s=1.0, mx0=0.0, mx_s=0.0, my0=0.0, my_s=0.0, diameter_m=10.0
            )
            == 0.0
        )

    def test_a_demand_that_never_grows_is_unbounded(self):
        assert math.isinf(
            solve_bearing_line_load_capacity_kN(
                100.0, fz0=10.0, fz_s=-1.0, mx0=0.0, mx_s=0.0, my0=0.0, my_s=0.0, diameter_m=10.0
            )
        )

    def test_moment_only_capacity_is_exact(self):
        # q = 4 |M| / (pi D^2) with M = 1000 H: q = L at H = L pi D^2 / 4000.
        capacity = solve_bearing_line_load_capacity_kN(
            50.0, fz0=0.0, fz_s=0.0, mx0=0.0, mx_s=600.0, my0=0.0, my_s=800.0, diameter_m=10.0
        )
        assert capacity == pytest.approx(50.0 * math.pi * 100.0 / 4000.0)
