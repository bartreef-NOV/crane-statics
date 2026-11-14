"""Brute-force chart reference sanity checks."""

from __future__ import annotations

from typing import Any

import pytest

from tests.chart_reference import reference_capacity
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core.lead_channels import compose_lead_channel_point
from tests.authored_helpers import authored_daf, case_document, load_example


def test_reference_equals_single_case_when_everything_is_zero() -> None:
    doc = load_example("crane_input_GT283.yaml")
    condition = doc.conditions["default"]
    condition.wind_speed_m_s = 0.0
    for field in type(condition.vessel_motion).model_fields:
        setattr(condition.vessel_motion, field, 0.0)
    hoist = next(h for h in doc.hoists if h.id == "MH")
    condition.hoists["MH"].offlead_deg = 0.0
    condition.hoists["MH"].sidelead_deg = 0.0
    calc = CraneCalculator(case_document(doc))
    limits = {"boom_hoist": {"T": 1.0e9}, "heel_point": {"Fz": 5000.0}}
    kwargs: dict[str, Any] = dict(
        hook_daf=authored_daf(doc, "MH"), lower_block_mass_t=hoist.lower_block_mass_t
    )

    pt = calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
    assert pt is not None
    expected = calc.compute_allowable_load(
        compose_lead_channel_point(pt, 0.0, 0.0), limits, **kwargs
    )
    got = reference_capacity(calc, doc, "MH", 45.0, limits, overrides=None, **kwargs)
    assert got.max_allowable_load_kN == pytest.approx(expected.max_allowable_load_kN)
    assert got.max_allowable_load_t == pytest.approx(expected.max_allowable_load_t)
