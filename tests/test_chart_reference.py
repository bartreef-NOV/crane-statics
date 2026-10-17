"""Brute-force chart reference sanity checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.chart_reference import reference_capacity
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core import load_document
from crane_statics.core.lead_channels import compose_lead_channel_point

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_reference_equals_single_case_when_everything_is_zero() -> None:
    doc = load_document(EXAMPLES / "crane_input_GT283.yaml")
    doc.environment.max_wind_speed_m_s = 0.0
    for field in type(doc.environment.vessel_motion).model_fields:
        setattr(doc.environment.vessel_motion, field, 0.0)
    hoist = next(h for h in doc.hoists if h.id == "MH")
    hoist.offlead_deg = 0.0
    if hasattr(hoist, "sidelead_deg"):
        hoist.sidelead_deg = 0.0
    calc = CraneCalculator(doc)
    limits = {"boom_hoist": {"T": 1.0e9}, "heel_point": {"Fz": 5000.0}}
    kwargs = dict(hook_daf=hoist.hook_daf, hook_mass_t=hoist.hook_mass_t)

    pt = calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
    assert pt is not None
    expected = calc.compute_allowable_load(
        compose_lead_channel_point(pt, 0.0, 0.0), limits, **kwargs
    )
    got = reference_capacity(calc, doc, "MH", 45.0, limits, overrides=None, **kwargs)
    assert got.max_allowable_load_kN == pytest.approx(expected.max_allowable_load_kN)
    assert got.max_allowable_load_t == pytest.approx(expected.max_allowable_load_t)
