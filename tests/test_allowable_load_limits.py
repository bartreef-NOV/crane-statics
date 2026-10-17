"""Allowable hook load when a design limit is already exceeded, or none applies.

A limit already exceeded with no hook load gives a negative (linear) or zero
(radial/bisection) candidate. Those used to be skipped, and with no candidate left
the allowable load fell back to 1000 kN, so an overloaded crane showed capacity.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crane_statics.calculation import CraneCalculator
from crane_statics.core import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture(scope="module")
def solved():
    calc = CraneCalculator(load_document(EXAMPLE))
    point = calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
    assert point is not None
    return calc, point


def test_limit_exceeded_with_no_hook_load_gives_zero(solved) -> None:
    calc, point = solved
    heel_fz = point.baseline_reactions["heel_point"]["Fz"]
    cap = calc.compute_allowable_load(point, {"heel_point": {"Fz": 0.5 * heel_fz}})
    assert cap.max_allowable_load_kN == 0.0
    assert cap.max_allowable_load_t == 0.0
    assert cap.governing_limit_id == "heel_point"


def test_exceeded_limit_governs_over_a_satisfied_one(solved) -> None:
    calc, point = solved
    heel_fz = point.baseline_reactions["heel_point"]["Fz"]
    limits = {"boom_hoist": {"T": 1.0e9}, "heel_point": {"Fz": 0.5 * heel_fz}}
    cap = calc.compute_allowable_load(point, limits)
    assert cap.max_allowable_load_kN == 0.0
    assert cap.governing_limit_id == "heel_point"


def test_exceeded_resultant_limit_gives_zero(solved) -> None:
    calc, point = solved
    heel = point.baseline_reactions["heel_point"]
    resultant = math.hypot(heel["Fx"], heel["Fz"])
    cap = calc.compute_allowable_load(point, {"heel_point": {"resultant": 0.5 * resultant}})
    assert cap.max_allowable_load_kN == 0.0
    assert cap.governing_limit_id == "heel_point"


def test_no_applicable_limit_means_unlimited(solved) -> None:
    calc, point = solved
    cap = calc.compute_allowable_load(point, {})
    assert math.isinf(cap.max_allowable_load_kN)
    assert math.isinf(cap.max_allowable_load_t)
    assert cap.governing_limit_id is None
