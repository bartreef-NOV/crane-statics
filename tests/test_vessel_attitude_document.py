"""Vessel heel and trim as an optional, signed design condition in the document."""

import copy

import pytest
import yaml

from crane_statics.core.io import DocumentIOError, load_document, save_document
from crane_statics.data.authored_models import AUTHORED_SCHEMA_VERSION
from crane_statics.data.models import VesselMotion
from tests.test_document_io_formats import _minimal_v6


def _with_vessel_motion(**values: float) -> dict:
    data = copy.deepcopy(_minimal_v6())
    data["schema"]["version"] = "6.1.0"
    data["model_definition"]["vessel_motion"] = dict(values)
    return data


def _load(tmp_path, data: dict):
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_document(path)


def test_schema_version_is_bumped_for_the_new_optional_fields():
    assert AUTHORED_SCHEMA_VERSION == "6.2.0"


def test_heel_and_trim_load_with_their_signs(tmp_path):
    doc = _load(tmp_path, _with_vessel_motion(heel_deg=3.0, trim_deg=-1.5))

    assert doc.environment.vessel_motion.heel_deg == 3.0
    assert doc.environment.vessel_motion.trim_deg == -1.5


def test_omitted_heel_and_trim_mean_a_level_vessel(tmp_path):
    doc = _load(tmp_path, _minimal_v6())

    assert doc.environment.vessel_motion.heel_deg == 0.0
    assert doc.environment.vessel_motion.trim_deg == 0.0


@pytest.mark.parametrize("field", ["heel_deg", "trim_deg"])
@pytest.mark.parametrize("value", [30.5, -30.5])
def test_out_of_range_attitude_is_rejected(tmp_path, field, value):
    with pytest.raises(DocumentIOError):
        _load(tmp_path, _with_vessel_motion(**{field: value}))


def test_accelerations_stay_non_negative(tmp_path):
    with pytest.raises(DocumentIOError):
        _load(tmp_path, _with_vessel_motion(accel_x_m_s2=-0.1))


def test_runtime_vessel_motion_accepts_a_negative_attitude():
    motion = VesselMotion(heel_deg=-2.0, trim_deg=-1.0)
    assert (motion.heel_deg, motion.trim_deg) == (-2.0, -1.0)


def test_save_round_trips_a_tilted_vessel(tmp_path):
    doc = _load(tmp_path, _with_vessel_motion(heel_deg=2.5, trim_deg=-0.5))
    out = tmp_path / "saved.yaml"

    save_document(doc, out)

    on_disk = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert on_disk["schema"]["version"] == "6.2.0"
    motion = on_disk["model_definition"]["vessel_motion"]
    assert (motion["heel_deg"], motion["trim_deg"]) == (2.5, -0.5)
    reloaded = load_document(out)
    assert reloaded.environment.vessel_motion.heel_deg == 2.5
    assert reloaded.environment.vessel_motion.trim_deg == -0.5


def test_save_omits_a_level_attitude(tmp_path):
    doc = _load(tmp_path, _with_vessel_motion(accel_x_m_s2=0.3))
    out = tmp_path / "saved.yaml"

    save_document(doc, out)

    motion = yaml.safe_load(out.read_text(encoding="utf-8"))["model_definition"]["vessel_motion"]
    assert motion["accel_x_m_s2"] == 0.3
    assert "heel_deg" not in motion and "trim_deg" not in motion


def test_a_6_0_document_still_loads(tmp_path):
    data = _minimal_v6()
    assert data["schema"]["version"] == "6.0.0"
    assert _load(tmp_path, data).environment.vessel_motion.heel_deg == 0.0
