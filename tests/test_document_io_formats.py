"""Tests for JSON/YAML format dispatch in document load/save."""

import json

import pytest
import yaml

from crane_statics.core import create_default_document, load_document
from crane_statics.core.io import DocumentIOError, save_document


def _minimal_v5() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "5.13.0"},
        "metadata": {"name": "V5 Minimal"},
        "model_definition": {
            "boom_width_m": 1.0,
            "slewing_bearing_diameter_m": 1.0,
            "environment": {
                "gravity_m_s2": 9.81,
                "air_density_kg_m3": 1.225,
                "wind_profile_exponent": 0.143,
                "wind_reference_height_m_asl": 10.0,
                "mean_sealevel_z_m": -35.0,
                "max_wind_speed_m_s": 20.0,
            },
            "vessel_motion": {
                "accel_x_m_s2": 0.0,
                "accel_y_m_s2": 0.0,
                "accel_z_m_s2": 0.0,
                "pitch_angular_accel_rad_s2": 0.0,
                "roll_angular_accel_rad_s2": 0.0,
                "reference_x_m": 0.0,
                "reference_z_m": 0.0,
            },
            "boom_heel": {"x_m": 8.5, "z_m": 8.0},
            "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
            "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
            "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            "boom": {
                "mass_points": [],
                "wind_areas": [],
                "nodes": {"mh_hook": {"u_m": 40.0, "w_m": -2.0}},
            },
            "rear_leg": {"mass_points": [], "wind_areas": [], "nodes": {}},
            "front_leg": {"mass_points": [], "wind_areas": [], "nodes": {}},
            "platform": {"mass_points": [], "wind_areas": [], "nodes": {}},
            "payload_hoists": {
                "MH": {
                    "support_node_id": "mh_hook",
                    "hook_daf": 1.0,
                    "offlead_deg": 0.0,
                    "rope_segments": [{"from": "boom_heel", "to": "mh_hook"}],
                    "falls": 1,
                    "hook_mass_t": 0.0,
                    "contractual_points": [{"outreach_m": 0.0, "load_t": 0.0}],
                }
            },
            "boom_hoist": {
                "rope_segments": [{"from": "boom_heel", "to": "rear_top", "parts": 2}],
            },
        },
    }


def test_load_document_accepts_yaml_extension(tmp_path):
    data = _minimal_v5()
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doc = load_document(path)

    assert doc.metadata.name == "V5 Minimal"


def test_load_document_accepts_yml_extension(tmp_path):
    data = _minimal_v5()
    path = tmp_path / "model.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doc = load_document(path)

    assert doc.metadata.name == "V5 Minimal"


def test_save_document_writes_yaml_for_yaml_path(tmp_path):
    doc = create_default_document()
    path = tmp_path / "out.yaml"

    save_document(doc, path)

    with open(path, "r", encoding="utf-8") as f:
        on_disk = yaml.safe_load(f)
    assert on_disk["schema"]["name"] == "crane-statics"
    assert on_disk["metadata"]["name"] == "New Crane Model"
    with pytest.raises(json.JSONDecodeError):
        json.loads(path.read_text(encoding="utf-8"))


def test_save_document_still_writes_json_for_json_path(tmp_path):
    doc = create_default_document()
    path = tmp_path / "out.json"

    save_document(doc, path)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema"]["name"] == "crane-statics"
    assert on_disk["metadata"]["name"] == "New Crane Model"


def test_load_document_rejects_unknown_extension(tmp_path):
    path = tmp_path / "model.txt"
    path.write_text("irrelevant", encoding="utf-8")

    with pytest.raises(DocumentIOError, match="Unsupported file extension"):
        load_document(path)


def test_load_document_reports_malformed_yaml_as_document_io_error(tmp_path):
    path = tmp_path / "model.yaml"
    path.write_text("key: value:\n  bad indentation: [unbalanced", encoding="utf-8")

    with pytest.raises(DocumentIOError, match="Failed to read file"):
        load_document(path)


def test_yaml_and_json_round_trip_to_the_same_document(tmp_path):
    data = _minimal_v5()
    json_path = tmp_path / "model.json"
    yaml_path = tmp_path / "model.yaml"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doc_json = load_document(json_path)
    doc_yaml = load_document(yaml_path)

    assert doc_json.model_dump() == doc_yaml.model_dump()


def test_save_then_reload_preserves_a_yaml_document(tmp_path):
    doc = create_default_document()
    path = tmp_path / "m.yaml"

    save_document(doc, path)
    reloaded = load_document(path)

    assert reloaded.metadata.name == doc.metadata.name
