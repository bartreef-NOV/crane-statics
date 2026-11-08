"""Authored and runtime models for rules, conditions, rope EA and hoisting speed."""

from copy import deepcopy
from pathlib import Path

import pytest

from crane_statics.core.io import DocumentIOError, load_document, save_document
from crane_statics.data import normalize_document

_ALL_EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.yaml"))
#: The ``*_abs``/``*_dnv`` examples carry rules; the others are legacy documents.
RULES_EXAMPLES = [p for p in _ALL_EXAMPLES if p.stem.endswith(("_abs", "_dnv"))]
EXAMPLES = [p for p in _ALL_EXAMPLES if p not in RULES_EXAMPLES]


def _authored() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "11.1.0"},
        "metadata": {"name": "Rules"},
        "model_definition": {
            "environment": {},
            "structure": {
                "boom_width_m": 1.0,
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            },
            "hoists": {
                "BH": {
                    "reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 4}],
                    "rope": {"ea_kN": 90000.0},
                },
                "MH": {
                    "reeving": [
                        {"node": "winch", "body": "platform", "x_m": -5.0, "z_m": 3.0},
                        {"node": "tip", "body": "boom", "u_m": 100.0, "w_m": -1.0, "parts": 2},
                    ],
                    "hook_mass_t": 5.0,
                    "falls": 4,
                    "daf": 1.1,
                    "offlead_deg": 1.0,
                    "rope": {"ea_kN": 40000.0},
                    "max_hoisting_speed_m_s": 0.25,
                    "load_chart": [{"outreach_m": 30.0, "load_t": 100.0}],
                },
            },
            "rules": {"standard": "DNV"},
            "conditions": {
                "onboard_sea": {
                    "wind_speed_m_s": 20.0,
                    "significant_wave_height_m": 2.5,
                    "vessel_motion": {"accel_z_m_s2": 1.5, "roll_deg": 5.0},
                },
                "offboard_calm": {
                    "lift": "offboard",
                    "wind_speed_m_s": 12.0,
                    "significant_wave_height_m": 1.0,
                    "v_in_m_s": 0.5,
                    "v_t_m_s": 0.8,
                    "load_wind_area_m2": 4.0,
                    "load_drag_coefficient": 1.2,
                    "hook_height_override_m": 15.0,
                },
            },
        },
    }


def _legacy() -> dict:
    data = _authored()
    md = data["model_definition"]
    del md["rules"], md["conditions"]
    for hoist in md["hoists"].values():
        hoist.pop("rope", None)
        hoist.pop("max_hoisting_speed_m_s", None)
    md["environment"] = {"max_wind_speed_m_s": 20.0}
    return data


def _error(data: dict) -> str:
    with pytest.raises(ValueError) as info:
        normalize_document(data)
    return str(info.value)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_legacy_examples_unchanged(example):
    doc = load_document(example)
    assert doc.rules is None
    assert doc.conditions == {}
    assert all(h.max_hoisting_speed_m_s is None for h in doc.hoists)
    assert all(r.axial_stiffness_kN is None for r in doc.ropes)


def test_rules_examples_carry_rules_and_offboard_inputs():
    assert [p.stem for p in RULES_EXAMPLES] == ["crane_input_GT283_abs", "crane_input_GT283_dnv"]
    for example in RULES_EXAMPLES:
        doc = load_document(example)
        assert doc.rules is not None and doc.rules.standard == example.stem[-3:].upper()
        assert doc.conditions
        assert all(r.axial_stiffness_kN is not None for r in doc.ropes)
        assert all(h.hook_daf == 1.0 for h in doc.hoists)


