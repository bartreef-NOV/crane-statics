"""The vessel-motion reference point belongs to the crane (``structure.motion_reference``),
not to a condition: schema v14, its migration from v13, the round trip and the form edit."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from crane_statics.core.io import load_document, save_document
from crane_statics.data.authored_models import AuthoredDocument, AuthoredVesselMotion
from crane_statics.data.migrate_v14 import migrate_document, migrate_file
from crane_statics.qml_app.models.document_forms import (
    condition_fields,
    environment_settings,
    set_environment_value,
)
from tests.authored_helpers import example_dict, example_path

EXAMPLE = "crane_input_GT283.yaml"


def _v13(*references: tuple[float, float]) -> dict:
    """The GT283 example as a v13 document with one condition per reference point."""
    data = example_dict(EXAMPLE)
    data["schema"]["version"] = "13.0.0"
    md = data["model_definition"]
    md["structure"].pop("motion_reference", None)
    first = next(iter(md["conditions"].values()))
    md["conditions"] = {}
    for index, (x, z) in enumerate(references):
        condition = deepcopy(first)
        condition["vessel_motion"] = {"roll_deg": 2.0, "reference_x_m": x, "reference_z_m": z}
        md["conditions"][f"c{index}"] = condition
    for hoist in md["hoists"].values():
        for point in hoist.get("load_chart", []):
            point["conditions"] = list(md["conditions"])
    return data


def test_a_condition_no_longer_takes_a_reference_point() -> None:
    with pytest.raises(ValidationError):
        AuthoredVesselMotion.model_validate({"reference_x_m": 1.0})


def test_migration_moves_the_reference_to_the_structure() -> None:
    migrated = migrate_document(_v13((3.0, -2.0), (3.0, -2.0)))
    md = migrated["model_definition"]
    assert migrated["schema"]["version"] == "14.0.0"
    assert md["structure"]["motion_reference"] == {"x_m": 3.0, "z_m": -2.0}
    assert list(md["structure"]).index("motion_reference") < list(md["structure"]).index(
        "boom_heel"
    )
    for condition in md["conditions"].values():
        assert condition["vessel_motion"] == {"roll_deg": 2.0}
    AuthoredDocument.model_validate(migrated)


def test_migration_omits_a_zero_reference() -> None:
    migrated = migrate_document(_v13((0.0, 0.0)))
    assert "motion_reference" not in migrated["model_definition"]["structure"]


def test_migration_refuses_conditions_that_disagree() -> None:
    with pytest.raises(ValueError, match="disagree") as info:
        migrate_document(_v13((3.0, -2.0), (0.0, 0.0)))
    assert "c0: x 3, z -2" in str(info.value)


def test_migration_does_not_touch_its_input() -> None:
    data = _v13((3.0, -2.0))
    before = deepcopy(data)
    migrate_document(data)
    assert data == before


def test_migrate_file_rewrites_the_file(tmp_path: Path) -> None:
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(_v13((1.5, 0.5)), sort_keys=False), encoding="utf-8")
    migrate_file(path)
    doc = load_document(path)
    assert doc.motion_reference.reference_x_m == 1.5
    assert doc.motion_reference.reference_z_m == 0.5


def test_the_reference_round_trips_through_save_and_load(tmp_path: Path) -> None:
    doc = load_document(example_path(EXAMPLE))
    doc.motion_reference.reference_x_m = 4.0
    doc.motion_reference.reference_z_m = -1.5
    out = tmp_path / "out.yaml"
    save_document(doc, out)
    saved = yaml.safe_load(out.read_text(encoding="utf-8"))
    md = saved["model_definition"]
    assert md["structure"]["motion_reference"] == {"x_m": 4.0, "z_m": -1.5}
    assert all("reference_x_m" not in c.get("vessel_motion", {}) for c in md["conditions"].values())
    again = load_document(out)
    assert again.motion_reference == doc.motion_reference


def test_the_form_edits_the_crane_reference_and_conditions_do_not_show_it() -> None:
    doc = load_document(example_path(EXAMPLE))
    assert set_environment_value(doc, "reference_x_m", 2.5)
    assert set_environment_value(doc, "reference_z_m", -0.5)
    assert not set_environment_value(doc, "reference_z_m", -0.5)  # unchanged
    settings = environment_settings(doc)
    assert (settings["reference_x_m"], settings["reference_z_m"]) == (2.5, -0.5)
    for spec in doc.conditions.values():
        fields = condition_fields(spec)
        assert "reference_x_m" not in fields and "reference_z_m" not in fields
