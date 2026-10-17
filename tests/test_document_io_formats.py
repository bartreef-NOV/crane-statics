"""Tests for JSON/YAML format dispatch in document load/save."""

import json

import pytest
import yaml

from crane_statics.core import create_default_document, load_document
from crane_statics.core.io import DocumentIOError, save_document


def _minimal_v6() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "7.0.0"},
        "metadata": {"name": "V6 Minimal"},
        "model_definition": {
            "environment": {
                "gravity_m_s2": 9.81,
                "air_density_kg_m3": 1.225,
                "max_wind_speed_m_s": 20.0,
            },
            "structure": {
                "boom_width_m": 1.0,
                "slewing_bearing_diameter_m": 1.0,
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            },
            "boom_hoist": {
                "reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 2}],
            },
            "payload_hoists": {
                "MH": {
                    "reeving": [
                        {"node": "boom_heel"},
                        {"node": "hook", "body": "boom", "u_m": 40.0, "w_m": -2.0},
                    ],
                    "hook": {"mass_t": 0.0, "falls": 1, "daf": 1.0, "offlead_deg": 0.0},
                    "load_chart": [{"outreach_m": 0.0, "load_t": 0.0}],
                }
            },
        },
    }


def test_load_document_accepts_yaml_extension(tmp_path):
    data = _minimal_v6()
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doc = load_document(path)

    assert doc.metadata.name == "V6 Minimal"


def test_load_document_accepts_yml_extension(tmp_path):
    data = _minimal_v6()
    path = tmp_path / "model.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doc = load_document(path)

    assert doc.metadata.name == "V6 Minimal"


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
    data = _minimal_v6()
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


def test_load_document_does_not_misread_leading_zero_as_octal(tmp_path):
    """YAML 1.1's safe_load reads bare `020` as octal 16; a hand-edited crane
    file meaning twenty falls must not silently become sixteen."""
    data = _minimal_v6()
    yaml_text = yaml.safe_dump(data).replace("falls: 1\n", "falls: 020\n", 1)
    assert "falls: 020\n" in yaml_text
    path = tmp_path / "model.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    doc = load_document(path)

    hoist = next(h for h in doc.hoists if h.id == "MH")
    assert hoist.falls == 20


def test_load_document_rejects_sexagesimal_looking_int(tmp_path):
    """YAML 1.1's safe_load reads `1:20` as sexagesimal (80); such ambiguous
    input must fail validation rather than silently resolve to a number."""
    data = _minimal_v6()
    yaml_text = yaml.safe_dump(data).replace("falls: 1\n", "falls: 1:20\n", 1)
    assert "falls: 1:20\n" in yaml_text
    path = tmp_path / "model.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(DocumentIOError):
        load_document(path)


def test_load_document_reports_invalid_encoding_as_document_io_error(tmp_path):
    path = tmp_path / "model.yaml"
    path.write_bytes(b"\xff\xfe\x00\x01invalid utf-8")

    with pytest.raises(DocumentIOError, match="Failed to read file"):
        load_document(path)


def test_load_document_rejects_schema_v6(tmp_path):
    data = _minimal_v6()
    data["schema"]["version"] = "6.0.0"
    path = tmp_path / "model.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(DocumentIOError, match="Unsupported authored schema version"):
        load_document(path)


def test_signed_vessel_motion_round_trips(tmp_path):
    data = _minimal_v6()
    data["model_definition"]["vessel_motion"] = {"accel_x_m_s2": -1.0, "roll_deg": -3.0}
    path = tmp_path / "model.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    doc = load_document(path)
    out = tmp_path / "out.json"
    save_document(doc, out)
    saved = json.loads(out.read_text(encoding="utf-8"))

    vm = saved["model_definition"]["vessel_motion"]
    assert vm["accel_x_m_s2"] == -1.0
    assert vm["roll_deg"] == -3.0
    assert load_document(out).environment.vessel_motion.roll_deg == -3.0
