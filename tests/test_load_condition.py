"""Analyses read wind and vessel-motion limits through a LoadCondition."""

from __future__ import annotations

from pathlib import Path

import pytest

from crane_statics.core import load_document
from crane_statics.core.load_condition import (
    DEFAULT_CONDITION_NAME,
    condition_cases,
    condition_document,
    condition_names,
    default_load_condition,
    load_conditions,
)
from crane_statics.core.session_model import SessionModel
from crane_statics.core.vessel_envelope import vessel_limit
from tests.rules_docs import MOTION, gale, rules_doc

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


def test_default_condition_is_the_document_environment():
    doc = load_document(EXAMPLE)

    condition = default_load_condition(doc)

    assert condition.name == DEFAULT_CONDITION_NAME
    assert condition.wind_speed_m_s == float(doc.environment.max_wind_speed_m_s)
    assert condition.vessel_motion is doc.environment.vessel_motion


# --- rules documents: one LoadCondition per (condition x profile case) --------------------


def test_legacy_load_conditions_is_the_default_condition():
    doc = load_document(EXAMPLE)

    assert load_conditions(doc) == (default_load_condition(doc),)
    assert condition_names(doc) == (DEFAULT_CONDITION_NAME,)
    assert condition_cases(doc, None) == (default_load_condition(doc),)
    assert condition_cases(doc, DEFAULT_CONDITION_NAME) == (default_load_condition(doc),)
    assert condition_document(doc, default_load_condition(doc)) is doc


def test_dnv_two_conditions_give_four_cases():
    doc = rules_doc("DNV", gale("gale"), gale("calm", wind=12.0))

    conditions = load_conditions(doc)

    assert [c.name for c in conditions] == [
        "gale/Case I",
        "gale/Case II",
        "calm/Case I",
        "calm/Case II",
    ]
    assert [c.condition_name for c in conditions] == ["gale", "gale", "calm", "calm"]
    assert [c.wind_speed_m_s for c in conditions] == [0.0, 30.0, 0.0, 12.0]
    assert all(c.spec is doc.conditions[c.condition_name] for c in conditions)
    assert [c.case.name for c in conditions] == ["Case I", "Case II"] * 2
    assert conditions[1].vessel_motion == conditions[1].case.vessel_motion
    assert conditions[1].vessel_motion.roll_deg == pytest.approx(1.5 * MOTION.roll_deg)
    assert condition_names(doc) == ("gale", "calm")
    assert condition_cases(doc, "calm") == conditions[2:]
    assert condition_cases(doc, None) == conditions[:2]


def test_abs_condition_has_one_in_service_case():
    doc = rules_doc("ABS", gale())

    (only,) = load_conditions(doc)

    assert only.name == "gale/In-service"
    assert only.wind_speed_m_s == 30.0
    assert only.vessel_motion == MOTION


def test_unknown_condition_raises_naming_it():
    with pytest.raises(KeyError, match="nope"):
        condition_cases(rules_doc("ABS", gale()), "nope")
    with pytest.raises(KeyError, match="nope"):
        condition_cases(load_document(EXAMPLE), "nope")


def test_condition_document_carries_the_case_environment():
    doc = rules_doc("ABS", gale())
    (case,) = load_conditions(doc)

    case_doc = condition_document(doc, case)

    assert case_doc.environment.max_wind_speed_m_s == 30.0
    assert case_doc.environment.vessel_motion == MOTION
    assert case_doc.environment.gravity_m_s2 == doc.environment.gravity_m_s2
    assert doc.environment.max_wind_speed_m_s == 20.0  # the document is not touched


def test_scene_starts_at_the_first_condition_not_the_dummies():
    doc = rules_doc("ABS", gale(wind=27.0))
    session = SessionModel()

    session.set_document(doc)

    scene = session.hoist_states["MH"].scene_state
    assert scene.wind_speed_m_s == 27.0
    assert scene.vessel_roll_deg == vessel_limit(MOTION, "roll_deg")
    assert scene.accel_x_m_s2 == vessel_limit(MOTION, "accel_x_m_s2")