def test_rules_document_round_trips(tmp_path):
    doc = normalize_document(_authored())
    assert doc.rules.standard == "DNV"
    assert set(doc.conditions) == {"onboard_sea", "offboard_calm"}
    assert doc.conditions["onboard_sea"].vessel_motion.accel_z_m_s2 == 1.5
    assert doc.conditions["offboard_calm"].lift == "offboard"

    first = tmp_path / "a.yaml"
    second = tmp_path / "b.yaml"
    save_document(doc, first)
    reloaded = load_document(first)
    assert reloaded.rules == doc.rules
    assert reloaded.conditions == doc.conditions
    save_document(reloaded, second)
    assert second.read_text(encoding="utf-8") == first.read_text(encoding="utf-8")
    assert "max_wind_speed_m_s" not in first.read_text(encoding="utf-8")


def test_ea_speed_round_trip(tmp_path):
    data = _authored()
    hoists = data["model_definition"]["hoists"]
    hoists["MH"]["rope"] = {"ea_kN": 40000.0}
    hoists["MH"]["max_hoisting_speed_m_s"] = 0.25
    hoists["BH"]["rope"] = {"elastic_modulus_kN_mm2": 100.0, "metallic_area_mm2": 500.0}
    doc = normalize_document(data)
    path = tmp_path / "a.yaml"
    save_document(doc, path)
    reloaded = load_document(path)
    mh = next(h for h in reloaded.hoists if h.id == "MH")
    assert mh.max_hoisting_speed_m_s == 0.25
    assert reloaded.model_dump() == doc.model_dump()


def test_ea_pair_normalizes():
    data = _authored()
    data["model_definition"]["hoists"]["MH"]["rope"] = {
        "elastic_modulus_kN_mm2": 100.0,
        "metallic_area_mm2": 500.0,
    }
    data["model_definition"]["hoists"]["BH"]["rope"] = {"ea_kN": 123.0}
    doc = normalize_document(data)
    ropes = {r.id: r for r in doc.ropes}
    mh = ropes[next(h.rope_id for h in doc.hoists if h.id == "MH")]
    bh = ropes[next(h.rope_id for h in doc.hoists if h.id == "BH")]
    assert mh.axial_stiffness_kN == 50000.0
    assert bh.axial_stiffness_kN == 123.0


def test_rules_without_conditions_rejected():
    data = _authored()
    del data["model_definition"]["conditions"]
    assert "conditions" in _error(data)


def test_conditions_without_rules_rejected():
    data = _legacy()
    data["model_definition"]["conditions"] = {"c": {"wind_speed_m_s": 10.0}}
    assert "rules" in _error(data)


def test_vessel_motion_beside_rules_rejected():
    data = _authored()
    data["model_definition"]["vessel_motion"] = {"roll_deg": 3.0}
    assert "vessel_motion" in _error(data)


def test_max_wind_beside_rules_rejected():
    data = _authored()
    data["model_definition"]["environment"]["max_wind_speed_m_s"] = 20.0
    assert "max_wind_speed_m_s" in _error(data)


def test_max_wind_required_without_rules():
    data = _legacy()
    data["model_definition"]["environment"] = {}
    assert "max_wind_speed_m_s" in _error(data)


def test_ea_with_modulus_rejected():
    data = _authored()
    data["model_definition"]["hoists"]["MH"]["rope"] = {
        "ea_kN": 1000.0,
        "elastic_modulus_kN_mm2": 100.0,
    }
    assert "ea_kN" in _error(data)


def test_modulus_without_area_rejected():
    data = _authored()
    data["model_definition"]["hoists"]["MH"]["rope"] = {"elastic_modulus_kN_mm2": 100.0}
    assert "metallic_area_mm2" in _error(data)


def test_legacy_document_round_trips_without_new_keys(tmp_path):
    doc = normalize_document(_legacy())
    path = tmp_path / "a.yaml"
    save_document(doc, path)
    text = path.read_text(encoding="utf-8")
    for key in ("rules", "conditions", "ea_kN", "max_hoisting_speed_m_s"):
        assert key not in text


def test_rules_error_surfaces_through_load(tmp_path):
    data = deepcopy(_authored())
    del data["model_definition"]["conditions"]
    import yaml

    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(DocumentIOError, match="conditions"):
        load_document(path)
