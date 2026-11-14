"""Tests for shared statics analysis-case enumeration."""

from crane_statics.core.analysis_cases import (
    iter_wind_lead_directional_cases,
    iter_hoist_analysis_modes,
)
from crane_statics.core.io import load_document
from tests.authored_helpers import example_path, hoist_settings

EXAMPLE = example_path("crane_input_22689.yaml")


def test_example_modes_and_directional_case_counts():
    doc = load_document(EXAMPLE)
    mh = next(hoist for hoist in doc.hoists if hoist.id == "MH")
    mh_settings = hoist_settings(doc, "MH")
    wh_settings = hoist_settings(doc, "WH")

    mh_modes = iter_hoist_analysis_modes(mh, mh_settings)
    assert [mode.name for mode in mh_modes] == ["normal", "split"]
    assert len(list(iter_wind_lead_directional_cases(mh_settings, 15.1))) == 16
    assert len(list(iter_wind_lead_directional_cases(wh_settings, 15.1))) == 16


def test_zero_wind_has_one_directional_case_per_lead_combination():
    doc = load_document(EXAMPLE)
    cases = list(iter_wind_lead_directional_cases(hoist_settings(doc, "MH"), 0.0))

    assert len(cases) == 4
    assert {case.wind_direction for case in cases} == {"+X"}
