"""Authored v13 contract: conditions own the hoist settings and chart points name conditions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from crane_statics.core.io import DocumentIOError, load_document
from crane_statics.data.authored_models import (
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AUTHORED_SCHEMA_VERSION,
    EXAMPLE_DOCUMENT,
    AuthoredConditionHoist,
    AuthoredDocument,
    AuthoredEnvironment,
    AuthoredPayloadHoist,
    format_authored_validation_error,
)
from crane_statics.data.migrate_v13 import migrate_document

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.yaml"))


def _v12_rules() -> dict:
    """A v12 rules document with a split main hoist and an auxiliary hoist."""
    return {
        "schema": {"name": "crane-statics", "version": "12.0.0"},
        "metadata": {"name": "Rules"},
        "model_definition": {
            "environment": {},
            "rules": {"standard": "DNV"},
            "conditions": {
                "onboard_sea": {
                    "wind_speed_m_s": 20.0,
                    "vessel_motion": {"accel_z_m_s2": 1.5, "roll_deg": 5.0},
                },
                "offboard_calm": {
                    "lift": "offboard",
                    "wind_speed_m_s": 12.0,
                    "significant_wave_height_m": 1.0,
                },
            },
            "structure": {
                "boom_width_m": 1.0,
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            },
            "hoists": {
                "BH": {"reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 4}]},
                "MH": {
                    "reeving": [
                        {"node": "winch", "body": "platform", "x_m": -5.0, "z_m": 3.0},
                        {"node": "tip", "body": "boom", "u_m": 100.0, "w_m": -1.0, "parts": 2},
                    ],
                    "lower_block_mass_t": 5.0,
                    "falls": 4,
                    "daf": 1.1,
                    "offlead_deg": 1.0,
                    "sidelead_deg": 2.5,
                    "load_chart": [{"outreach_m": 30.0, "load_t": 100.0}],
                    "split": {
                        "lower_block_mass_t": 2.0,
                        "falls": 2,
                        "load_chart": [{"outreach_m": 30.0, "load_t": 50.0}],
                    },
                },
                "AH": {
                    "reeving": [
                        {"node": "winch", "body": "platform", "x_m": -4.0, "z_m": 3.0},
                        {"node": "tip", "body": "boom", "u_m": 101.0, "w_m": -1.0},
                    ],
                    "lower_block_mass_t": 1.0,
                    "falls": 1,
                    "daf": 1.0,
                    "offlead_deg": 2.0,
                    "load_chart": [{"outreach_m": 40.0, "load_t": 20.0}],
                },
            },
        },
    }


def _v12_plain() -> dict:
    data = _v12_rules()
    md = data["model_definition"]
    del md["rules"], md["conditions"]
    md["environment"] = {"max_wind_speed_m_s": 20.0}
    md["vessel_motion"] = {"roll_deg": 2.0}
    return data


def _rules() -> dict:
    return migrate_document(_v12_rules())


def _plain() -> dict:
    return migrate_document(_v12_plain())


def _md(data: dict) -> dict:
    md: dict = data["model_definition"]
    return md


def _error(data: dict) -> str:
    with pytest.raises(ValidationError) as info:
        AuthoredDocument.model_validate(data)
    return format_authored_validation_error(info.value)


def test_version_is_13():
    assert AUTHORED_SCHEMA_MAJOR_VERSION == 13
    assert AUTHORED_SCHEMA_VERSION == "13.0.0"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_migrated_examples_validate(example):
    with open(example, encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)
    AuthoredDocument.model_validate(migrate_document(data))


def test_migrated_inline_documents_validate():
    rules = AuthoredDocument.model_validate(_rules())
    plain = AuthoredDocument.model_validate(_plain())
    settings = rules.model_definition.conditions["onboard_sea"].hoists["MH"]
    assert (settings.offlead_deg, settings.sidelead_deg, settings.daf) == (1.0, 2.5, 1.1)
    ah = rules.model_definition.conditions["offboard_calm"].hoists["AH"]
    assert (ah.offlead_deg, ah.sidelead_deg, ah.daf) == (2.0, 0.0, None)
    assert list(plain.model_definition.conditions) == ["default"]
    default = plain.model_definition.conditions["default"]
    assert default.wind_speed_m_s == 20.0
    assert default.vessel_motion.roll_deg == 2.0
    assert plain.model_definition.rules is None


def test_example_document_validates():
    AuthoredDocument.model_validate(deepcopy(EXAMPLE_DOCUMENT))


def test_removed_fields_rejected():
    with pytest.raises(ValidationError):
        AuthoredEnvironment(max_wind_speed_m_s=20.0)
    assert "daf" not in AuthoredPayloadHoist.model_fields
    assert "offlead_deg" not in AuthoredPayloadHoist.model_fields
    assert "sidelead_deg" not in AuthoredPayloadHoist.model_fields
    data = _plain()
    _md(data)["vessel_motion"] = {"roll_deg": 1.0}
    assert "vessel_motion" in _error(data)
    data = _plain()
    _md(data)["hoists"]["MH"]["daf"] = 1.1
    assert "daf" in _error(data)


def test_condition_hoist_defaults_and_bounds():
    entry = AuthoredConditionHoist(offlead_deg=1.0)
    assert entry.sidelead_deg == 0.0 and entry.daf is None
    with pytest.raises(ValidationError):
        AuthoredConditionHoist()
    with pytest.raises(ValidationError):
        AuthoredConditionHoist(offlead_deg=-1.0)
    with pytest.raises(ValidationError):
        AuthoredConditionHoist(offlead_deg=1.0, sidelead_deg=-0.5)


def test_daf_below_one_rejected():
    data = _rules()
    _md(data)["conditions"]["onboard_sea"]["hoists"]["MH"]["daf"] = 0.9
    message = _error(data)
    assert "onboard_sea" in message and "MH" in message and "daf" in message


def test_conditions_required():
    data = _plain()
    del _md(data)["conditions"]
    assert "conditions" in _error(data)


def test_rules_without_conditions_rejected_by_min_length():
    data = _rules()
    _md(data)["conditions"] = {}
    assert "conditions" in _error(data)


def test_condition_needs_at_least_one_hoist():
    data = _rules()
    _md(data)["conditions"]["onboard_sea"]["hoists"] = {}
    assert "onboard_sea" in _error(data)


def test_usable_hoist_without_chart_points_rejected():
    data = _rules()
    for point in _md(data)["hoists"]["AH"]["load_chart"]:
        point["conditions"] = ["onboard_sea"]
    message = _error(data)
    assert "offboard_calm" in message and "AH" in message


def test_chart_point_names_undefined_condition():
    data = _rules()
    _md(data)["hoists"]["AH"]["load_chart"][0]["conditions"] = ["onboard_sea", "onbaord_sea"]
    message = _error(data)
    assert "onbaord_sea" in message and "AH" in message and "load_chart" in message
    assert "0" in message


def test_split_point_names_undefined_condition():
    data = _rules()
    _md(data)["hoists"]["MH"]["split"]["load_chart"][0]["conditions"].append("nope")
    message = _error(data)
    assert "nope" in message and "MH" in message and "split" in message


def test_chart_point_conditions_required_nonempty_unique():
    data = _rules()
    del _md(data)["hoists"]["AH"]["load_chart"][0]["conditions"]
    assert "conditions" in _error(data)
    data = _rules()
    _md(data)["hoists"]["AH"]["load_chart"][0]["conditions"] = []
    assert "conditions" in _error(data)
    data = _rules()
    _md(data)["hoists"]["AH"]["load_chart"][0]["conditions"] = ["onboard_sea", "onboard_sea"]
    message = _error(data)
    assert "onboard_sea" in message and "conditions" in message


def test_boom_hoist_not_allowed_in_condition():
    data = _rules()
    _md(data)["conditions"]["onboard_sea"]["hoists"]["BH"] = {"offlead_deg": 0.0}
    message = _error(data)
    assert "onboard_sea" in message and "BH" in message


def test_condition_lists_nonexistent_hoist():
    data = _rules()
    _md(data)["conditions"]["onboard_sea"]["hoists"]["XH"] = {"offlead_deg": 0.0}
    message = _error(data)
    assert "onboard_sea" in message and "XH" in message


def test_hoist_unused_by_any_condition_rejected():
    data = _rules()
    for condition in _md(data)["conditions"].values():
        del condition["hoists"]["AH"]
    message = _error(data)
    assert "AH" in message and "condition" in message


def test_hoist_usable_in_one_condition_only_is_valid():
    data = _rules()
    del _md(data)["conditions"]["offboard_calm"]["hoists"]["AH"]
    for point in _md(data)["hoists"]["AH"]["load_chart"]:
        point["conditions"] = ["onboard_sea"]
    AuthoredDocument.model_validate(data)


def test_chart_point_naming_condition_without_the_hoist_rejected():
    data = _rules()
    del _md(data)["conditions"]["offboard_calm"]["hoists"]["AH"]
    message = _error(data)
    assert "hoists.AH.load_chart.0 names condition 'offboard_calm'" in message
    assert "does not list hoist 'AH'" in message


def test_split_point_naming_condition_without_the_hoist_rejected():
    data = _rules()
    del _md(data)["conditions"]["offboard_calm"]["hoists"]["MH"]
    for point in _md(data)["hoists"]["MH"]["load_chart"]:
        point["conditions"] = ["onboard_sea"]
    message = _error(data)
    assert "hoists.MH.split.load_chart.0 names condition 'offboard_calm'" in message
    assert "does not list hoist 'MH'" in message


def test_split_needs_split_points_per_usable_condition():
    data = _rules()
    for point in _md(data)["hoists"]["MH"]["split"]["load_chart"]:
        point["conditions"] = ["onboard_sea"]
    message = _error(data)
    assert "offboard_calm" in message and "MH" in message and "split" in message


def test_offboard_requires_rules():
    data = _plain()
    _md(data)["conditions"]["default"]["lift"] = "offboard"
    message = _error(data)
    assert "default" in message and "offboard" in message and "rules" in message


def test_several_conditions_without_rules_valid():
    data = _plain()
    md = _md(data)
    md["conditions"]["calm"] = deepcopy(md["conditions"]["default"])
    md["conditions"]["calm"]["wind_speed_m_s"] = 5.0
    for hoist in md["hoists"].values():
        for chart in (hoist.get("load_chart", []), hoist.get("split", {}).get("load_chart", [])):
            for point in chart:
                point["conditions"].append("calm")
    AuthoredDocument.model_validate(data)


def test_v12_document_rejected_with_version_message(tmp_path):
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(_v12_rules()), encoding="utf-8")
    with pytest.raises(DocumentIOError) as info:
        load_document(path)
    message = str(info.value)
    assert "Unsupported authored schema version '12.0.0'" in message
    assert "major version 13" in message
    assert "migrate_authored_v13" in message
    with pytest.raises(ValidationError):
        AuthoredDocument.model_validate(_v12_rules())


def test_schema_publishes_condition_hoists_and_point_conditions():
    schema = AuthoredDocument.model_json_schema()
    defs = schema["$defs"]
    assert "hoists" in defs["AuthoredCondition"]["required"]
    assert set(defs["AuthoredConditionHoist"]["properties"]) == {
        "offlead_deg",
        "sidelead_deg",
        "daf",
    }
    assert "conditions" in defs["AuthoredLoadChartPoint"]["required"]
    assert "conditions" in defs["AuthoredModelDefinition"]["required"]
    assert "vessel_motion" not in defs["AuthoredModelDefinition"]["properties"]
    assert "max_wind_speed_m_s" not in defs["AuthoredEnvironment"]["properties"]
    for removed in ("daf", "offlead_deg", "sidelead_deg"):
        assert removed not in defs["AuthoredPayloadHoist"]["properties"]
