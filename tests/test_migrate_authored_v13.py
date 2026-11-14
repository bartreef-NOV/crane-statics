"""Tests for the authored v12 -> v13 migration."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from crane_statics.data.migrate_v13 import migrate_document, migrate_file

EXAMPLES = Path(__file__).parent.parent / "examples"
MOTION = {"accel_x_m_s2": 0.3, "roll_deg": 2.0}


def _hoists() -> dict:
    return {
        "BH": {"rope": {"linear_mass_kg_m": 20.3}, "reeving": []},
        "MH": {
            "rope": {"linear_mass_kg_m": 9.17},
            "reeving": [],
            "hook_mass_t": 50.0,
            "falls": 20,
            "daf": 1.1,
            "offlead_deg": 1.0,
            "sidelead_deg": 2.5,
            "load_chart": [{"outreach_m": 16.0, "load_t": 1000.0}],
            "split": {
                "hook_mass_t": 10.0,
                "falls": 10,
                "load_chart": [{"outreach_m": 16.0, "load_t": 500.0}],
            },
        },
        "AH": {
            "rope": {"linear_mass_kg_m": 5.83},
            "reeving": [],
            "hook_mass_t": 7.0,
            "falls": 6,
            "daf": 1.0,
            "offlead_deg": 2.0,
            "sidelead_deg": 0.0,
            "load_chart": [{"outreach_m": 23.0, "load_t": 160.0}],
        },
    }


def _v12_plain() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "12.0.0"},
        "metadata": {"name": "x"},
        "model_definition": {
            "environment": {"gravity_m_s2": 9.81, "max_wind_speed_m_s": 20.0},
            "vessel_motion": dict(MOTION),
            "structure": {"boom_width_m": 10.0},
            "hoists": _hoists(),
        },
    }


def _v12_rules() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "12.0.0"},
        "metadata": {"name": "x"},
        "model_definition": {
            "environment": {"gravity_m_s2": 9.81},
            "rules": {"standard": "ABS", "crane_class": "offshore"},
            "conditions": {
                "onboard_sea": {"wind_speed_m_s": 20.0, "vessel_motion": dict(MOTION)},
                "offboard_supply": {
                    "lift": "offboard",
                    "wind_speed_m_s": 15.0,
                    "vessel_motion": dict(MOTION),
                    "significant_wave_height_m": 1.5,
                },
            },
            "structure": {"boom_width_m": 10.0},
            "hoists": _hoists(),
        },
    }


def _md(doc: dict) -> dict:
    md: dict = doc["model_definition"]
    return md


def test_no_rules_gets_default_condition():
    out = migrate_document(_v12_plain())
    md = _md(out)
    assert md["conditions"]["default"]["wind_speed_m_s"] == 20.0
    assert md["conditions"]["default"]["vessel_motion"] == MOTION
    assert "max_wind_speed_m_s" not in md["environment"]
    assert "vessel_motion" not in md
    assert list(md["conditions"]["default"]) == ["wind_speed_m_s", "vessel_motion", "hoists"]


def test_no_rules_without_vessel_motion_omits_it():
    doc = _v12_plain()
    del _md(doc)["vessel_motion"]
    cond = _md(migrate_document(doc))["conditions"]["default"]
    assert "vessel_motion" not in cond


def test_rules_document_keeps_conditions_and_adds_hoists():
    md = _md(migrate_document(_v12_rules()))
    assert list(md["conditions"]) == ["onboard_sea", "offboard_supply"]
    assert md["conditions"]["offboard_supply"]["lift"] == "offboard"
    assert list(md["conditions"]["offboard_supply"])[-1] == "hoists"
    for cond in md["conditions"].values():
        assert cond["hoists"]["MH"] == {"offlead_deg": 1.0, "sidelead_deg": 2.5, "daf": 1.1}
        assert list(cond["hoists"]["MH"]) == ["offlead_deg", "sidelead_deg", "daf"]
        assert "BH" not in cond["hoists"]


def test_daf_one_and_zero_sidelead_omitted():
    md = _md(migrate_document(_v12_plain()))
    assert md["conditions"]["default"]["hoists"]["AH"] == {"offlead_deg": 2.0}


def test_chart_points_tagged_with_every_condition():
    md = _md(migrate_document(_v12_rules()))
    names = ["onboard_sea", "offboard_supply"]
    mh = md["hoists"]["MH"]
    assert mh["load_chart"] == [{"outreach_m": 16.0, "load_t": 1000.0, "conditions": names}]
    assert mh["split"]["load_chart"][0]["conditions"] == names
    assert list(mh["split"]["load_chart"][0]) == ["outreach_m", "load_t", "conditions"]
    assert md["hoists"]["AH"]["load_chart"][0]["conditions"] == names


def test_hoist_loses_lead_fields():
    md = _md(migrate_document(_v12_plain()))
    for hoist in md["hoists"].values():
        for key in ("daf", "offlead_deg", "sidelead_deg"):
            assert key not in hoist


def test_version_bumped():
    assert migrate_document(_v12_plain())["schema"]["version"] == "13.0.0"


def test_input_not_mutated():
    doc = _v12_rules()
    snapshot = copy.deepcopy(doc)
    migrate_document(doc)
    assert doc == snapshot


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.name)
def test_examples_migrate_cleanly(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["schema"]["version"] = "12.0.0"  # examples are not yet bumped (done in a later task)
    out = migrate_document(doc)
    md = _md(out)
    names = list(md["conditions"])
    assert out["schema"]["version"] == "13.0.0"
    for hid, hoist in md["hoists"].items():
        for key in ("daf", "offlead_deg", "sidelead_deg"):
            assert key not in hoist
        if hid == "BH":
            continue
        charts = [hoist["load_chart"]]
        if "split" in hoist:
            charts.append(hoist["split"]["load_chart"])
        for chart in charts:
            assert all(p["conditions"] == names for p in chart)
        for cond in md["conditions"].values():
            assert hid in cond["hoists"]


def test_v13_document_rejected():
    out = migrate_document(_v12_plain())
    with pytest.raises(ValueError, match="13.0.0"):
        migrate_document(out)


def test_missing_schema_block_rejected():
    doc = _v12_plain()
    del doc["schema"]
    with pytest.raises(ValueError, match="schema"):
        migrate_document(doc)
    doc = _v12_plain()
    del doc["model_definition"]
    with pytest.raises(ValueError, match="model_definition"):
        migrate_document(doc)


def test_migrate_file_in_place_then_refuses_second_run(tmp_path: Path):
    target = tmp_path / "doc.yaml"
    target.write_text(yaml.safe_dump(_v12_plain(), sort_keys=False), encoding="utf-8")

    migrate_file(target)
    migrated_text = target.read_text(encoding="utf-8")
    assert yaml.safe_load(migrated_text)["schema"]["version"] == "13.0.0"

    with pytest.raises(ValueError, match="doc.yaml"):
        migrate_file(target)
    assert target.read_text(encoding="utf-8") == migrated_text
