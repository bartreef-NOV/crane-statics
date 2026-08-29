"""Tests for shared statics analysis-case enumeration."""

from pathlib import Path

from crane_statics.core.analysis_cases import (
    iter_wind_lead_directional_cases,
    iter_wind_directional_cases,
    iter_hoist_analysis_modes,
)
from crane_statics.core.io import load_document


EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


def test_example_modes_and_directional_case_counts():
    doc = load_document(EXAMPLE)
    mh = next(hoist for hoist in doc.hoists if hoist.id == "MH")
    wh = next(hoist for hoist in doc.hoists if hoist.id == "WH")

    mh_modes = iter_hoist_analysis_modes(mh)
    assert [mode.name for mode in mh_modes] == ["normal", "split"]
    assert len(list(iter_wind_lead_directional_cases(mh, 15.1))) == 16
    assert len(list(iter_wind_lead_directional_cases(wh, 15.1))) == 16
    assert len(list(iter_wind_directional_cases(mh, 15.1))) == 4


def test_zero_wind_has_one_directional_case_per_lead_combination():
    doc = load_document(EXAMPLE)
    mh = next(hoist for hoist in doc.hoists if hoist.id == "MH")

    cases = list(iter_wind_lead_directional_cases(mh, 0.0))

    assert len(cases) == 4
    assert {case.wind_direction for case in cases} == {"+X"}
