"""Analyses read wind and vessel-motion limits through a LoadCondition."""

from __future__ import annotations

import pytest

from crane_statics.core.load_condition import (
    DEFAULT_CONDITION_NAME,
    LoadCondition,
    condition_cases,
    condition_document,
    condition_names,
    load_conditions,
    scene_case,
)
from crane_statics.core.session_model import SessionModel
from crane_statics.core.vessel_envelope import vessel_limit
from crane_statics.data.models import ConditionHoist, ConditionSpec, CraneDocument, VesselMotion
from tests.rules_docs import GT283, MOTION, gale, load_v13, rules_doc

CALM = VesselMotion(accel_z_m_s2=0.3, roll_deg=1.0, pitch_deg=0.5)


def _rules_less() -> CraneDocument:
    """GT283 as migrated: no rules, one condition named ``default``."""
    doc = load_v13(GT283)
    assert doc.rules is None and list(doc.conditions) == [DEFAULT_CONDITION_NAME]
    return doc


def _two_rules_less_conditions() -> CraneDocument:
    doc = _rules_less()
    default = doc.conditions[DEFAULT_CONDITION_NAME]
    calm = default.model_copy(update={"name": "calm", "wind_speed_m_s": 7.0, "vessel_motion": CALM})
    return doc.model_copy(update={"conditions": {"default": default, "calm": calm}})


# --- rules-less documents: one LoadCondition per condition ------------------------------


def test_rules_less_condition_yields_one_case():
    doc = _rules_less()
    spec = doc.conditions[DEFAULT_CONDITION_NAME]

    expected = LoadCondition(
        name=DEFAULT_CONDITION_NAME,
        wind_speed_m_s=float(spec.wind_speed_m_s),
        vessel_motion=spec.vessel_motion,
        spec=spec,
        case=None,
    )

    assert load_conditions(doc) == (expected,)
    assert condition_names(doc) == (DEFAULT_CONDITION_NAME,)
    assert condition_cases(doc, None) == (expected,)
    assert condition_cases(doc, DEFAULT_CONDITION_NAME) == (expected,)
    assert scene_case(doc, None) == expected
    assert scene_case(doc, DEFAULT_CONDITION_NAME) == expected
    assert expected.condition_name == DEFAULT_CONDITION_NAME
    assert expected.wind_speed_m_s == 0.01  # GT283's own wind, not the environment's 20


def test_rules_less_cases_use_condition_wind_and_motion():
    doc = _two_rules_less_conditions()

    conditions = load_conditions(doc)

    assert [c.name for c in conditions] == ["default", "calm"]
    assert [c.wind_speed_m_s for c in conditions] == [0.01, 7.0]
    assert conditions[1].vessel_motion == CALM
    assert all(c.case is None for c in conditions)
    assert all(c.spec is doc.conditions[c.name] for c in conditions)
    assert condition_cases(doc, "calm") == conditions[1:]
    assert scene_case(doc, "calm") == conditions[1]
    with pytest.raises(KeyError, match="In-service"):
        scene_case(doc, "calm", "In-service")


def test_hoist_settings_unknown_hoist_names_condition_and_hoist():
    doc = _rules_less()
    (condition,) = load_conditions(doc)

    assert condition.hoist_settings("MH") is doc.conditions["default"].hoists["MH"]
    with pytest.raises(KeyError, match=r"(?s)default.*BH|BH.*default"):
        condition.hoist_settings("BH")
    with pytest.raises(KeyError, match=r"(?s)default.*nope|nope.*default"):
        condition.hoist_settings("nope")


def test_usable_hoist_ids_follow_spec_order():
    spec = ConditionSpec(
        name="sea",
        wind_speed_m_s=10.0,
        hoists={
            "trolley": ConditionHoist(offlead_deg=1.0),
            "MH": ConditionHoist(offlead_deg=2.0),
        },
    )
    doc = _rules_less().model_copy(update={"conditions": {"sea": spec}})

    (condition,) = load_conditions(doc)

    assert condition.usable_hoist_ids() == ("trolley", "MH")
    assert condition.hoist_settings("MH").offlead_deg == 2.0
    with pytest.raises(KeyError, match=r"(?s)sea.*AH|AH.*sea"):
        condition.hoist_settings("AH")
    # A rules case lists the same hoists as its condition.
    rules_cases = load_conditions(rules_doc("DNV", gale()))
    assert all(c.usable_hoist_ids() == ("MH", "AH", "trolley") for c in rules_cases)


def test_condition_document_substitutes_environment_for_rules_less():
    doc = _two_rules_less_conditions()
    calm = condition_cases(doc, "calm")[0]

    case_doc = condition_document(doc, calm)

    assert case_doc is not doc
    assert case_doc.environment.max_wind_speed_m_s == 7.0
    assert case_doc.environment.vessel_motion == CALM
    assert case_doc.environment.gravity_m_s2 == doc.environment.gravity_m_s2
    assert doc.environment.max_wind_speed_m_s == 20.0  # the document is not touched


def test_no_conditions_returns_empty_and_condition_cases_raises_keyerror():
    doc = _rules_less().model_copy(update={"conditions": {}})

    assert load_conditions(doc) == ()
    assert condition_names(doc) == ()
    with pytest.raises(KeyError, match="document has no load condition"):
        condition_cases(doc, None)
    with pytest.raises(KeyError, match="document has no load condition"):
        scene_case(doc, None)
    with pytest.raises(KeyError, match="nope"):
        condition_cases(doc, "nope")


# --- rules documents: one LoadCondition per (condition x profile case) --------------------


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
    assert scene_case(doc, "calm") == conditions[3]
    assert scene_case(doc, "calm", "Case I") == conditions[2]


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
        condition_cases(_rules_less(), "nope")


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
