"""Analyses read wind and vessel-motion limits through a LoadCondition."""

from __future__ import annotations

from pathlib import Path

from crane_statics.core import load_document
from crane_statics.core.load_condition import DEFAULT_CONDITION_NAME, default_load_condition

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


def test_default_condition_is_the_document_environment():
    doc = load_document(EXAMPLE)

    condition = default_load_condition(doc)

    assert condition.name == DEFAULT_CONDITION_NAME
    assert condition.wind_speed_m_s == float(doc.environment.max_wind_speed_m_s)
    assert condition.vessel_motion is doc.environment.vessel_motion
